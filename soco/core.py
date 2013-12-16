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
import re
import cgi
import requests

from .services import DeviceProperties, ContentDirectory
from .services import RenderingControl, AVTransport
from .exceptions import CannotCreateDIDLMetadata
from .data_structures import ns_tag, get_ml_item, QueueableItem
from .utils import really_unicode, really_utf8, camel_to_underscore

LOGGER = logging.getLogger(__name__)


class SonosDiscovery(object):  # pylint: disable=R0903
    """A simple class for discovering Sonos speakers.

    Public functions:
    get_speaker_ips -- Get a list of IPs of all zoneplayers.

    """

    def __init__(self):
        self._sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    def get_speaker_ips(self):
        """ Get a list of ips for Sonos devices that can be controlled """
        speakers = []
        self._sock.sendto(really_utf8(PLAYER_SEARCH), (MCAST_GRP, MCAST_PORT))

        while True:
            response, _, _ = select.select([self._sock], [], [], 1)
            if response:
                data, addr = self._sock.recvfrom(2048)
                # Look for the model in parentheses in a line like this
                # SERVER: Linux UPnP/1.0 Sonos/22.0-65180 (ZPS5)
                search = re.search(br'SERVER.*\((.*)\)', data)
                try:
                    model = really_unicode(search.group(1))
                except AttributeError:
                    model = None

                # BR100 = Sonos Bridge,        ZPS3 = Zone Player 3
                # ZP120 = Zone Player Amp 120, ZPS5 = Zone Player 5
                # ZP90  = Sonos Connect
                # If it's the bridge, then it's not a speaker and shouldn't
                # be returned
                if (model and model != "BR100"):
                    speakers.append(addr[0])
            else:
                break
        return speakers


