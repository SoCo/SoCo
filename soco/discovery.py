"""This module contains methods for discovering Sonos devices on the
network."""


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


def discover(timeout=5, include_invisible=False, interface_addr=None, allow_network_scan=False, **network_scan_kwargs):
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
            the source of the datagrams (i.e., it is a value for
            `socket.IP_MULTICAST_IF <socket>`). If `None` or not specified,
            the system default interface(s) for UDP multicast messages will be
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
    """

    def create_socket(interface_addr):
        """A helper function for creating a socket for discovery purposes.

        Create and return a socket with appropriate options set for multicast.
        """

        _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # UPnP v1.0 requires a TTL of 4
        _sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack("B", 4)
        )
        _sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface_addr)
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
        except OSError as e:
            raise ValueError(
                "{} is not a valid IP address string".format(interface_addr)
            ) from e
        _sockets.append(create_socket(interface_addr))
        _LOG.info("Sending discovery packets on specified interface")
    else:
        # Use all relevant network interfaces
        for address in _find_ipv4_addresses():
            try:
                _sockets.append(create_socket(address))
            except OSError as e:
                _LOG.warning(
                    "Can't make a discovery socket for %s: %s: %s",
                    address,
                    e.__class__.__name__,
                    e,
                )
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
        SoCo: A `SoCo` instance (or subclass if `config.SOCO_CLASS` is set),
        or `None` if no instances are found.
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
        SoCo: A `SoCo` instance (or subclass if `config.SOCO_CLASS` is set),
        or `None` if no instances are found.
    """
    devices = discover(allow_network_scan=allow_network_scan, **network_scan_kwargs)
    if devices is None:
        return None

    for device in devices:
        if device.player_name == name:
            return device
    return None


# pylint: disable=too-many-arguments
def scan_network(
    include_invisible=False,
    multi_household=False,
    max_threads=256,
    scan_timeout=0.1,
    min_netmask=24,
    networks_to_scan=None,
):
    """Scan all attached networks for Sonos devices.

    This function scans the IPv4 networks to which this node is attached,
    searching for Sonos devices. Multiple parallel threads are used to
    scan IP addresses in parallel for faster discovery.

    Public, loopback and link local IP ranges are excluded from the scan,
    and the scope of the search can be controlled by setting a minimum netmask.

    Alternatively, a list of networks to scan can be provided.

    This function is intended for use when the usual discovery function is not
    working, perhaps due to multicast problems on the network to which the SoCo
    host is attached. The function can also be used to find a complete list of
    speakers when there are multiple Sonos households present.
    For example, this is the case where there are 'split' S1/S2 Sonos systems
    on the network.

    Note that this call may fail to find speakers present on the network, and
    this can be due to ARP cache misses and ARP requests that don't
    complete within the timeout. The call can be retried with longer values for
    scan_timeout if necessary.

    Args:
        include_invisible (bool, optional): Whether to include invisible Sonos devices
            in the set of devices returned.
        multi_household (bool, optional): Whether to find all the speakers on the
            network exhaustively.
            If set to `False`, discovery will stop as soon as at least one speaker is
            found. In the case of multiple households on the attached networks, this
            means that only the speakers from the first-discovered household will be
            returned.
            If set to `True`, discovery will proceed until all speakers, from all
            households, have been found.
        max_threads (int, optional): The maximum number of threads to use when
            scanning the network.
        scan_timeout (float, optional): The network timeout in seconds to use when
            checking each IP address for a Sonos device.
        min_netmask (int, optional): The minimum number of netmask bits. Used to
            constrain the network search space.
        networks_to_scan (list, optional): A `list` of IPv4 networks to search,
            each a `str` of form "192.168.0.1/24". Only the specified networks will
            be searched. The 'min_netmask' option (if supplied) is ignored.

    Returns:
        set: A set of `SoCo` instances, one for each zone found, or else `None`.
    """

    # Generate the set of IPs to check
    ip_set = set()
    if networks_to_scan:
        for network_to_scan in networks_to_scan:
            try:
                network = ipaddress.IPv4Network(network_to_scan, False)
            except ValueError:
                _LOG.info("'%s' is not a valid IPv4 network", network_to_scan)
                # Ignore the error and continue processing the list
                continue
            ip_set.update(set(network))
    else:
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
            target=_sonos_scan_worker_thread,
            args=(ip_set, scan_timeout, sonos_ip_addresses, multi_household),
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

    # Collect SoCo instances
    zones = set()
    for ip_address in sonos_ip_addresses:
        if include_invisible:
            for zone in config.SOCO_CLASS(ip_address).all_zones:
                zones.add(zone)
        else:
            for zone in config.SOCO_CLASS(ip_address).visible_zones:
                zones.add(zone)
        # Stop after first zone unless we want exhaustively to find
        # all zones across all households
        if not multi_household:
            break

    _LOG.info(
        "Include_invisible: %s | multi_household: %s | %d Zones: %s",
        include_invisible,
        multi_household,
        len(zones),
        zones,
    )

    return zones


