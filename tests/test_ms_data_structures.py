# pylint: disable=star-args,no-member

"""Unit tests for the music service data structures."""


from xml.sax.saxutils import escape

import pytest

from soco.exceptions import DIDLMetadataError
from soco.ms_data_structures import (
    MSAlbum,
    MSAlbumList,
    MSArtist,
    MSArtistTracklist,
    MSCollection,
    MSFavorites,
    MSPlaylist,
    MSTrack,
)
from soco.xml import XML

##############################################################################
# Example XML and the content dict to compare with for MS items              #
##############################################################################
DIDL_TEMPLATE = """
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
<item id="{extended_id}" parentID="{parent_id}" restricted="true">
<dc:title>{title}</dc:title>
<upnp:class>{item_class}</upnp:class>
<desc id="cdudn"
 nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">{description}</desc>
</item>
</DIDL-Lite>
"""
DIDL_TEMPLATE = DIDL_TEMPLATE.replace("\n", "")

MS_TRACK_SEARCH_XML = """
<ns0:mediaMetadata xmlns:ns0="http://www.sonos.com/Services/1.1">
<ns0:id>trackid_24125935</ns0:id>
<ns0:itemType>track</ns0:itemType>
<ns0:mimeType>audio/aac</ns0:mimeType>
<ns0:title>Pilgrim</ns0:title>
<ns0:trackMetadata>
<ns0:artistId>artistid_4816276</ns0:artistId>
<ns0:artist>MØ</ns0:artist>
<ns0:composerId>artistid_4816276</ns0:composerId>
<ns0:composer>MØ</ns0:composer>
<ns0:albumId>albumid_24125922</ns0:albumId>
<ns0:album>Nytårsfesten 2014</ns0:album>
<ns0:albumArtistId>artistid_4816276</ns0:albumArtistId>
<ns0:albumArtist>MØ</ns0:albumArtist>
<ns0:duration>231</ns0:duration>
<ns0:albumArtURI>http://varnish01.music.aspiro.com/sca/imscale?h=90&amp;
w=90&amp;img=/content/sg19/vd00/music/prod/sonyddex/1386109801/
A10301A00030834072_20131203071914171/resources/A10301A00030834072_T-10764
_Image.jpg</ns0:albumArtURI>
<ns0:canPlay>true</ns0:canPlay>
<ns0:canSkip>true</ns0:canSkip>
<ns0:canAddToFavorites>true</ns0:canAddToFavorites>
</ns0:trackMetadata>
</ns0:mediaMetadata>
"""
MS_TRACK_SEARCH_XML = MS_TRACK_SEARCH_XML.replace("\n", "")
MS_TRACK_SEARCH_DICT = {
    "can_add_to_favorites": True,
    "composer": "M\xd8",
    "album_id": "albumid_24125922",
    "can_skip": True,
    "uri": "x-sonos-http:trackid_24125935.mp4?sid=20&flags=32",
    "item_id": "trackid_24125935",
    "item_type": "track",
    "extended_id": "00030020trackid_24125935",
    "duration": 231,
    "can_play": True,
    "composer_id": "artistid_4816276",
    "description": "SA_RINCON5127_4542255535",
    "album": "Nyt\xe5rsfesten 2014",
    "title": "Pilgrim",
    "artist": "M\xd8",
    "album_artist_id": "artistid_4816276",
    "album_art_uri": "http://varnish01.music.aspiro.com/sca/imscale?"
    "h=90&w=90&img=/content/sg19/vd00/music/prod/sonyddex"
    "/1386109801/A10301A00030834072_20131203071914171/"
    "resources/A10301A00030834072_T-10764_Image.jpg",
    "album_artist": "M\xd8",
    "parent_id": "00020064tracksearch:pilgrim",
    "service_id": 20,
    "artist_id": "artistid_4816276",
    "mime_type": "audio/aac",
}
MS_ALBUM_SEARCH_XML = """
<ns0:mediaCollection readOnly="true"
 xmlns:ns0="http://www.sonos.com/Services/1.1">
<ns0:id>albumid_5738780</ns0:id>
<ns0:itemType>album</ns0:itemType>
<ns0:title>Greatest De Unge År</ns0:title>
<ns0:artist>tv·2</ns0:artist>
<ns0:canPlay>true</ns0:canPlay>
<ns0:canAddToFavorites>true</ns0:canAddToFavorites>
<ns0:albumArtURI>http://varnish01.music.aspiro.com/sca/imscale?h=90&amp;w=90
&amp;img=/content/music8/prod/sonybmg/content/00000000000002304180/000/000/
000/000/056/501/97/00000000000005650197-1000x1000_72dpi_RGB_100Q.jpg
</ns0:albumArtURI>
</ns0:mediaCollection>
"""
MS_ALBUM_SEARCH_XML = MS_ALBUM_SEARCH_XML.replace("\n", "")
MS_ALBUM_SEARCH_DICT = {
    "can_add_to_favorites": True,
    "description": "SA_RINCON5127_4542255535",
    "artist": "tv\xb72",
    "title": "Greatest De Unge \xc5r",
    "album_art_uri": "http://varnish01.music.aspiro.com/sca/imscale?h=90&w=90"
    "&img=/content/music8/prod/sonybmg/content/"
    "00000000000002304180/000/000/000/000/056/501/97/"
    "00000000000005650197-1000x1000_72dpi_RGB_100Q.jpg",
    "uri": "x-rincon-cpcontainer:0004002calbumid_5738780",
    "parent_id": "00020064albumsearch:de unge",
    "item_type": "album",
    "extended_id": "0004002calbumid_5738780",
    "item_id": "albumid_5738780",
    "service_id": 20,
    "can_play": True,
}
MS_ARTIST_SEARCH_XML = """
<ns0:mediaCollection readOnly="true"
 xmlns:ns0="http://www.sonos.com/Services/1.1">
<ns0:id>artistid_4761386</ns0:id>
<ns0:itemType>artist</ns0:itemType>
<ns0:title>Fritjof Såheim</ns0:title>
<ns0:artist>Fritjof Såheim</ns0:artist>
<ns0:canAddToFavorites>true</ns0:canAddToFavorites>
<ns0:albumArtURI>http://varnish01.music.aspiro.com/im/im?h=42&amp;w=64&amp;
artistid=4761386</ns0:albumArtURI>
</ns0:mediaCollection>
"""
MS_ARTIST_SEARCH_XML = MS_ARTIST_SEARCH_XML.replace("\n", "")
MS_ARTIST_SEARCH_DICT = {
    "can_add_to_favorites": True,
    "description": "SA_RINCON5127_4542255535",
    "artist": "Fritjof S\xe5heim",
    "title": "Fritjof S\xe5heim",
    "album_art_uri": "http://varnish01.music.aspiro.com/im/im?h=42&w=64"
    "&artistid=4761386",
    "parent_id": "00020064artistsearch:Fritjof",
    "item_type": "artist",
    "extended_id": "10050024artistid_4761386",
    "item_id": "artistid_4761386",
    "service_id": 20,
}
MS_PLAYLIST_SEARCH_XML = """
<ns0:mediaCollection readOnly="true" xmlns:ns0="http://www.sonos.com/Services/1.1">
  <ns0:id>playlistid_133fe1ff-1f16-4300-b440-fb80573f19ce</ns0:id>
  <ns0:itemType>albumList</ns0:itemType>
  <ns0:title>Kunstnerliste: Dans &amp; Lær</ns0:title>
  <ns0:artist>39 sange</ns0:artist>
  <ns0:artistId>artistid_0</ns0:artistId>
  <ns0:canPlay>true</ns0:canPlay>
  <ns0:canEnumerate>true</ns0:canEnumerate>
  <ns0:canAddToFavorites>true</ns0:canAddToFavorites>
  <ns0:albumArtURI>http://varnish01.music.aspiro.com/im/im?h=160&amp;w=240&amp;rows=1&amp;cols=2&amp;artimg&amp;uuid=133fe1ff-1f16-4300-b440-fb80573f19ce</ns0:albumArtURI>
</ns0:mediaCollection>
"""
MS_PLAYLIST_SEARCH_XML = MS_PLAYLIST_SEARCH_XML.replace("\n", "")
MS_PLAYLIST_SEARCH_DICT = {
    "can_add_to_favorites": True,
    "description": "SA_RINCON5127_4542255535",
    "artist": "39 sange",
    "title": "Kunstnerliste: Dans & L\xe6r",
    "album_art_uri": "http://varnish01.music.aspiro.com/im/im?h=160&w=240&"
    "rows=1&cols=2&artimg&uuid=133fe1ff-1f16-4300-b440-"
    "fb80573f19ce",
    "uri": "x-rincon-cpcontainer:000d006cplaylistid_133fe1ff-1f16-4300-b440"
    "-fb80573f19ce",
    "parent_id": "00020064playlistsearch:Dans &",
    "item_type": "albumList",
    "extended_id": "000d006cplaylistid_133fe1ff-1f16-4300-b440-fb80573f19ce",
    "item_id": "playlistid_133fe1ff-1f16-4300-b440-fb80573f19ce",
    "service_id": 20,
    "artist_id": "artistid_0",
    "can_play": True,
    "can_enumerate": True,
}


