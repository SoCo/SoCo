from unittest import mock
import pytest
import requests_mock

from soco import SoCo
from soco.data_structures import DidlMusicTrack, to_didl_string
from soco.exceptions import (
    SoCoSlaveException,
    SoCoUPnPException,
    SoCoNotVisibleException,
    NotSupportedException,
)
from soco.groups import ZoneGroup
from soco.xml import XML

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
        "GroupRenderingControl",
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


@pytest.fixture()
def moco_only_on_master():
    """A mock soco with fake services.

    Allows calls to services to be tracked. Should not cause any network
    access
    """
    services = (
        "AVTransport",
        "RenderingControl",
        "DeviceProperties",
        "ContentDirectory",
        "ZoneGroupTopology",
        "GroupRenderingControl",
    )
    patchers = [mock.patch("soco.core.{}".format(service)) for service in services]
    for patch in patchers:
        patch.start()
    yield SoCo(IP_ADDR)
    for patch in reversed(patchers):
        patch.stop()


ZGS = (
    """<ZoneGroupState>
      <ZoneGroups>
        <ZoneGroup Coordinator="RINCON_000XXX1400" ID="RINCON_000E5876A0E801400:210">
          <ZoneGroupMember
              UUID="RINCON_000XXX1400"
              Location="http://192.168.1.101:1400/xml/device_description.xml"
              ZoneName="Kitchen"
              Icon="x-rincon-roomicon:kitchen"
              Configuration="1"
              SoftwareVersion="49.2-64250"
              MinCompatibleVersion="48.0-00000"
              LegacyCompatibleVersion="36.0-00000"
              BootSeq="162"
              TVConfigurationError="0"
              HdmiCecAvailable="0"
              WirelessMode="0"
              WirelessLeafOnly="0"
              HasConfiguredSSID="1"
              ChannelFreq="2437"
              BehindWifiExtender="0"
              WifiEnabled="1"
              Orientation="0"
              RoomCalibrationState="4"
              SecureRegState="3"
              VoiceConfigState="0"
              MicEnabled="0"
              AirPlayEnabled="0"
              IdleState="1"
              MoreInfo=""/>
          <ZoneGroupMember
              UUID="RINCON_B8E93781F3EA01400"
              Location="http://192.168.1.31:1400/xml/device_description.xml"
              ZoneName="Living Room"
              Icon="x-rincon-roomicon:masterbedroom"
              Configuration="1"
              SoftwareVersion="49.2-64250"
              MinCompatibleVersion="48.0-00000"
              LegacyCompatibleVersion="36.0-00000"
              BootSeq="226"
              TVConfigurationError="0"
              HdmiCecAvailable="0"
              WirelessMode="0"
              WirelessLeafOnly="0"
              HasConfiguredSSID="1"
              ChannelFreq="2437"
              BehindWifiExtender="0"
              WifiEnabled="1"
              Orientation="0"
              RoomCalibrationState="4"
              SecureRegState="3"
              VoiceConfigState="0"
              MicEnabled="0"
              AirPlayEnabled="0"
              IdleState="1"
              MoreInfo=""/>
        </ZoneGroup>
        <ZoneGroup Coordinator="RINCON_000E58A53FAE01400" """
    """ID="RINCON_000E58A53FAE01400:107">
          <ZoneGroupMember
              UUID="RINCON_000E58A53FAE01400"
              Location="http://192.168.1.173:1400/xml/device_description.xml"
              ZoneName="Stue"
              Icon="x-rincon-roomicon:living"
              Configuration="1"
              SoftwareVersion="49.2-64250"
              MinCompatibleVersion="48.0-00000"
              LegacyCompatibleVersion="36.0-00000"
              BootSeq="1777"
              TVConfigurationError="0"
              HdmiCecAvailable="0"
              WirelessMode="0"
              WirelessLeafOnly="0"
              HasConfiguredSSID="0"
              ChannelFreq="2437"
              BehindWifiExtender="0"
              WifiEnabled="1"
              Orientation="0"
              RoomCalibrationState="4"
              SecureRegState="3"
              VoiceConfigState="0"
              MicEnabled="0"
              AirPlayEnabled="0"
              IdleState="1"
              MoreInfo=""/>
        </ZoneGroup>
        <ZoneGroup Coordinator="RINCON_000E5884455C01400" """
    """ID="RINCON_000E5884455C01400:114">
          <ZoneGroupMember
              UUID="RINCON_000E5884455C01400"
              Location="http://192.168.1.197:1400/xml/device_description.xml"
              ZoneName="Kontor"
              Icon="x-rincon-roomicon:office"
              Configuration="1"
              SoftwareVersion="49.2-64250"
              MinCompatibleVersion="48.0-00000"
              LegacyCompatibleVersion="36.0-00000"
              BootSeq="196"
              TVConfigurationError="0"
              HdmiCecAvailable="0"
              WirelessMode="0"
              WirelessLeafOnly="0"
              HasConfiguredSSID="1"
              ChannelFreq="2437"
              BehindWifiExtender="0"
              WifiEnabled="1"
              Orientation="0"
              RoomCalibrationState="4"
              SecureRegState="3"
              VoiceConfigState="0"
              MicEnabled="0"
              AirPlayEnabled="0"
              IdleState="0"
              MoreInfo=""/>
        </ZoneGroup>
      </ZoneGroups>
      <VanishedDevices></VanishedDevices>
    </ZoneGroupState>"""
)


@pytest.fixture()
def moco_zgs(moco):
    """A mock soco with zone group state."""
    moco.zoneGroupTopology.GetZoneGroupState.return_value = {"ZoneGroupState": ZGS}
    yield moco


