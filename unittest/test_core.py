# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import pytest
import mock

from soco import SoCo
from soco.groups import ZoneGroup
from soco.xml import XML
from soco.data_structures import DidlMusicTrack, to_didl_string
from soco.exceptions import SoCoUPnPException, SoCoSlaveException

IP_ADDR = '192.168.1.101'


@pytest.yield_fixture()
def moco():
    """A mock soco with fake services and hardcoded is_coordinator

    Allows calls to services to be tracked. Should not cause any network access
    """
    services = (
        'AVTransport', 'RenderingControl', 'DeviceProperties',
        'ContentDirectory', 'ZoneGroupTopology')
    patchers = [mock.patch('soco.core.{0}'.format(service))
                for service in services]
    for patch in patchers:
        patch.start()
    with mock.patch("soco.SoCo.is_coordinator",
                    new_callable=mock.PropertyMock) as is_coord:
        is_coord = True
        yield SoCo(IP_ADDR)
    for patch in reversed(patchers):
        patch.stop()


@pytest.yield_fixture()
def moco_only_on_master():
    """A mock soco with fake services.

    Allows calls to services to be tracked. Should not cause any network access
    """
    services = (
        'AVTransport', 'RenderingControl', 'DeviceProperties',
        'ContentDirectory', 'ZoneGroupTopology')
    patchers = [mock.patch('soco.core.{0}'.format(service))
                for service in services]
    for patch in patchers:
        patch.start()
    yield SoCo(IP_ADDR)
    for patch in reversed(patchers):
        patch.stop()


ZGS = """<ZoneGroups>
      <ZoneGroup Coordinator="RINCON_000ZZZ1400" ID="RINCON_000ZZZ1400:0">
        <ZoneGroupMember
            BootSeq="33"
            Configuration="1"
            Icon="x-rincon-roomicon:zoneextender"
            Invisible="1"
            IsZoneBridge="1"
            Location="http://192.168.1.100:1400/xml/device_description.xml"
            MinCompatibleVersion="22.0-00000"
            SoftwareVersion="24.1-74200"
            UUID="RINCON_000ZZZ1400"
            ZoneName="BRIDGE"/>
      </ZoneGroup>
      <ZoneGroup Coordinator="RINCON_000XXX1400" ID="RINCON_000XXX1400:46">
        <ZoneGroupMember
            BootSeq="44"
            Configuration="1"
            Icon="x-rincon-roomicon:living"
            Location="http://192.168.1.101:1400/xml/device_description.xml"
            MinCompatibleVersion="22.0-00000"
            SoftwareVersion="24.1-74200"
            UUID="RINCON_000XXX1400"
            ZoneName="Living Room"/>
        <ZoneGroupMember
            BootSeq="52"
            Configuration="1"
            Icon="x-rincon-roomicon:kitchen"
            Location="http://192.168.1.102:1400/xml/device_description.xml"
            MinCompatibleVersion="22.0-00000"
            SoftwareVersion="24.1-74200"
            UUID="RINCON_000YYY1400"
            ZoneName="Kitchen"/>
      </ZoneGroup>
      <ZoneGroup Coordinator="RINCON_000PPP1400" ID="RINCON_000PPP1400:49">
        <ZoneGroupMember
            BootSeq="8"
            Configuration="1"
            HTSatChanMapSet="RINCON_000PPP1400:LF,RF;RINCON_000RRR1400:RR;RINCON_000SSS1400:LR;RINCON_000QQQ1400:SW"
            Icon="x-rincon-roomicon:living"
            Location="http://192.168.1.103:1400/xml/device_description.xml"
            MinCompatibleVersion="22.0-00000"
            SoftwareVersion="24.0-71060"
            UUID="RINCON_000PPP1400"
            ZoneName="Home Theatre">
          <Satellite
              BootSeq="4"
              Configuration="1"
              HTSatChanMapSet="RINCON_000PPP1400:LF,RF;RINCON_000QQQ1400:SW"
              Icon="x-rincon-roomicon:living"
              Invisible="1"
              Location="http://192.168.1.104:1400/xml/device_description.xml"
              MinCompatibleVersion="22.0-00000"
              SoftwareVersion="24.0-71060"
              UUID="RINCON_000QQQ1400"
              ZoneName="Home Theatre"/>
          <Satellite
              BootSeq="6"
              Configuration="1"
              HTSatChanMapSet="RINCON_000PPP1400:LF,RF;RINCON_000RRR1400:RR"
              Icon="x-rincon-roomicon:living"
              Invisible="1"
              Location="http://192.168.1.105:1400/xml/device_description.xml"
              MinCompatibleVersion="22.0-00000"
              SoftwareVersion="24.0-71060"
              UUID="RINCON_000RRR1400"
              ZoneName="Home Theatre"/>
          <Satellite
              BootSeq="4"
              Configuration="1"
              HTSatChanMapSet="RINCON_000PPP1400:LF,RF;RINCON_000SSS1400:LR"
              Icon="x-rincon-roomicon:living"
              Invisible="1"
              Location="http://192.168.1.106:1400/xml/device_description.xml"
              MinCompatibleVersion="22.0-00000"
              SoftwareVersion="24.0-71060"
              UUID="RINCON_000SSS1400"
              ZoneName="Home Theatre"/>
        </ZoneGroupMember>
      </ZoneGroup>
    </ZoneGroups>"""

