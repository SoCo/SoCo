"""Integration test data_structures_entry"""

import pytest

from soco.data_structures_entry import from_didl_string
from soco.data_structures import (
    DidlMusicTrack,
    DidlMusicArtist,
    DidlMusicGenre,
    DidlContainer,
    DidlPlaylistContainer,
    DidlMusicAlbum,
    DidlPerson,
    DidlAudioBroadcast,
)


from conftest import DataLoader

DATA_LOADER = DataLoader("data_structures_entry_integration")


TEST_ITEMS_DATA = (
    (DidlMusicTrack, *DATA_LOADER.load_xml_and_json("track")),
    (DidlMusicAlbum, *DATA_LOADER.load_xml_and_json("album")),
    (DidlMusicArtist, *DATA_LOADER.load_xml_and_json("artist")),
    (DidlMusicGenre, *DATA_LOADER.load_xml_and_json("genre")),
    (DidlContainer, *DATA_LOADER.load_xml_and_json("share")),
    (DidlPlaylistContainer, *DATA_LOADER.load_xml_and_json("playlist")),
    (DidlAudioBroadcast, *DATA_LOADER.load_xml_and_json("audio_broadcast")),
)


@pytest.mark.parametrize(
    "klass,didl_xml_string,data",
    TEST_ITEMS_DATA,
    ids=[i[0].__name__ for i in TEST_ITEMS_DATA],
)
def test_items(klass, didl_xml_string, data):
    """Test standard DIDL item loading"""
    item = from_didl_string(didl_xml_string)[0]
    assert item.__class__ is klass
    for key, value in data.items():
        assert getattr(item, key) == value


# FIXME For the tests below that doesn't have a dedicated JSON data file, the
# XML used is faked, created by just editing the didl_class in a copy of the
# XML of the class it is derived from and therefore also compared to the same
# data as the class it is derived from. It should be replaced with data
# captured in the wild.
KNOWN_VENDOR_EXTENDED_CLASSES = (
    (
        "DidlRecentShow",
        DidlMusicTrack,
        DATA_LOADER.load_xml("recent_show.xml"),
        DATA_LOADER.load_json("track.json"),
    ),
    (
        "DidlMusicAlbumFavorite",
        DidlMusicAlbum,
        DATA_LOADER.load_xml("album_favorite.xml"),
        DATA_LOADER.load_json("album.json"),
    ),
    (
        "DidlMusicAlbumCompilation",
        DidlMusicAlbum,
        DATA_LOADER.load_xml("album_compilation.xml"),
        DATA_LOADER.load_json("album.json"),
    ),
    (
        "DidlComposer",
        DidlPerson,
        DATA_LOADER.load_xml("composer.xml"),
        DATA_LOADER.load_json("composer.json"),
    ),
    (
        "DidlAlbumList",
        DidlContainer,
        DATA_LOADER.load_xml("album_list.xml"),
        DATA_LOADER.load_json("share.json"),
    ),
    (
        "DidlSameArtist",
        DidlPlaylistContainer,
        DATA_LOADER.load_xml("same_artist.xml"),
        DATA_LOADER.load_json("playlist.json"),
    ),
    (
        "DidlPlaylistContainerFavorite",
        DidlPlaylistContainer,
        DATA_LOADER.load_xml("playlist_favorite.xml"),
        DATA_LOADER.load_json("playlist.json"),
    ),
    (
        "DidlPlaylistContainerTracklist",
        DidlPlaylistContainer,
        DATA_LOADER.load_xml("tracklist.xml"),
        DATA_LOADER.load_json("playlist.json"),
    ),
    (
        "DidlRadioShow",
        DidlContainer,
        DATA_LOADER.load_xml("radio_show.xml"),
        DATA_LOADER.load_json("radio_show.json"),
    ),
)

# There doesn't exist any tests of this kind yet for:
# "object.item.audioItem.audioBroadcast.sonos-favorite"
# "DidlAudioBroadcastFavorite",
#
# "object.itemobject.item.sonos-favorite"
# "DidlFavorite",


@pytest.mark.parametrize(
    "class_name,base_class,didl_xml_string,data",
    KNOWN_VENDOR_EXTENDED_CLASSES,
    ids=[i[0] for i in KNOWN_VENDOR_EXTENDED_CLASSES],
)
def test_vendor_extended_didl_class(class_name, base_class, didl_xml_string, data):
    """Test that vendor extended DIDL classes have proper names and base class"""
    item = from_didl_string(didl_xml_string)[0]

    # Test inheritance
    assert item.__class__.__name__ == class_name
    assert base_class is item.__class__.__bases__[0]
    assert base_class._translation == item._translation
