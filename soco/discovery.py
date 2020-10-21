# -*- coding: utf-8 -*-
"""This module contains methods for discovering Sonos devices on the
network."""

from __future__ import unicode_literals

import logging
import socket
import select
from textwrap import dedent
import time
import struct
import ipaddress
import threading
import ifaddr

from . import config
from .utils import really_utf8

_LOG = logging.getLogger(__name__)

# pylint: disable=too-many-locals, too-many-branches


def discover(
    timeout=5,
    include_invisible=False,
    interface_addr=None,
    allow_network_scan=False,
    min_netmask=24,
):
    """Discover Sonos zones on the local network.

    Return a set of `SoCo` instances for each zone found.
    Include invisible zones (bridges and slave zones in stereo pairs if
    ``include_invisible`` is `True`. Will block for up to ``timeout`` seconds,
     after which return `None` if no zones found.

    Args:
        timeout (int, optional): block for this many seconds, at most.
            Defaults to 5.
        include_invisible (bool, optional): include invisible zones in the
            return set. Defaults to `False`.
        interface_addr (str or None): Discovery operates by sending UDP
            multicast datagrams. ``interface_addr`` is a string (dotted
            quad) representation of the network interface address to use as
            the source of the datagrams (i.e. it is a value for
            `socket.IP_MULTICAST_IF <socket>`). If `None` or not specified,
            the system default interface for UDP multicast messages will be
            used. This is probably what you want to happen. Defaults to
            `None`.
        allow_network_scan (bool, optional): If normal discovery fails, fall
            back to a scan of the attached network(s) to detect Sonos
            devices.
        min_netmask (int, optional): The minimum number of netmask bits. Used to
            constrain the network search space when network scanning is
            used.
    Returns:
        set: a set of `SoCo` instances, one for each zone found, or else
            `None`.

    Note:
        There is no easy cross-platform way to find out the addresses of the
        local machine's network interfaces. You might try the
        `netifaces module <https://pypi.python.org/pypi/netifaces>`_ and some
        code like this:

            >>> from netifaces import interfaces, AF_INET, ifaddresses
            >>> data = [ifaddresses(i) for i in interfaces()]
            >>> [d[AF_INET][0]['addr'] for d in data if d.get(AF_INET)]
            ['127.0.0.1', '192.168.1.20']

            This should provide you with a list of values to try for
            interface_addr if you are having trouble finding your Sonos devices

    """

    def create_socket(interface_addr=None):
        """A helper function for creating a socket for discover purposes.

        Create and return a socket with appropriate options set for multicast.
        """

        _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # UPnP v1.0 requires a TTL of 4
        _sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack("B", 4)
        )
        if interface_addr is not None:
            _sock.setsockopt(
                socket.IPPROTO_IP,
                socket.IP_MULTICAST_IF,
                socket.inet_aton(interface_addr),
            )
        return _sock

    # pylint: disable=invalid-name
    PLAYER_SEARCH = dedent(
        """\
        M-SEARCH * HTTP/1.1
        HOST: 239.255.255.250:1900
        MAN: "ssdp:discover"
        MX: 1
        ST: urn:schemas-upnp-org:device:ZonePlayer:1
        """
    ).encode("utf-8")
    MCAST_GRP = "239.255.255.250"
    MCAST_PORT = 1900

    _sockets = []
    # Use the specified interface, if any
    if interface_addr is not None:
        try:
            address = socket.inet_aton(interface_addr)
        except socket.error as e:
            raise ValueError(
                "{0} is not a valid IP address string".format(interface_addr)
            ) from e
        _sockets.append(create_socket(interface_addr))
        _LOG.info("Sending discovery packets on default interface")
    else:
        # Find the local network address using a couple of different methods.
        # Create a socket for each unique address found, and one for the
        # default multicast address
        addresses = set()
        try:
            addresses.add(socket.gethostbyname(socket.gethostname()))
        except socket.error:
            pass
        try:
            addresses.add(socket.gethostbyname(socket.getfqdn()))
        except socket.error:
            pass
        for address in addresses:
            try:
                _sockets.append(create_socket(address))
            except socket.error as e:
                _LOG.warning(
                    "Can't make a discovery socket for %s: %s: %s",
                    address,
                    e.__class__.__name__,
                    e,
                )
        # Add a socket using the system default address
        _sockets.append(create_socket())
        # Used to be logged as:
        # list(s.getsockname()[0] for s in _sockets)
        # but getsockname fails on Windows with unconnected unbound sockets
        # https://bugs.python.org/issue1049
        _LOG.info("Sending discovery packets on %s", _sockets)

    for _ in range(0, 3):
        # Send a few times to each socket. UDP is unreliable
        for _sock in _sockets:
            _sock.sendto(really_utf8(PLAYER_SEARCH), (MCAST_GRP, MCAST_PORT))

    t0 = time.time()
    while True:
        # Check if the timeout is exceeded. We could do this check just
        # before the currently only continue statement of this loop,
        # but I feel it is safer to do it here, so that we do not forget
        # to do it if/when another continue statement is added later.
        # Note: this is sensitive to clock adjustments. AFAIK there
        # is no monotonic timer available before Python 3.3.
        t1 = time.time()
        if t1 - t0 > timeout:
            return None

        # The timeout of the select call is set to be no greater than
        # 100ms, so as not to exceed (too much) the required timeout
        # in case the loop is executed more than once.
        response, _, _ = select.select(_sockets, [], [], min(timeout, 0.1))

        # Only Zone Players should respond, given the value of ST in the
        # PLAYER_SEARCH message. However, to prevent misbehaved devices
        # on the network disrupting the discovery process, we check that
        # the response contains the "Sonos" string; otherwise we keep
        # waiting for a correct response.
        #
        # Here is a sample response from a real Sonos device (actual numbers
        # have been redacted):
        # HTTP/1.1 200 OK
        # CACHE-CONTROL: max-age = 1800
        # EXT:
        # LOCATION: http://***.***.***.***:1400/xml/device_description.xml
        # SERVER: Linux UPnP/1.0 Sonos/26.1-76230 (ZPS3)
        # ST: urn:schemas-upnp-org:device:ZonePlayer:1
        # USN: uuid:RINCON_B8*************00::urn:schemas-upnp-org:device:
        #                                                     ZonePlayer:1
        # X-RINCON-BOOTSEQ: 3
        # X-RINCON-HOUSEHOLD: Sonos_7O********************R7eU

        if response:
            for _sock in response:
                data, addr = _sock.recvfrom(1024)
                _LOG.debug('Received discovery response from %s: "%s"', addr, data)
                if b"Sonos" in data:
                    # Now we have an IP, we can build a SoCo instance and query
                    # that player for the topology to find the other players.
                    # It is much more efficient to rely upon the Zone
                    # Player's ability to find the others, than to wait for
                    # query responses from them ourselves.
                    zone = config.SOCO_CLASS(addr[0])
                    if include_invisible:
                        return zone.all_zones
                    else:
                        return zone.visible_zones
        elif allow_network_scan:
            _LOG.info("Falling back to network scan discovery")
            return scan_network(
                min_netmask=min_netmask, include_invisible=include_invisible
            )


