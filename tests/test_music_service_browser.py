"""Tests for read-only configured music-service browsing."""

import base64
import builtins
import hashlib
import json
from types import SimpleNamespace

import pytest

from soco.exceptions import MusicServiceAuthException, MusicServiceException
from soco.music_services import browser
from soco.music_services.browser import (
    ConfiguredMusicServiceAccount,
    MusicServiceBrowseItem,
    MusicServiceBrowser,
)
from soco.xml import XML

ACCOUNT_XML = b"""\
<MediaServers>
  <Service
    UDN="SA_RINCON52231_X_#Svc204-00abcdef-Token"
    SerialNum0="3"
    Username0="user@example.com"
    Password0=""
    Token0="token-value"
    Key0="key-value"
    Nickname0="Personal"
    Tier0="paid" />
</MediaServers>
"""

SMAPI_METADATA = b"""\
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <getMetadataResponse xmlns="http://www.sonos.com/Services/1.1">
      <getMetadataResult>
        <index>0</index><count>2</count><total>2</total>
        <mediaCollection>
          <id>library</id><itemType>container</itemType><title>Library</title>
          <canEnumerate>true</canEnumerate>
          <albumArtURI>https://img/${width}/${height}</albumArtURI>
        </mediaCollection>
        <mediaCollection>
          <id>upsell-banner/foo</id><itemType>container</itemType><title>Upgrade</title>
          <canPlay>true</canPlay>
        </mediaCollection>
      </getMetadataResult>
    </getMetadataResponse>
  </s:Body>
</s:Envelope>
"""

SEARCH_RESPONSE = b"""\
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <searchResponse xmlns="http://www.sonos.com/Services/1.1">
      <searchResult>
        <count>1</count><total>1</total>
        <mediaMetadata>
          <id>track:1</id><itemType>track</itemType><title>Result</title>
          <trackMetadata><artist>Artist</artist></trackMetadata>
        </mediaMetadata>
      </searchResult>
    </searchResponse>
  </s:Body>
</s:Envelope>
"""

MEDIA_METADATA = b"""\
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <getMediaMetadataResponse xmlns="http://www.sonos.com/Services/1.1">
      <getMediaMetadataResult>
        <id>track:1</id><itemType>track</itemType><title>Result</title>
        <trackMetadata><albumArtURI>https://img/cover.jpg</albumArtURI></trackMetadata>
      </getMediaMetadataResult>
    </getMediaMetadataResponse>
  </s:Body>
</s:Envelope>
"""


class FakeResponse:
    """Small requests.Response stand-in used by transport tests."""

    def __init__(self, status_code=200, content=b"", json_value=None):
        self.status_code = status_code
        self.content = content
        self._json_value = json_value

    def json(self):
        if isinstance(self._json_value, Exception):
            raise self._json_value
        if self._json_value is None:
            return json.loads(self.content.decode("utf-8"))
        return self._json_value

    def raise_for_status(self):
        if self.status_code >= 400:
            response = SimpleNamespace(status_code=self.status_code)
            error = browser.requests.HTTPError("HTTP {}".format(self.status_code))
            error.response = response
            raise error


class FakeSession:
    """Record HTTP calls and return queued responses."""

    def __init__(self, get_responses=None, post_responses=None):
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.get_calls = []
        self.post_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.get_responses.pop(0)

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.post_responses.pop(0)


class FakeService:
    """MusicService-compatible descriptor used without network discovery."""

    def __init__(
        self,
        name="Example",
        service_id="204",
        auth_type="AppLink",
        capabilities="0",
        manifest_uri=None,
        presentation_map_uri=None,
        strings_uri=None,
        search_variants=None,
    ):
        self.service_name = name
        self.service_id = service_id
        self.service_type = "MusicService"
        self.auth_type = auth_type
        self.capabilities = capabilities
        self.version = "1.0"
        self.container_type = "MusicService"
        self.uri = "http://example.invalid/smapi"
        self.secure_uri = "https://example.invalid/smapi"
        self.presentation_map_uri = presentation_map_uri
        self.strings_uri = strings_uri
        self.manifest_uri = manifest_uri
        if search_variants is None:
            search_variants = {"tracks": [("default", "search:track")]}
        self.search_variants = search_variants

    def _get_search_variants(self):
        return self.search_variants

    def _get_search_prefix_map(self):
        return {
            category: entries[0][1]
            for category, entries in self.search_variants.items()
        }

    @property
    def available_search_categories(self):
        return list(self.search_variants)

    @property
    def available_search_variants(self):
        return {
            category: [entry[0] for entry in entries]
            for category, entries in self.search_variants.items()
        }


class FakeSystemProperties:
    def GetString(self, args):  # pylint: disable=invalid-name
        assert args == [("VariableName", "R_TrialZPSerial")]
        return {"StringValue": "player-device-id"}


class FakeDevice:
    """The small SoCo surface the browser needs."""

    household_id = "Sonos_household"
    uid = "RINCON_000000000001400"
    systemProperties = FakeSystemProperties()


class FakeSubscription:
    def __init__(self, event):
        import queue

        self.events = queue.Queue()
        self.events.put(event)
        self.unsubscribed = False

    def unsubscribe(self):
        self.unsubscribed = True


class FakeZoneGroupTopology:
    def __init__(self, event):
        self.subscription = FakeSubscription(event)
        self.requested_timeout = None

    def subscribe(self, requested_timeout=None):
        self.requested_timeout = requested_timeout
        return self.subscription


def make_account():
    return ConfiguredMusicServiceAccount(
        204,
        3,
        "SA_RINCON52231_X_#Svc204-00abcdef-Token",
        token="token-value",
        key="key-value",
        nickname="Personal",
    )


def test_parse_configured_accounts():
    accounts = ConfiguredMusicServiceAccount.from_payload(ACCOUNT_XML)

    assert len(accounts) == 1
    account = accounts[0]
    assert account.service_id == 204
    assert account.schema_revision == 7
    assert account.serial_number == 3
    assert account.nickname == "Personal"
    assert account.token == "token-value"
    assert account.key == "key-value"
    assert account.account_uid == 0x00ABCDEF
    assert "token-value" not in repr(account)


