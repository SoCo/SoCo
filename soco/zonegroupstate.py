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
import logging
import time

from lxml import etree as LXML

from . import config
from .groups import ZoneGroup

EVENT_CACHE_TIMEOUT = 60
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

        # Statistics
        self.total_requests = 0
        self.processed_count = 0

    def clear_cache(self):
        """Clear the cache timestamp."""
        self._cache_until = NEVER_TIME

    def clear_zone_groups(self):
        """Clear all known group sets."""
        self.groups.clear()
        self.all_zones.clear()
        self.visible_zones.clear()

    def poll(self, soco):
        """Poll using the provided SoCo instance and process the payload."""
        # pylint: disable=protected-access
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

        zgs = soco.zoneGroupTopology.GetZoneGroupState()["ZoneGroupState"]
        self.process_payload(payload=zgs, source="poll", source_ip=soco.ip_address)

    def process_payload(self, payload, source, source_ip):
        """Update using the provided XML payload."""
        self.total_requests += 1

        def update_cache():
            if source == "event":
                timeout = EVENT_CACHE_TIMEOUT
            else:
                timeout = POLLING_CACHE_TIMEOUT
            self._cache_until = time.monotonic() + timeout
            _LOG.debug("Setting ZGS cache to %ss", timeout)

        tree = normalize_zgs_xml(payload)
        normalized_zgs = str(tree)
        if normalized_zgs == self._last_zgs:
            _LOG.debug(
                "Duplicate ZGS received from %s (%s), ignoring", source_ip, source
            )
            update_cache()
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
        update_cache()
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
