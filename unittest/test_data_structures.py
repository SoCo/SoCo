# -*- coding: utf-8 -*-
# pylint: disable=R0913,W0142

"""Module to test the data structure classes with pytest"""

from __future__ import unicode_literals
try:
    import xml.etree.cElementTree as XML
except ImportError:
    import xml.etree.ElementTree as XML
import textwrap

# at the moment, all these tests will fail
import pytest
pytestmark = pytest.mark.xfail

from soco import data_structures

TITLE = 'Dummy title with non ascii chars æøå'
ALBUM = '«Album title with fancy characters»'
ART_URI = 'http://fake_address.jpg'
CREATOR = 'Creative Ŋ Ħ̛ Þ dummy'
XML_TEMPLATE = u"""
  <DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
  <item id="{item_id}" parentID="{parent_id}"
     restricted="true">
  <dc:title>{title}</dc:title>
  <upnp:class>{item_class}</upnp:class>
  <desc id="cdudn"
     nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">
    RINCON_AssociatedZPUDN</desc></item></DIDL-Lite>
    """
XML_TEMPLATE = textwrap.dedent(XML_TEMPLATE).replace('\n', '').strip()

##############################################################################
# Example XML and the content dict to compare with for ML items              #
##############################################################################
TRACK_XML = """
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
<item id="S://TLE-SERVER/share/ogg/Mozart%20-%20Orpheus%20Orchestra_convert/
5-Mozart-...%20-II%20Adagio.ogg" parentID="A:TRACKS" restricted="true">
<res protocolInfo="x-file-cifs:*:application/ogg:*">x-file-cifs://TLE-SERVER/
share/ogg/Mozart%20-%20Orpheus%20Orchestra_convert/5-Mozart-...%20-II%20
Adagio.ogg</res>
<upnp:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fTLE-SERVER
%2fshare%2fogg%2fMozart%2520-%2520Orpheus%2520Orchestra_convert%2f5-Mozart-
...%2520-II%2520Adagio.ogg&amp;v=2</upnp:albumArtURI>
<dc:title>... - II  Adagio</dc:title>
<upnp:class>object.item.audioItem.musicTrack</upnp:class>
<dc:creator>Mozart</dc:creator>
<upnp:album>Orpheus Orchestra</upnp:album>
<upnp:originalTrackNumber>5</upnp:originalTrackNumber>
</item>
</DIDL-Lite>"""
TRACK_XML = TRACK_XML.replace('\n', '')
TRACK_DICT = {
    'album': 'Orpheus Orchestra',
    'creator': 'Mozart',
    'title': '... - II  Adagio',
    'uri': 'x-file-cifs://TLE-SERVER/share/ogg/Mozart'
           '%20-%20Orpheus%20Orchestra_convert/5-Mozart-...%20-II%20'
           'Adagio.ogg',
    'album_art_uri': '/getaa?u=x-file-cifs%3a%2f%2fTLE-SERVER'
                     '%2fshare%2fogg%2fMozart%2520-%2520Orpheus%2520'
                     'Orchestra_convert%2f5-Mozart-...%2520-II%2520'
                     'Adagio.ogg&v=2',
    'parent_id': 'A:TRACKS',
    'item_id' : 'S://TLE-SERVER/share/ogg/Mozart%20-%20Orpheus%20Orchestra_convert/5-Mozart-...%20-II%20Adagio.ogg',
    'original_track_number': 5}
ALBUM_XML = """
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
<container xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
 id="A:ALBUM/...and%20Justice%20for%20All" parentID="A:ALBUM"
 restricted="true">
<dc:title>...and Justice for All</dc:title>
<upnp:class>object.container.album.musicAlbum</upnp:class>
<res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:
RINCON_000E5884455C01400#A:ALBUM/...and%20Justice%20for%20All</res>
<dc:creator>Metallica</dc:creator>
<upnp:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fTLE-SERVER%2fshare%2fogg%2f
Metallica%2520-%2520and%2520Justice%2520for%2520All%2f01%2520-%2520Blackened.
ogg&amp;v=2</upnp:albumArtURI>
</container>
</DIDL-Lite>"""
ALBUM_XML = ALBUM_XML.replace('\n', '')
ALBUM_DICT = {
    'title': '...and Justice for All',
    'parent_id': 'A:ALBUM',
    'item_id' : 'A:ALBUM/...and%20Justice%20for%20All',
    'uri': 'x-rincon-playlist:RINCON_000E5884455C01400#A:ALBUM/...and%20'
           'Justice%20for%20All',
    'album_art_uri': '/getaa?u=x-file-cifs%3a%2f%2fTLE-SERVER%2fshare%2fogg'
                     '%2fMetallica%2520-%2520and%2520Justice%2520for%2520All'
                     '%2f01%2520-%2520Blackened.ogg&v=2',
    'creator': 'Metallica'}