def test_capture_accounts_reuses_zone_group_topology_subscription(monkeypatch):
    event = SimpleNamespace(variables={"third_party_media_servers_x": "2:encoded"})
    device = FakeDevice()
    device.zoneGroupTopology = FakeZoneGroupTopology(event)
    monkeypatch.setattr(
        browser.credentials,
        "_decrypt_account_payload",
        lambda value, household: ACCOUNT_XML,
    )

    accounts = ConfiguredMusicServiceAccount.get_accounts(device, timeout=4)

    assert len(accounts) == 1
    assert device.zoneGroupTopology.requested_timeout == 15
    assert device.zoneGroupTopology.subscription.unsubscribed is True


def test_account_payload_key_derivation_and_integrity(monkeypatch):
    household = "Sonos_household"
    iv = b"0" * 16
    ciphertext = b"1" * 16
    payload = b"<MediaServers />"
    checked = payload + hashlib.md5(payload).digest()[:4]
    raw = iv + ciphertext
    encoded = "2:" + base64.b64encode(raw).decode("ascii")
    observed = {}

    def fake_decrypt(received_ciphertext, key, received_iv):
        observed["ciphertext"] = received_ciphertext
        observed["key"] = key
        observed["iv"] = received_iv
        return checked

    monkeypatch.setattr(browser.credentials, "_aes_128_cbc_decrypt", fake_decrypt)

    assert browser._decrypt_account_payload(encoded, household) == payload
    global_key = hashlib.md5(household.encode("utf-8") + browser._ACCOUNT_SALT).digest()
    assert observed == {
        "ciphertext": ciphertext,
        "key": hashlib.md5(iv + global_key).digest(),
        "iv": iv,
    }


def test_account_payload_rejects_bad_integrity(monkeypatch):
    encoded = "2:" + base64.b64encode(b"0" * 32).decode("ascii")
    monkeypatch.setattr(
        browser.credentials, "_aes_128_cbc_decrypt", lambda *_args: b"payloadbad!"
    )

    with pytest.raises(MusicServiceException, match="integrity"):
        browser._decrypt_account_payload(encoded, "Sonos_household")


def _block_cryptography_import(monkeypatch):
    """Force the credential helpers down their OpenSSL fallback path."""
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "cryptography" or name.startswith("cryptography."):
            raise ImportError("cryptography disabled by test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)


def test_aes_cryptography_backend_round_trip(monkeypatch):
    """The optional Python backend can encrypt and decrypt account values."""
    pytest.importorskip("cryptography")

    def unexpected_openssl(_name):
        raise AssertionError("OpenSSL fallback used with cryptography installed")

    monkeypatch.setattr(browser.credentials.shutil, "which", unexpected_openssl)
    key = bytes(range(16))
    iv = bytes(range(16, 32))
    plaintext = b"configured account value"

    ciphertext = browser.credentials._aes_128_cbc_encrypt(plaintext, key, iv)

    assert ciphertext != plaintext
    assert browser.credentials._aes_128_cbc_decrypt(ciphertext, key, iv) == plaintext


def test_aes_openssl_fallback_round_trip(monkeypatch):
    """OpenSSL remains a working fallback when cryptography is unavailable."""
    if not browser.credentials.shutil.which("openssl"):
        pytest.skip("OpenSSL executable is not available")
    _block_cryptography_import(monkeypatch)
    key = bytes(range(16))
    iv = bytes(range(16, 32))
    plaintext = b"configured account value"

    ciphertext = browser.credentials._aes_128_cbc_encrypt(plaintext, key, iv)

    assert ciphertext != plaintext
    assert browser.credentials._aes_128_cbc_decrypt(ciphertext, key, iv) == plaintext


def test_aes_backend_error_without_cryptography_or_openssl(monkeypatch):
    """A useful error is raised when neither supported backend is available."""
    _block_cryptography_import(monkeypatch)
    monkeypatch.setattr(browser.credentials.shutil, "which", lambda _name: None)

    with pytest.raises(MusicServiceException, match="cryptography.*OpenSSL"):
        browser.credentials._aes_128_cbc_decrypt(b"0" * 16, b"1" * 16, b"2" * 16)


def test_smapi_get_metadata_preserves_provider_quirks_and_artwork():
    session = FakeSession(post_responses=[FakeResponse(content=SMAPI_METADATA)])
    client = browser._ConfiguredSmapiClient(
        FakeService(capabilities=str(1 << 16)),
        make_account(),
        FakeDevice(),
        FakeDevice.household_id,
        "player-device-id",
        "controller-id",
        "America/Los_Angeles",
        session=session,
    )

    page = client.get_metadata()

    assert page["total"] == 2
    assert page["items"][0]["kind"] == "mediaCollection"
    assert page["items"][0]["album_art_uri"] == "https://img/400/400"
    assert page["items"][1]["kind"] == "mediaMetadata"
    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    assert browser._children(envelope, "timeZone")[0].text == "America/Los_Angeles"


def test_capability_eight_moves_token_to_bearer_header():
    session = FakeSession(post_responses=[FakeResponse(content=SMAPI_METADATA)])
    client = browser._ConfiguredSmapiClient(
        FakeService(capabilities="8"),
        make_account(),
        FakeDevice(),
        FakeDevice.household_id,
        "player-device-id",
        "controller-id",
        "UTC",
        session=session,
    )

    client.get_metadata()

    _url, request = session.post_calls[0]
    assert request["headers"]["Authorization"] == "Bearer token-value"
    envelope = XML.fromstring(request["data"])
    assert not browser._children(envelope, "token")
    assert browser._children(envelope, "householdId")[0].text == FakeDevice.household_id


def test_get_metadata_retries_transient_provider_fault():
    fault = b"""\
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
      <s:Body><s:Fault><faultcode>Server</faultcode><faultstring>Temporary</faultstring>
        <detail><SonosError>999</SonosError></detail></s:Fault></s:Body>
    </s:Envelope>
    """
    session = FakeSession(
        post_responses=[FakeResponse(500, fault), FakeResponse(content=SMAPI_METADATA)]
    )
    client = browser._ConfiguredSmapiClient(
        FakeService(),
        make_account(),
        FakeDevice(),
        FakeDevice.household_id,
        "player-device-id",
        "controller-id",
        "UTC",
        session=session,
    )

    assert client.get_metadata()["count"] == 2
    assert len(session.post_calls) == 2


def test_expired_token_does_not_refresh_unless_enabled():
    fault = b"""\
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
      <s:Body><s:Fault><faultcode>Client.AuthTokenExpired</faultcode>
        <faultstring>Token Expired</faultstring><detail /></s:Fault></s:Body>
    </s:Envelope>
    """
    session = FakeSession(post_responses=[FakeResponse(500, fault)])
    client = browser._ConfiguredSmapiClient(
        FakeService(),
        make_account(),
        FakeDevice(),
        FakeDevice.household_id,
        "player-device-id",
        "controller-id",
        "UTC",
        allow_credential_refresh=False,
        session=session,
    )

    with pytest.raises(MusicServiceAuthException, match="AuthTokenExpired"):
        client.get_metadata()


def test_manifest_root_returns_sections_and_embedded_items(monkeypatch):
    manifest = {
        "endpoints": [{"type": "browse", "uri": "https://content.invalid/browse/v1"}]
    }
    page = {
        "views": [
            {
                "id": {"objectId": "library"},
                "displayType": "grid",
                "content": {"container": {"name": "Library"}},
                "total": 1,
                "items": [
                    {
                        "id": {"objectId": "album:1"},
                        "content": {
                            "container": {
                                "name": "Album",
                                "type": "album",
                                "canEnumerate": True,
                                "imageUrl": "https://img/${width}/${height}/${ratio}",
                            }
                        },
                    }
                ],
            }
        ]
    }
    session = FakeSession(
        get_responses=[FakeResponse(json_value=manifest), FakeResponse(json_value=page)]
    )
    service = FakeService(manifest_uri="https://content.invalid/manifest.json")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)

    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )
    root = music_browser.get_metadata()
    library = root.items[0]
    embedded = music_browser.get_metadata(library)

    assert music_browser.root_transport == "content"
    assert root.transport == "content"
    assert library.source_transport == "content-section"
    assert embedded.items[0].item_id == "album:1"
    assert embedded.items[0].album_art_uri == "https://img/400/400/1x1"
    _url, request = session.get_calls[1]
    assert request["headers"]["X-Sonos-Device-Id"] == "Sonos_household_00abcdef"
    assert request["headers"]["Authorization"] == "Bearer token-value"


