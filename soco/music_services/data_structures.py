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

from __future__ import print_function, absolute_import
from collections import OrderedDict
#from ..data_structures import DidlResource, DidlItem, SearchResult
from ..  import data_structures
from ..utils import camel_to_underscore
from ..compat import quote_url
from ..xml import XML
from ..discovery import discover
from ..compat import urlparse
from . import music_service
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
        class: Subclass of MusicServiceItem
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
            items.append(cls.from_music_service(service, raw_item))
    return data_structures.SearchResult(items, **search_metadata)


# FIXME, Obviously imcomplete 
DIDL_NAME_TO_QUALIFIED_MS_NAME = {
    'DidlMusicTrack': 'MediaMetadataTrack'
}
def attempt_datastructure_upgrade(didl_item):
    """Attempt to upgrade a didl_item to a music services data structure
    if it originates from a music services

    """
    resource = didl_item.resources[0]
    # FIXME are we guarantied that there are resources and that they have a uri????
    if resource.uri.startswith('x-sonos-http'):
        # Get data
        uri = resource.uri
        # Now we need to create a DIDL item id. It seems to be based on the uri
        path = urlparse(uri).path
        # Strip any extensions, eg .mp3, from the end of the path
        path = path.rsplit('.', 1)[0]
        # The ID has an 8 (hex) digit prefix. But it doesn't seem to matter what it is!
        item_id = '11111111{0}'.format(path)
        
        # FIXME Ignore other metadata for now, in future ask ms data
        # structure to upgrade metadata from the service
        metadata = {}
        try:
            metadata['title'] = didl_item.title
        except AttributeError:
            pass

        # Get class and instantiate
        cls = get_class(DIDL_NAME_TO_QUALIFIED_MS_NAME[didl_item.__class__.__name__])
        return cls(
            item_id=item_id,
            desc=music_service.desc_from_uri(resource.uri),
            resources=didl_item.resources,
            uri=uri,
            metadata_dict=metadata,
        )
    return didl_item


def form_uri(item_id, service, is_track):
    """Form and return uri from item_id, service and is_track info"""
    if is_track:
        uri = service.sonos_uri_from_id(item_id)
    else:
        uri = 'x-rincon-cpcontainer:' + item_id
    return uri


### Type Helper
BOOL_STRS = {'true', 'false'}
def bool_str(string):
    """Returns a boolean from a string imput of 'true' or 'false'"""
    if string not in BOOL_STRS:
        raise ValueError('Invalid boolean string: "{}"'.format(string))
    return True if string == "true" else False


### Music Service item base classes
class MetadataDictBase(object):
    """Class used to parse metadata from kwargs"""

    # The following two fields should be overwritten in subclasses

    # _valid_fields is a set of valid fields
    _valid_fields = {}

    # _types is a dict of fields with non-string types and their
    # convertion callables
    _types = {}
    
    def __init__(self, metadata_dict):
        """Initialize local variables"""
        # Check for invalid fields
        for key in metadata_dict:
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
                print(message.format(key, metadata_dict[key], self.__class__))
                #raise ValueError(message.format(key, metadata_dict[key], self.__class__))

        # Convert names and create metadata dict
        self.metadata = {}
        for key, value in metadata_dict.items():
            if key in self._types:
                convertion_callable = self._types[key] 
                value = convertion_callable(value)
            self.metadata[camel_to_underscore(key)] = value

    @classmethod
    def from_dict(cls, content_dict):
        """Init cls from a dict (alternative initializer)"""
        return cls(content_dict)

    def __getattr__(self, key):
        """Return item from metadata in case of unknown attribute"""
        try:
            return self.metadata[key]
        except KeyError:
            message = 'Class {0} has no attribute "{1}"'
            raise AttributeError(message.format(self.__class__.__name__, key))


class MusicServiceItem(MetadataDictBase):
    """A base class for all music service items"""

    # See comment in MetadataDictBase for these two attributes
    _valid_fields = {}
    _types = {}

    def __init__(self, item_id, desc, resources, uri, metadata_dict,
                 music_service = None):
        """Init music service item

        Args:
            item_id (str): This is the Didl compatible id NOT the music item id
            desc (str): A DIDL descriptor, default ``'RINCON_AssociatedZPUDN'
            resources (list): List of DidlResource
            uri (str): The uri for the location of the item
            metdata_dict (dict): Mapping of metadata
            music_service (MusicService): The MusicService instance the item originates from
        """
        super(MusicServiceItem, self).__init__(metadata_dict)
        self.item_id = item_id
        self.desc = desc
        self.resources = resources
        self.uri = uri
        self.music_service = music_service

    @classmethod
    def from_music_service(cls, music_service, content_dict):
        """Return an element instantiated from the information that a music
        service has

        """
        # Form the item_id
        quoted_id = quote_url(content_dict['id'].encode('utf-8'))
        item_id = '0fffffff{0}'.format(quoted_id)
        # Form the uri
        is_track = cls == get_class('MediaMetadataTrack')
        uri = form_uri(item_id, music_service, is_track)
        # Form resources and get desc
        resources = [data_structures.DidlResource(uri=uri, protocol_info="DUMMY")]
        desc = music_service.desc
        return cls(item_id, desc, resources, uri, content_dict,
                   music_service=music_service)

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
        didl_item = data_structures.DidlItem(
            title="DUMMY",
            # This is ignored. Sonos gets the title from the item_id
            parent_id="DUMMY",  # Ditto
            item_id=self.item_id,
            desc=self.desc,
            resources=self.resources
        )
        # FIXME think about separating to_element code out into function
        # in soco.data_structures
        return didl_item.to_element(include_namespaces=include_namespaces)


class TrackMetadata(MetadataDictBase):
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


class StreamMetadata(MetadataDictBase):
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