ARTIST_XML = """
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
<container xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" id="A:ARTIST/10%20Years"
 parentID="A:ARTIST" restricted="true">
<dc:title>10 Years</dc:title>
<upnp:class>object.container.person.musicArtist</upnp:class>
<res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:
RINCON_000E5884455C01400#A:ARTIST/10%20Years</res>
</container></DIDL-Lite>"""
ARTIST_XML = ARTIST_XML.replace('\n', '')
ARTIST_DICT = {
    'parent_id': 'A:ARTIST',
    'item_id' : 'A:ARTIST/10%20Years',
    'uri': 'x-rincon-playlist:RINCON_000E5884455C01400#A:ARTIST/10%20Years',
    'title': '10 Years',
}
GENRE_XML = """
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
<container xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" id="A:GENRE/Acid"
 parentID="A:GENRE" restricted="true">
<dc:title>Acid</dc:title>
<upnp:class>object.container.genre.musicGenre</upnp:class>
<res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:
RINCON_000E5884455C01400#A:GENRE/Acid</res>
</container></DIDL-Lite>"""
GENRE_XML = GENRE_XML.replace('\n', '')
GENRE_DICT = {
    'parent_id': 'A:GENRE',
    'item_id': 'A:GENRE/Acid',
    'uri': 'x-rincon-playlist:RINCON_000E5884455C01400#A:GENRE/Acid',
    'title': 'Acid'
}
COMPOSER_XML = """
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
<container xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
 id="A:COMPOSER/A.%20Kiedis%2fFlea%2fJ.%20Frusciante%2fC.%20Smith"
 parentID="A:COMPOSER" restricted="true">
<dc:title>A. Kiedis/Flea/J. Frusciante/C. Smith</dc:title>
<upnp:class>object.container.person.composer</upnp:class>
<res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:RINCON_
000E5884455C01400#A:COMPOSER/A.%20Kiedis%2fFlea%2fJ.%20Frusciante%2fC.%20
Smith</res>
</container></DIDL-Lite>"""
COMPOSER_XML = COMPOSER_XML.replace('\n', '')
COMPOSER_DICT = {
    'parent_id': 'A:COMPOSER',
    'item_id' : 'A:COMPOSER/A.%20Kiedis%2fFlea%2fJ.%20Frusciante%2fC.%20Smith',
    'uri': 'x-rincon-playlist:RINCON_000E5884455C01400#A:COMPOSER/'
           'A.%20Kiedis%2fFlea%2fJ.%20Frusciante%2fC.%20Smith',
    'title': 'A. Kiedis/Flea/J. Frusciante/C. Smith'
}
PLAYLIST_XML = """
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
<container xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
 id="S://TLE-SERVER/share/mp3/Trentem%c3%b8ller%20-%20The%20
Trentem%c3%b8ller%20Chronicles/-%3dTrentem%c3%b8ller%20-%20The%20
Trentem%c3%b8ller%20Chronicles%20(CD%201).m3u" parentID="A:PLAYLISTS"
 restricted="true">
<res protocolInfo="x-file-cifs:*:audio/mpegurl:*">x-file-cifs://TLE-SERVER/
share/mp3/Trentem%c3%b8ller%20-%20The%20Trentem%c3%b8ller%20Chronicles/
-%3dTrentem%c3%b8ller%20-%20The%20Trentem%c3%b8ller%20Chronicles%20(CD%201)
.m3u</res>
<dc:title>-=Trentem&#248;ller - The Trentem&#248;ller Chronicles (CD 1).m3u
</dc:title>
<upnp:class>object.container.playlistContainer</upnp:class>
</container></DIDL-Lite>"""
PLAYLIST_XML = PLAYLIST_XML.replace('\n', '')
PLAYLIST_DICT = {
    'parent_id': 'A:PLAYLISTS',
    'item_id' : 'S://TLE-SERVER/share/mp3/Trentem%c3%b8ller%20-%20The%20'
                'Trentem%c3%b8ller%20Chronicles/-%3dTrentem%c3%b8ller%20-%20'
                'The%20Trentem%c3%b8ller%20Chronicles%20(CD%201).m3u',
    'uri': 'x-file-cifs://TLE-SERVER/share/mp3/Trentem%c3%b8ller%20-%20The%20'
           'Trentem%c3%b8ller%20Chronicles/-%3dTrentem%c3%b8ller%20-%20The%20'
           'Trentem%c3%b8ller%20Chronicles%20(CD%201).m3u',
    'title': '-=Trentem\xf8ller - The Trentem\xf8ller Chronicles (CD 1).m3u'}