def test_content_child_switches_to_smapi_with_account_scoped_household(monkeypatch):
    manifest = {
        "endpoints": [{"type": "browse", "uri": "https://content.invalid/browse/v1"}]
    }
    session = FakeSession(
        get_responses=[FakeResponse(json_value=manifest)],
        post_responses=[FakeResponse(content=SMAPI_METADATA)],
    )
    service = FakeService(manifest_uri="https://content.invalid/manifest.json")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )
    content_item = MusicServiceBrowseItem(
        "library:albums", "Albums", "mediaCollection", source_transport="content"
    )

    child = music_browser.get_metadata(content_item)

    assert child.transport == "smapi"
    assert child.items[0].source_transport == "content"
    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    assert browser._children(envelope, "householdId")[0].text == (
        "Sonos_household_00abcdef"
    )


def test_manifest_without_browse_endpoint_falls_back_to_smapi(monkeypatch):
    session = FakeSession(
        get_responses=[FakeResponse(json_value={"endpoints": []})],
        post_responses=[FakeResponse(content=SMAPI_METADATA)],
    )
    service = FakeService(manifest_uri="https://content.invalid/manifest.json")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    result = music_browser.get_metadata()

    assert music_browser.root_transport == "smapi"
    assert result.transport == "smapi"
    assert len(session.post_calls) == 1


def test_search_uses_existing_music_service_category_map(monkeypatch):
    session = FakeSession(post_responses=[FakeResponse(content=SEARCH_RESPONSE)])
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    result = music_browser.search("tracks", "hello")

    assert result.items[0].item_id == "track:1"
    assert result.items[0].artist == "Artist"
    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    assert browser._children(envelope, "id")[0].text == "search:track"
    assert browser._children(envelope, "term")[0].text == "hello"
    # Search runs under the account's OAuth device identity, not the bare
    # household ID: Apple rejects SMAPI calls under the plain household
    # identity with InvalidTokenException.
    assert browser._children(envelope, "householdId")[0].text == (
        "Sonos_household_00abcdef"
    )


def test_search_combines_all_variants_and_labels_items(monkeypatch):
    catalog_response = SEARCH_RESPONSE.replace(b"track:1", b"track:1")
    library_response = SEARCH_RESPONSE.replace(b"track:1", b"track:9")
    session = FakeSession(
        post_responses=[
            FakeResponse(content=catalog_response),
            FakeResponse(content=library_response),
        ]
    )
    service = FakeService(
        search_variants={
            "tracks": [
                ("SearchTitle", "search:track"),
                ("LibrarySearchTitle", "librarytrack"),
            ]
        }
    )
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    result = music_browser.search("tracks", "hello")

    assert [item.item_id for item in result.items] == ["track:1", "track:9"]
    assert result.total == 2
    assert result.items[0].variant == "SearchTitle"
    assert result.items[1].variant == "LibrarySearchTitle"
    # Both variant searches run under the account-scoped identity
    assert len(session.post_calls) == 2
    for _url, request in session.post_calls:
        envelope = XML.fromstring(request["data"])
        assert browser._children(envelope, "householdId")[0].text == (
            "Sonos_household_00abcdef"
        )
    _url, first = session.post_calls[0]
    _url, second = session.post_calls[1]
    first_envelope = XML.fromstring(first["data"])
    second_envelope = XML.fromstring(second["data"])
    assert browser._children(first_envelope, "id")[0].text == "search:track"
    assert browser._children(second_envelope, "id")[0].text == "librarytrack"


def test_search_single_variant_only(monkeypatch):
    session = FakeSession(post_responses=[FakeResponse(content=SEARCH_RESPONSE)])
    service = FakeService(
        search_variants={
            "tracks": [
                ("SearchTitle", "search:track"),
                ("LibrarySearchTitle", "librarytrack"),
            ]
        }
    )
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    result = music_browser.search("tracks", "hello", variant="LibrarySearchTitle")

    assert result.items[0].item_id == "track:1"
    assert result.items[0].variant == "LibrarySearchTitle"
    assert len(session.post_calls) == 1
    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    assert browser._children(envelope, "id")[0].text == "librarytrack"


def test_search_unknown_variant_raises(monkeypatch):
    session = FakeSession()
    service = FakeService(search_variants={"tracks": [("SearchTitle", "search:track")]})
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    with pytest.raises(MusicServiceException, match="Unknown search variant"):
        music_browser.search("tracks", "hello", variant="nope")


