"""Tests for the music_service module."""


from unittest import mock
import pytest

import soco.soap
from soco.exceptions import MusicServiceException
from soco.music_services.accounts import Account
from soco.music_services.music_service import (
    MusicService,
    MusicServiceSoapClient,
    desc_from_uri,
)


# Typical account data from http://{Sonos-ip}:1400/status/accounts
ACCOUNT_DATA = """<?xml version="1.0" ?>
<ZPSupportInfo type="User">
    <Accounts
    LastUpdateDevice="RINCON_000XXXXXXXX400" Version="8" NextSerialNum="5">
    <Account Type="2311" SerialNum="1">
        <UN>12345678</UN>
        <MD>1</MD>
        <NN>mysonos</NN>
        <OADevID>12345</OADevID>
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
SERVICES_DESCRIPTOR_LIST = (
    """<?xml version="1.0"?>
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
            <Strings Version="11" Uri="http://"""
    """soundcloud-static.ws.sonos.com/strings.xml"/>
            <PresentationMap Version="11" Uri="http://"""
    """soundcloud-static.ws.sonos.com/pmap.xml"/>
        </Presentation>
    </Service>
</Services>
"""
)


@pytest.fixture(autouse=True)
def patch_music_services(monkeypatch):
    """Patch MusicService, Account and SoapMessage to avoid network requests
    and use dummy data."""
    monkeypatch.setattr(
        MusicService,
        "_get_music_services_data_xml",
        mock.Mock(return_value=SERVICES_DESCRIPTOR_LIST),
    )
    monkeypatch.setattr(soco.soap, "SoapMessage", mock.Mock())
    monkeypatch.setattr(
        soco.music_services.music_service, "MusicServiceSoapClient", mock.Mock()
    )
    monkeypatch.setattr(
        Account, "_get_account_xml", mock.Mock(return_value=ACCOUNT_DATA)
    )


def test_initialise_account():
    assert len(Account._all_accounts) == 0
    accounts = Account.get_accounts()
    assert len(accounts) == 4  # TuneIn account is added automatically
    assert accounts["0"].service_type == "65031"  # TuneIn
    assert accounts["1"].username == "12345678"
    assert accounts["1"].service_type == "2311"
    assert accounts["1"].deleted is False
    assert accounts["1"].nickname == "mysonos"
    assert accounts.get("4") is None


def test_get_all_accounts():
    a = Account.get_accounts()
    assert len(a) == 4  # Including TuneIn


def test_get_accounts_for_service():
    a = Account.get_accounts_for_service("2311")
    assert len(a) == 1
    assert a[0].username == "12345678"


def test_initialise_services():
    assert MusicService._music_services_data is None
    data = MusicService._get_music_services_data()
    assert len(data) == 6
    deezer = data["519"]
    assert deezer["Name"] == "Deezer"
    assert deezer["Capabilities"] == "563"
    assert deezer["Auth"] == "UserId"
    assert deezer["Version"] == "1.1"
    assert deezer["ContainerType"] == "MService"
    assert deezer["Id"] == "2"
    assert (
        deezer["PresentationMapUri"]
        == "http://sonos-pmap.ws.sonos.com/deezer_pmap.4.xml"
    )
    assert deezer["ServiceType"] == "519"


def test_get_data_for_name():
    s = MusicService.get_data_for_name("Spotify")
    assert s["Name"] == "Spotify"
    assert s["Capabilities"] == "2563"


def test_get_names():
    names = MusicService.get_all_music_services_names()
    assert len(names) == 6
    assert "Spotify" in names
    assert "Deezer" in names


def test_get_subscribed_names():
    names = MusicService.get_subscribed_services_names()
    assert len(names) == 4
    assert set(names) == {"TuneIn", "Spotify", "Spreaker", "radioPup"}


def test_create_music_service():
    ms = MusicService("Spotify")
    assert ms.account.username == "12345678"
    with pytest.raises(MusicServiceException) as excinfo:
        unknown = MusicService("Unknown Music Service")
    assert "Unknown music service" in str(excinfo.value)
    with pytest.raises(MusicServiceException) as excinfo:
        soundcloud = MusicService("SoundCloud")
    assert "No account found" in str(excinfo.value)


def test_tunein():
    """TuneIn is handles specially by MusicServices."""
    tunein = MusicService("TuneIn")
    assert tunein
    assert tunein.service_id == "254"
    assert tunein.service_type == "65031"
    assert tunein.account.serial_number == "0"


def test_search():
    spotify = MusicService("Spotify")
    # Set up dummy search categories
    spotify._get_search_prefix_map = lambda: {
        "stations": "search:station",
        "shows": "search:show",
        "hosts": "search:host",
    }
    categories = spotify.available_search_categories
    assert len(categories) == 3
    assert set(categories) == {"stations", "shows", "hosts"}
    with pytest.raises(MusicServiceException) as excinfo:
        spotify.search("badcategory")
    assert "support the 'badcategory' search category" in str(excinfo.value)


def test_sonos_uri_from_id():
    spotify = MusicService("Spotify")
    track = "spotify:track:2qs5ZcLByNTctJKbhAZ9JE"
    assert (
        spotify.sonos_uri_from_id(track)
        == "soco://spotify%3Atrack%3A2qs5ZcLByNTctJKbhAZ9JE?sid=9&sn=1"
    )
    # Check for escaping with a few difficult characters
    track = "spotify: track\2qc%ünicøde?"
    assert (
        spotify.sonos_uri_from_id(track)
        == "soco://spotify%3A%20track%02qc%25%C3%BCnic%C3%B8de%3F?sid=9&sn=1"
    )
    # and a different service
    spreaker = MusicService("Spreaker")
    track = "spreaker12345678"
    assert spreaker.sonos_uri_from_id(track) == "soco://spreaker12345678?sid=163&sn=3"


def test_desc():
    spotify = MusicService("Spotify")
    assert spotify.desc == "SA_RINCON2311_12345678"
    spreaker = MusicService("Spreaker")
    assert spreaker.desc == "SA_RINCON41735_"


def test_desc_from_uri():
    URI = "x-sonos-http:track%3a3402413.mp3?sid=2&amp;flags=32&amp;sn=1"
    assert desc_from_uri(URI) == "SA_RINCON2311_12345678"
    SID_ONLY = "x-sonos-http:track%3a3402413.mp3?sid=9&amp;flags=32"
    assert desc_from_uri(SID_ONLY) == "SA_RINCON2311_12345678"
    TUNEIN_URI = "x-sonosapi-stream:s49815?sid=254&amp;flags=8224&amp;sn=0"
    assert desc_from_uri(TUNEIN_URI) == "SA_RINCON65031_"
    UNKNOWN_AC_WITH_SID = (
        "x-sonos-http:track%3a3402413.mp3?sid=9&amp;flags=32&amp;sn=400"
    )
    assert desc_from_uri(UNKNOWN_AC_WITH_SID) == "SA_RINCON2311_12345678"
    NO_DATA = "x-sonos-http:track%3a3402413.mp3?flags=32"
    assert desc_from_uri(NO_DATA) == "RINCON_AssociatedZPUDN"
    HTTP = "http://archive.org/download/TenD/TenD2005-07-16t10Wonderboy_64kb.mp3"
    assert desc_from_uri(HTTP) == "RINCON_AssociatedZPUDN"
