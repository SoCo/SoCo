# -*- coding: utf-8 -*-
# pylint: disable=C0302,fixme, protected-access
""" The core module contains SonosDiscovery and SoCo classes that implement
the main entry to the SoCo functionality
"""

from __future__ import unicode_literals

import select
import socket
import logging
from textwrap import dedent
import re
import itertools
import requests

from .services import DeviceProperties, ContentDirectory
from .services import RenderingControl, AVTransport, ZoneGroupTopology
from .services import AlarmClock
from .groups import ZoneGroup
from .exceptions import CannotCreateDIDLMetadata
from .data_structures import get_ml_item, QueueItem, URI, MLSonosPlaylist,\
    MLShare
from .utils import really_utf8, camel_to_underscore
from .xml import XML
from soco import config

LOGGER = logging.getLogger(__name__)


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
    _sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    # Send a few times. UDP is unreliable
    _sock.sendto(really_utf8(PLAYER_SEARCH), (MCAST_GRP, MCAST_PORT))
    _sock.sendto(really_utf8(PLAYER_SEARCH), (MCAST_GRP, MCAST_PORT))
    _sock.sendto(really_utf8(PLAYER_SEARCH), (MCAST_GRP, MCAST_PORT))

    response, _, _ = select.select([_sock], [], [], timeout)
    # Only Zone Players will respond, given the value of ST in the
    # PLAYER_SEARCH message. It doesn't matter what response they make. All
    # we care about is the IP address
    if response:
        _, addr = _sock.recvfrom(1024)
        # Now we have an IP, we can build a SoCo instance and query that player
        # for the topology to find the other players. It is much more efficient
        # to rely upon the Zone Player's ability to find the others, than to
        # wait for query responses from them ourselves.
        zone = config.SOCO_CLASS(addr[0])
        if include_invisible:
            return zone.all_zones
        else:
            return zone.visible_zones
    else:
        return None


class SonosDiscovery(object):  # pylint: disable=R0903
    """Retained for backward compatibility only. Will be removed in future
    releases

    .. deprecated:: 0.7
       Use :func:`discover` instead.

    """

    def __init__(self):
        import warnings
        warnings.warn("SonosDiscovery is deprecated. Use discover instead.")

    @staticmethod
    def get_speaker_ips():
        """ Deprecated in favour of discover() """
        import warnings
        warnings.warn("get_speaker_ips is deprecated. Use discover instead.")
        return [i.ip_address for i in discover()]


class _ArgsSingleton(type):
    """ A metaclass which permits only a single instance of each derived class
    sharing the same `_class_group` class attribute to exist for any given set
    of positional arguments.

    Attempts to instantiate a second instance of a derived class, or another
    class with the same `_class_group`, with the same args will return the
    existing instance.

    For example:

    >>> class ArgsSingletonBase(object):
    ...     __metaclass__ = _ArgsSingleton
    ...
    >>> class First(ArgsSingletonBase):
    ...     _class_group = "greeting"
    ...     def __init__(self, param):
    ...         pass
    ...
    >>> class Second(ArgsSingletonBase):
    ...     _class_group = "greeting"
    ...     def __init__(self, param):
    ...         pass
    >>> assert First('hi') is First('hi')
    >>> assert First('hi') is First('bye')
    AssertionError
    >>> assert First('hi') is Second('hi')

     """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        key = cls._class_group if hasattr(cls, '_class_group') else cls
        if key not in cls._instances:
            cls._instances[key] = {}
        if args not in cls._instances[key]:
            cls._instances[key][args] = super(_ArgsSingleton, cls).__call__(
                *args, **kwargs)
        return cls._instances[key][args]


class _SocoSingletonBase(  # pylint: disable=too-few-public-methods
        _ArgsSingleton(str('ArgsSingletonMeta'), (object,), {})):
    """ The base class for the SoCo class.

    Uses a Python 2 and 3 compatible method of declaring a metaclass. See, eg,
    here: http://www.artima.com/weblogs/viewpost.jsp?thread=236234 and
    here: http://mikewatkins.ca/2008/11/29/python-2-and-3-metaclasses/

    """
    pass


