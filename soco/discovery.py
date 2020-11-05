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
    **network_scan_kwargs
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
        **network_scan_kwargs: Arguments for the `scan_network` function.
            See its docstring for details.
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
                include_invisible=include_invisible,
                **network_scan_kwargs,
            )


def any_soco(allow_network_scan=False, **network_scan_kwargs):
    """Return any visible soco device, for when it doesn't matter which.

    Try to obtain an existing instance, or use `discover` if necessary.
    Note that this assumes that the existing instance has not left
    the network.

    Args:
        allow_network_scan (bool, optional): If normal discovery fails, fall
            back to a scan of the attached network(s) to detect Sonos
            devices.
        **network_scan_kwargs: Arguments for the `scan_network` function.
            See its docstring for details.

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
        devices = discover(allow_network_scan=allow_network_scan, **network_scan_kwargs)
        return None if devices is None else devices.pop()

    return device


def by_name(name, allow_network_scan=False, **network_scan_kwargs):
    """Return a device by name.

    Args:
        name (str): The name of the device to return.
        allow_network_scan (bool, optional): If normal discovery fails, fall
            back to a scan of the attached network(s) to detect Sonos
            devices.
        **network_scan_kwargs: Arguments for the `scan_network` function.
            See its docstring for details.

    Returns:
        :class:`~.SoCo`: The first device encountered among all zones with the
        given player name. If none are found `None` is returned.
    """
    devices = discover(allow_network_scan=allow_network_scan, **network_scan_kwargs)
    if devices is None:
        return None

    for device in devices:
        if device.player_name == name:
            return device
    return None


def _is_ipv4_address(ip_address):
    """Helper function to test for an IPv4 address.

    Args:
        ip_address (str): The IP address to be tested, e.g.,
            "192.168.1.35".

    Returns:
        bool: True if this is a well-formed IPv4 address.
    """
    try:
        ipaddress.IPv4Network(ip_address)
        return True
    except ValueError:
        return False


def _find_ipv4_networks(min_netmask):
    """Discover attached IP networks.

    Helper function to return a set of IPv4 networks to which
    the network interfaces on this node are attached.
    Excludes public and loopback network ranges.

    Args:
        min_netmask(int): The minimum netmask to be used.

    Returns:
        set: A set of `ipaddress.ip_network` instances.
    """

    ipv4_net_list = set()
    adapters = ifaddr.get_adapters()
    for adapter in adapters:
        for ifaddr_network in adapter.ips:
            if _is_ipv4_address(ifaddr_network.ip):
                ipv4_network = ipaddress.ip_network(ifaddr_network.ip)
                # Restrict to private networks and exclude loopback
                if ipv4_network.is_private and not ipv4_network.is_loopback:
                    # Constrain the size of network that will be searched
                    netmask = ifaddr_network.network_prefix
                    if netmask < min_netmask:
                        _LOG.debug(
                            "%s: Constraining netmask from %d to %d",
                            ifaddr_network.ip,
                            ifaddr_network.network_prefix,
                            min_netmask,
                        )
                        netmask = min_netmask
                    network = ipaddress.ip_network(
                        ifaddr_network.ip + "/" + str(netmask),
                        False,
                    )
                    ipv4_net_list.add(network)
    _LOG.info("Set of networks to search: %s", str(ipv4_net_list))
    return ipv4_net_list


def _check_ip_and_port(ip_address, port, timeout):
    """Helper function to check if a port is open.

    Args:
        ip_address(str): The IP address to be checked.
        port(int): The port to be checked.
        timeout(float): The timeout to use.

    Returns:
        bool: True if a connection can be made.
    """

    _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _socket.settimeout(timeout)
    return not bool(_socket.connect_ex((ip_address, port)))


def _is_sonos(ip_address):
    """Helper function to check if this is a Sonos device.

    Args:
        ip_address(str): The IP address to be checked.

    Returns:
        bool: True if there is a Sonos device at the address.
    """

    try:
        # Try getting a device property
        _ = config.SOCO_CLASS(ip_address).is_visible
        return True
    # The exception is unimportant
    # pylint: disable=bare-except
    except:  # noqa: E722
        return False


def scan_network(
    include_invisible=False, max_threads=256, scan_timeout=0.1, min_netmask=24
):
    """Scan all attached networks for Sonos devices.

    This function scans the IPv4 networks to which this node is attached,
    searching for Sonos devices. Multiple parallel threads are used to
    scan IP addresses in parallel. Once any Sonos is device is found, scanning
    stops and the discovered device is used to obtain details of the Sonos
    system and all of its speakers.

    Public and loopback IP ranges are excluded from the scan. The scope of search
    can be controlled by setting a minimum netmask.

    This function is intended for use when the usual discovery function is not
    working, perhaps due to multicast problems on the network to which the SoCo
    host is attached.

    Note that this call may fail to find speakers present on the network, and
    this can be due to ARP cache misses and ARP requests that don't
    complete within the timeout. The call can be retried with longer values for
    scan_timeout if necessary.

    Args:
        include_invisible (bool, optional): Whether to include invisible Sonos devices
            in the set of devices returned.
        max_threads (int, optional): The maximum number of threads to use when
            scanning the network.
        scan_timeout (float, optional): The network timeout in seconds to use when
            checking each IP address for a Sonos device.
        min_netmask (int, optional): The minimum number of netmask bits. Used to
                constrain the network search space.

    Returns:
        set: A set of `SoCo` instances, one for each zone found, or else `None`.
    """

    def sonos_scan_worker_thread(ip_set, socket_timeout, sonos_ip_addresses):
        """Helper function worker thread to take IP addresses from a set and
        test whether there is (1) a device with port 1400 open at that IP
        address, then (2) check the device is a Sonos device.
        Once a there is a hit, the list is cleared to prevent any further
        checking of addresses by any thread.
        """

        while True:
            try:
                ip = ip_set.pop()
            except KeyError:
                break

            ip_address = str(ip)
            try:
                check = _check_ip_and_port(ip_address, 1400, socket_timeout)
            except OSError:
                # With large numbers of threads, we can exceed the file handle limit.
                # Put the address back on the list and drop out of this thread.
                ip_set.add(ip)
                break

            if check:
                _LOG.info("Found open port 1400 at IP '%s'", ip_address)
                if _is_sonos(ip_address):
                    _LOG.info("Confirmed Sonos device at IP '%s'", ip_address)
                    sonos_ip_addresses.append(ip_address)
                    # Clear the list to eliminate further searching by
                    # all threads
                    ip_set.clear()

    # Generate the set of IPs to check
    ip_set = set()
    for network in _find_ipv4_networks(min_netmask):
        ip_set.update(set(network))

    # Find Sonos devices on the list of IPs
    # Use threading to scan the list efficiently
    sonos_ip_addresses = []
    thread_list = []
    if max_threads > len(ip_set):
        max_threads = len(ip_set)
    for _ in range(max_threads):
        thread = threading.Thread(
            target=sonos_scan_worker_thread,
            args=(ip_set, scan_timeout, sonos_ip_addresses),
        )
        try:
            thread.start()
        except RuntimeError:
            # We probably can't start any more threads
            # Cease thread creation and continue
            _LOG.info(
                "Runtime error starting thread number %d ... continue",
                len(thread_list) + 1,
            )
            break
        thread_list.append(thread)
    _LOG.info("Created %d scanner threads", len(thread_list))

    # Wait for all threads to finish
    for thread in thread_list:
        thread.join()
    _LOG.info("All %d scanner threads terminated", len(thread_list))

    # No Sonos devices found
    if len(sonos_ip_addresses) == 0:
        _LOG.info("No Sonos zones discovered")
        return None

    # Use the first IP address in the list to create a SoCo instance, and
    # find the remaining zones
    zone = config.SOCO_CLASS(sonos_ip_addresses[0])
    _LOG.info(
        "Using zone '%s' (%s) to find other zones", zone.player_name, zone.ip_address
    )
    if include_invisible:
        zones = zone.all_zones
        _LOG.info("Returning all Sonos zones: %s", str(zones))
    else:
        zones = zone.visible_zones
        _LOG.info("Returning visible Sonos zones: %s", str(zones))
    return zones
