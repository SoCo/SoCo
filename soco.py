# -*- coding: utf-8 -*-

""" SoCo (Sonos Controller) is a simple library to control Sonos speakers """

# Will be parsed by setup.py to determine package metadata
__author__ = 'Rahim Sonawalla <rsonawalla@gmail.com>'
__version__ = '0.2'
__website__ = 'https://github.com/rahims/SoCo'
__license__ = 'MIT License'

import xml.etree.cElementTree as XML

import requests
import select
import socket
import logging, traceback


__all__ = ['SonosDiscovery', 'SoCo']

class SonosDiscovery(object):
    """A simple class for discovering Sonos speakers.

    Public functions:
    get_speaker_ips -- Get a list of IPs of all zoneplayers.
    """

    def __init__(self):
        self._sock = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)


    def get_speaker_ips(self):
        speakers = []

        self._sock.sendto(PLAYER_SEARCH, (MCAST_GRP, MCAST_PORT))

        while True:
            rs, _, _ = select.select([self._sock], [], [], 1)
            if rs:
                _, addr = self._sock.recvfrom(2048)
                speakers.append(addr[0])
            else:
                break
        return speakers

class SoCo(object):
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
    mute -- Mute (or unmute) the speaker.
    volume -- Get or set the volume of the speaker.
    bass -- Get or set the speaker's bass EQ.
    treble -- Set the speaker's treble EQ.
    set_play_mode -- Change repeat and shuffle settings on the queue.
    set_loudness -- Turn on (or off) the speaker's loudness compensation.
    switch_to_line_in -- Switch the speaker's input to line-in.
    status_light -- Turn on (or off) the Sonos status light.
    get_current_track_info -- Get information about the currently playing track.
    get_speaker_info -- Get information about the Sonos speaker.
    partymode -- Put all the speakers in the network in the same group, a.k.a Party Mode.
    join -- Join this speaker to another "master" speaker.
    get_speaker_info -- Get information on this speaker.
    get_queue -- Get information about the queue.
    add_to_queue -- Add a track to the end of the queue
    remove_from_queue -- Remove a track from the queue
    clear_queue -- Remove all tracks from queue

    """

    speakers_ip = [] # Stores the IP addresses of all the speakers in a network

    def __init__(self, speaker_ip):
        self.speaker_ip = speaker_ip
        self.speaker_info = {} # Stores information about the current speaker

    def set_play_mode(self, playmode):
        """ Sets the play mode for the queue. Case-insensitive options are:
        NORMAL -- Turns off shuffle and repeat.
        REPEAT_ALL -- Turns on repeat and turns off shuffle.
        SHUFFLE -- Turns on shuffle *and* repeat. (It's strange, I know.) 
        SHUFFLE_NOREPEAT -- Turns on shuffle and turns off repeat.

        Returns:
        True if the play mode was successfully set.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        modes = ('NORMAL','SHUFFLE_NOREPEAT','SHUFFLE','REPEAT_ALL')
        playmode = playmode.upper()
        if not playmode in modes: raise KeyError, "invalid play mode"

        action = '"urn:schemas-upnp-org:service:AVTransport:1#SetPlayMode"'
        body = '<u:SetPlayMode xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><NewPlayMode>'+playmode+'</NewPlayMode></u:SetPlayMode>'
        response = self.__send_command(TRANSPORT_ENDPOINT, action, body)
        if "errorCode" in response:
            return self.__parse_error(response)
        else:
            return True

    def play_from_queue(self, queue_index):
        """ Play an item from the queue. The track number is required as an
        argument, where the first track is 0.

        Returns:
        True if the Sonos speaker successfully started playing the track.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        # Grab the speaker's information if we haven't already since we'll need
        # it in the next step.
        if not self.speaker_info:
            self.get_speaker_info()

        # first, set the queue itself as the source URI
        uri = 'x-rincon-queue:{0}#0'.format(self.speaker_info['uid'])
        body = PLAY_FROM_QUEUE_BODY_TEMPLATE.format(uri=uri)

        response = self.__send_command(TRANSPORT_ENDPOINT, SET_TRANSPORT_ACTION, body)
        if not (response == PLAY_FROM_QUEUE_RESPONSE):
            return self.__parse_error(response)

        # second, set the track number with a seek command
        body = SEEK_TRACK_BODY_TEMPLATE.format(track=queue_index+1)

        response = self.__send_command(TRANSPORT_ENDPOINT, SEEK_ACTION, body)
        if "errorCode" in response:
            return self.__parse_error(response)

        # finally, just play what's set
        return self.play()

    def play(self):
        """Play the currently selected track.

        Returns:
        True if the Sonos speaker successfully started playing the track.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.
        """

        response = self.__send_command(TRANSPORT_ENDPOINT, PLAY_ACTION, PLAY_BODY)
        if (response == PLAY_RESPONSE):
            return True
        else:
            return self.__parse_error(response)


    def play_uri(self, uri=''):
        """Play a given stream. Pauses the queue.

        Arguments:
        uri -- URI of a stream to be played.

        Returns:
        True if the Sonos speaker successfully started playing the track.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        body = PLAY_URI_BODY_TEMPLATE.format(uri=uri)

        response = self.__send_command(TRANSPORT_ENDPOINT, SET_TRANSPORT_ACTION, body)

        if (response == ENQUEUE_RESPONSE):
            # The track is enqueued, now play it.
            return self.play()
        else:
            return self.__parse_error(response)


    def pause(self):
        """ Pause the currently playing track.

        Returns:
        True if the Sonos speaker successfully paused the track.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        response = self.__send_command(TRANSPORT_ENDPOINT, PAUSE_ACTION, PAUSE_BODY)

        if (response == PAUSE_RESPONSE):
            return True
        else:
            return self.__parse_error(response)

    def stop(self):
        """ Stop the currently playing track.

        Returns:
        True if the Sonos speaker successfully stopped the playing track.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        response = self.__send_command(TRANSPORT_ENDPOINT, STOP_ACTION, STOP_BODY)

        if (response == STOP_RESPONSE):
            return True
        else:
            return self.__parse_error(response)

    def seek(self, timestamp):
        """ Seeks to a given timestamp in the current track, specified in the
        format of HH:MM:SS.

        Returns:
        True if the Sonos speaker successfully seeked to the timecode.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        import re
        if not re.match(r'^[0-9][0-9]:[0-9][0-9]:[0-9][0-9]$',timestamp):
            raise ValueError, "invalid timestamp, use HH:MM:SS format"

        body = SEEK_TIMESTAMP_BODY_TEMPLATE.format(timestamp=timestamp)
        response = self.__send_command(TRANSPORT_ENDPOINT, SEEK_ACTION, body)
        if "errorCode" in response:
            return self.__parse_error(response)
        else:
            return True

    def next(self):
        """ Go to the next track.

        Returns:
        True if the Sonos speaker successfully skipped to the next track.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned. Keep in mind that next() can return errors
        for a variety of reasons. For example, if the Sonos is streaming
        Pandora and you call next() several times in quick succession an error
        code will likely be returned (since Pandora has limits on how many
        songs can be skipped).

        """
        response = self.__send_command(TRANSPORT_ENDPOINT, NEXT_ACTION, NEXT_BODY)

        if (response == NEXT_RESPONSE):
            return True
        else:
            return self.__parse_error(response)

    def previous(self):
        """ Go back to the previously played track.

        Returns:
        True if the Sonos speaker successfully went to the previous track.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned. Keep in mind that previous() can return errors
        for a variety of reasons. For example, previous() will return an error
        code (error code 701) if the Sonos is streaming Pandora since you can't
        go back on tracks.

        """
        response = self.__send_command(TRANSPORT_ENDPOINT, PREV_ACTION, PREV_BODY)

        if (response == PREV_RESPONSE):
            return True
        else:
            return self.__parse_error(response)

    def mute(self, mute):
        """ Mute or unmute the Sonos speaker.

        Arguments:
        mute -- True to mute. False to unmute.

        Returns:
        True if the Sonos speaker was successfully muted or unmuted.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        mute_value = '1' if mute else '0'

        body = MUTE_BODY_TEMPLATE.format(mute=mute_value)

        response = self.__send_command(RENDERING_ENDPOINT, MUTE_ACTION, body)

        if (response == MUTE_RESPONSE):
            return True
        else:
            return self.parse(response)

    def volume(self, volume=False):
        """ Get or set the Sonos speaker volume.

        Arguments:
        volume -- A value between 0 and 100.

        Returns:
        If the volume argument was specified: returns true if the Sonos speaker
        successfully set the volume.

        If the volume argument was not specified: returns the current volume of
        the Sonos speaker.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        if volume:
            body = SET_VOLUME_BODY_TEMPLATE.format(volume=volume)

            response = self.__send_command(RENDERING_ENDPOINT, SET_VOLUME_ACTION, body)

            if (response == SET_VOLUME_RESPONSE):
                return True
            else:
                return self.__parse_error(response)
        else:
            response = self.__send_command(RENDERING_ENDPOINT, GET_VOLUME_ACTION, GET_VOLUME_BODY)

            dom = XML.fromstring(response)

            volume = dom.findtext('.//CurrentVolume')

            return int(volume)

    def bass(self, bass=False):
        """ Get or set the Sonos speaker's bass EQ.

        Arguments:
        bass -- A value between -10 and 10.

        Returns:
        If the bass argument was specified: returns true if the Sonos speaker
        successfully set the bass EQ.

        If the bass argument was not specified: returns the current base value.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        if bass is not False:
            body = SET_BASS_BODY_TEMPLATE.format(bass=bass)

            response = self.__send_command(RENDERING_ENDPOINT, SET_BASS_ACTION, body)

            if (response == SET_BASS_RESPONSE):
                return True
            else:
                return self.__parse_error(response)
        else:
            response = self.__send_command(RENDERING_ENDPOINT, GET_BASS_ACTION, GET_BASS_BODY)

            dom = XML.fromstring(response)

            bass = dom.findtext('.//CurrentBass')

            return int(bass)

    def treble(self, treble=False):
        """ Get or set the Sonos speaker's treble EQ.

        Arguments:
        treble -- A value between -10 and 10.

        Returns:
        If the treble argument was specified: returns true if the Sonos speaker
        successfully set the treble EQ.

        If the treble argument was not specified: returns the current treble value.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        if treble is not False:
            body = SET_TREBLE_BODY_TEMPLATE.format(treble=treble)

            response = self.__send_command(RENDERING_ENDPOINT, SET_TREBLE_ACTION, body)

            if (response == SET_TREBLE_RESPONSE):
                return True
            else:
                return self.__parse_error(response)
        else:
            response = self.__send_command(RENDERING_ENDPOINT, GET_TREBLE_ACTION, GET_TREBLE_BODY)

            dom = XML.fromstring(response)

            treble = dom.findtext('.//CurrentTreble')

            return int(treble)

    def set_loudness(self, loudness):
        """ Set the Sonos speaker's loudness compensation.

        Loudness is a complicated topic. You can find a nice summary about this
        feature here: http://forums.sonos.com/showthread.php?p=4698#post4698

        Arguments:
        loudness -- True to turn on loudness compensation. False to disable it.

        Returns:
        True if the Sonos speaker successfully set the loundess compensation.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        loudness_value = '1' if loudness else '0'

        body = SET_LOUDNESS_BODY_TEMPLATE.format(loudness=loudness_value)

        response = self.__send_command(RENDERING_ENDPOINT, SET_LOUDNESS_ACTION, body)

        if (response == SET_LOUDNESS_RESPONSE):
            return True
        else:
            return self.__parse_error(response)

    def partymode (self):
        """ Put all the speakers in the network in the same group, a.k.a Party Mode.

		This blog shows the initial research responsible for this:
        http://travelmarx.blogspot.dk/2010/06/exploring-sonos-via-upnp.html

		The trick seems to be (only tested on a two-speaker setup) to tell each
        speaker which to join. There's probably a bit more to it if multiple
        groups have been defined.

        Code contributed by Thomas Bartvig (thomas.bartvig@gmail.com)

		Returns:
		True if partymode is set

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

		"""
        master_speaker_info = self.get_speaker_info()
        ips = self.get_speakers_ip()

        rc = True
        # loop through all IP's in topology and make them join this master
        for ip in ips:
            if not (ip == self.speaker_ip):
                slave = SoCo(ip)
                ret = slave.join(master_speaker_info["uid"])
                if ret is False:
                    rc = False

        return rc

    def join(self, master_uid):
        """ Join this speaker to another "master" speaker.

        Code contributed by Thomas Bartvig (thomas.bartvig@gmail.com)

		Returns:
		True if this speaker has joined the master speaker

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

		"""
        body = JOIN_BODY_TEMPLATE.format(master_uid=master_uid)

        response = self.__send_command(TRANSPORT_ENDPOINT, SET_TRANSPORT_ACTION, body)

        if (response == JOIN_RESPONSE):
            return True
        else:
            return self.__parse_error(response)

    def switch_to_line_in(self):
        """ Switch the speaker's input to line-in.

        Returns:
        True if the Sonos speaker successfully switched to line-in.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned. Note, an error will be returned if you try
        to switch to line-in on a device (like the Play:3) that doesn't have
        line-in capability.

        """
        speaker_info = self.get_speaker_info()

        body = SET_LINEIN_BODY_TEMPLATE.format(speaker_uid=speaker_info['uid'])

        response = self.__send_command(TRANSPORT_ENDPOINT, SET_TRANSPORT_ACTION, body)

        if (response == SET_LINEIN_RESPONSE):
            return True
        else:
            return self.__parse_error(response)

    def status_light(self, led_on):
        """ Turn on (or off) the white Sonos status light.

        Turns on or off the little white light on the Sonos speaker. (It's
        between the mute button and the volume up button on the speaker.)

        Arguments:
        led_on -- True to turn on the light. False to turn off the light.

        Returns:
        True if the Sonos speaker successfully turned on (or off) the light.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        led_state = 'On' if led_on else 'Off'

        body = SET_LEDSTATE_BODY_TEMPLATE.format(state=led_state)

        response = self.__send_command(DEVICE_ENDPOINT, SET_LEDSTATE_ACTION, body)

        if (response == SET_LEDSTATE_RESPONSE):
            return True
        else:
            return self.parse(response)

    def get_current_track_info(self):
        """ Get information about the currently playing track.

        Returns:
        A dictionary containing the following information about the currently
        playing track: playlist_position, duration, title, artist, album, and
        a link to the album art.

        If we're unable to return data for a field, we'll return an empty
        string. This can happen for all kinds of reasons so be sure to check
        values. For example, a track may not have complete metadata and be
        missing an album name. In this case track['album'] will be an empty string.

        """
        response = self.__send_command(TRANSPORT_ENDPOINT, GET_CUR_TRACK_ACTION, GET_CUR_TRACK_BODY)

        dom = XML.fromstring(response)

        track = {}

        track['playlist_position'] = dom.findtext('.//Track')
        track['duration'] = dom.findtext('.//TrackDuration')
        track['uri'] = dom.findtext('.//TrackURI')

        d = dom.findtext('.//TrackMetaData')

        # Duration seems to be '0:00:00' when listening to radio
        if track['duration'] == '0:00:00':
            metadata = XML.fromstring(d.encode('utf-8'))

            # #Try parse trackinfo
            trackinfo = metadata.findtext('.//{urn:schemas-rinconnetworks-com:metadata-1-0/}streamContent')

            try:
                index = trackinfo.find(' - ')

                if index > -1:
                    track['artist'] = trackinfo[:index]
                    track['title'] = trackinfo[index+3:]
            except:
                logging.warning('Could not handle track info: "%s"', trackinfo)
                logging.warning(traceback.format_exc())
                track['artist'] = ''
                track['title'] = trackinfo

            track['album'] = ''
            track['album_art'] = ''

        # If the speaker is playing from the line-in source, querying for track
        # metadata will return "NOT_IMPLEMENTED".
        elif d is not '' or d is not 'NOT_IMPLEMENTED':
            # Track metadata is returned in DIDL-Lite format
            metadata = XML.fromstring(d.encode('utf-8'))

            track['title'] = metadata.findtext('.//{http://purl.org/dc/elements/1.1/}title')
            track['artist'] = metadata.findtext('.//{http://purl.org/dc/elements/1.1/}creator')
            track['album'] = metadata.findtext('.//{urn:schemas-upnp-org:metadata-1-0/upnp/}album')

            album_art = metadata.findtext('.//{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI')

            if album_art is not None:
                track['album_art'] = 'http://' + self.speaker_ip + ':1400' + metadata.findtext('.//{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI')
            else:
                track['album_art'] = ''
        else:
            track['title'] = ''
            track['artist'] = ''
            track['album'] = ''
            track['album_art'] = ''

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
            response = requests.get('http://' + self.speaker_ip + ':1400/status/zp')

            dom = XML.fromstring(response.content)

            self.speaker_info['zone_name'] = dom.findtext('.//ZoneName')
            self.speaker_info['zone_icon'] = dom.findtext('.//ZoneIcon')
            self.speaker_info['uid'] = dom.findtext('.//LocalUID')
            self.speaker_info['serial_number'] = dom.findtext('.//SerialNumber')
            self.speaker_info['software_version'] = dom.findtext('.//SoftwareVersion')
            self.speaker_info['hardware_version'] = dom.findtext('.//HardwareVersion')
            self.speaker_info['mac_address'] = dom.findtext('.//MACAddress')

            return self.speaker_info

    def get_speakers_ip(self, refresh=False):
        """ Get the IP addresses of all the Sonos speakers in the network.

        Code contributed by Thomas Bartvig (thomas.bartvig@gmail.com)

        Arguments:
        refresh -- Refresh the speakers IP cache.

        Returns:
        IP addresses of the Sonos speakers.

        """
        import re

        if self.speakers_ip and not refresh:
            return self.speakers_ip
        else:
            response = requests.get('http://' + self.speaker_ip + ':1400/status/topology')
            text = response.text
            grp = re.findall(r'(\d+\.\d+\.\d+\.\d+):1400', text)

            for i in grp:
                response = requests.get('http://' + i + ':1400/status')

                if response.status_code == 200:
                    self.speakers_ip.append(i)

            return self.speakers_ip

    def get_queue(self, start = 0, max_items = 100):
        """ Get information about the queue.

        Returns:
        A list containing a dictionary for each track in the queue. The track dictionary
        contains the following information about the track: title, artist, album, album_art, uri

        If we're unable to return data for a field, we'll return an empty
        list. This can happen for all kinds of reasons so be sure to check
        values.

        This method is heavly based on Sam Soffes (aka soffes) ruby implementation

        """
        meta_data = {
            'name': 'Browse',
            'CONTENT_DIRECTORY_XMLNS': 'urn:schemas-upnp-org:service:ContentDirectory:1',
            'starting_index': start,
            'requested_count': max_items
        }

        queue = []

        action = '"%(CONTENT_DIRECTORY_XMLNS)s#%(name)s"' % meta_data
        body = '''<u:%(name)s xmlns:u="%(CONTENT_DIRECTORY_XMLNS)s">
                    <ObjectID>Q:0</ObjectID>
                    <BrowseFlag>BrowseDirectChildren</BrowseFlag>
                    <Filter>dc:title,res,dc:creator,upnp:artist,upnp:album,upnp:albumArtURI</Filter>
                    <StartingIndex>%(starting_index)d</StartingIndex>
                    <RequestedCount>%(requested_count)d</RequestedCount>
                    <SortCriteria></SortCriteria>
                    </u:Browse>''' % meta_data

        response = self.__send_command('/MediaServer/ContentDirectory/Control', action, body)

        try:
            dom = XML.fromstring(response.encode('utf-8'))
            resultText = dom.findtext('.//Result')
            if not resultText: return queue

            resultDom  = XML.fromstring(resultText.encode('utf-8'))
            for element in resultDom.findall('.//{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item'):
                try:
                    item = {
                        'title': None,
                        'artist': None,
                        'album': None,
                        'album_art': None,
                        'uri': None
                        }

                    item['title'] =     element.findtext('{http://purl.org/dc/elements/1.1/}title')
                    item['artist'] =    element.findtext('{http://purl.org/dc/elements/1.1/}creator')
                    item['album'] =     element.findtext('{urn:schemas-upnp-org:metadata-1-0/upnp/}album')
                    item['album_art'] = element.findtext('{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI')
                    item['uri'] =       element.findtext('{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res')

                    queue.append(item)
                except:
                    logging.warning('Could not handle item: %s', element)
                    logging.error(traceback.format_exc())

        except:
            logging.error('Could not handle result from sonos')
            logging.error(traceback.format_exc())

        return queue

    def add_to_queue(self, uri):
        """ Adds a given track to the queue.

        Returns:
        If the Sonos speaker successfully added the track, returns the queue
        position of the track added.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        body = ADD_TO_QUEUE_BODY_TEMPLATE.format(uri=uri)

        response = self.__send_command(TRANSPORT_ENDPOINT, ADD_TO_QUEUE_ACTION, body)
        if "errorCode" in response:
            return self.__parse_error(response)
        else:
            dom = XML.fromstring(response)
            qnumber = dom.findtext('.//FirstTrackNumberEnqueued')
            return int(qnumber)

    def remove_from_queue(self, index):
        """ Removes a track from the queue.

        index: the index of the track to remove; first item in the queue is 1

        Returns:
        True if the Sonos speaker successfully removed the track

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        #TODO: what do these parameters actually do?
        instance = updid = '0'
        objid = 'Q:0/'+str(index)
        body = REMOVE_FROM_QUEUE_BODY_TEMPLATE.format(instance=instance, objid=objid, updateid=updid)
        response = self.__send_command(TRANSPORT_ENDPOINT, REMOVE_FROM_QUEUE_ACTION, body)
        if "errorCode" in response:
            return self.__parse_error(response)
        else:
            return True

    def clear_queue(self):
        """ Removes all tracks from the queue.

        Returns:
        True if the Sonos speaker cleared the queue.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.
        """
        response = self.__send_command(TRANSPORT_ENDPOINT, CLEAR_QUEUE_ACTION, CLEAR_QUEUE_BODY)
        if "errorCode" in response:
            return self.__parse_error(response)
        else:
            return True

    def __send_command(self, endpoint, action, body):
        """ Send a raw command to the Sonos speaker.

        Returns:
        The raw response body returned by the Sonos speaker.

        """
        headers = {
            'Content-Type': 'text/xml',
            'SOAPACTION': action
        }

        soap = SOAP_TEMPLATE.format(body=body)

        r = requests.post('http://' + self.speaker_ip + ':1400' + endpoint, data=soap, headers=headers)

        return r.content

    def __parse_error(self, response):
        """ Parse an error returned from the Sonos speaker.

        Returns:
        The UPnP error code returned by the Sonos speaker.

        If we're unable to parse the error response for whatever reason, the
        raw response sent back from the Sonos speaker will be returned.

        """
        error = XML.fromstring(response)

        errorCode = error.findtext('.//{urn:schemas-upnp-org:control-1-0}errorCode')

        if errorCode is not None:
            return int(errorCode)
        else:
            # Unknown error, so just return the entire response
            return response



# definition section

PLAYER_SEARCH = """M-SEARCH * HTTP/1.1
HOST: 239.255.255.250:reservedSSDPport
MAN: ssdp:discover
MX: 1
ST: urn:schemas-upnp-org:device:ZonePlayer:1"""


MCAST_GRP = "239.255.255.250"
MCAST_PORT = 1900

TRANSPORT_ENDPOINT = '/MediaRenderer/AVTransport/Control'
RENDERING_ENDPOINT = '/MediaRenderer/RenderingControl/Control'
DEVICE_ENDPOINT = '/DeviceProperties/Control'

ENQUEUE_BODY_TEMPLATE = '<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><CurrentURI>{uri}</CurrentURI><CurrentURIMetaData></CurrentURIMetaData></u:SetAVTransportURI>'
ENQUEUE_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetAVTransportURIResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:SetAVTransportURIResponse></s:Body></s:Envelope>'

PLAY_ACTION = '"urn:schemas-upnp-org:service:AVTransport:1#Play"'
PLAY_BODY = '<u:Play xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Speed>1</Speed></u:Play>'
PLAY_RESPONSE =  '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:PlayResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:PlayResponse></s:Body></s:Envelope>'

PLAY_FROM_QUEUE_BODY_TEMPLATE = '''
<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
    <InstanceID>0</InstanceID>
    <CurrentURI>{uri}</CurrentURI>
    <CurrentURIMetaData></CurrentURIMetaData>
</u:SetAVTransportURI>
'''
PLAY_FROM_QUEUE_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetAVTransportURIResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:SetAVTransportURIResponse></s:Body></s:Envelope>'



PAUSE_ACTION =  '"urn:schemas-upnp-org:service:AVTransport:1#Pause"'
PAUSE_BODY = '<u:Pause xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Speed>1</Speed></u:Pause>'
PAUSE_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:PauseResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:PauseResponse></s:Body></s:Envelope>'

STOP_ACTION = '"urn:schemas-upnp-org:service:AVTransport:1#Stop"'
STOP_BODY = '<u:Stop xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Speed>1</Speed></u:Stop>'
STOP_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:StopResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:StopResponse></s:Body></s:Envelope>'

NEXT_ACTION = '"urn:schemas-upnp-org:service:AVTransport:1#Next"'
NEXT_BODY = '<u:Next xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Speed>1</Speed></u:Next>'
NEXT_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:NextResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:NextResponse></s:Body></s:Envelope>'

PREV_ACTION = '"urn:schemas-upnp-org:service:AVTransport:1#Previous"'
PREV_BODY = '<u:Previous xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Speed>1</Speed></u:Previous>'
PREV_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:PreviousResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:PreviousResponse></s:Body></s:Envelope>'

MUTE_ACTION = '"urn:schemas-upnp-org:service:RenderingControl:1#SetMute"'
MUTE_BODY_TEMPLATE = '<u:SetMute xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel><DesiredMute>{mute}</DesiredMute></u:SetMute>'
MUTE_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetMuteResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"></u:SetMuteResponse></s:Body></s:Envelope>'

SET_VOLUME_ACTION = '"urn:schemas-upnp-org:service:RenderingControl:1#SetVolume"'
SET_VOLUME_BODY_TEMPLATE  = '<u:SetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel><DesiredVolume>{volume}</DesiredVolume></u:SetVolume>'
SET_VOLUME_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetVolumeResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"></u:SetVolumeResponse></s:Body></s:Envelope>'

GET_VOLUME_ACTION = '"urn:schemas-upnp-org:service:RenderingControl:1#GetVolume"'
GET_VOLUME_BODY = '<u:GetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel></u:GetVolume>'

SET_BASS_ACTION = '"urn:schemas-upnp-org:service:RenderingControl:1#SetBass"'
SET_BASS_BODY_TEMPLATE = '<u:SetBass xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><DesiredBass>{bass}</DesiredBass></u:SetBass>'
SET_BASS_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetBassResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"></u:SetBassResponse></s:Body></s:Envelope>'

GET_BASS_ACTION = '"urn:schemas-upnp-org:service:RenderingControl:1#GetBass"'
GET_BASS_BODY = '<u:GetBass xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel></u:GetBass>'

SET_TREBLE_ACTION = '"urn:schemas-upnp-org:service:RenderingControl:1#SetTreble"'
SET_TREBLE_BODY_TEMPLATE = '<u:SetTreble xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><DesiredTreble>{treble}</DesiredTreble></u:SetTreble>'
SET_TREBLE_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetTrebleResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"></u:SetTrebleResponse></s:Body></s:Envelope>'

GET_TREBLE_ACTION = '"urn:schemas-upnp-org:service:RenderingControl:1#GetTreble"'
GET_TREBLE_BODY = '<u:GetTreble xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel></u:GetTreble>'

SET_LOUDNESS_ACTION = '"urn:schemas-upnp-org:service:RenderingControl:1#SetLoudness"'
SET_LOUDNESS_BODY_TEMPLATE = '<u:SetLoudness xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel><DesiredLoudness>{loudness}</DesiredLoudness></u:SetLoudness>'
SET_LOUDNESS_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetLoudnessResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"></u:SetLoudnessResponse></s:Body></s:Envelope>'

SET_TRANSPORT_ACTION = '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"'

JOIN_BODY_TEMPLATE = '<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><CurrentURI>x-rincon:{master_uid}</CurrentURI><CurrentURIMetaData></CurrentURIMetaData></u:SetAVTransportURI>'
JOIN_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetAVTransportURIResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:SetAVTransportURIResponse></s:Body></s:Envelope>'

SET_LINEIN_BODY_TEMPLATE = '<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><CurrentURI>x-rincon-stream:{speaker_uid}</CurrentURI><CurrentURIMetaData></CurrentURIMetaData></u:SetAVTransportURI>'
SET_LINEIN_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetAVTransportURIResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:SetAVTransportURIResponse></s:Body></s:Envelope>'

SET_LEDSTATE_ACTION = '"urn:schemas-upnp-org:service:DeviceProperties:1#SetLEDState"'
SET_LEDSTATE_BODY_TEMPLATE = '<u:SetLEDState xmlns:u="urn:schemas-upnp-org:service:DeviceProperties:1"><DesiredLEDState>{state}</DesiredLEDState>'
SET_LEDSTATE_RESPONSE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetLEDStateResponse xmlns:u="urn:schemas-upnp-org:service:DeviceProperties:1"></u:SetLEDStateResponse></s:Body></s:Envelope>'

GET_CUR_TRACK_ACTION = '"urn:schemas-upnp-org:service:AVTransport:1#GetPositionInfo"'
GET_CUR_TRACK_BODY = '<u:GetPositionInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Channel>Master</Channel></u:GetPositionInfo>'

SOAP_TEMPLATE = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>{body}</s:Body></s:Envelope>'

SEEK_ACTION = '"urn:schemas-upnp-org:service:AVTransport:1#Seek"'
SEEK_TRACK_BODY_TEMPLATE = '''
<u:Seek xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
<InstanceID>0</InstanceID>
<Unit>TRACK_NR</Unit>
<Target>{track}</Target>
</u:Seek>
'''

SEEK_TIMESTAMP_BODY_TEMPLATE = '<u:Seek xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Unit>REL_TIME</Unit><Target>{timestamp}</Target></u:Seek>'

PLAY_URI_BODY_TEMPLATE = '<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><CurrentURI>{uri}</CurrentURI><CurrentURIMetaData></CurrentURIMetaData></u:SetAVTransportURI>'

ADD_TO_QUEUE_ACTION = 'urn:schemas-upnp-org:service:AVTransport:1#AddURIToQueue'
ADD_TO_QUEUE_BODY_TEMPLATE = '<u:AddURIToQueue xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><EnqueuedURI>{uri}</EnqueuedURI><EnqueuedURIMetaData></EnqueuedURIMetaData><DesiredFirstTrackNumberEnqueued>0</DesiredFirstTrackNumberEnqueued><EnqueueAsNext>1</EnqueueAsNext></u:AddURIToQueue>'


REMOVE_FROM_QUEUE_ACTION = 'urn:schemas-upnp-org:service:AVTransport:1#RemoveTrackFromQueue'
REMOVE_FROM_QUEUE_BODY_TEMPLATE = '<u:RemoveTrackFromQueue xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>{instance}</InstanceID><ObjectID>{objid}</ObjectID><UpdateID>{updateid}</UpdateID></u:RemoveTrackFromQueue>'

CLEAR_QUEUE_ACTION = '"urn:schemas-upnp-org:service:AVTransport:1#RemoveAllTracksFromQueue"'
CLEAR_QUEUE_BODY = '<u:RemoveAllTracksFromQueue xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID></u:RemoveAllTracksFromQueue>'