@pytest.yield_fixture
def moco_zgs(moco):
    """A mock soco with zone group state"""
    moco.zoneGroupTopology.GetZoneGroupState.return_value = {
        'ZoneGroupState': ZGS
    }
    yield moco


@pytest.mark.parametrize('bad_ip_addr', [
    'not_ip', '555.555.555.555'
])
def test_soco_bad_ip(bad_ip_addr):
    with pytest.raises(ValueError):
            speaker = SoCo(bad_ip_addr)


def test_soco_init(moco):
    assert moco.ip_address == IP_ADDR
    assert moco.speaker_info == {}


def test_soco_str(moco):
    assert str(moco) == "<SoCo object at ip {0}>".format(IP_ADDR)


def test_soco_repr(moco):
    assert repr(moco) == 'SoCo("{0}")'.format(IP_ADDR)


class TestAVTransport:

    @pytest.mark.parametrize('playmode', [
        "NORMAL", "REPEAT_ALL", "SHUFFLE", "SHUFFLE_NOREPEAT"
    ])
    def test_soco_play_mode_values(self, moco, playmode):
        moco.avTransport.GetTransportSettings.return_value = {
            'PlayMode': playmode}
        assert moco.play_mode == playmode
        moco.avTransport.GetTransportSettings.assert_called_once_with(
            [('InstanceID', 0)]
        )
        moco.avTransport.reset_mock()

    def test_soco_play_mode_bad_value(self, moco):
        with pytest.raises(KeyError):
            moco.play_mode = "BAD_VALUE"
        assert not moco.avTransport.SetPlayMode.called

    def test_soco_play_mode_lowercase(self, moco):
        moco.play_mode = "normal"
        moco.avTransport.SetPlayMode.assert_called_once_with(
            [('InstanceID', 0), ('NewPlayMode', 'NORMAL')]
        )

    def test_soco_cross_fade(self, moco):
        moco.avTransport.GetCrossfadeMode.return_value = {'CrossfadeMode': '1'}
        assert moco.cross_fade
        moco.avTransport.GetCrossfadeMode.return_value = {'CrossfadeMode': '0'}
        assert not moco.cross_fade
        moco.avTransport.GetCrossfadeMode.assert_called_with(
            [('InstanceID', 0)]
        )
        moco.cross_fade = True
        moco.avTransport.SetCrossfadeMode.assert_called_once_with(
            [('InstanceID', 0), ('CrossfadeMode', '1')]
        )

    def test_soco_play(self, moco):
        moco.play()
        moco.avTransport.Play.assert_called_once_with(
            [('InstanceID', 0), ('Speed', 1)]
        )

    def test_soco_play_uri(self, moco):
        uri = 'http://archive.org/download/TenD2005-07-16.flac16/TenD2005-07-16t10Wonderboy_64kb.mp3'
        moco.play_uri(uri)
        moco.avTransport.SetAVTransportURI.assert_called_once_with([
            ('InstanceID', 0),
            ('CurrentURI', uri),
            ('CurrentURIMetaData', '')
        ])

    def test_soco_play_uri_calls_play(self, moco):
        uri = 'http://archive.org/download/tend2005-07-16.flac16/tend2005-07-16t10wonderboy_64kb.mp3'
        moco.play_uri(uri)

        moco.avTransport.Play.assert_called_with(
            [('InstanceID', 0), ('Speed', 1)]
        )

    def test_soco_pause(self, moco):
        moco.pause()
        moco.avTransport.Pause.assert_called_once_with(
            [('InstanceID', 0), ('Speed', 1)]
        )

    def test_soco_stop(self, moco):
        moco.stop()
        moco.avTransport.Stop.assert_called_once_with(
            [('InstanceID', 0), ('Speed', 1)]
        )

    def test_soco_next(self, moco):
        moco.next()
        moco.avTransport.Next.assert_called_once_with(
            [('InstanceID', 0), ('Speed', 1)]
        )

    def test_soco_previous(self, moco):
        moco.previous()
        moco.avTransport.Previous.assert_called_once_with(
            [('InstanceID', 0), ('Speed', 1)]
        )

    @pytest.mark.parametrize('bad_timestamp', [
        'NOT_VALID',
        '12:34:56:78',
        '99',
        '12:3:4'
    ])
    def test_soco_seek_invalid(self, moco, bad_timestamp):
        with pytest.raises(ValueError):
            moco.seek(bad_timestamp)
        assert not moco.avTransport.Seek.called

    @pytest.mark.parametrize('timestamp', [
        # '12:34', # Should this be valid?
        '1:23:45',
        '10:23:45',
        '12:78:78'  # Should this really be valid?
    ])
    def test_soco_seek_valid(self, moco, timestamp):
            moco.seek(timestamp)
            moco.avTransport.Seek.assert_called_once_with(
                [('InstanceID', 0), ('Unit', 'REL_TIME'),
                    ('Target', timestamp)])
            moco.avTransport.reset_mock()

    def test_soco_current_transport_info(self, moco):
        moco.avTransport.GetTransportInfo.return_value = {
            'CurrentTransportState': 'PLAYING',
            'CurrentTransportStatus': 'OK',
            'CurrentSpeed': '1'}
        playstate = moco.get_current_transport_info()
        moco.avTransport.GetTransportInfo.assert_called_once_with(
            [('InstanceID', 0)]
        )
        assert playstate['current_transport_state'] == 'PLAYING'
        assert playstate['current_transport_status'] == 'OK'
        assert playstate['current_transport_speed'] == '1'

    def test_soco_get_queue(self, moco):
        moco.contentDirectory.Browse.return_value = {
            'Result' : '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"><item id="Q:0/1" parentID="Q:0" restricted="true"><res protocolInfo="fake.com-fake-direct:*:audio/mp3:*" duration="0:02:32">radea:Tra.12345678.mp3</res><upnp:albumArtURI>/getaa?r=1&amp;u=radea%3aTra.12345678.mp3</upnp:albumArtURI><dc:title>Item 1 Title</dc:title><upnp:class>object.item.audioItem.musicTrack</upnp:class><dc:creator>Item 1 Creator</dc:creator><upnp:album>Item 1 Album</upnp:album></item></DIDL-Lite>',
            'NumberReturned': '1',
            'TotalMatches': '10',
            'UpdateID' : '1'}
        queue = moco.get_queue(start=8, max_items=32)
        moco.contentDirectory.Browse.assert_called_once_with([
            ('ObjectID', 'Q:0'),
            ('BrowseFlag', 'BrowseDirectChildren'),
            ('Filter', '*'),
            ('StartingIndex', 8),
            ('RequestedCount', 32),
            ('SortCriteria', '')
        ])
        assert queue is not None
        assert len(queue) == 1
        moco.contentDirectory.reset_mock()

    def test_soco_queue_size(self, moco):
        moco.contentDirectory.Browse.return_value = {
            'NumberReturned': '1',
            'Result': '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"><container id="Q:0" parentID="Q:" restricted="true" childCount="384"><dc:title>Queue Instance 0</dc:title><upnp:class>object.container.playlistContainer</upnp:class><res protocolInfo="x-rincon-queue:*:*:*">x-rincon-queue:RINCON_00012345678901400#0</res></container></DIDL-Lite>',
            'TotalMatches': '1',
            'UpdateID': '1'}
        queue_size = moco.queue_size
        moco.contentDirectory.Browse.assert_called_once_with([
            ('ObjectID', 'Q:0'),
            ('BrowseFlag', 'BrowseMetadata'),
            ('Filter', '*'),
            ('StartingIndex', 0),
            ('RequestedCount', 1),
            ('SortCriteria', '')
        ])
        assert queue_size == 384
        moco.contentDirectory.reset_mock()

    def test_join(self, moco):
        moco2 = mock.Mock()
        moco2.uid = "RINCON_000XXX1400"
        moco.join(moco2)
        moco.avTransport.SetAVTransportURI.assert_called_once_with(
            [('InstanceID', 0),
                ('CurrentURI', 'x-rincon:RINCON_000XXX1400'),
                ('CurrentURIMetaData', '')]
        )

    def test_unjoin(self, moco):
        moco.unjoin()
        moco.avTransport.BecomeCoordinatorOfStandaloneGroup\
            .assert_called_once_with([('InstanceID', 0)])

    def test_switch_to_line_in(self, moco_zgs):
        moco_zgs.avTransport.reset_mock()
        moco_zgs.switch_to_line_in()
        moco_zgs.avTransport.SetAVTransportURI.assert_called_once_with(
            [('InstanceID', 0),
                ('CurrentURI', 'x-rincon-stream:RINCON_000XXX1400'),
                ('CurrentURIMetaData', '')]
        )

    def test_switch_to_tv(self, moco_zgs):
        moco_zgs.avTransport.reset_mock()
        moco_zgs.switch_to_tv()
        moco_zgs.avTransport.SetAVTransportURI.assert_called_once_with(
            [('InstanceID', 0),
                ('CurrentURI', 'x-sonos-htastream:RINCON_000XXX1400:spdif'),
                ('CurrentURIMetaData', '')]
        )

    def test_is_playing_tv(self, moco):
        moco.avTransport.reset_mock()
        moco.avTransport.GetPositionInfo.return_value = {
            'TrackURI': 'x-sonos-htastream:RINCON_00012345678901234:spdif'
        }
        playing_tv = moco.is_playing_tv
        assert playing_tv
        moco.avTransport.GetPositionInfo.assert_called_once_with(
            [('InstanceID', 0),
             ('Channel', 'Master')]
        )

        moco.avTransport.GetPositionInfo.return_value = {
            'TrackURI': 'not-tv',
        }
        playing_tv = moco.is_playing_tv
        assert not playing_tv

    def test_is_playing_radio(self, moco):
        moco.avTransport.reset_mock()
        moco.avTransport.GetPositionInfo.return_value = {
            'TrackURI': 'x-rincon-mp3radio://example.com:80/myradio'
        }
        playing_tv = moco.is_playing_radio
        assert playing_tv
        moco.avTransport.GetPositionInfo.assert_called_once_with(
            [('InstanceID', 0),
             ('Channel', 'Master')]
        )

        moco.avTransport.GetPositionInfo.return_value = {
            'TrackURI': 'not-radio',
        }
        playing_tv = moco.is_playing_radio
        assert not playing_tv

    def test_is_playing_line_in(self, moco):
        moco.avTransport.reset_mock()
        moco.avTransport.GetPositionInfo.return_value = {
            'TrackURI': 'x-rincon-stream:blah-blah'
        }
        playing_tv = moco.is_playing_line_in
        assert playing_tv
        moco.avTransport.GetPositionInfo.assert_called_once_with(
            [('InstanceID', 0),
             ('Channel', 'Master')]
        )

        moco.avTransport.GetPositionInfo.return_value = {
            'TrackURI': 'not-line-in',
        }
        playing_tv = moco.is_playing_line_in
        assert not playing_tv

    def test_create_sonos_playlist(self, moco):
        playlist_name = "cool music"
        playlist_id = 1
        moco.avTransport.CreateSavedQueue.return_value = {
            'AssignedObjectID': 'SQ:{0}'.format(playlist_id)
        }
        playlist = moco.create_sonos_playlist(playlist_name)
        moco.avTransport.CreateSavedQueue.assert_called_once_with(
            [('InstanceID', 0),
             ('Title', playlist_name),
             ('EnqueuedURI', ''),
             ('EnqueuedURIMetaData', '')]
        )
        assert playlist.title == playlist_name
        expected_uri = "file:///jffs/settings/savedqueues.rsq#{0}".format(
            playlist_id)
        assert playlist.resources[0].uri == expected_uri
        assert playlist.parent_id == "SQ:"

    def test_create_sonos_playlist_from_queue(self, moco):
        playlist_name = "saved queue"
        playlist_id = 1
        moco.avTransport.SaveQueue.return_value = {
            'AssignedObjectID': 'SQ:{0}'.format(playlist_id)
        }
        playlist = moco.create_sonos_playlist_from_queue(playlist_name)
        moco.avTransport.SaveQueue.assert_called_once_with(
            [('InstanceID', 0),
             ('Title', playlist_name),
             ('ObjectID', '')]
        )
        assert playlist.title == playlist_name
        expected_uri = "file:///jffs/settings/savedqueues.rsq#{0}".format(
            playlist_id)
        assert playlist.resources[0].uri == expected_uri
        assert playlist.parent_id == "SQ:"

    def test_add_item_to_sonos_playlist(self, moco):
        moco.contentDirectory.reset_mock()

        playlist = mock.Mock()
        playlist.item_id = 7

        ressource = mock.Mock()
        ressource.uri  = 'fake_uri'
        track = mock.Mock()
        track.resources = [ressource]
        track.uri = 'fake_uri'
        track.to_element.return_value = XML.Element('a')

        update_id = 100

        moco.contentDirectory.Browse.return_value = {
            'NumberReturned': '0',
            'Result': '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"></DIDL-Lite>',
            'TotalMatches': '0',
            'UpdateID': update_id
        }

        moco.add_item_to_sonos_playlist(track, playlist)
        moco.contentDirectory.Browse.assert_called_once_with([
            ('ObjectID', playlist.item_id),
            ('BrowseFlag', 'BrowseDirectChildren'), 
            ('Filter', '*'),
            ('StartingIndex', 0),
            ('RequestedCount', 1),
            ('SortCriteria', '')
        ])
        moco.avTransport.AddURIToSavedQueue.assert_called_once_with(
            [('InstanceID', 0),
             ('UpdateID', update_id),
             ('ObjectID', playlist.item_id),
             ('EnqueuedURI', track.uri),
             ('EnqueuedURIMetaData', to_didl_string(track)),
             ('AddAtIndex', 4294967295)]
        )

    def test_soco_cross_fade(self, moco):
        moco.avTransport.GetCrossfadeMode.return_value = {
            'CrossfadeMode': '1'}
        assert moco.cross_fade
        moco.avTransport.GetCrossfadeMode.assert_called_once_with(
            [('InstanceID', 0)]
        )
        moco.cross_fade = False
        moco.avTransport.SetCrossfadeMode.assert_called_once_with(
            [('InstanceID', 0), ('CrossfadeMode', '0')]
        )

    def test_soco_get_item_album_art_uri(self, moco):
        uri = 'x-file-cifs://dummy_uri'
        title = 'fake-title'
        parent_id = 'A:TRACKS'
        item_id = 'fake-id'
        kwargs = {'album': 'fake-album',
                  'album_art_uri': '/getaa?r=1&u=track.mp3',
                  'creator': 'fake-artist',
                  'original_track_number': 47}
        content = {'uri': uri, 'title': title, 'parent_id': parent_id}
        content.update(kwargs)
        track = DidlMusicTrack(uri, title, parent_id, item_id, **kwargs)
        full_uri = moco.get_item_album_art_uri(track)
        assert full_uri == "http://192.168.1.101:1400/getaa?r=1&u=track.mp3"

    def test_search_track_no_result(self, moco):
        moco.contentDirectory.reset_mock()
        # Browse returns an exception if the artist can't be found
        # <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><s:Fault><faultcode>s:Client</faultcode><faultstring>UPnPError</faultstring><detail><UPnPError xmlns="urn:schemas-upnp-org:control-1-0"><errorCode>701</errorCode></UPnPError></detail></s:Fault></s:Body></s:Envelope>
        moco.contentDirectory.Browse.side_effect = SoCoUPnPException("No such object", "701", "error XML")

        result = moco.search_track("artist")

        assert len(result) == 0

        moco.contentDirectory.Browse.assert_called_once_with([
            ('ObjectID', 'A:ALBUMARTIST/artist/'),
            ('BrowseFlag', 'BrowseDirectChildren'),
            ('Filter', '*'),
            ('StartingIndex', 0),
            ('RequestedCount', 100000),
            ('SortCriteria', '')
        ])

    def test_search_track_no_artist_album_track(self, moco):
        moco.contentDirectory.reset_mock()
        # Browse returns an empty result set if artist and album and
        # track cannot be found
        moco.contentDirectory.Browse.side_effect = None
        moco.contentDirectory.Browse.return_value = {
            'NumberReturned': '0',
            'Result': '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"></DIDL-Lite>',
            'TotalMatches': '0',
            'UpdateID': '0'
        }

        result = moco.search_track("artist", "album", "track")

        assert len(result) == 0

        moco.contentDirectory.Browse.assert_called_once_with([
            ('ObjectID', 'A:ALBUMARTIST/artist/album:track'),
            ('BrowseFlag', 'BrowseDirectChildren'),
            ('Filter', '*'),
            ('StartingIndex', 0),
            ('RequestedCount', 100000),
            ('SortCriteria', '')
        ])

    def test_search_track_artist_albums(self, moco):
        moco.contentDirectory.reset_mock()
        moco.contentDirectory.Browse.side_effect = None
        moco.contentDirectory.Browse.return_value = {
            'NumberReturned': '2',
            'Result': '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:ns2="urn:schemas-upnp-org:metadata-1-0/upnp/"><container id="A:ALBUMARTIST/The%20Artist/First%20Album" parentID="A:ALBUMARTIST/The%20Artist" restricted="true"><dc:title>First Album</dc:title><ns2:class>object.container.album.musicAlbum</ns2:class><res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:RINCON_000123456789001400#A:ALBUMARTIST/The%20Artist/First%20Album</res><dc:creator>The Artist</dc:creator><ns2:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fserver%2fThe%2520Artist%2fFirst%2520Album%2ftrack2.mp3&amp;v=432</ns2:albumArtURI></container><container id="A:ALBUMARTIST/The%20Artist/Second%20Album" parentID="A:ALBUMARTIST/The%20Artist" restricted="true"><dc:title>Second Album</dc:title><ns2:class>object.container.album.musicAlbum</ns2:class><res protocolInfo="x-rincon-playlist:*:*:*">x-rincon-playlist:RINCON_000123456789001400#A:ALBUMARTIST/The%20Artist/Second%20Album</res><dc:creator>The Artist</dc:creator><ns2:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fserver%2fThe%2520Artist%2fSecond%2520Album%2ftrack2.mp3&amp;v=432</ns2:albumArtURI></container></DIDL-Lite>',
            'TotalMatches': '2',
            'UpdateID': '0'
        }
        results = moco.search_track("The Artist")

        assert results.number_returned == 2

        album = results[0]
        assert album.title == 'First Album'
        assert album.item_id == 'A:ALBUMARTIST/The%20Artist/First%20Album'
        album = results[1]
        assert album.title == 'Second Album'
        assert album.item_id == 'A:ALBUMARTIST/The%20Artist/Second%20Album'

        moco.contentDirectory.Browse.assert_called_once_with([
            ('ObjectID', 'A:ALBUMARTIST/The%20Artist/'),
            ('BrowseFlag', 'BrowseDirectChildren'),
            ('Filter', '*'),
            ('StartingIndex', 0),
            ('RequestedCount', 100000),
            ('SortCriteria', '')
        ])

    def test_search_track_artist_album_tracks(self, moco):
        moco.contentDirectory.reset_mock()
        moco.contentDirectory.Browse.side_effect = None
        moco.contentDirectory.Browse.return_value = {
            'NumberReturned': '3',
            'Result': '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:ns1="urn:schemas-upnp-org:metadata-1-0/upnp/"><item id="S://server/The%20Artist/The%20Album/03%20-%20Track%20Title%201.mp3" parentID="A:ALBUMARTIST/The%20Artist/The%20Album" restricted="true"><res protocolInfo="x-file-cifs:*:audio/mpeg:*">x-file-cifs://server/The%20Artist/The%20Album/03%20-%20Track%20Title%201.mp3</res><ns1:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fserver%2fThe%2520Artist%2fThe%2520Album%2f03%2520-%2520Track%2520Title%25201.mp3&amp;v=432</ns1:albumArtURI><dc:title>Track Title 1</dc:title><ns1:class>object.item.audioItem.musicTrack</ns1:class><dc:creator>The Artist</dc:creator><ns1:album>The Album</ns1:album><ns1:originalTrackNumber>3</ns1:originalTrackNumber></item><item id="S://server/The%20Artist/The%20Album/04%20-%20Track%20Title%202.m4a" parentID="A:ALBUMARTIST/The%20Artist/The%20Album" restricted="true"><res protocolInfo="x-file-cifs:*:audio/mp4:*">x-file-cifs://server/The%20Artist/The%20Album/04%20-%20Track%20Title%202.m4a</res><ns1:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fserver%2fThe%2520Artist%2fThe%2520Album%2f04%2520-%2520Track%2520Title%25202.m4a&amp;v=432</ns1:albumArtURI><dc:title>Track Title 2</dc:title><ns1:class>object.item.audioItem.musicTrack</ns1:class><dc:creator>The Artist</dc:creator><ns1:album>The Album</ns1:album><ns1:originalTrackNumber>4</ns1:originalTrackNumber></item><item id="S://server/The%20Artist/The%20Album/05%20-%20Track%20Title%203.mp3" parentID="A:ALBUMARTIST/The%20Artist/The%20Album" restricted="true"><res protocolInfo="x-file-cifs:*:audio/mpeg:*">x-file-cifs://server/The%20Artist/The%20Album/05%20-%20Track%20Title%203.mp3</res><ns1:albumArtURI>/getaa?u=x-file-cifs%3a%2f%2fserver%2fThe%2520Artist%2fThe%2520Album%2f05%2520-%2520Track%2520Title%25203.mp3&amp;v=432</ns1:albumArtURI><dc:title>Track Title 3</dc:title><ns1:class>object.item.audioItem.musicTrack</ns1:class><dc:creator>The Artist</dc:creator><ns1:album>The Album</ns1:album><ns1:originalTrackNumber>5</ns1:originalTrackNumber></item></DIDL-Lite>',
            'TotalMatches': '3',
            'UpdateID': '0'
        }

        results = moco.search_track("The Artist", "The Album")

        assert len(results) == 3

        track = results[0]
        assert track.title == 'Track Title 1'
        assert track.item_id == 'S://server/The%20Artist/The%20Album/03%20-%20Track%20Title%201.mp3'
        track = results[1]
        assert track.title == 'Track Title 2'
        assert track.item_id == 'S://server/The%20Artist/The%20Album/04%20-%20Track%20Title%202.m4a'
        track = results[2]
        assert track.title == 'Track Title 3'
        assert track.item_id == 'S://server/The%20Artist/The%20Album/05%20-%20Track%20Title%203.mp3'

        moco.contentDirectory.Browse.assert_called_once_with([
            ('ObjectID', 'A:ALBUMARTIST/The%20Artist/The%20Album'),
            ('BrowseFlag', 'BrowseDirectChildren'),
            ('Filter', '*'),
            ('StartingIndex', 0),
            ('RequestedCount', 100000),
            ('SortCriteria', '')
        ])