class TestSoco:
    device_description = (
        """<?xml version="1.0" encoding="utf-8" ?>
        <root xmlns="urn:schemas-upnp-org:device-1-0">
          <specVersion>
            <major>1</major>
            <minor>0</minor>
          </specVersion>
          <device>
            <deviceType>urn:schemas-upnp-org:device:ZonePlayer:1</deviceType>
            <friendlyName>"""
        + IP_ADDR
        + """ - Sonos Play:5</friendlyName>
            <manufacturer>Sonos, Inc.</manufacturer>
            <manufacturerURL>http://www.sonos.com</manufacturerURL>
            <modelNumber>S3</modelNumber>
            <modelDescription>Sonos Play:5</modelDescription>
            <modelName>Sonos Play:3</modelName>
            <modelURL>http://www.sonos.com/products/zoneplayers/S5</modelURL>
            <softwareVersion>49.2-64250</softwareVersion>
            <hardwareVersion>1.8.1.2-2</hardwareVersion>
            <serialNum>00-11-22-33-44-55:E</serialNum>
            <UDN>uuid:RINCON_000E5884455C01400</UDN>
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
            <minCompatibleVersion>48.0-00000</minCompatibleVersion>
            <legacyCompatibleVersion>36.0-00000</legacyCompatibleVersion>
            <apiVersion>1.11.1</apiVersion>
            <minApiVersion>1.1.0</minApiVersion>
            <displayVersion>10.1.2</displayVersion>
            <extraVersion>OTP: 1.1.1(1-16-4-zp5s-0.5)</extraVersion>
            <roomName>Room</roomName>
            <displayName>Play:5</displayName>
            <zoneType>5</zoneType>
            <feature1>0x02000002</feature1>
            <feature2>0x00006172</feature2>
            <feature3>0x0003002a</feature3>
            <seriesid>P100</seriesid>
            <variant>0</variant>
            <internalSpeakerSize>3</internalSpeakerSize>
            <bassExtension>0.000</bassExtension>
            <satGainOffset>0.000</satGainOffset>
            <memory>32</memory>
            <flash>32</flash>
            <flashRepartitioned>1</flashRepartitioned>
            <ampOnTime>425</ampOnTime>
            <retailMode>0</retailMode>
            <serviceList>
              <service>
                <serviceType>urn:schemas-upnp-org:service:AlarmClock:1</serviceType>
                <serviceId>urn:upnp-org:serviceId:AlarmClock</serviceId>
                <controlURL>/AlarmClock/Control</controlURL>
                <eventSubURL>/AlarmClock/Event</eventSubURL>
                <SCPDURL>/xml/AlarmClock1.xml</SCPDURL>
              </service>
              <service>
                <serviceType>urn:schemas-upnp-org:service:MusicServices:1</serviceType>
                <serviceId>urn:upnp-org:serviceId:MusicServices</serviceId>
                <controlURL>/MusicServices/Control</controlURL>
                <eventSubURL>/MusicServices/Event</eventSubURL>
                <SCPDURL>/xml/MusicServices1.xml</SCPDURL>
              </service>
              <service>
                <serviceType>urn:schemas-upnp-org:service:AudioIn:1</serviceType>
                <serviceId>urn:upnp-org:serviceId:AudioIn</serviceId>
                <controlURL>/AudioIn/Control</controlURL>
                <eventSubURL>/AudioIn/Event</eventSubURL>
                <SCPDURL>/xml/AudioIn1.xml</SCPDURL>
              </service>
              <service>
                <serviceType>urn:schemas-upnp-org:service:DeviceProperties:1</serviceType>
                <serviceId>urn:upnp-org:serviceId:DeviceProperties</serviceId>
                <controlURL>/DeviceProperties/Control</controlURL>
                <eventSubURL>/DeviceProperties/Event</eventSubURL>
                <SCPDURL>/xml/DeviceProperties1.xml</SCPDURL>
              </service>
              <service>
                <serviceType>urn:schemas-upnp-org:service:SystemProperties:1</serviceType>
                <serviceId>urn:upnp-org:serviceId:SystemProperties</serviceId>
                <controlURL>/SystemProperties/Control</controlURL>
                <eventSubURL>/SystemProperties/Event</eventSubURL>
                <SCPDURL>/xml/SystemProperties1.xml</SCPDURL>
              </service>
              <service>
                <serviceType>urn:schemas-upnp-org:service:ZoneGroupTopology:1</serviceType>
                <serviceId>urn:upnp-org:serviceId:ZoneGroupTopology</serviceId>
                <controlURL>/ZoneGroupTopology/Control</controlURL>
                <eventSubURL>/ZoneGroupTopology/Event</eventSubURL>
                <SCPDURL>/xml/ZoneGroupTopology1.xml</SCPDURL>
              </service>
              <service>
                <serviceType>urn:schemas-upnp-org:service:GroupManagement:1</serviceType>
                <serviceId>urn:upnp-org:serviceId:GroupManagement</serviceId>
                <controlURL>/GroupManagement/Control</controlURL>
                <eventSubURL>/GroupManagement/Event</eventSubURL>
                <SCPDURL>/xml/GroupManagement1.xml</SCPDURL>
              </service>
              <service>
                <serviceType>urn:schemas-tencent-com:service:QPlay:1</serviceType>
                <serviceId>urn:tencent-com:serviceId:QPlay</serviceId>
                <controlURL>/QPlay/Control</controlURL>
                <eventSubURL>/QPlay/Event</eventSubURL>
                <SCPDURL>/xml/QPlay1.xml</SCPDURL>
              </service>
            </serviceList>
            <deviceList>
              <device>
          <deviceType>urn:schemas-upnp-org:device:MediaServer:1</deviceType>
          <friendlyName>192.168.1.197 - Sonos Play:5 Media Server</friendlyName>
          <manufacturer>Sonos, Inc.</manufacturer>
          <manufacturerURL>http://www.sonos.com</manufacturerURL>
          <modelNumber>S5</modelNumber>
          <modelDescription>Sonos Play:5 Media Server</modelDescription>
          <modelName>Sonos Play:5</modelName>
          <modelURL>http://www.sonos.com/products/zoneplayers/S5</modelURL>
          <UDN>uuid:RINCON_000E5884455C01400_MS</UDN>
          <serviceList>
            <service>
              <serviceType>urn:schemas-upnp-org:service:ContentDirectory:1</serviceType>
              <serviceId>urn:upnp-org:serviceId:ContentDirectory</serviceId>
              <controlURL>/MediaServer/ContentDirectory/Control</controlURL>
              <eventSubURL>/MediaServer/ContentDirectory/Event</eventSubURL>
              <SCPDURL>/xml/ContentDirectory1.xml</SCPDURL>
            </service>
            <service>
              <serviceType>urn:schemas-upnp-org:service:ConnectionManager:1</serviceType>
                    <serviceId>urn:upnp-org:serviceId:ConnectionManager</serviceId>
                    <controlURL>/MediaServer/ConnectionManager/Control</controlURL>
                    <eventSubURL>/MediaServer/ConnectionManager/Event</eventSubURL>
                    <SCPDURL>/xml/ConnectionManager1.xml</SCPDURL>
                  </service>
                </serviceList>
              </device>
              <device>
                <deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType>
          <friendlyName>Kontor - Sonos Play:5 Media Renderer</friendlyName>
          <manufacturer>Sonos, Inc.</manufacturer>
          <manufacturerURL>http://www.sonos.com</manufacturerURL>
          <modelNumber>S5</modelNumber>
          <modelDescription>Sonos Play:5 Media Renderer</modelDescription>
          <modelName>Sonos Play:5</modelName>
          <modelURL>http://www.sonos.com/products/zoneplayers/S5</modelURL>
                <UDN>uuid:RINCON_000E5884455C01400_MR</UDN>
                <serviceList>
                  <service>
                    <serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>
                    <serviceId>urn:upnp-org:serviceId:RenderingControl</serviceId>
                    <controlURL>/MediaRenderer/RenderingControl/Control</controlURL>
                    <eventSubURL>/MediaRenderer/RenderingControl/Event</eventSubURL>
                    <SCPDURL>/xml/RenderingControl1.xml</SCPDURL>
                  </service>
                  <service>
                    <serviceType>urn:schemas-upnp-org:service:ConnectionManager:1</serviceType>
                    <serviceId>urn:upnp-org:serviceId:ConnectionManager</serviceId>
                    <controlURL>/MediaRenderer/ConnectionManager/Control</controlURL>
                    <eventSubURL>/MediaRenderer/ConnectionManager/Event</eventSubURL>
                    <SCPDURL>/xml/ConnectionManager1.xml</SCPDURL>
                  </service>
                  <service>
                    <serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
                    <serviceId>urn:upnp-org:serviceId:AVTransport</serviceId>
                    <controlURL>/MediaRenderer/AVTransport/Control</controlURL>
                    <eventSubURL>/MediaRenderer/AVTransport/Event</eventSubURL>
                    <SCPDURL>/xml/AVTransport1.xml</SCPDURL>
                  </service>
                  <service>
                    <serviceType>urn:schemas-sonos-com:service:Queue:1</serviceType>
                    <serviceId>urn:sonos-com:serviceId:Queue</serviceId>
                    <controlURL>/MediaRenderer/Queue/Control</controlURL>
                    <eventSubURL>/MediaRenderer/Queue/Event</eventSubURL>
                    <SCPDURL>/xml/Queue1.xml</SCPDURL>
                  </service>
              <service>
                <serviceType>urn:schemas-upnp-org:service:GroupRenderingControl:1</serviceType>
                <serviceId>urn:upnp-org:serviceId:GroupRenderingControl</serviceId>
                <controlURL>/MediaRenderer/GroupRenderingControl/Control</controlURL>
                <eventSubURL>/MediaRenderer/GroupRenderingControl/Event</eventSubURL>
                <SCPDURL>/xml/GroupRenderingControl1.xml</SCPDURL>
              </service>
                </serviceList>
                <X_Rhapsody-Extension """
        """xmlns="http://www.real.com/rhapsody/xmlns/upnp-1-0">
                  <deviceID>urn:rhapsody-real-com:device-id-1-0:"""
        """sonos_1:RINCON_000E5884455C01400</deviceID>
                    <deviceCapabilities>
                      <interactionPattern type="real-rhapsody-upnp-1-0"/>
                    </deviceCapabilities>
                </X_Rhapsody-Extension>
                <qq:X_QPlay_SoftwareCapability xmlns:qq="http://www.tencent.com">"""
        """QPlay:2</qq:X_QPlay_SoftwareCapability>
                <iconList>
                  <icon>
                    <mimetype>image/png</mimetype>
                    <width>48</width>
                    <height>48</height>
                    <depth>24</depth>
                    <url>/img/icon-S5.png</url>
                  </icon>
                </iconList>
              </device>
            </deviceList>
          </device>
        </root>
    """
    )

    @pytest.mark.parametrize("bad_ip_addr", ["not_ip", "555.555.555.555"])
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

    @pytest.mark.parametrize(
        "model_name",
        (
            ("Play:5", False),
            ("Sonos One", False),
            ("PLAYBAR", True),
            ("Sonos Beam", True),
            ("Sonos Playbar", True),
            ("Sonos Playbase", True),
            ("Sonos Arc", True),
            ("Sonos Arc SL", True),
        ),
    )
    def test_soco_is_soundbar(self, moco, model_name):
        moco._is_soundbar = None
        moco.speaker_info["model_name"] = model_name[0]
        assert moco.is_soundbar == model_name[1]

    @mock.patch("soco.core.requests")
    @pytest.mark.parametrize("refresh", [None, False, True])
    def test_soco_get_speaker_info_speaker_not_set_refresh(
        self, mocr, moco_zgs, refresh
    ):
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
            "http://" + IP_ADDR + ":1400/xml/device_description.xml",
            timeout=None,
        )
        should = {
            "zone_name": "Room",
            "player_icon": "/img/icon-S3.png",
            "uid": "RINCON_000XXX1400",
            "serial_number": "00-11-22-33-44-55:E",
            "software_version": "49.2-64250",
            "hardware_version": "1.8.1.2-2",
            "model_number": "S3",
            "model_name": "Sonos Play:3",
            "display_version": "10.1.2",
            "mac_address": "00-11-22-33-44-55",
        }
        assert should == res

    @mock.patch("soco.core.requests")
    @pytest.mark.parametrize("refresh", [None, False])
    def test_soco_get_speaker_info_speaker_set_no_refresh(
        self, mocr, moco_zgs, refresh
    ):
        """Internal speaker_info set; No refresh (default, False)

        => should not update
        """
        should = {"info": "yes"}
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
    @pytest.mark.parametrize("should", [{}, {"info": "yes"}])
    def test_soco_get_speaker_info_speaker_set_refresh(self, mocr, moco_zgs, should):
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
            "http://" + IP_ADDR + ":1400/xml/device_description.xml",
            timeout=None,
        )
        # get_speaker_info only updates internal speaker_info and does not
        # replace it
        should.update(
            {
                "zone_name": "Room",
                "player_icon": "/img/icon-S3.png",
                "uid": "RINCON_000XXX1400",
                "serial_number": "00-11-22-33-44-55:E",
                "software_version": "29.5-91030",
                "hardware_version": "1.8.1.2-2",
                "model_number": "S3",
                "model_name": "Sonos Play:3",
                "display_version": "10.1.2",
                "mac_address": "00-11-22-33-44-55",
            }
        )
        assert should == res


