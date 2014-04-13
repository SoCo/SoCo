# -*- coding: utf-8 -*-
# pylint: disable=R0913,W0142

"""Module to test the data structure classes with pytest"""

from __future__ import unicode_literals
try:
    import xml.etree.cElementTree as XML
except ImportError:
    import xml.etree.ElementTree as XML
import textwrap

from soco import data_structures

TITLE = 'Dummy title with non ascii chars æøå'
ALBUM = '«Album title with fancy characters»'
ART_URI = 'http://fake_address.jpg'
CREATOR = 'Creative Ŋ Ħ̛ Þ dummy'
XML_TEMPLATE = """
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

# Example XML and the content dict to compare with
TRACK_XML = """
<item xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
 id="S://TLE-SERVER/share/ogg/Mozart%20-%20Orpheus%20Orchestra_convert/
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
</item>"""
TRACK_DICT = {
    'album': 'Orpheus Orchestra',
    'creator': 'Mozart',
    'title': '... - II  Adagio',
    'uri': 'x-file-cifs://TLE-SERVER/\nshare/ogg/Mozart'
           '%20-%20Orpheus%20Orchestra_convert/5-Mozart-...%20-II%20'
           '\nAdagio.ogg',
    'album_art_uri': '/getaa?u=x-file-cifs%3a%2f%2fTLE-SERVER'
                     '\n%2fshare%2fogg%2fMozart%2520-%2520Orpheus%2520'
                     'Orchestra_convert%2f5-Mozart-\n...%2520-II%2520'
                     'Adagio.ogg&v=2',
    'item_class': 'object.item.audioItem.musicTrack',
    'original_track_number': 5}
ALBUM_XML = """
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
</container>"""
ALBUM_XML = ALBUM_XML.replace('\n', '')
ALBUM_DICT = {
    'title': '...and Justice for All',
    'item_class': 'object.container.album.musicAlbum',
    'uri': 'x-rincon-playlist:RINCON_000E5884455C01400#A:ALBUM/...and%20'
           'Justice%20for%20All',
    'album_art_uri': '/getaa?u=x-file-cifs%3a%2f%2fTLE-SERVER%2fshare%2fogg'
                     '%2fMetallica%2520-%2520and%2520Justice%2520for%2520All'
                     '%2f01%2520-%2520Blackened.ogg&v=2',
    'creator': 'Metallica'}
ARTIST_XML = """
<container xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" id="A:ARTIST/10%20Years"
 parentID="A:ARTIST" restricted="true">
  <dc:title>10 Years</dc:title>
  <upnp:class>object.container.person.musicArtist</upnp:class>
  <res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:
RINCON_000E5884455C01400#A:ARTIST/10%20Years</res>
</container>"""
ARTIST_XML = ARTIST_XML.replace('\n', '')
ARTIST_DICT = {
    'item_class': 'object.container.person.musicArtist',
    'uri': 'x-rincon-playlist:RINCON_000E5884455C01400#A:ARTIST/10%20Years',
    'title': '10 Years'
}
ALBUMARTIST_XML = """
<container xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
 id="A:ALBUMARTIST/3%20Doors%20Down" parentID="A:ALBUMARTIST"
 restricted="true">
  <dc:title>3 Doors Down</dc:title>
  <upnp:class>object.container.person.musicArtist</upnp:class>
  <res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:RINCON_
000E5884455C01400#A:ALBUMARTIST/3%20Doors%20Down</res>
</container>"""
ALBUMARTIST_XML = ALBUMARTIST_XML.replace('\n', '')
ALBUMARTIST_DICT = {
    'item_class': 'object.container.person.musicArtist',
    'uri': 'x-rincon-playlist:RINCON_000E5884455C01400#A:ALBUMARTIST/'
           '3%20Doors%20Down',
    'title': '3 Doors Down'
}
GENRE_XML = """
<container xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" id="A:GENRE/Acid"
 parentID="A:GENRE" restricted="true">
  <dc:title>Acid</dc:title>
  <upnp:class>object.container.genre.musicGenre</upnp:class>
  <res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:
RINCON_000E5884455C01400#A:GENRE/Acid</res>
</container>"""
GENRE_XML = GENRE_XML.replace('\n', '')
GENRE_DICT = {
    'item_class': 'object.container.genre.musicGenre',
    'uri': 'x-rincon-playlist:RINCON_000E5884455C01400#A:GENRE/Acid',
    'title': 'Acid'
}
COMPOSER_XML = """
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
</container>"""
COMPOSER_XML = COMPOSER_XML.replace('\n', '')
COMPOSER_DICT = {
    'item_class': 'object.container.person.composer',
    'uri': 'x-rincon-playlist:RINCON_000E5884455C01400#A:COMPOSER/'
           'A.%20Kiedis%2fFlea%2fJ.%20Frusciante%2fC.%20Smith',
    'title': 'A. Kiedis/Flea/J. Frusciante/C. Smith'
}
PLAYLIST_XML = """
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
</container>"""
PLAYLIST_XML = PLAYLIST_XML.replace('\n', '')
PLAYLIST_DICT = {
    'item_class': 'object.container.playlistContainer',
    'uri': 'x-file-cifs://TLE-SERVER/share/mp3/Trentem%c3%b8ller%20-%20The%20'
           'Trentem%c3%b8ller%20Chronicles/-%3dTrentem%c3%b8ller%20-%20The%20'
           'Trentem%c3%b8ller%20Chronicles%20(CD%201).m3u',
    'title': '-=Trentem\xf8ller - The Trentem\xf8ller Chronicles (CD 1).m3u'}
SHARE_XML = """
<container xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" id="S://TLE-SERVER/share"
 parentID="S:" restricted="true">
  <dc:title>//TLE-SERVER/share</dc:title>
  <upnp:class>object.container</upnp:class>
  <res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:RINCON_
