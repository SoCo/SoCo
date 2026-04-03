"""Provides handling for ZoneGroupState information.

ZoneGroupState XML payloads are received from both:
* zoneGroupTopology.GetZoneGroupState()['ZoneGroupState']
* zoneGroupTopology subscription event callbacks

The ZoneGroupState payloads are identical between all speakers in a
household, but may be generated with differing orders for contained
ZoneGroup or ZoneGroupMember elements and children. To benefit from
similar contents, payloads are passed through an XSL transformation
to normalize the data, to allow simple equality comparisons, and to
avoid unnecessary reprocessing of identical data.

Since the payloads are identical between all speakers, we can use a
common cache per household.

As satellites can sometimes deliver outdated payloads when they are
directly polled, these requests are instead forwarded to the parent
device.

Example payload contents:

  <ZoneGroupState>
    <ZoneGroups>
      <ZoneGroup Coordinator="RINCON_000XXX1400" ID="RINCON_000XXXX1400:0">
        <ZoneGroupMember
            BootSeq="33"
            Configuration="1"
            Icon="x-rincon-roomicon:zoneextender"
            Invisible="1"
            IsZoneBridge="1"
            Location="http://192.168.1.100:1400/xml/device_description.xml"
            MinCompatibleVersion="22.0-00000"
            SoftwareVersion="24.1-74200"
            UUID="RINCON_000ZZZ1400"
            ZoneName="BRIDGE"/>
      </ZoneGroup>
      <ZoneGroup Coordinator="RINCON_000XXX1400" ID="RINCON_000XXX1400:46">
        <ZoneGroupMember
            BootSeq="44"
            Configuration="1"
            Icon="x-rincon-roomicon:living"
            Location="http://192.168.1.101:1400/xml/device_description.xml"
            MinCompatibleVersion="22.0-00000"
            SoftwareVersion="24.1-74200"
            UUID="RINCON_000XXX1400"
            ZoneName="Living Room"/>
        <ZoneGroupMember
            BootSeq="52"
            Configuration="1"
            Icon="x-rincon-roomicon:kitchen"
            Location="http://192.168.1.102:1400/xml/device_description.xml"
            MinCompatibleVersion="22.0-00000"
            SoftwareVersion="24.1-74200"
            UUID="RINCON_000YYY1400"
            ZoneName="Kitchen"/>
      </ZoneGroup>
    </ZoneGroups>
    <VanishedDevices/>
  </ZoneGroupState>

"""

import asyncio
import logging
import time
from weakref import WeakSet

from lxml import etree as LXML

from . import config
from .events_base import SubscriptionBase
from .exceptions import NotSupportedException, SoCoException, SoCoUPnPException
from .groups import ZoneGroup

POLLING_CACHE_TIMEOUT = 5
NEVER_TIME = -1200.0

ZGS_ATTRIB_MAPPING = {
    "BootSeq": "_boot_seqnum",
    "ChannelMapSet": "_channel_map",
    "HTSatChanMapSet": "_ht_sat_chan_map",
    "MicEnabled": "_mic_enabled",
    "UUID": "_uid",
    "VoiceConfigState": "_voice_config_state",
    "ZoneName": "_player_name",
}
ZGS_XSLT = """
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="xml" encoding="UTF-8"/>
  <xsl:template match="*">
    <xsl:copy>
     <xsl:copy-of select="@*"/>
      <xsl:apply-templates select="*">
       <xsl:sort select="(@Coordinator | @UUID)"/>
      </xsl:apply-templates>
    </xsl:copy>
  </xsl:template>
</xsl:stylesheet>
"""
ZGS_TRANSFORM = LXML.XSLT(LXML.fromstring(ZGS_XSLT))  # pylint:disable=I1101

_LOG = logging.getLogger(__name__)


