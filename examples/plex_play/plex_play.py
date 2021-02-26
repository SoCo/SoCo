""" Example on how to play music from a connected Plex media server.

Requires the Plex service to be linked to the Sonos system.

Depends on use of the `plexapi` library to gather internal Plex metadata.
"""


from urllib.parse import quote
import xml.etree.ElementTree as XML

from plexapi.server import PlexServer
from soco import SoCo
from soco.data_structures import DidlMusicAlbumTitleSummary
from soco.services import Queue

SONOS_IP = '<SONOS_SPEAKER_IP>'

# START `plexapi` specific code
baseurl = 'http://<PLEX_SERVER_IP>:32400'
token = '<PLEX_TOKEN>'

plex_server = PlexServer(baseurl, token)
plex_track = plex_server.library.section('Music').get('Stevie Wonder').album('Innervisions').track('Higher Ground')
plex_album = plex_track.album()
plex_artist = plex_track.artist()

base_id = f'{plex_server.machineIdentifier}:{plex_track.librarySectionID}'
item_id = quote(f'1004206c{base_id}:{plex_album.ratingKey}:album')
parent_id = quote(f'1005206c{base_id}:{plex_artist.ratingKey}:artist')

album_title = plex_album.title
album_art_uri = plex_album.artUrl
artist_title = plex_artist.title
track_index = plex_track.index
# END `plexapi` specific code

didl_dict = {
    'title': album_title,
    'parent_id': parent_id,
    'item_id': item_id,
    'album': album_title,
    'album_art_uri': album_art_uri,
    'creator': artist_title,
    'description': artist_title,
}
album_didl = DidlMusicAlbumTitleSummary(**didl_dict, desc="SA_RINCON54279_X_#Svc54279-0-Token")

br = SoCo(SONOS_IP)
q = Queue(br)

URIs = XML.Element("URIs")
URI = XML.SubElement(URIs, "URI", {"uri": f"x-rincon-cpcontainer:{item_id}?sid=212&flags=8300&sn=9"})
didl = XML.SubElement(
    URI,
    "DIDL-Lite",
    {
        "xmlns": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
        "xmlns:dc": "http://purl.org/dc/elements/1.1/",
        "xmlns:upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/",
        "xmlns:r": "urn:schemas-rinconnetworks-com:metadata-1-0/",
    },
)

didl.append(album_didl.to_element())

uris_and_metadata = XML.tostring(URIs, encoding="unicode")

action = "ReplaceAllTracks"
args = [
    ("QueueID", 0),
    ("UpdateID", 0),
    ("ContainerURI", ""),
    ("ContainerMetaData", ""),
    ("CurrentTrackIndex", 0),
    ("NewCurrentTrackIndices", track_index),
    ("NumberOfURIs", 1),
    ("EnqueuedURIsAndMetaData", uris_and_metadata),
]

q.send_command(action, args)
br.play_from_queue(int(track_index)-1)