000E5884455C01400#S://TLE-SERVER/share</res>
</container>"""
SHARE_XML = SHARE_XML.replace('\n', '')
SHARE_DICT = {
    'item_class': 'object.container',
    'uri': 'x-rincon-playlist:RINCON_000E5884455C01400#S://TLE-SERVER/share',
    'title': '//TLE-SERVER/share'
}
QUEUE_XML1 = """
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
</item>"""
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
<item xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
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
</item>
"""
QUEUE_XML2 = QUEUE_XML2.replace('\n', '')
QUEUE_DICT2 = {
    'album': 'Philharmonics',
    'creator': 'Agnes Obel',
    'title': 'Falling, Catching',
    'uri': 'x-file-cifs://TLE-SERVER/share/flac/Agnes%20Obel%20-%20'
    'Philharmonics/1%20-%20Falling,%20Catching.flac',
    'album_art_uri': '/getaa?u=x-file-cifs%3a%2f%2fTLE-SERVER%2fshare%2fflac'
    '%2fAgnes%2520Obel%2520-%2520Philharmonics%2f1%2520-%2520Falling,'
    '%2520Catching.flac&v=2',
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


def common_tests(parent_id, item_id, instance, content, item_xml, item_dict):
    """Test all the common methods inherited from MusicLibraryItem

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
    content1.pop('title')
    title = 'Dummy title with non ascii chars &#230;&#248;&#229;'
    xml = XML_TEMPLATE.format(parent_id=parent_id, item_id=item_id,
                              title=title, **content1)
    assert XML.tostring(instance.didl_metadata).decode() == xml

    # Test common attributes
    for key in ['uri', 'title', 'item_class']:
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

    # Test default class and None for un-assigned attributes
    instance4 = instance.__class__(content['uri'], content['title'])
    assert instance4.item_class == item_dict['item_class']
    for key in content.keys():
        if key not in ['uri', 'title', 'item_class']:
            assert getattr(instance4, key) is None


def common_tests_queue(parent_id, instance, content, item_xml,
                       item_dict):
    """Test all the common methods inherited from MusicLibraryItem

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

    # Test common attributes
    for key in ['uri', 'title', 'item_class']:
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

    # Test default class and None for un-assigned attributes
    instance4 = instance.__class__(content['uri'], content['title'])
    assert instance4.item_class == item_dict['item_class']
    for key in content.keys():
        if key not in ['uri', 'title', 'item_class']:
            assert getattr(instance4, key) is None


# The functions that test the different classes
def test_mltrack():
    """Test the MLTrack class"""
    # Set the tests up
    uri = 'x-file-cifs://dummy_uri'
    kwargs = {'album': ALBUM, 'album_art_uri': ART_URI, 'creator': CREATOR,
              'original_track_number': 47}
    content = {'uri': uri, 'title': TITLE, 'item_class': 'dummy.class'}
    content.update(kwargs)
    track = data_structures.MLTrack(uri, TITLE, 'dummy.class', **kwargs)

    # Run tests on inherited methods and attributes
    common_tests('A:TRACKS', 'S://dummy_uri', track, content, TRACK_XML,
                 TRACK_DICT)

    # Test class specific attributes
    for key in ['album', 'album_art_uri', 'creator']:
        set_and_get_test(track, content, key)

    assert track.original_track_number == 47
    track.original_track_number = 42
    assert track.original_track_number == 42
    track.original_track_number = 47


def test_mlalbum():
    """Test the MLAlbum class"""
    # Set the tests up
    uri = 'x-rincon-playlist:RINCON_000E5884455C01400#A:ALBUM/dummy_album'
    kwargs = {'album_art_uri': ART_URI, 'creator': CREATOR}
    album = data_structures.MLAlbum(uri, TITLE, 'dummy.class', **kwargs)

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'item_class': 'dummy.class'}
    content.update(kwargs)
    common_tests('A:ALBUM', 'A:ALBUM/dummy_album', album, content, ALBUM_XML,
                 ALBUM_DICT)

    # Test class specific attributes
    for key in ['album_art_uri', 'creator']:
        set_and_get_test(album, content, key)


def test_mlartist():
    """Test the MLArtist class"""
    # Set the tests up
    uri = 'x-rincon-playlist:RINCON_000E5884455C01400#A:ARTIST/10%20Years'
    artist = data_structures.MLArtist(uri, TITLE, 'dummy.class')

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'item_class': 'dummy.class'}
    common_tests('A:ARTIST', 'A:ARTIST/10%20Years', artist, content,
                 ARTIST_XML, ARTIST_DICT)


def test_mlalbumartist():
    """Test the MLAlbumArtist class"""
    # Set the tests up
    uri = 'x-rincon-playlist:RINCON_000E5884455C01400#A:ALBUMARTIST/'\
          '3%20Doors%20Down'
    albumartist = data_structures.MLAlbumArtist(uri, TITLE, 'dummy.class')

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'item_class': 'dummy.class'}
    common_tests('A:ALBUMARTIST', 'A:ALBUMARTIST/3%20Doors%20Down',
                 albumartist, content, ALBUMARTIST_XML, ALBUMARTIST_DICT)


def test_mlgenre():
    """Test the MLGenre class"""
    # Set the tests up
    uri = 'x-rincon-playlist:RINCON_000E5884455C01400#A:GENRE/Acid'
    genre = data_structures.MLGenre(uri, TITLE, 'dummy.class')

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'item_class': 'dummy.class'}
    common_tests('A:GENRE', 'A:GENRE/Acid', genre, content,
                 GENRE_XML, GENRE_DICT)


def test_mlcomposer():
    """Test the MLComposer class"""
    # Set the tests up
    uri = 'x-rincon-playlist:RINCON_000E5884455C01400#A:COMPOSER/A.%20Kiedis'\
          '%2fFlea%2fJ.%20Frusciante%2fC.%20Smith'
    composer = data_structures.MLComposer(uri, TITLE, 'dummy.class')

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'item_class': 'dummy.class'}
    common_tests(
        'A:COMPOSER',
        'A:COMPOSER/A.%20Kiedis%2fFlea%2fJ.%20Frusciante%2fC.%20Smith',
        composer, content, COMPOSER_XML, COMPOSER_DICT
    )


