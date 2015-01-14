# -*- coding: utf-8 -*-
""" Discovery of Sonos devices on the network. """

from __future__ import unicode_literals

import socket
import select
from textwrap import dedent
import time
import struct

from soco import config
from .utils import really_utf8


def discover(timeout=1, include_invisible=False):
    """ Discover Sonos zones on the local network.

    Return an set of visible SoCo instances for each zone found.
    Include invisible zones (bridges and slave zones in stereo pairs if
    `include_invisible` is True. Will block for up to `timeout` seconds, after
    which return `None` if no zones found.

    """

    # pylint: disable=invalid-name
    PLAYER_SEARCH = dedent("""\
        M-SEARCH * HTTP/1.1
        HOST: 239.255.255.250:1900
        MAN: "ssdp:discover"
        MX: 1
        ST: urn:schemas-upnp-org:device:ZonePlayer:1
        """).encode('utf-8')
    MCAST_GRP = "239.255.255.250"
    MCAST_PORT = 1900

    _sock = socket.socket(
        socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    # UPnP v1.0 requires a TTL of 4
    _sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL,
                     struct.pack("B", 4))
    # Send a few times. UDP is unreliable
    _sock.sendto(really_utf8(PLAYER_SEARCH), (MCAST_GRP, MCAST_PORT))
    _sock.sendto(really_utf8(PLAYER_SEARCH), (MCAST_GRP, MCAST_PORT))
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
        if t1-t0 > timeout:
            return None

        # The timeout of the select call is set to be no greater than
        # 100ms, so as not to exceed (too much) the required timeout
        # in case the loop is executed more than once.
        response, _, _ = select.select([_sock], [], [], min(timeout, 0.1))

        # Only Zone Players should respond, given the value of ST in the
        # PLAYER_SEARCH message. However, to prevent misbehaved devices
        # on the network to disrupt the discovery process, we check that
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
            data, addr = _sock.recvfrom(1024)
            if b"Sonos" not in data:
                continue

            # Now we have an IP, we can build a SoCo instance and query that
            # player for the topology to find the other players. It is much
            # more efficient to rely upon the Zone Player's ability to find
            # the others, than to wait for query responses from them
            # ourselves.
            zone = config.SOCO_CLASS(addr[0])
            if include_invisible:
                return zone.all_zones
            else:
                return zone.visible_zones