def test_anonymous_browse_with_bare_udn_uses_shared_client(monkeypatch):
    # Anonymous services (eg myTuner Radio) have a bare ``SA_RINCON…_`` UDN
    # with no account UID; scoping must not crash on it.
    session = FakeSession(post_responses=[FakeResponse(content=SMAPI_METADATA)])
    service = FakeService(auth_type="Anonymous")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    account = ConfiguredMusicServiceAccount(204, 0, "SA_RINCON68615_")
    music_browser = MusicServiceBrowser(
        "Example", account=account, device=FakeDevice(), session=session
    )

    result = music_browser.get_metadata()
    assert result.transport == "smapi"
    assert len(result.items) == 2
    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    # No account-scoped householdId may be derived from a bare UDN.
    assert not browser._children(envelope, "householdId")


def test_anonymous_search_uses_shared_household_client(monkeypatch):
    session = FakeSession(post_responses=[FakeResponse(content=SEARCH_RESPONSE)])
    service = FakeService(auth_type="Anonymous")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    monkeypatch.setattr(
        ConfiguredMusicServiceAccount, "get_accounts", lambda *_args, **_kwargs: []
    )
    music_browser = MusicServiceBrowser("Example", device=FakeDevice(), session=session)

    result = music_browser.search("tracks", "hello")

    assert result.items[0].item_id == "track:1"
    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    # Anonymous services carry no token, so no account-scoped householdId is
    # sent; the search runs through the shared plain client.
    assert not browser._children(envelope, "householdId")


def test_get_media_metadata_is_read_only(monkeypatch):
    session = FakeSession(post_responses=[FakeResponse(content=MEDIA_METADATA)])
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    metadata = music_browser.get_media_metadata("track:1")

    assert metadata["id"] == "track:1"
    assert metadata["album_art_uri"] == "https://img/cover.jpg"
    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    assert browser._children(envelope, "getMediaMetadata")
    assert not browser._children(envelope, "AddAccountX")
    assert not browser._children(envelope, "AddOAuthAccountX")
    # SMAPI providers reject the plain household identity (InvalidToken);
    # get_media_metadata must use the account-scoped device identity.
    household = browser._children(envelope, "householdId")
    assert household and household[0].text == "Sonos_household_00abcdef"


def test_sonos_uri_from_id_encodes_account_serial(monkeypatch):
    service = FakeService(service_id="204")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=FakeSession()
    )

    uri = music_browser.sonos_uri_from_id("spotify:track:2qs5ZcLByNTctJKbhAZ9JE")

    assert (
        uri == "x-sonosapi-stream:spotify%3Atrack%3A2qs5ZcLByNTctJKbhAZ9JE?sid=204&sn=3"
    )


def test_sonos_uri_from_id_spotify_track_string_maps_to_spotify_resource(
    monkeypatch,
):
    # Review regression: ``sonos_uri_from_id(track.item_id)`` (a raw string)
    # for a Spotify track must produce the x-sonos-spotify resource, never
    # the x-sonosapi-stream radio scheme.
    service = FakeService(service_id="12")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    account = ConfiguredMusicServiceAccount(
        12,
        3,
        "SA_RINCON3079_X_#Svc3079-00abcdef-Token",
        token="token-value",
        key="key-value",
        nickname="Personal",
    )
    music_browser = MusicServiceBrowser(
        "Spotify", account=account, device=FakeDevice(), session=FakeSession()
    )

    uri = music_browser.sonos_uri_from_id("spotify:track:7azylXFRsebfrIoAtwfjaB")

    assert uri.startswith("x-sonos-spotify:spotify%3atrack%3a7azylXFRsebfrIoAtwfjaB?")
    assert "sid=12" in uri
    assert "flags=8224" in uri
    assert "sn=3" in uri


def test_get_extended_metadata_parses_related_items_and_text(monkeypatch):
    extended = b"""\
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
      <s:Body>
        <getExtendedMetadataResponse xmlns="http://www.sonos.com/Services/1.1">
          <getExtendedMetadataResult>
            <index>0</index><count>1</count><total>1</total>
            <mediaCollection>
              <id>related:1</id><itemType>container</itemType><title>Related</title>
              <mediaMetadata>
                <id>track:2</id><itemType>track</itemType><title>Another Track</title>
                <trackMetadata><artist>Artist</artist></trackMetadata>
              </mediaMetadata>
            </mediaCollection>
            <relatedText>
              <type>ARTIST_BIO</type>
              <text>Some biography text</text>
            </relatedText>
            <relatedPlay>
              <id>radio:ra.1</id><itemType>program</itemType>
              <title>Artist Radio</title><canPlay>true</canPlay>
            </relatedPlay>
          </getExtendedMetadataResult>
        </getExtendedMetadataResponse>
      </s:Body>
    </s:Envelope>
    """
    session = FakeSession(post_responses=[FakeResponse(content=extended)])
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    data = music_browser.get_extended_metadata("track:1")

    assert [item.title for item in data["items"]] == ["Another Track", "Artist Radio"]
    assert data["items"][0].item_id == "track:2"
    assert data["items"][1].item_id == "radio:ra.1"
    assert data["items"][1].kind == "mediaMetadata"
    assert data["text"] == [{"type": "ARTIST_BIO", "text": "Some biography text"}]
    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    assert browser._children(envelope, "getExtendedMetadata")
    assert browser._children(envelope, "id")[0].text == "track:1"


def test_get_last_update_returns_change_timestamps(monkeypatch):
    last_update = b"""\
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
      <s:Body>
        <getLastUpdateResponse xmlns="http://www.sonos.com/Services/1.1">
          <getLastUpdateResult>
            <catalog>2024-01-01T00:00:00</catalog>
            <favorites>2024-01-02T00:00:00</favorites>
          </getLastUpdateResult>
        </getLastUpdateResponse>
      </s:Body>
    </s:Envelope>
    """
    session = FakeSession(post_responses=[FakeResponse(content=last_update)])
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    data = music_browser.get_last_update()

    assert data == {
        "catalog": "2024-01-01T00:00:00",
        "favorites": "2024-01-02T00:00:00",
    }
    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    assert browser._children(envelope, "getLastUpdate")


def test_get_metadata_sends_sort_params(monkeypatch):
    session = FakeSession(post_responses=[FakeResponse(content=SMAPI_METADATA)])
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    music_browser.get_metadata("library", sort_order="Artist", sort_ascending=False)

    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    op = browser._children(envelope, "getMetadata")[0]
    fields = {browser._local_name(node.tag): node.text or "" for node in op}
    assert fields["sortOrder"] == "Artist"
    assert fields["sortAscending"] == "false"