class TestAVTransport:
    @pytest.mark.parametrize(
        "playmode",
        [
            "NORMAL",
            "SHUFFLE_NOREPEAT",
            "SHUFFLE",
            "REPEAT_ALL",
            "SHUFFLE_REPEAT_ONE",
            "REPEAT_ONE",
        ],
    )
    def test_soco_play_mode_values(self, moco, playmode):
        moco.avTransport.GetTransportSettings.return_value = {"PlayMode": playmode}
        assert moco.play_mode == playmode
        moco.avTransport.GetTransportSettings.assert_called_once_with(
            [("InstanceID", 0)]
        )
        moco.avTransport.reset_mock()

    def test_soco_play_mode_bad_value(self, moco):
        with pytest.raises(KeyError):
            moco.play_mode = "BAD_VALUE"
        assert not moco.avTransport.SetPlayMode.called

    def test_soco_play_mode_lowercase(self, moco):
        moco.play_mode = "normal"
        moco.avTransport.SetPlayMode.assert_called_once_with(
            [("InstanceID", 0), ("NewPlayMode", "NORMAL")]
        )

    def test_available_actions(self, moco):
        moco.avTransport.GetCurrentTransportActions.return_value = {
            "Actions": "Set, Stop, Pause, Play, X_DLNA_SeekTime, X_DLNA_SeekTrackNr"
        }
        assert moco.available_actions == [
            "Set",
            "Stop",
            "Pause",
            "Play",
            "SeekTime",
            "SeekTrackNr",
        ]
        moco.avTransport.GetCurrentTransportActions.assert_called_once_with(
            [("InstanceID", 0)]
        )

    def test_soco_cross_fade2(self, moco):
        moco.avTransport.GetCrossfadeMode.return_value = {"CrossfadeMode": "1"}
        assert moco.cross_fade
        moco.avTransport.GetCrossfadeMode.return_value = {"CrossfadeMode": "0"}
        assert not moco.cross_fade
        moco.avTransport.GetCrossfadeMode.assert_called_with([("InstanceID", 0)])
        moco.cross_fade = True
        moco.avTransport.SetCrossfadeMode.assert_called_once_with(
            [("InstanceID", 0), ("CrossfadeMode", "1")]
        )

    def test_soco_play(self, moco):
        moco.play()
        moco.avTransport.Play.assert_called_once_with([("InstanceID", 0), ("Speed", 1)])

    # Test that uris are forced to Radio style display and controls when
    # force_radio is True prefix is replaced with "x-rincon-mp3radion://"
    # first set of test with no forcing, second set with force_radio=True

    # No forcing
    @pytest.mark.parametrize(
        "uri_in, uri_passed",
        [
            (
                "x-file-cifs://server/MyNiceRing.mp3",
                "x-file-cifs://server/MyNiceRing.mp3",
            ),
            (
                "http://archive.org/download/TenD2005-07-16t_64kb.mp3",
                "http://archive.org/download/TenD2005-07-16t_64kb.mp3",
            ),
            (
                "x-sonosapi-radio:station%3a%3aps.147077612?sid=203&flags=76&sn=2",
                "x-sonosapi-radio:station%3a%3aps.147077612?sid=203&flags=76&sn=2",
            ),
        ],
    )
    def test_soco_play_uri(self, moco, uri_in, uri_passed):
        moco.play_uri(uri_in)
        moco.avTransport.SetAVTransportURI.assert_called_once_with(
            [("InstanceID", 0), ("CurrentURI", uri_passed), ("CurrentURIMetaData", "")]
        )
        moco.avTransport.reset_mock()

    # with force_radio=True
    @pytest.mark.parametrize(
        "uri_in, uri_passed",
        [
            (
                "http://archive.org/download/TenD2005-07-16t_64kb.mp3",
                "x-rincon-mp3radio://archive.org/download/TenD2005-07-16t_64kb.mp3",
            ),
            (
                "https://archive.org/download/TenD2005-07-16t_64kb.mp3",
                "x-rincon-mp3radio://archive.org/download/TenD2005-07-16t_64kb.mp3",
            ),
            (
                "aac://icy-e-bz-04-cr.sharp-stream.com/magic1054.aac?amsparams="
                "playerid:BMUK_tunein;skey:1483570441&awparams=loggedin:false",
                "x-rincon-mp3radio://icy-e-bz-04-cr.sharp-stream.com/magic1054.aac?"
                "amsparams=playerid:BMUK_tunein;skey:1483570441&awparams=loggedin:"
                "false",
            ),
        ],
    )
    def test_soco_play_uri_force_radio(self, moco, uri_in, uri_passed):
        moco.play_uri(uri_in, force_radio=True)
        moco.avTransport.SetAVTransportURI.assert_called_once_with(
            [("InstanceID", 0), ("CurrentURI", uri_passed), ("CurrentURIMetaData", "")]
        )
        moco.avTransport.reset_mock()

    def test_soco_play_uri_calls_play(self, moco):
        uri = (
            "http://archive.org/download/tend2005-07-16.flac16/"
            "tend2005-07-16t10wonderboy_64kb.mp3"
        )
        moco.play_uri(uri)

        moco.avTransport.Play.assert_called_with([("InstanceID", 0), ("Speed", 1)])

    def test_soco_play_uri_with_title(self, moco):
        uri = (
            "http://archive.org/download/tend2005-07-16.flac16/"
            "tend2005-07-16t10wonderboy_64kb.mp3"
        )
        moco.play_uri(uri, title="<Fast & Loose>")

        moco.avTransport.SetAVTransportURI.assert_called_with(
            [
                ("InstanceID", 0),
                ("CurrentURI", uri),
                (
                    "CurrentURIMetaData",
                    '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                    'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                    'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
                    'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                    '<item id="R:0/0/0" parentID="R:0/0" restricted="true">'
                    "<dc:title>&lt;Fast &amp; Loose&gt;</dc:title>"
                    "<upnp:class>object.item.audioItem.audioBroadcast</upnp:class>"
                    '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:'
                    'metadata-1-0/">SA_RINCON65031_</desc></item></DIDL-Lite>',
                ),
            ]
        )

    def test_soco_pause(self, moco):
        moco.pause()
        moco.avTransport.Pause.assert_called_once_with(
            [("InstanceID", 0), ("Speed", 1)]
        )

    def test_soco_stop(self, moco):
        moco.stop()
        moco.avTransport.Stop.assert_called_once_with([("InstanceID", 0), ("Speed", 1)])

    def test_soco_next(self, moco):
        moco.next()
        moco.avTransport.Next.assert_called_once_with([("InstanceID", 0), ("Speed", 1)])

    def test_soco_previous(self, moco):
        moco.previous()
        moco.avTransport.Previous.assert_called_once_with(
            [("InstanceID", 0), ("Speed", 1)]
        )

    @pytest.mark.parametrize(
        "bad_timestamp", ["NOT_VALID", "12:34:56:78", "99", "12:3:4"]
    )
    def test_soco_seek_invalid(self, moco, bad_timestamp):
        with pytest.raises(ValueError):
            moco.seek(bad_timestamp)
        assert not moco.avTransport.Seek.called

    @pytest.mark.parametrize(
        "timestamp",
        [
            # '12:34', # Should this be valid?
            "1:23:45",
            "10:23:45",
            "12:78:78",  # Should this really be valid?
        ],
    )
    def test_soco_seek_valid(self, moco, timestamp):
        moco.seek(timestamp)
        moco.avTransport.Seek.assert_called_once_with(
            [("InstanceID", 0), ("Unit", "REL_TIME"), ("Target", timestamp)]
        )
        moco.avTransport.reset_mock()

    def test_soco_current_transport_info(self, moco):
        moco.avTransport.GetTransportInfo.return_value = {
            "CurrentTransportState": "PLAYING",
            "CurrentTransportStatus": "OK",
            "CurrentSpeed": "1",
        }
        playstate = moco.get_current_transport_info()
        moco.avTransport.GetTransportInfo.assert_called_once_with([("InstanceID", 0)])
        assert playstate["current_transport_state"] == "PLAYING"
        assert playstate["current_transport_status"] == "OK"
        assert playstate["current_transport_speed"] == "1"

    def test_soco_get_queue(self, moco):
        moco.contentDirectory.Browse.return_value = {
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<item id="Q:0/1" parentID="Q:0" restricted="true">'
                '<res protocolInfo="fake.com-fake-direct:*:audio/mp3:*" '
                'duration="0:02:32">radea:Tra.12345678.mp3</res>'
                "<upnp:albumArtURI>/getaa?r=1&amp;u=radea%3aTra.12345678.mp3"
                "</upnp:albumArtURI><dc:title>Item 1 Title</dc:title>"
                "<upnp:class>object.item.audioItem.musicTrack</upnp:class>"
                "<dc:creator>Item 1 Creator</dc:creator>"
                "<upnp:album>Item 1 Album</upnp:album></item></DIDL-Lite>"
            ),
            "NumberReturned": "1",
            "TotalMatches": "10",
            "UpdateID": "1",
        }
        queue = moco.get_queue(start=8, max_items=32)
        moco.contentDirectory.Browse.assert_called_once_with(
            [
                ("ObjectID", "Q:0"),
                ("BrowseFlag", "BrowseDirectChildren"),
                ("Filter", "*"),
                ("StartingIndex", 8),
                ("RequestedCount", 32),
                ("SortCriteria", ""),
            ]
        )
        assert queue is not None
        assert len(queue) == 1
        moco.contentDirectory.reset_mock()

    def test_soco_queue_size(self, moco):
        moco.contentDirectory.Browse.return_value = {
            "NumberReturned": "1",
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
                '<container id="Q:0" parentID="Q:" restricted="true" childCount="384">'
                "<dc:title>Queue Instance 0</dc:title><upnp:class>"
                "object.container.playlistContainer</upnp:class>"
                '<res protocolInfo="x-rincon-queue:*:*:*">'
                "x-rincon-queue:RINCON_00012345678901400#0</res>"
                "</container></DIDL-Lite>"
            ),
            "TotalMatches": "1",
            "UpdateID": "1",
        }
        queue_size = moco.queue_size
        moco.contentDirectory.Browse.assert_called_once_with(
            [
                ("ObjectID", "Q:0"),
                ("BrowseFlag", "BrowseMetadata"),
                ("Filter", "*"),
                ("StartingIndex", 0),
                ("RequestedCount", 1),
                ("SortCriteria", ""),
            ]
        )
        assert queue_size == 384
        moco.contentDirectory.reset_mock()

    def test_join(self, moco_zgs):
        moco2 = mock.Mock()
        moco2.uid = "RINCON_000XXX1400"
        moco_zgs.join(moco2)
        moco_zgs.avTransport.SetAVTransportURI.assert_called_once_with(
            [
                ("InstanceID", 0),
                ("CurrentURI", "x-rincon:RINCON_000XXX1400"),
                ("CurrentURIMetaData", ""),
            ]
        )

    def test_unjoin(self, moco_zgs):
        moco_zgs.unjoin()
        moco_zgs.avTransport.BecomeCoordinatorOfStandaloneGroup.assert_called_once_with(
            [("InstanceID", 0)]
        )

    def test_switch_to_line_in(self, moco_zgs):
        moco_zgs.avTransport.reset_mock()
        moco_zgs.switch_to_line_in()
        moco_zgs.avTransport.SetAVTransportURI.assert_called_once_with(
            [
                ("InstanceID", 0),
                ("CurrentURI", "x-rincon-stream:RINCON_000XXX1400"),
                ("CurrentURIMetaData", ""),
            ]
        )

        moco_zgs.avTransport.reset_mock()
        moco2 = mock.Mock()
        moco2.uid = "RINCON_000YYY1400"
        moco_zgs.switch_to_line_in(moco2)
        moco_zgs.avTransport.SetAVTransportURI.assert_called_once_with(
            [
                ("InstanceID", 0),
                ("CurrentURI", "x-rincon-stream:RINCON_000YYY1400"),
                ("CurrentURIMetaData", ""),
            ]
        )

    def test_switch_to_tv(self, moco_zgs):
        moco_zgs.avTransport.reset_mock()
        moco_zgs.switch_to_tv()
        moco_zgs.avTransport.SetAVTransportURI.assert_called_once_with(
            [
                ("InstanceID", 0),
                ("CurrentURI", "x-sonos-htastream:RINCON_000XXX1400:spdif"),
                ("CurrentURIMetaData", ""),
            ]
        )

    def test_is_playing_tv(self, moco):
        moco.avTransport.reset_mock()
        moco.avTransport.GetPositionInfo.return_value = {
            "TrackURI": "x-sonos-htastream:RINCON_00012345678901234:spdif"
        }
        playing_tv = moco.is_playing_tv
        assert playing_tv
        moco.avTransport.GetPositionInfo.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master")]
        )

        moco.avTransport.GetPositionInfo.return_value = {
            "TrackURI": "not-tv",
        }
        playing_tv = moco.is_playing_tv
        assert not playing_tv

    def test_is_playing_radio(self, moco):
        moco.avTransport.reset_mock()
        moco.avTransport.GetPositionInfo.return_value = {
            "TrackURI": "x-rincon-mp3radio://example.com:80/myradio"
        }
        playing_tv = moco.is_playing_radio
        assert playing_tv
        moco.avTransport.GetPositionInfo.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master")]
        )

        moco.avTransport.GetPositionInfo.return_value = {
            "TrackURI": "not-radio",
        }
        playing_tv = moco.is_playing_radio
        assert not playing_tv

    def test_is_playing_line_in(self, moco):
        moco.avTransport.reset_mock()
        moco.avTransport.GetPositionInfo.return_value = {
            "TrackURI": "x-rincon-stream:blah-blah"
        }
        playing_tv = moco.is_playing_line_in
        assert playing_tv
        moco.avTransport.GetPositionInfo.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master")]
        )

        moco.avTransport.GetPositionInfo.return_value = {
            "TrackURI": "not-line-in",
        }
        playing_tv = moco.is_playing_line_in
        assert not playing_tv

    def test_create_sonos_playlist(self, moco):
        playlist_name = "cool music"
        playlist_id = 1
        moco.avTransport.CreateSavedQueue.return_value = {
            "AssignedObjectID": "SQ:{}".format(playlist_id)
        }
        playlist = moco.create_sonos_playlist(playlist_name)
        moco.avTransport.CreateSavedQueue.assert_called_once_with(
            [
                ("InstanceID", 0),
                ("Title", playlist_name),
                ("EnqueuedURI", ""),
                ("EnqueuedURIMetaData", ""),
            ]
        )
        assert playlist.title == playlist_name
        expected_uri = "file:///jffs/settings/savedqueues.rsq#{}".format(playlist_id)
        assert playlist.resources[0].uri == expected_uri
        assert playlist.parent_id == "SQ:"

    def test_create_sonos_playlist_from_queue(self, moco):
        playlist_name = "saved queue"
        playlist_id = 1
        moco.avTransport.SaveQueue.return_value = {
            "AssignedObjectID": "SQ:{}".format(playlist_id)
        }
        playlist = moco.create_sonos_playlist_from_queue(playlist_name)
        moco.avTransport.SaveQueue.assert_called_once_with(
            [("InstanceID", 0), ("Title", playlist_name), ("ObjectID", "")]
        )
        assert playlist.title == playlist_name
        expected_uri = "file:///jffs/settings/savedqueues.rsq#{}".format(playlist_id)
        assert playlist.resources[0].uri == expected_uri
        assert playlist.parent_id == "SQ:"

    def test_add_item_to_sonos_playlist(self, moco):
        moco.contentDirectory.reset_mock()

        playlist = mock.Mock()
        playlist.item_id = 7

        ressource = mock.Mock()
        ressource.uri = "fake_uri"
        track = mock.Mock()
        track.resources = [ressource]
        track.uri = "fake_uri"
        track.to_element.return_value = XML.Element("a")

        update_id = 100

        moco.contentDirectory.Browse.return_value = {
            "NumberReturned": "0",
            "Result": (
                '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
                'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
                'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"></DIDL-Lite>'
            ),
            "TotalMatches": "0",
            "UpdateID": update_id,
        }

        moco.add_item_to_sonos_playlist(track, playlist)
        moco.contentDirectory.Browse.assert_called_once_with(
            [
                ("ObjectID", playlist.item_id),
                ("BrowseFlag", "BrowseDirectChildren"),
                ("Filter", "*"),
                ("StartingIndex", 0),
                ("RequestedCount", 1),
                ("SortCriteria", ""),
            ]
        )
        moco.avTransport.AddURIToSavedQueue.assert_called_once_with(
            [
                ("InstanceID", 0),
                ("UpdateID", update_id),
                ("ObjectID", playlist.item_id),
                ("EnqueuedURI", track.uri),
                ("EnqueuedURIMetaData", to_didl_string(track)),
                ("AddAtIndex", 4294967295),
            ]
        )

    def test_soco_cross_fade(self, moco):
        moco.avTransport.GetCrossfadeMode.return_value = {"CrossfadeMode": "1"}
        assert moco.cross_fade
        moco.avTransport.GetCrossfadeMode.assert_called_once_with([("InstanceID", 0)])
        moco.cross_fade = False
        moco.avTransport.SetCrossfadeMode.assert_called_once_with(
            [("InstanceID", 0), ("CrossfadeMode", "0")]
        )

    def test_shuffle(self, moco):
        moco.avTransport.GetTransportSettings.return_value = {"PlayMode": "NORMAL"}
        assert moco.shuffle is False
        moco.avTransport.GetTransportSettings.assert_called_once_with(
            [("InstanceID", 0)]
        )
        moco.shuffle = True
        moco.avTransport.SetPlayMode.assert_called_once_with(
            [("InstanceID", 0), ("NewPlayMode", "SHUFFLE_NOREPEAT")]
        )

        moco.avTransport.GetTransportSettings.return_value = {
            "PlayMode": "SHUFFLE_NOREPEAT"
        }
        assert moco.shuffle is True
        moco.avTransport.GetTransportSettings.assert_called_with([("InstanceID", 0)])
        moco.shuffle = False
        moco.avTransport.SetPlayMode.assert_called_with(
            [("InstanceID", 0), ("NewPlayMode", "NORMAL")]
        )

    def test_repeat(self, moco):
        moco.avTransport.GetTransportSettings.return_value = {"PlayMode": "NORMAL"}
        assert moco.repeat is False
        moco.avTransport.GetTransportSettings.assert_called_with([("InstanceID", 0)])
        moco.repeat = True
        moco.avTransport.SetPlayMode.assert_called_with(
            [("InstanceID", 0), ("NewPlayMode", "REPEAT_ALL")]
        )

        moco.avTransport.GetTransportSettings.return_value = {"PlayMode": "REPEAT_ALL"}
        assert moco.repeat is True
        moco.avTransport.GetTransportSettings.assert_called_with([("InstanceID", 0)])
        moco.repeat = False
        moco.avTransport.SetPlayMode.assert_called_with(
            [("InstanceID", 0), ("NewPlayMode", "NORMAL")]
        )

        moco.avTransport.GetTransportSettings.return_value = {"PlayMode": "REPEAT_ONE"}
        assert moco.repeat == "ONE"
        moco.avTransport.GetTransportSettings.assert_called_with([("InstanceID", 0)])
        moco.repeat = "ONE"
        moco.avTransport.SetPlayMode.assert_called_with(
            [("InstanceID", 0), ("NewPlayMode", "REPEAT_ONE")]
        )

    def test_set_sleep_timer(self, moco):
        moco.avTransport.reset_mock()
        moco.avTransport.ConfigureSleepTimer.return_value = None
        result = moco.set_sleep_timer(None)
        assert result is None
        moco.avTransport.ConfigureSleepTimer.assert_called_once_with(
            [("InstanceID", 0), ("NewSleepTimerDuration", "")]
        )

        moco.avTransport.reset_mock()
        moco.avTransport.ConfigureSleepTimer.return_value = None
        result = moco.set_sleep_timer(7200)
        assert result is None
        moco.avTransport.ConfigureSleepTimer.assert_called_once_with(
            [("InstanceID", 0), ("NewSleepTimerDuration", "2:00:00")]
        )

        moco.avTransport.reset_mock()
        moco.avTransport.ConfigureSleepTimer.return_value = None
        result = moco.set_sleep_timer(0)
        assert result is None
        moco.avTransport.ConfigureSleepTimer.assert_called_once_with(
            [("InstanceID", 0), ("NewSleepTimerDuration", "0:00:00")]
        )

    @pytest.mark.parametrize("bad_sleep_time", ["BadTime", "00:43:23", "4200s", ""])
    def test_set_sleep_timer_bad_sleep_time(self, moco, bad_sleep_time):
        with pytest.raises(ValueError):
            result = moco.set_sleep_timer(bad_sleep_time)

    def test_get_sleep_timer(self, moco):
        moco.avTransport.reset_mock()
        moco.avTransport.GetRemainingSleepTimerDuration.return_value = {
            "RemainingSleepTimerDuration": "02:00:00",
            "CurrentSleepTimerGeneration": "3",
        }
        result = moco.get_sleep_timer()
        assert result == 7200

        moco.avTransport.reset_mock()
        moco.avTransport.GetRemainingSleepTimerDuration.return_value = {
            "RemainingSleepTimerDuration": "",
            "CurrentSleepTimerGeneration": "0",
        }
        result = moco.get_sleep_timer()
        assert result is None