SONOS_PLAYLIST_XML = """
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
<container xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
 id="SQ:13" parentID="SQ:"
 restricted="true">
<res protocolInfo="x-file-cifs:*:audio/mpegurl:*">file:///jffs/settings/savedqueues.rsq#13 title: Koop</res>
<dc:title>Koop</dc:title>
<upnp:class>object.container.playlistContainer</upnp:class>
</container></DIDL-Lite>"""
SONOS_PLAYLIST_XML = SONOS_PLAYLIST_XML.replace('\n', '')
SONOS_PLAYLIST_DICT = {
    'parent_id': 'SQ:',
    'item_id' : 'SQ:13',
    'uri': 'file:///jffs/settings/savedqueues.rsq#13 title: Koop',
    'title': 'Koop'}
SHARE_XML = """
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"><container xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" id="S://TLE-SERVER/share"
 parentID="S:" restricted="true">
<dc:title>//TLE-SERVER/share</dc:title>
<upnp:class>object.container</upnp:class>
<res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:RINCON_
000E5884455C01400#S://TLE-SERVER/share</res>
</container></DIDL-Lite>"""
SHARE_XML = SHARE_XML.replace('\n', '')
SHARE_DICT = {
    'parent_id': 'S:',
    'item_id': 'S://TLE-SERVER/share',
    'uri': 'x-rincon-playlist:RINCON_000E5884455C01400#S://TLE-SERVER/share',
    'title': '//TLE-SERVER/share'
}
ALBUMLIST_XML = """
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"><container xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" id="A:ALBUM"
 parentID="A:" restricted="true">
<dc:title>Albums</dc:title>
<upnp:class>object.container.albumlist</upnp:class>
<res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:RINCON_
000E5884455C01400#A:ALBUM</res>
</container></DIDL-Lite>
"""
ALBUMLIST_XML = ALBUMLIST_XML.replace('\n', '')
ALBUMLIST_DICT = {
    'parent_id': 'A:',
    'item_id': 'A:ALBUM',
    'uri': 'x-rincon-playlist:RINCON_000E5884455C01400#A:ALBUM',
    'title': 'Albums'
}
QUEUE_XML1 = """
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
<item xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" id="Q:0/1" parentID="Q:0"
 restricted="true">
<res duration="0:04:43" protocolInfo="sonos.com-mms:*:audio/x-ms-wma:*">
x-sonos-mms:AnyArtistTrack%3a126778459?sid=50&amp;flags=32</res>
<upnp:albumArtURI>/getaa?s=1&amp;u=x-sonos-mms%3aAnyArtistTrack%253a126778459
%3fsid%3d50%26flags%3d32</upnp:albumArtURI>
<dc:title>Airworthy</dc:title>
<upnp:class>object.item.audioItem.musicTrack</upnp:class>
<dc:creator>Randi Laubek</dc:creator>
<upnp:album>Almost Gracefully</upnp:album>
</item></DIDL-Lite>"""
QUEUE_XML1 = QUEUE_XML1.replace('\n', '')
QUEUE_DICT1 = {
    'album': 'Almost Gracefully',
    'creator': 'Randi Laubek',
    'title': 'Airworthy',
    'uri': 'x-sonos-mms:AnyArtistTrack%3a126778459?sid=50&flags=32',
    'album_art_uri': '/getaa?s=1&u=x-sonos-mms%3aAnyArtistTrack%253a126778459'
                     '%3fsid%3d50%26flags%3d32',
    'item_class': 'object.item.audioItem.musicTrack',
    'original_track_number': None
}

