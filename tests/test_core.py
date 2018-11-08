# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import mock
import pytest

from soco import SoCo
from soco.data_structures import (
    DidlMusicTrack, to_didl_string
)
from soco.exceptions import (
    SoCoSlaveException, SoCoUPnPException
)
from soco.groups import ZoneGroup
from soco.xml import XML

IP_ADDR = '192.168.1.101'


@pytest.yield_fixture()
def moco():
    """A mock soco with fake services and hardcoded is_coordinator.

    Allows calls to services to be tracked. Should not cause any network
    access
    """
    services = (
        'AVTransport', 'RenderingControl', 'DeviceProperties',
        'ContentDirectory', 'ZoneGroupTopology')
    patchers = [mock.patch('soco.core.{}'.format(service))
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

    Allows calls to services to be tracked. Should not cause any network
    access
    """
    services = (
        'AVTransport', 'RenderingControl', 'DeviceProperties',
        'ContentDirectory', 'ZoneGroupTopology')
    patchers = [mock.patch('soco.core.{}'.format(service))
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
    """A mock soco with zone group state."""
    moco.zoneGroupTopology.GetZoneGroupState.return_value = {
        'ZoneGroupState': ZGS
    }
    yield moco


class TestSoco:
    device_description = """<?xml version="1.0" encoding="utf-8" ?>
        <root xmlns="urn:schemas-upnp-org:device-1-0">
          <specVersion>
            <major>1</major>
            <minor>0</minor>
          </specVersion>
          <device>
            <deviceType>urn:schemas-upnp-org:device:ZonePlayer:1</deviceType>
            <friendlyName>""" + IP_ADDR + """ - Sonos PLAY:3</friendlyName>
            <manufacturer>Sonos, Inc.</manufacturer>
            <manufacturerURL>http://www.sonos.com</manufacturerURL>
            <modelNumber>S3</modelNumber>
            <modelDescription>Sonos PLAY:3</modelDescription>
            <modelName>Sonos PLAY:3</modelName>
            <modelURL>http://www.sonos.com/products/zoneplayers/S3</modelURL>
            <softwareVersion>29.5-91030</softwareVersion>
            <hardwareVersion>1.8.1.2-2</hardwareVersion>
            <serialNum>00-11-22-33-44-55:E</serialNum>
            <UDN>uuid:RINCON_00112233445501400</UDN>
            <iconList>
              <icon>
                <id>0</id>
                <mimetype>image/png</mimetype>
                <width>48</width>
                <height>48</height>
                <depth>24</depth>
                <url>/img/icon-S3.png</url>
              </icon>
            </iconList>
            <minCompatibleVersion>28.0-00000</minCompatibleVersion>
            <legacyCompatibleVersion>24.0-0000</legacyCompatibleVersion>
            <displayVersion>5.4</displayVersion>
            <extraVersion>OTP: </extraVersion>
            <roomName>Room</roomName>
          </device>
        </root>
    """

    @pytest.mark.parametrize('bad_ip_addr', ['not_ip', '555.555.555.555'])
    def test_soco_bad_ip(self, bad_ip_addr):
        with pytest.raises(ValueError):
            speaker = SoCo(bad_ip_addr)

    def test_soco_init(self, moco):
        assert moco.ip_address == IP_ADDR
        assert moco.speaker_info == {}

    def test_soco_str(self, moco):
        assert str(moco) == "<SoCo object at ip {}>".format(IP_ADDR)

    def test_soco_repr(self, moco):
        assert repr(moco) == 'SoCo("{}")'.format(IP_ADDR)

    @pytest.mark.parametrize('model_name', (
        ('Play:5', False),
        ('Sonos One', False),
        ('PLAYBAR', True),
        ('Sonos Beam', True),
        ('Sonos Playbar', True),
        ('Sonos Playbase', True)))
    def test_soco_is_soundbar(self, moco, model_name):
        moco._is_soundbar = None
        moco.speaker_info['model_name'] = model_name[0]
        assert moco.is_soundbar == model_name[1]

    @mock.patch("soco.core.requests")
    @pytest.mark.parametrize('refresh', [None, False, True])
    def test_soco_get_speaker_info_speaker_not_set_refresh(
            self, mocr, moco_zgs, refresh):
        """Internal speaker_info not set; Refresh all values (default, False,
        True)

        => should update
        """
        response = mock.MagicMock()
        mocr.get.return_value = response
        response.content = self.device_description
        # save old state
        old = moco_zgs.speaker_info
        moco_zgs.speaker_info = {}
        if refresh is None:
            res = moco_zgs.get_speaker_info()
        else:
            res = moco_zgs.get_speaker_info(refresh)
        # restore original value
        moco_zgs.speaker_info = old
        mocr.get.assert_called_once_with(
            'http://' + IP_ADDR + ':1400/xml/device_description.xml',
            timeout=None,
        )
        should = {
            'zone_name': "Room",
            'player_icon': "/img/icon-S3.png",
            'uid': "RINCON_000XXX1400",
            'serial_number': "00-11-22-33-44-55:E",
            'software_version': "29.5-91030",
            'hardware_version': "1.8.1.2-2",
            'model_number': "S3",
            'model_name': "Sonos PLAY:3",
            'display_version': "5.4",
            'mac_address': "00-11-22-33-44-55"
        }
        assert should == res

    @mock.patch("soco.core.requests")
    @pytest.mark.parametrize('refresh', [None, False])
    def test_soco_get_speaker_info_speaker_set_no_refresh(
            self, mocr, moco_zgs, refresh):
        """Internal speaker_info set; No refresh (default, False)

        => should not update
        """
        should = {
            'info': "yes"
        }
        # save old state
        old = moco_zgs.speaker_info
        moco_zgs.speaker_info = should
        if refresh is None:
            res = moco_zgs.get_speaker_info()
        else:
            res = moco_zgs.get_speaker_info(refresh)
        # restore original value
        moco_zgs.speaker_info = old
        # got 'should' returned
        assert res is should
        # no network request performed
        assert not mocr.get.called

    @mock.patch("soco.core.requests")
    @pytest.mark.parametrize('should', [{}, {'info': "yes"}])
    def test_soco_get_speaker_info_speaker_set_no_refresh(
            self, mocr, moco_zgs, should):
        """Internal speaker_info not set/set; Refresh True.

        => should update
        """
        response = mock.MagicMock()
        mocr.get.return_value = response
        response.content = self.device_description
        # save old state
        old = moco_zgs.speaker_info
        moco_zgs.speaker_info = should
        res = moco_zgs.get_speaker_info(True)
        # restore original value
        moco_zgs.speaker_info = old
        mocr.get.assert_called_once_with(
            'http://' + IP_ADDR + ':1400/xml/device_description.xml',
            timeout=None,
        )
        # get_speaker_info only updates internal speaker_info and does not
        # replace it
        should.update({
            'zone_name': "Room",
            'player_icon': "/img/icon-S3.png",
            'uid': "RINCON_000XXX1400",
            'serial_number': "00-11-22-33-44-55:E",
            'software_version': "29.5-91030",
            'hardware_version': "1.8.1.2-2",
            'model_number': "S3",
            'model_name': "Sonos PLAY:3",
            'display_version': "5.4",
            'mac_address': "00-11-22-33-44-55"
        })
        assert should == res


class TestAVTransport:

    @pytest.mark.parametrize('playmode', [
        "NORMAL", "SHUFFLE_NOREPEAT", "SHUFFLE", "REPEAT_ALL", "SHUFFLE_REPEAT_ONE", "REPEAT_ONE"
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

    # Test that uris are forced to Radio style display and controls when
    # force_radio is True prefix is replaced with "x-rincon-mp3radion://"
    # first set of test with no forcing, second set with force_radio=True

    # No forcing
    @pytest.mark.parametrize("uri_in, uri_passed", [
        ('x-file-cifs://server/MyNiceRing.mp3',
         'x-file-cifs://server/MyNiceRing.mp3'),
        ('http://archive.org/download/TenD2005-07-16t_64kb.mp3',
         'http://archive.org/download/TenD2005-07-16t_64kb.mp3'),
        ('x-sonosapi-radio:station%3a%3aps.147077612?sid=203&flags=76&sn=2',
         'x-sonosapi-radio:station%3a%3aps.147077612?sid=203&flags=76&sn=2'),
    ])
    def test_soco_play_uri(self, moco, uri_in, uri_passed):
        moco.play_uri(uri_in)
        moco.avTransport.SetAVTransportURI.assert_called_once_with([
            ('InstanceID', 0),
            ('CurrentURI', uri_passed),
            ('CurrentURIMetaData', '')
        ])
        moco.avTransport.reset_mock()

    # with force_radio=True
    @pytest.mark.parametrize("uri_in, uri_passed", [
        ('http://archive.org/download/TenD2005-07-16t_64kb.mp3',
         'x-rincon-mp3radio://archive.org/download/TenD2005-07-16t_64kb.mp3'),
        ('https://archive.org/download/TenD2005-07-16t_64kb.mp3',
         'x-rincon-mp3radio://archive.org/download/TenD2005-07-16t_64kb.mp3'),
        ('aac://icy-e-bz-04-cr.sharp-stream.com/magic1054.aac?amsparams=playerid:BMUK_tunein;skey:1483570441&awparams=loggedin:false',
         'x-rincon-mp3radio://icy-e-bz-04-cr.sharp-stream.com/magic1054.aac?amsparams=playerid:BMUK_tunein;skey:1483570441&awparams=loggedin:false')
    ])
    def test_soco_play_uri_force_radio(self, moco, uri_in, uri_passed):
        moco.play_uri(uri_in, force_radio=True)
        moco.avTransport.SetAVTransportURI.assert_called_once_with([
            ('InstanceID', 0),
            ('CurrentURI', uri_passed),
            ('CurrentURIMetaData', '')
        ])
        moco.avTransport.reset_mock()

    def test_soco_play_uri_calls_play(self, moco):
        uri = 'http://archive.org/download/tend2005-07-16.flac16/tend2005-07-16t10wonderboy_64kb.mp3'
        moco.play_uri(uri)

        moco.avTransport.Play.assert_called_with(
            [('InstanceID', 0), ('Speed', 1)]
        )

    def test_soco_play_uri_with_title(self, moco):
        uri = 'http://archive.org/download/tend2005-07-16.flac16/tend2005-07-16t10wonderboy_64kb.mp3'
        moco.play_uri(uri, title='<Fast & Loose>')

        moco.avTransport.SetAVTransportURI.assert_called_with([
            ('InstanceID', 0),
            ('CurrentURI', uri),
            ('CurrentURIMetaData', '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"><item id="R:0/0/0" parentID="R:0/0" restricted="true"><dc:title>&lt;Fast &amp; Loose&gt;</dc:title><upnp:class>object.item.audioItem.audioBroadcast</upnp:class><desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">SA_RINCON65031_</desc></item></DIDL-Lite>')
        ])

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
            'Result': '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"><item id="Q:0/1" parentID="Q:0" restricted="true"><res protocolInfo="fake.com-fake-direct:*:audio/mp3:*" duration="0:02:32">radea:Tra.12345678.mp3</res><upnp:albumArtURI>/getaa?r=1&amp;u=radea%3aTra.12345678.mp3</upnp:albumArtURI><dc:title>Item 1 Title</dc:title><upnp:class>object.item.audioItem.musicTrack</upnp:class><dc:creator>Item 1 Creator</dc:creator><upnp:album>Item 1 Album</upnp:album></item></DIDL-Lite>',
            'NumberReturned': '1',
            'TotalMatches': '10',
            'UpdateID': '1'}
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

    def test_join(self, moco_zgs):
        moco2 = mock.Mock()
        moco2.uid = "RINCON_000XXX1400"
        moco_zgs.join(moco2)
        moco_zgs.avTransport.SetAVTransportURI.assert_called_once_with(
            [('InstanceID', 0),
             ('CurrentURI', 'x-rincon:RINCON_000XXX1400'),
             ('CurrentURIMetaData', '')]
        )

    def test_unjoin(self, moco_zgs):
        moco_zgs.unjoin()
        moco_zgs.avTransport.BecomeCoordinatorOfStandaloneGroup\
            .assert_called_once_with([('InstanceID', 0)])

    def test_switch_to_line_in(self, moco_zgs):
        moco_zgs.avTransport.reset_mock()
        moco_zgs.switch_to_line_in()
        moco_zgs.avTransport.SetAVTransportURI.assert_called_once_with(
            [('InstanceID', 0),
                ('CurrentURI', 'x-rincon-stream:RINCON_000XXX1400'),
                ('CurrentURIMetaData', '')]
        )

        moco_zgs.avTransport.reset_mock()
        moco2 = mock.Mock()
        moco2.uid = "RINCON_000YYY1400"
        moco_zgs.switch_to_line_in(moco2)
        moco_zgs.avTransport.SetAVTransportURI.assert_called_once_with(
            [('InstanceID', 0),
             ('CurrentURI', 'x-rincon-stream:RINCON_000YYY1400'),
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
            'AssignedObjectID': 'SQ:{}'.format(playlist_id)
        }
        playlist = moco.create_sonos_playlist(playlist_name)
        moco.avTransport.CreateSavedQueue.assert_called_once_with(
            [('InstanceID', 0),
             ('Title', playlist_name),
             ('EnqueuedURI', ''),
             ('EnqueuedURIMetaData', '')]
        )
        assert playlist.title == playlist_name
        expected_uri = "file:///jffs/settings/savedqueues.rsq#{}".format(
            playlist_id)
        assert playlist.resources[0].uri == expected_uri
        assert playlist.parent_id == "SQ:"

    def test_create_sonos_playlist_from_queue(self, moco):
        playlist_name = "saved queue"
        playlist_id = 1
        moco.avTransport.SaveQueue.return_value = {
            'AssignedObjectID': 'SQ:{}'.format(playlist_id)
        }
        playlist = moco.create_sonos_playlist_from_queue(playlist_name)
        moco.avTransport.SaveQueue.assert_called_once_with(
            [('InstanceID', 0),
             ('Title', playlist_name),
             ('ObjectID', '')]
        )
        assert playlist.title == playlist_name
        expected_uri = "file:///jffs/settings/savedqueues.rsq#{}".format(
            playlist_id)
        assert playlist.resources[0].uri == expected_uri
        assert playlist.parent_id == "SQ:"

    def test_add_item_to_sonos_playlist(self, moco):
        moco.contentDirectory.reset_mock()

        playlist = mock.Mock()
        playlist.item_id = 7

        ressource = mock.Mock()
        ressource.uri = 'fake_uri'
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

    def test_set_sleep_timer(self, moco):
        moco.avTransport.reset_mock()
        moco.avTransport.ConfigureSleepTimer.return_value = None
        result = moco.set_sleep_timer(None)
        assert result is None
        moco.avTransport.ConfigureSleepTimer.assert_called_once_with(
            [('InstanceID', 0),
             ('NewSleepTimerDuration', '')]
        )

        moco.avTransport.reset_mock()
        moco.avTransport.ConfigureSleepTimer.return_value = None
        result = moco.set_sleep_timer(7200)
        assert result is None
        moco.avTransport.ConfigureSleepTimer.assert_called_once_with(
            [('InstanceID', 0),
             ('NewSleepTimerDuration', '2:00:00')]
        )

        moco.avTransport.reset_mock()
        moco.avTransport.ConfigureSleepTimer.return_value = None
        result = moco.set_sleep_timer(0)
        assert result is None
        moco.avTransport.ConfigureSleepTimer.assert_called_once_with(
            [('InstanceID', 0),
             ('NewSleepTimerDuration', '0:00:00')]
        )

    @pytest.mark.parametrize('bad_sleep_time', ['BadTime', '00:43:23', '4200s',''])
    def test_set_sleep_timer_bad_sleep_time(self, moco, bad_sleep_time):
        with pytest.raises(ValueError):
            result = moco.set_sleep_timer(bad_sleep_time)

    def test_get_sleep_timer(self, moco):
        moco.avTransport.reset_mock()
        moco.avTransport.GetRemainingSleepTimerDuration.return_value = {
            'RemainingSleepTimerDuration': '02:00:00',
            'CurrentSleepTimerGeneration': '3',
        }
        result = moco.get_sleep_timer()
        assert result == 7200

        moco.avTransport.reset_mock()
        moco.avTransport.GetRemainingSleepTimerDuration.return_value = {
            'RemainingSleepTimerDuration': '',
            'CurrentSleepTimerGeneration': '0',
        }
        result = moco.get_sleep_timer()
        assert result == None


class TestContentDirectory:

    def test_remove_sonos_playlist_success(self, moco):
        moco.contentDirectory.reset_mock()
        moco.contentDirectory.return_value = True
        result = moco.remove_sonos_playlist('SQ:10')
        moco.contentDirectory.DestroyObject.assert_called_once_with(
            [('ObjectID', 'SQ:10')]
        )
        assert result


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

    def test_soco_ramp_to_volume(self, moco):
        moco.renderingControl.RampToVolume.return_value = {'RampTime': '12'}
        ramp_time = moco.ramp_to_volume(15)
        moco.renderingControl.RampToVolume.assert_called_once_with(
            [('InstanceID', 0), ('Channel', 'Master'),
             ('RampType', 'SLEEP_TIMER_RAMP_TYPE'), ('DesiredVolume', 15),
             ('ResetVolumeAfter', False), ('ProgramURI', '')]
        )
        assert ramp_time == 12

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
