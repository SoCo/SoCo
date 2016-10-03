# -*- coding: utf-8 -*-
# pylint: disable=fixme, protected-access
"""The core module contains the SoCo class that implements
the main entry to the SoCo functionality
"""

from __future__ import unicode_literals

import datetime
import logging
import re
import socket
from functools import wraps
import warnings
from soco.exceptions import SoCoUPnPException


import requests

from . import config
from .compat import UnicodeType
from .data_structures import (
    DidlObject, DidlPlaylistContainer, DidlResource,
    Queue, from_didl_string, to_didl_string
)
from .exceptions import SoCoSlaveException
from .groups import ZoneGroup
from .music_library import MusicLibrary
from .services import (
    DeviceProperties, ContentDirectory, RenderingControl, AVTransport,
    ZoneGroupTopology, AlarmClock, SystemProperties, MusicServices,
    zone_group_state_shared_cache,
)
from .utils import (
    really_utf8, camel_to_underscore, deprecated
)
from .xml import XML

_LOG = logging.getLogger(__name__)


class _ArgsSingleton(type):

    """A metaclass which permits only a single instance of each derived class
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


class _SocoSingletonBase(  # pylint: disable=too-few-public-methods,no-init
        _ArgsSingleton(str('ArgsSingletonMeta'), (object,), {})):

    """The base class for the SoCo class.

    Uses a Python 2 and 3 compatible method of declaring a metaclass. See, eg,
    here: http://www.artima.com/weblogs/viewpost.jsp?thread=236234 and
    here: http://mikewatkins.ca/2008/11/29/python-2-and-3-metaclasses/
    """
    pass


def only_on_master(function):
    """Decorator that raises SoCoSlaveException on master call on slave."""
    @wraps(function)
    def inner_function(self, *args, **kwargs):
        """Master checking inner function."""
        if not self.is_coordinator:
            message = 'The method or property "{0}" can only be called/used '\
                'on the coordinator in a group'.format(function.__name__)
            raise SoCoSlaveException(message)
        return function(self, *args, **kwargs)
    return inner_function


# pylint: disable=R0904,too-many-instance-attributes
class SoCo(_SocoSingletonBase):

    """A simple class for controlling a Sonos speaker.

    For any given set of arguments to __init__, only one instance of this class
    may be created. Subsequent attempts to create an instance with the same
    arguments will return the previously created instance. This means that all
    SoCo instances created with the same ip address are in fact the *same* SoCo
    instance, reflecting the real world position.

    ..  rubric:: Methods
    ..  autosummary::

        play
        play_uri
        play_from_queue
        pause
        stop
        seek
        next
        previous
        switch_to_line_in
        switch_to_tv
        get_current_track_info
        get_speaker_info
        partymode
        join
        unjoin
        get_queue
        get_current_transport_info
        add_uri_to_queue
        add_to_queue
        remove_from_queue
        clear_queue
        get_favorite_radio_shows
        get_favorite_radio_stations
        get_sonos_favorites
        create_sonos_playlist
        create_sonos_playlist_from_queue
        remove_sonos_playlist
        add_item_to_sonos_playlist
        get_item_album_art_uri
        set_sleep_timer
        get_sleep_timer

    ..  rubric:: Properties
    .. warning::

        These properties are not generally cached and may obtain information
        over the network, so may take longer than expected to set or return
        a value. It may be a good idea for you to cache the value in your
        own code.

    ..  autosummary::

        uid
        household_id
        mute
        volume
        bass
        treble
        loudness
        cross_fade
        status_light
        player_name
        play_mode
        queue_size

        is_playing_tv
        is_playing_radio
        is_playing_line_in


    """

    _class_group = 'SoCo'

    # pylint: disable=super-on-old-class
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
        self.systemProperties = SystemProperties(self)
        self.musicServices = MusicServices(self)

        self.music_library = MusicLibrary(self)

        # Some private attributes
        self._all_zones = set()
        self._groups = set()
        self._is_bridge = None
        self._is_coordinator = False
        self._player_name = None
        self._uid = None
        self._household_id = None
        self._visible_zones = set()
        self._zgs_cache = None

        _LOG.debug("Created SoCo instance for ip: %s", ip_address)

    def __str__(self):
        return "<{0} object at ip {1}>".format(
            self.__class__.__name__, self.ip_address)

    def __repr__(self):
        return '{0}("{1}")'.format(self.__class__.__name__, self.ip_address)

    @property
    def player_name(self):
        """The speaker's name.

        A string.
        """
        # We could get the name like this:
        # result = self.deviceProperties.GetZoneAttributes()
        # return result["CurrentZoneName"]
        # but it is probably quicker to get it from the group topology
        # and take advantage of any caching
        self._parse_zone_group_state()
        return self._player_name

    @player_name.setter
    def player_name(self, playername):
        """Set the speaker's name."""
        self.deviceProperties.SetZoneAttributes([
            ('DesiredZoneName', playername),
            ('DesiredIcon', ''),
            ('DesiredConfiguration', '')
        ])

    @property
    def uid(self):
        """A unique identifier.

        Looks like: ``'RINCON_000XXXXXXXXXX1400'``
        """
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
    def household_id(self):
        """A unique identifier for all players in a household.

        Looks like: ``'Sonos_asahHKgjgJGjgjGjggjJgjJG34'``
        """
        # Since this does not change over time (?) check whether we already
        # know the answer. If so, return the cached version
        if self._household_id is None:
            self._household_id = self.deviceProperties.GetHouseholdID()[
                'CurrentHouseholdID']
        return self._household_id

    @property
    def is_visible(self):
        """Is this zone visible? A zone might be invisible if, for example it
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
        """Is this zone a bridge?"""
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
        """Return True if this zone is a group coordinator, otherwise False.

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
        """str: The queue's play mode.

        Case-insensitive options are:

        *   ``'NORMAL'`` -- Turns off shuffle and repeat.
        *   ``'REPEAT_ALL'`` -- Turns on repeat and turns off shuffle.
        *   ``'SHUFFLE'`` -- Turns on shuffle *and* repeat. (It's
            strange, I know.)
        *   ``'SHUFFLE_NOREPEAT'`` -- Turns on shuffle and turns off
            repeat.

        """
        result = self.avTransport.GetTransportSettings([
            ('InstanceID', 0),
        ])
        return result['PlayMode']

    @play_mode.setter
    def play_mode(self, playmode):
        """Set the speaker's mode."""
        playmode = playmode.upper()
        if playmode not in PLAY_MODES:
            raise KeyError("'%s' is not a valid play mode" % playmode)

        self.avTransport.SetPlayMode([
            ('InstanceID', 0),
            ('NewPlayMode', playmode)
        ])

    @property
    @only_on_master  # Only for symmetry with the setter
    def cross_fade(self):
        """The speaker's cross fade state.

        True if enabled, False otherwise
        """

        response = self.avTransport.GetCrossfadeMode([
            ('InstanceID', 0),
        ])
        cross_fade_state = response['CrossfadeMode']
        return True if int(cross_fade_state) else False

    @cross_fade.setter
    @only_on_master
    def cross_fade(self, crossfade):
        """Set the speaker's cross fade state."""
        crossfade_value = '1' if crossfade else '0'
        self.avTransport.SetCrossfadeMode([
            ('InstanceID', 0),
            ('CrossfadeMode', crossfade_value)
        ])

    @only_on_master
    def play_from_queue(self, index, start=True):
        """ Play a track from the queue by index. The index number is
        required as an argument, where the first index is 0.

        index: the index of the track to play; first item in the queue is 0
        start: If the item that has been set should start playing

        Returns:
        True if the Sonos speaker successfully started playing the track.
        False if the track did not start (this may be because it was not
        requested to start because "start=False")

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

        # finally, just play what's set if needed
        if start:
            return self.play()
        return False

    @only_on_master
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

    @only_on_master
    def play_uri(self, uri='', meta='', title='', start=True):
        """Play a given stream. Pauses the queue. If there is no metadata
        passed in and there is a title set then a metadata object will be
        created. This is often the case if you have a custom stream, it will
        need at least the title in the metadata in order to play.

        Arguments:
        uri -- URI of a stream to be played.
        meta -- The track metadata to show in the player, DIDL format.
        title -- The track title to show in the player
        start -- If the URI that has been set should start playing

        Returns:
        True if the Sonos speaker successfully started playing the track.
        False if the track did not start (this may be because it was not
        requested to start because "start=False")

        Raises SoCoException (or a subclass) upon errors.
        """
        if meta == '' and title != '':
            meta_template = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements'\
                '/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '\
                'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '\
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'\
                '<item id="R:0/0/0" parentID="R:0/0" restricted="true">'\
                '<dc:title>{title}</dc:title><upnp:class>'\
                'object.item.audioItem.audioBroadcast</upnp:class><desc '\
                'id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:'\
                'metadata-1-0/">{service}</desc></item></DIDL-Lite>'
            tunein_service = 'SA_RINCON65031_'
            # Radio stations need to have at least a title to play
            meta = meta_template.format(title=title, service=tunein_service)

        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', uri),
            ('CurrentURIMetaData', meta)
        ])
        # The track is enqueued, now play it if needed
        if start:
            return self.play()
        return False

    @only_on_master
    def pause(self):
        """Pause the currently playing track.

        Returns:
        True if the Sonos speaker successfully paused the track.

        Raises SoCoException (or a subclass) upon errors.
        """
        self.avTransport.Pause([
            ('InstanceID', 0),
            ('Speed', 1)
        ])

    @only_on_master
    def stop(self):
        """Stop the currently playing track.

        Returns:
        True if the Sonos speaker successfully stopped the playing track.

        Raises SoCoException (or a subclass) upon errors.
        """
        self.avTransport.Stop([
            ('InstanceID', 0),
            ('Speed', 1)
        ])

    @only_on_master
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

    @only_on_master
    def next(self):
        """Go to the next track.

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

    @only_on_master
    def previous(self):
        """Go back to the previously played track.

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
        """The speaker's mute state.

        True if muted, False otherwise
        """

        response = self.renderingControl.GetMute([
            ('InstanceID', 0),
            ('Channel', 'Master')
        ])
        mute_state = response['CurrentMute']
        return True if int(mute_state) else False

    @mute.setter
    def mute(self, mute):
        """Mute (or unmute) the speaker."""
        mute_value = '1' if mute else '0'
        self.renderingControl.SetMute([
            ('InstanceID', 0),
            ('Channel', 'Master'),
            ('DesiredMute', mute_value)
        ])

    @property
    def volume(self):
        """The speaker's volume.

        An integer between 0 and 100.
        """

        response = self.renderingControl.GetVolume([
            ('InstanceID', 0),
            ('Channel', 'Master'),
        ])
        volume = response['CurrentVolume']
        return int(volume)

    @volume.setter
    def volume(self, volume):
        """Set the speaker's volume."""
        volume = int(volume)
        volume = max(0, min(volume, 100))  # Coerce in range
        self.renderingControl.SetVolume([
            ('InstanceID', 0),
            ('Channel', 'Master'),
            ('DesiredVolume', volume)
        ])

    @property
    def bass(self):
        """The speaker's bass EQ.

        An integer between -10 and 10.
        """

        response = self.renderingControl.GetBass([
            ('InstanceID', 0),
            ('Channel', 'Master'),
        ])
        bass = response['CurrentBass']
        return int(bass)

    @bass.setter
    def bass(self, bass):
        """Set the speaker's bass."""
        bass = int(bass)
        bass = max(-10, min(bass, 10))  # Coerce in range
        self.renderingControl.SetBass([
            ('InstanceID', 0),
            ('DesiredBass', bass)
        ])

    @property
    def treble(self):
        """The speaker's treble EQ.

        An integer between -10 and 10.
        """

        response = self.renderingControl.GetTreble([
            ('InstanceID', 0),
            ('Channel', 'Master'),
        ])
        treble = response['CurrentTreble']
        return int(treble)

    @treble.setter
    def treble(self, treble):
        """Set the speaker's treble."""
        treble = int(treble)
        treble = max(-10, min(treble, 10))  # Coerce in range
        self.renderingControl.SetTreble([
            ('InstanceID', 0),
            ('DesiredTreble', treble)
        ])

    @property
    def loudness(self):
        """The Sonos speaker's loudness compensation. True if on, otherwise
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
        """Switch on/off the speaker's loudness compensation."""
        loudness_value = '1' if loudness else '0'
        self.renderingControl.SetLoudness([
            ('InstanceID', 0),
            ('Channel', 'Master'),
            ('DesiredLoudness', loudness_value)
        ])

    def _parse_zone_group_state(self):
        """The Zone Group State contains a lot of useful information.

        Retrieve and parse it, and populate the relevant properties.
        """

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

        def parse_zone_group_member(member_element):
            """Parse a ZoneGroupMember or Satellite element from Zone Group
            State, create a SoCo instance for the member, set basic attributes
            and return it."""
            # Create a SoCo instance for each member. Because SoCo
            # instances are singletons, this is cheap if they have already
            # been created, and useful if they haven't. We can then
            # update various properties for that instance.
            member_attribs = member_element.attrib
            ip_addr = member_attribs['Location'].\
                split('//')[1].split(':')[0]
            zone = config.SOCO_CLASS(ip_addr)
            # uid doesn't change, but it's not harmful to (re)set it, in case
            # the zone is as yet unseen.
            zone._uid = member_attribs['UUID']
            zone._player_name = member_attribs['ZoneName']
            # add the zone to the set of all members, and to the set
            # of visible members if appropriate
            is_visible = False if member_attribs.get(
                'Invisible') == '1' else True
            if is_visible:
                self._visible_zones.add(zone)
            self._all_zones.add(zone)
            return zone

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
            group_coordinator = None
            members = set()
            for member_element in group_element.findall('ZoneGroupMember'):
                zone = parse_zone_group_member(member_element)
                # Perform extra processing relevant to direct zone group
                # members
                #
                # If this element has the same UUID as the coordinator, it is
                # the coordinator
                if zone._uid == coordinator_uid:
                    group_coordinator = zone
                    zone._is_coordinator = True
                else:
                    zone._is_coordinator = False
                # is_bridge doesn't change, but it does no real harm to
                # set/reset it here, just in case the zone has not been seen
                # before
                zone._is_bridge = True if member_element.attrib.get(
                    'IsZoneBridge') == '1' else False
                # add the zone to the members for this group
                members.add(zone)
                # Loop over Satellite elements if present, and process as for
                # ZoneGroup elements
                for satellite_element in member_element.findall('Satellite'):
                    zone = parse_zone_group_member(satellite_element)
                    # Assume a satellite can't be a bridge or coordinator, so
                    # no need to check.
                    #
                    # Add the zone to the members for this group.
                    members.add(zone)
                # Now create a ZoneGroup with this info and add it to the list
                # of groups
            self._groups.add(ZoneGroup(group_uid, group_coordinator, members))

    @property
    def all_groups(self):
        """Return a set of all the available groups."""
        self._parse_zone_group_state()
        return self._groups

    @property
    def group(self):
        """The Zone Group of which this device is a member.

        group will be None if this zone is a slave in a stereo pair.
        """

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
        """Return a set of all the available zones."""
        self._parse_zone_group_state()
        return self._all_zones

    @property
    def visible_zones(self):
        """Return an set of all visible zones."""
        self._parse_zone_group_state()
        return self._visible_zones

    def partymode(self):
        """Put all the speakers in the network in the same group, a.k.a Party
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
        """Join this speaker to another "master" speaker.

        ..  note:: The signature of this method has changed in 0.8. It now
            requires a SoCo instance to be passed as `master`, not an IP
            address
        """
        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', 'x-rincon:{0}'.format(master.uid)),
            ('CurrentURIMetaData', '')
        ])
        zone_group_state_shared_cache.clear()
        self._parse_zone_group_state()

    def unjoin(self):
        """Remove this speaker from a group.

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
        zone_group_state_shared_cache.clear()
        self._parse_zone_group_state()

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

    @property
    def is_playing_radio(self):
        """Is the speaker playing radio?

        return True or False
        """
        response = self.avTransport.GetPositionInfo([
            ('InstanceID', 0),
            ('Channel', 'Master')
        ])
        track_uri = response['TrackURI']
        return re.match(r'^x-rincon-mp3radio:', track_uri) is not None

    @property
    def is_playing_line_in(self):
        """ Is the speaker playing line-in?

        return True or False
        """
        response = self.avTransport.GetPositionInfo([
            ('InstanceID', 0),
            ('Channel', 'Master')
        ])
        track_uri = response['TrackURI']
        return re.match(r'^x-rincon-stream:', track_uri) is not None

    @property
    def is_playing_tv(self):
        """Is the playbar speaker input from TV?

        return True or False
        """
        response = self.avTransport.GetPositionInfo([
            ('InstanceID', 0),
            ('Channel', 'Master')
        ])
        track_uri = response['TrackURI']
        return re.match(r'^x-sonos-htastream:', track_uri) is not None

    def switch_to_tv(self):
        """Switch the playbar speaker's input to TV.

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
        """The white Sonos status light between the mute button and the volume
        up button on the speaker.

        True if on, otherwise False.
        """
        result = self.deviceProperties.GetLEDState()
        LEDState = result["CurrentLEDState"]  # pylint: disable=invalid-name
        return True if LEDState == "On" else False

    @status_light.setter
    def status_light(self, led_on):
        """Switch on/off the speaker's status light."""
        led_state = 'On' if led_on else 'Off'
        self.deviceProperties.SetLEDState([
            ('DesiredLEDState', led_state),
        ])

    def get_current_track_info(self):
        """Get information about the currently playing track.

        Returns:
        A dictionary containing the following information about the currently
        playing track: playlist_position, duration, title, artist, album,
        position and a link to the album art.

        If we're unable to return data for a field, we'll return an empty
        string. This can happen for all kinds of reasons so be sure to check
        values. For example, a track may not have complete metadata and be
        missing an album name. In this case track['album'] will be an empty
        string.

        .. note:: Calling this method on a slave in a group will not
            return the track the group is playing, but the last track
            this speaker was playing.

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
        # Store the entire Metadata entry in the track, this can then be
        # used if needed by the client to restart a given URI
        track['metadata'] = metadata
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
                # Might find some kind of title anyway in metadata
                track['title'] = metadata.findtext('.//{http://purl.org/dc/'
                                                   'elements/1.1/}title')
                if not track['title']:
                    _LOG.warning('Could not handle track info: "%s"',
                                 trackinfo)
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

            album_art_url = metadata.findtext(
                './/{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI')
            if album_art_url is not None:
                track['album_art'] = self._build_album_art_full_uri(
                    album_art_url)

        return track

    def get_speaker_info(self, refresh=False, timeout=None):
        """Get information about the Sonos speaker.

        Arguments:
        refresh -- Refresh the speaker info cache.
        timeout -- How long to wait for the server to send
                   data before giving up, as a float, or a
                   (`connect timeout, read timeout`_) tuple
                   e.g. (3, 5). Default is no timeout.

        Returns:
        Information about the Sonos speaker, such as the UID, MAC Address, and
        Zone Name.
        """
        if self.speaker_info and refresh is False:
            return self.speaker_info
        else:
            response = requests.get('http://' + self.ip_address +
                                    ':1400/xml/device_description.xml',
                                    timeout=timeout)
            dom = XML.fromstring(response.content)

        device = dom.find('{urn:schemas-upnp-org:device-1-0}device')
        if device is not None:
            self.speaker_info['zone_name'] = device.findtext(
                '{urn:schemas-upnp-org:device-1-0}roomName')

            # no zone icon in device_description.xml -> player icon
            self.speaker_info['player_icon'] = device.findtext(
                '{urn:schemas-upnp-org:device-1-0}iconList/'
                '{urn:schemas-upnp-org:device-1-0}icon/'
                '{urn:schemas-upnp-org:device-1-0}url'
            )

            self.speaker_info['uid'] = self.uid
            self.speaker_info['serial_number'] = device.findtext(
                '{urn:schemas-upnp-org:device-1-0}serialNum')
            self.speaker_info['software_version'] = device.findtext(
                '{urn:schemas-upnp-org:device-1-0}softwareVersion')
            self.speaker_info['hardware_version'] = device.findtext(
                '{urn:schemas-upnp-org:device-1-0}hardwareVersion')
            self.speaker_info['model_number'] = device.findtext(
                '{urn:schemas-upnp-org:device-1-0}modelNumber')
            self.speaker_info['model_name'] = device.findtext(
                '{urn:schemas-upnp-org:device-1-0}modelName')
            self.speaker_info['display_version'] = device.findtext(
                '{urn:schemas-upnp-org:device-1-0}displayVersion')

            # no mac address - extract from serial number
            mac = self.speaker_info['serial_number'].split(':')[0]
            self.speaker_info['mac_address'] = mac

            return self.speaker_info

    def get_current_transport_info(self):
        """Get the current playback state.

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

    def get_queue(self, start=0, max_items=100, full_album_art_uri=False):
        """Get information about the queue.

        :param start: Starting number of returned matches
        :param max_items: Maximum number of returned matches
        :param full_album_art_uri: If the album art URI should include the
            IP address
        :returns: A :py:class:`~.soco.data_structures.Queue` object

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

        metadata = {}
        for tag in ['NumberReturned', 'TotalMatches', 'UpdateID']:
            metadata[camel_to_underscore(tag)] = int(response[tag])

        # I'm not sure this necessary (any more). Even with an empty queue,
        # there is still a result object. This shoud be investigated.
        if not result:
            # pylint: disable=star-args
            return Queue(queue, **metadata)

        items = from_didl_string(result)
        for item in items:
            # Check if the album art URI should be fully qualified
            if full_album_art_uri:
                self._update_album_art_to_full_uri(item)
            queue.append(item)

        # pylint: disable=star-args
        return Queue(queue, **metadata)

    @property
    def queue_size(self):
        """Get size of queue."""
        response = self.contentDirectory.Browse([
            ('ObjectID', 'Q:0'),
            ('BrowseFlag', 'BrowseMetadata'),
            ('Filter', '*'),
            ('StartingIndex', 0),
            ('RequestedCount', 1),
            ('SortCriteria', '')
        ])
        dom = XML.fromstring(really_utf8(response['Result']))

        queue_size = None
        container = dom.find(
            '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}container')
        if container is not None:
            child_count = container.get('childCount')
            if child_count is not None:
                queue_size = int(child_count)

        return queue_size

    def get_sonos_playlists(self, *args, **kwargs):
        """ Convenience method for:
            get_music_library_information('sonos_playlists')
            Refer to the docstring for that method

        """
        args = tuple(['sonos_playlists'] + list(args))
        return self.music_library.get_music_library_information(*args,
                                                                **kwargs)

    @only_on_master
    def add_uri_to_queue(self, uri):
        """Adds the URI to the queue.

        :param uri: The URI to be added to the queue
        :type uri: str
        """
        # FIXME: The res.protocol_info should probably represent the mime type
        # etc of the uri. But this seems OK.
        res = [DidlResource(uri=uri, protocol_info="x-rincon-playlist:*:*:*")]
        item = DidlObject(resources=res, title='', parent_id='', item_id='')
        return self.add_to_queue(item)

    @only_on_master
    def add_to_queue(self, queueable_item):
        """Adds a queueable item to the queue."""
        metadata = to_didl_string(queueable_item)
        response = self.avTransport.AddURIToQueue([
            ('InstanceID', 0),
            ('EnqueuedURI', queueable_item.resources[0].uri),
            ('EnqueuedURIMetaData', metadata),
            ('DesiredFirstTrackNumberEnqueued', 0),
            ('EnqueueAsNext', 1)
        ])
        qnumber = response['FirstTrackNumberEnqueued']
        return int(qnumber)

    @only_on_master
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

    @only_on_master
    def clear_queue(self):
        """Removes all tracks from the queue.

        Returns:
        True if the Sonos speaker cleared the queue.

        Raises SoCoException (or a subclass) upon errors.
        """
        self.avTransport.RemoveAllTracksFromQueue([
            ('InstanceID', 0),
        ])

    def get_favorite_radio_shows(self, start=0, max_items=100):
        """Get favorite radio shows from Sonos' Radio app.

        Returns:
        A list containing the total number of favorites, the number of
        favorites returned, and the actual list of favorite radio shows,
        represented as a dictionary with `title` and `uri` keys.

        Depending on what you're building, you'll want to check to see if the
        total number of favorites is greater than the amount you
        requested (`max_items`), if it is, use `start` to page through and
        get the entire list of favorites.
        """
        message = 'The output type of this method will probably change in '\
                  'the future to use SoCo data structures'
        warnings.warn(message, stacklevel=2)
        return self.__get_favorites(RADIO_SHOWS, start, max_items)

    def get_favorite_radio_stations(self, start=0, max_items=100):
        """Get favorite radio stations from Sonos' Radio app.

        Returns:
        A list containing the total number of favorites, the number of
        favorites returned, and the actual list of favorite radio stations,
        represented as a dictionary with `title` and `uri` keys.

        Depending on what you're building, you'll want to check to see if the
        total number of favorites is greater than the amount you
        requested (`max_items`), if it is, use `start` to page through and
        get the entire list of favorites.
        """
        message = 'The output type of this method will probably change in '\
                  'the future to use SoCo data structures'
        warnings.warn(message, stacklevel=2)
        return self.__get_favorites(RADIO_STATIONS, start, max_items)

    def get_sonos_favorites(self, start=0, max_items=100):
        """Get Sonos favorites.

        Returns:
        A list containing the total number of favorites, the number of
        favorites returned, and the actual list of favorite radio stations,
        represented as a dictionary with `title`, `uri` and `meta` keys.

        Depending on what you're building, you'll want to check to see if the
        total number of favorites is greater than the amount you
        requested (`max_items`), if it is, use `start` to page through and
        get the entire list of favorites.
        """
        message = 'The output type of this method will probably change in '\
                  'the future to use SoCo data structures'
        warnings.warn(message, stacklevel=2)
        return self.__get_favorites(SONOS_FAVORITES, start, max_items)

    def __get_favorites(self, favorite_type, start=0, max_items=100):
        """ Helper method for `get_favorite_radio_*` methods.

        Arguments:
        favorite_type -- Specify either `RADIO_STATIONS` or `RADIO_SHOWS`.
        start -- Which number to start the retrieval from. Used for paging.
        max_items -- The total number of results to return.

        """
        if favorite_type != RADIO_SHOWS and favorite_type != RADIO_STATIONS:
            favorite_type = SONOS_FAVORITES

        response = self.contentDirectory.Browse([
            ('ObjectID',
             'FV:2' if favorite_type is SONOS_FAVORITES
             else 'R:0/{0}'.format(favorite_type)),
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
                    '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}container'
                    if favorite_type == RADIO_SHOWS else
                    '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item'):
                favorite = {}
                favorite['title'] = item.findtext(
                    '{http://purl.org/dc/elements/1.1/}title')
                favorite['uri'] = item.findtext(
                    '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res')
                if favorite_type == SONOS_FAVORITES:
                    favorite['meta'] = item.findtext(
                        '{urn:schemas-rinconnetworks-com:metadata-1-0/}resMD')
                favorites.append(favorite)

        result['total'] = response['TotalMatches']
        result['returned'] = len(favorites)
        result['favorites'] = favorites

        return result

    def _update_album_art_to_full_uri(self, item):
        """Update an item's Album Art URI to be an absolute URI.

        :param item: The item to update the URI for
        """
        if getattr(item, 'album_art_uri', False):
            item.album_art_uri = self._build_album_art_full_uri(
                item.album_art_uri)

    def create_sonos_playlist(self, title):
        """Create a new empty Sonos playlist.

        :params title: Name of the playlist

        :returns: An instance of
            :py:class:`~.soco.data_structures.DidlPlaylistContainer`
        """
        response = self.avTransport.CreateSavedQueue([
            ('InstanceID', 0),
            ('Title', title),
            ('EnqueuedURI', ''),
            ('EnqueuedURIMetaData', ''),
        ])

        item_id = response['AssignedObjectID']
        obj_id = item_id.split(':', 2)[1]
        uri = "file:///jffs/settings/savedqueues.rsq#{0}".format(obj_id)

        res = [DidlResource(uri=uri, protocol_info="x-rincon-playlist:*:*:*")]
        return DidlPlaylistContainer(
            resources=res, title=title, parent_id='SQ:', item_id=item_id)

    @only_on_master
    # pylint: disable=invalid-name
    def create_sonos_playlist_from_queue(self, title):
        """Create a new Sonos playlist from the current queue.

        :params title: Name of the playlist

        :returns: An instance of
            :py:class:`~.soco.data_structures.DidlPlaylistContainer`
        """
        # Note: probably same as Queue service method SaveAsSonosPlaylist
        # but this has not been tested.  This method is what the
        # controller uses.
        response = self.avTransport.SaveQueue([
            ('InstanceID', 0),
            ('Title', title),
            ('ObjectID', '')
        ])
        item_id = response['AssignedObjectID']
        obj_id = item_id.split(':', 2)[1]
        uri = "file:///jffs/settings/savedqueues.rsq#{0}".format(obj_id)
        res = [DidlResource(uri=uri, protocol_info="x-rincon-playlist:*:*:*")]
        return DidlPlaylistContainer(
            resources=res, title=title, parent_id='SQ:', item_id=item_id)

    @only_on_master
    def remove_sonos_playlist(self, sonos_playlist):
        """Remove a Sonos playlist.

        Args:
            sonos_playlist (DidlPlaylistContainer): Sonos playlist to remove
                or the item_id (str).

        Returns:
            bool: True if succesful, False otherwise

        Raises:
            SoCoUPnPException: If sonos_playlist does not point to a valid
                object.

        """
        object_id = getattr(sonos_playlist, 'item_id', sonos_playlist)
        return self.contentDirectory.DestroyObject([('ObjectID', object_id)])

    def add_item_to_sonos_playlist(self, queueable_item, sonos_playlist):
        """Adds a queueable item to a Sonos' playlist.

        :param queueable_item: the item to add to the Sonos' playlist
        :param sonos_playlist: the Sonos' playlist to which the item should
            be added
        """
        # Get the update_id for the playlist
        response, _ = self.music_library._music_lib_search(
            sonos_playlist.item_id, 0, 1)
        update_id = response['UpdateID']

        # Form the metadata for queueable_item
        metadata = to_didl_string(queueable_item)

        # Make the request
        self.avTransport.AddURIToSavedQueue([
            ('InstanceID', 0),
            ('UpdateID', update_id),
            ('ObjectID', sonos_playlist.item_id),
            ('EnqueuedURI', queueable_item.resources[0].uri),
            ('EnqueuedURIMetaData', metadata),
            # 2 ** 32 - 1 = 4294967295, this field has always this value. Most
            # likely, playlist positions are represented as a 32 bit uint and
            # this is therefore the largest index possible. Asking to add at
            # this index therefore probably amounts to adding it "at the end"
            ('AddAtIndex', 4294967295)
        ])

    def get_item_album_art_uri(self, item):
        """Get an item's Album Art absolute URI."""

        if getattr(item, 'album_art_uri', False):
            return self._build_album_art_full_uri(item.album_art_uri)
        else:
            return None

    @only_on_master
    def set_sleep_timer(self, sleep_time_seconds):
        """Sets the sleep timer.

        Args:
            sleep_time_seconds (int or NoneType): How long to wait before
                turning off speaker in seconds, None to cancel a sleep timer.
                Maximum value of 86399

        Raises:
            SoCoException: Upon errors interacting with Sonos controller
            ValueError: Argument/Syntax errors

        """
        # Note: A value of None for sleep_time_seconds is valid, and needs to
        # be preserved distinctly separate from 0. 0 means go to sleep now,
        # which will immediately start the sound tappering, and could be a
        # useful feature, while None means cancel the current timer
        try:
            if sleep_time_seconds is None:
                sleep_time = ''
            else:
                sleep_time = format(
                    datetime.timedelta(seconds=int(sleep_time_seconds))
                )
            self.avTransport.ConfigureSleepTimer([
                ('InstanceID', 0),
                ('NewSleepTimerDuration', sleep_time),
            ])
        except SoCoUPnPException as err:
            if 'Error 402 received' in str(err):
                raise ValueError('invalid sleep_time_seconds, must be integer \
                    value between 0 and 86399 inclusive or None')
            else:
                raise
        except ValueError:
            raise ValueError('invalid sleep_time_seconds, must be integer \
                value between 0 and 86399 inclusive or None')

    @only_on_master
    def get_sleep_timer(self):
        """Retrieves remaining sleep time, if any

        Returns:
            int or NoneType: Number of seconds left in timer. If there is no
                sleep timer currently set it will return None.

        Raises SoCoException (or a subclass) upon errors.

        """
        resp = self.avTransport.GetRemainingSleepTimerDuration([
            ('InstanceID', 0),
        ])
        if resp['RemainingSleepTimerDuration']:
            times = resp['RemainingSleepTimerDuration'].split(':')
            return (int(times[0]) * 3600 +
                    int(times[1]) * 60 +
                    int(times[2]))
        else:
            return None

    # Deprecated methods - moved to music_library.py
    # pylint: disable=missing-docstring, too-many-arguments
    @deprecated('0.12', "soco.music_library.get_artists", '0.14')
    def get_artists(self, *args, **kwargs):
        return self.music_library.get_artists(*args, **kwargs)

    @deprecated('0.12', "soco.music_library.get_album_artists", '0.14')
    def get_album_artists(self, *args, **kwargs):
        return self.music_library.get_album_artists(*args, **kwargs)

    @deprecated('0.12', "soco.music_library.get_music_library_information",
                '0.14')
    def get_albums(self, *args, **kwargs):
        return self.music_library.get_music_library_information(*args,
                                                                **kwargs)

    @deprecated('0.12', "soco.music_library.get_music_library_information",
                '0.14')
    def get_genres(self, *args, **kwargs):
        return self.music_library.get_music_library_information(*args,
                                                                **kwargs)

    @deprecated('0.12', "soco.music_library.get_composers", '0.14')
    def get_composers(self, *args, **kwargs):
        return self.music_library.get_music_library_information(*args,
                                                                **kwargs)

    @deprecated('0.12', "soco.music_library.get_tracks", '0.14')
    def get_tracks(self, *args, **kwargs):
        return self.music_library.get_tracks(*args, **kwargs)

    @deprecated('0.12', "soco.music_library.get_playlists", '0.14')
    def get_playlists(self, *args, **kwargs):
        return self.music_library.get_music_library_information(*args,
                                                                **kwargs)

    @deprecated('0.12', "soco.music_library.get_music_library_information",
                '0.14')
    def get_music_library_information(self, search_type, start=0,
                                      max_items=100, full_album_art_uri=False,
                                      search_term=None, subcategories=None,
                                      complete_result=False):
        return self.music_library.get_music_library_information(
            search_type,
            start,
            max_items,
            full_album_art_uri,
            search_term,
            subcategories,
            complete_result
        )

    @deprecated('0.12', "soco.music_library.browse", '0.14')
    def browse(self, ml_item=None, start=0, max_items=100,
               full_album_art_uri=False, search_term=None, subcategories=None):
        return self.music_library.browse(ml_item, start, max_items,
                                         full_album_art_uri, search_term,
                                         subcategories)

    @deprecated('0.12', "soco.music_library.browse_by_idstring", '0.14')
    def browse_by_idstring(self, search_type, idstring, start=0,
                           max_items=100, full_album_art_uri=False):
        return self.music_library.browse_by_idstring(search_type, idstring,
                                                     start,
                                                     max_items,
                                                     full_album_art_uri)

    @property
    @deprecated('0.12', "soco.music_library.library_updating", '0.14')
    def library_updating(self):
        """.."""
        return self.music_library.library_updating

    @deprecated('0.12', "soco.music_library.start_library_update", '0.14')
    def start_library_update(self, album_artist_display_option=''):
        return self.music_library.start_library_update(
            album_artist_display_option)

    @deprecated('0.12', "soco.music_library.search_track", '0.14')
    def search_track(self, artist, album=None, track=None,
                     full_album_art_uri=False):
        return self.music_library.search_track(
            artist, album, track, full_album_art_uri
        )

    @deprecated('0.12', "soco.music_library.get_albums_for_artist", '0.14')
    def get_albums_for_artist(self, artist, full_album_art_uri=False):
        return self.music_library.get_albums_for_artist(
            artist, full_album_art_uri
        )

    @deprecated('0.12', "soco.music_library.get_tracks_for_album", '0.14')
    def get_tracks_for_album(self, artist, album, full_album_art_uri=False):
        return self.music_library.get_tracks_for_album(
            artist, album, full_album_art_uri
        )

    @property
    @deprecated('0.12', "soco.music_library.album_artist_display", '0.14')
    def album_artist_display_option(self):
        """.."""
        return self.music_library.album_artist_display_option

    def _build_album_art_full_uri(self, url):
        return self.music_library._build_album_art_full_uri(url)

    def _music_lib_search(self, search, start, max_items):
        return self.music_library._music_lib_search(search, start, max_items)

    @only_on_master
    def reorder_sonos_playlist(self, sonos_playlist, tracks, new_pos,
                               update_id=0):
        """Reorder and/or Remove tracks in a Sonos playlist.

        The underlying call is quite complex as it can both move a track
        within the list or delete a track from the playlist.  All of this
        depends on what tracks and new_pos specify.

        If a list is specified for tracks, then a list must be used for
        new_pos. Each list element is a discrete modification and the next
        list operation must anticipate the new state of the playlist.

        If a comma formatted string to tracks is specified, then use
        a similiar string to specify new_pos. Those operations should be
        ordered from the end of the list to the beginning

        See the helper methods
        :py:meth:`clear_sonos_playlist`, :py:meth:`move_in_sonos_playlist`,
        :py:meth:`remove_from_sonos_playlist` for simplified usage.

        update_id - If you have a series of operations, tracking the update_id
        and setting it, will save a lookup operation.

        Examples:
          To reorder the first two tracks::

            # sonos_playlist specified by the DidlPlaylistContainer object
            sonos_playlist = device.get_sonos_playlists()[0]
            device.reorder_sonos_playlist(sonos_playlist,
                                          tracks=[0, ], new_pos=[1, ])
            # OR specified by the item_id
            device.reorder_sonos_playlist('SQ:0', tracks=[0, ], new_pos=[1, ])

          To delete the second track::

            # tracks/new_pos are a list of int
            device.reorder_sonos_playlist(sonos_playlist,
                                          tracks=[1, ], new_pos=[None, ])
            # OR tracks/new_pos are a list of int-like
            device.reorder_sonos_playlist(sonos_playlist,
                                          tracks=['1', ], new_pos=['', ])
            # OR tracks/new_pos are strings - no transform is done
            device.reorder_sonos_playlist(sonos_playlist, tracks='1',
                                          new_pos='')

          To reverse the order of a playlist with 4 items::

            device.reorder_sonos_playlist(sonos_playlist, tracks='3,2,1,0',
                                          new_pos='0,1,2,3')

        Args:
            sonos_playlist
                (:py:class:`~.soco.data_structures.DidlPlaylistContainer`): The
                Sonos playlist object or the item_id (str) of the Sonos
                playlist.
            tracks: (list): list of track indices(int) to reorder. May also be
                a list of int like things. i.e. ``['0', '1',]`` OR it may be a
                str of comma separated int like things. ``"0,1"``.  Tracks are
                **0**-based. Meaning the first track is track 0, just like
                indexing into a Python list.
            new_pos (list): list of new positions (int|None)
                corresponding to track_list. MUST be the same type as
                ``tracks``. **0**-based, see tracks above. ``None`` is the
                indicator to remove the track. If using a list of strings,
                then a remove is indicated by an empty string.
            update_id (int): operation id (default: 0) If set to 0, a lookup
                is done to find the correct value.

        Returns:
            dict: Which contains 3 elements: change, length and update_id.
                Change in size between original playlist and the resulting
                playlist, the length of resulting playlist, and the new
                update_id.

        Raises:
            SoCoUPnPException: If playlist does not exist or if your tracks
                and/or new_pos arguments are invalid.
        """
        # allow either a string 'SQ:10' or an object with item_id attribute.
        object_id = getattr(sonos_playlist, 'item_id', sonos_playlist)

        if isinstance(tracks, UnicodeType):
            track_list = [tracks, ]
            position_list = [new_pos, ]
        elif isinstance(tracks, int):
            track_list = [tracks, ]
            if new_pos is None:
                new_pos = ''
            position_list = [new_pos, ]
        else:
            track_list = [str(x) for x in tracks]
            position_list = [str(x) if x is not None else '' for x in new_pos]
        # track_list = ','.join(track_list)
        # position_list = ','.join(position_list)
        if update_id == 0:  # retrieve the update id for the object
            response, _ = self._music_lib_search(object_id, 0, 1)
            update_id = response['UpdateID']
        change = 0

        for track, position in zip(track_list, position_list):
            if track == position:   # there is no move, a no-op
                continue
            response = self.avTransport.ReorderTracksInSavedQueue([
                ("InstanceID", 0),
                ("ObjectID", object_id),
                ("UpdateID", update_id),
                ("TrackList", track),
                ("NewPositionList", position),
            ])
            change += int(response['QueueLengthChange'])
            update_id = int(response['NewUpdateID'])
        length = int(response['NewQueueLength'])
        response = {'change': change,
                    'update_id': update_id,
                    'length': length}
        return response

    @only_on_master
    def clear_sonos_playlist(self, sonos_playlist, update_id=0):
        """Clear all tracks from a Sonos playlist.
        This is a convenience method for :py:meth:`reorder_sonos_playlist`.

        Example::

            device.clear_sonos_playlist(sonos_playlist)

        Args:
            sonos_playlist
                (:py:class:`~.soco.data_structures.DidlPlaylistContainer`):
                Sonos playlist object or the item_id (str) of the Sonos
                playlist.
            update_id (int): Optional update counter for the object. If left
                at the default of 0, it will be looked up.

        Returns:
            dict: See :py:meth:`reorder_sonos_playlist`

        Raises:
            ValueError: If sonos_playlist specified by string and is not found.
            SoCoUPnPException: See :py:meth:`reorder_sonos_playlist`
        """
        if not isinstance(sonos_playlist, DidlPlaylistContainer):
            sonos_playlist = self.get_sonos_playlist_by_attr('item_id',
                                                             sonos_playlist)
        count = self.music_library.browse(ml_item=sonos_playlist).total_matches
        tracks = ','.join([str(x) for x in range(count)])
        if tracks:
            return self.reorder_sonos_playlist(sonos_playlist, tracks=tracks,
                                               new_pos='', update_id=update_id)
        else:
            return {'change': 0, 'update_id': update_id, 'length': count}

    @only_on_master
    def move_in_sonos_playlist(self, sonos_playlist, track, new_pos,
                               update_id=0):
        """Move a track to a new position within a Sonos Playlist.
        This is a convenience method for :py:meth:`reorder_sonos_playlist`.

        Example::

            device.move_in_sonos_playlist(sonos_playlist, track=0, new_pos=1)

        Args:
            sonos_playlist
                (:py:class:`~.soco.data_structures.DidlPlaylistContainer`):
                Sonos playlist object or the item_id (str) of the Sonos
                playlist.
            track (int): **0**-based position of the track to move. The first
                track is track 0, just like indexing into a Python list.
            new_pos (int): **0**-based location to move the track.
            update_id (int): Optional update counter for the object. If left
                at the default of 0, it will be looked up.

        Returns:
            dict: See :py:meth:`reorder_sonos_playlist`

        Raises:
            SoCoUPnPException: See :py:meth:`reorder_sonos_playlist`
        """
        return self.reorder_sonos_playlist(sonos_playlist, int(track),
                                           int(new_pos), update_id)

    @only_on_master
    def remove_from_sonos_playlist(self, sonos_playlist, track, update_id=0):
        """Remove a track from a Sonos Playlist.
        This is a convenience method for :py:meth:`reorder_sonos_playlist`.

        Example::

            device.remove_from_sonos_playlist(sonos_playlist, track=0)

        Args:
            sonos_playlist
                (:py:class:`~.soco.data_structures.DidlPlaylistContainer`):
                Sonos playlist object or the item_id (str) of the Sonos
                playlist.
            track (int): *0**-based position of the track to move. The first
                track is track 0, just like indexing into a Python list.
            update_id (int): Optional update counter for the object. If left
                at the default of 0, it will be looked up.

        Returns:
            dict: See :py:meth:`reorder_sonos_playlist`

        Raises:
            SoCoUPnPException: See :py:meth:`reorder_sonos_playlist`
        """
        return self.reorder_sonos_playlist(sonos_playlist, int(track), None,
                                           update_id)

    @only_on_master
    def get_sonos_playlist_by_attr(self, attr_name, match):
        """Return the first Sonos Playlist DidlPlaylistContainer that
        matches the attribute specified.

        Args:
            attr_name (str): DidlPlaylistContainer attribute to compare. The
                most useful being: 'title' and 'item_id'.
            match (str): Value to match.

        Returns:
            (:class:`~.soco.data_structures.DidlPlaylistContainer`): The
                first matching playlist object.

        Raises:
            (AttributeError): If indicated attribute name does not exist.
            (ValueError): If a match can not be found.

        Example::

            device.get_sonos_playlist_by_attr('title', 'Foo')
            device.get_sonos_playlist_by_attr('item_id', 'SQ:3')

        """
        for sonos_playlist in self.get_sonos_playlists():
            if getattr(sonos_playlist, attr_name) == match:
                return sonos_playlist
        raise ValueError('No match on "{0}" for value "{1}"'.format(attr_name,
                                                                    match))


# definition section

RADIO_STATIONS = 0
RADIO_SHOWS = 1
SONOS_FAVORITES = 2

NS = {'dc': '{http://purl.org/dc/elements/1.1/}',
      'upnp': '{urn:schemas-upnp-org:metadata-1-0/upnp/}',
      '': '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}'}
# Valid play modes
PLAY_MODES = ('NORMAL', 'SHUFFLE_NOREPEAT', 'SHUFFLE', 'REPEAT_ALL',
              'SHUFFLE_REPEAT_ONE', 'REPEAT_ONE')

if config.SOCO_CLASS is None:
    config.SOCO_CLASS = SoCo
