# -*- coding: utf-8 -*-
# pylint: disable=R0913,W0142

""" Spotify Plugin """

import requests

from ..xml import XML
from ..compat import quote_plus
from . import SoCoPlugin


__all__ = ['Spotify']


class SpotifyTrack(object):

    """ Class that represents a Spotify track

    usage example: SpotifyTrack('spotify:track:20DfkHC5grnKNJCzZQB6KC') """

    def __init__(self, spotify_uri):
        self.data = {}
        self.data['spotify_uri'] = spotify_uri

    @property
    def spotify_uri(self):
        """ The track's Spotify URI """
        return self.data['spotify_uri']

    @spotify_uri.setter
    def spotify_uri(self, uri):
        """ Set the track's Spotify URI """
        self.data['spotify_uri'] = uri

    @property
    def album_uri(self):
        """ The album's URI """
        return self.data['album_uri']

    @album_uri.setter
    def album_uri(self, uri):
        """ Set the album's URI """
        self.data['album_uri'] = uri

    @property
    def title(self):
        """ The track's title """
        return self.data['title']

    @title.setter
    def title(self, title):
        """ Set the track's title """
        self.data['title'] = title.encode('utf-8')

    @property
    def didl_metadata(self):
        """ DIDL Metadata """
        if ('spotify_uri' in self.data and 'title' in self.data and
                'album_uri' in self.data):

            didl_metadata = """\
<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"
           xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
           xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"
           xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
    <item id="{0}" parentID="{1}" restricted="true">
        <dc:title>{2}</dc:title>
        <upnp:class>object.item.audioItem.musicTrack</upnp:class>
        <desc id="cdudn"
            nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">
            SA_RINCON2311_X_#Svc2311-0-Token
        </desc>
    </item>
</DIDL-Lite>""".format(quote_plus(self.data['spotify_uri']),
                       quote_plus(self.data['album_uri']),
                       quote_plus(self.data['title']))
            didl_metadata = didl_metadata.encode('utf-8')
            return XML.fromstring(didl_metadata)
        else:
            return None

    @property
    def uri(self):
        """ Sonos-Spotify URI """
        if 'spotify_uri' in self.data:
            track = self.data['spotify_uri']
            track = track.encode('utf-8')
            track = quote_plus(track)
            return 'x-sonos-spotify:' + track
        else:
            return ''

    def satisfied(self):
        """ Checks if necessary track data is available """
        return 'title' in self.data and 'didl_metadata' in self.data


class SpotifyAlbum(object):

    """ Class that represents a Spotifyalbum

    usage example: SpotifyAlbum('spotify:album:6a50SaJpvdWDp13t0wUcPU') """

    def __init__(self, spotify_uri):
        self.data = {}
        self.data['spotify_uri'] = spotify_uri

    @property
    def spotify_uri(self):
        """ The album's Spotify URI """
        return self.data['spotify_uri']

    @spotify_uri.setter
    def spotify_uri(self, uri):
        """ Set the album's Spotify URI """
        self.data['spotify_uri'] = uri

    @property
    def artist_uri(self):
        """ The artist's URI """
        return self.data['artist_uri']

    @artist_uri.setter
    def artist_uri(self, artist_uri):
        """ Set the artist's URI """
        self.data['artist_uri'] = artist_uri

    @property
    def title(self):
        """ The album's title """
        return self.data['title']

    @title.setter
    def title(self, title):
        """ Set the album's title """
        self.data['title'] = title.encode('utf-8')

    @property
    def uri(self):
        """ Sonos-Spotify URI """
        if 'spotify_uri' in self.data:
            album = self.data['spotify_uri']
            album = album.encode('utf-8')
            album = quote_plus(album)
            return "x-rincon-cpcontainer:" + album
        else:
            return ""

    @property
    def didl_metadata(self):
        """ DIDL Metadata """
        if self.satisfied:
            didl_metadata = """\
<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"
           xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
           xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"
           xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
    <item id="{0}" parentID="{1}" restricted="true">
        <dc:title>{2}</dc:title>
        <upnp:class>object.container.album.musicAlbum</upnp:class>
        <desc id="cdudn"
              nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">
            SA_RINCON2311_X_#Svc2311-0-Token
        </desc>
    </item>
</DIDL-Lite>""".format(quote_plus(self.data['spotify_uri']),
                       quote_plus(self.data['artist_uri']),
                       quote_plus(self.data['title']))
            didl_metadata = didl_metadata.encode('utf-8')
            return XML.fromstring(didl_metadata)
        else:
            return None

    def satisfied(self):
        """ Checks if necessary album data is available """
        return ('spotify_uri' in self.data and
                'artist' in self.data and
                'title' in self.data)


class Spotify(SoCoPlugin):

    """ Class that implements spotify plugin"""

    sid = '9'
    api_lookup_url = 'http://ws.spotify.com/lookup/1/.json'

    def __init__(self, soco):
        """ Initialize the plugin"""
        super(Spotify, self).__init__(soco)

    @property
    def name(self):
        return 'Spotify plugin'

    def _add_track_metadata(self, spotify_track):
        """ Adds metadata by using the spotify public API """
        track = SpotifyTrack(spotify_track.spotify_uri)
        params = {'uri': spotify_track.spotify_uri}
        res = requests.get(self.api_lookup_url, params=params)
        data = res.json()

        if 'track' in data:
            track.title = data['track']['name']
            track.album_uri = data['track']['album']['href']

        return track

    def _add_album_metadata(self, spotify_album):
        """ Adds metadata by using the spotify public API """
        album = SpotifyAlbum(spotify_album.spotify_uri)
        params = {'uri': spotify_album.spotify_uri}
        res = requests.get(self.api_lookup_url, params=params)
        data = res.json()

        if 'album' in data:
            album.title = data['album']['name']
            album.artist_uri = data['album']['artist-id']

        return album

    def add_track_to_queue(self, spotify_track):
        """ Add a spotify track to the queue using the SpotifyTrack class"""
        if not spotify_track.satisfied():
            spotify_track = self._add_track_metadata(spotify_track)

        return self.soco.add_to_queue(spotify_track)

    def add_album_to_queue(self, spotify_album):
        """ Add a spotify album to the queue using the SpotifyAlbum class """
        if not spotify_album.satisfied():
            spotify_album = self._add_album_metadata(spotify_album)

        return self.soco.add_to_queue(spotify_album)