def test_get_metadata_omits_sort_params_when_unset(monkeypatch):
    session = FakeSession(post_responses=[FakeResponse(content=SMAPI_METADATA)])
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    music_browser.get_metadata("library")

    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    op = browser._children(envelope, "getMetadata")[0]
    fields = {browser._local_name(node.tag): node.text or "" for node in op}
    assert "sortOrder" not in fields
    assert "sortAscending" not in fields


def test_available_search_variants_delegates_to_legacy(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=FakeSession()
    )

    assert music_browser.available_search_variants == {"tracks": ["default"]}


def test_browser_proxies_descriptor_attributes(monkeypatch):
    service = FakeService(service_id="204", auth_type="AppLink")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=FakeSession()
    )

    assert music_browser.service_id == "204"
    assert music_browser.service_name == "Example"
    assert music_browser.service_type == "MusicService"
    assert music_browser.auth_type == "AppLink"
    assert music_browser.capabilities == "0"
    assert music_browser.version == "1.0"
    assert music_browser.container_type == "MusicService"
    assert music_browser.uri == "http://example.invalid/smapi"
    assert music_browser.secure_uri == "https://example.invalid/smapi"
    assert music_browser.presentation_map_uri is None
    assert music_browser.manifest_uri is None


def test_device_link_without_token_uses_get_session_id():
    session_response = b"""\
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
      <s:Body>
        <getSessionIdResponse xmlns="http://www.sonos.com/Services/1.1">
          <getSessionIdResult>session-123</getSessionIdResult>
        </getSessionIdResponse>
      </s:Body>
    </s:Envelope>
    """
    account = ConfiguredMusicServiceAccount(
        204,
        3,
        "SA_RINCON52231_X_#Svc204-00abcdef-Token",
        username="user",
        password="password",
    )
    session = FakeSession(
        post_responses=[
            FakeResponse(content=session_response),
            FakeResponse(content=SMAPI_METADATA),
        ]
    )
    client = browser._ConfiguredSmapiClient(
        FakeService(auth_type="DeviceLink"),
        account,
        FakeDevice(),
        FakeDevice.household_id,
        "player-device-id",
        "controller-id",
        "UTC",
        session=session,
    )

    client.get_metadata()

    first = XML.fromstring(session.post_calls[0][1]["data"])
    second = XML.fromstring(session.post_calls[1][1]["data"])
    assert browser._children(first, "getSessionId")
    assert browser._children(second, "sessionId")[0].text == "session-123"


def test_user_id_password_credentials_stay_in_soap():
    account = ConfiguredMusicServiceAccount(
        204,
        3,
        "SA_RINCON52231_X_#Svc204-00abcdef-Token",
        username="user",
        password="password",
    )
    session = FakeSession(post_responses=[FakeResponse(content=SMAPI_METADATA)])
    client = browser._ConfiguredSmapiClient(
        FakeService(auth_type="UserIdPassword"),
        account,
        FakeDevice(),
        FakeDevice.household_id,
        "player-device-id",
        "controller-id",
        "UTC",
        session=session,
    )

    client.get_metadata()

    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    assert browser._children(envelope, "username")[0].text == "user"
    assert browser._children(envelope, "password")[0].text == "password"
    assert "Authorization" not in request["headers"]


def test_embedded_refresh_credentials_are_accepted_only_when_enabled():
    refresh_fault = b"""\
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
      <s:Body><s:Fault>
        <faultcode>Client.TokenRefreshRequired</faultcode>
        <faultstring>Token Expired</faultstring>
        <detail>
          <RefreshAuthTokenResult xmlns="http://www.sonos.com/Services/1.1">
            <authToken>replacement-token</authToken>
            <privateKey>replacement-key</privateKey>
          </RefreshAuthTokenResult>
        </detail>
      </s:Fault></s:Body>
    </s:Envelope>
    """
    account = make_account()
    session = FakeSession(
        post_responses=[
            FakeResponse(500, refresh_fault),
            FakeResponse(content=SMAPI_METADATA),
        ]
    )
    client = browser._ConfiguredSmapiClient(
        FakeService(),
        account,
        FakeDevice(),
        FakeDevice.household_id,
        "player-device-id",
        "controller-id",
        "UTC",
        allow_credential_refresh=True,
        session=session,
    )

    client.get_metadata()

    assert account.token == "replacement-token"
    assert account.key == "replacement-key"
    assert len(session.post_calls) == 2


def test_malformed_sonos_radio_xsi_prefix_is_repaired():
    malformed = SMAPI_METADATA.replace(
        b"<index>0</index>", b'<index xsi:nil="true">0</index>'
    )
    session = FakeSession(post_responses=[FakeResponse(content=malformed)])
    client = browser._ConfiguredSmapiClient(
        FakeService(),
        make_account(),
        FakeDevice(),
        FakeDevice.household_id,
        "player-device-id",
        "controller-id",
        "UTC",
        session=session,
    )

    assert client.get_metadata()["count"] == 2


def test_plain_text_unauthorized_is_an_auth_fault_not_malformed_xml():
    # Sonos Radio answers with the literal text ``Unauthorized`` (HTTP 200)
    # when the token it is given is unusable.
    session = FakeSession(post_responses=[FakeResponse(content=b"Unauthorized")])
    # Refresh is on by default now; this test is about error classification,
    # so opt out to keep it focused on the plain-text fault surfacing.
    client = browser._ConfiguredSmapiClient(
        FakeService(),
        make_account(),
        FakeDevice(),
        FakeDevice.household_id,
        "player-device-id",
        "controller-id",
        "UTC",
        allow_credential_refresh=False,
        session=session,
    )

    with pytest.raises(MusicServiceAuthException, match="Unauthorized"):
        client.get_metadata()


