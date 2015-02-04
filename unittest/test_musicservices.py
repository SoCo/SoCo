# -*- coding: utf-8 -*-
""" Tests for the music_service module """

from __future__ import unicode_literals
import pytest
import mock
from pysimplesoap.client import SoapClient
from soco.exceptions import MusicServiceException
from soco.music_services.music_service import MusicAccount
from soco.music_services.music_service import MusicService
from soco.music_services.music_service import desc_from_uri


# Typical account data from http://{Sonos-ip}:1400/status/accounts
ACCOUNT_DATA="""<?xml version="1.0" ?>
<ZPSupportInfo type="User">
    <Accounts
    LastUpdateDevice="RINCON_000XXXXXXXX400" Version="8" NextSerialNum="5">
    <Account Type="2311" SerialNum="1">
        <UN>12345678</UN>
        <MD>1</MD>
        <NN></NN>
        <OADevID></OADevID>
        <Key></Key>
    </Account>
    <Account Type="41735" SerialNum="3">
        <UN></UN>
        <MD>1</MD>
        <NN></NN>
        <OADevID></OADevID>
        <Key></Key>
    </Account>
    <Account Type="519" SerialNum="4" Deleted="1">
        <UN>email@example.com</UN>
        <MD>1</MD>
        <NN>myservice</NN>
        <OADevID></OADevID>
        <Key></Key>
    </Account>
    <Account Type="41479" SerialNum="2">
    <UN></UN>
    <MD>1</MD>
    <NN></NN>
    <OADevID></OADevID>
    <Key></Key></Account></Accounts>
</ZPSupportInfo>"""

# Typical service descriptor list
# available_services = device.musicServices.ListAvailableServices()
# descriptor_list_xml = available_services['AvailableServiceDescriptorList']
# The list has been edited to include services represented in ACCOUNT_DATA
SERVICES_DESCRIPTOR_LIST = """<?xml version="1.0"?>
<Services
    SchemaVersion="1">
    <Service
        Id="163"
        Name="Spreaker"
        Version="1.1"
        Uri="http://sonos.spreaker.com/sonos/service/v1"
        SecureUri="https://sonos.spreaker.com/sonos/service/v1"
        ContainerType="MService"
        Capabilities="513"
        MaxMessagingChars="0">
        <Policy
            Auth="Anonymous"
            PollInterval="30" />
        <Presentation>
            <Strings
                Version="1"
                Uri="https://www.spreaker.com/sonos/string_table.xml" />
            <PresentationMap
                Version="2"
                Uri="https://www.spreaker.com/sonos/presentation_map.xml" />
        </Presentation>
    </Service>
    <Service
        Id="162"
        Name="radioPup"
        Version="1.1"
        Uri="http://sonos.townsquaremedia.com/index.php"
        SecureUri="https://sonos.townsquaremedia.com/index.php"
        ContainerType="MService"
        Capabilities="513"
        MaxMessagingChars="0">
        <Policy
            Auth="Anonymous"
            PollInterval="3600" />
        <Presentation>
            <Strings
                Version="1"
                Uri="http://sonos.townsquaremedia.com/strings.xml" />
            <PresentationMap
                Version="1"
                Uri="http://sonos.townsquaremedia.com/pmap.xml" />
        </Presentation>
    </Service>
    <Service
        Id="9"
        Name="Spotify"
        Version="1.1"
        Uri="https://spotify.ws.sonos.com/smapi"
        SecureUri="https://spotify.ws.sonos.com/smapi"
        ContainerType="MService"
        Capabilities="2563"
        MaxMessagingChars="0">
        <Policy
            Auth="DeviceLink"
            PollInterval="30" />
        <Presentation>
            <Strings
                Version="11"
                Uri="http://spotify-static-resources.s3.amazonaws.com/strings.xml" />
            <PresentationMap
                Version="8"
                Uri="http://sonos-pmap.ws.sonos.com/spotify_pmap.8.xml" />
        </Presentation>
    </Service>
    <Service
        Id="2"
        Name="Deezer"
        Version="1.1"
        Uri="http://deezer.ws.sonos.com/services/smapi"
        SecureUri="https://deezer.ws.sonos.com/services/smapi"
        ContainerType="MService"
        Capabilities="563"
        MaxMessagingChars="0">
        <Policy
            Auth="UserId"
            PollInterval="300" />
        <Presentation>
            <Strings
                Version="5"
                Uri="http://static.deezer.sonos-ws-us.com/strings.xml" />
            <PresentationMap
                Version="4"
                Uri="http://sonos-pmap.ws.sonos.com/deezer_pmap.4.xml" />
        </Presentation>
    </Service>
    <Service
        Id="254"
        Name="TuneIn" Version="1.1"
        Uri="http://legato.radiotime.com/Radio.asmx"
        SecureUri="http://legato.radiotime.com/Radio.asmx"
        ContainerType="MService"
        Capabilities="0"
        MaxMessagingChars="0">
        <Policy
            Auth="Anonymous"
            PollInterval="0"/>
        <Presentation>
        </Presentation>
    </Service>
    <Service
        Id="160"
        Name="SoundCloud"
        Version="1.1"
        Uri="https://soundcloud.ws.sonos.com/smapi"
        SecureUri="https://soundcloud.ws.sonos.com/smapi"
        ContainerType="MService"
        Capabilities="515"
        MaxMessagingChars="0">
        <Policy
            Auth="DeviceLink"
            PollInterval="30"/>
        <Presentation>
            <Strings Version="11" Uri="http://soundcloud-static.ws.sonos.com/strings.xml"/>
            <PresentationMap Version="11" Uri="http://soundcloud-static.ws.sonos.com/pmap.xml"/>
        </Presentation>
    </Service>
</Services>
"""
HEADER = """<s:Header>
    <credentials xmlns="http://www.sonos.com/Services/1.1">
        <deviceId>00-0E-58-XX-XX-XX:D</deviceId>
        <deviceProvider>Sonos</deviceProvider>
        <sessionId>praFt7jMSd546905c3243bdgBsq1n7S547905c3243f47LqmHH:2:123456789</sessionId>
    </credentials>
    </s:Header>"""