def scan_network_by_household_id(
    household_id, include_invisible=False, **network_scan_kwargs
):
    """Convenience function to find the zones in a specific Sonos
    household.

    Args:
        household_id (str): The Sonos household ID to search for. IDs take the
            form 'Sonos_XXXXXXXXXXXXXXXXXXXXXXXXXX'.
        include_invisible (bool, optional): Whether to include invisible Sonos devices
            in the set of devices returned.
        **network_scan_kwargs: Arguments for the `scan_network` function.
            See its docstring for details. (Note that the argument
            'multi_household' is forced to `True` when this function is
            called.)

    Returns:
        set: A set of `SoCo` instances, one for each zone found, or else `None`.
    """

    # multi_household must be set to True
    network_scan_kwargs["multi_household"] = True
    zones = scan_network(include_invisible=include_invisible, **network_scan_kwargs)
    if zones:
        zones = {zone for zone in zones if zone.household_id == household_id}
    _LOG.info("Returning zones: %s", zones)
    return zones


def scan_network_get_household_ids(**network_scan_kwargs):
    """Convenience function to find the all Sonos households on the attached
    networks.

    Args:
        **network_scan_kwargs: Arguments for the `scan_network` function.
            See its docstring for details. (Note that the argument
            'multi_household' is forced to `True` when this function is
            called.)

    Returns:
        set: A set of Sonos household IDs, each in the form of a `str`
        like 'Sonos_XXXXXXXXXXXXXXXXXXXXXXXXXX'.
    """

    # multi_household must be set to True
    network_scan_kwargs["multi_household"] = True
    zones = scan_network(include_invisible=True, **network_scan_kwargs)
    household_ids = set()
    if zones:
        for zone in zones:
            household_ids.add(zone.household_id)

    _LOG.info("Returning household IDs: %s", household_ids)
    return household_ids


def scan_network_get_by_name(name, household_id=None, **network_scan_kwargs):
    """Convenience function to use `scan_network` to find a zone
    by its name.

    Note that if there are multiple zones with the same name,
    then only one of the zones will be returned. Optionally,
    the search can be constrained to a specific household.

    Args:
        name (str): The name of the zone to find.
        household_id (str, optional): Use this to find the zone in a specific
             Sonos household.
        **network_scan_kwargs: Arguments for the `scan_network` function.
            See its docstring for details. (Note that the argument
            'multi_household' is forced to `True` when this function is
            called.)

    Returns:
        SoCo: A `SoCo` instance representing the zone, or `None` if no
        matching zone is found. Only returns visible zones.
    """

    # multi_household must be set to True
    network_scan_kwargs["multi_household"] = True
    zones = scan_network(include_invisible=False, **network_scan_kwargs)
    matching_zone = None
    if zones:
        for zone in zones:
            if zone.player_name == name:
                if household_id:
                    if zone.household_id == household_id:
                        matching_zone = zone
                        break
                else:
                    matching_zone = zone
                    break

    _LOG.info("Returning zone: %s", matching_zone)
    return matching_zone