def any_soco(allow_network_scan=False, min_netmask=24):
    """Return any visible soco device, for when it doesn't matter which.

    Try to obtain an existing instance, or use `discover` if necessary.
    Note that this assumes that the existing instance has not left
    the network.

    Args:
        allow_network_scan (bool, optional): If normal discovery fails, fall
            back to a scan of the attached network(s) to detect Sonos
            devices.
        min_netmask (int, optional): The minimum number of netmask bits. Used to
            constrain the network search space when network scanning is
            used.

    Returns:
        SoCo: A `SoCo` instance (or subclass if `config.SOCO_CLASS` is set,
            or `None` if no instances are found
    """

    cls = config.SOCO_CLASS
    # pylint: disable=no-member, protected-access
    try:
        # Try to get the first pre-existing soco instance we know about,
        # as long as it is visible (i.e. not a bridge etc). Otherwise,
        # perform discovery (again, excluding invisibles) and return one of
        # those
        device = next(
            d for d in cls._instances[cls._class_group].values() if d.is_visible
        )
    except (KeyError, StopIteration):
        devices = discover(
            allow_network_scan=allow_network_scan, min_netmask=min_netmask
        )
        return None if devices is None else devices.pop()

    return device


def by_name(name, allow_network_scan=False, min_netmask=24):
    """Return a device by name.

    Args:
        name (str): The name of the device to return.
        allow_network_scan (bool, optional): If normal discovery fails, fall
            back to a scan of the attached network(s) to detect Sonos
            devices.
        min_netmask (int, optional): The minimum number of netmask bits. Used to
            constrain the network search space when network scanning is
            used.

    Returns:
        :class:`~.SoCo`: The first device encountered among all zone with the
            given player name. If none are found `None` is returned.
    """
    devices = discover(allow_network_scan=allow_network_scan, min_netmask=min_netmask)
    if devices is None:
        return None

    for device in devices:
        if device.player_name == name:
            return device
    return None


