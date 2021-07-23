# Disable while we have Python 2.x compatability
# pylint: disable=useless-object-inheritance, too-many-arguments

"""Data structures for music service items

The basis for this implementation is this page in the Sonos API
documentation: http://musicpartners.sonos.com/node/83

A note about naming. The Sonos API uses camel case with starting lower
case. These names have been adapted to match general Python class
naming conventions.

MediaMetadata:
    Track
    Stream
    Show
    Other

MediaCollection:
    Artist
    Album
    Genre
    Playlist
    Search
    Program
    Favorites
    Favorite
    Collection
    Container
    AlbumList
    TrackList
    StreamList
    ArtistTrackList
    Other

NOTE: "Other" is allowed under both.

Class overview:

+----------------+   +----------------+   +---------------+
|MetadataDictBase+-->+MusicServiceItem+-->+MediaCollection|
+-----+----------+   +--------+-------+   +---------------+
      |                       |
      |                       |     +------------------+
      |                       +---->+  MediaMetadata   |
      |                             |                  |
      |                             | +-------------+  |
      +------------------------------>+TrackMetadata|  |
      |                             | +-------------+  |
      |                             |                  |
      |                             | +--------------+ |
      +------------------------------>+StreamMetadata| |
                                    | +--------------+ |
                                    |                  |
                                    +------------------+


"""
from urllib.parse import quote as quote_url

import logging
from collections import OrderedDict
from ..data_structures import DidlResource, DidlItem, SearchResult
from ..utils import camel_to_underscore


_LOG = logging.getLogger(__name__)
_LOG.addHandler(logging.NullHandler())


# For now we generate classes dynamically. This is shorter, but
# provides no custom documentation for all the different types.
CLASSES = {}


def get_class(class_key):
    """Form a music service data structure class from the class key

    Args:
        class_key (str): A concatenation of the base class (e.g. MediaMetadata)
            and the class name

    Returns:
        class: Subclass of MusicServiceItem
    """
    if class_key not in CLASSES:
        for basecls in (MediaMetadata, MediaCollection):
            if class_key.startswith(basecls.__name__):
                # So MediaMetadataTrack turns into MSTrack
                class_name = "MS" + class_key.replace(basecls.__name__, "")
                CLASSES[class_key] = type(class_name, (basecls,), {})
                _LOG.debug("Class %s created", CLASSES[class_key])
    return CLASSES[class_key]


def parse_response(service, response, search_type):
    """Parse the response to a music service query and return a SearchResult

    Args:
        service (MusicService): The music service that produced the response
        response (OrderedDict): The response from the soap client call
        search_type (str): A string that indicates the search type that the
            response is from

    Returns:
        SearchResult: A SearchResult object
    """
    _LOG.debug(
        'Parse response "%s" from service "%s" of type "%s"',
        response,
        service,
        search_type,
    )
    items = []
    # The result to be parsed is in either searchResult or getMetadataResult
    if "searchResult" in response:
        response = response["searchResult"]
    elif "getMetadataResult" in response:
        response = response["getMetadataResult"]
    else:
        raise ValueError(
            '"response" should contain either the key '
            '"searchResult" or "getMetadataResult"'
        )

    # Form the search metadata
    search_metadata = {
        "number_returned": response["count"],
        "total_matches": None,
        "search_type": search_type,
        "update_id": None,
    }

    for result_type in ("mediaCollection", "mediaMetadata"):
        # Upper case the first letter (used for the class_key)
        result_type_proper = result_type[0].upper() + result_type[1:]
        raw_items = response.get(result_type, [])
        # If there is only 1 result, it is not put in an array
        if isinstance(raw_items, OrderedDict):
            raw_items = [raw_items]

        for raw_item in raw_items:
            # Form the class_key, which is a unique string for this type,
            # formed by concatenating the result type with the item type. Turns
            # into e.g: MediaMetadataTrack
            class_key = result_type_proper + raw_item["itemType"].title()
            cls = get_class(class_key)
            items.append(cls.from_music_service(service, raw_item))
    return SearchResult(items, **search_metadata)


