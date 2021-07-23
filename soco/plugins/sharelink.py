"""ShareLink Plugin."""

import re

from ..plugins import SoCoPlugin
from ..exceptions import SoCoException


class ShareClass:
    """Base class for supported services."""

    def canonical_uri(self, uri):
        """Recognize a share link and return its canonical representation.

        Args:
            uri (str): A URI like "https://tidal.com/browse/album/157273956".

        Returns:
            str: The canonical URI or None if not recognized.
        """
        raise NotImplementedError

    def service_number(self):
        """Return the service number.

        Returns:
            int: A number identifying the supported music service.
        """
        raise NotImplementedError

    @staticmethod
    def magic():
        """Return magic.

        Returns:
            dict: Magic prefix/key/class values for each share type.
        """
        return {
            "album": {
                "prefix": "x-rincon-cpcontainer:1004206c",
                "key": "00040000",
                "class": "object.container.album.musicAlbum",
            },
            "track": {
                "prefix": "",
                "key": "00032020",
                "class": "object.item.audioItem.musicTrack",
            },
            "playlist": {
                "prefix": "x-rincon-cpcontainer:1006206c",
                "key": "1006206c",
                "class": "object.container.playlistContainer",
            },
        }

    def extract(self, uri):
        """Extract the share type and encoded URI from a share link.

        Returns:
            share_type: The shared type, like "album" or "track".
            encoded_uri: An escaped URI with a service-specific format.
        """
        raise NotImplementedError


class SpotifyShare(ShareClass):
    """Spotify share class."""

    def canonical_uri(self, uri):
        match = re.search(r"spotify.*[:/](album|track|playlist)[:/](\w+)", uri)
        if match:
            return "spotify:" + match.group(1) + ":" + match.group(2)

        return None

    def service_number(self):
        return 2311

    def extract(self, uri):
        spotify_uri = self.canonical_uri(uri)
        share_type = spotify_uri.split(":")[1]
        encoded_uri = spotify_uri.replace(":", "%3a")
        return (share_type, encoded_uri)


class SpotifyUSShare(SpotifyShare):
    """Spotify US share class."""

    def service_number(self):
        return 3079


class TIDALShare(ShareClass):
    """TIDAL share class."""

    def canonical_uri(self, uri):
        match = re.search(r"https://tidal.*[:/](album|track|playlist)[:/]([\w-]+)", uri)
        if match:
            return "tidal:" + match.group(1) + ":" + match.group(2)

        return None

    def service_number(self):
        return 44551

    def extract(self, uri):
        tidal_uri = self.canonical_uri(uri)
        share_type = tidal_uri.split(":")[1]
        encoded_uri = tidal_uri.replace("tidal:", "").replace(":", "%2f")
        return (share_type, encoded_uri)


class ShareLinkPlugin(SoCoPlugin):
    """A SoCo plugin for playing Spotify/Tidal share links."""

    def __init__(self, soco):
        """Initialize the plugin."""
        super().__init__(soco)
        self.services = [
            SpotifyShare(),
            SpotifyUSShare(),
            TIDALShare(),
        ]

    @property
    def name(self):
        return "ShareLink Plugin"

    def is_share_link(self, uri):
        """bool: Is the URI for a supported music service."""
        for service in self.services:
            if service.canonical_uri(uri):
                return True

        return False

    def add_share_link_to_queue(self, uri, position=0, as_next=False):
        """Add a Spotify/Tidal/... item to the queue.

        This is similar to soco.add_uri_to_queue() but will work with
        music service share links that do not directly point to sound
        files.

        Args:
            uri (str): A URI like "spotify:album:6wiUBliPe76YAVpNEdidpY".
            position (int): The index (1-based) at which the URI should be
                added. Default is 0 (add URI at the end of the queue).
            as_next (bool): Whether this URI should be played as the next
                track in shuffle mode. This only works if "play_mode=SHUFFLE".

        Returns:
            int: The index of the new item in the queue.
        """
        fault = SoCoException("Unsupported URI: " + uri)

        for service in self.services:
            if service.canonical_uri(uri):
                (share_type, encoded_uri) = service.extract(uri)
                magic = service.magic()

                enqueue_uri = magic[share_type]["prefix"] + encoded_uri

                metadata_template = (
                    '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements'
                    '/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata'
                    '-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-'
                    'com:metadata-1-0/" xmlns="urn:schemas-upnp-org:m'
                    'etadata-1-0/DIDL-Lite/"><item id="{item_id}" res'
                    'tricted="true"><upnp:class>{item_class}</upnp:cl'
                    'ass><desc id="cdudn" nameSpace="urn:schemas-rinc'
                    'onnetworks-com:metadata-1-0/">SA_RINCON{sn}_X_#S'
                    "vc{sn}-0-Token</desc></item></DIDL-Lite>"
                )

                metadata = metadata_template.format(
                    item_id=magic[share_type]["key"] + encoded_uri,
                    item_class=magic[share_type]["class"],
                    sn=service.service_number(),
                )

                try:
                    response = self.soco.avTransport.AddURIToQueue(
                        [
                            ("InstanceID", 0),
                            ("EnqueuedURI", enqueue_uri),
                            ("EnqueuedURIMetaData", metadata),
                            ("DesiredFirstTrackNumberEnqueued", position),
                            ("EnqueueAsNext", int(as_next)),
                        ]
                    )

                    qnumber = response["FirstTrackNumberEnqueued"]
                    return int(qnumber)
                except SoCoException as err:
                    # Try remaining services on failure but keep the exception
                    # around in case nothing succeeds.
                    fault = err

        raise fault
