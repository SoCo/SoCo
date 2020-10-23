# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import socket
import select
import ipaddress
import ifaddr

from collections import OrderedDict

from mock import patch, MagicMock as Mock, PropertyMock, call

from soco import discover
from soco import config
from soco.discovery import (
    any_soco,
    by_name,
    _is_ipv4_address,
    _find_ipv4_networks,
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
        # Each time gethostbyname is called, it gets a different value
        monkeypatch.setattr(
            "socket.gethostbyname", Mock(side_effect=["192.168.1.15", "192.168.1.16"])
        )
        # Stop getfqdn from working, to avoud network access
        monkeypatch.setattr("socket.getfqdn", Mock())
        # prevent creation of soco instances
        monkeypatch.setattr("soco.config.SOCO_CLASS", Mock())
        # Fake return value for select
        monkeypatch.setattr("select.select", Mock(return_value=([sock], 1, 1)))

        # set timeout
        TIMEOUT = 2
        discover(timeout=TIMEOUT)
        # 9 packets in total should be sent (3 to default, 3 to
        # 192.168.1.15 and 3 to 192.168.1.15)
        assert sock.sendto.call_count == 9
        # select called with the relevant timeout
        select.select.assert_called_with([sock, sock, sock], [], [], min(TIMEOUT, 0.1))
        # SoCo should be created with the IP address received
        config.SOCO_CLASS.assert_called_with(IP_ADDR)

        # Now test include_visible parameter. include_invisible=True should
        # result in calling SoCo.all_zones etc
        # Reset gethostbyname, to always return the same value
        monkeypatch.setattr("socket.gethostbyname", Mock(return_value="192.168.1.15"))
        config.SOCO_CLASS.return_value = Mock(all_zones="ALL", visible_zones="VISIBLE")
        assert discover(include_invisible=True) == "ALL"
        assert discover(include_invisible=False) == "VISIBLE"

        # if select does not return within timeout SoCo should not be called
        # at all
        # simulate no data being returned within timeout
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


def test__is_ipv4_address():
    assert _is_ipv4_address("192.168.0.1") is True
    assert _is_ipv4_address("192.168.0") is False
    assert _is_ipv4_address("2001:db8:0:1:1:1:1:1") is False


def test__find_ipv4_networks(monkeypatch):
    # Set up the response from ifaddr.get_adapters()
    adapters = OrderedDict()
    ips = []
    # Create a variety of networks
    # Private IP range
    ips.append(ifaddr.IP("192.168.0.1", 24, "private-24"))
    # Private IP range: test constraints
    ips.append(ifaddr.IP("192.168.1.1", 16, "private-16"))
    # Public IP range
    ips.append(ifaddr.IP("15.100.100.100", 8, "public"))
    # Loopback range
    ips.append(ifaddr.IP("127.0.0.1", 24, "loopback"))
    index = 1
    for ip in ips:
        adapters[ip.nice_name] = ifaddr._shared.Adapter(
            ip.nice_name, ip.nice_name, [ip], index=index
        )
        index += 1
    monkeypatch.setattr("ifaddr.get_adapters", Mock(return_value=adapters.values()))

    # Check that we get the networks we expect; test different min_netmask values
    assert ipaddress.ip_network("192.168.0.55/24", False) in _find_ipv4_networks(24)
    assert ipaddress.ip_network("192.168.1.1/24", False) in _find_ipv4_networks(24)
    assert ipaddress.ip_network("192.168.1.1/16", False) not in _find_ipv4_networks(24)
    assert ipaddress.ip_network("192.168.1.1/16", False) in _find_ipv4_networks(16)
    assert ipaddress.ip_network("192.168.1.1/16", False) in _find_ipv4_networks(0)
    assert ipaddress.ip_network("15.100.100.100/8", False) not in _find_ipv4_networks(8)
    assert ipaddress.ip_network("127.0.0.1/24", False) not in _find_ipv4_networks(24)
