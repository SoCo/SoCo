# -*- coding: utf-8 -*-
# pylint: disable=C0302,fixme, protected-access
""" The core module contains the SoCo class that implements
the main entry to the SoCo functionality
"""

from __future__ import unicode_literals

import socket
import logging
import re
import requests
from functools import wraps

from .services import DeviceProperties, ContentDirectory
from .services import RenderingControl, AVTransport, ZoneGroupTopology
from .services import AlarmClock
from .groups import ZoneGroup
from .exceptions import SoCoUPnPException, SoCoSlaveException
from .data_structures import DidlPlaylistContainer,\
    SearchResult, Queue, DidlObject, DidlMusicAlbum,\
    from_didl_string, to_didl_string, DidlResource
from .utils import really_utf8, camel_to_underscore, really_unicode,\
    url_escape_path
from .xml import XML
from soco import config

_LOG = logging.getLogger(__name__)


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


class _SocoSingletonBase(  # pylint: disable=too-few-public-methods,no-init
        _ArgsSingleton(str('ArgsSingletonMeta'), (object,), {})):

    """ The base class for the SoCo class.

    Uses a Python 2 and 3 compatible method of declaring a metaclass. See, eg,
    here: http://www.artima.com/weblogs/viewpost.jsp?thread=236234 and
    here: http://mikewatkins.ca/2008/11/29/python-2-and-3-metaclasses/

    """
    pass