class SoCo(object):  # pylint: disable=R0904
    """A simple class for controlling a Sonos speaker.

    Public functions:
    play -- Plays the current item.
    play_uri -- Plays a track or a music stream by URI.
    play_from_queue -- Plays an item in the queue.
    pause -- Pause the currently playing track.
    stop -- Stop the currently playing track.
    seek -- Move the currently playing track a given elapsed time.
    next -- Go to the next track.
    previous -- Go back to the previous track.
    mute -- Get or Set Mute (or unmute) the speaker.
    volume -- Get or set the volume of the speaker.
    bass -- Get or set the speaker's bass EQ.
    set_player_name  -- set the name of the Sonos Speaker
    treble -- Set the speaker's treble EQ.
    set_play_mode -- Change repeat and shuffle settings on the queue.
    set_loudness -- Turn on (or off) the speaker's loudness compensation.
    switch_to_line_in -- Switch the speaker's input to line-in.
    status_light -- Turn on (or off) the Sonos status light.
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
    get_favorite_radio_shows -- Get favorite radio shows from Sonos' Radio app.
    get_favorite_radio_stations -- Get favorite radio stations.
    get_group_coordinator -- Get the coordinator for a grouped collection of
                             Sonos units.
    get_speakers_ip -- Get the IP addresses of all the Sonos speakers in the
                       network.

    """
    # Stores the IP addresses of all the speakers in a network
    speakers_ip = []
    # Stores the topology of all Zones in the network
    topology = {}

    def __init__(self, speaker_ip):
        self.speaker_ip = speaker_ip
        self.speaker_info = {}  # Stores information about the current speaker
        self.deviceProperties = DeviceProperties(self)
        self.contentDirectory = ContentDirectory(self)
        self.renderingControl = RenderingControl(self)
        self.avTransport = AVTransport(self)

    def set_player_name(self, playername):
        """  Sets the name of the player

        Returns:
        True if the player name was successfully set.

        Raises SoCoException (or a subclass) upon errors.

        """
        self.deviceProperties.SetZoneAtrributes([
            ('DesiredZoneName', playername),
            ('DesiredIcon', ''),
            ('DesiredConfiguration', '')
            ])

    def set_play_mode(self, playmode):
        """ Sets the play mode for the queue. Case-insensitive options are:
        NORMAL -- Turns off shuffle and repeat.
        REPEAT_ALL -- Turns on repeat and turns off shuffle.
        SHUFFLE -- Turns on shuffle *and* repeat. (It's strange, I know.)
        SHUFFLE_NOREPEAT -- Turns on shuffle and turns off repeat.

        Returns:
        True if the play mode was successfully set.

        Raises SoCoException (or a subclass) upon errors.

        """
        modes = ('NORMAL', 'SHUFFLE_NOREPEAT', 'SHUFFLE', 'REPEAT_ALL')
        playmode = playmode.upper()
        if not playmode in modes:
            raise KeyError('invalid play mode')

        self.avTransport.SetPlayMode([
            ('InstanceID', 0),
            ('NewPlayMode', playmode)
            ])

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

    def mute(self, mute=None):
        """ Mute or unmute the Sonos speaker.

        Arguments:
        mute -- True to mute. False to unmute.

        Returns:
        True if the Sonos speaker was successfully muted or unmuted.

        If the mute argument was not specified: returns the current mute status
        0 for unmuted, 1 for muted

        Raises SoCoException (or a subclass) upon errors.

        """
        if mute is None:
            response = self.renderingControl.GetMute([
                ('InstanceID', 0),
                ('Channel', 'Master')
                ])
            mute_state = response['CurrentMute']
            return int(mute_state)
        else:
            mute_value = '1' if mute else '0'
            self.renderingControl.SetMute([
                ('InstanceID', 0),
                ('Channel', 'Master'),
                ('DesiredMute', mute_value)
                ])

    def volume(self, volume=None):
        """ Get or set the Sonos speaker volume.

        Arguments:
        volume -- A value between 0 and 100.

        Returns:
        If the volume argument was specified: returns true if the Sonos speaker
        successfully set the volume.

        If the volume argument was not specified: returns the current volume of
        the Sonos speaker.

        Raises SoCoException (or a subclass) upon errors.

        """
        if volume is not None:
            volume = max(0, min(volume, 100))  # Coerce in range
            self.renderingControl.SetVolume([
                ('InstanceID', 0),
                ('Channel', 'Master'),
                ('DesiredVolume', volume)
                ])
        else:
            response = self.renderingControl.GetVolume([
                ('InstanceID', 0),
                ('Channel', 'Master'),
                ])
            volume = response['CurrentVolume']
            return int(volume)

    def bass(self, bass=None):
        """ Get or set the Sonos speaker's bass EQ.

        Arguments:
        bass -- A value between -10 and 10.

        Returns:
        If the bass argument was specified: returns true if the Sonos speaker
        successfully set the bass EQ.

        If the bass argument was not specified: returns the current base value.

        Raises SoCoException (or a subclass) upon errors.

        """
        if bass is not None:
            bass = max(-10, min(bass, 10))  # Coerce in range
            self.renderingControl.SetBass([
                ('InstanceID', 0),
                ('DesiredBass', bass)
                ])
        else:
            response = self.renderingControl.GetBass([
                ('InstanceID', 0),
                ('Channel', 'Master'),
                ])
            bass = response['CurrentBass']
            return int(bass)

    def treble(self, treble=None):
        """ Get or set the Sonos speaker's treble EQ.

        Arguments:
        treble -- A value between -10 and 10.

        Returns:
        If the treble argument was specified: returns true if the Sonos speaker
        successfully set the treble EQ.

        If the treble argument was not specified: returns the current treble
        value.

        Raises SoCoException (or a subclass) upon errors.

        """
        if treble is not None:
            treble = max(-10, min(treble, 10))  # Coerce in range
            self.renderingControl.SetTreble([
                ('InstanceID', 0),
                ('DesiredTreble', treble)
                ])
        else:
            response = self.renderingControl.GetTreble([
                ('InstanceID', 0),
                ('Channel', 'Master'),
                ])
            treble = response['CurrentTreble']
            return int(treble)

    def set_loudness(self, loudness):
        """ Set the Sonos speaker's loudness compensation.

        Loudness is a complicated topic. You can find a nice summary about this
        feature here: http://forums.sonos.com/showthread.php?p=4698#post4698

        Arguments:
        loudness -- True to turn on loudness compensation. False to disable it.

        Returns:
        True if the Sonos speaker successfully set the loundess compensation.

        Raises SoCoException (or a subclass) upon errors.

        """
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
        http://travelmarx.blogspot.dk/2010/06/exploring-sonos-via-upnp.html

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
            if not (ip == self.speaker_ip):
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
            ('InstanceID', 0),
            ('Speed', '1')
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

    def status_light(self, led_on):
        """ Turn on (or off) the white Sonos status light.

        Turns on or off the little white light on the Sonos speaker. (It's
        between the mute button and the volume up button on the speaker.)

        Arguments:
        led_on -- True to turn on the light. False to turn off the light.

        Returns:
        True if the Sonos speaker successfully turned on (or off) the light.

        Raises SoCoException (or a subclass) upon errors.

        """
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
                track['title'] = really_utf8(trackinfo)

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
                track['title'] = really_utf8(md_title)
            track['artist'] = ""
            if (md_artist):
                track['artist'] = really_utf8(md_artist)
            track['album'] = ""
            if (md_album):
                track['album'] = really_utf8(md_album)

            album_art = metadata.findtext(
                './/{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI')
            if album_art is not None:
                url = metadata.findtext(
                    './/{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI')
                if url.startswith(('http:', 'https:')):
                    track['album_art'] = url
                else:
                    track['album_art'] = 'http://' + self.speaker_ip + ':1400'\
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
            response = requests.get('http://' + self.speaker_ip +
                                    ':1400/status/zp')
            dom = XML.fromstring(response.content)

        if dom.findtext('.//ZoneName') is not None:
            self.speaker_info['zone_name'] = \
                really_utf8(dom.findtext('.//ZoneName'))
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

    def get_group_coordinator(self, zone_name, refresh=False):
        """ Get the IP address of the Sonos system that is coordinator for
            the group containing zone_name

        Code contributed by Aaron Daubman (daubman@gmail.com)

        Arguments:
        zone_name -- the name of the Zone to control for which you need the
                     coordinator

        refresh -- Refresh the topology cache prior to looking for coordinator

        Returns:
        The IP address of the coordinator or None of one can not be determined

        """
        if not self.topology or refresh:
            self.__get_topology(refresh=True)

        # The zone name must be in the topology
        if zone_name not in self.topology:
            return None

        zone_dict = self.topology[zone_name]
        zone_group = zone_dict['group']
        for zone_value in self.topology.values():
            if zone_value['group'] == zone_group and zone_value['coordinator']:
                return zone_value['ip']

        # Not Found
        return None

    def __get_topology(self, refresh=False):
        """ Gets the topology if it is not already available or if refresh=True

        Code contributed by Aaron Daubman (daubman@gmail.com)

        Arguments:
        refresh -- Refresh the topology cache

        """
        if not self.topology or refresh:
            self.topology = {}
            response = requests.get('http://' + self.speaker_ip +
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
            response = requests.get('http://' + self.speaker_ip +
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
        """ Get information about the queue.

        Returns:
        A list containing a dictionary for each track in the queue. The track
        dictionary contains the following information about the track: title,
        artist, album, album_art, uri

        If we're unable to return data for a field, we'll return an empty
        list. This can happen for all kinds of reasons so be sure to check
        values.

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
        try:
            result_dom = XML.fromstring(really_utf8(result))
            for element in result_dom.findall(
                    './/{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item'):
                try:
                    item = {'title': None,
                            'artist': None,
                            'album': None,
                            'album_art': None,
                            'uri': None
                            }

                    item['title'] = element.findtext(
                        '{http://purl.org/dc/elements/1.1/}title')
                    item['artist'] = element.findtext(
                        '{http://purl.org/dc/elements/1.1/}creator')
                    item['album'] = element.findtext(
                        '{urn:schemas-upnp-org:metadata-1-0/upnp/}album')
                    item['album_art'] = element.findtext(
                        '{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI')
                    item['uri'] = element.findtext(
                        '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res')

                    queue.append(item)
                except:  # pylint: disable=W0702
                    LOGGER.warning('Could not handle item: %s', element)
                    LOGGER.error(traceback.format_exc())

        except:  # pylint: disable=W0702
            LOGGER.error('Could not handle result from Sonos')
            LOGGER.error(traceback.format_exc())

        return queue

    def get_artists(self, start=0, max_items=100):
        """ Convinience method for: get_music_library_information('artists')
        Refer to the docstring for that method

        """
        out = self.get_music_library_information('artists', start, max_items)
        return out

    def get_album_artists(self, start=0, max_items=100):
        """ Convinience method for:
        get_music_library_information('album_artists')
        Refer to the docstring for that method

        """
        out = self.get_music_library_information('album_artists',
                                                 start, max_items)
        return out

    def get_albums(self, start=0, max_items=100):
        """ Convinience method for: get_music_library_information('albums')
        Refer to the docstring for that method

        """
        out = self.get_music_library_information('albums', start, max_items)
        return out

    def get_genres(self, start=0, max_items=100):
        """ Convinience method for: get_music_library_information('genres')
        Refer to the docstring for that method.

        """
        out = self.get_music_library_information('genres', start, max_items)
        return out

    def get_composers(self, start=0, max_items=100):
        """ Convinience method for: get_music_library_information('composers')
        Refer to the docstring for that method

        """
        out = self.get_music_library_information('composers', start, max_items)
        return out

    def get_tracks(self, start=0, max_items=100):
        """ Convinience method for: get_music_library_information('tracks')
        Refer to the docstring for that method

        """
        out = self.get_music_library_information('tracks', start, max_items)
        return out

    def get_playlists(self, start=0, max_items=100):
        """ Convinience method for: get_music_library_information('playlists')
        Refer to the docstring for that method

        """
        out = self.get_music_library_information('playlists', start, max_items)
        return out

    def get_music_library_information(self, search_type, start=0,
                                      max_items=100):
        """ Retrieve information about the music library

        Arguments:
        search      The kind of information to retrieve. Can be one of:
                    'folders', 'artists', 'album_artists', 'albums', 'genres',
                    'composers', 'tracks', 'share' and 'playlists', where
                    playlists are the imported file based playlists from the
                    music library
        start       starting number of returned matches
        max_items   maximum number of returned matches. NOTE: The maximum
                    may be restricted by the unit, presumably due to transfer
                    size consideration, so check the returned number against
                    the requested.

        Returns a dictionary with metadata for the search, with the keys
        'number_returned', 'update_id', 'total_matches' and an 'item' list with
        the search results. The search results are instances of one of the
        subclasses of MusicLibraryItem depending on the search class. See the
        docs for those class for the details on the available information.

        Raises SoCoException (or a subclass) upon errors.

        The information about the which searches can be performed and the form
        of the query has been gathered from the Janos project:
        http://sourceforge.net/projects/janos/ Probs to the authors of that
        project.

        """
        search_translation = {'folders': 'A:', 'artists': 'A:ARTIST',
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
        #result_xml = XML.fromstring(really_utf8(dom.findtext('.//Result')))
        for container in dom:
            item = get_ml_item(container)
            # Append the item to the list
            out['item_list'].append(item)

        return out

    def add_to_queue(self, queueable_item):
        """ Adds a queueable item to the queue """
        if not isinstance(queueable_item, QueueableItem):
            raise TypeError('queueable_item must be an instance of '
                            'QueueableItem or sub classes')

        try:
            metadata = XML.tostring(queueable_item.get_didl_metadata())
        except CannotCreateDIDLMetadata as exception:
            message = ('The queueable item could not be enqueued, because it '
                       'raised a CannotCreateDIDLMetadata exception with the '
                       'following message:\n{0}').format(exception.message)
            raise ValueError(message)
        metadata = cgi.escape(metadata).encode('utf-8')

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
                favorite['title'] = really_utf8(item.findtext(
                    './/{http://purl.org/dc/elements/1.1/}title'))
                favorite['uri'] = item.findtext(
                    './/{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res')
                favorites.append(favorite)

        result['total'] = response['TotalMatches']
        result['returned'] = len(favorites)
        result['favorites'] = favorites

        return result


# definition section

PLAYER_SEARCH = """M-SEARCH * HTTP/1.1
HOST: 239.255.255.250:reservedSSDPport
MAN: ssdp:discover
MX: 1
ST: urn:schemas-upnp-org:device:ZonePlayer:1"""

MCAST_GRP = "239.255.255.250"
MCAST_PORT = 1900

RADIO_STATIONS = 0
RADIO_SHOWS = 1

NS = {'dc': '{http://purl.org/dc/elements/1.1/}',
      'upnp': '{urn:schemas-upnp-org:metadata-1-0/upnp/}',
      '': '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}'}