class FakeMusicService:
    """A fake music service."""

    def __init__(self, username):
        self.description = "SA_RINCON5127_{}".format(username)
        self.service_id = 20

    @staticmethod
    def id_to_extended_id(item_id, item_class):
        """ID to extended ID method."""
        id_prefix = {
            MSTrack: "00030020",
            MSAlbum: "0004002c",
            MSArtist: "10050024",
            MSAlbumList: "000d006c",
            MSPlaylist: "0006006c",
            MSArtistTracklist: "100f006c",
            MSFavorites: None,  # This one is unknown
            MSCollection: None,  # This one is unknown
        }
        out = id_prefix[item_class]
        if out:
            out += item_id
        return out

    @staticmethod
    def form_uri(item_content, item_class):
        """Form the URI."""
        mime_type_to_extension = {"audio/aac": "mp4"}
        uris = {
            MSTrack: "x-sonos-http:{item_id}.{extension}?sid={service_id}&" "flags=32",
            MSAlbum: "x-rincon-cpcontainer:{extended_id}",
            MSAlbumList: "x-rincon-cpcontainer:{extended_id}",
            MSPlaylist: "x-rincon-cpcontainer:{extended_id}",
            MSArtistTracklist: "x-rincon-cpcontainer:{extended_id}",
        }
        extension = None
        if "mime_type" in item_content:
            extension = mime_type_to_extension[item_content["mime_type"]]
        out = uris.get(item_class)
        if out:
            # pylint: disable=star-args
            out = out.format(extension=extension, **item_content)
        return out


