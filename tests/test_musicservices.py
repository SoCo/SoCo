"""Tests for the music_service module."""

from unittest import mock
import pytest

import soco.music_services.music_service
import soco.soap
from soco.exceptions import MusicServiceAuthException, MusicServiceException
from soco.music_services.accounts import Account
from soco.music_services.music_service import MusicService, MusicServiceSoapClient

# Typical account data from http://{Sonos-ip}:1400/status/accounts
from soco.music_services.token_store import JsonFileTokenStore

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


def test_create_music_service():
    # Normal instantiation, default token store
    ms = MusicService("Spotify")
    assert ms.service_name == "Spotify"
    assert isinstance(ms.token_store, JsonFileTokenStore)
    # Custom token store
    obj = object()
    ms = MusicService("Spotify", token_store=obj)
    assert ms.token_store is obj


def test_tunein():
    """TuneIn is handles specially by MusicServices."""
    tunein = MusicService("TuneIn")
    assert tunein
    assert tunein.service_id == "254"
    assert tunein.service_type == "65031"


PMAP_WITH_VARIANTS = """<?xml version="1.0" ?>
<Presentation>
  <PresentationMap type="Search">
    <Match>
      <SearchCategories stringId="SearchTitle">
        <Category id="artists" mappedId="artist"/>
        <Category id="albums" mappedId="album"/>
      </SearchCategories>
      <SearchCategories stringId="LibrarySearchTitle">
        <Category id="artists" mappedId="libraryartist"/>
        <Category id="albums" mappedId="libraryalbum"/>
      </SearchCategories>
    </Match>
  </PresentationMap>
</Presentation>
"""

MANIFEST_WITH_PMAP = (
    """{"presentationMap": {"uri": "https://cf.ws.sonos.com/p/p/mock"}}"""
)


def _apple_music_service(monkeypatch):
    """Build a MusicService backed by Apple-style manifest+pmap data."""
    # The class-level services cache may have been populated by other tests
    MusicService._music_services_data = None
    monkeypatch.setattr(
        MusicService,
        "_get_music_services_data",
        classmethod(
            lambda cls: {
                "52231": {
                    "Name": "Apple Music",
                    "Id": "204",
                    "ServiceType": "52231",
                    "Uri": "https://apple.invalid/smapi",
                    "SecureUri": "https://apple.invalid/smapi",
                    "Capabilities": "0",
                    "Version": "1.1",
                    "ContainerType": "MService",
                    "Auth": "AppLink",
                    "PresentationMapUri": None,
                    "ManifestUri": "https://cf.ws.sonos.com/p/m/mock",
                }
            }
        ),
    )

    def fake_get(url, timeout=9):
        if url == "https://cf.ws.sonos.com/p/m/mock":
            return mock.Mock(content=MANIFEST_WITH_PMAP.encode("utf-8"))
        if url == "https://cf.ws.sonos.com/p/p/mock":
            return mock.Mock(content=PMAP_WITH_VARIANTS.encode("utf-8"))
        raise AssertionError("unexpected request to {}".format(url))

    monkeypatch.setattr(soco.music_services.music_service.requests, "get", fake_get)
    return MusicService("Apple Music")


def test_search_variants_keep_every_pmap_block(monkeypatch):
    apple = _apple_music_service(monkeypatch)

    variants = apple._get_search_variants()

    assert variants == {
        "artists": [
            ("SearchTitle", "artist"),
            ("LibrarySearchTitle", "libraryartist"),
        ],
        "albums": [
            ("SearchTitle", "album"),
            ("LibrarySearchTitle", "libraryalbum"),
        ],
    }
    assert apple.available_search_variants == {
        "artists": ["SearchTitle", "LibrarySearchTitle"],
        "albums": ["SearchTitle", "LibrarySearchTitle"],
    }
    # The default prefix map uses the first (catalog) variant, not the last
    assert apple._get_search_prefix_map() == {
        "artists": "artist",
        "albums": "album",
    }


def test_search_combines_all_variants(monkeypatch):
    apple = _apple_music_service(monkeypatch)

    def fake_call(method, parameters=None):
        parameters = parameters or []
        search_id = dict(parameters)["id"]
        item_id = "artist:1" if search_id == "artist" else "artist:9"
        return {
            "searchResult": {
                "count": 1,
                "mediaCollection": [
                    {"id": item_id, "itemType": "artist", "title": "Artist"}
                ],
            }
        }

    apple.soap_client.call = fake_call

    result = apple.search("artists", "miles", variant="all")

    assert len(result) == 2
    assert result[0].item_id.endswith("artist%3A1")
    assert result[1].item_id.endswith("artist%3A9")
    assert result.number_returned == 2