class TestContentDirectory:

    def test_soco_library_updating(self, moco):
        moco.contentDirectory.GetShareIndexInProgress.return_value = {'IsIndexing': '0'}
        assert not moco.library_updating
        moco.contentDirectory.reset_mock()
        moco.contentDirectory.GetShareIndexInProgress.return_value = {'IsIndexing': '1'}
        assert moco.library_updating

    def test_soco_start_library_update(self, moco):
        moco.contentDirectory.RefreshShareIndex.return_value = True
        assert moco.start_library_update()
        moco.contentDirectory.RefreshShareIndex.assert_called_with([
            ('AlbumArtistDisplayOption', ''),
        ])


class TestRenderingControl:

    def test_soco_mute(self, moco):
        moco.renderingControl.GetMute.return_value = {'CurrentMute': '1'}
        assert moco.mute
        moco.renderingControl.reset_mock()
        moco.renderingControl.GetMute.return_value = {'CurrentMute': '0'}
        assert not moco.mute
        moco.renderingControl.GetMute.assert_called_once_with(
            [('InstanceID', 0), ('Channel', 'Master')]
        )
        moco.mute = False
        moco.renderingControl.SetMute.assert_called_once_with(
            [('InstanceID', 0), ('Channel', 'Master'),
                ('DesiredMute', '0')]
        )
        moco.renderingControl.reset_mock()
        moco.mute = True
        moco.renderingControl.SetMute.assert_called_once_with(
            [('InstanceID', 0), ('Channel', 'Master'),
                ('DesiredMute', '1')]
        )

    @pytest.mark.parametrize('volume', [1, 4, 10, 100])
    def test_soco_volume(self, moco, volume):
        moco.renderingControl.GetVolume.return_value = {
            'CurrentVolume': volume}
        assert moco.volume == volume
        moco.renderingControl.GetVolume.assert_called_once_with(
            [('InstanceID', 0), ('Channel', 'Master')]
        )
        moco.renderingControl.reset_mock()

    @pytest.mark.parametrize('vol_set, vol_called', [
        (-120, 0),
        (-10, 0),
        (0, 0),
        (5, 5),
        (99, 99),
        (100, 100),
        (110, 100),
        (300, 100)
    ])
    def soco_volume_set(self, moco, vol_set, vol_called):
        moco.volume = vol_set
        moco.renderingControl.SetVolume.assert_called_once_with(
            [('InstanceID', 0), ('Channel', 'Master'),
                ('DesiredVolume', vol_called)]
        )

    def test_soco_treble(self, moco):
        moco.renderingControl.GetTreble.return_value = {'CurrentTreble': '15'}
        assert moco.treble == 15
        moco.renderingControl.GetTreble.assert_called_once_with(
            [('InstanceID', 0), ('Channel', 'Master')]
        )
        moco.treble = '10'
        moco.renderingControl.SetTreble.assert_called_once_with(
            [('InstanceID', 0),
                ('DesiredTreble', 10)]
        )

    def test_soco_loudness(self, moco):
        moco.renderingControl.GetLoudness.return_value = {
            'CurrentLoudness': '1'}
        assert moco.loudness
        moco.renderingControl.GetLoudness.assert_called_once_with(
            [('InstanceID', 0), ('Channel', 'Master')]
        )
        moco.loudness = False
        moco.renderingControl.SetLoudness.assert_called_once_with(
            [('InstanceID', 0), ('Channel', 'Master'),
                ('DesiredLoudness', '0')]
        )