def form_uri(item_id, service, is_track):
    """Form and return a music service item uri

    Args:
        item_id (str): The item id
        service (MusicService): The music service that the item originates from
        is_track (bool): Whether the item_id is from a track or not

    Returns:
        str: The music service item uri
    """
    if is_track:
        uri = service.sonos_uri_from_id(item_id)
    else:
        uri = "x-rincon-cpcontainer:" + item_id
    return uri


# Type Helper
BOOL_STRS = {"true", "false"}


def bool_str(string):
    """Returns a boolean from a string imput of 'true' or 'false'"""
    if string not in BOOL_STRS:
        raise ValueError('Invalid boolean string: "{}"'.format(string))
    return string == "true"


# Music Service item base classes
class MetadataDictBase:
    """Class used to parse metadata from kwargs"""

    # The following two fields should be overwritten in subclasses

    # _valid_fields is a set of valid fields
    _valid_fields = {}

    # _types is a dict of fields with non-string types and their convertion
    # callables
    _types = {}

    def __init__(self, metadata_dict):
        """Initialize local variables"""
        _LOG.debug("MetadataDictBase.__init__ with: %s", metadata_dict)
        for key in metadata_dict:
            # Check for invalid fields
            if key not in self._valid_fields:
                message = '%s instantiated with invalid field "%s" and value: "%s"'
                # Really wanted to raise exceptions here, but as it
                # turns out I have already encountered invalid fields
                # from music services.
                _LOG.debug(message, self.__class__, key, metadata_dict[key])

        # Convert names and create metadata dict
        self.metadata = {}
        for key, value in metadata_dict.items():
            if key in self._types:
                convertion_callable = self._types[key]
                value = convertion_callable(value)
            self.metadata[camel_to_underscore(key)] = value

    def __getattr__(self, key):
        """Return item from metadata in case of unknown attribute"""
        try:
            return self.metadata[key]
        except KeyError as error:
            message = 'Class {} has no attribute "{}"'
            raise AttributeError(
                message.format(self.__class__.__name__, key)
            ) from error


class MusicServiceItem(MetadataDictBase):
    """A base class for all music service items"""

    # See comment in MetadataDictBase for explanation of these two attributes
    _valid_fields = {}
    _types = {}

    def __init__(
        self,
        item_id,
        desc,  # pylint: disable=too-many-arguments
        resources,
        uri,
        metadata_dict,
        music_service=None,
    ):
        """Init music service item

        Args:
            item_id (str): This is the Didl compatible id NOT the music item id
            desc (str): A DIDL descriptor, default ``'RINCON_AssociatedZPUDN'
            resources (list): List of DidlResource
            uri (str): The uri for the location of the item
            metdata_dict (dict): Mapping of metadata
            music_service (MusicService): The MusicService instance the item
                originates from
        """
        _LOG.debug(
            "%s.__init__ with item_id=%s, desc=%s, resources=%s, "
            "uri=%s, metadata_dict=..., music_service=%s",
            self.__class__.__name__,
            item_id,
            desc,
            resources,
            uri,
            music_service,
        )
        super().__init__(metadata_dict)
        self.item_id = item_id
        self.desc = desc
        self.resources = resources
        self.uri = uri
        self.music_service = music_service

    @classmethod
    def from_music_service(cls, music_service, content_dict):
        """Return an element instantiated from the information that a music
        service has (alternative constructor)

        Args:
            music_service (MusicService): The music service that content_dict
                originated from
            content_dict (OrderedDict): The data to instantiate the music
                service item from

        Returns:
            MusicServiceItem: A MusicServiceItem instance
        """
        # Form the item_id
        quoted_id = quote_url(content_dict["id"].encode("utf-8"))
        # The hex prefix remains a mistery for now
        item_id = "0fffffff{}".format(quoted_id)
        # Form the uri
        is_track = cls == get_class("MediaMetadataTrack")
        uri = form_uri(item_id, music_service, is_track)
        # Form resources and get desc
        resources = [DidlResource(uri=uri, protocol_info="DUMMY")]
        desc = music_service.desc
        return cls(
            item_id, desc, resources, uri, content_dict, music_service=music_service
        )

    def __str__(self):
        """Return custom string representation"""
        title = self.metadata.get("title")
        str_ = '<{} title="{}">'
        return str_.format(self.__class__.__name__, title)

    def to_element(self, include_namespaces=False):
        """Return an ElementTree Element representing this instance.

        Args:
            include_namespaces (bool, optional): If True, include xml
                namespace attributes on the root element

        Return:
            ~xml.etree.ElementTree.Element: The (XML) Element representation of
                this object
        """
        # We piggy back on the implementation in DidlItem
        didl_item = DidlItem(
            title="DUMMY",
            # This is ignored. Sonos gets the title from the item_id
            parent_id="DUMMY",  # Ditto
            item_id=self.item_id,
            desc=self.desc,
            resources=self.resources,
        )
        return didl_item.to_element(include_namespaces=include_namespaces)