# pylint: disable=R0904,too-many-instance-attributes
class SoCo(_SocoSingletonBase):
    """A simple class for controlling a Sonos speaker.

    For any given set of arguments to __init__, only one instance of this class
    may be created. Subsequent attempts to create an instance with the same
    arguments will return the previously created instance. This means that all
    SoCo instances created with the same ip address are in fact the *same* SoCo
    instance, reflecting the real world position.

    Public functions::

        play -- Plays the current item.
        play_uri -- Plays a track or a music stream by URI.
        play_from_queue -- Plays an item in the queue.
        pause -- Pause the currently playing track.
        stop -- Stop the currently playing track.
        seek -- Move the currently playing track a given elapsed time.
        next -- Go to the next track.
        previous -- Go back to the previous track.
        switch_to_line_in -- Switch the speaker's input to line-in.
        switch_to_tv -- Switch the speaker's input to TV.
        get_current_track_info -- Get information about the currently playing
                                  track.
        get_speaker_info -- Get information about the Sonos speaker.
        partymode -- Put all the speakers in the network in the same group.
        join -- Join this speaker to another "master" speaker.
        unjoin -- Remove this speaker from a group.
        get_queue -- Get information about the queue.
        get_folders -- Get search folders from the music library
        get_artists -- Get artists from the music library
        get_album_artists -- Get album artists from the music library
        get_albums -- Get albums from the music library
        get_genres -- Get genres from the music library
        get_composers -- Get composers from the music library
        get_tracks -- Get tracks from the music library
        get_playlists -- Get playlists from the music library
        get_music_library_information -- Get information from the music library
        get_current_transport_info -- get speakers playing state
        add_uri_to_queue -- Adds an URI to the queue
        add_to_queue -- Add a track to the end of the queue
        remove_from_queue -- Remove a track from the queue
        clear_queue -- Remove all tracks from queue
        get_favorite_radio_shows -- Get favorite radio shows from Sonos'
                                    Radio app.
        get_favorite_radio_stations -- Get favorite radio stations.

    Properties::

        uid -- The speaker's unique identifier
        mute -- The speaker's mute status.
        volume -- The speaker's volume.
        bass -- The speaker's bass EQ.
        treble -- The speaker's treble EQ.
        loudness -- The status of the speaker's loudness compensation.
        status_light -- The state of the Sonos status light.
        player_name  -- The speaker's name.
        play_mode -- The queue's repeat/shuffle settings.

    .. warning::

        These properties are not cached and will obtain information over the
        network, so may take longer than expected to set or return a value. It
        may be a good idea for you to cache the value in your own code.

    """

    _class_group = 'SoCo'

    def __init__(self, ip_address):
        # Note: Creation of a SoCo instance should be as cheap and quick as
        # possible. Do not make any network calls here
        super(SoCo, self).__init__()
        # Check if ip_address is a valid IPv4 representation.
        # Sonos does not (yet) support IPv6
        try:
            socket.inet_aton(ip_address)
        except socket.error:
            raise ValueError("Not a valid IP address string")
        #: The speaker's ip address
        self.ip_address = ip_address
        self.speaker_info = {}  # Stores information about the current speaker

        # The services which we use
        # pylint: disable=invalid-name
        self.avTransport = AVTransport(self)
        self.contentDirectory = ContentDirectory(self)
        self.deviceProperties = DeviceProperties(self)
        self.renderingControl = RenderingControl(self)
        self.zoneGroupTopology = ZoneGroupTopology(self)
        self.alarmClock = AlarmClock(self)

        # Some private attributes
        self._all_zones = set()
        self._groups = set()
        self._is_bridge = None
        self._is_coordinator = False
        self._player_name = None
        self._uid = None
        self._visible_zones = set()
        self._zgs_cache = None

    def __str__(self):
        return "<{0} object at ip {1}>".format(
            self.__class__.__name__, self.ip_address)

    def __repr__(self):
        return '{0}("{1}")'.format(self.__class__.__name__, self.ip_address)

    @property
    def player_name(self):
        """  The speaker's name. A string. """
        # We could get the name like this:
        # result = self.deviceProperties.GetZoneAttributes()
        # return result["CurrentZoneName"]
        # but it is probably quicker to get it from the group topology
        # and take advantage of any caching
        self._parse_zone_group_state()
        return self._player_name

    @player_name.setter
    def player_name(self, playername):
        """ Set the speaker's name """
        self.deviceProperties.SetZoneAttributes([
            ('DesiredZoneName', playername),
            ('DesiredIcon', ''),
            ('DesiredConfiguration', '')
            ])

    @property
    def uid(self):
        """ A unique identifier.  Looks like: RINCON_000XXXXXXXXXX1400 """
        # Since this does not change over time (?) check whether we already
        # know the answer. If so, there is no need to go further
        if self._uid is not None:
            return self._uid
        # if not, we have to get it from the zone topology, which
        # is probably quicker than any alternative, since the zgt is probably
        # cached. This will set self._uid for us for next time, so we won't
        # have to do this again
        self._parse_zone_group_state()
        return self._uid
        # An alternative way of getting the uid is as follows:
        # self.device_description_url = \
        #    'http://{0}:1400/xml/device_description.xml'.format(
        #     self.ip_address)
        # response = requests.get(self.device_description_url).text
        # tree = XML.fromstring(response.encode('utf-8'))
        # udn = tree.findtext('.//{urn:schemas-upnp-org:device-1-0}UDN')
        # # the udn has a "uuid:" prefix before the uid, so we need to strip it
        # self._uid = uid = udn[5:]
        # return uid

    @property
    def is_visible(self):
        """ Is this zone visible? A zone might be invisible if, for example it
        is a bridge, or the slave part of stereo pair.

        return True or False

        """
        # We could do this:
        # invisible = self.deviceProperties.GetInvisible()['CurrentInvisible']
        # but it is better to do it in the following way, which uses the
        # zone group topology, to capitalise on any caching.
        return self in self.visible_zones

    @property
    def is_bridge(self):
        """ Is this zone a bridge? """
        # Since this does not change over time (?) check whether we already
        # know the answer. If so, there is no need to go further
        if self._is_bridge is not None:
            return self._is_bridge
        # if not, we have to get it from the zone topology. This will set
        # self._is_bridge for us for next time, so we won't have to do this
        # again
        self._parse_zone_group_state()
        return self._is_bridge

    @property
    def is_coordinator(self):
        """ Return True if this zone is a group coordinator, otherwise False.

        return True or False

        """
        # We could do this:
        # invisible = self.deviceProperties.GetInvisible()['CurrentInvisible']
        # but it is better to do it in the following way, which uses the
        # zone group topology, to capitalise on any caching.
        self._parse_zone_group_state()
        return self._is_coordinator

    @property
    def play_mode(self):
        """ The queue's play mode. Case-insensitive options are::

        NORMAL -- Turns off shuffle and repeat.
        REPEAT_ALL -- Turns on repeat and turns off shuffle.
        SHUFFLE -- Turns on shuffle *and* repeat. (It's strange, I know.)
        SHUFFLE_NOREPEAT -- Turns on shuffle and turns off repeat.

        """
        result = self.avTransport.GetTransportSettings([
            ('InstanceID', 0),
            ])
        return result['PlayMode']

    @play_mode.setter
    def play_mode(self, playmode):
        """ Set the speaker's mode """
        playmode = playmode.upper()
        if playmode not in PLAY_MODES:
            raise KeyError("'%s' is not a valid play mode" % playmode)

        self.avTransport.SetPlayMode([
            ('InstanceID', 0),
            ('NewPlayMode', playmode)
            ])

    @property
    def cross_fade(self):
        """ The speaker's cross fade state.
        True if enabled, False otherwise """

        response = self.avTransport.GetCrossfadeMode([
            ('InstanceID', 0),
            ])
        cross_fade_state = response['CrossfadeMode']
        return True if int(cross_fade_state) else False

    @cross_fade.setter
    def cross_fade(self, crossfade):
        """ Set the speaker's cross fade state. """
        crossfade_value = '1' if crossfade else '0'
        self.avTransport.SetCrossfadeMode([
            ('InstanceID', 0),
            ('CrossfadeMode', crossfade_value)
            ])

    @property
    def speaker_ip(self):
        """Retained for backward compatibility only. Will be removed in future
        releases

        .. deprecated:: 0.7
           Use :attr:`ip_address` instead.

        """
        import warnings
        warnings.warn("speaker_ip is deprecated. Use ip_address instead.")
        return self.ip_address

    def play_from_queue(self, index):
        """ Play a track from the queue by index. The index number is
        required as an argument, where the first index is 0.

        index: the index of the track to play; first item in the queue is 0

        Returns:
        True if the Sonos speaker successfully started playing the track.

        Raises SoCoException (or a subclass) upon errors.

        """
        # Grab the speaker's information if we haven't already since we'll need
        # it in the next step.
        if not self.speaker_info:
            self.get_speaker_info()

        # first, set the queue itself as the source URI
        uri = 'x-rincon-queue:{0}#0'.format(self.uid)
        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', uri),
            ('CurrentURIMetaData', '')
            ])

        # second, set the track number with a seek command
        self.avTransport.Seek([
            ('InstanceID', 0),
            ('Unit', 'TRACK_NR'),
            ('Target', index + 1)
            ])

        # finally, just play what's set
        return self.play()

    def play(self):
        """Play the currently selected track.

        Returns:
        True if the Sonos speaker successfully started playing the track.

        Raises SoCoException (or a subclass) upon errors.

        """
        self.avTransport.Play([
            ('InstanceID', 0),
            ('Speed', 1)
            ])

    def play_uri(self, uri='', meta=''):
        """ Play a given stream. Pauses the queue.

        Arguments:
        uri -- URI of a stream to be played.
        meta --- The track metadata to show in the player, DIDL format.

        Returns:
        True if the Sonos speaker successfully started playing the track.

        Raises SoCoException (or a subclass) upon errors.

        """

        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', uri),
            ('CurrentURIMetaData', meta)
            ])
        # The track is enqueued, now play it.
        return self.play()

    def pause(self):
        """ Pause the currently playing track.

        Returns:
        True if the Sonos speaker successfully paused the track.

        Raises SoCoException (or a subclass) upon errors.

        """
        self.avTransport.Pause([
            ('InstanceID', 0),
            ('Speed', 1)
            ])

    def stop(self):
        """ Stop the currently playing track.

        Returns:
        True if the Sonos speaker successfully stopped the playing track.

        Raises SoCoException (or a subclass) upon errors.

        """
        self.avTransport.Stop([
            ('InstanceID', 0),
            ('Speed', 1)
            ])

    def seek(self, timestamp):
        """ Seeks to a given timestamp in the current track, specified in the
        format of HH:MM:SS or H:MM:SS.

        Returns:
        True if the Sonos speaker successfully seeked to the timecode.

        Raises SoCoException (or a subclass) upon errors.

        """
        if not re.match(r'^[0-9][0-9]?:[0-9][0-9]:[0-9][0-9]$', timestamp):
            raise ValueError('invalid timestamp, use HH:MM:SS format')

        self.avTransport.Seek([
            ('InstanceID', 0),
            ('Unit', 'REL_TIME'),
            ('Target', timestamp)
            ])

    def next(self):
        """ Go to the next track.

        Returns:
        True if the Sonos speaker successfully skipped to the next track.

        Raises SoCoException (or a subclass) upon errors.

        Keep in mind that next() can return errors
        for a variety of reasons. For example, if the Sonos is streaming
        Pandora and you call next() several times in quick succession an error
        code will likely be returned (since Pandora has limits on how many
        songs can be skipped).

        """
        self.avTransport.Next([
            ('InstanceID', 0),
            ('Speed', 1)
            ])

    def previous(self):
        """ Go back to the previously played track.

        Returns:
        True if the Sonos speaker successfully went to the previous track.

        Raises SoCoException (or a subclass) upon errors.

        Keep in mind that previous() can return errors
        for a variety of reasons. For example, previous() will return an error
        code (error code 701) if the Sonos is streaming Pandora since you can't
        go back on tracks.

        """
        self.avTransport.Previous([
            ('InstanceID', 0),
            ('Speed', 1)
            ])

    @property
    def mute(self):
        """ The speaker's mute state. True if muted, False otherwise """

        response = self.renderingControl.GetMute([
            ('InstanceID', 0),
            ('Channel', 'Master')
            ])
        mute_state = response['CurrentMute']
        return True if int(mute_state) else False

    @mute.setter
    def mute(self, mute):
        """ Mute (or unmute) the speaker """
        mute_value = '1' if mute else '0'
        self.renderingControl.SetMute([
            ('InstanceID', 0),
            ('Channel', 'Master'),
            ('DesiredMute', mute_value)
            ])

    @property
    def volume(self):
        """ The speaker's volume. An integer between 0 and 100. """

        response = self.renderingControl.GetVolume([
            ('InstanceID', 0),
            ('Channel', 'Master'),
            ])
        volume = response['CurrentVolume']
        return int(volume)

    @volume.setter
    def volume(self, volume):
        """ Set the speaker's volume """
        volume = int(volume)
        volume = max(0, min(volume, 100))  # Coerce in range
        self.renderingControl.SetVolume([
            ('InstanceID', 0),
            ('Channel', 'Master'),
            ('DesiredVolume', volume)
            ])

    @property
    def bass(self):
        """ The speaker's bass EQ. An integer between -10 and 10. """

        response = self.renderingControl.GetBass([
            ('InstanceID', 0),
            ('Channel', 'Master'),
            ])
        bass = response['CurrentBass']
        return int(bass)

    @bass.setter
    def bass(self, bass):
        """ Set the speaker's bass """
        bass = int(bass)
        bass = max(-10, min(bass, 10))  # Coerce in range
        self.renderingControl.SetBass([
            ('InstanceID', 0),
            ('DesiredBass', bass)
            ])

    @property
    def treble(self):
        """ The speaker's treble EQ. An integer between -10 and 10. """

        response = self.renderingControl.GetTreble([
            ('InstanceID', 0),
            ('Channel', 'Master'),
            ])
        treble = response['CurrentTreble']
        return int(treble)

    @treble.setter
    def treble(self, treble):
        """ Set the speaker's treble """
        treble = int(treble)
        treble = max(-10, min(treble, 10))  # Coerce in range
        self.renderingControl.SetTreble([
            ('InstanceID', 0),
            ('DesiredTreble', treble)
            ])

    @property
    def loudness(self):
        """ The Sonos speaker's loudness compensation. True if on, otherwise
        False.

        Loudness is a complicated topic. You can find a nice summary about this
        feature here: http://forums.sonos.com/showthread.php?p=4698#post4698

        """
        response = self.renderingControl.GetLoudness([
            ('InstanceID', 0),
            ('Channel', 'Master'),
            ])
        loudness = response["CurrentLoudness"]
        return True if int(loudness) else False

    @loudness.setter
    def loudness(self, loudness):
        """ Switch on/off the speaker's loudness compensation """
        loudness_value = '1' if loudness else '0'
        self.renderingControl.SetLoudness([
            ('InstanceID', 0),
            ('Channel', 'Master'),
            ('DesiredLoudness', loudness_value)
            ])

    def _parse_zone_group_state(self):
        """ The Zone Group State contains a lot of useful information. Retrieve
        and parse it, and populate the relevant properties. """

