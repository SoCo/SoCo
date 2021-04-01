import socket
import select
import ipaddress
import ifaddr

from collections import OrderedDict

from unittest.mock import patch, MagicMock as Mock, PropertyMock, call

from soco import discover
from soco import config
from soco.discovery import (
    any_soco,
    by_name,
    _find_ipv4_addresses,
    _find_ipv4_networks,
    _check_ip_and_port,
    _is_sonos,
    _sonos_scan_worker_thread,
    scan_network,
)

IP_ADDR = "192.168.1.101"
TIMEOUT = 5


class TestDiscover:
    def test_discover(self, monkeypatch):
        # Create a fake socket, whose data is always a certain string
        monkeypatch.setattr("socket.socket", Mock())
        sock = socket.socket.return_value
        sock.recvfrom.return_value = (
            b"SERVER: Linux UPnP/1.0 Sonos/26.1-76230 (ZPS3)",
            [IP_ADDR],
        )  # (data, # address)
        # Return a couple of IP addresses from _find_ipv4_addresses()
        monkeypatch.setattr(
            "soco.discovery._find_ipv4_addresses",
            Mock(return_value={"192.168.0.15", "192.168.1.16"}),
        )
        # Prevent creation of soco instances
        monkeypatch.setattr("soco.config.SOCO_CLASS", Mock())
        # Fake return value for select
        monkeypatch.setattr("select.select", Mock(return_value=([sock], 1, 1)))

        # Set timeout
        TIMEOUT = 2
        discover(timeout=TIMEOUT)
        # 6 packets in total should be sent (3 to
        # 192.168.0.15 and 3 to 192.168.1.16)
        assert sock.sendto.call_count == 6
        # select called with the relevant timeout
        select.select.assert_called_with([sock, sock], [], [], min(TIMEOUT, 0.1))
        # SoCo should be created with the IP address received
        config.SOCO_CLASS.assert_called_with(IP_ADDR)

        # Now test include_visible parameter. include_invisible=True should
        # result in calling SoCo.all_zones etc
        # Reset gethostbyname, to always return the same value
        monkeypatch.setattr("socket.gethostbyname", Mock(return_value="192.168.1.15"))
        config.SOCO_CLASS.return_value = Mock(all_zones="ALL", visible_zones="VISIBLE")
        assert discover(include_invisible=True) == "ALL"
        assert discover(include_invisible=False) == "VISIBLE"

        # If select does not return within timeout SoCo should not be called
        # at all
        # Simulate no data being returned within timeout
        select.select.return_value = (0, 1, 1)
        discover(timeout=1)
        # Check no SoCo instance created
        config.SOCO_CLASS.assert_not_called


def test_by_name():
    """Test the by_name method"""
    devices = set()
    for name in ("fake", "non", "Kitchen"):
        mymock = Mock(player_name=name)
        devices.add(mymock)

    # The mock we want to find is the last one
    mock_to_be_found = mymock

    # Patch out discover and test
    with patch("soco.discovery.discover") as discover_:
        discover_.return_value = devices

        # Test not found
        device = by_name("Living Room")
        assert device is None
        discover_.assert_called_once_with(allow_network_scan=False)

        # Test found
        device = by_name("Kitchen")
        assert device is mock_to_be_found
        discover_.assert_has_calls(
            [call(allow_network_scan=False), call(allow_network_scan=False)]
        )


# Tests for scan_network()


def test__find_ipv4_networks(monkeypatch):
    _set_up_adapters(monkeypatch)
    # Check that we get the expected networks; test different min_netmask values
    assert ipaddress.ip_network("192.168.0.55/24", False) in _find_ipv4_networks(24)
    assert ipaddress.ip_network("192.168.1.1/24", False) in _find_ipv4_networks(24)
    assert ipaddress.ip_network("192.168.1.1/16", False) not in _find_ipv4_networks(24)
    assert ipaddress.ip_network("192.168.1.1/16", False) in _find_ipv4_networks(16)
    assert ipaddress.ip_network("192.168.1.1/16", False) in _find_ipv4_networks(0)
    assert ipaddress.ip_network("15.100.100.100/8", False) not in _find_ipv4_networks(8)
    assert ipaddress.ip_network("127.0.0.1/24", False) not in _find_ipv4_networks(24)
    assert ipaddress.ip_network("169.254.1.10/16", False) not in _find_ipv4_networks(16)


def test__find_ipv4_addresses(monkeypatch):
    _set_up_adapters(monkeypatch)
    assert _find_ipv4_addresses() == {"192.168.0.1", "192.168.1.1", "15.100.100.100"}


def test__check_ip_and_port(monkeypatch):
    _setup_sockets(monkeypatch)
    assert _check_ip_and_port("192.168.0.1", 1400, 0.1) is True
    assert _check_ip_and_port("192.168.0.1", 1401, 0.1) is False
    assert _check_ip_and_port("192.168.0.3", 1400, 0.1) is False