QUEUE_XML2 = """
<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
<item xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" id="Q:0/2" parentID="Q:0"
 restricted="true">
<res protocolInfo="x-file-cifs:*:audio/flac:*">x-file-cifs://TLE-SERVER/
share/flac/Agnes%20Obel%20-%20Philharmonics/1%20-%20Falling,%20Catching.flac
</res>
<upnp:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fTLE-SERVER%2fshare%2fflac%2f
Agnes%2520Obel%2520-%2520Philharmonics%2f1%2520-%2520Falling,%2520
Catching.flac&amp;v=2</upnp:albumArtURI>
<dc:title>Falling, Catching</dc:title>
<upnp:class>object.item.audioItem.musicTrack</upnp:class>
<dc:creator>Agnes Obel</dc:creator>
<upnp:album>Philharmonics</upnp:album>
<upnp:originalTrackNumber>1</upnp:originalTrackNumber>
</item></DIDL-Lite>
"""
QUEUE_XML2 = QUEUE_XML2.replace('\n', '')
QUEUE_DICT2 = {
    'album': 'Philharmonics',
    'creator': 'Agnes Obel',
    'title': 'Falling, Catching',
    'uri': 'x-file-cifs://TLE-SERVER/share/flac/Agnes%20Obel%20-%20'
           'Philharmonics/1%20-%20Falling,%20Catching.flac',
    'album_art_uri': '/getaa?u=x-file-cifs%3a%2f%2fTLE-SERVER%2fshare%2fflac'
                     '%2fAgnes%2520Obel%2520-%2520Philharmonics%2f1%2520-'
                     '%2520Falling,%2520Catching.flac&v=2',
    'item_class': 'object.item.audioItem.musicTrack',
    'original_track_number': 1
}



# Helper test functions
def set_and_get_test(instance, content, key):
    """Test get and set of a single unicode attribute

    :param instance: The object to be tested
    :param content: The content dict that contains the test values
    :param key: The name of the attribute and key in content to test
    """
    # Test if the attribute has the correct value
    original = getattr(instance, key)
    assert original == content[key]
    # Test if the attribute value can be changed and return the new value
    setattr(instance, key, original + '!addition¡')
    assert getattr(instance, key) == original + '!addition¡'
    # Reset
    setattr(instance, key, original)


def common_tests(item_class, item_id, instance, content, item_xml, item_dict):
    """Test all the common methods inherited from DidlObject

    :param parent_id: The parent ID of the class
    :param item_id: The expected item_id result for instance
    :param instance: The main object to be tested
    :param content: The content dict that corresponds to instance
    :param item_xml: A real XML example for from_xml
    :param item_dict: The content dict result corresponding to item_xml
    """
    # from_xml, this test uses real data examples
    instance2 = instance.__class__.from_xml(
        XML.fromstring(item_xml.encode('utf8')))
    assert instance2.to_dict == item_dict

    # from_dict and to_dict
    instance3 = instance.__class__.from_dict(content)
    assert instance3.to_dict == content

    # Test item_id
    assert instance.item_id == item_id

    # Test didl_metadata
    content1 = content.copy()
    xml = XML_TEMPLATE.format(item_class=item_class,
                               **content1)

    assert XML.tostring(instance.didl_metadata) == item_xml

    # Test common attributes
    for key in  ['title', 'parent_id', 'item_id']:
        set_and_get_test(instance, content, key)

    # Test equals (should fail if we change any attribute)
    assert instance == instance3
    for key in content.keys():
        original = getattr(instance3, key)
        if key == 'original_track_number':
            setattr(instance3, key, original + 1)
        else:
            setattr(instance3, key, original + '!addition¡')
        assert instance != instance3
        setattr(instance3, key, original)

    # un-assigned attributes should not be assigned
    instance4 = instance.__class__(content['title'],
                                   content['parent_id'],
                                   content['item_id'])
    for key in content.keys():
        if key not in ['title', 'parent_id', 'item_id', 'creator']:
            assert not hasattr(instance4, key)


