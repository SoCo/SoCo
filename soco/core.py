# -*- coding: utf-8 -*-
# pylint: disable=C0302
""" The core module contains SonosDiscovery and SoCo classes that implement
the main entry to the SoCo functionality
"""

from __future__ import unicode_literals

try:
    import xml.etree.cElementTree as XML
except ImportError:
    import xml.etree.ElementTree as XML

import select
import socket
import logging
import traceback
from textwrap import dedent
import re
import requests

from .services import DeviceProperties, ContentDirectory
from .services import RenderingControl, AVTransport, ZoneGroupTopology
from .exceptions import CannotCreateDIDLMetadata
from .data_structures import get_ml_item, QueueItem
from .utils import really_unicode, really_utf8, camel_to_underscore

LOGGER = logging.getLogger(__name__)


def discover():
    """ Discover Sonos zones on the local network.

    Return an iterator providing SoCo instances for each zone found.

    """
    PLAYER_SEARCH = dedent("""\
        M-SEARCH * HTTP/1.1
        HOST: 239.255.255.250:reservedSSDPport
        MAN: ssdp:discover
        MX: 1
        ST: urn:schemas-upnp-org:device:ZonePlayer:1
        """)
    MCAST_GRP = "239.255.255.250"
    MCAST_PORT = 1900

    _sock = socket.socket(
        socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    _sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    _sock.sendto(really_utf8(PLAYER_SEARCH), (MCAST_GRP, MCAST_PORT))

    while True:
        response, _, _ = select.select([_sock], [], [], 1)
        if response:
            data, addr = _sock.recvfrom(2048)
            # Look for the model in parentheses in a line like this
            # SERVER: Linux UPnP/1.0 Sonos/22.0-65180 (ZPS5)
            search = re.search(br'SERVER.*\((.*)\)', data)
            try:
                model = really_unicode(search.group(1))
            except AttributeError:
                model = None

            # BR100 = Sonos Bridge,        ZPS3 = Zone Player 3
            # ZP120 = Zone Player Amp 120, ZPS5 = Zone Player 5
            # ZP90  = Sonos Connect,       ZPS1 = Zone Player 1
            # If it's the bridge, then it's not a speaker and shouldn't
            # be returned
            if (model and model != "BR100"):
                soco = SoCo(addr[0])
                yield soco
        else:
            break


class SonosDiscovery(object):  # pylint: disable=R0903
    """Retained for backward compatibility only. Will be removed in future
    releases

    .. deprecated:: 0.7
       Use :func:`discover` instead.

    """

    def __init__(self):
        import warnings
        warnings.warn("SonosDiscovery is deprecated. Use discover instead.")

    def get_speaker_ips(self):
        import warnings
        warnings.warn("get_speaker_ips is deprecated. Use discover instead.")
        return [i.ip_address for i in discover()]


class _ArgsSingleton(type):
    """ A metaclass which permits only a single instance of each derived class
    to exist for any given set of positional arguments.

    Attempts to instantiate a second instance of a derived class will return
    the existing instance.

    For example:

    >>> class ArgsSingletonBase(object):
    ...     __metaclass__ = _ArgsSingleton
    ...
    >>> class First(ArgsSingletonBase):
    ...     def __init__(self, param):
    ...         pass
    ...
    >>> assert First('hi') is First('hi')
    >>> assert First('hi') is First('bye')
    AssertionError

     """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = {}
        if args not in cls._instances[cls]:
            cls._instances[cls][args] = super(_ArgsSingleton, cls).__call__(
                *args, **kwargs)
        return cls._instances[cls][args]


class _SocoSingletonBase(
        _ArgsSingleton(str('ArgsSingletonMeta'), (object,), {})):
    """ The base class for the SoCo class.

    Uses a Python 2 and 3 compatible method of declaring a metaclass. See, eg,
    here: http://www.artima.com/weblogs/viewpost.jsp?thread=236234 and
    here: http://mikewatkins.ca/2008/11/29/python-2-and-3-metaclasses/

    """
    pass


class SoCo(_SocoSingletonBase):  # pylint: disable=R0904
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
        add_to_queue -- Add a track to the end of the queue
        remove_from_queue -- Remove a track from the queue
        clear_queue -- Remove all tracks from queue
        get_favorite_radio_shows -- Get favorite radio shows from Sonos'
                                    Radio app.
        get_favorite_radio_stations -- Get favorite radio stations.
        get_group_coordinator -- Get the coordinator for a grouped
                                 collection of Sonos units.
        get_speakers_ip -- Get the IP addresses of all the Sonos
                           speakers in the network.

    Properties::

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
    # Stores the IP addresses of all the speakers in a network
    speakers_ip = []
    # Stores the topology of all Zones in the network
    topology = {}

    def __init__(self, ip_address):
        # Check if ip_address is a valid IPv4 representation.
        # Sonos does not (yet) support IPv6
        try:
            socket.inet_aton(ip_address)
        except socket.error:
            raise ValueError("Not a valid IP address string")
        #: The speaker's ip address
        self.ip_address = ip_address
        self.speaker_info = {}  # Stores information about the current speaker
        self.deviceProperties = DeviceProperties(self)
        self.contentDirectory = ContentDirectory(self)
        self.renderingControl = RenderingControl(self)
        self.avTransport = AVTransport(self)
        self.zoneGroupTopology = ZoneGroupTopology(self)

    def __str__(self):
        return "<SoCo object at ip {}>".format(self.ip_address)

    def __repr__(self):
        return '{}("{}")'.format(self.__class__.__name__, self.ip_address)

    @property
    def player_name(self):
        """  The speaker's name. A string. """
        result = self.deviceProperties.GetZoneAttributes()
        return result["CurrentZoneName"]

    @player_name.setter
    def player_name(self, playername):
        self.deviceProperties.SetZoneAtrributes([
            ('DesiredZoneName', playername),
            ('DesiredIcon', ''),
            ('DesiredConfiguration', '')
            ])

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
        modes = ('NORMAL', 'SHUFFLE_NOREPEAT', 'SHUFFLE', 'REPEAT_ALL')
        playmode = playmode.upper()
        if playmode not in modes:
            raise KeyError('invalid play mode')

        self.avTransport.SetPlayMode([
            ('InstanceID', 0),
            ('NewPlayMode', playmode)
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

    def play_from_queue(self, queue_index):
        """ Play an item from the queue. The track number is required as an
        argument, where the first track is 0.

        Returns:
        True if the Sonos speaker successfully started playing the track.

        Raises SoCoException (or a subclass) upon errors.

        """
        # Grab the speaker's information if we haven't already since we'll need
        # it in the next step.
        if not self.speaker_info:
            self.get_speaker_info()

        # first, set the queue itself as the source URI
        uri = 'x-rincon-queue:{0}#0'.format(self.speaker_info['uid'])
        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', uri),
            ('CurrentURIMetaData', '')
            ])

        # second, set the track number with a seek command
        self.avTransport.Seek([
            ('InstanceID', 0),
            ('Unit', 'TRACK_NR'),
            ('Target', queue_index + 1)
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
        loudness_value = '1' if loudness else '0'
        self.renderingControl.SetLoudness([
            ('InstanceID', 0),
            ('Channel', 'Master'),
            ('DesiredLoudness', loudness_value)
            ])

    def partymode(self):
        """ Put all the speakers in the network in the same group, a.k.a Party
        Mode.

        This blog shows the initial research responsible for this:
        http://blog.travelmarx.com/2010/06/exploring-sonos-via-upnp.html

        The trick seems to be (only tested on a two-speaker setup) to tell each
        speaker which to join. There's probably a bit more to it if multiple
        groups have been defined.

        Code contributed by Thomas Bartvig (thomas.bartvig@gmail.com)

        Returns:
        True if partymode is set

        Raises SoCoException (or a subclass) upon errors.

        """
        master_speaker_info = self.get_speaker_info()
        ips = self.get_speakers_ip()

        return_status = True
        # loop through all IP's in topology and make them join this master
        for ip in ips:  # pylint: disable=C0103
            if not (ip == self.ip_address):
                slave = SoCo(ip)
                ret = slave.join(master_speaker_info["uid"])
                if ret is False:
                    return_status = False

        return return_status

    def join(self, master_uid):
        """ Join this speaker to another "master" speaker.

        Code contributed by Thomas Bartvig (thomas.bartvig@gmail.com)

        Returns:
        True if this speaker has joined the master speaker

        Raises SoCoException (or a subclass) upon errors.

        """
        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', 'x-rincon:{}'.format(master_uid)),
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
        speaker_info = self.get_speaker_info()
        speaker_uid = speaker_info['uid']
        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', 'x-rincon-stream:{}'.format(speaker_uid)),
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
        speaker_info = self.get_speaker_info()
        speaker_uid = speaker_info['uid']
        self.avTransport.SetAVTransportURI([
            ('InstanceID', 0),
            ('CurrentURI', 'x-sonos-htastream:{}:spdif'.format(speaker_uid)),
            ('CurrentURIMetaData', '')
            ])

    @property
    def status_light(self):
        """ The white Sonos status light between the mute button and the volume
        up button on the speaker. True if on, otherwise False.

        """
        result = self.deviceProperties.GetLEDState()
        LEDState = result["CurrentLEDState"]
        return True if LEDState == "On" else False

    @status_light.setter
    def status_light(self, led_on):
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
                LOGGER.warning(traceback.format_exc())
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
            if (md_title):
                track['title'] = md_title
            track['artist'] = ""
            if (md_artist):
                track['artist'] = md_artist
            track['album'] = ""
            if (md_album):
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
            self.speaker_info['uid'] = dom.findtext('.//LocalUID')
            self.speaker_info['serial_number'] = \
                dom.findtext('.//SerialNumber')
            self.speaker_info['software_version'] = \
                dom.findtext('.//SoftwareVersion')
            self.speaker_info['hardware_version'] = \
                dom.findtext('.//HardwareVersion')
            self.speaker_info['mac_address'] = dom.findtext('.//MACAddress')

            return self.speaker_info

    def get_group_coordinator(self, zone_name):
        """ Get the IP address of the Sonos system that is coordinator for
        the group containing zone_name

        Code contributed by Aaron Daubman (daubman@gmail.com)
                            Murali Allada (amuralis@hotmail.com)

        Arguments:
        zone_name -- Name of the Zone, for which you need a coordinator

        Returns:
        The IP address of the coordinator or None if one cannot be determined

        """
        coord_ip = None
        coord_uuid = None
        zgroups = self.zoneGroupTopology.GetZoneGroupState()['ZoneGroupState']
        XMLtree = XML.fromstring(really_utf8(zgroups))

        for grp in XMLtree:
            for zone in grp:
                if zone_name == zone.attrib['ZoneName']:
                    # find UUID of coordinator
                    coord_uuid = grp.attrib['Coordinator']

        for grp in XMLtree:
            for zone in grp:
                if coord_uuid == zone.attrib['UUID']:
                    # find IP of coordinator UUID for this group
                    coord_ip = zone.attrib['Location'].\
                        split('//')[1].split(':')[0]

        return coord_ip

    def __get_topology(self, refresh=False):
        """ Gets the topology if it is not already available or if refresh=True

        Code contributed by Aaron Daubman (daubman@gmail.com)

        Arguments:
        refresh -- Refresh the topology cache

        """
        if not self.topology or refresh:
            self.topology = {}
            response = requests.get('http://' + self.ip_address +
                                    ':1400/status/topology')
            dom = XML.fromstring(really_utf8(response.content))
            for player in dom.find('ZonePlayers'):
                if player.text not in self.topology:
                    self.topology[player.text] = {}
                self.topology[player.text]['group'] = \
                    player.attrib.get('group')
                self.topology[player.text]['uuid'] = player.attrib.get('uuid')
                self.topology[player.text]['coordinator'] = \
                    (player.attrib.get('coordinator') == 'true')
                # Split the IP out of the URL returned in location
                # e.g. return '10.1.1.1' from 'http://10.1.1.1:1400/...'
                self.topology[player.text]['ip'] = \
                    player.attrib.get('location').split('//')[1].split(':')[0]

    def get_speakers_ip(self, refresh=False):
        """ Get the IP addresses of all the Sonos speakers in the network.

        Code contributed by Thomas Bartvig (thomas.bartvig@gmail.com)

        Arguments:
        refresh -- Refresh the speakers IP cache.

        Returns:
        IP addresses of the Sonos speakers.

        """
        if self.speakers_ip and not refresh:
            return self.speakers_ip
        else:
            response = requests.get('http://' + self.ip_address +
                                    ':1400/status/topology')
            text = response.text
            grp = re.findall(r'(\d+\.\d+\.\d+\.\d+):1400', text)

            for i in grp:
                response = requests.get('http://' + i + ':1400/status')
                if response.status_code == 200:
                    self.speakers_ip.append(i)

            return self.speakers_ip

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
                './/{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item'):
            item = QueueItem.from_xml(element)
            queue.append(item)

        return queue

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
            'tracks', 'share' and 'playlists', where playlists are the imported
            file based playlists from the music library
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
            :py:class:`~.soco.data_structures.MLShare` and
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
                              'albums': 'A:ALBUM', 'genres': 'A:GENRE',
                              'composers': 'A:COMPOSER', 'tracks': 'A:TRACKS',
                              'playlists': 'A:PLAYLISTS', 'share': 'S:'}
        search = search_translation[search_type]
        response = self.contentDirectory.Browse([
            ('ObjectID', search),
            ('BrowseFlag', 'BrowseDirectChildren'),
            ('Filter', '*'),
            ('StartingIndex', start),
            ('RequestedCount', max_items),
            ('SortCriteria', '')
            ])

        dom = XML.fromstring(really_utf8(response['Result']))

        # Get result information
        out = {'item_list': [], 'search_type': search_type}
        for tag in ['NumberReturned', 'TotalMatches', 'UpdateID']:
            out[camel_to_underscore(tag)] = int(response[tag])

        # Parse the results
        for container in dom:
            item = get_ml_item(container)
            # Append the item to the list
            out['item_list'].append(item)

        return out

    def add_to_queue(self, queueable_item):
        """ Adds a queueable item to the queue """
        # Check if teh required attributes are there
        for attribute in ['didl_metadata', 'uri']:
            if not hasattr(queueable_item, attribute):
                message = 'queueable_item has no attribute {}'.\
                    format(attribute)
                raise AttributeError(message)
        # Get the metadata
        try:
            metadata = XML.tostring(queueable_item.didl_metadata)
        except CannotCreateDIDLMetadata as exception:
            message = ('The queueable item could not be enqueued, because it '
                       'raised a CannotCreateDIDLMetadata exception with the '
                       'following message:\n{0}').format(exception.message)
            raise ValueError(message)
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
        """ Removes a track from the queue.

        index: the index of the track to remove; first item in the queue is 1

        Returns:
        True if the Sonos speaker successfully removed the track

        Raises SoCoException (or a subclass) upon errors.

        """
        # TODO: what do these parameters actually do?
        updid = '0'
        objid = 'Q:0/' + str(index)
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
            ('ObjectID', 'R:0/{}'.format(favorite_type)),
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
                    './/{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item'):
                favorite = {}
                favorite['title'] = item.findtext(
                    './/{http://purl.org/dc/elements/1.1/}title')
                favorite['uri'] = item.findtext(
                    './/{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res')
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