def test__is_sonos(monkeypatch):
    with patch("soco.config.SOCO_CLASS", new=_mock_soco_new):
        assert _is_sonos("192.168.0.1") is True
        assert _is_sonos("192.168.0.2") is True
        assert _is_sonos("192.168.0.3") is False


def test__sonos_scan_worker_thread(monkeypatch):
    _setup_sockets(monkeypatch)

    with patch("soco.config.SOCO_CLASS", new=_mock_soco_new):
        ip_set = {"192.168.0.1", "192.168.0.2", "192.168.0.3"}
        sonos_ip_addresses = []
        _sonos_scan_worker_thread(ip_set, 0.1, sonos_ip_addresses, False)
        assert len(sonos_ip_addresses) == 1
        assert (
            "192.168.0.1" in sonos_ip_addresses or "192.168.0.2" in sonos_ip_addresses
        )
        assert "192.168.0.3" not in sonos_ip_addresses

        ip_set = {"192.168.0.1", "192.168.0.2", "192.168.0.3"}
        sonos_ip_addresses = []
        _sonos_scan_worker_thread(ip_set, 0.1, sonos_ip_addresses, True)
        assert len(sonos_ip_addresses) == 2
        assert {"192.168.0.1", "192.168.0.2"} == set(sonos_ip_addresses)
        assert "192.168.0.3" not in sonos_ip_addresses


def test_scan_network(monkeypatch):
    _setup_sockets(monkeypatch)
    _set_up_adapters(monkeypatch)
    with patch("soco.config.SOCO_CLASS", new=_mock_soco_new):
        assert "192.168.0.1" in scan_network(include_invisible=False)
        assert "192.168.0.2" not in scan_network(include_invisible=False)
        assert "192.168.0.1" in scan_network(
            include_invisible=False, multi_household=True
        )
        assert "192.168.0.2" not in scan_network(
            include_invisible=False, multi_household=True
        )
        assert "192.168.0.1" in scan_network(
            include_invisible=True, multi_household=True
        )
        assert "192.168.0.2" in scan_network(include_invisible=True)
        assert "192.168.0.2" in scan_network(
            include_invisible=True, multi_household=True
        )
        # This one can take a few seconds to run; large address
        # space, and large number of threads
        assert "192.168.0.1" in scan_network(
            include_invisible=False,
            multi_household=True,
            max_threads=15000,
            min_netmask=16,
        )
        # Test specified networks
        assert "192.168.0.1" in scan_network(
            include_invisible=False, networks_to_scan=["192.168.0.1/24"]
        )
        assert "192.168.0.2" in scan_network(
            include_invisible=True, networks_to_scan=["192.168.0.1/24"]
        )
        assert "192.168.0.2" not in scan_network(
            include_invisible=False, networks_to_scan=["192.168.0.1/24"]
        )
        assert "192.168.0.1" in scan_network(networks_to_scan=[])
        assert scan_network(networks_to_scan=["not_a_network", ""]) is None


# Helper functions for scan_network() tests


def _set_up_adapters(monkeypatch):
    """Helper function that creates a number of mock network adapters to be
    returned by ifaddr.get_adapters()."""

    private_24 = ifaddr.IP("192.168.0.1", 24, "private-24")
    private_16 = ifaddr.IP("192.168.1.1", 16, "private-16")
    public = ifaddr.IP("15.100.100.100", 8, "public")
    loopback = ifaddr.IP("127.0.0.1", 24, "loopback")
    link_local = ifaddr.IP("169.254.1.10", 16, "link_local")
    ips = [private_24, private_16, public, loopback, link_local]

    # Set up mock adapters
    adapters = OrderedDict()
    for index in range(len(ips)):
        ip = ips[index]
        adapters[ip.nice_name] = ifaddr._shared.Adapter(
            ip.nice_name, ip.nice_name, [ip], index=index + 1
        )

    # Patch the response from ifaddr.get_adapters()
    monkeypatch.setattr("ifaddr.get_adapters", Mock(return_value=adapters.values()))


def _mock_soco_new(ip_address):
    """Helper function that replaces the SoCo constructor. Returns Mock objects for
    Sonos devices at two specific IP addresses."""

    if ip_address in ["192.168.0.1", "192.168.0.2"]:
        return Mock(
            visible_zones=["192.168.0.1"], all_zones=["192.168.0.1", "192.168.0.2"]
        )
    else:
        raise ValueError


def _setup_sockets(monkeypatch):
    """Helper function to create fake socket connection responses corresponding to
    Sonos speakers on specific IP address / port combinations only."""

    def mock_socket_connect_ex_return(_, address_port):
        if address_port in [("192.168.0.1", 1400), ("192.168.0.2", 1400)]:
            return 0
        else:
            return 1

    monkeypatch.setattr("socket.socket.connect_ex", mock_socket_connect_ex_return)
