# -*- coding: utf-8 -*-
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

+----------+   +----------------+   +---------------+
|KwargsBase+-->+MusicServiceItem+-->+MediaCollection|
+-----+-----   +--------------+-+   +---------------+
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

from __future__ import print_function, absolute_import
from collections import OrderedDict
from ..data_structures import DidlResource, DidlItem, SearchResult
from ..utils import camel_to_underscore
from ..compat import quote_url
from ..xml import XML
from ..discovery import discover
from pprint import pprint


# For now we generate classes dynamically. This is shorter, but
# provides no custom documentation for all the different types.
CLASSES = {}
def get_class(class_key):
    """Form a class from the class key

    Args:
        class_key (str): A concatenation of the base class (e.g. MediaMetadata)
            and the class name

    Returns:
        MusicServiceItem
    """
    if class_key not in CLASSES:
        for basecls in (MediaMetadata, MediaCollection):
            if class_key.startswith(basecls.__name__):
                # So MediaMetadataTrack turns into MSTrack
                class_name = 'MS' + class_key.replace(basecls.__name__, '')
                CLASSES[class_key] = type(class_name, (basecls,), {})
    return CLASSES[class_key]


def parse_response(service, response, search_type):
    """Parse the query response"""
    items = []
    if 'searchResult' in response:
        response = response['searchResult']
    elif 'getMetadataResult' in response:
        response = response['getMetadataResult']
    search_metadata = {
        'number_returned': response['count'],
        'total_matches': None,
        'search_type': search_type,
        'update_id': None,
    }
    for result_type in ('mediaCollection', 'mediaMetadata'):
        result_type_proper = result_type[0].upper() + result_type[1:]
        raw_items = response.get(result_type, [])
        # If there is only 1 result, it is not put in an array
        if isinstance(raw_items, OrderedDict):
            raw_items = [raw_items]
        for raw_item in raw_items:
            class_key = result_type_proper + raw_item['itemType'].title()
            cls = get_class(class_key)
            items.append(cls.from_dict(service, raw_item))
    return SearchResult(items, **search_metadata)


### Type Helper
BOOL_STRS = {'true', 'false'}
def bool_str(string):
    """Returns a boolean from a string imput of 'true' or 'false'"""
    if string not in BOOL_STRS:
        raise ValueError('Invalid boolean string: "{}"'.format(string))
    return True if string == "true" else False


### Music Service item base classes
class KwargsBase(object):
    """Class used to parse metadata from kwargs"""

    # The following two fields should be overwritten in subclasses

    # _valid_fields is a set of valid fields
    _valid_fields = {}

    # _types is a dict of fields with non-string types and their
    # convertion callables
    _types = {}
    
    def __init__(self, **kwargs):
        """Initialize local variables"""
        # Check for invalid fields
        for key in kwargs:
            if key not in self._valid_fields:
                message = ('Field: "{0}" with value "{1}" is not valid for '
                           'class "{2}"')
                # Really wanted to raise exceptions here, but as it
                # turns out I have already encountered invalid fields
                # from music services. We should think about how to
                # handle those. Raising warnings will only annoy the
                # user. The easy thing is to just allow them in, and
                # ignore type conversion, so we only guaranty the
                # correct type for valid fields. Alternative, we might
                # also start to collect a list of invalid fields.
                #
                # For new we just print the warning message
                print(message.format(key, kwargs[key], self.__class__))
                #raise ValueError(message.format(key, kwargs[key], self.__class__))

        # Convert names and create metadata dict
        self.metadata = {}
        for key, value in kwargs.items():
            if key in self._types:
                convertion_callable = self._types[key] 
                value = convertion_callable(value)
            self.metadata[camel_to_underscore(key)] = value

    @classmethod
    def from_dict(cls, content_dict):
        """Init cls from a dict (alternative initializer)"""
        return cls(**content_dict)

    def __getattr__(self, key):
        """Return item from metadata in case of unknown attribute"""
        try:
            return self.metadata[key]
        except KeyError:
            message = 'Class {0} has no attribute "{1}"'
            raise AttributeError(message.format(self.__class__.__name__, key))


