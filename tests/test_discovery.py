# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from mock import patch, Mock

from soco import discover
from soco import config

IP_ADDR = '192.168.1.101'
TIMEOUT = 5

@patch('socket.socket', spec=True)
@patch('select.select', spec=True)
@patch('soco.config.SOCO_CLASS')
class TestDiscover:
    def test_discover(self, mock_soco, mock_select, mock_socket):
        socket = mock_socket.return_value
        socket.recvfrom.return_value = (b'SERVER: Linux UPnP/1.0 Sonos/26.1-76230 (ZPS3)', [IP_ADDR])  # (data,
        # address)
        mock_select.return_value = (1, 1, 1)
        # set timeout
        TIMEOUT = 5
        discover(timeout=TIMEOUT)
        # 3 packets should be sent
        assert socket.sendto.call_count == 3
        # select called with the relevant timeout
        mock_select.assert_called_once_with([socket], [], [], min(TIMEOUT, 0.1))
        # SoCo should be created with the IP address received
        mock_soco.assert_called_with(IP_ADDR)

        # Now test include_visible parameter. include_invisible=True should
        # result in calling SoCo.all_zones etc
        mock_soco.return_value = Mock(all_zones='ALL', visible_zones='VISIBLE')
        assert discover(include_invisible=True) == 'ALL'
        assert discover(include_invisible=False) == 'VISIBLE'

        # if select does not return within timeout SoCo should not be called
        # at all
        # simulate no data being returned within timeout
        mock_select.return_value = (0, 1, 1)
        discover()
        # Check no SoCo instance created
        mock_soco.assert_not_called