def only_on_master(function):
    """Decorator that raises SoCoSlaveException on master call on slave"""
    @wraps(function)
    def inner_function(self, *args, **kwargs):
        """Master checking inner function"""
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
        switch_to_tv -- Switch the playbar speaker's input to TV.
        get_current_track_info -- Get information about the currently playing
                                  track.
        get_speaker_info -- Get information about the Sonos speaker.
        partymode -- Put all the speakers in the network in the same group.
        join -- Join this speaker to another "master" speaker.
        unjoin -- Remove this speaker from a group.
        get_queue -- Get information about the queue.
        get_artists -- Get artists from the music library
        get_album_artists -- Get album artists from the music library
        get_albums -- Get albums from the music library
        get_genres -- Get genres from the music library
        get_composers -- Get composers from the music library
        get_tracks -- Get tracks from the music library
        get_playlists -- Get playlists from the music library
        get_music_library_information -- Get information from the music library
        get_current_transport_info -- get speakers playing state
        browse_by_idstring -- Browse (get sub-elements) a given type
        add_uri_to_queue -- Adds an URI to the queue
        add_to_queue -- Add a track to the end of the queue
        remove_from_queue -- Remove a track from the queue
        clear_queue -- Remove all tracks from queue
        get_favorite_radio_shows -- Get favorite radio shows from Sonos'
                                    Radio app.
        get_favorite_radio_stations -- Get favorite radio stations.
        create_sonos_playlist -- Create a new empty Sonos playlist
        create_sonos_playlist_from_queue -- Create a new Sonos playlist
                                            from the current queue.
        add_item_to_sonos_playlist -- Adds a queueable item to a Sonos'
                                       playlist
        get_item_album_art_uri -- Get an item's Album Art absolute URI.
        search_track -- Search for an artist, artist's albums, or track.
        get_albums_for_artist -- Get albums for an artist.
        get_tracks_for_album -- Get tracks for an artist's album.
        start_library_update -- Trigger an update of the music library.

    Properties::

        uid -- The speaker's unique identifier
        mute -- The speaker's mute status.
        volume -- The speaker's volume.
        bass -- The speaker's bass EQ.
        treble -- The speaker's treble EQ.
        loudness -- The status of the speaker's loudness compensation.
        cross_fade -- The status of the speaker's crossfade.
        status_light -- The state of the Sonos status light.
        player_name  -- The speaker's name.
        play_mode -- The queue's repeat/shuffle settings.
        queue_size -- Get size of queue.
        library_updating -- Whether music library update is in progress.
        album_artist_display_option -- album artist display option
        is_playing_tv -- Is the playbar speaker input from TV?
        is_playing_radio -- Is the speaker input from radio?
        is_playing_line_in -- Is the speaker input from line-in?

    .. warning::

        These properties are not cached and will obtain information over the
        network, so may take longer than expected to set or return a value. It
        may be a good idea for you to cache the value in your own code.

    """

    _class_group = 'SoCo'

    # Key words used when performing searches
    SEARCH_TRANSLATION = {'artists': 'A:ARTIST',
                          'album_artists': 'A:ALBUMARTIST',
                          'albums': 'A:ALBUM',
                          'genres': 'A:GENRE',
                          'composers': 'A:COMPOSER',
                          'tracks': 'A:TRACKS',
                          'playlists': 'A:PLAYLISTS',
                          'share': 'S:',
                          'sonos_playlists': 'SQ:',
                          'categories': 'A:'}

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

        # Some private attributes
        self._all_zones = set()
        self._groups = set()
        self._is_bridge = None
        self._is_coordinator = False
        self._player_name = None
        self._uid = None
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
        """ The queue's play mode. Case-insensitive options are:

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
    @only_on_master  # Only for symmetry with the setter
    def cross_fade(self):
        """ The speaker's cross fade state.
        True if enabled, False otherwise """

        response = self.avTransport.GetCrossfadeMode([
            ('InstanceID', 0),
        ])
        cross_fade_state = response['CrossfadeMode']
        return True if int(cross_fade_state) else False

    @cross_fade.setter
    @only_on_master
    def cross_fade(self, crossfade):
        """ Set the speaker's cross fade state. """
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
        """ Play a given stream. Pauses the queue.
        If there is no metadata passed in and there is a title set then a
        metadata object will be created. This is often the case if you have
        a custom stream, it will need at least the title in the metadata in
        order to play.

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
        """ Pause the currently playing track.

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
        """ Stop the currently playing track.

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

    @only_on_master
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

        def parse_zone_group_member(member_element):
            """ Parse a ZoneGroupMember or Satellite element from Zone Group
            State, create a SoCo instance for the member, set basic attributes
            and return it. """
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

    @property
    def is_playing_radio(self):
        """ Is the speaker playing radio?

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
        """ Is the playbar speaker input from TV?

        return True or False
        """
        response = self.avTransport.GetPositionInfo([
            ('InstanceID', 0),
            ('Channel', 'Master')
        ])
        track_uri = response['TrackURI']
        return re.match(r'^x-sonos-htastream:', track_uri) is not None

    def switch_to_tv(self):
        """ Switch the playbar speaker's input to TV.

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

    def _build_album_art_full_uri(self, url):
        """ Ensure an Album Art URI is an absolute URI

        :param url: The album art URI
        """

        # Add on the full album art link, as the URI version
        # does not include the ipaddress
        if not url.startswith(('http:', 'https:')):
            url = 'http://' + self.ip_address + ':1400' + url
        return url

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

    def get_queue(self, start=0, max_items=100, full_album_art_uri=False):
        """ Get information about the queue

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
        """ Get size of queue """
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
        return self.get_music_library_information(*args, **kwargs)

    def get_artists(self, *args, **kwargs):
        """ Convenience method for :py:meth:`get_music_library_information`
        with `search_type='artists'`. For details on remaining arguments refer
        to the docstring for that method.

        """
        args = tuple(['artists'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    def get_album_artists(self, *args, **kwargs):
        """ Convenience method for :py:meth:`get_music_library_information`
        with `search_type='album_artists'`. For details on remaining arguments
        refer to the docstring for that method.

        """
        args = tuple(['album_artists'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    def get_albums(self, *args, **kwargs):
        """ Convenience method for :py:meth:`get_music_library_information`
        with `search_type='albums'`. For details on remaining arguments refer
        to the docstring for that method.

        """
        args = tuple(['albums'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    def get_genres(self, *args, **kwargs):
        """ Convenience method for :py:meth:`get_music_library_information`
        with `search_type='genres'`. For details on remaining arguments refer
        to the docstring for that method.

        """
        args = tuple(['genres'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    def get_composers(self, *args, **kwargs):
        """ Convenience method for :py:meth:`get_music_library_information`
        with `search_type='composers'`. For details on remaining arguments
        refer to the docstring for that method.

        """
        args = tuple(['composers'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    def get_tracks(self, *args, **kwargs):
        """ Convenience method for :py:meth:`get_music_library_information`
        with `search_type='tracks'`. For details on remaining arguments refer
        to the docstring for that method.

        """
        args = tuple(['tracks'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    def get_playlists(self, *args, **kwargs):
        """ Convenience method for :py:meth:`get_music_library_information`
        with `search_type='playlists'`. For details on remaining arguments
        refer to the docstring for that method.

        NOTE: The playlists that are referred to here are the playlist (files)
        imported from the music library, they are not the Sonos playlists.

        """
        args = tuple(['playlists'] + list(args))
        return self.get_music_library_information(*args, **kwargs)

    # pylint: disable=too-many-locals, too-many-arguments, too-many-branches
    def get_music_library_information(self, search_type, start=0,
                                      max_items=100, full_album_art_uri=False,
                                      search_term=None, subcategories=None,
                                      complete_result=False):
        """ Retrieve music information objects from the music library

        This method is the main method to get music information items, like
        e.g. tracks, albums etc., from the music library with. It can be used
        in a few different ways:

        The **search_term** argument performs a fuzzy search on that string in
        the results, so e.g calling::

          get_music_library_items('artist', search_term='Metallica')

        will perform a fuzzy search for the term 'Metallica' among all the
        artists.

        Using the **subcategories** argument, will jump directly into that
        subcategory of the search and return results from there. So. e.g
        knowing that among the artist is one called 'Metallica', calling::

          get_music_library_items('artist', subcategories=['Metallica'])

        will jump directly into the 'Metallica' sub category and return the
        albums associated with Metallica and::

          get_music_library_items('artist', subcategories=['Metallica',
                                                           'Black'])

        will return the tracks of the album 'Black' by the artist 'Metallica'.
        The order of sub category types is: Genres->Artists->Albums->Tracks.
        It is also possible to combine the two, to perform a fuzzy search in a
        sub category.

        The **start**, **max_items** and **complete_result** arguments all
        has to do with paging of the results. Per default, the searches are
        always paged, because there is a limit to how many items we can get at
        a time. This paging is exposed to the user with the start and max_items
        arguments. So calling::

          get_music_library_items('artists', start=0, max_items=100)
          get_music_library_items('artists', start=100, max_items=100)

        will get the first and next 100 items, respectively. It is also
        possible to ask for all the elements at once::

          get_music_library_items('artists', complete_result=True)

        This will perform the paging internally and simply return all the
        items.

        :param search_type: The kind of information to retrieve. Can be one of:
            'artists', 'album_artists', 'albums', 'genres', 'composers',
            'tracks', 'share', 'sonos_playlists', and 'playlists', where
            playlists are the imported file based playlists from the
            music library
        :param start: Starting number of returned matches (zero based).
        :param max_items: Maximum number of returned matches. NOTE: The maximum
            may be restricted by the unit, presumably due to transfer
            size consideration, so check the returned number against the
            requested.
        :param full_album_art_uri: If the album art URI should include the
            IP address
        :param search_term: A string that will be used to perform a fuzzy
            search among the search results. If used in combination with
            subcategories, the fuzzy search will be performed in the
            subcategory
        :param subcategories: A list of strings that indicate one or more
            subcategories to dive into
        :param complete_result: Will disable paging (ignore start and
            max_items) and return all results for the search. WARNING! Getting
            e.g. all the tracks in a large collection might take some time.
        :returns: A :py:class:`~.soco.data_structures.SearchResult` object
        :raises: :py:class:`SoCoException` upon errors

        NOTE: The playlists that are returned with the 'playlists' search, are
        the playlists imported from (files in) the music library, they are not
        the Sonos playlists.

        The information about the which searches can be performed and the form
        of the query has been gathered from the Janos project:
        http://sourceforge.net/projects/janos/ Props to the authors of that
        project.

        """
        search = self.SEARCH_TRANSLATION[search_type]

        # Add sub categories
        if subcategories is not None:
            for category in subcategories:
                search += '/' + url_escape_path(really_unicode(category))
        # Add fuzzy search
        if search_term is not None:
            search += ':' + url_escape_path(really_unicode(search_term))

        item_list = []
        metadata = {'total_matches': 100000}
        while len(item_list) < metadata['total_matches']:
            # Change start and max for complete searches
            if complete_result:
                start, max_items = len(item_list), 100000

            # Try and get this batch of results
            try:
                response, metadata =\
                    self._music_lib_search(search, start, max_items)
            except SoCoUPnPException as exception:
                # 'No such object' UPnP errors
                if exception.error_code == '701':
                    return SearchResult([], search_type, 0, 0, None)
                else:
                    raise exception

            # Parse the results
            items = from_didl_string(response['Result'])
            for item in items:
                # Check if the album art URI should be fully qualified
                if full_album_art_uri:
                    self._update_album_art_to_full_uri(item)
                # Append the item to the list
                item_list.append(item)

            # If we are not after the complete results, the stop after 1
            # iteration
            if not complete_result:
                break

        metadata['search_type'] = search_type
        if complete_result:
            metadata['number_returned'] = len(item_list)

        # pylint: disable=star-args
        return SearchResult(item_list, **metadata)

    def browse(self, ml_item=None, start=0, max_items=100,
               full_album_art_uri=False, search_term=None, subcategories=None):
        """Browse (get sub-elements) a music library item

        :param ml_item: The MusicLibraryItem to browse, if left out or passed
            None, the items at the base level will be returned
        :type ml_item: MusicLibraryItem
        :param start: The starting index of the results
        :type start: int
        :param max_items: The maximum number of items to return
        :type max_items: int
        :param full_album_art_uri: If the album art URI should include the IP
            address
        :type full_album_art_uri: bool
        :param search_term: A string that will be used to perform a fuzzy
            search among the search results. If used in combination with
            subcategories, the fuzzy search will be performed on the
            subcategory. NOTE: Searching will not work if ml_item is None.
        :type search_term: str
        :param subcategories: A list of strings that indicate one or more
            subcategories to dive into. NOTE: Providing sub categories will
            not work if ml_item is None.
        :type subcategories: list
        :returns: A :py:class:`~.soco.data_structures.SearchResult` object
        :rtype: :py:class:`~.soco.data_structures.SearchResult`
        :raises: AttributeError: If ``ml_item`` has no ``item_id`` attribute
            SoCoUPnPException: With ``error_code='701'`` if the item cannot be
            browsed
        """
        if ml_item is None:
            search = 'A:'
        else:
            search = ml_item.item_id

        # Add sub categories
        if subcategories is not None:
            for category in subcategories:
                search += '/' + url_escape_path(really_unicode(category))
        # Add fuzzy search
        if search_term is not None:
            search += ':' + url_escape_path(really_unicode(search_term))

        try:
            response, metadata =\
                self._music_lib_search(search, start, max_items)
        except SoCoUPnPException as exception:
            # 'No such object' UPnP errors
            if exception.error_code == '701':
                return SearchResult([], 'browse', 0, 0, None)
            else:
                raise exception
        metadata['search_type'] = 'browse'

        # Parse the results
        containers = from_didl_string(response['Result'])
        item_list = []
        for container in containers:
            # Check if the album art URI should be fully qualified
            if full_album_art_uri:
                self._update_album_art_to_full_uri(container)
            item_list.append(container)

        # pylint: disable=star-args
        return SearchResult(item_list, **metadata)

    # pylint: disable=too-many-arguments
    def browse_by_idstring(self, search_type, idstring, start=0,
                           max_items=100, full_album_art_uri=False):
        """Browse (get sub-elements) a given type

        :param search_type: The kind of information to retrieve. Can be one of:
            'artists', 'album_artists', 'albums', 'genres', 'composers',
            'tracks', 'share', 'sonos_playlists', and 'playlists', where
            playlists are the imported file based playlists from the
            music library
        :param idstring: String ID to search for
        :param start: Starting number of returned matches
        :param max_items: Maximum number of returned matches. NOTE: The maximum
            may be restricted by the unit, presumably due to transfer
            size consideration, so check the returned number against the
            requested.
        :param full_album_art_uri: If the album art URI should include the
                IP address
        :returns: A dictionary with metadata for the search, with the
            keys 'number_returned', 'update_id', 'total_matches' and an
            'item_list' list with the search results.
        """
        search = self.SEARCH_TRANSLATION[search_type]

        # Check if the string ID already has the type, if so we do not want to
        # add one also Imported playlist have a full path to them, so they do
        # not require the A:PLAYLISTS part first
        if idstring.startswith(search) or (search_type == 'playlists'):
            search = ""

        search_item_id = search + idstring
        search_uri = "#" + search_item_id
        # Not sure about the res protocol. But this seems to work
        res = [DidlResource(
            uri=search_uri, protocol_info="x-rincon-playlist:*:*:*")]
        search_item = DidlObject(
            resources=res, title='', parent_id='',
            item_id=search_item_id)

        # Call the base version
        return self.browse(search_item, start, max_items, full_album_art_uri)

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

    @only_on_master
    def add_uri_to_queue(self, uri):
        """Adds the URI to the queue

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
        """ Adds a queueable item to the queue """
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

    def _update_album_art_to_full_uri(self, item):
        """Update an item's Album Art URI to be an absolute URI

        :param item: The item to update the URI for
        """
        if getattr(item, 'album_art_uri', False):
            item.album_art_uri = self._build_album_art_full_uri(
                item.album_art_uri)

    def create_sonos_playlist(self, title):
        """ Create a new empty Sonos playlist.

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
        """ Create a new Sonos playlist from the current queue.

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

    def add_item_to_sonos_playlist(self, queueable_item, sonos_playlist):
        """ Adds a queueable item to a Sonos' playlist

            :param queueable_item: the item to add to the Sonos' playlist
            :param sonos_playlist: the Sonos' playlist to which the item should
                be added

        """
        # Get the update_id for the playlist
        response, _ = self._music_lib_search(sonos_playlist.item_id, 0, 1)
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
        """ Get an item's Album Art absolute URI. """

        if getattr(item, 'album_art_uri', False):
            return self._build_album_art_full_uri(item.album_art_uri)
        else:
            return None

    # pylint: disable=too-many-locals
    def search_track(self, artist, album=None, track=None,
                     full_album_art_uri=False):
        """Search for an artist, artist's albums, or specific track.

        :param artist: Artist name
        :type artist: str
        :param album: Album name
        :type album: str
        :param track: Track name
        :type track: str
        :param full_album_art_uri: If the album art URI should include the
            IP address
        :type full_album_art_uri: bool
        :returns: A :py:class:`~.soco.data_structures.SearchResult` object.
        :rtype: :py:class:`~.soco.data_structures.SearchResult`

        """
        subcategories = [artist]
        subcategories.append(album or '')

        # Perform the search
        result = self.get_album_artists(
            full_album_art_uri=full_album_art_uri,
            subcategories=subcategories, search_term=track,
            complete_result=True)
        result._metadata['search_type'] = 'search_track'
        return result

    def get_albums_for_artist(self, artist, full_album_art_uri=False):
        """Get albums for an artist.

        :param artist: Artist name
        :type artist: str
        :param full_album_art_uri: If the album art URI should include the
            IP address
        :type full_album_art_uri: bool
        :returns: A :py:class:`~.soco.data_structures.SearchResult` object.
        :rtype: :py:class:`~.soco.data_structures.SearchResult`

        """
        subcategories = [artist]
        result = self.get_album_artists(
            full_album_art_uri=full_album_art_uri,
            subcategories=subcategories,
            complete_result=True)

        reduced = [item for item in result if item.__class__ == DidlMusicAlbum]
        # It is necessary to update the list of items in two places, due to
        # a bug in SearchResult
        result[:] = reduced
        result._metadata.update({
            'item_list': reduced,
            'search_type': 'albums_for_artist',
            'number_returned': len(reduced),
            'total_matches': len(reduced)
        })
        return result

    def get_tracks_for_album(self, artist, album, full_album_art_uri=False):
        """Get tracks for an artist's album.

        :param artist: Artist name
        :type artist: str
        :param album: Album name
        :type album: str
        :param full_album_art_uri: If the album art URI should include the
            IP address
        :type full_album_art_uri: bool
        :returns: A :py:class:`~.soco.data_structures.SearchResult` object.
        :rtype: :py:class:`~.soco.data_structures.SearchResult`

        """
        subcategories = [artist, album]
        result = self.get_album_artists(
            full_album_art_uri=full_album_art_uri,
            subcategories=subcategories,
            complete_result=True)
        result._metadata['search_type'] = 'tracks_for_album'
        return result

    @property
    def library_updating(self):
        """True if the music library is in the process of being updated

        :returns: True if the music library is in the process of being updated
        :rtype: bool
        """
        result = self.contentDirectory.GetShareIndexInProgress()
        return result['IsIndexing'] != '0'

    def start_library_update(self, album_artist_display_option=''):
        """Start an update of the music library.

        If specified, album_artist_display_option changes the album
        artist compilation setting (see also album_artist_display_option).
        """
        return self.contentDirectory.RefreshShareIndex([
            ('AlbumArtistDisplayOption', album_artist_display_option),
        ])

    @property
    def album_artist_display_option(self):
        """Return the current value of the album artist compilation
        setting (see
        http://www.sonos.com/support/help/3.4/en/sonos_user_guide/
        Chap07_new/Compilation_albums.htm)

        This is a string. Possible values:

        * "WMP" - Use Album Artists
        * "ITUNES" - Use iTunes® Compilations
        * "NONE" - Do not group compilations

        To change the current setting, call `start_library_update` and
        pass the new setting.
        """
        result = self.contentDirectory.GetAlbumArtistDisplayOption()
        return result['AlbumArtistDisplayOption']


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