FAKE_MUSIC_SERVICE = FakeMusicService("4542255535")


def getter_attributes_test(name, from_xml, from_dict, result):
    """Test if the getters return the right value."""
    assert getattr(from_xml, name) == result
    assert getattr(from_dict, name) == result


def common_tests(class_, xml_, dict_, parent_id, helpers):
    """Common tests for the MS classes."""
    xml_content = XML.fromstring(xml_.encode("utf8"))

    # MusicServiceItem.from_xml and MusicServiceItem.to_dict
    item_from_xml = class_.from_xml(xml_content, FAKE_MUSIC_SERVICE, parent_id)
    assert item_from_xml.to_dict == dict_

    # MusicServiceItem.from_dict and MusicServiceItem.to_dict
    item_from_dict = class_.from_dict(dict_)
    assert item_from_dict.to_dict == dict_

    # MusicServiceItem.didl_metadata
    # NOTE! These tests is reliant on the attributes being put in the same
    # order by ElementTree and so it might fail if that changes
    if item_from_xml.can_play:
        dict_encoded = {}
        for key, value in dict_.items():
            try:
                is_str = isinstance(value, unicode)
            except NameError:
                is_str = isinstance(value, str)
            if is_str:
                dict_encoded[key] = (
                    escape(value).encode("ascii", "xmlcharrefreplace").decode("ascii")
                )

            else:
                dict_encoded[key] = value
        didl = DIDL_TEMPLATE.format(item_class=class_.item_class, **dict_encoded)

        assert helpers.compare_xml(item_from_xml.didl_metadata, XML.fromstring(didl))
        assert helpers.compare_xml(item_from_dict.didl_metadata, XML.fromstring(didl))
    else:
        with pytest.raises(DIDLMetadataError):
            # pylint: disable=pointless-statement
            item_from_xml.didl_metadata

    # Text attributes with mandatory content
    for name in ["item_id", "extended_id", "title", "service_id"]:
        getter_attributes_test(name, item_from_xml, item_from_dict, dict_[name])
    # Text attributes with voluntary content
    for name in ["parent_id", "album_art_uri"]:
        getter_attributes_test(name, item_from_xml, item_from_dict, dict_.get(name))
    # Boolean attribute
    getter_attributes_test(
        "can_play", item_from_xml, item_from_dict, bool(dict_.get("can_play"))
    )
    return item_from_xml, item_from_dict


def test_ms_track_search(helpers):
    """Test the MSTrack item when instantiated from a search."""
    item_from_xml, item_from_dict = common_tests(
        MSTrack,
        MS_TRACK_SEARCH_XML,
        MS_TRACK_SEARCH_DICT,
        "00020064tracksearch:pilgrim",
        helpers,
    )
    getter_attributes_test(
        "artist", item_from_xml, item_from_dict, MS_TRACK_SEARCH_DICT.get("artist")
    )
    getter_attributes_test(
        "uri", item_from_xml, item_from_dict, MS_TRACK_SEARCH_DICT["uri"]
    )


def test_ms_album_search(helpers):
    """Test the MSAlbum item when instantiated from a search."""
    item_from_xml, item_from_dict = common_tests(
        MSAlbum,
        MS_ALBUM_SEARCH_XML,
        MS_ALBUM_SEARCH_DICT,
        "00020064albumsearch:de unge",
        helpers,
    )
    getter_attributes_test(
        "artist", item_from_xml, item_from_dict, MS_ALBUM_SEARCH_DICT.get("artist")
    )
    getter_attributes_test(
        "uri", item_from_xml, item_from_dict, MS_ALBUM_SEARCH_DICT["uri"]
    )


def test_ms_artist_search(helpers):
    """Test the MSAlbum item when instantiated from a search."""
    common_tests(
        MSArtist,
        MS_ARTIST_SEARCH_XML,
        MS_ARTIST_SEARCH_DICT,
        "00020064artistsearch:Fritjof",
        helpers,
    )


def test_ms_playlist_search(helpers):
    """Test the MSAlbum item when instantiated from a search."""
    item_from_xml, item_from_dict = common_tests(
        MSAlbumList,
        MS_PLAYLIST_SEARCH_XML,
        MS_PLAYLIST_SEARCH_DICT,
        "00020064playlistsearch:Dans &",
        helpers,
    )
    getter_attributes_test(
        "uri", item_from_xml, item_from_dict, MS_PLAYLIST_SEARCH_DICT["uri"]
    )
