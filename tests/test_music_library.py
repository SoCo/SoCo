from unittest import mock
import pytest

from soco import SoCo
from soco.exceptions import SoCoUPnPException

IP_ADDR = "192.168.1.101"


@pytest.fixture()
def moco():
    """A mock soco with fake services and hardcoded is_coordinator.

    Allows calls to services to be tracked. Should not cause any network
    access
    """
    services = (
        "AVTransport",
        "RenderingControl",
        "DeviceProperties",
        "ContentDirectory",
        "ZoneGroupTopology",
    )
    patchers = [mock.patch("soco.core.{}".format(service)) for service in services]
    for patch in patchers:
        patch.start()
    with mock.patch(
        "soco.SoCo.is_coordinator", new_callable=mock.PropertyMock
    ) as is_coord:
        is_coord = True
        yield SoCo(IP_ADDR)
    for patch in reversed(patchers):
        patch.stop()


class TestMusicLibrary:
    def test_search_track_no_result(self, moco):
        moco.contentDirectory.reset_mock()
        # Browse returns an exception if the artist can't be found
        # <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
        #  s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        #   <s:Body>
        #     <s:Fault>
        #       <faultcode>s:Client</faultcode>
        #       <faultstring>UPnPError</faultstring>
        #       <detail>
        #         <UPnPError xmlns="urn:schemas-upnp-org:control-1-0">
        #           <errorCode>701</errorCode>
        #         </UPnPError>
        #       </detail>
        #     </s:Fault>
        #   </s:Body>
        # </s:Envelope>
        moco.contentDirectory.Browse.side_effect = SoCoUPnPException(
            "No such object", "701", "error XML"
        )

        result = moco.music_library.search_track("artist")

        assert len(result) == 0

        moco.contentDirectory.Browse.assert_called_once_with(
            [
                ("ObjectID", "A:ALBUMARTIST/artist/"),
                ("BrowseFlag", "BrowseDirectChildren"),
                ("Filter", "*"),
                ("StartingIndex", 0),
                ("RequestedCount", 100000),
                ("SortCriteria", ""),
            ]
        )

    def test_search_track_no_artist_album_track(self, moco):
        moco.contentDirectory.reset_mock()
        # Browse returns an empty result set if artist and album and
        # track cannot be found
        moco.contentDirectory.Browse.side_effect = None
        moco.contentDirectory.Browse.return_value = {
            "NumberReturned": "0",
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"></DIDL-Lite>'
            ),
            "TotalMatches": "0",
            "UpdateID": "0",
        }

        result = moco.music_library.search_track("artist", "album", "track")

        assert len(result) == 0

        moco.contentDirectory.Browse.assert_called_once_with(
            [
                ("ObjectID", "A:ALBUMARTIST/artist/album:track"),
                ("BrowseFlag", "BrowseDirectChildren"),
                ("Filter", "*"),
                ("StartingIndex", 0),
                ("RequestedCount", 100000),
                ("SortCriteria", ""),
            ]
        )

    def test_search_track_artist_albums(self, moco):
        moco.contentDirectory.reset_mock()
        moco.contentDirectory.Browse.side_effect = None
        moco.contentDirectory.Browse.return_value = {
            "NumberReturned": "2",
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
                'xmlns:ns2="urn:schemas-upnp-org:metadata-1-0/upnp/">'
                '<container id="A:ALBUMARTIST/The%20Artist/First%20Album" '
                'parentID="A:ALBUMARTIST/The%20Artist" restricted="true">'
                "<dc:title>First Album</dc:title>"
                "<ns2:class>object.container.album.musicAlbum</ns2:class>"
                '<res protocolInfo="x-rincon-playlist:*:*:*">'
                "x-rincon-playlist:RINCON_000123456789001400#A:ALBUMARTIST/"
                "The%20Artist/First%20Album</res>"
                "<dc:creator>The Artist</dc:creator>"
                "<ns2:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fserver%2fThe%2520Artist"
                "%2fFirst%2520Album%2ftrack2.mp3&amp;v=432</ns2:albumArtURI>"
                "</container>"
                '<container id="A:ALBUMARTIST/The%20Artist/Second%20Album" '
                'parentID="A:ALBUMARTIST/The%20Artist" restricted="true">'
                "<dc:title>Second Album</dc:title>"
                "<ns2:class>object.container.album.musicAlbum</ns2:class>"
                '<res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:'
                "RINCON_000123456789001400#A:ALBUMARTIST/The%20Artist/Second%20Album"
                "</res>"
                "<dc:creator>The Artist</dc:creator>"
                "<ns2:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fserver%2fThe%2520Artist"
                "%2fSecond%2520Album%2ftrack2.mp3&amp;v=432</ns2:albumArtURI>"
                "</container>"
                "</DIDL-Lite>"
            ),
            "TotalMatches": "2",
            "UpdateID": "0",
        }
        results = moco.music_library.search_track("The Artist")

        assert results.number_returned == 2

        album = results[0]
        assert album.title == "First Album"
        assert album.item_id == "A:ALBUMARTIST/The%20Artist/First%20Album"
        album = results[1]
        assert album.title == "Second Album"
        assert album.item_id == "A:ALBUMARTIST/The%20Artist/Second%20Album"

        moco.contentDirectory.Browse.assert_called_once_with(
            [
                ("ObjectID", "A:ALBUMARTIST/The%20Artist/"),
                ("BrowseFlag", "BrowseDirectChildren"),
                ("Filter", "*"),
                ("StartingIndex", 0),
                ("RequestedCount", 100000),
                ("SortCriteria", ""),
            ]
        )

    def test_search_track_artist_album_tracks(self, moco):
        moco.contentDirectory.reset_mock()
        moco.contentDirectory.Browse.side_effect = None
        moco.contentDirectory.Browse.return_value = {
            "NumberReturned": "3",
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
                'xmlns:ns1="urn:schemas-upnp-org:metadata-1-0/upnp/">'
                '<item id="S://server/The%20Artist/The%20Album/'
                '03%20-%20Track%20Title%201.mp3" '
                'parentID="A:ALBUMARTIST/The%20Artist/The%20Album" restricted="true">'
                '<res protocolInfo="x-file-cifs:*:audio/mpeg:*">x-file-cifs://server/'
                "The%20Artist/The%20Album/03%20-%20Track%20Title%201.mp3</res>"
                "<ns1:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fserver%2fThe%2520Artist"
                "%2fThe%2520Album%2f03%2520-%2520Track%2520Title%25201.mp3&amp;v=432"
                "</ns1:albumArtURI>"
                "<dc:title>Track Title 1</dc:title>"
                "<ns1:class>object.item.audioItem.musicTrack</ns1:class>"
                "<dc:creator>The Artist</dc:creator>"
                "<ns1:album>The Album</ns1:album>"
                "<ns1:originalTrackNumber>3</ns1:originalTrackNumber>"
                "</item>"
                '<item id="S://server/The%20Artist/The%20Album/'
                '04%20-%20Track%20Title%202.m4a" '
                'parentID="A:ALBUMARTIST/The%20Artist/The%20Album" restricted="true">'
                '<res protocolInfo="x-file-cifs:*:audio/mp4:*">x-file-cifs://server/'
                "The%20Artist/The%20Album/04%20-%20Track%20Title%202.m4a</res>"
                "<ns1:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fserver%2fThe%2520"
                "Artist%2fThe%2520Album%2f04%2520-%2520Track%2520Title%25202.m4a"
                "&amp;v=432</ns1:albumArtURI>"
                "<dc:title>Track Title 2</dc:title>"
                "<ns1:class>object.item.audioItem.musicTrack</ns1:class>"
                "<dc:creator>The Artist</dc:creator>"
                "<ns1:album>The Album</ns1:album>"
                "<ns1:originalTrackNumber>4</ns1:originalTrackNumber>"
                "</item>"
                '<item id="S://server/The%20Artist/The%20Album/'
                '05%20-%20Track%20Title%203.mp3" '
                'parentID="A:ALBUMARTIST/The%20Artist/The%20Album" restricted="true">'
                '<res protocolInfo="x-file-cifs:*:audio/mpeg:*">'
                "x-file-cifs://server/The%20Artist/The%20Album/"
                "05%20-%20Track%20Title%203.mp3</res>"
                "<ns1:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fserver%2fThe%2520"
                "Artist%2fThe%2520Album%2f05%2520-%2520Track%2520Title%25203.mp3"
                "&amp;v=432</ns1:albumArtURI>"
                "<dc:title>Track Title 3</dc:title>"
                "<ns1:class>object.item.audioItem.musicTrack</ns1:class>"
                "<dc:creator>The Artist</dc:creator>"
                "<ns1:album>The Album</ns1:album>"
                "<ns1:originalTrackNumber>5</ns1:originalTrackNumber>"
                "</item>"
                "</DIDL-Lite>"
            ),
            "TotalMatches": "3",
            "UpdateID": "0",
        }

        results = moco.music_library.search_track("The Artist", "The Album")

        assert len(results) == 3

        track = results[0]
        assert track.title == "Track Title 1"
        assert (
            track.item_id
            == "S://server/The%20Artist/The%20Album/03%20-%20Track%20Title%201.mp3"
        )
        track = results[1]
        assert track.title == "Track Title 2"
        assert (
            track.item_id
            == "S://server/The%20Artist/The%20Album/04%20-%20Track%20Title%202.m4a"
        )
        track = results[2]
        assert track.title == "Track Title 3"
        assert (
            track.item_id
            == "S://server/The%20Artist/The%20Album/05%20-%20Track%20Title%203.mp3"
        )

        moco.contentDirectory.Browse.assert_called_once_with(
            [
                ("ObjectID", "A:ALBUMARTIST/The%20Artist/The%20Album"),
                ("BrowseFlag", "BrowseDirectChildren"),
                ("Filter", "*"),
                ("StartingIndex", 0),
                ("RequestedCount", 100000),
                ("SortCriteria", ""),
            ]
        )

    def test_soco_library_updating(self, moco):
        moco.contentDirectory.GetShareIndexInProgress.return_value = {"IsIndexing": "0"}
        assert not moco.music_library.library_updating
        moco.contentDirectory.reset_mock()
        moco.contentDirectory.GetShareIndexInProgress.return_value = {"IsIndexing": "1"}
        assert moco.music_library.library_updating

    def test_soco_start_library_update(self, moco):
        moco.contentDirectory.RefreshShareIndex.return_value = True
        assert moco.music_library.start_library_update()
        moco.contentDirectory.RefreshShareIndex.assert_called_with(
            [
                ("AlbumArtistDisplayOption", ""),
            ]
        )

    def test_soco_list_library_shares(self, moco):
        # Tests with 2, 1 and 0 library shares
        moco.contentDirectory.Browse.return_value = {
            "TotalMatches": "2",
            "NumberReturned": "2",
            "UpdateID": "0",
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<container id="S://share_host/music_01/Music/Lossless" '
                'parentID="S:" restricted="true"><dc:title>//share_host/music_01/Music/'
                "Lossless"
                "</dc:title><upnp:class>object.container</upnp:class><res "
                'protocolInfo="x-rincon-playlist:*:*:*">'
                "x-rincon-playlist:RINCON_XXXXXXXXXXXXX1400"
                "#S://share_host/music_01/Music/Lossless</res></container>"
                '<container id="S://share_host_2/music_01" parentID="S:" '
                'restricted="true">'
                "<dc:title>//share_host_2/music_01</dc:title>"
                "<upnp:class>object.container"
                '</upnp:class><res protocolInfo="x-rincon-playlist:*:*:*">'
                "x-rincon-playlist"
                ":RINCON_XXXXXXXXXXXXX1400#S://share_host_2/music_01</res>"
                "</container></DIDL-Lite>"
            ),
        }
        results = moco.music_library.list_library_shares()
        assert len(results) == 2
        assert "//share_host/music_01/Music/Lossless" in results
        assert "//share_host_2/music_01" in results

        moco.contentDirectory.Browse.return_value = {
            "TotalMatches": "1",
            "NumberReturned": "1",
            "UpdateID": "0",
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<container id="S://share_host/music_01/Music/Lossless" parentID="S:" '
                'restricted="true">'
                "<dc:title>//share_host/music_01/Music/Lossless</dc:title>"
                "<upnp:class>object.container</upnp:class>"
                '<res protocolInfo="x-rincon-playlist:*:*:*">'
                "x-rincon-playlist:RINCON_XXXXXXXXXXXXXX400#"
                "S://share_host/music_01/Music/Lossless</res></container></DIDL-Lite>"
            ),
        }
        results = moco.music_library.list_library_shares()
        assert len(results) == 1
        assert "//share_host/music_01/Music/Lossless" in results

        moco.contentDirectory.Browse.return_value = {
            "TotalMatches": "0",
            "NumberReturned": "0",
            "UpdateID": "0",
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"/>'
            ),
        }
        results = moco.music_library.list_library_shares()
        assert len(results) == 0

    def test_soco_delete_library_share(self, moco):
        share = "//host/share"
        moco.music_library.delete_library_share(share)
        moco.contentDirectory.DestroyObject.assert_called_once_with(
            [("ObjectID", "S:" + share)]
        )
