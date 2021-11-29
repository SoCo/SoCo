"""This plugin supports playback from a linked Plex music service.
See: https://support.plex.tv/articles/218168898-installing-plex-for-sonos/

Requires:
    * Plex music service must be linked in the Sonos app
    * Use of 'plexapi' library (https://github.com/pkkid/python-plexapi)
    * Plex server URI used in 'plexapi' must be reachable from Sonos speakers

    Example usage:

        >>> from plexapi.server import PlexServer
        >>> from soco import SoCo
        >>> from soco.plugins.plex import PlexPlugin
        >>>
        >>> s = SoCo("<SPEAKER_IP>")
        >>> plugin = PlexPlugin(s)
        >>>
        >>> plex_uri = "http://1.2.3.4:32400"
        >>> plex_token = "<YOUR_PLEX_TOKEN>"
        >>> plex = PlexServer(plex_uri, token=plex_token)
        >>> music = plex.library.section("Music")
        >>> artist = music.get("Stevie Wonder")
        >>> album = artist.album("Innervisions")
        >>> track = album.tracks()[4]
        >>> playlist = plex.playlist("My Playlist")
        >>>
        >>> plugin.play_now(track)    # Play a single track
        >>> plugin.play_now(album)    # Play a complete album
        >>> plugin.play_now(artist)   # Play all music from an artist
        >>> plugin.play_now(playlist) # Play an existing playlist
"""

from urllib.parse import quote

from ..core import to_didl_string
from ..data_structures import (
    DidlMusicAlbum,
    DidlMusicArtist,
    DidlMusicTrack,
    DidlPlaylistContainer,
)
from ..exceptions import SoCoException
from ..music_services import MusicService
from ..plugins import SoCoPlugin


PREFIX_LOOKUP = {
    "album": "1004206c",
    "artist": "1005004c",
    "playlist": "1006206c",
    "track": "10036020",
    "albums:directory": "100d2066",
    "artists:directory": "10fe2066",
    "playlists:directory": "10fe2064",
}

PARENT_TYPE = {
    "album": "artist",
    "artist": "artists:directory",
    "playlist": "playlists:directory",
    "track": "album",
}

CLASS_MAPPING = {
    "album": DidlMusicAlbum,
    "artist": DidlMusicArtist,
    "playlist": DidlPlaylistContainer,
    "track": DidlMusicTrack,
}


class PlexPlugin(SoCoPlugin):
    """A SoCo plugin for playing Plex media using the plexapi library."""

    def __init__(self, soco):
        """Initialize the plugin."""
        super().__init__(soco)
        self._service_info = None

    @property
    def name(self):
        """Return the name of the plugin."""
        return "Plex Plugin"

    @property
    def service_name(self):
        """Return the service name of the Plex music service."""
        return "Plex"

    @property
    def service_info(self):
        """Cache and return the service info of the Plex music service."""
        if not self._service_info:
            self._service_info = MusicService.get_data_for_name(self.service_name)
        return self._service_info

    @property
    def service_id(self):
        """Return the service ID of the Plex music service."""
        return self.service_info["ServiceID"]

    @property
    def service_type(self):
        """Return the service type of the Plex music service."""
        return self.service_info["ServiceType"]

    def play_now(self, plex_media):
        """Insert the media next in the queue and immediately begin playback."""
        position = self.add_to_queue(plex_media, add_next=True)
        position -= 1
        self.soco.play_from_queue(position)

    def add_to_queue(
        self, plex_media, add_next=False
    ):  # pylint: disable=too-many-locals
        """Add the provided media to the speaker's playback queue.

        Args:
            plex_media (plexapi): The plexapi object representing the Plex media
                to be enqueued. Can be one of plexapi.audio.Track,
                plexapi.audio.Album, plexapi.audio.Artist or
                plexapi.playlist.Playlist.
            add_next (bool): True if media should be enqueued after the
                currently selected track, False to add to the end of the queue.

        Returns:
            int: The index of the new item in the queue.
        """
        plex_server = plex_media._server  # pylint: disable=protected-access
        try:
            base_id = "{}:{}".format(
                plex_server.machineIdentifier, plex_media.librarySectionID
            )
        except AttributeError:
            base_id = "{}:".format(plex_server.machineIdentifier)

        item_type = plex_media.TYPE
        parent_type = PARENT_TYPE[item_type]
        didl_class = CLASS_MAPPING[item_type]
        item_uri = "{}:{}:{}".format(base_id, plex_media.ratingKey, item_type)
        desc = "SA_RINCON{st}_X_#Svc{st}-0-Token".format(st=self.service_type)

        if item_type == "track":
            parent_uri = "{}:{}:{}".format(
                base_id, plex_media.album().ratingKey, parent_type
            )
        elif item_type == "album":
            parent_uri = "{}:{}:{}".format(
                base_id, plex_media.artist().ratingKey, parent_type
            )
        elif item_type == "artist":
            parent_uri = "{}:{}".format(
                "00020000artist", plex_media.title.split(" ")[0]
            )
        elif item_type == "playlist":
            if not plex_media.isAudio:
                raise SoCoException("Non-audio playlists are not supported")
            parent_uri = "{}:{}".format(base_id, parent_type)

        item_didl = didl_class(
            plex_media.title,
            PREFIX_LOOKUP[parent_type] + quote(parent_uri),
            PREFIX_LOOKUP[item_type] + quote(item_uri),
            desc=desc,
        )

        desired_first_track = 0
        enqueue_as_next = 0

        if add_next:
            current_track_info = self.soco.get_current_track_info()
            current_position = int(current_track_info["playlist_position"])
            desired_first_track = current_position + 1
            enqueue_as_next = 1

        metadata = to_didl_string(item_didl)
        enqueued_uri = "x-rincon-cpcontainer:{}?sid={}&flags=8300&sn=9".format(
            item_didl.item_id, self.service_id
        )
        response = self.soco.avTransport.AddURIToQueue(
            [
                ("InstanceID", 0),
                ("EnqueuedURI", enqueued_uri),
                ("EnqueuedURIMetaData", metadata),
                ("DesiredFirstTrackNumberEnqueued", desired_first_track),
                ("EnqueueAsNext", enqueue_as_next),
            ]
        )
        qnumber = response["FirstTrackNumberEnqueued"]
        return int(qnumber)
