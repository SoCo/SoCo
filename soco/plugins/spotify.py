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
from .__init__ import SoCoPlugin


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
		 		<item id=\"""" + urllib.quote_plus(self.data['spotify_uri']) + """\" parentID=\"""" + urllib.quote_plus(self.data['album_uri']) +  """\" restricted="true">
		 			<dc:title>""" + urllib.quote_plus(self.data['title']) + """</dc:title>
		 			<upnp:class>object.item.audioItem.musicTrack</upnp:class>
		 			<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">SA_RINCON2311_X_#Svc2311-0-Token</desc>
		 		</item>
		 	</DIDL-Lite>"""
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


class Spotify(SoCoPlugin):

	sid = '9'
	api_lookup_url = 'http://ws.spotify.com/lookup/1/.json'
	api_search_track_url = 'http://ws.spotify.com/search/1/track.json'

	def __init__(self, soco):
		""" Initialize the plugin"""
		super(Spotify, self).__init__(soco)


	@property
	def name(self):
		return 'Spotify plugin'

	def _add_metadata(self, spotify_track):
		retTrack = SpotifyTrack(spotify_track.spotify_uri)
		params = {'uri': spotify_track.spotify_uri}
		res = requests.get(self.api_lookup_url, params=params)
		data = res.json()

		if 'track' in data:
			retTrack.title = data['track']['name']
			retTrack.album_uri = data['track']['album']['href']

		return retTrack

	def add_to_queue(self, spotify_track):
		if not spotify_track.satisfied():
			spotify_track = self._add_metadata(spotify_track)

		index = -1
		try:
			index = self.soco.add_to_queue(spotify_track)
		except SoCoUPnPException:
			print "Couldn't add song.."

		return index

	def get_spotify_top_tracks(artist, max):
		retList = []

		params = {'q': 'artist:' + artist}
		res = requests.get(api_url, params=params)

		if 'tracks' in data:
			i = 0
			data = res.json()
			for d in data['tracks']:
				t = SpotifyTrack(d['href'])
				t.title = d['name']
				t.album_uri = d['album']['href']

				retList.append(t)
				i = i + 1
				if i >= max: 
					break

		return retList