# zoneGroupTopology.GetZoneGroupState()['ZoneGroupState'] returns XML like
# this:
#
# <ZoneGroups>
#   <ZoneGroup Coordinator="RINCON_000XXX1400" ID="RINCON_000XXXX1400:0">
#     <ZoneGroupMember
#         BootSeq="33"
#         Configuration="1"
#         Icon="x-rincon-roomicon:zoneextender"
#         Invisible="1"
#         IsZoneBridge="1"
#         Location="http://192.168.1.100:1400/xml/device_description.xml"
#         MinCompatibleVersion="22.0-00000"
#         SoftwareVersion="24.1-74200"
#         UUID="RINCON_000ZZZ1400"
#         ZoneName="BRIDGE"/>
#   </ZoneGroup>
#   <ZoneGroup Coordinator="RINCON_000XXX1400" ID="RINCON_000XXX1400:46">
#     <ZoneGroupMember
#         BootSeq="44"
#         Configuration="1"
#         Icon="x-rincon-roomicon:living"
#         Location="http://192.168.1.101:1400/xml/device_description.xml"
#         MinCompatibleVersion="22.0-00000"
#         SoftwareVersion="24.1-74200"
#         UUID="RINCON_000XXX1400"
#         ZoneName="Living Room"/>
#     <ZoneGroupMember
#         BootSeq="52"
#         Configuration="1"
#         Icon="x-rincon-roomicon:kitchen"
#         Location="http://192.168.1.102:1400/xml/device_description.xml"
#         MinCompatibleVersion="22.0-00000"
#         SoftwareVersion="24.1-74200"
#         UUID="RINCON_000YYY1400"
#         ZoneName="Kitchen"/>
#   </ZoneGroup>
# </ZoneGroups>
#

        # This is called quite frequently, so it is worth optimising it.
        # Maintain a private cache. If the zgt has not changed, there is no
        # need to repeat all the XML parsing. In addition, switch on network
        # caching for a short interval (5 secs).
        zgs = self.zoneGroupTopology.GetZoneGroupState(
            cache_timeout=5)['ZoneGroupState']
        if zgs == self._zgs_cache:
            return
        self._zgs_cache = zgs
        tree = XML.fromstring(zgs.encode('utf-8'))
        # Empty the set of all zone_groups
        self._groups.clear()
        # and the set of all members
        self._all_zones.clear()
        self._visible_zones.clear()
        # Loop over each ZoneGroup Element
        for group_element in tree.findall('ZoneGroup'):
            coordinator_uid = group_element.attrib['Coordinator']
            group_uid = group_element.attrib['ID']
            members = set()
            for member_element in group_element.findall('ZoneGroupMember'):
                # Create a SoCo instance for each member. Because SoCo
                # instances are singletons, this is cheap if they have already
                # been created, and useful if they haven't. We can then
                # update various properties for that instance.
                member_attribs = member_element.attrib
                ip_addr = member_attribs['Location'].\
                    split('//')[1].split(':')[0]
                zone = config.SOCO_CLASS(ip_addr)
                zone._uid = member_attribs['UUID']
                # If this element has the same UUID as the coordinator, it is
                # the coordinator
                group_coordinator = None
                if zone._uid == coordinator_uid:
                    group_coordinator = zone
                    zone._is_coordinator = True
                else:
                    zone._is_coordinator = False
                zone._player_name = member_attribs['ZoneName']
                # uid and is_bridge do not change, but it does no real harm to
                # set/reset them here, just in case the zone has not been seen
                # before
                zone._is_bridge = True if member_attribs.get(
                    'IsZoneBridge') == '1' else False
                is_visible = False if member_attribs.get(
                    'Invisible') == '1' else True
                # add the zone to the members for this group, and to the set of
                # all members, and to the set of visible members if appropriate
                members.add(zone)
                self._all_zones.add(zone)
                if is_visible:
                    self._visible_zones.add(zone)
                # Now create a ZoneGroup with this info and add it to the list
                # of groups
            self._groups.add(ZoneGroup(group_uid, group_coordinator, members))

    @property
    def all_groups(self):
        """  Return a set of all the available groups"""
        self._parse_zone_group_state()
        return self._groups

    @property
    def group(self):
        """The Zone Group of which this device is a member.

        group will be None if this zone is a slave in a stereo pair."""

        for group in self.all_groups:
            if self in group:
                return group
        return None

        # To get the group directly from the network, try the code below
        # though it is probably slower than that above
        # current_group_id = self.zoneGroupTopology.GetZoneGroupAttributes()[
        #     'CurrentZoneGroupID']
        # if current_group_id:
        #     for group in self.all_groups:
        #         if group.uid == current_group_id:
        #             return group
        # else:
        #     return None

    @property
    def all_zones(self):
        """ Return a set of all the available zones"""
        self._parse_zone_group_state()
        return self._all_zones

    @property
    def visible_zones(self):
        """ Return an set of all visible zones"""
        self._parse_zone_group_state()
        return self._visible_zones

    def partymode(self):
        """ Put all the speakers in the network in the same group, a.k.a Party
        Mode.

        This blog shows the initial research responsible for this:
        http://blog.travelmarx.com/2010/06/exploring-sonos-via-upnp.html

        The trick seems to be (only tested on a two-speaker setup) to tell each
        speaker which to join. There's probably a bit more to it if multiple
        groups have been defined.

        """
        # Tell every other visible zone to join this one
        # pylint: disable = expression-not-assigned
        [zone.join(self) for zone in self.visible_zones if zone is not self]

    def join(self, master):
        """ Join this speaker to another "master" speaker.

        ..  note:: The signature of this method has changed in 0.8. It now
            requires a SoCo instance to be passed as `master`, not an IP
            address

        """
        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', 'x-rincon:{0}'.format(master.uid)),
            ('CurrentURIMetaData', '')
            ])

    def unjoin(self):
        """ Remove this speaker from a group.

        Seems to work ok even if you remove what was previously the group
        master from it's own group. If the speaker was not in a group also
        returns ok.

        Returns:
        True if this speaker has left the group.

        Raises SoCoException (or a subclass) upon errors.

        """

        self.avTransport.BecomeCoordinatorOfStandaloneGroup([
            ('InstanceID', 0)
            ])

    def switch_to_line_in(self):
        """ Switch the speaker's input to line-in.

        Returns:
        True if the Sonos speaker successfully switched to line-in.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        Raises SoCoException (or a subclass) upon errors.

        """

        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', 'x-rincon-stream:{0}'.format(self.uid)),
            ('CurrentURIMetaData', '')
            ])

    def switch_to_tv(self):
        """ Switch the speaker's input to TV.

        Returns:
        True if the Sonos speaker successfully switched to TV.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        Raises SoCoException (or a subclass) upon errors.

        """

        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', 'x-sonos-htastream:{0}:spdif'.format(self.uid)),
            ('CurrentURIMetaData', '')
            ])

    @property
    def status_light(self):
        """ The white Sonos status light between the mute button and the volume
        up button on the speaker. True if on, otherwise False.

        """
        result = self.deviceProperties.GetLEDState()
        LEDState = result["CurrentLEDState"]  # pylint: disable=invalid-name
        return True if LEDState == "On" else False

    @status_light.setter
    def status_light(self, led_on):
        """ Switch on/off the speaker's status light """
        led_state = 'On' if led_on else 'Off'
        self.deviceProperties.SetLEDState([
            ('DesiredLEDState', led_state),
            ])

    def get_current_track_info(self):
        """ Get information about the currently playing track.

        Returns:
        A dictionary containing the following information about the currently
        playing track: playlist_position, duration, title, artist, album,
        position and a link to the album art.

        If we're unable to return data for a field, we'll return an empty
        string. This can happen for all kinds of reasons so be sure to check
        values. For example, a track may not have complete metadata and be
        missing an album name. In this case track['album'] will be an empty
        string.

        """
        response = self.avTransport.GetPositionInfo([
            ('InstanceID', 0),
            ('Channel', 'Master')
            ])

        track = {'title': '', 'artist': '', 'album': '', 'album_art': '',
                 'position': ''}
        track['playlist_position'] = response['Track']
        track['duration'] = response['TrackDuration']
        track['uri'] = response['TrackURI']
        track['position'] = response['RelTime']

        metadata = response['TrackMetaData']
        # Duration seems to be '0:00:00' when listening to radio
        if metadata != '' and track['duration'] == '0:00:00':
            metadata = XML.fromstring(really_utf8(metadata))
            # Try parse trackinfo
            trackinfo = metadata.findtext('.//{urn:schemas-rinconnetworks-com:'
                                          'metadata-1-0/}streamContent')
            index = trackinfo.find(' - ')

            if index > -1:
                track['artist'] = trackinfo[:index]
                track['title'] = trackinfo[index + 3:]
            else:
                LOGGER.warning('Could not handle track info: "%s"', trackinfo)
                track['title'] = trackinfo

        # If the speaker is playing from the line-in source, querying for track
        # metadata will return "NOT_IMPLEMENTED".
        elif metadata not in ('', 'NOT_IMPLEMENTED', None):
            # Track metadata is returned in DIDL-Lite format
            metadata = XML.fromstring(really_utf8(metadata))
            md_title = metadata.findtext(
                './/{http://purl.org/dc/elements/1.1/}title')
            md_artist = metadata.findtext(
                './/{http://purl.org/dc/elements/1.1/}creator')
            md_album = metadata.findtext(
                './/{urn:schemas-upnp-org:metadata-1-0/upnp/}album')

            track['title'] = ""
            if md_title:
                track['title'] = md_title
            track['artist'] = ""
            if md_artist:
                track['artist'] = md_artist
            track['album'] = ""
            if md_album:
                track['album'] = md_album

            album_art = metadata.findtext(
                './/{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI')
            if album_art is not None:
                url = metadata.findtext(
                    './/{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI')
                if url.startswith(('http:', 'https:')):
                    track['album_art'] = url
                else:
                    track['album_art'] = 'http://' + self.ip_address + ':1400'\
                        + url

        return track

    def get_speaker_info(self, refresh=False):
        """ Get information about the Sonos speaker.

        Arguments:
        refresh -- Refresh the speaker info cache.

        Returns:
        Information about the Sonos speaker, such as the UID, MAC Address, and
        Zone Name.

        """
        if self.speaker_info and refresh is False:
            return self.speaker_info
        else:
            response = requests.get('http://' + self.ip_address +
                                    ':1400/status/zp')
            dom = XML.fromstring(response.content)

        if dom.findtext('.//ZoneName') is not None:
            self.speaker_info['zone_name'] = \
                dom.findtext('.//ZoneName')
            self.speaker_info['zone_icon'] = dom.findtext('.//ZoneIcon')
            self.speaker_info['uid'] = self.uid
            self.speaker_info['serial_number'] = \
                dom.findtext('.//SerialNumber')
            self.speaker_info['software_version'] = \
                dom.findtext('.//SoftwareVersion')
            self.speaker_info['hardware_version'] = \
                dom.findtext('.//HardwareVersion')
            self.speaker_info['mac_address'] = dom.findtext('.//MACAddress')

            return self.speaker_info

    def get_group_coordinator(self, zone_name):
        """     .. deprecated:: 0.8
                   Use :meth:`group` or :meth:`all_groups` instead.

        """
        import warnings
        warnings.warn(
            "get_group_coordinator is deprecated. "
            "Use the group or all_groups methods instead")
        for group in self.all_groups:
            for member in group:
                if member.player_name == zone_name:
                    return group.coordinator.ip_address
        return None

    def get_speakers_ip(self, refresh=False):
        """ Get the IP addresses of all the Sonos speakers in the network.

        Arguments:
        refresh -- Refresh the speakers IP cache. Ignored. For backward
            compatibility only

        Returns:
        a set of IP addresses of the Sonos speakers.

        .. deprecated:: 0.8


        """
        # pylint: disable=star-args, unused-argument
        return set(z.ip_address for z in itertools.chain(*self.all_groups))

    def get_current_transport_info(self):
        """ Get the current playback state

        Returns:
        A dictionary containing the following information about the speakers
        playing state
        current_transport_state (PLAYING, PAUSED_PLAYBACK, STOPPED),
        current_trasnport_status (OK, ?), current_speed(1,?)

        This allows us to know if speaker is playing or not. Don't know other
        states of CurrentTransportStatus and CurrentSpeed.

        """
        response = self.avTransport.GetTransportInfo([
            ('InstanceID', 0),
            ])

        playstate = {
            'current_transport_status': '',
            'current_transport_state': '',
            'current_transport_speed': ''
        }

        playstate['current_transport_state'] = \
            response['CurrentTransportState']
        playstate['current_transport_status'] = \
            response['CurrentTransportStatus']
        playstate['current_transport_speed'] = response['CurrentSpeed']

        return playstate

    def get_queue(self, start=0, max_items=100):
        """ Get information about the queue

        :param start: Starting number of returned matches
        :param max_items: Maximum number of returned matches
        :returns: A list of :py:class:`~.soco.data_structures.QueueItem`.

        This method is heavly based on Sam Soffes (aka soffes) ruby
        implementation

        """
        queue = []
        response = self.contentDirectory.Browse([
            ('ObjectID', 'Q:0'),
            ('BrowseFlag', 'BrowseDirectChildren'),
            ('Filter', '*'),
            ('StartingIndex', start),
            ('RequestedCount', max_items),
            ('SortCriteria', '')
            ])
        result = response['Result']
        if not result:
            return queue

        result_dom = XML.fromstring(really_utf8(result))
        for element in result_dom.findall(
                '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item'):
            item = QueueItem.from_xml(element)
            queue.append(item)

        return queue

    def get_sonos_playlists(self, start=0, max_items=100):
        """ Convenience method for:
            get_music_library_information('sonos_playlists')
            Refer to the docstring for that method

        """
        out = self.get_music_library_information(
            'sonos_playlists',
            start,
            max_items)
        return out

    def get_artists(self, start=0, max_items=100):
        """ Convinience method for :py:meth:`get_music_library_information`
        with `search_type='artists'`. For details on remaining arguments refer
        to the docstring for that method.

        """
        out = self.get_music_library_information('artists', start, max_items)
        return out

    def get_album_artists(self, start=0, max_items=100):
        """ Convinience method for :py:meth:`get_music_library_information`
        with `search_type='album_artists'`. For details on remaining arguments
        refer to the docstring for that method.

        """
        out = self.get_music_library_information('album_artists',
                                                 start, max_items)
        return out

    def get_albums(self, start=0, max_items=100):
        """ Convinience method for :py:meth:`get_music_library_information`
        with `search_type='albums'`. For details on remaining arguments refer
        to the docstring for that method.

        """
        out = self.get_music_library_information('albums', start, max_items)
        return out

    def get_genres(self, start=0, max_items=100):
        """ Convinience method for :py:meth:`get_music_library_information`
        with `search_type='genres'`. For details on remaining arguments refer
        to the docstring for that method.

        """
        out = self.get_music_library_information('genres', start, max_items)
        return out

    def get_composers(self, start=0, max_items=100):
        """ Convinience method for :py:meth:`get_music_library_information`
        with `search_type='composers'`. For details on remaining arguments
        refer to the docstring for that method.

        """
        out = self.get_music_library_information('composers', start, max_items)
        return out

    def get_tracks(self, start=0, max_items=100):
        """ Convinience method for :py:meth:`get_music_library_information`
        with `search_type='tracks'`. For details on remaining arguments refer
        to the docstring for that method.

        """
        out = self.get_music_library_information('tracks', start, max_items)
        return out

    def get_playlists(self, start=0, max_items=100):
        """ Convinience method for :py:meth:`get_music_library_information`
        with `search_type='playlists'`. For details on remaining arguments
        refer to the docstring for that method.

        NOTE: The playlists that are referred to here are the playlist (files)
        imported from the music library, they are not the Sonos playlists.

        """
        out = self.get_music_library_information('playlists', start, max_items)
        return out

    def get_music_library_information(self, search_type, start=0,
                                      max_items=100):
        """ Retrieve information about the music library

        :param search_type: The kind of information to retrieve. Can be one of:
            'artists', 'album_artists', 'albums', 'genres', 'composers',
            'tracks', 'share', 'sonos_playlists', and 'playlists', where
            playlists are the imported file based playlists from the
            music library
        :param start: Starting number of returned matches
        :param max_items: Maximum number of returned matches. NOTE: The maximum
            may be restricted by the unit, presumably due to transfer
            size consideration, so check the returned number against the
            requested.
        :returns: A dictionary with metadata for the search, with the
            keys 'number_returned', 'update_id', 'total_matches' and an
            'item_list' list with the search results. The search results
            are instances of one of
            :py:class:`~.soco.data_structures.MLArtist`,
            :py:class:`~.soco.data_structures.MLAlbumArtist`,
            :py:class:`~.soco.data_structures.MLAlbum`,
            :py:class:`~.soco.data_structures.MLGenre`,
            :py:class:`~.soco.data_structures.MLComposer`,
            :py:class:`~.soco.data_structures.MLTrack`,
            :py:class:`~.soco.data_structures.MLShare`,
            :py:class:`~.soco.data_structures.MLSonosPlaylist and
            :py:class:`~.soco.data_structures.MLPlaylist` depending on the
            type of the search.
        :raises: :py:class:`SoCoException` upon errors

        NOTE: The playlists that are returned with the 'playlists' search, are
        the playlists imported from (files in) the music library, they are not
        the Sonos playlists.

        The information about the which searches can be performed and the form
        of the query has been gathered from the Janos project:
        http://sourceforge.net/projects/janos/ Props to the authors of that
        project.

        """
        search_translation = {'artists': 'A:ARTIST',
                              'album_artists': 'A:ALBUMARTIST',
                              'albums': 'A:ALBUM',
                              'genres': 'A:GENRE',
                              'composers': 'A:COMPOSER',
                              'tracks': 'A:TRACKS',
                              'playlists': 'A:PLAYLISTS',
                              'share': 'S:',
                              'sonos_playlists': 'SQ:',
                              'categories': 'A:'}
        search = search_translation[search_type]
        response, out = self._music_lib_search(search, start, max_items)
        out['search_type'] = search_type
        out['item_list'] = []

        # Parse the results
        dom = XML.fromstring(really_utf8(response['Result']))
        for container in dom:
            if search_type == 'sonos_playlists':
                item = MLSonosPlaylist.from_xml(container)
            elif search_type == 'share':
                item = MLShare.from_xml(container)
            else:
                item = get_ml_item(container)
            # Append the item to the list
            out['item_list'].append(item)

        return out

    def browse(self, ml_item=None, start=0, max_items=100):
        """Browse (get sub-elements) a music library item

        Keyword arguments:
            ml_item (MusicLibraryItem): The MusicLibraryItem to browse, if left
                out or passed None, the items at the base level will be
                returned
            start (int): The starting index of the results
            max_items (int): The maximum number of items to return

        Returns:
            dict: A dictionary with metadata for the search, with the
                keys 'number_returned', 'update_id', 'total_matches' and an
                'item_list' list with the search results.

        Raises:
            AttributeError: If ``ml_item`` has no ``item_id`` attribute
            SoCoUPnPException: With ``error_code='701'`` if the item cannot be
                browsed
        """
        if ml_item is None:
            search = 'A:'
        else:
            search = ml_item.item_id

        response, out = self._music_lib_search(search, start, max_items)
        out['search_type'] = 'browse'
        out['item_list'] = []

        # Parse the results
        dom = XML.fromstring(really_utf8(response['Result']))
        for container in dom:
            item = get_ml_item(container)
            out['item_list'].append(item)

        return out

    def _music_lib_search(self, search, start, max_items):
        """Perform a music library search and extract search numbers

        You can get an overview of all the relevant search prefixes (like
        'A:') and their meaning with the request:

        .. code ::

         response = device.contentDirectory.Browse([
             ('ObjectID', '0'),
             ('BrowseFlag', 'BrowseDirectChildren'),
             ('Filter', '*'),
             ('StartingIndex', 0),
             ('RequestedCount', 100),
             ('SortCriteria', '')
         ])

        Args:
            search (str): The ID to search
            start: The index of the forst item to return
            max_items: The maximum number of items to return

        Returns:
            tuple: (response, metadata) where response is the returned metadata
                and metadata is a dict with the 'number_returned',
                'total_matches' and 'update_id' integers
        """
        response = self.contentDirectory.Browse([
            ('ObjectID', search),
            ('BrowseFlag', 'BrowseDirectChildren'),
            ('Filter', '*'),
            ('StartingIndex', start),
            ('RequestedCount', max_items),
            ('SortCriteria', '')
            ])

        # Get result information
        metadata = {}
        for tag in ['NumberReturned', 'TotalMatches', 'UpdateID']:
            metadata[camel_to_underscore(tag)] = int(response[tag])
        return response, metadata

    def add_uri_to_queue(self, uri):
        """Adds the URI to the queue

        :param uri: The URI to be added to the queue
        :type uri: str
        """
        item = URI(uri)
        self.add_to_queue(item)

    def add_to_queue(self, queueable_item):
        """ Adds a queueable item to the queue """
        # Check if teh required attributes are there
        for attribute in ['didl_metadata', 'uri']:
            if not hasattr(queueable_item, attribute):
                message = 'queueable_item has no attribute {0}'.\
                    format(attribute)
                raise AttributeError(message)
        # Get the metadata
        try:
            metadata = XML.tostring(queueable_item.didl_metadata)
        except CannotCreateDIDLMetadata as exception:
            message = ('The queueable item could not be enqueued, because it '
                       'raised a CannotCreateDIDLMetadata exception with the '
                       'following message:\n{0}').format(str(exception))
            raise ValueError(message)
        if isinstance(metadata, str):
            metadata = metadata.encode('utf-8')

        response = self.avTransport.AddURIToQueue([
            ('InstanceID', 0),
            ('EnqueuedURI', queueable_item.uri),
            ('EnqueuedURIMetaData', metadata),
            ('DesiredFirstTrackNumberEnqueued', 0),
            ('EnqueueAsNext', 1)
            ])
        qnumber = response['FirstTrackNumberEnqueued']
        return int(qnumber)

    def remove_from_queue(self, index):
        """ Remove a track from the queue by index. The index number is
        required as an argument, where the first index is 0.

        index: the index of the track to remove; first item in the queue is 0

        Returns:
            True if the Sonos speaker successfully removed the track

        Raises SoCoException (or a subclass) upon errors.

        """
        # TODO: what do these parameters actually do?
        updid = '0'
        objid = 'Q:0/' + str(index + 1)
        self.avTransport.RemoveTrackFromQueue([
            ('InstanceID', 0),
            ('ObjectID', objid),
            ('UpdateID', updid),
            ])

    def clear_queue(self):
        """ Removes all tracks from the queue.

        Returns:
        True if the Sonos speaker cleared the queue.

        Raises SoCoException (or a subclass) upon errors.

        """
        self.avTransport.RemoveAllTracksFromQueue([
            ('InstanceID', 0),
            ])

    def get_favorite_radio_shows(self, start=0, max_items=100):
        """ Get favorite radio shows from Sonos' Radio app.

        Returns:
        A list containing the total number of favorites, the number of
        favorites returned, and the actual list of favorite radio shows,
        represented as a dictionary with `title` and `uri` keys.

        Depending on what you're building, you'll want to check to see if the
        total number of favorites is greater than the amount you
        requested (`max_items`), if it is, use `start` to page through and
        get the entire list of favorites.

        """

        return self.__get_radio_favorites(RADIO_SHOWS, start, max_items)

    def get_favorite_radio_stations(self, start=0, max_items=100):
        """ Get favorite radio stations from Sonos' Radio app.

        Returns:
        A list containing the total number of favorites, the number of
        favorites returned, and the actual list of favorite radio stations,
        represented as a dictionary with `title` and `uri` keys.

        Depending on what you're building, you'll want to check to see if the
        total number of favorites is greater than the amount you
        requested (`max_items`), if it is, use `start` to page through and
        get the entire list of favorites.

        """
        return self.__get_radio_favorites(RADIO_STATIONS, start, max_items)

    def __get_radio_favorites(self, favorite_type, start=0, max_items=100):
        """ Helper method for `get_favorite_radio_*` methods.

        Arguments:
        favorite_type -- Specify either `RADIO_STATIONS` or `RADIO_SHOWS`.
        start -- Which number to start the retrieval from. Used for paging.
        max_items -- The total number of results to return.

        """
        if favorite_type != RADIO_SHOWS or RADIO_STATIONS:
            favorite_type = RADIO_STATIONS

        response = self.contentDirectory.Browse([
            ('ObjectID', 'R:0/{0}'.format(favorite_type)),
            ('BrowseFlag', 'BrowseDirectChildren'),
            ('Filter', '*'),
            ('StartingIndex', start),
            ('RequestedCount', max_items),
            ('SortCriteria', '')
            ])
        result = {}
        favorites = []
        results_xml = response['Result']

        if results_xml != '':
            # Favorites are returned in DIDL-Lite format
            metadata = XML.fromstring(really_utf8(results_xml))

            for item in metadata.findall(
                    '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item'):
                favorite = {}
                favorite['title'] = item.findtext(
                    '{http://purl.org/dc/elements/1.1/}title')
                favorite['uri'] = item.findtext(
                    '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res')
                favorites.append(favorite)

        result['total'] = response['TotalMatches']
        result['returned'] = len(favorites)
        result['favorites'] = favorites

        return result


# definition section

RADIO_STATIONS = 0
RADIO_SHOWS = 1

NS = {'dc': '{http://purl.org/dc/elements/1.1/}',
      'upnp': '{urn:schemas-upnp-org:metadata-1-0/upnp/}',
      '': '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}'}
# Valid play modes
PLAY_MODES = ('NORMAL', 'SHUFFLE_NOREPEAT', 'SHUFFLE', 'REPEAT_ALL')

if config.SOCO_CLASS is None:
    config.SOCO_CLASS = SoCo