@pytest.fixture(autouse=True)
def patch_music_services(monkeypatch):
    """Patch MusicService and MusicAccount to avoid network requests and use
    dummy data."""
    monkeypatch.setattr(
        MusicService, 'get_music_services_data_xml',
        mock.Mock(return_value=SERVICES_DESCRIPTOR_LIST))
    monkeypatch.setattr(
        MusicService, '_get_headers',
        mock.Mock(return_value=HEADER)
    )
    # ensure that the soap client cannot use the network
    monkeypatch.setattr(
        SoapClient, 'call', mock.MagicMock()
    )
    monkeypatch.setattr(
        MusicAccount, '_get_account_xml',
        mock.Mock(return_value=ACCOUNT_DATA))

def test_initialise_account():
    assert MusicAccount._account_data is None
    accounts = MusicAccount.get_account_data()
    assert len(accounts) == 4
    assert accounts['1'].username == '12345678'
    assert accounts['1'].account_type == '2311'
    assert accounts['1'].deleted == False
    assert accounts['1'].nickname == ''
    assert accounts['4'].account_type == '519'
    assert accounts['4'].username == 'email@example.com'
    assert accounts['4'].serial_number == '4'
    assert accounts['4'].nickname == "myservice"
    assert accounts['4'].deleted == True

def test_get_all_accounts():
    a = MusicAccount.get_all_accounts()
    assert len(a) == 3

def test_get_accounts_for_service():
    a = MusicAccount.get_accounts_for_service('2311')
    assert len(a) == 1
    assert a[0].username == "12345678"

def test_initialise_services():
    assert MusicService._music_services_data is None
    data = MusicService.get_music_services_data()
    assert len(data) == 6
    deezer = data['519']
    assert deezer['Name'] == "Deezer"
    assert deezer['Capabilities'] == '563'
    assert deezer['Auth'] == 'UserId'
    assert deezer['Version'] == '1.1'
    assert deezer['ContainerType'] == 'MService'
    assert deezer['Id'] == '2'
    assert deezer['PresentationMapUri'] == 'http://sonos-pmap.ws.sonos.com/deezer_pmap.4.xml'
    assert deezer['ServiceType'] == '519'

def test_get_data_for_name():
    s = MusicService.get_data_for_name('Spotify')
    assert s['Name'] == "Spotify"
    assert s['Capabilities'] == '2563'

def test_get_names():
    names = MusicService.get_all_music_services_names()
    assert len(names) == 6
    assert "Spotify" in names
    assert "Deezer" in names

def test_create_music_service():
    ms = MusicService('Spotify')
    assert ms.account.username == '12345678'
    with pytest.raises(MusicServiceException) as excinfo:
        unknown = MusicService('Unknown Music Service')
    assert 'Unknown music service' in str(excinfo.value)
    with pytest.raises(MusicServiceException) as excinfo:
        soundcloud = MusicService('SoundCloud')
    assert 'No account found' in str(excinfo.value)

def test_tunein():
    """TuneIn is handles specially by MusicServices"""
    tunein = MusicService('TuneIn')
    assert tunein

def test_search():
    spotify = MusicService('Spotify')
    # Set up dummy search categories
    spotify._get_search_prefix_map = lambda: {
        'stations': 'search:station',
        'shows': 'search:show',
        'hosts': 'search:host',
    }
    categories = spotify.available_search_categories
    assert len(categories) == 3
    for c in ('stations', 'shows', 'hosts'):
        assert c in categories
    with pytest.raises(MusicServiceException) as excinfo:
        spotify.search('badcategory')
    assert "support the 'badcategory' search category" in str(excinfo.value)

def test_desc_from_uri():
    URI = 'x-sonos-http:track%3a3402413.mp3?sid=2&amp;flags=32&amp;sn=4'
    assert desc_from_uri(URI) == 'SA_RINCON519_email@example.com'
    SID_ONLY = 'x-sonos-http:track%3a3402413.mp3?sid=9&amp;flags=32'
    assert desc_from_uri(SID_ONLY) == 'SA_RINCON2311_12345678'
    UNKNOWN_AC_AND_SID = 'x-sonos-http:track%3a3402413.mp3?sid=2&amp;flags=32&amp;sn=400'
    UNKNOWN_AC_WITH_SID = 'x-sonos-http:track%3a3402413.mp3?sid=9&amp;flags=32&amp;sn=400'
    assert desc_from_uri(UNKNOWN_AC_WITH_SID) == 'SA_RINCON2311_12345678'
    NO_DATA = 'x-sonos-http:track%3a3402413.mp3?flags=32'
    assert desc_from_uri(NO_DATA) == 'RINCON_AssociatedZPUDN'