def test_search_defaults_to_first_variant(monkeypatch):
    apple = _apple_music_service(monkeypatch)

    def fake_call(method, parameters=None):
        search_id = dict(parameters or [])["id"]
        # The default search must use the first (catalog) variant only
        assert search_id == "artist"
        return {
            "searchResult": {
                "count": 1,
                "mediaCollection": [
                    {"id": "artist:1", "itemType": "artist", "title": "Artist"}
                ],
            }
        }

    apple.soap_client.call = fake_call

    result = apple.search("artists", "miles")

    assert len(result) == 1
    assert result[0].item_id.endswith("artist%3A1")


def test_search_single_variant(monkeypatch):
    apple = _apple_music_service(monkeypatch)

    def fake_call(method, parameters=None):
        search_id = dict(parameters or [])["id"]
        assert search_id == "libraryartist"
        return {
            "searchResult": {
                "count": 1,
                "mediaCollection": [
                    {"id": "artist:9", "itemType": "artist", "title": "Artist"}
                ],
            }
        }

    apple.soap_client.call = fake_call

    result = apple.search("artists", "miles", variant="LibrarySearchTitle")

    assert len(result) == 1
    assert result[0].item_id.endswith("artist%3A9")


def test_get_metadata_with_sort(monkeypatch):
    apple = _apple_music_service(monkeypatch)

    def fake_call(method, parameters=None):
        assert method == "getMetadata"
        params = dict(parameters or [])
        assert params["sortOrder"] == "Artist"
        assert params["sortAscending"] == 0
        return {
            "getMetadataResult": {
                "count": 1,
                "mediaCollection": [
                    {"id": "album:1", "itemType": "album", "title": "Album"}
                ],
            }
        }

    apple.soap_client.call = fake_call

    result = apple.get_metadata("root", sort_order="Artist", sort_ascending=False)

    assert len(result) == 1


def test_get_metadata_omits_sort_when_unset(monkeypatch):
    apple = _apple_music_service(monkeypatch)

    def fake_call(method, parameters=None):
        params = dict(parameters or [])
        assert "sortOrder" not in params
        assert "sortAscending" not in params
        return {"getMetadataResult": {"count": 0, "mediaCollection": []}}

    apple.soap_client.call = fake_call

    result = apple.get_metadata("root")

    assert len(result) == 0


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


def test_call_with_none_faultcode_raises_clean_error(monkeypatch):
    """A provider returning a fault with no code at all (eg Atmosphere)
    must raise a MusicServiceException, not crash on the faultcode check."""
    client = MusicServiceSoapClient.__new__(MusicServiceSoapClient)
    client.endpoint = "https://invalid/smapi"
    client.timeout = 1
    client.http_headers = {}
    client.namespace = "http://www.sonos.com/Services/1.1"
    client.get_soap_header = mock.Mock(return_value="<credentials/>")
    client.music_service = mock.Mock(service_name="Atmosphere by Kollekt.fm")
    client.token_store = mock.Mock()

    message = mock.Mock()
    message.call.side_effect = soco.soap.SoapFault(None, None, None)
    monkeypatch.setattr(
        soco.music_services.music_service,
        "SoapMessage",
        mock.Mock(return_value=message),
    )

    with pytest.raises(MusicServiceException):
        client.call("getMetadata")


def _soap_client_for(name):
    """A bare MusicServiceSoapClient with only the attributes call() needs."""
    client = MusicServiceSoapClient.__new__(MusicServiceSoapClient)
    client.endpoint = "https://invalid/smapi"
    client.timeout = 1
    client.http_headers = {}
    client.namespace = "http://www.sonos.com/Services/1.1"
    client.get_soap_header = mock.Mock(return_value="<credentials/>")
    client.music_service = mock.Mock(
        service_name=name, service_id=0, auth_type="DeviceLink"
    )
    client.token_store = mock.Mock()
    client._device = mock.Mock(household_id="household")
    return client


def test_call_wraps_http_errors_as_provider_errors(monkeypatch):
    """HTTP 4xx/5xx from a provider (eg YouTube Music 403, Spectre 401) must
    surface as a MusicServiceException, not a raw HTTPError."""
    import requests

    client = _soap_client_for("YouTube Music")
    message = mock.Mock()
    message.call.side_effect = requests.exceptions.HTTPError(
        "403 Client Error: Forbidden"
    )
    monkeypatch.setattr(
        soco.music_services.music_service,
        "SoapMessage",
        mock.Mock(return_value=message),
    )

    with pytest.raises(MusicServiceException) as excinfo:
        client.call("getMetadata")
    assert "403" in str(excinfo.value)