class TrackMetadata(MetadataDictBase):
    """Track metadata class"""

    # _valid_fields is a set of valid fields
    _valid_fields = {
        "artistId",
        "artist",
        "composerId",
        "composer",
        "albumId",
        "album",
        "albumArtURI",
        "albumArtistId",
        "albumArtist",
        "genreId",
        "genre",
        "duration",
        "canPlay",
        "canSkip",
        "canAddToFavorites",
        "rating",
        "trackNumber",
        "isFavorite",
    }
    # _types is a dict of fields with non-string types and their
    # convertion callables
    _types = {
        "duration": int,
        "canPlay": bool_str,
        "canSkip": bool_str,
        "canAddToFavorites": bool_str,
        "rating": int,
        "trackNumber": int,
        "isFavorite": bool_str,
    }


class StreamMetadata(MetadataDictBase):
    """Stream metadata class"""

    # _valid_fields is a set of valid fields
    _valid_fields = {
        "currentHost",
        "currentShowId",
        "currentShow",
        "secondsRemaining",
        "secondsToNextShow",
        "bitrate",
        "logo",
        "hasOutOfBandMetadata",
        "description",
        "isEphemeral",
    }
    # _types is a dict of fields with non-string types and their
    # convertion callables
    _types = {
        "secondsRemaining": int,
        "secondsToNextShow": int,
        "bitrate": int,
        "hasOutOfBandMetadata": bool_str,
        "isEphemeral": bool_str,
    }


class MediaMetadata(MusicServiceItem):
    """Base class for all media metadata items"""

    # _valid_fields is a set of valid fields
    _valid_fields = {
        "id",
        "title",
        "mimeType",
        "itemType",
        "displayType",
        "summary",
        "trackMetadata",
        "streamMetadata",
        "dynamic",
    }
    # _types is a dict of fields with non-string types and their
    # convertion callables
    _types = {
        "trackMetadata": TrackMetadata,
        "streamMetadata": StreamMetadata,
        # We ignore types on the dynamic field
        # 'dynamic': ???,
    }


class MediaCollection(MusicServiceItem):
    """Base class for all mediaCollection items"""

    # _valid_fields is a set of valid fields
    _valid_fields = {
        "id",
        "title",
        "itemType",
        "displayType",
        "summary",
        "artistId",
        "artist",
        "albumArtURI",
        "canPlay",
        "canEnumerate",
        "canAddToFavorites",
        "containsFavorite",
        "canScroll",
        "canSkip",
        "isFavorite",
    }

    # _types is a dict of fields with non-string types and their
    # convertion callables
    _types = {
        "canPlay": bool_str,
        "canEnumerate": bool_str,
        "canAddToFavorites": bool_str,
        "containsFavorite": bool_str,
        "canScroll": bool_str,
        "canSkip": bool_str,
        "isFavorite": bool_str,
    }
