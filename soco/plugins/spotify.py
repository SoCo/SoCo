 # -*- coding: utf-8 -*-
# pylint: disable=R0913,W0142

import requests, urllib
try:
    import xml.etree.cElementTree as XML
except ImportError:
    import xml.etree.ElementTree as XML

from ..services import MusicServices
from ..data_structures import get_ms_item
from ..exceptions import SoCoUPnPException
from . import SoCoPlugin


__all__ = ['Spotify']

class SpotifyTrack(object):
    def __init__(self, spotify_uri):
        self.data = {}
        self.data['spotify_uri'] = spotify_uri


    @property
    def spotify_uri(self):
        return self.data['spotify_uri']

    @spotify_uri.setter
    def spotify_uri(self, uri):
        self.data['spotify_uri'] = uri

    @property
    def album_uri(self):
        return self.data['album_uri']

    @album_uri.setter
    def album_uri(self, uri):
        self.data['album_uri'] = uri

    @property
    def title(self):
        return self.data['title']

    @title.setter
    def title(self, title):
        self.data['title'] = title

    @property
    def didl_metadata(self):
        if 'spotify_uri' in self.data and 'title' in self.data and 'album_uri' in self.data:
            didl_metadata = """<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
                <item id="{0}" parentID="{1}" restricted="true">
                    <dc:title>{2}</dc:title>
                    <upnp:class>object.item.audioItem.musicTrack</upnp:class>
                    <desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">SA_RINCON2311_X_#Svc2311-0-Token</desc>
                </item>
            </DIDL-Lite>""".format(urllib.quote_plus(self.data['spotify_uri']), urllib.quote_plus(self.data['album_uri']), urllib.quote_plus(self.data['title']))
            didl_metadata = didl_metadata.encode('utf-8')
            return XML.fromstring(didl_metadata)
        else:
            return None


    @property
    def uri(self):
        if 'spotify_uri' in self.data:
            t = self.data['spotify_uri']
            t = t.encode('utf-8')
            t = urllib.quote_plus(t)
            return 'x-sonos-spotify:' + t
        else:
            return ''


    def satisfied(self):
        return 'title' in self.data and 'didl_metadata' in self.data

class SpotifyAlbum(object):
    def __init__(self, spotify_uri):
        self.data = {}
        self.data['spotify_uri'] = spotify_uri


    @property
    def spotify_uri(self):
        return self.data['spotify_uri']

    @spotify_uri.setter
    def spotify_uri(self, uri):
        self.data['spotify_uri'] = uri

    @property
    def artist_uri(self):
        return self.data['artist_uri']

    @artist_uri.setter
    def artist_uri(self, artist_uri):
        self.data['artist_uri'] = artist_uri

    @property
    def title(self):
        return self.data['title']

    @title.setter
    def title(self, title):
        self.data['title'] = title

    @property
    def uri(self):
        if 'spotify_uri' in self.data:
            t = self.data['spotify_uri']
            t = t.encode('utf-8')
            t = urllib.quote_plus(t)
            return "x-rincon-cpcontainer:" + t
        else:
            return ""

    @property
    def didl_metadata(self):
        if self.satisfied:
            didl_metadata = """<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
                <item id="{0}" parentID="{1}" restricted="true">
                <dc:title>{2}</dc:title>
                <upnp:class>object.container.album.musicAlbum</upnp:class>
                <desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">SA_RINCON2311_X_#Svc2311-0-Token</desc></item></DIDL-Lite>
                """.format(urllib.quote_plus(self.data['spotify_uri']), urllib.quote_plus(self.data['artist_uri']), urllib.quote_plus(self.data['title']))
            didl_metadata = didl_metadata.encode('utf-8')
            return XML.fromstring(didl_metadata)
        else:
            return None

    def satisfied(self):
        return 'spotify_uri' in self.data and 'artist' in self.data and 'title' in self.data

class Spotify(SoCoPlugin):

    sid = '9'
    api_lookup_url = 'http://ws.spotify.com/lookup/1/.json'

    def __init__(self, soco):
        """ Initialize the plugin"""
        super(Spotify, self).__init__(soco)


    @property
    def name(self):
        return 'Spotify plugin'

    def _add_track_metadata(self, spotify_track):
        retTrack = SpotifyTrack(spotify_track.spotify_uri)
        params = {'uri': spotify_track.spotify_uri}
        res = requests.get(self.api_lookup_url, params=params)
        data = res.json()

        if 'track' in data:
            retTrack.title = data['track']['name']
            retTrack.album_uri = data['track']['album']['href']

        return retTrack

    def _add_album_metadata(self, spotify_album):
        retAlbum = SpotifyAlbum(spotify_album.spotify_uri)
        params = {'uri': spotify_album.spotify_uri}
        res = requests.get(self.api_lookup_url, params=params)
        data = res.json()

        if 'album' in data:
            retAlbum.title = data['album']['name']
            retAlbum.artist_uri = data['album']['artist-id']

        return retAlbum

    def add_track_to_queue(self, spotify_track):
        if not spotify_track.satisfied():
            spotify_track = self._add_track_metadata(spotify_track)

        return self.soco.add_to_queue(spotify_track)

    def add_album_to_queue(self, spotify_album):
        if not spotify_album.satisfied():
            spotify_album = self._add_album_metadata(spotify_album)

        return self.soco.add_to_queue(spotify_album)
