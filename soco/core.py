# -*- coding: utf-8 -*-
# pylint: disable=fixme, protected-access
"""The core module contains the SoCo class that implements
the main entry to the SoCo functionality
"""

from __future__ import absolute_import, unicode_literals

import datetime
import logging
import re
import socket
from functools import wraps
from xml.sax.saxutils import escape
import warnings

import requests

from . import config
from .compat import UnicodeType
from .data_structures import (
    DidlObject, DidlPlaylistContainer, DidlResource,
    Queue, to_didl_string
)
from .data_structures_entry import from_didl_string
from .exceptions import (
    SoCoSlaveException, SoCoUPnPException, NotSupportedException,
)
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

    ..  rubric:: Basic Methods
    ..  autosummary::

        play_from_queue
        play
        play_uri
        pause
        stop
        seek
        next
        previous
        mute
        volume
        play_mode
        cross_fade
        ramp_to_volume
        get_current_track_info
        get_speaker_info
        get_current_transport_info

    ..  rubric:: Queue Management
    ..  autosummary::

        get_queue
        queue_size
        add_to_queue
        add_uri_to_queue
        add_multiple_to_queue
        remove_from_queue
        clear_queue

    ..  rubric:: Group Management
    ..  autosummary::

        group
        partymode
        join
        unjoin
        all_groups
        all_zones
        visible_zones

    ..  rubric:: Player Identity and Settings
    ..  autosummary::

        player_name
        uid
        household_id
        is_visible
        is_bridge
        is_coordinator
        bass
        treble
        loudness
        night_mode
        dialog_mode
        status_light

    ..  rubric:: Playlists and Favorites
    ..  autosummary::

        get_sonos_playlists
        create_sonos_playlist
        create_sonos_playlist_from_queue
        remove_sonos_playlist
        add_item_to_sonos_playlist
        reorder_sonos_playlist
        clear_sonos_playlist
        move_in_sonos_playlist
        remove_from_sonos_playlist
        get_sonos_playlist_by_attr
        get_favorite_radio_shows
        get_favorite_radio_stations
        get_sonos_favorites

    ..  rubric:: Miscellaneous
    ..  autosummary::

        switch_to_line_in
        is_playing_radio
        is_playing_line_in
        is_playing_tv
        switch_to_tv
        set_sleep_timer
        get_sleep_timer

    .. warning::

        Properties on this object are not generally cached and may obtain
        information over the network, so may take longer than expected to set
        or return a value. It may be a good idea for you to cache the value in
        your own code.

    .. note::

        Since all methods/properties on this object will result in an UPnP
        request, they might result in an exception without it being mentioned
        in the Raises section.

        In most cases, the exception will be a
        :class:`soco.exceptions.SoCoUPnPException`
        (if the player returns an UPnP error code), but in special cases
        it might also be another :class:`soco.exceptions.SoCoException`
        or even a `requests` exception.

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
        """str: The speaker's name."""
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
        """str: A unique identifier.

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
        """str: A unique identifier for all players in a household.

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
        """bool: Is this zone visible?

        A zone might be invisible if, for example, it is a bridge, or the slave
        part of stereo pair.
        """
        # We could do this:
        # invisible = self.deviceProperties.GetInvisible()['CurrentInvisible']
        # but it is better to do it in the following way, which uses the
        # zone group topology, to capitalise on any caching.
        return self in self.visible_zones

    @property
    def is_bridge(self):
        """bool: Is this zone a bridge?"""
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
        """bool: Is this zone a group coordinator?"""
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
        """bool: The speaker's cross fade state.

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

    def ramp_to_volume(self, volume, ramp_type='SLEEP_TIMER_RAMP_TYPE'):
        """Smoothly change the volume.

        There are three ramp types available:

            * ``'SLEEP_TIMER_RAMP_TYPE'`` (default): Linear ramp from the
              current volume up or down to the new volume. The ramp rate is
              1.25 steps per second. For example: To change from volume 50 to
              volume 30 would take 16 seconds.
            * ``'ALARM_RAMP_TYPE'``: Resets the volume to zero, waits for about
              30 seconds, and then ramps the volume up to the desired value at
              a rate of 2.5 steps per second. For example: Volume 30 would take
              12 seconds for the ramp up (not considering the wait time).
            * ``'AUTOPLAY_RAMP_TYPE'``: Resets the volume to zero and then
              quickly ramps up at a rate of 50 steps per second. For example:
              Volume 30 will take only 0.6 seconds.

        The ramp rate is selected by Sonos based on the chosen ramp type and
        the resulting transition time returned.
        This method is non blocking and has no network overhead once sent.

        Args:
            volume (int): The new volume.
            ramp_type (str, optional): The desired ramp type, as described
                above.

        Returns:
            int: The ramp time in seconds, rounded down. Note that this does
            not include the wait time.
        """
        response = self.renderingControl.RampToVolume([
            ('InstanceID', 0),
            ('Channel', 'Master'),
            ('RampType', ramp_type),
            ('DesiredVolume', volume),
            ('ResetVolumeAfter', False),
            ('ProgramURI', '')
        ])
        return int(response['RampTime'])

    @only_on_master
    def play_from_queue(self, index, start=True):
        """Play a track from the queue by index.

        The index number is required as an argument, where the first index
        is 0.

        Args:
            index (int): 0-based index of the track to play
            start (bool): If the item that has been set should start playing
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
            self.play()

    @only_on_master
    def play(self):
        """Play the currently selected track."""
        self.avTransport.Play([
            ('InstanceID', 0),
            ('Speed', 1)
        ])

    @only_on_master
    # pylint: disable=too-many-arguments
    def play_uri(self, uri='', meta='', title='', start=True,
                 force_radio=False):
        """Play a URI.

        Playing a URI will replace what was playing with the stream given by
        the URI. For some streams at least a title is required as metadata.
        This can be provided using the `meta` argument or the `title` argument.
        If the `title` argument is provided minimal metadata will be generated.
        If `meta` argument is provided the `title` argument is ignored.

        Args:
            uri (str): URI of the stream to be played.
            meta (str): The metadata to show in the player, DIDL format.
            title (str): The title to show in the player (if no meta).
            start (bool): If the URI that has been set should start playing.
            force_radio (bool): forces a uri to play as a radio stream.

        On a Sonos controller music is shown with one of the following display
        formats and controls:

        * Radio format: Shows the name of the radio station and other available
          data. No seek, next, previous, or voting capability.
          Examples: TuneIn, radioPup
        * Smart Radio:  Shows track name, artist, and album. Limited seek, next
          and sometimes voting capability depending on the Music Service.
          Examples: Amazon Prime Stations, Pandora Radio Stations.
        * Track format: Shows track name, artist, and album the same as when
          playing from a queue. Full seek, next and previous capabilities.
          Examples: Spotify, Napster, Rhapsody.

        How it is displayed is determined by the URI prefix:
        `x-sonosapi-stream:`, `x-sonosapi-radio:`, `x-rincon-mp3radio:`,
        `hls-radio:` default to radio or smart radio format depending on the
        stream. Others default to track format: `x-file-cifs:`, `aac:`,
        `http:`, `https:`, `x-sonos-spotify:` (used by Spotify),
        `x-sonosapi-hls-static:` (Amazon Prime),
        `x-sonos-http:` (Google Play & Napster).

        Some URIs that default to track format could be radio streams,
        typically `http:`, `https:` or `aac:`.
        To force display and controls to Radio format set `force_radio=True`

        .. note:: Other URI prefixes exist but are less common.
           If you have information on these please add to this doc string.

        .. note:: A change in Sonos® (as of at least version 6.4.2) means that
           the devices no longer accepts ordinary `http:` and `https:` URIs for
           radio stations. This method has the option to replaces these
           prefixes with the one that Sonos® expects: `x-rincon-mp3radio:` by
           using the "force_radio=True" parameter.
           A few streams may fail if not forced to to Radio format.
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
            meta = meta_template.format(
                title=escape(title),
                service=tunein_service)

        # change uri prefix to force radio style display and commands
        if force_radio:
            colon = uri.find(':')
            if colon > 0:
                uri = 'x-rincon-mp3radio{0}'.format(uri[colon:])

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
        """Pause the currently playing track."""
        self.avTransport.Pause([
            ('InstanceID', 0),
            ('Speed', 1)
        ])

    @only_on_master
    def stop(self):
        """Stop the currently playing track."""
        self.avTransport.Stop([
            ('InstanceID', 0),
            ('Speed', 1)
        ])

    @only_on_master
    def seek(self, timestamp):
        """Seek to a given timestamp in the current track, specified in the
        format of HH:MM:SS or H:MM:SS.

        Raises:
            ValueError: if the given timestamp is invalid.
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
        """bool: The speaker's mute state.

        True if muted, False otherwise.
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
        """int: The speaker's volume.

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
        """int: The speaker's bass EQ.

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
        """int: The speaker's treble EQ.

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
        """bool: The Sonos speaker's loudness compensation.

        True if on, False otherwise.

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

    @property
    def night_mode(self):
        """bool: The speaker's night mode.

        True if on, False if off, None if not supported.
        """
        if not self.speaker_info:
            self.get_speaker_info()
        if self.speaker_info['model_name'] not in {'Sonos Playbase', 'Sonos Playbar', 'Sonos Beam'}:
            return None

        response = self.renderingControl.GetEQ([
            ('InstanceID', 0),
            ('EQType', 'NightMode')
        ])
        return bool(int(response['CurrentValue']))

    @night_mode.setter
    def night_mode(self, night_mode):
        """Switch on/off the speaker's night mode.

        :param night_mode: Enable or disable night mode
        :type night_mode: bool
        :raises NotSupportedException: If the device does not support
        night mode.
        """
        if not self.speaker_info:
            self.get_speaker_info()
        if self.speaker_info['model_name'] not in {'Sonos Playbase', 'Sonos Playbar', 'Sonos Beam'}:
            message = 'This device does not support night mode'
            raise NotSupportedException(message)

        self.renderingControl.SetEQ([
            ('InstanceID', 0),
            ('EQType', 'NightMode'),
            ('DesiredValue', int(night_mode))
        ])

    @property
    def dialog_mode(self):
        """bool: Get the Sonos speaker's dialog mode.

        True if on, False if off, None if not supported.
        """
        if not self.speaker_info:
            self.get_speaker_info()
        if self.speaker_info['model_name'] not in {'Sonos Playbase', 'Sonos Playbar', 'Sonos Beam'}:
            return None

        response = self.renderingControl.GetEQ([
            ('InstanceID', 0),
            ('EQType', 'DialogLevel')
        ])
        return bool(int(response['CurrentValue']))

    @dialog_mode.setter
    def dialog_mode(self, dialog_mode):
        """Switch on/off the speaker's dialog mode.

        :param dialog_mode: Enable or disable dialog mode
        :type dialog_mode: bool
        :raises NotSupportedException: If the device does not support
        dialog mode.
        """
        if not self.speaker_info:
            self.get_speaker_info()
        if self.speaker_info['model_name'] not in {'Sonos Playbase', 'Sonos Playbar', 'Sonos Beam'}:
            message = 'This device does not support dialog mode'
            raise NotSupportedException(message)

        self.renderingControl.SetEQ([
            ('InstanceID', 0),
            ('EQType', 'DialogLevel'),
            ('DesiredValue', int(dialog_mode))
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
        """set of :class:`soco.groups.ZoneGroup`: All available groups."""
        self._parse_zone_group_state()
        return self._groups.copy()

    @property
    def group(self):
        """:class:`soco.groups.ZoneGroup`: The Zone Group of which this device
        is a member.

        None if this zone is a slave in a stereo pair.
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
        """set of :class:`soco.groups.ZoneGroup`: All available zones."""
        self._parse_zone_group_state()
        return self._all_zones.copy()

    @property
    def visible_zones(self):
        """set of :class:`soco.groups.ZoneGroup`: All visible zones."""
        self._parse_zone_group_state()
        return self._visible_zones.copy()

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
        """Join this speaker to another "master" speaker."""
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
        """

        self.avTransport.BecomeCoordinatorOfStandaloneGroup([
            ('InstanceID', 0)
        ])
        zone_group_state_shared_cache.clear()
        self._parse_zone_group_state()

    def switch_to_line_in(self, source=None):
        """ Switch the speaker's input to line-in.

        Args:
            source (SoCo): The speaker whose line-in should be played.
                Default is line-in from the speaker itself.
        """
        if source:
            uid = source.uid
        else:
            uid = self.uid

        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', 'x-rincon-stream:{0}'.format(uid)),
            ('CurrentURIMetaData', '')
        ])

    @property
    def is_playing_radio(self):
        """bool: Is the speaker playing radio?"""
        response = self.avTransport.GetPositionInfo([
            ('InstanceID', 0),
            ('Channel', 'Master')
        ])
        track_uri = response['TrackURI']
        return re.match(r'^x-rincon-mp3radio:', track_uri) is not None

    @property
    def is_playing_line_in(self):
        """bool: Is the speaker playing line-in?"""
        response = self.avTransport.GetPositionInfo([
            ('InstanceID', 0),
            ('Channel', 'Master')
        ])
        track_uri = response['TrackURI']
        return re.match(r'^x-rincon-stream:', track_uri) is not None

    @property
    def is_playing_tv(self):
        """bool: Is the playbar speaker input from TV?"""
        response = self.avTransport.GetPositionInfo([
            ('InstanceID', 0),
            ('Channel', 'Master')
        ])
        track_uri = response['TrackURI']
        return re.match(r'^x-sonos-htastream:', track_uri) is not None

    def switch_to_tv(self):
        """Switch the playbar speaker's input to TV."""

        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', 'x-sonos-htastream:{0}:spdif'.format(self.uid)),
            ('CurrentURIMetaData', '')
        ])

    @property
    def status_light(self):
        """bool: The white Sonos status light between the mute button and the
        volume up button on the speaker.

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
            dict: A dictionary containing information about the currently
            playing track: playlist_position, duration, title, artist, album,
            position and an album_art link.

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
                                          'metadata-1-0/}streamContent') or ''
            index = trackinfo.find(' - ')

            if index > -1:
                track['artist'] = trackinfo[:index]
                track['title'] = trackinfo[index + 3:]
            else:
                # Might find some kind of title anyway in metadata
                track['title'] = metadata.findtext('.//{http://purl.org/dc/'
                                                   'elements/1.1/}title')
                if not track['title']:
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
                track['album_art'] = \
                    self.music_library.build_album_art_full_uri(album_art_url)

        return track

    def get_speaker_info(self, refresh=False, timeout=None):
        """Get information about the Sonos speaker.

        Arguments:
            refresh(bool): Refresh the speaker info cache.
            timeout: How long to wait for the server to send
                data before giving up, as a float, or a
                `(connect timeout, read timeout)` tuple
                e.g. (3, 5). Default is no timeout.

        Returns:
            dict: Information about the Sonos speaker, such as the UID,
            MAC Address, and Zone Name.
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
        return None

    def get_current_transport_info(self):
        """Get the current playback state.

        Returns:
            dict: The following information about the
            speaker's playing state:

            *   current_transport_state (``PLAYING``, ``TRANSITIONING``,
                ``PAUSED_PLAYBACK``, ``STOPPED``)
            *   current_transport_status (OK, ?)
            *   current_speed(1, ?)

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
                self.music_library._update_album_art_to_full_uri(item)
            queue.append(item)

        # pylint: disable=star-args
        return Queue(queue, **metadata)

    @property
    def queue_size(self):
        """int: Size of the queue."""
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
        """Convenience method for
        `get_music_library_information('sonos_playlists')`.

        Refer to the docstring for that method

        """
        args = tuple(['sonos_playlists'] + list(args))
        return self.music_library.get_music_library_information(*args,
                                                                **kwargs)

    @only_on_master
    def add_uri_to_queue(self, uri, position=0, as_next=False):
        """Add the URI to the queue.

        For arguments and return value see `add_to_queue`.
        """
        # FIXME: The res.protocol_info should probably represent the mime type
        # etc of the uri. But this seems OK.
        res = [DidlResource(uri=uri, protocol_info="x-rincon-playlist:*:*:*")]
        item = DidlObject(resources=res, title='', parent_id='', item_id='')
        return self.add_to_queue(item, position, as_next)

    @only_on_master
    def add_to_queue(self, queueable_item, position=0, as_next=False):
        """Add a queueable item to the queue.

        Args:
            queueable_item (DidlObject or MusicServiceItem): The item to be
                added to the queue
            position (int): The index (1-based) at which the URI should be
                added. Default is 0 (add URI at the end of the queue).
            as_next (bool): Whether this URI should be played as the next
                track in shuffle mode. This only works if `play_mode=SHUFFLE`.

        Returns:
            int: The index of the new item in the queue.
        """
        metadata = to_didl_string(queueable_item)
        response = self.avTransport.AddURIToQueue([
            ('InstanceID', 0),
            ('EnqueuedURI', queueable_item.resources[0].uri),
            ('EnqueuedURIMetaData', metadata),
            ('DesiredFirstTrackNumberEnqueued', position),
            ('EnqueueAsNext', int(as_next))
        ])
        qnumber = response['FirstTrackNumberEnqueued']
        return int(qnumber)

    def add_multiple_to_queue(self, items, container=None):
        """Add a sequence of items to the queue.

        Args:
            items (list): A sequence of items to the be added to the queue
            container (DidlObject, optional): A container object which
                includes the items.
        """
        if container is not None:
            container_uri = container.resources[0].uri
            container_metadata = to_didl_string(container)
        else:
            container_uri = ''  # Sonos seems to accept this as well
            container_metadata = ''  # pylint: disable=redefined-variable-type

        chunk_size = 16  # With each request, we can only add 16 items
        item_list = list(items)  # List for slicing
        for index in range(0, len(item_list), chunk_size):
            chunk = item_list[index:index + chunk_size]
            uris = ' '.join([item.resources[0].uri for item in chunk])
            uri_metadata = ' '.join([to_didl_string(item) for item in chunk])
            self.avTransport.AddMultipleURIsToQueue([
                ('InstanceID', 0),
                ('UpdateID', 0),
                ('NumberOfURIs', len(chunk)),
                ('EnqueuedURIs', uris),
                ('EnqueuedURIsMetaData', uri_metadata),
                ('ContainerURI', container_uri),
                ('ContainerMetaData', container_metadata),
                ('DesiredFirstTrackNumberEnqueued', 0),
                ('EnqueueAsNext', 0)
            ])

    @only_on_master
    def remove_from_queue(self, index):
        """Remove a track from the queue by index. The index number is
        required as an argument, where the first index is 0.

        Args:
            index (int): The (0-based) index of the track to remove
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
        """Remove all tracks from the queue."""
        self.avTransport.RemoveAllTracksFromQueue([
            ('InstanceID', 0),
        ])

    @deprecated('0.13', "soco.music_library.get_favorite_radio_shows", '0.15')
    def get_favorite_radio_shows(self, start=0, max_items=100):
        """Get favorite radio shows from Sonos' Radio app.

        Returns:
            dict: A dictionary containing the total number of favorites, the
            number of favorites returned, and the actual list of favorite radio
            shows, represented as a dictionary with `title` and `uri` keys.

        Depending on what you're building, you'll want to check to see if the
        total number of favorites is greater than the amount you
        requested (`max_items`), if it is, use `start` to page through and
        get the entire list of favorites.
        """
        message = 'The output type of this method will probably change in '\
                  'the future to use SoCo data structures'
        warnings.warn(message, stacklevel=2)
        return self.__get_favorites(RADIO_SHOWS, start, max_items)

    @deprecated('0.13', "soco.music_library.get_favorite_radio_stations",
                '0.15')
    def get_favorite_radio_stations(self, start=0, max_items=100):
        """Get favorite radio stations from Sonos' Radio app.

        See :meth:`get_favorite_radio_shows` for return type and remarks.
        """
        message = 'The output type of this method will probably change in '\
                  'the future to use SoCo data structures'
        warnings.warn(message, stacklevel=2)
        return self.__get_favorites(RADIO_STATIONS, start, max_items)

    @deprecated('0.13', "soco.music_library.get_sonos_favorites", '0.15')
    def get_sonos_favorites(self, start=0, max_items=100):
        """Get Sonos favorites.

        See :meth:`get_favorite_radio_shows` for return type and remarks.
        """
        message = 'The output type of this method will probably change in '\
                  'the future to use SoCo data structures'
        warnings.warn(message, stacklevel=2)
        return self.__get_favorites(SONOS_FAVORITES, start, max_items)

    def __get_favorites(self, favorite_type, start=0, max_items=100):
        """ Helper method for `get_favorite_radio_*` methods.

        Args:
            favorite_type (str): Specify either `RADIO_STATIONS` or
                `RADIO_SHOWS`.
            start (int): Which number to start the retrieval from. Used for
                paging.
            max_items (int): The total number of results to return.

        """
        if favorite_type not in (RADIO_SHOWS, RADIO_STATIONS):
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

    def create_sonos_playlist(self, title):
        """Create a new empty Sonos playlist.

        Args:
            title: Name of the playlist

        :rtype: :py:class:`~.soco.data_structures.DidlPlaylistContainer`
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

        Args:
            title: Name of the playlist

        :rtype: :py:class:`~.soco.data_structures.DidlPlaylistContainer`
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

        Args:
            queueable_item (DidlObject): the item to add to the Sonos' playlist
            sonos_playlist (DidlPlaylistContainer): the Sonos' playlist to
                which the item should be added
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
            response, _ = self.music_library._music_lib_search(object_id, 0, 1)
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