def scan_network(max_threads=256, timeout=3.0, min_netmask=24, include_invisible=False):
    """Scan all attached networks for Sonos devices.

    Scans the IPv4 network attached to each interface to check for network devices
    with port 1400 open. Check IPs in parallel threads for efficiency. Once the first
    Sonos device is found, stop checking and use that device to find the other
    devices. Returns a set of `SoCo` instances, or `None` if no Sonos devices are
    discovered.

    This function is intended for use when the usual discovery functions aren't
    working, perhaps due to multicast problems on the network to which the SoCo
    host is attached.

    Args:
        max_threads (int, optional): The maximum number of threads to use when scanning the
            network.
        timeout (float, optional): The network timeout in seconds to use when checking
            each IP address for a Sonos device
        min_netmask (int, optional): The minimum number of netmask bits. Used to
                constrain the network search space.
        include_invisible (bool, optional): Whether to include invisible Sonos devices in
            the set of devices returned.

    Returns:
        set: A set of `SoCo` instances, one for each zone found, or else `None`.
    """

    def is_ipv4_address(ip_address):
        """Helper function to test for an IPv4 address."""
        try:
            ipaddress.IPv4Network(ip_address)
            return True
        except ValueError:
            return False

    def find_ipv4_networks(min_netmask):
        """Helper function to return a set of IPv4 networks to which
        this node is attached.

        Args:
            min_netmask (int): The minimum number of netmask bits. Used to
                constrain the network search space.

        Returns:
            set: A set of attached networks.
        """
        ipv4_net_list = set()
        adapters = ifaddr.get_adapters()
        for adapter in adapters:
            for ip_address in adapter.ips:
                if is_ipv4_address(ip_address.ip):
                    network_ip = ipaddress.ip_network(ip_address.ip)
                    # Restrict to private networks and exclude loopback
                    if network_ip.is_private and not network_ip.is_loopback:
                        # Constrain the size of network that will be searched
                        if ip_address.network_prefix < min_netmask:
                            ip_address.network_prefix = min_netmask
                        network = ipaddress.ip_network(
                            ip_address.ip + "/" + str(ip_address.network_prefix), False
                        )
                        ipv4_net_list.add(network)
        _LOG.info("List of networks to search: {}".format(ipv4_net_list))
        return ipv4_net_list

    def check_ip_and_port(ip_address, port, timeout):
        """Helper function to check if a port is open"""
        _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _socket.settimeout(timeout)
        return not bool(_socket.connect_ex((ip_address, port)))

    def sonos_scan_worker_thread(ip_list, socket_timeout, sonos_ip_addresses):
        """Helper function worker thread to take IP addresses off a list and
        test whether there is a device with port 1400 open at that IP address.
        Once a there is a hit, the list is cleared to prevent any further
        checking of addresses by any thread.
        """
        while len(ip_list) > 0:
            ip_addr = ip_list.pop()
            if check_ip_and_port(str(ip_addr), 1400, socket_timeout):
                _LOG.info("Found open port 1400 at IP '{}'".format(str(ip_addr)))
                sonos_ip_addresses.append(str(ip_addr))
                # Clearing the list will eliminate further work by all threads
                ip_list.clear()

    # Generate the set of IPs to check
    ip_set = set()
    for network in find_ipv4_networks(min_netmask):
        for ip_address in network:
            ip_set.add(ip_address)

    # Find IP addresses with open port 1400
    # Use threading to scan the IP range efficiently
    sonos_ip_addresses = []
    thread_list = []
    if max_threads > len(ip_set):
        max_threads = len(ip_set)
    for _ in range(max_threads):
        try:
            thread = threading.Thread(
                target=sonos_scan_worker_thread,
                args=(ip_set, timeout, sonos_ip_addresses),
            )
            thread_list.append(thread)
            thread.start()
        except RuntimeError:
            # We probably can't create any more threads. Continue without
            # creating additional threads.
            _LOG.info("Runtime error creating threads. Continuing")
            break

    # Wait for all threads to finish
    for thread in thread_list:
        thread.join()

    # Pick the first IP address in the list to create a SoCo instance, and
    # use it to find the remaining zones
    for ip_address in sonos_ip_addresses:
        try:
            zone = config.SOCO_CLASS(ip_address)
            _LOG.info("Found Sonos device at IP '{}'".format(ip_address))
            if include_invisible:
                return zone.all_zones
            else:
                return zone.visible_zones
        # pylint: disable=bare-except
        except:  # noqa: E722
            # Although port 1400 is open, this is probably not a Sonos device.
            # I really do want to catch all exceptions here, then try the next
            # address if there is one.
            _LOG.info("No Sonos device at IP '{}'".format(ip_address))
            continue
    return None