def scan_network_any_soco(household_id=None, **network_scan_kwargs):
    """Convenience function to use `scan_network` to find any zone,
    optionally specifying a Sonos household.

    Args:
        household_id (str, optional): Use this to find a zone in a specific
            Sonos household.
        **network_scan_kwargs: Arguments for the `scan_network` function.
            See its docstring for details.

    Returns:
        SoCo: A `SoCo` instance representing the zone, or `None` if no
        zone is found (or no zone is found that matches a supplied
        household_id).
    """

    if household_id:
        network_scan_kwargs["multi_household"] = True

    zones = scan_network(include_invisible=False, **network_scan_kwargs)
    any_zone = None
    if zones:
        if not household_id:
            any_zone = zones.pop()
        else:
            for zone in zones:
                if zone.household_id == household_id:
                    any_zone = zone
                    break

    _LOG.info("Returning zone: %s", any_zone)
    return any_zone


def _find_ipv4_networks(min_netmask):
    """Discover attached IP networks.

    Helper function to return a set of IPv4 networks to which
    the network interfaces on this node are attached.
    Exclude public, loopback and link local network ranges.

    Args:
        min_netmask(int): The minimum netmask to be used.

    Returns:
        set: A set of `ipaddress.ip_network` instances.
    """

    ipv4_net_list = set()
    adapters = ifaddr.get_adapters()
    for adapter in adapters:
        for ifaddr_network in adapter.ips:
            try:
                ipaddress.IPv4Network(ifaddr_network.ip)
            except ValueError:
                # Not an IPv4 address
                continue

            ipv4_network = ipaddress.ip_network(ifaddr_network.ip)
            # Restrict to private networks, and exclude loopback and link local
            if (
                ipv4_network.is_private
                and not ipv4_network.is_loopback
                and not ipv4_network.is_link_local
            ):
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


def _find_ipv4_addresses():
    """Discover and return all the host's IPv4 addresses.

    Helper function to return a set of IPv4 addresses associated
    with the network interfaces of this host. Loopback and link
    local addresses are excluded.

    Returns:
        set: A set of IPv4 addresses (dotted decimal strings). Empty
        set if there are no addresses found.
    """

    ipv4_addresses = set()
    for adapter in ifaddr.get_adapters():
        for ifaddr_network in adapter.ips:
            try:
                ipaddress.IPv4Network(ifaddr_network.ip)
            except ValueError:
                # Not an IPv4 address
                continue
            ipv4_network = ipaddress.ip_network(ifaddr_network.ip)
            if not ipv4_network.is_loopback and not ipv4_network.is_link_local:
                ipv4_addresses.add(ifaddr_network.ip)

    _LOG.info("Set of attached IPs: %s", str(ipv4_addresses))
    return ipv4_addresses


def _check_ip_and_port(ip_address, port, timeout):
    """Helper function to check if a port is open.

    Args:
        ip_address(str): The IP address to be checked.
        port(int): The port to be checked.
        timeout(float): The timeout to use.

    Returns:
        bool: True if a connection can be made.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as socket_:
        socket_.settimeout(timeout)
        return not bool(socket_.connect_ex((ip_address, port)))


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


def _sonos_scan_worker_thread(
    ip_set, socket_timeout, sonos_ip_addresses, multi_household
):
    """Helper function worker thread to take IP addresses from a set and
    test whether there is (1) a device with port 1400 open at that IP
    address, then (2) check the device is a Sonos device.

    Once a there is a hit, the set is cleared to prevent any further
    checking of addresses by any thread, unless 'multi_household' is
    `True`, in which case all IP addresses will be checked.
    """

    while True:
        try:
            ip_addr = ip_set.pop()
        except KeyError:
            break

        ip_address = str(ip_addr)
        try:
            check = _check_ip_and_port(ip_address, 1400, socket_timeout)
        except OSError:
            # With large numbers of threads, we can exceed the file handle limit.
            # Put the address back on the list and drop out of this thread.
            ip_set.add(ip_addr)
            break

        if check:
            _LOG.info("Found open port 1400 at IP '%s'", ip_address)
            if _is_sonos(ip_address):
                _LOG.info("Confirmed Sonos device at IP '%s'", ip_address)
                sonos_ip_addresses.append(ip_address)
                # Clear the list to eliminate further searching by
                # all threads, if we're not doing an exhaustive search
                if not multi_household:
                    ip_set.clear()
                    break
            else:
                _LOG.info("'%s' is not a Sonos device", ip_address)