class ZoneGroupState:
    """Handles processing and caching of ZoneGroupState payloads.

    Only one ZoneGroupState instance is created per Sonos household.
    """

    def __init__(self):
        """Initialize the ZoneGroupState instance."""
        self.all_zones = set()
        self.groups = set()
        self.visible_zones = set()

        self._cache_until = NEVER_TIME
        self._last_zgs = None
        self._subscriptions = WeakSet()

        # Statistics
        self.total_requests = 0
        self.processed_count = 0

    def clear_cache(self):
        """Clear the cache timestamp."""
        self._cache_until = NEVER_TIME

    def add_subscription(self, subscription: SubscriptionBase):
        """Start tracking a ZoneGroupTopology subscription."""
        if (
            subscription.service.service_type == "ZoneGroupTopology"
            and subscription not in self._subscriptions
        ):
            self._subscriptions.add(subscription)
            _LOG.debug(
                "Monitoring ZoneGroupTopology subscription %s on %s",
                subscription.sid,
                subscription.service.soco,
            )

    def remove_subscription(self, subscription: SubscriptionBase):
        """Stop tracking a ZoneGroupTopology subscription."""
        if subscription in self._subscriptions:
            self._subscriptions.remove(subscription)
            _LOG.debug(
                "Discarded unsubscribed subscription %s from %s, %d remaining",
                subscription.sid,
                subscription.service.soco,
                len(self._subscriptions),
            )

    @property
    def has_subscriptions(self):
        """Return True if active subscriptions are updating this ZoneGroupState."""
        stale_subscriptions = [sub for sub in self._subscriptions if not sub.time_left]
        for sub in stale_subscriptions:
            _LOG.debug("Discarding stale subscription: %s", sub.sid)
            self.remove_subscription(sub)
        return bool(self._subscriptions)

    def clear_zone_groups(self):
        """Clear all known group sets."""
        self.groups.clear()
        self.all_zones.clear()
        self.visible_zones.clear()

    def poll(self, soco):
        """Poll using the provided SoCo instance and process the payload."""
        # pylint: disable=protected-access
        if self.has_subscriptions:
            self.total_requests += 1
            _LOG.debug(
                "Subscriptions (%s) still active during poll for %s, using cache",
                len(self._subscriptions),
                soco.ip_address,
            )
            return

        if time.monotonic() < self._cache_until:
            self.total_requests += 1
            _LOG.debug(
                "Cache still active (GetZoneGroupState) during poll for %s",
                soco.ip_address,
            )
            return

        if soco._is_satellite:
            # Satellites can return outdated information, use the parent
            _LOG.debug(
                "Poll request on satellite (%s), using parent (%s)",
                soco.ip_address,
                soco._satellite_parent.ip_address,
            )
            soco = soco._satellite_parent

        # On large (about 20+ players) systems, GetZoneGroupState() can cause
        # the target Sonos player to return an HTTP 501 error, raising a
        # SoCoUPnPException.
        try:
            zgs = soco.zoneGroupTopology.GetZoneGroupState()["ZoneGroupState"]
            self.process_payload(payload=zgs, source="poll", source_ip=soco.ip_address)
            self._cache_until = time.monotonic() + POLLING_CACHE_TIMEOUT
            _LOG.debug("Extending ZGS cache by %ss", POLLING_CACHE_TIMEOUT)

        # In the event of failure, we fall back to using a ZGT event to
        # determine the ZGS. Fallback behaviour can be disabled by setting the
        # config.ZGT_EVENT_FALLBACK flag to False.
        except SoCoUPnPException as soco_upnp_exception:
            _LOG.debug(
                "Exception (%s) raised on 'GetZoneGroupState()'",
                soco_upnp_exception,
            )

            if config.ZGT_EVENT_FALLBACK is False:
                _LOG.debug("ZGT event fallback disabled (config.ZGT_EVENT_FALLBACK)")
                raise NotSupportedException(
                    "'GetZoneGroupState()' call fails on large Sonos systems "
                    "and event fallback is disabled"
                ) from soco_upnp_exception

            _LOG.debug("Falling back to using a ZGT event")
            try:
                self.update_zgs_by_event(soco)
            except Exception as soco_exception:
                raise soco_exception from soco_upnp_exception

    def update_zgs_by_event(self, speaker):
        """
        Fall back to updating the ZGS using a ZGT event.
        Use of the 'events_twisted' module is not currently supported.
        """
        if config.EVENTS_MODULE.__name__ == "soco.events":
            _LOG.debug("Updating ZGS using standard 'events' module")
            self.update_zgs_by_event_default(speaker)

        elif config.EVENTS_MODULE.__name__ == "soco.events_asyncio":
            _LOG.debug("Updating ZGS using 'events_asyncio' module")
            # Explicit asyncio event loop control required for Python 3.6
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(ZoneGroupState.update_zgs_by_event_asyncio(speaker))
            asyncio.set_event_loop(None)
            loop.close()
            # From Python 3.7, we can just use the single statement:
            # asyncio.run(ZoneGroupState.update_zgs_events_asyncio(speaker))

        elif config.EVENTS_MODULE.__name__ == "soco.events_twisted":
            # Future: Insert code here to handle the 'events_twisted' case
            raise SoCoException(
                "ZGT event fallback not yet implemented when using the "
                "'events_twisted' module"
            )

        else:
            # In case any additional events frameworks come along ...
            raise SoCoException(
                "ZGT event fallback not implemented for "
                f"'{config.EVENTS_MODULE.__name__}' module"
            )

    def update_zgs_by_event_default(self, speaker):
        """
        Update the ZGS using the default events module.
        """
        sub = speaker.zoneGroupTopology.subscribe()
        event = sub.events.get(timeout=1.0)
        sub.unsubscribe()
        zgs = event.variables.get("zone_group_state")
        self.process_payload(payload=zgs, source="event", source_ip=speaker.ip_address)

    @staticmethod
    async def update_zgs_by_event_asyncio(speaker):
        """
        Update ZGS using events_asyncio. When the event is received,
        the events_asyncio notify handler will call 'process_payload' with
        the updated ZGS.
        """
        from . import events_asyncio  # pylint: disable=C0415

        event_listener_is_running = events_asyncio.event_listener.is_running
        sub = await speaker.zoneGroupTopology.subscribe()
        await asyncio.sleep(0.25)
        await sub.unsubscribe()
        if not event_listener_is_running:
            # The event listener was started as a result of our
            # subscribe() call, so stop it
            await events_asyncio.event_listener.async_stop()

    def process_payload(self, payload, source, source_ip):
        """Update using the provided XML payload."""
        self.total_requests += 1
        tree = normalize_zgs_xml(payload)
        normalized_zgs = str(tree)
        if normalized_zgs == self._last_zgs:
            _LOG.debug(
                "Duplicate ZGS received from %s (%s), ignoring", source_ip, source
            )
            return

        self.processed_count += 1
        _LOG.debug(
            "Updating ZGS with %s payload from %s (%s/%s processed)",
            source,
            source_ip,
            self.processed_count,
            self.total_requests,
        )

        self.update_soco_instances(tree)
        self._last_zgs = normalized_zgs

    def parse_zone_group_member(self, member_element):
        """Parse a ZoneGroupMember or Satellite element from Zone Group
        State, create a SoCo instance for the member, set basic attributes
        and return it."""
        # pylint: disable=protected-access

        # Create a SoCo instance for each member. Because SoCo
        # instances are singletons, this is cheap if they have already
        # been created, and useful if they haven't. We can then
        # update various properties for that instance.
        member_attribs = member_element.attrib

        # Example Location contents:
        #   http://192.168.1.100:1400/xml/device_description.xml
        ip_addr = member_attribs["Location"].split("//")[1].split(":")[0]
        zone = config.SOCO_CLASS(ip_addr)
        for key, attrib in ZGS_ATTRIB_MAPPING.items():
            setattr(zone, attrib, member_attribs.get(key))

        # Example ChannelMapSet (stereo pair) contents:
        #   RINCON_001XXX1400:LF,LF;RINCON_002XXX1400:RF,RF
        # Example HTSatChanMapSet (home theater) contents:
        #   RINCON_001XXX1400:LF,RF;RINCON_002XXX1400:LR;RINCON_003XXX1400:RR
        for channel_map in list(
            filter(None, [zone._channel_map, zone._ht_sat_chan_map])
        ):
            for channel in channel_map.split(";"):
                if channel.startswith(zone._uid):
                    zone._channel = channel.split(":")[-1]

        # Add the zone to the set of all members, and to the set
        # of visible members if appropriate
        if member_attribs.get("Invisible") != "1":
            self.visible_zones.add(zone)
        self.all_zones.add(zone)
        return zone

    def update_soco_instances(self, tree):
        """Update all SoCo instances with the provided payload."""
        # pylint: disable=protected-access
        self.clear_zone_groups()

        # Compatibility fallback for pre-10.1 firmwares
        # where a "ZoneGroups" element is not used
        zone_groups = tree.find("ZoneGroups")
        if zone_groups is None:
            zone_groups = tree

        for group_element in zone_groups.findall("ZoneGroup"):
            coordinator_uid = group_element.attrib["Coordinator"]
            group_uid = group_element.attrib["ID"]
            group_coordinator = None
            members = set()
            for member_element in group_element.findall("ZoneGroupMember"):
                zone = self.parse_zone_group_member(member_element)
                zone._is_satellite = False
                zone._satellite_parent = None
                if zone._uid == coordinator_uid:
                    group_coordinator = zone
                    zone._is_coordinator = True
                else:
                    zone._is_coordinator = False
                # is_bridge doesn't change, but it does no real harm to
                # set/reset it here, just in case the zone has not been seen
                # before
                zone._is_bridge = member_element.attrib.get("IsZoneBridge") == "1"
                # add the zone to the members for this group
                members.add(zone)
                # Loop over Satellite elements if present, and process as for
                # ZoneGroup elements
                satellite_elements = member_element.findall("Satellite")
                zone._has_satellites = bool(satellite_elements)
                for satellite_element in satellite_elements:
                    satellite = self.parse_zone_group_member(satellite_element)
                    satellite._is_satellite = True
                    satellite._satellite_parent = zone
                    # Assume a satellite can't be a bridge or coordinator, so
                    # no need to check.
                    members.add(satellite)
            self.groups.add(ZoneGroup(group_uid, group_coordinator, members))


def normalize_zgs_xml(xml):
    """Normalize the ZoneGroupState payload and return an lxml ElementTree instance."""
    parser = LXML.XMLParser(remove_blank_text=True)  # pylint:disable=I1101
    tree = LXML.fromstring(xml, parser)  # pylint:disable=I1101
    return ZGS_TRANSFORM(tree)
