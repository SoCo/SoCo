import xml.etree.cElementTree as XML

import requests
import select
import socket
import logging, traceback

class SonosDiscovery(object):
    """A simple class for discovering Sonos speakers.

    Public functions:
    get_speaker_ips -- Get a list of IPs of all zoneplayers.
    """

    PLAYER_SEARCH = """M-SEARCH * HTTP/1.1
HOST: 239.255.255.250:reservedSSDPport
MAN: ssdp:discover
MX: 1
ST: urn:schemas-upnp-org:device:ZonePlayer:1"""

    MCAST_GRP = "239.255.255.250"
    MCAST_PORT = 1900

    def __init__(self):
        self._all_speakers = []
        self._sock = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)


    def get_speaker_ips(self):
        speakers = []

        self._sock.sendto(self.PLAYER_SEARCH, (self.MCAST_GRP, self.MCAST_PORT))

        while True:
            print "selecting"
            rs, _, _ = select.select([self._sock], [], [], 1)
            if rs:
                _, addr = self._sock.recvfrom(2048)
                speakers.append(addr[0])
            else:
                break
        self._all_speakers = speakers
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
    get_info -- get information on this speaker.
    add_to_queue -- add a track to the end of the queue
    remove_from_queue -- remove a track from the queue
    clear_queue -- remove all tracks from queue

    """

    TRANSPORT_ENDPOINT = '/MediaRenderer/AVTransport/Control'
    RENDERING_ENDPOINT = '/MediaRenderer/RenderingControl/Control'
    DEVICE_ENDPOINT = '/DeviceProperties/Control'

    speakers_ip = [] # Stores the IP addresses of all the speakers in a network

    def __init__(self, speaker_ip):
        self.speaker_ip = speaker_ip
        self.speaker_info = {} # Stores information about the current speaker

    def clear_queue(self):
        """ Removes all tracks from the queue.

        Returns:
        True if the Sonos speaker cleared the queue.
        
        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.
        """
        action = '"urn:schemas-upnp-org:service:AVTransport:1#RemoveAllTracksFromQueue"'
        body = '<u:RemoveAllTracksFromQueue xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID></u:RemoveAllTracksFromQueue>'
        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)
        if "errorCode" in response:
            return self.__parse_error(response)
        else:
            return True

    def set_play_mode(self, playmode):
        """ Sets the play mode for the queue. Case-insensitive options are:
        NORMAL -- just play the queue once
        REPEAT_ALL -- loop the entire queue
        SHUFFLE -- play all the tracks in the queue with shuffling
        SHUFFLE_NOREPEAT -- shuffle the queue, play all tracks, stop

        Returns:
        True if the Sonos speaker successfully started playing the track.
        
        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.
        """
        modes = ('NORMAL','SHUFFLE_NOREPEAT','SHUFFLE','REPEAT_ALL')
        playmode = playmode.upper()
        if not playmode in modes: raise KeyError, "invalid play mode"

        action = '"urn:schemas-upnp-org:service:AVTransport:1#SetPlayMode"'
        body = '<u:SetPlayMode xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><NewPlayMode>'+playmode+'</NewPlayMode></u:SetPlayMode>'
        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)
        if "errorCode" in response:
            return self.__parse_error(response)
        else:
            return True

    def play_from_queue(self, trackno):
        """ Play an item from the queue. The track number is required as an
        argument, where the first track is 1.
        
        Returns:
        True if the Sonos speaker successfully started playing the track.
        
        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.
        """
        # first, set the queue itself as the source URI
        uri = 'x-rincon-queue:'+self.speaker_info['uid']+'#0'
        action = '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"'
        body = '<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><CurrentURI>' + uri + '</CurrentURI><CurrentURIMetaData></CurrentURIMetaData></u:SetAVTransportURI>'

        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)
        if not (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetAVTransportURIResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:SetAVTransportURIResponse></s:Body></s:Envelope>'):
            return self.__parse_error(response)
        
        # second, set the track number with a seek command
        body = '<u:Seek xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Unit>TRACK_NR</Unit><Target>'+str(trackno)+'</Target></u:Seek>'
        action = '"urn:schemas-upnp-org:service:AVTransport:1#Seek"'
        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)
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
        action = '"urn:schemas-upnp-org:service:AVTransport:1#Play"'

        body = '<u:Play xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Speed>1</Speed></u:Play>'
        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)
        if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:PlayResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:PlayResponse></s:Body></s:Envelope>'):
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
        action = '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"'

        body = '<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><CurrentURI>' + uri + '</CurrentURI><CurrentURIMetaData></CurrentURIMetaData></u:SetAVTransportURI>'

        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)

        if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetAVTransportURIResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:SetAVTransportURIResponse></s:Body></s:Envelope>'):
            # The track is enqueued, now play it.
            return self.play()
        else:
            return self.__parse_error(response)
            
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
        action = 'urn:schemas-upnp-org:service:AVTransport:1#RemoveTrackFromQueue'
        body = '<u:RemoveTrackFromQueue xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>'+instance+'</InstanceID><ObjectID>'+objid+'</ObjectID><UpdateID>'+updid+'</UpdateID></u:RemoveTrackFromQueue>'
        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)
        if "errorCode" in response:
            return self.__parse_error(response)
        else:
            return True

    def add_to_queue(self, uri):
        """ Adds a given track to the queue.

        Returns:
        If the Sonos speaker successfully added the track, returns the queue
        position of the track added.

        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.

        """
        action = 'urn:schemas-upnp-org:service:AVTransport:1#AddURIToQueue'

        body = '<u:AddURIToQueue xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><EnqueuedURI>'+uri+'</EnqueuedURI><EnqueuedURIMetaData></EnqueuedURIMetaData><DesiredFirstTrackNumberEnqueued>0</DesiredFirstTrackNumberEnqueued><EnqueueAsNext>1</EnqueueAsNext></u:AddURIToQueue>'

        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)
        if "errorCode" in response:
            return self.__parse_error(response)
        else:
            dom = XML.fromstring(response)
            qnumber = dom.findtext('.//FirstTrackNumberEnqueued')
            return int(qnumber)

    def pause(self):
        """ Pause the currently playing track.

        Returns:
        True if the Sonos speaker successfully paused the track.
        
        If an error occurs, we'll attempt to parse the error and return a UPnP
        error code. If that fails, the raw response sent back from the Sonos
        speaker will be returned.
        
        """
        action = '"urn:schemas-upnp-org:service:AVTransport:1#Pause"'

        body = '<u:Pause xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Speed>1</Speed></u:Pause>'

        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)

        if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:PauseResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:PauseResponse></s:Body></s:Envelope>'):
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
        action = '"urn:schemas-upnp-org:service:AVTransport:1#Stop"'

        body = '<u:Stop xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Speed>1</Speed></u:Stop>'

        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)

        if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:StopResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:StopResponse></s:Body></s:Envelope>'):
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

        action = 'urn:schemas-upnp-org:service:AVTransport:1#Seek'
        body = '<u:Seek xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Unit>REL_TIME</Unit><Target>'+timestamp+'</Target></u:Seek>'
        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)
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
        action = '"urn:schemas-upnp-org:service:AVTransport:1#Next"'

        body = '<u:Next xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Speed>1</Speed></u:Next>'

        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)

        if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:NextResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:NextResponse></s:Body></s:Envelope>'):
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
        action = '"urn:schemas-upnp-org:service:AVTransport:1#Previous"'

        body = '<u:Previous xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Speed>1</Speed></u:Previous>'

        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)

        if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:PreviousResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:PreviousResponse></s:Body></s:Envelope>'):
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
        if mute is True:
            mute_value = '1'
        else:
            mute_value = '0'

        action = '"urn:schemas-upnp-org:service:RenderingControl:1#SetMute"'

        body = '<u:SetMute xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel><DesiredMute>' + mute_value + '</DesiredMute></u:SetMute>'

        response = self.__send_command(SoCo.RENDERING_ENDPOINT, action, body)

        if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetMuteResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"></u:SetMuteResponse></s:Body></s:Envelope>'):
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
            action = '"urn:schemas-upnp-org:service:RenderingControl:1#SetVolume"'

            body = '<u:SetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel><DesiredVolume>' + repr(volume) + '</DesiredVolume></u:SetVolume>'

            response = self.__send_command(SoCo.RENDERING_ENDPOINT, action, body)

            if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetVolumeResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"></u:SetVolumeResponse></s:Body></s:Envelope>'):
                return True
            else:
                return self.__parse_error(response)
        else:
            action = '"urn:schemas-upnp-org:service:RenderingControl:1#GetVolume"'

            body = '<u:GetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel></u:GetVolume>'

            response = self.__send_command(SoCo.RENDERING_ENDPOINT, action, body)

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
        if bass:
            action = '"urn:schemas-upnp-org:service:RenderingControl:1#SetBass"'

            body = '<u:SetBass xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><DesiredBass>' + repr(bass) + '</DesiredBass></u:SetBass>'

            response = self.__send_command(SoCo.RENDERING_ENDPOINT, action, body)

            if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetBassResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"></u:SetBassResponse></s:Body></s:Envelope>'):
                return True
            else:
                return self.__parse_error(response)
        else:
            action = '"urn:schemas-upnp-org:service:RenderingControl:1#GetBass"'

            body = '<u:GetBass xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel></u:GetBass>'

            response = self.__send_command(SoCo.RENDERING_ENDPOINT, action, body)

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
        if treble:
            action = '"urn:schemas-upnp-org:service:RenderingControl:1#SetTreble"'

            body = '<u:SetTreble xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><DesiredTreble>' + repr(treble) + '</DesiredTreble></u:SetTreble>'

            response = self.__send_command(SoCo.RENDERING_ENDPOINT, action, body)

            if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetTrebleResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"></u:SetTrebleResponse></s:Body></s:Envelope>'):
                return True
            else:
                return self.__parse_error(response)
        else:
            action = '"urn:schemas-upnp-org:service:RenderingControl:1#GetTreble"'

            body = '<u:GetTreble xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel></u:GetTreble>'

            response = self.__send_command(SoCo.RENDERING_ENDPOINT, action, body)

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
        action = '"urn:schemas-upnp-org:service:RenderingControl:1#SetLoudness"'

        if loudness is True:
            loudness_value = '1'
        else:
            loudness_value = '0'

        body = '<u:SetLoudness xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"><InstanceID>0</InstanceID><Channel>Master</Channel><DesiredLoudness>' + loudness_value + '</DesiredLoudness></u:SetLoudness>'

        response = self.__send_command(SoCo.RENDERING_ENDPOINT, action, body)

        if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetLoudnessResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1"></u:SetLoudnessResponse></s:Body></s:Envelope>'):
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
                Slave = SoCo(ip)
                ret = Slave.join(master_speaker_info["uid"])
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
        action = '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"'

        body = '<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><CurrentURI>x-rincon:' + master_uid + '</CurrentURI><CurrentURIMetaData></CurrentURIMetaData></u:SetAVTransportURI>'        
        
        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)

        if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetAVTransportURIResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:SetAVTransportURIResponse></s:Body></s:Envelope>'):
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
        action = '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"'

        speaker_info = self.get_speaker_info()

        body = '<u:SetAVTransportURI xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><CurrentURI>x-rincon-stream:' + speaker_info['uid'] + '</CurrentURI><CurrentURIMetaData></CurrentURIMetaData></u:SetAVTransportURI>'

        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)

        if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetAVTransportURIResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"></u:SetAVTransportURIResponse></s:Body></s:Envelope>'):
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
        if led_on is True:
            led_state = 'On'
        else:
            led_state = 'Off'

        action = '"urn:schemas-upnp-org:service:DeviceProperties:1#SetLEDState"'

        body = '<u:SetLEDState xmlns:u="urn:schemas-upnp-org:service:DeviceProperties:1"><DesiredLEDState>' + led_state + '</DesiredLEDState>'

        response = self.__send_command(SoCo.DEVICE_ENDPOINT, action, body)

        if (response == '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:SetLEDStateResponse xmlns:u="urn:schemas-upnp-org:service:DeviceProperties:1"></u:SetLEDStateResponse></s:Body></s:Envelope>'):
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
        action = '"urn:schemas-upnp-org:service:AVTransport:1#GetPositionInfo"'

        body = '<u:GetPositionInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"><InstanceID>0</InstanceID><Channel>Master</Channel></u:GetPositionInfo>'

        response = self.__send_command(SoCo.TRANSPORT_ENDPOINT, action, body)

        dom = XML.fromstring(response)

        track = {}

        track['playlist_position'] = dom.findtext('.//Track')
        track['duration'] = dom.findtext('.//TrackDuration')
        track['uri'] = dom.findtext('.//TrackURI')

        d = dom.findtext('.//TrackMetaData')

        # If the speaker is playing from the line-in source, querying for track
        # metadata will return "NOT_IMPLEMENTED".
        if d is not '' or d is not 'NOT_IMPLEMENTED':
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

        if self.speakers_ip and refresh is False:
            return self.speakers_ip
        else:
            response = requests.get('http://' + self.speaker_ip + ':1400/status/topology')
            text = response.text
            grp = re.findall(r'(\d+\.\d+\.\d+\.\d+):1400', text)

            for i in grp:
                response = requests.get('http://' + i + ':1400/status')

                if response.status_code == 200:
                    (self.speakers_ip).append(i)

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
            dom = XML.fromstring(response)
            resultText = dom.findtext('.//Result')
            if not resultText: return queue
            
            resultDom  = XML.fromstring(resultText)
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

    def __send_command(self, endpoint, action, body):
        """ Send a raw command to the Sonos speaker.

        Returns:
        The raw response body returned by the Sonos speaker.

        """
        headers = {
            'Content-Type': 'text/xml',
            'SOAPACTION': action
        }

        soap = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>' + body + '</s:Body></s:Envelope>'

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