class MusicServiceItem(KwargsBase):
    """A base class for all music service items

    Attributes:
        service (soco.music_service.MusicService): The music service that this
            item originates from
        resources (list): List of DidlResource
        desc (str): A DIDL descriptor, default ``'RINCON_AssociatedZPUDN'
    """

    # See comment in KwargsBase for these two attributes
    _valid_fields = {}
    _types = {}

    def __init__(self, service, **kwargs):
        """Init music service item"""
        super(MusicServiceItem, self).__init__(**kwargs)
        self.service = service
        self.resources = [DidlResource(uri=self.uri, protocol_info="DUMMY")]
        self.desc = self.service.desc

    @classmethod
    def from_dict(cls, service, content_dict):
        """Return an element instantiated from a dict and the service
        (alternative constructor)

        Args:
            service (soco.music_service.MusicService): The music service that
                this element originates from
            content_dict (dict): Content to create the instance from. For
                information about valid elements and types see _valid_fields
                and _types
        """
        return cls(service, **content_dict)

    @property
    def item_id(self):
        """Return the DIDL Lite compatible item_id"""
        quoted_id = quote_url(self.metadata['id'].encode('utf-8'))
        return '0fffffff{0}'.format(quoted_id)
    
    @property
    def uri(self):
        """Return the uri"""
        # For an album
        if not isinstance(self, get_class('MediaMetadataTrack')):
            uri = 'x-rincon-cpcontainer:' + self.item_id
        # For a track
        else:
            uri = self.service.sonos_uri_from_id(self.item_id)
        return uri

    def __str__(self):
        """Return custom string representation"""
        title = self.metadata.get('title')
        str_ = '<{0} title="{1}">'
        return str_.format(self.__class__.__name__, title)

    def to_element(self, include_namespaces=False):
        """Return an ElementTree Element representing this instance.

        Args:
            include_namespaces (bool, optional): If True, include xml
                namespace attributes on the root element

        Return:
            ~xml.etree.ElementTree.Element: an Element.
        """
        # We piggy back on the implementation in DidlItem
        didl_item = DidlItem(
            title="DUMMY",
            # This is ignored. Sonos gets the title from the item_id
            parent_id="DUMMY",  # Ditto
            item_id=self.item_id,
            desc=self.desc,
            resources=self.resources
        )
        return didl_item.to_element(include_namespaces=include_namespaces)


class TrackMetadata(KwargsBase):
    """Track metadata class"""

    # _valid_fields is a set of valid fields
    _valid_fields = {
        'artistId',
        'artist',
        'composerId',
        'composer',
        'albumId',
        'album',
        'albumArtURI',
        'albumArtistId',
        'albumArtist',
        'genreId',
        'genre',
        'duration',
        'canPlay',
        'canSkip',
        'canAddToFavorites',
        'rating',
        'trackNumber',
        'isFavorite',
    }
    # _types is a dict of fields with non-string types and their
    # convertion callables
    _types = {
        'duration': int,
        'canPlay': bool_str,
        'canSkip': bool_str,
        'canAddToFavorites': bool_str,
        'rating': int,
        'trackNumber': int,
        'isFavorite': bool_str,
    }


class StreamMetadata(KwargsBase):
    """Track metadata class"""

    # _valid_fields is a set of valid fields
    _valid_fields = {
        'currentHost',
        'currentShowId',
        'currentShow',
        'secondsRemaining',
        'secondsToNextShow',
        'bitrate',
        'logo',
        'hasOutOfBandMetadata',
        'description',
        'isEphemeral',
    }
    # _types is a dict of fields with non-string types and their
    # convertion callables
    _types = {
        'secondsRemaining': int,
        'secondsToNextShow': int,
        'bitrate': int,
        'hasOutOfBandMetadata': bool_str,
        'isEphemeral': bool_str,
    }


class MediaMetadata(MusicServiceItem):
    """Base class for all media metadata items"""

    # _valid_fields is a set of valid fields
    _valid_fields = {
        'id',
        'title',
        'mimeType',
        'itemType',
        'displayType',
        'summary',
        'trackMetadata',
        'streamMetadata',
        'dynamic',
    }
    # _types is a dict of fields with non-string types and their
    # convertion callables
    _types = {
        'trackMetadata': TrackMetadata.from_dict,
        'streamMetadata': StreamMetadata.from_dict,
        # FIXME Think about what to do about dynamic. Is it possible
        # to type convert, is it even helpful?
        #'dynamic': ???, 
    }


class MediaCollection(MusicServiceItem):
    """Base class for all mediaCollection items"""

    # _valid_fields is a set of valid fields
    _valid_fields = {
        'id',
        'title',
        'itemType',
        'displayType',
        'summary',
        'artistId',
        'artist',
        'albumArtURI',
        'canPlay',
        'canEnumerate',
        'canAddToFavorites',
        'containsFavorite',
        'canScroll',
        'canSkip',
        'isFavorite',
    }

    # _types is a dict of fields with non-string types and their
    # convertion callables
    _types = {
        'canPlay': bool_str,
        'canEnumerate': bool_str,
        'canAddToFavorites': bool_str,
        'containsFavorite': bool_str,
        'canScroll': bool_str,
        'canSkip': bool_str,
        'isFavorite': bool_str,
    }