class TestContentDirectory:
    def test_remove_sonos_playlist_success(self, moco):
        moco.contentDirectory.reset_mock()
        moco.contentDirectory.return_value = True
        result = moco.remove_sonos_playlist("SQ:10")
        moco.contentDirectory.DestroyObject.assert_called_once_with(
            [("ObjectID", "SQ:10")]
        )
        assert result


class TestRenderingControl:
    def test_soco_mute(self, moco):
        moco.renderingControl.GetMute.return_value = {"CurrentMute": "1"}
        assert moco.mute
        moco.renderingControl.reset_mock()
        moco.renderingControl.GetMute.return_value = {"CurrentMute": "0"}
        assert not moco.mute
        moco.renderingControl.GetMute.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master")]
        )
        moco.mute = False
        moco.renderingControl.SetMute.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master"), ("DesiredMute", "0")]
        )
        moco.renderingControl.reset_mock()
        moco.mute = True
        moco.renderingControl.SetMute.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master"), ("DesiredMute", "1")]
        )

    @pytest.mark.parametrize("volume", [1, 4, 10, 100])
    def test_soco_volume(self, moco, volume):
        moco.renderingControl.GetVolume.return_value = {"CurrentVolume": volume}
        assert moco.volume == volume
        moco.renderingControl.GetVolume.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master")]
        )
        moco.renderingControl.reset_mock()

    @pytest.mark.parametrize(
        "vol_set, vol_called",
        [
            (-120, 0),
            (-10, 0),
            (0, 0),
            (5, 5),
            (99, 99),
            (100, 100),
            (110, 100),
            (300, 100),
        ],
    )
    def soco_volume_set(self, moco, vol_set, vol_called):
        moco.volume = vol_set
        moco.renderingControl.SetVolume.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master"), ("DesiredVolume", vol_called)]
        )

    def test_soco_ramp_to_volume(self, moco):
        moco.renderingControl.RampToVolume.return_value = {"RampTime": "12"}
        ramp_time = moco.ramp_to_volume(15)
        moco.renderingControl.RampToVolume.assert_called_once_with(
            [
                ("InstanceID", 0),
                ("Channel", "Master"),
                ("RampType", "SLEEP_TIMER_RAMP_TYPE"),
                ("DesiredVolume", 15),
                ("ResetVolumeAfter", False),
                ("ProgramURI", ""),
            ]
        )
        assert ramp_time == 12

    def test_set_relative_volume(self, moco):
        moco.renderingControl.SetRelativeVolume.return_value = {"NewVolume": "75"}
        new_volume = moco.set_relative_volume(25)
        moco.renderingControl.SetRelativeVolume.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master"), ("Adjustment", 25)]
        )
        assert new_volume == 75

    def test_soco_treble(self, moco):
        moco.renderingControl.GetTreble.return_value = {"CurrentTreble": "15"}
        assert moco.treble == 15
        moco.renderingControl.GetTreble.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master")]
        )
        moco.treble = "10"
        moco.renderingControl.SetTreble.assert_called_once_with(
            [("InstanceID", 0), ("DesiredTreble", 10)]
        )

    def test_soco_loudness(self, moco):
        moco.renderingControl.GetLoudness.return_value = {"CurrentLoudness": "1"}
        assert moco.loudness
        moco.renderingControl.GetLoudness.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master")]
        )
        moco.loudness = False
        moco.renderingControl.SetLoudness.assert_called_once_with(
            [("InstanceID", 0), ("Channel", "Master"), ("DesiredLoudness", "0")]
        )

    def test_soco_trueplay(self, moco):
        moco.renderingControl.GetRoomCalibrationStatus.return_value = {
            "RoomCalibrationAvailable": "0",
            "RoomCalibrationEnabled": "0",
        }
        assert moco.trueplay is None
        moco.renderingControl.GetRoomCalibrationStatus.assert_called_with(
            [("InstanceID", 0)]
        )
        moco.renderingControl.GetRoomCalibrationStatus.return_value = {
            "RoomCalibrationAvailable": "1",
            "RoomCalibrationEnabled": "1",
        }
        assert moco.trueplay
        moco.renderingControl.GetRoomCalibrationStatus.assert_called_with(
            [("InstanceID", 0)]
        )
        # Setter tests for 'is_visible' property, so this needs to be
        # mocked.
        with mock.patch(
            "soco.SoCo.is_visible", new_callable=mock.PropertyMock
        ) as mock_is_visible:
            mock_is_visible.return_value = True
            moco.trueplay = False
            moco.renderingControl.SetRoomCalibrationStatus.assert_called_with(
                [
                    ("InstanceID", 0),
                    ("RoomCalibrationEnabled", "0"),
                ]
            )
            moco.trueplay = True
            moco.renderingControl.SetRoomCalibrationStatus.assert_called_with(
                [
                    ("InstanceID", 0),
                    ("RoomCalibrationEnabled", "1"),
                ]
            )
            # Check for exception if attempt to set the property on a
            # non-visible speaker.
            mock_is_visible.return_value = False
            with pytest.raises(SoCoNotVisibleException):
                moco.trueplay = True

    def test_soco_fixed_volume(self, moco):
        moco.renderingControl.GetSupportsOutputFixed.return_value = {
            "CurrentSupportsFixed": "1"
        }
        assert moco.supports_fixed_volume
        moco.renderingControl.GetSupportsOutputFixed.assert_called_with(
            [("InstanceID", 0)]
        )
        moco.renderingControl.GetSupportsOutputFixed.return_value = {
            "CurrentSupportsFixed": "0"
        }
        assert not moco.supports_fixed_volume
        moco.renderingControl.GetSupportsOutputFixed.assert_called_with(
            [("InstanceID", 0)]
        )
        moco.renderingControl.GetOutputFixed.return_value = {"CurrentFixed": "1"}
        assert moco.fixed_volume
        moco.renderingControl.GetOutputFixed.assert_called_once_with(
            [("InstanceID", 0)]
        )
        moco.fixed_volume = False
        moco.renderingControl.SetOutputFixed.assert_called_once_with(
            [("InstanceID", 0), ("DesiredFixed", "0")]
        )
        moco.renderingControl.SetOutputFixed.side_effect = SoCoUPnPException(
            None, None, None
        )
        with pytest.raises(NotSupportedException):
            moco.fixed_volume = True

    def test_soco_balance(self, moco):
        # GetVolume is called twice, once for each of the left
        # and right channels
        moco.renderingControl.GetVolume.return_value = {"CurrentVolume": "100"}
        assert moco.balance == (100, 100)
        moco.renderingControl.GetVolume.assert_any_call(
            [("InstanceID", 0), ("Channel", "LF")]
        )
        moco.renderingControl.GetVolume.assert_any_call(
            [
                ("InstanceID", 0),
                ("Channel", "RF"),
            ]
        )
        # SetVolume is called twice, once for each of the left
        # and right channels
        moco.balance = (0, 100)
        moco.renderingControl.SetVolume.assert_any_call(
            [("InstanceID", 0), ("Channel", "LF"), ("DesiredVolume", 0)]
        )
        moco.renderingControl.SetVolume.assert_any_call(
            [("InstanceID", 0), ("Channel", "RF"), ("DesiredVolume", 100)]
        )