# The functions that test the different classes
def test_didltrack():
    """Test the DidlMusicTrack class"""
    # Set the tests up
    uri = 'x-file-cifs://dummy_uri'
    item_id = 'S://TLE-SERVER/share/ogg/Mozart%20-%20Orpheus%20Orchestra_convert/5-Mozart-...%20-II%20Adagio.ogg'
    kwargs = {'album': ALBUM, 'album_art_uri': ART_URI, 'creator': CREATOR,
              'original_track_number': 47, 'uri': uri}
    content = {'title': TITLE, 'parent_id': 'A:TRACKS',
               'item_id' : item_id}
    content.update(kwargs)
    track = data_structures.DidlMusicTrack(title=TITLE, parent_id='A:TRACKS', item_id=item_id, **kwargs)

    # Run tests on inherited methods and attributes
    common_tests('object.item.audioItem.musicTrack', item_id,
                 track, content, TRACK_XML, TRACK_DICT)

    # Test class specific attributes
    for key in ['album', 'album_art_uri', 'creator']:
        set_and_get_test(track, content, key)

    assert track.original_track_number == 47
    track.original_track_number = 42
    assert track.original_track_number == 42
    track.original_track_number = 47


def test_didlmusicalbum():
    """Test the DidlMusicAlbum class"""
    # Set the tests up
    uri = 'x-rincon-playlist:RINCON_000E5884455C01400#A:ALBUM/dummy_album'
    item_id = 'A:ALBUM/dummy_album'
    kwargs = {'album_art_uri': ART_URI, 'creator': CREATOR, 'uri': uri}
    album = data_structures.DidlMusicAlbum(TITLE, 'A:ALBUM', item_id, **kwargs)

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'parent_id': 'A:ALBUM',
               'item_id' : item_id}
    content.update(kwargs)
    common_tests('object.container.album.musicAlbum', item_id,
                 album, content, ALBUM_XML, ALBUM_DICT)

    # Test class specific attributes
    for key in ['album_art_uri', 'creator']:
        set_and_get_test(album, content, key)


def test_didlartist():
    """Test the DidlMusicArtist class"""
    # Set the tests up
    uri = 'x-rincon-playlist:RINCON_000E5884455C01400#A:ARTIST/10%20Years'
    item_id = 'A:ARTIST/10%20Years'
    artist = data_structures.DidlMusicArtist(uri=uri, title=TITLE,
        parent_id='A:ARTIST', item_id=item_id)

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'parent_id': 'A:ARTIST',
               'item_id' : item_id}
    common_tests('object.container.person.musicArtist', item_id,
                 artist, content, ARTIST_XML, ARTIST_DICT)


def test_didlmusicgenre():
    """Test the DidlMusicGenre class"""
    # Set the tests up
    uri = 'x-rincon-playlist:RINCON_000E5884455C01400#A:GENRE/Acid'
    item_id = 'A:GENRE/Acid'
    genre = data_structures.DidlMusicGenre(uri=uri, title=TITLE, parent_id='A:GENRE', item_id=item_id)

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'parent_id': 'A:GENRE',
               'item_id' : item_id}
    common_tests('object.container.genre.musicGenre', 'A:GENRE/Acid', genre,
                 content, GENRE_XML, GENRE_DICT)


def test_didlcomposer():
    """Test the DidlComposer class"""
    # Set the tests up
    uri = 'x-rincon-playlist:RINCON_000E5884455C01400#A:COMPOSER/A.%20Kiedis'\
          '%2fFlea%2fJ.%20Frusciante%2fC.%20Smith'
    item_id = 'A:COMPOSER/A.%20Kiedis%2fFlea%2fJ.%20Frusciante%2fC.%20Smith'
    composer = data_structures.DidlComposer(uri=uri, title=TITLE,
        parent_id='A:COMPOSER', item_id=item_id)

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'parent_id': 'A:COMPOSER',
               'item_id' : item_id}
    common_tests('object.container.person.composer',
                 item_id, composer, content, COMPOSER_XML, COMPOSER_DICT)


