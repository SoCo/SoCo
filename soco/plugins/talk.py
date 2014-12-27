import sys
import re
import urllib, urllib2
import time


from ..plugins import SoCoPlugin

__all__ = ['Talk']



class TalkerPlugin(SoCoPlugin):
    """
        The main use of this plugin is to make your Sonos system speak text.  It works by sending a request to the
        Google Text To Speech service, downloading an MP3 from the service, then playing the MP3 on the desired Sonos
        players.  It will pause and resume playback properly if you are listening to music at the time the message is
        sent.

        SETUP REQUIREMENTS:  You must add the path to the Google Text To Speech MP3 to your Sonos music library in order
        to obtain the URI for that file.  Once this is done, you can find the URI "get_music_library_information()"
        method in the soco package.
    """
    def __init__(self,soco,mp3Path,sonosURI,zoneNames=None,maxAttempts=5):
        """
        :param soco: soco instance per soco plugin instructions
        :param mp3Path: The path you wish for the TTS message to be saved.
        :param sonosURI: URI of mp3 file. This should point to the same file that exists at mp3Path
        :param zoneNames: List of Sonos player names you wish for your message to play on. i.e. ['Kitchen','Office'].
                          If nothing is passed, the message will play on all Sonos players.
        :param maxAttempts: Number of attempts to run soco.discover(). I found that regardless of the timeout passed to
                            soco.discover(), it may still fail, but multiple attempts usually works.
        :return: TalkerPlugin object

        """

        self.sonosURI = sonosURI
        self.mp3Path = mp3Path

        discovered = None
        iter=0
        while discovered is None and iter < maxAttempts:
            discovered = soco.discover(timeout=2)
            iter += 1

        zoneList = []
        nameList = []
        for zone in discovered:
            zoneList.append(zone)
            nameList.append(zone.player_name)

        if zoneNames:
            assert type(zoneNames) == list and all([zone in nameList for zone in zoneNames]), \
                'Speaker object must be instantiated with a list of existing zone names on your network'

        speakingSoCos = [zone for zone in zoneList if zone.player_name in zoneNames]

        self.masterSoCo = speakingSoCos[0]
        speakingSoCos.pop(0)
        self.slaveSoCos = speakingSoCos

        # if setup is True:
        #     self._setAudioDirectory()

        super(TalkerPlugin, self).__init__(soco)

    def talk(self,talkString='This is a test. Testing 1 2 3',volume=25):
        """
        :param talkString: String you wish your Sonos system to speak
        :param volume: Volume you wish for your Sonos system to speak at.  The volume will be set back to the previous
                       value after the message has been spoken
        :return: None
        """

        self._formGroup()

        tts = GoogleTTS()

        text_lines = tts.convertTextAsLinesOfText(talkString)


        tts.downloadAudioFile(text_lines,'en',open(self.mp3Path,'wb'))


        oldvolumes = [self.masterSoCo.volume]
        oldtracks = [self.masterSoCo.get_current_track_info()]
        oldqueues = [self.masterSoCo.get_queue()]
        oldStates = [self.masterSoCo.get_current_transport_info()]
        allSoCos = [self.masterSoCo]

        for SoCo in self.slaveSoCos:
            oldvolumes.append(SoCo.volume)
            oldtracks.append(SoCo.get_current_track_info())
            oldqueues.append(SoCo.get_queue())
            oldStates.append(SoCo.get_current_transport_info())
            allSoCos.append(SoCo)


        self.masterSoCo.volume = volume

        self.masterSoCo.play_uri(self.sonosURI,title=u'Python Talking Script')
        # self.masterSoCo.get_current_track_info()['duration']
        time.sleep(float(time.strptime(self.masterSoCo.get_current_track_info()['duration'],'%H:%M:%S').tm_sec))

        for ind,SoCo in enumerate(allSoCos):
            SoCo.volume=oldvolumes[ind]
            if oldStates[ind]['current_transport_state'] == 'PLAYING':
                SoCo.play_from_queue(int(oldtracks[ind]['playlist_position'])-1)
                SoCo.seek(oldtracks[ind]['position'])

        self._delGroup()


    def _formGroup(self):
        for SoCo in self.slaveSoCos:
            SoCo.join(self.masterSoCo)

    def _delGroup(self):
        for SoCo in self.slaveSoCos:
            SoCo.unjoin()






class GoogleTTS(object):
    """
        Taken from script at https://github.com/JulienD/Google-Text-To-Speech. No license info in repo.
    """
    def __init__(self):
        pass
    def convertTextAsLinesOfText(self,text):
        """ This convert a word, a short text, a long text into several parts to
            smaller than 100 characters.
        """

        # Sanitizes the text.
        text = text.replace('\n','')
        text_list = re.split('(\,|\.|\;|\:)', text)

        # Splits a text into chunks of texts.
        text_lines = []
        for idx, val in enumerate(text_list):

            if (idx % 2 == 0):
                text_lines.append(val)
            else :
                # Combines the string + the punctuation.
                joined_text = ''.join((text_lines.pop(),val))

                # Checks if the chunk need to be splitted again.
                if len(joined_text) < 100:
                    text_lines.append(joined_text)
                else:
                    subparts = re.split('( )', joined_text)
                    temp_string = ""
                    temp_array = []
                    for part in subparts:
                        temp_string = temp_string + part
                        if len(temp_string) > 80:
                            temp_array.append(temp_string)
                            temp_string = ""
                    #append final part
                    temp_array.append(temp_string)
                    text_lines.extend(temp_array)

        return text_lines

    def downloadAudioFile(self,text_lines, language, audio_file):
        """
            Donwloads a MP3 from Google Translatea mp3 based on a text and a
            language code.
        """
        for idx, line in enumerate(text_lines):
            query_params = {"tl": language, "q": line, "total": len(text_lines), "idx": idx}
            url = "http://translate.google.com/translate_tts?ie=UTF-8" + "&" + self.unicode_urlencode(query_params)
            headers = {"Host":"translate.google.com", "User-Agent":"Mozilla 5.10"}
            req = urllib2.Request(url, '', headers)
            sys.stdout.write('.')
            sys.stdout.flush()
            if len(line) > 0:
                try:
                    response = urllib2.urlopen(req)
                    audio_file.write(response.read())
                    time.sleep(.5)
                except urllib2.HTTPError as e:
                    print ('%s' % e)

        print 'Saved MP3 to %s' % (audio_file.name)
        audio_file.close()


    def unicode_urlencode(self,params):
        """
            Encodes params to be injected in an url.
        """
        if isinstance(params, dict):
            params = params.items()
        return urllib.urlencode([(k, isinstance(v, unicode) and v.encode('utf-8') or v) for k, v in params])


def testStuff():
    import soco
    talker = TalkerPlugin(soco,'/Users/Jeff/BitBucket/Personal/Python/SonosExperiments/AudioMessages/talkOutput.mp3',
                          'x-file-cifs://MACBOOKPRO-5A98/AudioMessages/talkOutput.mp3',['Office'])

    talker.talk(volume='75')

if __name__ == '__main__':
    testStuff()