def test_call_refresh_failure_raises_auth_error(monkeypatch):
    """When the token-refresh re-call itself faults (eg Pandora's token can
    only be fixed by re-linking in the Sonos app), surface a clean auth
    error instead of a raw SoapFault escaping call()."""
    from soco.xml import XML

    client = _soap_client_for("Pandora")
    detail = XML.Element("detail")
    auth_token = XML.SubElement(detail, "{%s}authToken" % client.namespace)
    auth_token.text = "new-token"
    private_key = XML.SubElement(detail, "{%s}privateKey" % client.namespace)
    private_key.text = "new-key"
    refresh_fault = soco.soap.SoapFault(
        "Client.TokenRefreshRequired", "TokenRefreshRequired", detail
    )

    message = mock.Mock()
    message.call.side_effect = [refresh_fault, refresh_fault]
    monkeypatch.setattr(
        soco.music_services.music_service,
        "SoapMessage",
        mock.Mock(return_value=message),
    )

    with pytest.raises(MusicServiceAuthException) as excinfo:
        client.call("search", [("id", "artists"), ("term", "a")])
    assert "Token refresh for Pandora failed" in str(excinfo.value)
    # The token pair from the first fault should have been saved
    client.token_store.save_token_pair.assert_called_once()


def test_sonos_uri_from_id():
    spotify = MusicService("Spotify")
    track = "spotify:track:2qs5ZcLByNTctJKbhAZ9JE"
    assert (
        spotify.sonos_uri_from_id(track)
        == "soco://spotify%3Atrack%3A2qs5ZcLByNTctJKbhAZ9JE?sid=9&sn=0"
    )
    # Check for escaping with a few difficult characters
    track = "spotify: track\2qc%ünicøde?"
    assert (
        spotify.sonos_uri_from_id(track)
        == "soco://spotify%3A%20track%02qc%25%C3%BCnic%C3%B8de%3F?sid=9&sn=0"
    )
    # and a different service
    spreaker = MusicService("Spreaker")
    track = "spreaker12345678"
    assert spreaker.sonos_uri_from_id(track) == "soco://spreaker12345678?sid=163&sn=0"


def test_desc():
    spotify = MusicService("Spotify")
    assert spotify.desc == "SA_RINCON2311_X_#Svc2311-0-Token"
    spreaker = MusicService("Spreaker")
    assert spreaker.desc == "SA_RINCON41735_"


def test_begin_authentication_is_deprecated():
    spotify = MusicService("Spotify")
    spotify.soap_client.begin_authentication = mock.Mock(
        return_value=("https://reg.example/", "CODE", "dev")
    )

    with pytest.warns(
        UserWarning, match="deprecated.*MusicServiceAccountManager"
    ):
        reg_url = spotify.begin_authentication()

    assert reg_url == "https://reg.example/"


def test_complete_authentication_is_deprecated():
    spotify = MusicService("Spotify")
    spotify.soap_client.complete_authentication = mock.Mock()

    with pytest.warns(
        UserWarning, match="deprecated.*MusicServiceAccountManager"
    ):
        spotify.complete_authentication("CODE")

    spotify.soap_client.complete_authentication.assert_called_once_with(
        "CODE", spotify.link_device_id
    )


# def test_desc_from_uri():
#     URI = "x-sonos-http:track%3a3402413.mp3?sid=2&amp;flags=32&amp;sn=1"
#     assert desc_from_uri(URI) == "SA_RINCON2311_12345678"
#     SID_ONLY = "x-sonos-http:track%3a3402413.mp3?sid=9&amp;flags=32"
#     assert desc_from_uri(SID_ONLY) == "SA_RINCON2311_12345678"
#     TUNEIN_URI = "x-sonosapi-stream:s49815?sid=254&amp;flags=8224&amp;sn=0"
#     assert desc_from_uri(TUNEIN_URI) == "SA_RINCON65031_"
#     UNKNOWN_AC_WITH_SID = (
#         "x-sonos-http:track%3a3402413.mp3?sid=9&amp;flags=32&amp;sn=400"
#     )
#     assert desc_from_uri(UNKNOWN_AC_WITH_SID) == "SA_RINCON2311_12345678"
#     NO_DATA = "x-sonos-http:track%3a3402413.mp3?flags=32"
#     assert desc_from_uri(NO_DATA) == "RINCON_AssociatedZPUDN"
#     HTTP = "http://archive.org/download/TenD/TenD2005-07-16t10Wonderboy_64kb.mp3"
#     assert desc_from_uri(HTTP) == "RINCON_AssociatedZPUDN"
