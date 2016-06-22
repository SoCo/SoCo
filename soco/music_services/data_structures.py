
"""Data structures for music service items

The basis for this implementation is this page in the Sonos API
documentation: http://musicpartners.sonos.com/node/83

A note about naming. The Sonos API uses camel case with stating lower
case. These names have been adapted to match generel Python class
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

"""

from __future__ import print_function
from collections import OrderedDict, defaultdict
from pprint import pprint


# For now we generate classes dynamically. This is shorter, but
# provides no custom documentation for all the different types.
CLASSES = {}
def get_class(class_key):
    """Form a class from the class key

    The class key is a concatenation of the base class
    (e.g. MediaMetadata) and the class name
    """
    if class_key not in CLASSES:
        for basecls in (MediaMetadata, MediaCollection):
            if class_key.startswith(basecls.__name__):
                class_name = 'MS' + class_key.replace(basecls.__name__, '')
                CLASSES[class_key] = type(class_name, (basecls,), {})
    return CLASSES[class_key]


def parse_response(search_result):
    """Parse the query response"""
    items = []
    search_result = search_result['searchResult']
    for result_type in ('mediaCollection', 'mediaMetadata'):
        result_type_proper = result_type[0].upper() + result_type[1:]
        raw_items = search_result.get(result_type, [])
        # If there is only 1 result, it is not put in an array
        if isinstance(raw_items, OrderedDict):
            raw_items = [raw_items]
        for raw_item in raw_items:
            class_key = result_type_proper + raw_item['itemType'].title()
            cls = get_class(class_key)
            items.append(cls.from_dict(raw_item))

    for item in items:
        print(item.__class__.__name__, item.__class__.__bases__)
        pprint(item.metadata)
    return items



### Type Helpers
def bool_str(string, valid={'true', 'false'}):
    """Type convert boolean string"""
    if string not in valid:
        raise ValueError('Invalid boolean string: "{}"'.format(string))
    return True if string == "true" else False

def passthrough(item):
    return item


### Music Service item base classes
class MusicServiceItem(object):
    """A base class for all music service items"""

    def __init__(self, **kwargs):
        self.metadata = kwargs
        for key, value in self.metadata.copy().items():
            if key not in self._valid_fields:
                message = 'Field: "{}" is not valid for class "{}"'
                raise ValueError(message.format(key, self.__class__))
            if key in self._types:
                convertion_callable = self._types[key] 
                self.metadata[key] = convertion_callable(value)

    @classmethod
    def from_dict(cls, content_dict):
        return cls(**content_dict)


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
        'trackMetadata': passthrough,  # 'trackMetadata' FIXME
        'streamMetadata': passthrough,  # 'streamMetadata' FIXME
        # FIXME Think about what to do about dynamic. Is it possible
        # to type convert, is it even helpful?
        'dynamic': passthrough,  # 'dynamic' FIXME
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


if __name__ == '__main__':
    import soco
    print(soco)
    from soco.music_services import MusicService
    #print(MusicService.get_all_music_services_names())
    ym = MusicService('YouSee Musik')
    #print(ym.available_search_categories)
    ym.search('artists', 'A', 0, 2)
    ym.search('tracks', 'A', 0, 2)
    print('\n\n\n\n\n')
    ym.search('artists', 'A', 0, 1)
    ym.search('tracks', 'A', 0, 1)
