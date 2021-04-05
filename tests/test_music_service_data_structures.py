"""Test for music_services/data_structures"""


from collections import OrderedDict
import pytest
from unittest.mock import PropertyMock, Mock, patch
from soco.music_services import data_structures
from soco.data_structures import DidlResource

# DATA
RESPONSES = []
RESPONSES.append(
    OrderedDict(
        [
            (
                "searchResult",
                OrderedDict(
                    [
                        ("index", "0"),
                        ("count", "2"),
                        ("total", "17230"),
                        (
                            "mediaCollection",
                            [
                                OrderedDict(
                                    [
                                        ("id", "album/43820695"),
                                        ("itemType", "album"),
                                        ("title", "Black Mosque"),
                                        ("artist", "Black Mosque"),
                                        ("artistId", "artist/6689314"),
                                        ("canPlay", "true"),
                                        ("canEnumerate", "true"),
                                        ("canAddToFavorites", "true"),
                                        ("canSkip", "true"),
                                        (
                                            "albumArtURI",
                                            "http://resources.wimpmusic.com/images/"
                                            "2238a5cd/ed4d/4ad0/848d/40356f11bda0/"
                                            "640x640.jpg",
                                        ),
                                        ("canAddToFavorite", "true"),
                                    ]
                                ),
                                OrderedDict(
                                    [
                                        ("id", "album/50340580"),
                                        ("itemType", "album"),
                                        ("title", "Black Hippy 2"),
                                        ("artist", "Black Hippy"),
                                        ("artistId", "artist/3882538"),
                                        ("canPlay", "true"),
                                        ("canEnumerate", "true"),
                                        ("canAddToFavorites", "true"),
                                        ("canSkip", "true"),
                                        (
                                            "albumArtURI",
                                            "http://resources.wimpmusic.com/images/"
                                            "eefb1532/dfe9/"
                                            "46bd/8775/c583844bc098/640x640.jpg",
                                        ),
                                        ("canAddToFavorite", "true"),
                                    ]
                                ),
                            ],
                        ),
                    ]
                ),
            )
        ]
    )
)
RESPONSES.append(
    OrderedDict(
        [
            (
                "getMetadataResult",
                OrderedDict(
                    [
                        (
                            "mediaMetadata",
                            OrderedDict(
                                [
                                    ("id", "Track@catalog:/tracks/104655624"),
                                    ("title", "Take Me Into Your Skin"),
                                    ("itemType", "track"),
                                    ("mimeType", "audio/aac"),
                                    (
                                        "trackMetadata",
                                        OrderedDict(
                                            [
                                                (
                                                    "albumArtURI",
                                                    "http://artwork.cdn.247e.com/"
                                                    "covers/104655587/256x256",
                                                ),
                                                (
                                                    "artistId",
                                                    "Artist@catalog:/artists/219591",
                                                ),
                                                ("artist", "Trentemøller"),
                                                ("album", "The Last Resort"),
                                                ("duration", "464"),
                                                ("canPlay", "true"),
                                                ("canSkip", "true"),
                                                ("canAddToFavorites", "true"),
                                                ("trackNumber", "1"),
                                            ]
                                        ),
                                    ),
                                ]
                            ),
                        ),
                        ("count", "1"),
                        ("index", "0"),
                        ("total", "13"),
                    ]
                ),
            )
        ]
    )
)
PARSE_RESULTS = (
    {
        "number_of_results": 2,
        "type": "searchResult",
        "class_key": "MediaCollectionAlbum",
    },
    {
        "number_of_results": 1,
        "type": "getMetadataResult",
        "class_key": "MediaMetadataTrack",
    },
)


def test_get_class():
    """Test the get_class function"""
    # Test core functionality for base class MediaMetadata
    cls = data_structures.get_class("MediaMetadataTrack")
    assert cls.__name__ == "MSTrack"
    assert issubclass(cls, data_structures.MediaMetadata)

    # Test core functionality for base class Mediacolection
    cls = data_structures.get_class("MediaCollectionArtist")
    assert cls.__name__ == "MSArtist"
    assert issubclass(cls, data_structures.MediaCollection)

    # Test the caching function
    cls2 = data_structures.get_class("MediaCollectionArtist")
    assert cls is cls2

    # Asking for bad class should raise KeyError
    with pytest.raises(KeyError):
        cls = data_structures.get_class("Nonsense")


@pytest.mark.parametrize("response, correct", zip(RESPONSES, PARSE_RESULTS))
def test_parse_response(response, correct):
    """Test the parse_response function"""
    music_service = Mock()
    music_service.desc = "DESC"
    results = data_structures.parse_response(music_service, response, "albums")

    # Check the search result metadata
    response_data = response[correct["type"]]
    assert results.number_returned == response_data["count"]
    assert results.search_type == "albums"

    # Check the result
    assert len(results) == correct["number_of_results"]
    klass = data_structures.get_class(correct["class_key"])
    for result in results:
        assert isinstance(result, klass)
        assert result.music_service is music_service


def test_parse_response_bad_type():
    """Test parse reponse bad code"""
    with pytest.raises(ValueError) as exp:
        data_structures.parse_response(None, {}, "albums")
    print(exp)