def test_didlplaylist():
    """Test the DidlPlaylistContainer class"""
    # Set the tests up
    uri = 'x-file-cifs://TLE-SERVER/share/mp3/Trentem%c3%b8ller%20-%20The%20'\
          'Trentem%c3%b8ller%20Chronicles/-%3dTrentem%c3%b8ller%20-%20The%20'\
          'Trentem%c3%b8ller%20Chronicles%20(CD%201).m3u'
    item_id = 'S://TLE-SERVER/share/mp3/Trentem%c3%b8ller%20-%20The%20Trentem%c3%b8ller%20Chronicles/-%3dTrentem%c3%b8ller%20-%20The%20Trentem%c3%b8ller%20Chronicles%20(CD%201).m3u'
    playlist = data_structures.DidlPlaylistContainer(uri=uri, title=TITLE,
        parent_id='A:PLAYLISTS', item_id=item_id)

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'parent_id': 'A:PLAYLISTS',
               'item_id' : item_id}
    common_tests('object.container.playlistContainer',
                 item_id, playlist, content,
                 PLAYLIST_XML, PLAYLIST_DICT)


def test_didlPlaylistContainer():
    """Test the DidlPlaylistContainer class"""
    # Set the tests up
    uri = 'file:///jffs/settings/savedqueues.rsq#13 title: Koop'
    item_id = 'SQ:13'
    playlist = data_structures.DidlPlaylistContainer(uri=uri, title=TITLE,
        parent_id='SQ:', item_id=item_id)

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'parent_id': 'SQ:',
               'item_id' : item_id}
    common_tests('object.container.playlistContainer', item_id,
          playlist, content, SONOS_PLAYLIST_XML, SONOS_PLAYLIST_DICT)


def test_didlshare():
    """Test the DidlShare class"""
    # Set the tests up
    uri = 'x-rincon-playlist:RINCON_000E5884455C01400#S://TLE-SERVER/share'
    item_id = 'S://TLE-SERVER/share'
    share = data_structures.DidlContainer(uri=uri, title=TITLE,
        parent_id='S:', item_id=item_id)

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'parent_id': 'S:',
               'item_id' : item_id}
    common_tests('object.container', item_id, share, content,
                 SHARE_XML, SHARE_DICT)


def test_didlalbumlist():
    """Test the DidlAlbumList class"""
    # Sets the tests up
    uri = 'x-rincon-playlist:RINCON_000E5884455C01400#A:ALBUM'
    item_id = 'A:ALBUM'
    albumlist = data_structures.DidlAlbumList(uri=uri, title=TITLE,
        parent_id='A:', item_id=item_id)

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'parent_id': 'A:',
               'item_id' : item_id}
    common_tests('object.container.albumlist', item_id, albumlist, content,
                 ALBUMLIST_XML, ALBUMLIST_DICT)


def test_ns_tag():
    """Test the ns_tag module function"""
    namespaces = ['http://purl.org/dc/elements/1.1/',
                  'urn:schemas-upnp-org:metadata-1-0/upnp/',
                  'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/']
    for ns_in, namespace in zip(['dc', 'upnp', ''], namespaces):
        res = data_structures.ns_tag(ns_in, 'testtag')
        correct = '{{{0}}}{1}'.format(namespace, 'testtag')
        assert res == correct


def test_get_ml_item():
    """Test the get_ml_item medule function"""
    xmls = [TRACK_XML,
            ALBUM_XML,
            ARTIST_XML,
            GENRE_XML,
            COMPOSER_XML,
            PLAYLIST_XML]
    classes = [data_structures.DidlMusicTrack,
               data_structures.DidlMusicAlbum,
               data_structures.DidlMusicArtist,
               data_structures.DidlMusicGenre,
               data_structures.DidlComposer,
               data_structures.DidlPlaylistContainer]
    for xml, class_ in zip(xmls, classes):
        etree = XML.fromstring(xml.encode('utf-8'))
        item = data_structures.get_ml_item(etree)
        assert item.__class__ == class_