def test_multiple_configured_accounts_require_explicit_selection(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    first = make_account()
    second = make_account()
    second.serial_number = 4
    monkeypatch.setattr(
        ConfiguredMusicServiceAccount,
        "get_accounts",
        lambda *_args, **_kwargs: [first, second],
    )

    with pytest.raises(MusicServiceAuthException, match="Multiple Example accounts"):
        MusicServiceBrowser("Example", device=FakeDevice(), session=FakeSession())


def test_anonymous_service_uses_household_account_when_added(monkeypatch):
    # Anonymous services can be added to a household, which gives them a real
    # account (serial number + UDN) that playback URIs need.
    service = FakeService(auth_type="Anonymous")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    account = make_account()
    monkeypatch.setattr(
        ConfiguredMusicServiceAccount,
        "get_accounts",
        lambda *_args, **_kwargs: [account],
    )

    music_browser = MusicServiceBrowser(
        "Example", device=FakeDevice(), session=FakeSession()
    )

    assert music_browser.account is account


def test_anonymous_service_without_account_uses_synthetic(monkeypatch):
    service = FakeService(auth_type="Anonymous")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    monkeypatch.setattr(
        ConfiguredMusicServiceAccount, "get_accounts", lambda *_args, **_kwargs: []
    )

    music_browser = MusicServiceBrowser(
        "Example", device=FakeDevice(), session=FakeSession()
    )

    assert music_browser.account.serial_number == 0
    assert music_browser.account.token == ""


def test_content_http_401_does_not_refresh_when_disabled(monkeypatch):
    manifest = {
        "endpoints": [{"type": "browse", "uri": "https://content.invalid/browse/v1"}]
    }
    session = FakeSession(
        get_responses=[FakeResponse(json_value=manifest), FakeResponse(status_code=401)]
    )
    service = FakeService(manifest_uri="https://content.invalid/manifest.json")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example",
        account=make_account(),
        device=FakeDevice(),
        session=session,
        allow_credential_refresh=False,
    )

    with pytest.raises(MusicServiceAuthException, match="HTTP 401"):
        music_browser.get_metadata()

    assert len(session.get_calls) == 2


def test_content_http_401_refreshes_by_default(monkeypatch):
    manifest = {
        "endpoints": [{"type": "browse", "uri": "https://content.invalid/browse/v1"}]
    }
    refresh_response = b"""\
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
      <s:Body>
        <refreshAuthTokenResponse xmlns="http://www.sonos.com/Services/1.1">
          <refreshAuthTokenResult>
            <authToken>new-token</authToken><privateKey>new-key</privateKey>
          </refreshAuthTokenResult>
        </refreshAuthTokenResponse>
      </s:Body>
    </s:Envelope>
    """
    session = FakeSession(
        get_responses=[
            FakeResponse(json_value=manifest),
            FakeResponse(status_code=401),
            FakeResponse(json_value={"views": []}),
        ],
        post_responses=[FakeResponse(content=refresh_response)],
    )
    service = FakeService(manifest_uri="https://content.invalid/manifest.json")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    account = make_account()
    music_browser = MusicServiceBrowser(
        "Example", account=account, device=FakeDevice(), session=session
    )

    root = music_browser.get_metadata()

    assert root.transport == "content"
    assert account.token == "new-token"
    assert account.key == "new-key"
    # manifest + 401 + retried page
    assert len(session.get_calls) == 3
    assert len(session.post_calls) == 1
    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    assert browser._children(envelope, "refreshAuthToken")


def test_credential_refresh_is_enabled_by_default(monkeypatch):
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=FakeSession()
    )

    assert music_browser.allow_credential_refresh is True
    assert music_browser._client.allow_credential_refresh is True

    client = browser._ConfiguredSmapiClient(
        FakeService(),
        make_account(),
        FakeDevice(),
        FakeDevice.household_id,
        "player-device-id",
        "controller-id",
        "UTC",
        session=FakeSession(),
    )
    assert client.allow_credential_refresh is True


PMAP_XML = b"""\
<Presentation>
    <BrowseOptions PageSize="100"/>
    <PresentationMap type="ArtWorkSizeMap">
        <Match><imageSizeMap>
            <sizeEntry size="40" substitution="40x40"/>
            <sizeEntry size="200" substitution="200x200"/>
        </imageSizeMap></Match>
    </PresentationMap>
    <PresentationMap type="BrowseIconSizeMap">
        <Match><browseIconSizeMap>
            <sizeEntry size="40" substitution="-40.png"/>
            <sizeEntry size="0" substitution="-legacy.png"/>
        </browseIconSizeMap></Match>
    </PresentationMap>
    <PresentationMap type="DisplayType">
        <RootNodeDisplayType><DisplayMode>BRAND</DisplayMode></RootNodeDisplayType>
        <DisplayType id="AlbumView">
            <Lines>
                <Line token="title"/>
                <Line token="artist"/>
                <Line token="summary"/>
            </Lines>
        </DisplayType>
        <DisplayType id="GridView"><DisplayMode>GRID</DisplayMode></DisplayType>
        <DisplayType id="TitleWithArtist">
            <Lines><Line token="title"/><Line stringId="Artist_And_Album"/></Lines>
            <ItemThumbnails source="albumArtUri"/>
        </DisplayType>
    </PresentationMap>
    <PresentationMap type="InfoView">
        <Match><MenuItemOverrides>
            <MenuItem StringId="StartStation" MenuItem="RelatedPlay"
                      PromptStringId="StartStation_PROMPT"/>
        </MenuItemOverrides></Match>
    </PresentationMap>
    <PresentationMap type="Search">
        <Match>
            <SearchCategories stringId="SearchTitle">
                <Category id="artists" mappedId="artist"/>
                <Category id="tracks" mappedId="song"/>
                <CustomCategory stringId="radioShows" mappedId="radioshow"/>
            </SearchCategories>
            <SearchCategories stringId="LibrarySearchTitle">
                <Category id="artists" mappedId="libraryartist"/>
            </SearchCategories>
        </Match>
    </PresentationMap>
    <PresentationMap type="StreamQualityBadgeDictionary">
        <StreamQualityBadgeDictionary>
            <QualityBadgeMap id="16bit" text="Lossless"/>
        </StreamQualityBadgeDictionary>
    </PresentationMap>
    <PresentationMap type="NowPlayingRatings">
        <Match propname="vote" value="0">
            <Ratings>
                <Rating AutoSkip="NEVER" Id="1" StringId="VoteUp"
                        OnSuccessStringId="VoteUpSuccess">
                    <Icon Controller="acr" Uri="https://img/star-acr.png"/>
                    <Icon Controller="universal" Uri="https://img/star.svg"/>
                </Rating>
            </Ratings>
        </Match>
    </PresentationMap>
    <PresentationMap type="QuickSkips">
        <QuickSkip type="episode.podcast" forwardSeconds="45" backwardSeconds="10"/>
    </PresentationMap>
</Presentation>
"""