def test_form_uri():
    """Test the form uri function"""
    music_service = Mock()
    music_service.sonos_uri_from_id.return_value = "99"

    # Test non track uri
    non_track_uri = data_structures.form_uri("dummy_id", None, False)
    assert non_track_uri == "x-rincon-cpcontainer:dummy_id"

    # Test track uri
    track_uri = data_structures.form_uri("dummy_id", music_service, True)
    music_service.sonos_uri_from_id.assert_called_once_with("dummy_id")


def test_bool_str():
    """Test the bool_str function"""
    assert data_structures.bool_str("true") is True
    assert data_structures.bool_str("false") is False
    with pytest.raises(ValueError):
        data_structures.bool_str("dummy")


class TestMetadataDictBase:
    """Tests for the MetadataDictBase class"""

    def test_init(self):
        """Test normal __init__ functionality; metadata stored and camel case
        names coverted

        """
        metadata_dict = {
            "superTitle": "Dummy Title",
        }
        metadata = data_structures.MetadataDictBase(metadata_dict)
        # Assert only metadata element, name conversion and value
        assert len(metadata.metadata) == 1
        assert metadata.super_title == "Dummy Title"

    def test_conversion(self):
        """Test the type conversion of fields in metadata"""
        conversion_mock = Mock()
        conversion_mock.return_value = 47

        # MetadataDictBase is meant to ve overwritten, to supply
        # valid_fields and conversion functions
        class MyClass(data_structures.MetadataDictBase):
            _types = {"trackDuration": conversion_mock}

        metadata_dict = {
            "title": "Dummy Title",
            "trackDuration": "47",
        }
        metadata = MyClass(metadata_dict)
        # Check that the duration has been properly type converted
        conversion_mock.assert_called_once_with("47")
        assert metadata.track_duration == 47
        # And that title has been left unchanged
        assert metadata.title == "Dummy Title"

    def test_get_attr(self):
        """Test the __getattr__ method"""
        metadata_dict = {
            "superTitle": "Dummy Title",
        }
        metadata = data_structures.MetadataDictBase(metadata_dict)
        # Test normal lookup
        assert metadata.super_title == "Dummy Title"
        # Test raise attribute error when the key is not in metadata
        with pytest.raises(AttributeError):
            metadata.nonexistent_key


class TestMusicServiceItem:
    """Test the MusicServiceItem class"""

    @patch("soco.music_services.data_structures.MetadataDictBase.__init__")
    def test_init(self, metadata_dict_base_init):
        """Test the __init__ method"""
        kwargs = {
            "item_id": "some_item_id",
            "desc": "the_desc",
            "resources": "the ressources",
            "uri": "https://the_uri",
            "metadata_dict": {"some": "dict"},
            "music_service": "the music service",
        }

        music_service_item = data_structures.MusicServiceItem(**kwargs)
        # Test call to super class init
        metadata_dict_base_init.assert_called_once_with({"some": "dict"})
        # Test that all but the metadata_dict arg have been set as
        # attributes with the same names as the arguments
        kwargs.pop("metadata_dict")
        for arg_name, arg_value in kwargs.items():
            assert getattr(music_service_item, arg_name) == arg_value

    @patch("soco.music_services.data_structures.MusicServiceItem.__init__")
    @patch("soco.music_services.data_structures.form_uri")
    @patch("soco.music_services.data_structures.DidlResource")
    def test_from_music_service(self, didl_resource, form_uri, music_service_init):
        """Test th from music service class method"""
        # Setup mock music service with mocked desc property
        ms = Mock()
        desc = PropertyMock(return_value="fake_desc")
        type(ms).desc = desc

        # Setup content dict
        id_ = "fakeid1234"
        item_id = "0fffffff" + id_
        content_dict = {"id": id_, "title": "fake title"}

        # Setup return values of mocks
        didl_resource.return_value = Mock()
        form_uri.return_value = "x-rincon-whatever:" + id_
        music_service_init.return_value = None

        # Call the class method and assert init called
        data_structures.MusicServiceItem.from_music_service(ms, content_dict)
        music_service_init.assert_called_once_with(
            item_id,
            "fake_desc",
            [didl_resource.return_value],
            form_uri.return_value,
            content_dict,
            music_service=ms,
        )
        form_uri.assert_called_once_with(item_id, ms, False)

    def test_str_(self):
        """Test the __str__ method"""
        content_dict = {"title": "fake title"}
        item = data_structures.MusicServiceItem(
            "fake_id", "desc", "ressources", "uri", content_dict
        )
        assert item.__str__() == '<MusicServiceItem title="fake title">'

    @patch("soco.music_services.data_structures.DidlItem.to_element")
    def test_to_element(self, didl_item_to_element):
        """Test the to_element method"""
        didl_item_to_element.return_value = object()
        content_dict = {"title": "fake title"}
        item = data_structures.MusicServiceItem(
            "fake_id", "desc", "ressources", "uri", content_dict
        )
        assert item.to_element() == didl_item_to_element.return_value