class TestDeviceProperties:

    def test_soco_status_light(self, moco):
        moco.deviceProperties.GetLEDState.return_value = {
            'CurrentLEDState': 'On'}
        assert moco.status_light
        moco.deviceProperties.GetLEDState.return_value = {
            'CurrentLEDState': 'Off'}
        assert not moco.status_light
        moco.deviceProperties.GetLEDState.assert_called_with()
        moco.status_light = False
        moco.deviceProperties.SetLEDState.assert_called_once_with(
            [('DesiredLEDState', 'Off')])
        moco.status_light = True
        moco.deviceProperties.SetLEDState.assert_called_with(
            [('DesiredLEDState', 'On')]
        )

    def test_soco_set_player_name(self, moco):
        moco.player_name = 'μИⅠℂ☺ΔЄ💋'
        moco.deviceProperties.SetZoneAttributes.assert_called_once_with(
            [('DesiredZoneName', 'μИⅠℂ☺ΔЄ💋'),
                ('DesiredIcon', ''),
                ('DesiredConfiguration', '')]
        )


class TestZoneGroupTopology:

    def test_soco_uid(self, moco_zgs):
        assert moco_zgs.uid == 'RINCON_000XXX1400'

    def test_soco_is_visible(self, moco_zgs):
        assert moco_zgs.is_visible

    def test_soco_is_bridge(self, moco_zgs):
        assert not moco_zgs.is_bridge

    def test_soco_is_coordinator(self, moco_zgs):
        assert moco_zgs.is_coordinator

    def test_all_groups(self, moco_zgs):
        groups = moco_zgs.all_groups
        assert len(groups) == 3
        # Check 3 unique groups
        assert len(set(groups)) == 3
        for group in groups:
            assert isinstance(group, ZoneGroup)

    def test_all_groups_have_coordinator(self, moco_zgs):
        for group in moco_zgs.all_groups:
            assert group.coordinator is not None

    def test_group(self, moco_zgs):
        assert isinstance(moco_zgs.group, ZoneGroup)
        assert moco_zgs in moco_zgs.group

    def test_all_zones(selfself, moco_zgs):
        zones = moco_zgs.all_zones
        assert len(zones) == 7
        assert len(set(zones)) == 7
        for zone in zones:
            assert isinstance(zone, SoCo)
        assert moco_zgs in zones

    def test_visible_zones(selfself, moco_zgs):
        zones = moco_zgs.visible_zones
        assert len(zones) == 3
        assert len(set(zones)) == 3
        for zone in zones:
            assert isinstance(zone, SoCo)
        assert moco_zgs in zones

    def test_group_label(selfself, moco_zgs):
        g = moco_zgs.group
        # Have to mock out group members zone group state here since
        # g.members is parsed from the XML.
        for speaker in g.members:
            speaker.zoneGroupTopology.GetZoneGroupState.return_value = {
                'ZoneGroupState': ZGS
            }
        assert g.label == "Kitchen, Living Room"

    def test_group_short_label(selfself, moco_zgs):
        g = moco_zgs.group
        # Have to mock out group members zone group state here since
        # g.members is parsed from the XML.
        for speaker in g.members:
            speaker.zoneGroupTopology.GetZoneGroupState.return_value = {
                'ZoneGroupState': ZGS
            }
        assert g.short_label == "Kitchen + 1"


def test_only_on_master_true(moco_only_on_master):
    with mock.patch('soco.SoCo.is_coordinator', new_callable=mock.PropertyMock) as is_coord:
        is_coord.return_value = True
        moco_only_on_master.play()
        is_coord.assert_called_once_with()


def test_not_on_master_false(moco_only_on_master):
    with mock.patch('soco.SoCo.is_coordinator', new_callable=mock.PropertyMock) as is_coord:
        is_coord.return_value = False
        with pytest.raises(SoCoSlaveException):
            moco_only_on_master.play()
        is_coord.assert_called_once_with()