STRINGS_XML = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<stringtables xmlns="http://sonos.com/sonosapi">
  <stringtable rev="1" xml:lang="en-US">
    <string stringId="StartStation">Start Station</string>
    <string stringId="StartStation_PROMPT">Start a station?</string>
    <string stringId="StartStation_SUCCESS">Station started</string>
    <string stringId="StartStation_FAILURE">Could not start</string>
    <string stringId="StartStation_DURING">Starting...</string>
    <string stringId="Artist_And_Album">{artist} - {album}</string>
  </stringtable>
  <stringtable rev="1" xml:lang="de-DE">
    <string stringId="StartStation">Sender starten</string>
    <string stringId="Artist_And_Album">{artist} - {album}</string>
  </stringtable>
</stringtables>
"""


def test_get_strings_parses_all_languages_and_caches(monkeypatch):
    manifest = {
        "endpoints": [{"type": "browse", "uri": "https://content.invalid/browse/v1"}],
        "strings": {"uri": "https://content.invalid/strings.xml", "version": 484},
    }
    session = FakeSession(
        get_responses=[
            FakeResponse(json_value=manifest),
            FakeResponse(content=STRINGS_XML),
        ]
    )
    service = FakeService(manifest_uri="https://content.invalid/manifest.json")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    strings = music_browser.get_strings()

    assert isinstance(strings, browser.StringTables)
    assert strings.uri == "https://content.invalid/strings.xml"
    assert strings.version == 484
    assert strings.languages == ("en-US", "de-DE")
    assert strings.localized("en-US")["StartStation"] == "Start Station"
    assert strings.localized("de-DE")["StartStation"] == "Sender starten"
    assert strings.resolve("StartStation", "de-DE") == "Sender starten"
    assert strings.resolve("StartStation_FAILURE", "de-DE") == "StartStation_FAILURE"
    assert strings.resolve("missing", "en-US", default="?") == "?"
    # Falls back to any language when the requested one is absent.
    assert strings.localized("fr-FR") == strings.localized("en-US")
    # Cached: the second call performs no additional fetch.
    assert music_browser.get_strings() is strings
    assert len(session.get_calls) == 2


def test_get_strings_none_without_strings_uri(monkeypatch):
    session = FakeSession()
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    assert music_browser.get_strings() is None
    assert music_browser.localized_strings() == {}
    assert len(session.get_calls) == 0


def test_get_strings_prefers_descriptor_uri(monkeypatch):
    session = FakeSession(get_responses=[FakeResponse(content=STRINGS_XML)])
    service = FakeService(strings_uri="https://content.invalid/strings.xml")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    assert music_browser.strings_uri == "https://content.invalid/strings.xml"
    assert music_browser.get_strings() is not None
    assert len(session.get_calls) == 1


def test_presentation_map_resolves_string_ids(monkeypatch):
    manifest = {
        "endpoints": [{"type": "browse", "uri": "https://content.invalid/browse/v1"}],
        "presentationMap": {
            "uri": "https://content.invalid/pmap.xml",
            "version": 484,
        },
        "strings": {"uri": "https://content.invalid/strings.xml", "version": 484},
    }
    session = FakeSession(
        get_responses=[
            FakeResponse(json_value=manifest),
            FakeResponse(content=PMAP_XML),
            FakeResponse(content=STRINGS_XML),
        ]
    )
    service = FakeService(manifest_uri="https://content.invalid/manifest.json")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    pmap = music_browser.get_presentation_map()
    resolved = pmap.resolve_strings(music_browser.get_strings(), "en-US")

    # Each string-id attribute resolves into its own field: the entry
    # carries both a plain label and a prompt, so both are preserved.
    override = resolved["menu_item_overrides"][0]
    assert override["text"] == "Start Station"
    assert override["raw_StringId"] == "StartStation"
    assert override["prompt_text"] == "Start a station?"
    assert override["raw_PromptStringId"] == "StartStation_PROMPT"
    # Display-type lines with string ids resolve; token lines are untouched.
    title_with_artist = resolved["display_types"]["TitleWithArtist"]["lines"]
    assert title_with_artist == [
        {"token": "title"},
        {
            "string_id": "Artist_And_Album",
            "text": "{artist} - {album}",
            "raw_id": "Artist_And_Album",
        },
    ]
    # Ratings carry both their label and success text (VoteUp/VoteUpSuccess
    # are not in the strings fixture, so each resolves to its own id).
    rating = resolved["now_playing_ratings"][0]["rating"]
    assert rating["text"] == "VoteUp"
    assert rating["raw_string_id"] == "VoteUp"
    assert rating["success_text"] == "VoteUpSuccess"
    assert rating["raw_on_success_string_id"] == "VoteUpSuccess"


def test_get_manifest_returns_parsed_json_and_caches(monkeypatch):
    manifest = {
        "endpoints": [{"type": "browse", "uri": "https://content.invalid/browse/v1"}],
        "presentationMap": {
            "uri": "https://content.invalid/pmap.xml",
            "version": 484,
        },
    }
    session = FakeSession(get_responses=[FakeResponse(json_value=manifest)])
    service = FakeService(manifest_uri="https://content.invalid/manifest.json")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    assert music_browser.get_manifest() == manifest
    assert music_browser.manifest_data == manifest
    assert music_browser.root_transport == "content"
    # The manifest is fetched once during construction and cached afterwards.
    assert len(session.get_calls) == 1


def test_get_manifest_empty_without_manifest_uri(monkeypatch):
    session = FakeSession()
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    assert music_browser.get_manifest() == {}
    assert music_browser.manifest_data == {}
    assert len(session.get_calls) == 0


def test_get_presentation_map_parses_all_blocks(monkeypatch):
    manifest = {
        "endpoints": [{"type": "browse", "uri": "https://content.invalid/browse/v1"}],
        "presentationMap": {
            "uri": "https://content.invalid/pmap.xml",
            "version": 484,
        },
    }
    session = FakeSession(
        get_responses=[
            FakeResponse(json_value=manifest),
            FakeResponse(content=PMAP_XML),
        ]
    )
    service = FakeService(manifest_uri="https://content.invalid/manifest.json")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    pmap = music_browser.get_presentation_map()

    assert isinstance(pmap, browser.PresentationMap)
    assert pmap.uri == "https://content.invalid/pmap.xml"
    assert pmap.version == 484
    assert pmap.page_size == 100
    assert pmap.artwork_size_map == {40: "40x40", 200: "200x200"}
    assert pmap.browse_icon_size_map == {40: "-40.png", 0: "-legacy.png"}
    assert pmap.display_types["__root__"] == {"display_mode": "BRAND"}
    assert pmap.display_types["GridView"] == {"display_mode": "GRID"}
    assert pmap.display_types["AlbumView"]["lines"] == [
        {"token": "title"},
        {"token": "artist"},
        {"token": "summary"},
    ]
    assert pmap.display_types["TitleWithArtist"]["lines"] == [
        {"token": "title"},
        {"string_id": "Artist_And_Album"},
    ]
    assert pmap.display_types["TitleWithArtist"]["item_thumbnails"] == "albumArtUri"
    assert pmap.search_categories == {
        "SearchTitle": [
            {"id": "artists", "mapped_id": "artist", "custom": False},
            {"id": "tracks", "mapped_id": "song", "custom": False},
            {"id": "radioShows", "mapped_id": "radioshow", "custom": True},
        ],
        "LibrarySearchTitle": [
            {"id": "artists", "mapped_id": "libraryartist", "custom": False}
        ],
    }
    assert pmap.search_variants() == {
        "artists": [
            ("SearchTitle", "artist"),
            ("LibrarySearchTitle", "libraryartist"),
        ],
        "tracks": [("SearchTitle", "song")],
        "radioShows": [("SearchTitle", "radioshow")],
    }
    assert pmap.menu_item_overrides == [
        {
            "StringId": "StartStation",
            "MenuItem": "RelatedPlay",
            "PromptStringId": "StartStation_PROMPT",
        }
    ]
    assert pmap.stream_quality_badges == {"16bit": "Lossless"}
    assert pmap.now_playing_ratings == [
        {
            "propname": "vote",
            "value": "0",
            "type": None,
            "rating": {
                "id": "1",
                "string_id": "VoteUp",
                "auto_skip": "NEVER",
                "on_success_string_id": "VoteUpSuccess",
                "type": None,
                "state": None,
                "icons": {
                    "acr": "https://img/star-acr.png",
                    "universal": "https://img/star.svg",
                },
            },
        }
    ]
    assert pmap.quick_skips == {
        "episode.podcast": {"forward_seconds": 45, "backward_seconds": 10}
    }
    # Cached: the second call performs no additional fetch.
    assert music_browser.get_presentation_map() is pmap
    assert len(session.get_calls) == 2


def test_get_presentation_map_prefers_descriptor_uri(monkeypatch):
    session = FakeSession(get_responses=[FakeResponse(content=PMAP_XML)])
    service = FakeService(presentation_map_uri="https://content.invalid/pmap.xml")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    pmap = music_browser.get_presentation_map()

    assert pmap.uri == "https://content.invalid/pmap.xml"
    assert pmap.version is None
    # No manifest fetch needed; only the descriptor-URI pmap is downloaded.
    assert len(session.get_calls) == 1


def test_get_presentation_map_returns_none_without_uri(monkeypatch):
    session = FakeSession()
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    assert music_browser.get_presentation_map() is None
    assert len(session.get_calls) == 0


def test_get_presentation_map_raises_on_fetch_failure(monkeypatch):
    manifest = {"presentationMap": {"uri": "https://content.invalid/pmap.xml"}}
    session = FakeSession(
        get_responses=[
            FakeResponse(json_value=manifest),
            FakeResponse(status_code=500),
        ]
    )
    service = FakeService(manifest_uri="https://content.invalid/manifest.json")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    with pytest.raises(MusicServiceException, match="presentation map request failed"):
        music_browser.get_presentation_map()


def test_get_presentation_map_raises_on_malformed_xml(monkeypatch):
    manifest = {"presentationMap": {"uri": "https://content.invalid/pmap.xml"}}
    session = FakeSession(
        get_responses=[
            FakeResponse(json_value=manifest),
            FakeResponse(content=b"<Presentation>"),
        ]
    )
    service = FakeService(manifest_uri="https://content.invalid/manifest.json")
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    with pytest.raises(MusicServiceException, match="not valid XML"):
        music_browser.get_presentation_map()


SCROLL_INDICES = b"""\
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <getScrollIndicesResponse xmlns="http://www.sonos.com/Services/1.1">
      <getScrollIndicesResult>
        <total>2</total>
        <index>
          <index>0</index><id>album:0</id><title>A</title>
        </index>
        <index>
          <index>100</index><id>album:100</id><title>B</title>
        </index>
      </getScrollIndicesResult>
    </getScrollIndicesResponse>
  </s:Body>
