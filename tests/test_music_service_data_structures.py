"""Test for music_services/data_structures"""

from __future__ import unicode_literals, print_function

from collections import OrderedDict
import pytest
from mock import Mock
from soco.music_services import data_structures

# DATA
RESPONSE = OrderedDict([('searchResult',
    OrderedDict([('index', '0'),
                 ('count', '2'),
                 ('total', '17230'),
                 ('mediaCollection',
        [OrderedDict([('id', 'album/43820695'),
                      ('itemType', 'album'),
                      ('title', 'Black Mosque'),
                      ('artist', 'Black Mosque'),
                      ('artistId', 'artist/6689314'),
                      ('canPlay', 'true'),
                      ('canEnumerate', 'true'),
                      ('canAddToFavorites', 'true'),
                      ('canSkip', 'true'),
                      ('albumArtURI', 'http://resources.wimpmusic.com/images/'
                       '2238a5cd/ed4d/4ad0/848d/40356f11bda0/640x640.jpg'),
                      ('canAddToFavorite', 'true')]),
         OrderedDict([('id', 'album/50340580'),
                      ('itemType', 'album'),
                      ('title', 'Black Hippy 2'),
                      ('artist', 'Black Hippy'),
                      ('artistId', 'artist/3882538'),
                      ('canPlay', 'true'),
                      ('canEnumerate', 'true'),
                      ('canAddToFavorites', 'true'),
                      ('canSkip', 'true'),
                      ('albumArtURI',
                       'http://resources.wimpmusic.com/images/eefb1532/dfe9/'
                       '46bd/8775/c583844bc098/640x640.jpg'),
                      ('canAddToFavorite', 'true')])
        ])
    ]))
])


def test_get_class():
    """Test the get_class function"""
    # Test core functionality for base class MediaMetadata
    cls = data_structures.get_class('MediaMetadataTrack')
    assert cls.__name__ == 'MSTrack'
    assert issubclass(cls, data_structures.MediaMetadata)

    # Test core functionality for base class Mediacolection
    cls = data_structures.get_class('MediaCollectionArtist')
    assert cls.__name__ == 'MSArtist'
    assert issubclass(cls, data_structures.MediaCollection)

    # Test the caching function
    cls2 = data_structures.get_class('MediaCollectionArtist')
    assert cls is cls2

    # Asking for bad class should raise KeyError
    with pytest.raises(KeyError):
        cls = data_structures.get_class('Nonsense')


def test_parse_response():
    """Test the parse_response function"""
    music_service = Mock()
    music_service.desc = 'DESC'
    results = data_structures.parse_response(music_service, RESPONSE, 'albums')

    # Check the search result metadata
    response_data = RESPONSE['searchResult']
    assert results.number_returned == response_data['count']
    assert results.search_type == 'albums'

    # Check the result
    assert len(results) == 2
    album_class = data_structures.get_class('MediaCollectionAlbum')
    for result in results:
        assert isinstance(result, album_class)
        assert result.music_service is music_service


def test_form_uri():
    """Test the form uri function"""
    music_service = Mock()
    music_service.sonos_uri_from_id.return_value = '99'

    # Test non track uri
    non_track_uri = data_structures.form_uri('dummy_id', None, False)
    assert non_track_uri == 'x-rincon-cpcontainer:dummy_id'

    # Test track uri
    track_uri = data_structures.form_uri('dummy_id', music_service, True)
    assert music_service.sonos_uri_from_id.called_once_with('dummy_id')


def test_bool_str():
    """Test the bool_str function"""
    assert data_structures.bool_str('true') is True
    assert data_structures.bool_str('false') is False
    with pytest.raises(ValueError):
        data_structures.bool_str('dummy')
