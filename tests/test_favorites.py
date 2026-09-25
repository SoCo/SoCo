"""Tests for the Favorites class."""

from unittest import mock

import pytest

from soco.data_structures import (
    DidlFavorite,
    DidlMusicArtist,
    DidlMusicTrack,
    DidlPlaylistContainer,
)
from soco.exceptions import (
    FavoritesAlreadyAddedError,
    FavoritesFullError,
    SoCoUPnPException,
)


class TestFavorites:
    def test_add_to_favorites(self, moco):
        moco.contentDirectory.CreateObject.return_value = {"ObjectID": "FV:2/130"}
        track = DidlMusicTrack("Song", "A:TRACKS", "t1")
        track.set_uri(
            "http://example.com/song.mp3", protocol_info="http-get:*:audio/mpeg:*"
        )
        fav = moco.favorites.add_to_favorites(track)
        args = moco.contentDirectory.CreateObject.call_args[0][0]
        assert args[0] == ("ContainerID", "FV:2")
        assert "<dc:title>Song</dc:title>" in args[1][1]
        assert "object.itemobject.item.sonos-favorite" in args[1][1]
        assert "<r:type>instantPlay</r:type>" in args[1][1]
        assert "http://example.com/song.mp3" in args[1][1]
        assert fav.item_id == "FV:2/130"
        assert fav.title == "Song"

    def test_add_to_favorites_with_title_and_description(self, moco):
        moco.contentDirectory.CreateObject.return_value = {"ObjectID": "FV:2/131"}
        track = DidlMusicTrack("Song", "A:TRACKS", "t1")
        track.set_uri(
            "http://example.com/song.mp3", protocol_info="http-get:*:audio/mpeg:*"
        )
        fav = moco.favorites.add_to_favorites(
            track, title="My Fave", description="By Artist"
        )
        args = moco.contentDirectory.CreateObject.call_args[0][0]
        assert "<dc:title>My Fave</dc:title>" in args[1][1]
        assert "<r:description>By Artist</r:description>" in args[1][1]
        assert fav.title == "My Fave"

    def test_add_to_favorites_full_raises_favorites_full_error(self, moco):
        moco.contentDirectory.CreateObject.side_effect = SoCoUPnPException(
            "UPnP Error 805 received", "805", "error xml"
        )
        track = DidlMusicTrack("Song", "A:TRACKS", "t1")
        track.set_uri(
            "http://example.com/song.mp3", protocol_info="http-get:*:audio/mpeg:*"
        )
        with pytest.raises(FavoritesFullError):
            moco.favorites.add_to_favorites(track)

    def test_add_to_favorites_duplicate_raises_already_added_error(self, moco):
        moco.contentDirectory.CreateObject.side_effect = SoCoUPnPException(
            "UPnP Error 803 received", "803", "error xml"
        )
        track = DidlMusicTrack("Song", "A:TRACKS", "t1")
        track.set_uri(
            "http://example.com/song.mp3", protocol_info="http-get:*:audio/mpeg:*"
        )
        with pytest.raises(FavoritesAlreadyAddedError):
            moco.favorites.add_to_favorites(track)

    def test_add_to_favorites_rejects_non_didl(self, moco):
        with pytest.raises(TypeError):
            moco.favorites.add_to_favorites("not a didl object")
        moco.contentDirectory.CreateObject.assert_not_called()

    def test_add_to_favorites_without_resource_raises_value_error(self, moco):
        track = DidlMusicTrack("Song", "A:TRACKS", "t1")
        with pytest.raises(ValueError):
            moco.favorites.add_to_favorites(track)
        moco.contentDirectory.CreateObject.assert_not_called()

    def test_add_to_favorites_album_art_at_favorite_level(self, moco):
        moco.contentDirectory.CreateObject.return_value = {"ObjectID": "FV:2/141"}
        track = DidlMusicTrack("Song", "A:TRACKS", "t1", album_art_uri="/art.jpg")
        track.set_uri(
            "http://example.com/song.mp3", protocol_info="http-get:*:audio/mpeg:*"
        )
        moco.favorites.add_to_favorites(track)
        elements = moco.contentDirectory.CreateObject.call_args[0][0][1][1]
        # albumArtURI is emitted on the favorite itself, and stripped from
        # resMD where the speaker would silently truncate it.
        assert "<upnp:albumArtURI>/art.jpg</upnp:albumArtURI>" in elements
        resmd = elements.split("<r:resMD>")[1]
        assert "albumArtURI" not in resmd

    def test_add_to_favorites_container_item(self, moco):
        moco.contentDirectory.CreateObject.return_value = {"ObjectID": "FV:2/140"}
        playlist = DidlPlaylistContainer("Morning Mix", "SQ:", "SQ:0")
        playlist.set_uri("file:///jffs/settings/savedqueues.rsq#0")
        fav = moco.favorites.add_to_favorites(playlist)
        args = moco.contentDirectory.CreateObject.call_args[0][0]
        elements = args[1][1]
        assert 'protocolInfo="file:*:*:*"' in elements
        assert ">file:///jffs/settings/savedqueues.rsq#0</res>" in elements
        assert fav.item_id == "FV:2/140"

    def test_add_to_favorites_container_without_resource(self, moco):
        # Service containers (e.g. a music service album) carry no res;
        # Sonos plays them via x-rincon-cpcontainer:<item_id> (verified on
        # S2 hardware).
        moco.contentDirectory.CreateObject.return_value = {"ObjectID": "FV:2/142"}
        album = DidlPlaylistContainer(
            "Two (Live)", "00052064artist:543347", "0004206calbum:1036288407"
        )
        moco.favorites.add_to_favorites(album)
        elements = moco.contentDirectory.CreateObject.call_args[0][0][1][1]
        assert 'protocolInfo="x-rincon-cpcontainer:*:*:*"' in elements
        assert ">x-rincon-cpcontainer:0004206calbum:1036288407</res>" in elements

    def test_add_to_favorites_artist_is_shortcut(self, moco):
        # Browsable-only containers (artists, composers) become
        # r:type=shortcut favorites with no res element, matching how the
        # Sonos app stores them.
        moco.contentDirectory.CreateObject.return_value = {"ObjectID": "FV:2/146"}
        artist = DidlMusicArtist("Nathaniel Rateliff", "10052064artist:362131302", "a1")
        moco.favorites.add_to_favorites(artist)
        elements = moco.contentDirectory.CreateObject.call_args[0][0][1][1]
        assert "<r:type>shortcut</r:type>" in elements
        assert "<res" not in elements

    def test_remove_from_favorites_with_didl_object(self, moco):
        fav = DidlFavorite("Breathe", "FV:2", "FV:2/28")
        moco.favorites.remove_from_favorites(fav)
        moco.contentDirectory.DestroyObject.assert_called_once_with(
            [("ObjectID", "FV:2/28")]
        )

    def test_remove_from_favorites_with_item_id(self, moco):
        moco.favorites.remove_from_favorites("FV:2/28")
        moco.contentDirectory.DestroyObject.assert_called_once_with(
            [("ObjectID", "FV:2/28")]
        )

    def test_update_favorite_title(self, moco):
        moco.contentDirectory.Browse.return_value = {
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<item id="FV:2/28" parentID="FV:2" restricted="false">'
                "<dc:title>Breathe</dc:title>"
                "<upnp:class>object.itemobject.item.sonos-favorite</upnp:class>"
                "</item></DIDL-Lite>"
            )
        }
        moco.favorites.update_favorite("FV:2/28", title="Deep Breath")
        moco.contentDirectory.Browse.assert_called_once_with(
            [
                ("ObjectID", "FV:2/28"),
                ("BrowseFlag", "BrowseMetadata"),
                ("Filter", "*"),
                ("StartingIndex", 0),
                ("RequestedCount", 0),
                ("SortCriteria", ""),
            ]
        )
        args = moco.contentDirectory.UpdateObject.call_args[0][0]
        assert args[0] == ("ObjectID", "FV:2/28")
        assert args[1] == ("CurrentTagValue", "<dc:title>Breathe</dc:title>")
        assert args[2] == ("NewTagValue", "<dc:title>Deep Breath</dc:title>")

    def test_update_favorite_title_and_description(self, moco):
        moco.contentDirectory.Browse.return_value = {
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<item id="FV:2/28" parentID="FV:2" restricted="false">'
                "<dc:title>Breathe</dc:title>"
                "<r:description>By Fleurie</r:description>"
                "</item></DIDL-Lite>"
            )
        }
        moco.favorites.update_favorite(
            "FV:2/28", title="Deep Breath", description="By Someone"
        )
        args = moco.contentDirectory.UpdateObject.call_args[0][0]
        assert args[1] == (
            "CurrentTagValue",
            "<dc:title>Breathe</dc:title>," "<r:description>By Fleurie</r:description>",
        )
        assert args[2] == (
            "NewTagValue",
            "<dc:title>Deep Breath</dc:title>,"
            "<r:description>By Someone</r:description>",
        )

    def test_update_favorite_escapes_title(self, moco):
        moco.contentDirectory.Browse.return_value = {
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<item id="FV:2/28" parentID="FV:2" restricted="false">'
                "<dc:title>Breathe</dc:title>"
                "</item></DIDL-Lite>"
            )
        }
        moco.favorites.update_favorite("FV:2/28", title="Rock & Roll <Live>")
        args = moco.contentDirectory.UpdateObject.call_args[0][0]
        assert args[2] == (
            "NewTagValue",
            "<dc:title>Rock &amp; Roll &lt;Live&gt;</dc:title>",
        )

    def test_update_favorite_with_backslash_in_title(self, moco):
        moco.contentDirectory.Browse.return_value = {
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<item id="FV:2/28" parentID="FV:2" restricted="false">'
                "<dc:title>Breathe</dc:title>"
                "</item></DIDL-Lite>"
            )
        }
        moco.favorites.update_favorite("FV:2/28", title=r"Rock \\ Band")
        args = moco.contentDirectory.UpdateObject.call_args[0][0]
        assert args[2] == ("NewTagValue", "<dc:title>Rock \\\\ Band</dc:title>")

    def test_update_favorite_new_property_uses_empty_placeholder(self, moco):
        moco.contentDirectory.Browse.return_value = {
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<item id="FV:2/28" parentID="FV:2" restricted="false">'
                "<dc:title>Breathe</dc:title>"
                "<upnp:class>object.itemobject.item.sonos-favorite</upnp:class>"
                "<r:resMD>inner-metadata-here</r:resMD>"
                "</item></DIDL-Lite>"
            )
        }
        moco.favorites.update_favorite("FV:2/28", description="By Fleurie")
        args = moco.contentDirectory.UpdateObject.call_args[0][0]
        # A property that does not yet exist gets an empty placeholder in
        # CurrentTagValue, per the ContentDirectory UpdateObject spec.
        assert args[1] == ("CurrentTagValue", "")
        assert args[2] == (
            "NewTagValue",
            "<r:description>By Fleurie</r:description>",
        )

    def test_update_favorite_no_change_is_noop(self, moco):
        moco.contentDirectory.Browse.return_value = {
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<item id="FV:2/28" parentID="FV:2" restricted="false">'
                "<dc:title>Breathe</dc:title>"
                "</item></DIDL-Lite>"
            )
        }
        moco.favorites.update_favorite("FV:2/28")
        moco.contentDirectory.Browse.assert_not_called()
        moco.contentDirectory.UpdateObject.assert_not_called()

    def test_update_favorite_empty_description_raises_value_error(self, moco):
        moco.contentDirectory.Browse.return_value = {
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<item id="FV:2/28" parentID="FV:2" restricted="false">'
                "<dc:title>Breathe</dc:title>"
                "<r:description>By Fleurie</r:description>"
                "</item></DIDL-Lite>"
            )
        }
        # Sonos rejects all forms of property deletion (UPnP 712), so
        # empty values are rejected client-side.
        with pytest.raises(ValueError):
            moco.favorites.update_favorite("FV:2/28", description="")
        moco.contentDirectory.UpdateObject.assert_not_called()

    def test_update_favorite_empty_title_raises_value_error(self, moco):
        # dc:title is a required property and cannot be deleted.
        with pytest.raises(ValueError):
            moco.favorites.update_favorite("FV:2/28", title="")
        moco.contentDirectory.Browse.assert_not_called()
        moco.contentDirectory.UpdateObject.assert_not_called()

    def test_update_favorite_with_comma_in_title(self, moco):
        moco.contentDirectory.Browse.return_value = {
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<item id="FV:2/28" parentID="FV:2" restricted="false">'
                "<dc:title>Old, Title</dc:title>"
                "</item></DIDL-Lite>"
            )
        }
        moco.favorites.update_favorite("FV:2/28", title="Jazz, Blues & Rock")
        args = moco.contentDirectory.UpdateObject.call_args[0][0]
        # Commas are sent unescaped: Sonos parses the TagValueList as XML
        # fragments and stores the spec's \, escaping literally (verified
        # on S2 hardware).
        assert args[1] == ("CurrentTagValue", "<dc:title>Old, Title</dc:title>")
        assert args[2] == (
            "NewTagValue",
            "<dc:title>Jazz, Blues &amp; Rock</dc:title>",
        )

    def test_update_favorite_unchanged_value_is_noop(self, moco):
        moco.contentDirectory.Browse.return_value = {
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<item id="FV:2/28" parentID="FV:2" restricted="false">'
                "<dc:title>Breathe</dc:title>"
                "</item></DIDL-Lite>"
            )
        }
        moco.favorites.update_favorite("FV:2/28", title="Breathe")
        moco.contentDirectory.UpdateObject.assert_not_called()

    def test_rename_favorite_delegates_to_update(self, moco):
        moco.contentDirectory.Browse.return_value = {
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<item id="FV:2/28" parentID="FV:2" restricted="false">'
                "<dc:title>Breathe</dc:title>"
                "</item></DIDL-Lite>"
            )
        }
        moco.favorites.rename_favorite("FV:2/28", "Deep Breath")
        args = moco.contentDirectory.UpdateObject.call_args[0][0]
        assert args[1] == ("CurrentTagValue", "<dc:title>Breathe</dc:title>")
        assert args[2] == ("NewTagValue", "<dc:title>Deep Breath</dc:title>")

    def test_get_sonos_favorites_delegates_to_music_library(self, moco):
        with mock.patch.object(
            moco.music_library, "get_music_library_information", return_value="favs"
        ) as mocked:
            result = moco.favorites.get_sonos_favorites()
        assert result == "favs"
        mocked.assert_called_once_with("sonos_favorites")