def test_mlplaylist():
    """Test the MLPlaylist class"""
    # Set the tests up
    uri = 'x-file-cifs://TLE-SERVER/share/mp3/Trentem%c3%b8ller%20-%20The%20'\
          'Trentem%c3%b8ller%20Chronicles/-%3dTrentem%c3%b8ller%20-%20The%20'\
          'Trentem%c3%b8ller%20Chronicles%20(CD%201).m3u'
    playlist = data_structures.MLPlaylist(uri, TITLE, 'dummy.class')

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'item_class': 'dummy.class'}
    common_tests('A:PLAYLISTS', 'S://TLE-SERVER/share/mp3/Trentem%c3%b8ller'
                 '%20-%20The%20Trentem%c3%b8ller%20Chronicles/-%3d'
                 'Trentem%c3%b8ller%20-%20The%20Trentem%c3%b8ller%20'
                 'Chronicles%20(CD%201).m3u', playlist, content,
                 PLAYLIST_XML, PLAYLIST_DICT)


def test_mlshare():
    """Test the MLShare class"""
    # Set the tests up
    uri = 'x-rincon-playlist:RINCON_000E5884455C01400#S://TLE-SERVER/share'
    share = data_structures.MLShare(uri, TITLE, 'dummy.class')

    # Run tests on inherited methods and attributes
    content = {'uri': uri, 'title': TITLE, 'item_class': 'dummy.class'}
    common_tests('S:', 'S://TLE-SERVER/share', share, content,
                 SHARE_XML, SHARE_DICT)


def test_ns_tag():
    """Test the ns_tag module function"""
    namespaces = ['http://purl.org/dc/elements/1.1/',
                  'urn:schemas-upnp-org:metadata-1-0/upnp/',
                  'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/']
    for ns_in, namespace in zip(['dc', 'upnp', ''], namespaces):
        res = data_structures.ns_tag(ns_in, 'testtag')
        correct = '{{{}}}{}'.format(namespace, 'testtag')
        assert res == correct


def test_get_ml_item():
    """Test the get_ml_item medule function"""
    xmls = [TRACK_XML, ALBUM_XML, ARTIST_XML, ALBUMARTIST_XML, GENRE_XML,
            COMPOSER_XML, PLAYLIST_XML, SHARE_XML]
    classes = [data_structures.MLTrack, data_structures.MLAlbum,
               data_structures.MLArtist, data_structures.MLAlbumArtist,
               data_structures.MLGenre, data_structures.MLComposer,
               data_structures.MLPlaylist, data_structures.MLShare]
    for xml, class_ in zip(xmls, classes):
        etree = XML.fromstring(xml.encode('utf-8'))
        item = data_structures.get_ml_item(etree)
        assert item.__class__ == class_


def test_queue_item():
    """Test the QueueItem class"""
    # Set the tests up
    uri = 'x-file-cifs://dummy_uri'
    kwargs = {'album': ALBUM, 'album_art_uri': ART_URI, 'creator': CREATOR,
              'original_track_number': 47}
    content = {'uri': uri, 'title': TITLE, 'item_class': 'dummy.class'}
    content.update(kwargs)
    track = data_structures.QueueItem(uri, TITLE, 'dummy.class', **kwargs)

    # Run tests on inherited methods and attributes
    common_tests_queue('Q:0', track, content, QUEUE_XML1, QUEUE_DICT1)

    # Test class specific attributes
    for key in ['album', 'album_art_uri', 'creator']:
        set_and_get_test(track, content, key)

    assert track.original_track_number == 47
    track.original_track_number = 42
    assert track.original_track_number == 42
    track.original_track_number = 47