</s:Envelope>
"""


def test_get_scroll_indices_parses_jump_entries(monkeypatch):
    session = FakeSession(post_responses=[FakeResponse(content=SCROLL_INDICES)])
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    data = music_browser.get_scroll_indices("albums")

    assert data["total"] == 2
    assert data["indices"] == [
        {"index": "0", "id": "album:0", "title": "A"},
        {"index": "100", "id": "album:100", "title": "B"},
    ]
    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    assert browser._children(envelope, "getScrollIndices")
    assert browser._children(envelope, "id")[0].text == "albums"


def test_get_scroll_indices_accepts_browse_item(monkeypatch):
    session = FakeSession(post_responses=[FakeResponse(content=SCROLL_INDICES)])
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    data = music_browser.get_scroll_indices(
        MusicServiceBrowseItem("albums", "Albums", "mediaCollection")
    )

    assert data["indices"][0]["id"] == "album:0"


def test_set_played_seconds_sends_progress(monkeypatch):
    session = FakeSession(
        post_responses=[
            FakeResponse(
                content=(
                    b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
                    b"<s:Body><getSetPlayedSecondsResponse/>"
                    b"</s:Body></s:Envelope>"
                )
            )
        ]
    )
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    result = music_browser.set_played_seconds("track:1", 42)

    assert result is None
    _url, request = session.post_calls[0]
    envelope = XML.fromstring(request["data"])
    op = browser._children(envelope, "setPlayedSeconds")[0]
    fields = {browser._local_name(node.tag): node.text or "" for node in op}
    assert fields == {"id": "track:1", "seconds": "42"}


def test_set_played_seconds_requires_integer_seconds(monkeypatch):
    session = FakeSession()
    service = FakeService()
    monkeypatch.setattr(browser, "MusicService", lambda *_args, **_kwargs: service)
    music_browser = MusicServiceBrowser(
        "Example", account=make_account(), device=FakeDevice(), session=session
    )

    with pytest.raises(ValueError, match="invalid literal"):
        music_browser.set_played_seconds("track:1", "not-a-number")