class TestDeviceProperties:
    def test_soco_status_light(self, moco):
        moco.deviceProperties.GetLEDState.return_value = {"CurrentLEDState": "On"}
        assert moco.status_light
        moco.deviceProperties.GetLEDState.return_value = {"CurrentLEDState": "Off"}
        assert not moco.status_light
        moco.deviceProperties.GetLEDState.assert_called_with()
        moco.status_light = False
        moco.deviceProperties.SetLEDState.assert_called_once_with(
            [("DesiredLEDState", "Off")]
        )
        moco.status_light = True
        moco.deviceProperties.SetLEDState.assert_called_with(
            [("DesiredLEDState", "On")]
        )

    def test_buttons_enabled(self, moco):
        moco.deviceProperties.GetButtonLockState.return_value = {
            "CurrentButtonLockState": "On"
        }
        assert not moco.buttons_enabled
        moco.deviceProperties.GetButtonLockState.return_value = {
            "CurrentButtonLockState": "Off"
        }
        assert moco.buttons_enabled
        moco.deviceProperties.GetButtonLockState.assert_called_with()
        # Setter tests for 'is_visible' property, so this needs to be
        # mocked.
        with mock.patch(
            "soco.SoCo.is_visible", new_callable=mock.PropertyMock
        ) as mock_is_visible:
            mock_is_visible.return_value = True
            moco.buttons_enabled = False
            moco.deviceProperties.SetButtonLockState.assert_called_once_with(
                [("DesiredButtonLockState", "On")]
            )
            moco.buttons_enabled = True
            moco.deviceProperties.SetButtonLockState.assert_called_with(
                [("DesiredButtonLockState", "Off")]
            )
            # Check for exception if attempt to set the property on a
            # non-visible speaker.
            mock_is_visible.return_value = False
            with pytest.raises(SoCoNotVisibleException):
                moco.buttons_enabled = True

    def test_soco_set_player_name(self, moco):
        moco.player_name = "μИⅠℂ☺ΔЄ💋"
        moco.deviceProperties.SetZoneAttributes.assert_called_once_with(
            [
                ("DesiredZoneName", "μИⅠℂ☺ΔЄ💋"),
                ("DesiredIcon", ""),
                ("DesiredConfiguration", ""),
            ]
        )

    def test_create_stereo_pair(self, moco):
        """Tests for a well-formed call to create a stereo pair.

        Creates a SoCo object for the slave (RH) speaker, and
        checks for the correct call with the correct parameters.
        """
        moco2 = mock.Mock()
        moco2.uid = "RINCON_000XXY1400"
        moco.create_stereo_pair(moco2)
        moco.deviceProperties.AddBondedZones.assert_called_once_with(
            [("ChannelMapSet", "RINCON_000XXX1400:LF,LF;RINCON_000XXY1400:RF,RF")]
        )

    def test_separate_stereo_pair(self, moco):
        """Tests for a well-formed call to separate a stereo pair."""
        moco.separate_stereo_pair()
        moco.deviceProperties.RemoveBondedZones.assert_called_once_with(
            [("ChannelMapSet", ""), ("KeepGrouped", "0")]
        )

    def test_get_battery_info(self, moco):
        url = "http://" + moco.ip_address + ":1400/status/batterystatus"

        # A speaker that returns battery information
        with requests_mock.Mocker() as m:
            response_text = (
                '<?xml version="1.0" ?>\n<?xml-stylesheet type="text/xsl"'
                + 'href="/xml/review.xsl"?><ZPSupportInfo><LocalBatteryStatus>\n'
                + '<Data name="Health">GREEN</Data>\n<Data name="Level">100</Data>\n'
                + '<Data name="Temperature">NORMAL</Data>\n'
                + '<Data name="PowerSource">SONOS_CHARGING_RING</Data>\n'
                + "</LocalBatteryStatus></ZPSupportInfo>"
            )
            m.get(url, text=response_text)
            assert moco.get_battery_info() == {
                "Health": "GREEN",
                "Level": 100,
                "Temperature": "NORMAL",
                "PowerSource": "SONOS_CHARGING_RING",
            }

        # A speaker that doesn't have battery information
        with requests_mock.Mocker() as m:
            response_text = (
                '<?xml version="1.0" ?>\n'
                + '<?xml-stylesheet type="text/xsl" href="/xml/review.xsl"?>'
                + "<ZPSupportInfo></ZPSupportInfo>"
            )
            m.get(url, text=response_text)
            with pytest.raises(NotSupportedException):
                moco.get_battery_info()

        # A network request that fails
        with requests_mock.Mocker() as m:
            m.get(url, status_code=404)
            with pytest.raises(ConnectionError):
                moco.get_battery_info()


class TestZoneGroupTopology:
    def test_soco_uid(self, moco_zgs):
        assert moco_zgs.uid == "RINCON_000XXX1400"

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
            print("GROUP", group.coordinator)
            print(group)
            assert group.coordinator is not None

    def test_group(self, moco_zgs):
        assert isinstance(moco_zgs.group, ZoneGroup)
        assert moco_zgs in moco_zgs.group

    def test_all_zones(selfself, moco_zgs):
        zones = moco_zgs.all_zones
        assert len(zones) == 4
        assert len(set(zones)) == 4
        for zone in zones:
            assert isinstance(zone, SoCo)
        assert moco_zgs in zones

    def test_visible_zones(selfself, moco_zgs):
        zones = moco_zgs.visible_zones
        assert len(zones) == 4
        assert len(set(zones)) == 4
        for zone in zones:
            assert isinstance(zone, SoCo)
        assert moco_zgs in zones

    def test_group_label(selfself, moco_zgs):
        g = moco_zgs.group
        # Have to mock out group members zone group state here since
        # g.members is parsed from the XML.
        for speaker in g.members:
            speaker.zoneGroupTopology.GetZoneGroupState.return_value = {
                "ZoneGroupState": ZGS
            }
        assert g.label == "Kitchen, Living Room"

    def test_group_short_label(selfself, moco_zgs):
        g = moco_zgs.group
        # Have to mock out group members zone group state here since
        # g.members is parsed from the XML.
        for speaker in g.members:
            speaker.zoneGroupTopology.GetZoneGroupState.return_value = {
                "ZoneGroupState": ZGS
            }
        assert g.short_label == "Kitchen + 1"

    def test_group_volume(self, moco_zgs):
        g = moco_zgs.group
        c = moco_zgs.group.coordinator
        c.groupRenderingControl.GetGroupVolume.return_value = {"CurrentVolume": 50}
        assert g.volume == 50
        c.groupRenderingControl.GetGroupVolume.assert_called_once_with(
            [("InstanceID", 0)]
        )
        g.volume = 75
        c.groupRenderingControl.SetGroupVolume.assert_called_once_with(
            [("InstanceID", 0), ("DesiredVolume", 75)]
        )

    def test_group_mute(self, moco_zgs):
        g = moco_zgs.group
        c = moco_zgs.group.coordinator
        c.groupRenderingControl.GetGroupMute.return_value = {"CurrentMute": "0"}
        assert g.mute is False
        c.groupRenderingControl.GetGroupMute.assert_called_once_with(
            [("InstanceID", 0)]
        )
        g.mute = True
        c.groupRenderingControl.SetGroupMute.assert_called_once_with(
            [("InstanceID", 0), ("DesiredMute", "1")]
        )

    def test_set_relative_group_volume(self, moco_zgs):
        g = moco_zgs.group
        c = moco_zgs.group.coordinator
        c.groupRenderingControl.SetRelativeGroupVolume.return_value = {
            "NewVolume": "75"
        }
        new_volume = g.set_relative_volume(25)
        c.groupRenderingControl.SetRelativeGroupVolume.assert_called_once_with(
            [("InstanceID", 0), ("Adjustment", 25)]
        )
        assert new_volume == 75


def test_only_on_master_true(moco_only_on_master):
    with mock.patch(
        "soco.SoCo.is_coordinator", new_callable=mock.PropertyMock
    ) as is_coord:
        is_coord.return_value = True
        moco_only_on_master.play()
        is_coord.assert_called_once_with()


def test_not_on_master_false(moco_only_on_master):
    with mock.patch(
        "soco.SoCo.is_coordinator", new_callable=mock.PropertyMock
    ) as is_coord:
        is_coord.return_value = False
        with pytest.raises(SoCoSlaveException):
            moco_only_on_master.play()
        is_coord.assert_called_once_with()
