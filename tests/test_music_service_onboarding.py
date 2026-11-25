"""Tests for music-service account onboarding and management."""

import pytest

from soco.exceptions import MusicServiceException
from soco.music_services import browser, onboarding
from soco.music_services.browser import ConfiguredMusicServiceAccount
from soco.music_services.onboarding import (
    AccountLink,
    DeviceAuthCredential,
    MusicServiceAccountManager,
    account_type,
)
from soco.xml import XML


class FakeResponse:
    """Small requests.Response stand-in for the player SOAP client."""

    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content


SUCCESS = b"""\
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Body><u:AddOAuthAccountXResponse
    xmlns:u="urn:schemas-upnp-org:service:SystemProperties:1">
<AccountUDN>SA_RINCON52231_X_#Svc52231-1-Token</AccountUDN>
<AccountNickname>Person</AccountNickname>
</u:AddOAuthAccountXResponse></s:Body></s:Envelope>"""


class FakeService:
    """MusicService-compatible descriptor used without network discovery."""

    def __init__(
        self, name="Apple Music", service_id=204, auth_type="AppLink", capabilities="0"
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
        self.presentation_map_uri = None
        self.manifest_uri = None


class FakeSystemProperties:
    def GetString(self, args):  # pylint: disable=invalid-name
        assert args == [("VariableName", "R_TrialZPSerial")]
        return {"StringValue": "player-device-id"}


class FakeDeviceProperties:
    def __init__(self, household, live_household=None):
        self.household = household
        self.live = live_household if live_household is not None else household
        self.calls = []

    def GetHouseholdID(self):  # pylint: disable=invalid-name
        self.calls.append("GetHouseholdID")
        return {"CurrentHouseholdID": self.live}


class FakeDevice:
    """The small SoCo surface the account manager needs."""

    uid = "RINCON_000000000001400"
    ip_address = "192.0.2.1"
    systemProperties = FakeSystemProperties()

    def __init__(self, household="Sonos_hh", live_household=None):
        self.household_id = household
        self.deviceProperties = FakeDeviceProperties(household, live_household)


def make_link(
    service_id=204,
    name="Apple Music",
    auth="AppLink",
    household="Sonos_hh",
    code="code",
):
    return AccountLink(
        service_id,
        name,
        auth,
        household,
        account_type(service_id),
        "https://login.example/",
        code,
        link_device_id="device",
        callback_path="sonos://addAccount",
    )


def build_manager(monkeypatch, service, device=None, **kwargs):
    """Construct a manager with the real MusicService swapped for a fake."""
    monkeypatch.setattr(onboarding, "MusicService", lambda *_args, **_kwargs: service)
    return MusicServiceAccountManager(
        service.service_name, device=device or FakeDevice(), **kwargs
    )


def patch_sp_call(monkeypatch, responses):
    """Patch _SystemPropertiesClient.call with a queue of results."""
    calls = []

    def fake_call(self, action, fields, timeout=35):  # pylint: disable=unused-argument
        calls.append((action, fields))
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(onboarding._SystemPropertiesClient, "call", fake_call)
    return calls


def patch_smapi_request(monkeypatch, results):
    """Patch the provider SMAPI _request with per-action XML results.

    ``results`` maps an action name to either the inner result XML (a str),
    an Exception instance, or a callable ``(action, fields) -> str``.
    """
    calls = []

    def fake_request(  # pylint: disable=unused-argument
        self, action, fields, credential_mode="normal", bearer_token=None
    ):
        calls.append((action, fields, credential_mode, bearer_token))
        result = results[action]
        if isinstance(result, Exception):
            raise result
        if callable(result):
            result = result(action, fields)
        return XML.fromstring(
            (
                '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
                '<s:Body><{0}Response xmlns="http://www.sonos.com/Services/1.1">'
                "{1}</{0}Response></s:Body></s:Envelope>"
            )
            .format(action, result)
            .encode("utf-8")
        )

    monkeypatch.setattr(onboarding._ConfiguredSmapiClient, "_request", fake_request)
    return calls


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------


def test_account_type_encodes_service_and_schema():
    assert account_type(204) == 52231
    assert account_type(12) == 3079
    with pytest.raises(ValueError, match="positive"):
        account_type(0)
    with pytest.raises(ValueError, match="0 and 255"):
        account_type(204, 256)


def test_account_envelope_round_trips_and_rejects_other_households():
    encoded = browser._encrypt_account_payload(b"secret-value", "Sonos_hh")
    assert encoded.startswith("2:")
    assert browser._decrypt_account_payload(encoded, "Sonos_hh") == b"secret-value"
    with pytest.raises(MusicServiceException):
        browser._decrypt_account_payload(encoded, "Sonos_other")


def test_keyless_account_property():
    assert ConfiguredMusicServiceAccount(204, 0, "SA_RINCON52231_").keyless
    assert not ConfiguredMusicServiceAccount(
        204, 0, "SA_RINCON52231_X_#Svc204-1-Token", token="t"
    ).keyless


# ---------------------------------------------------------------------------
# Link flow (provider SMAPI)
# ---------------------------------------------------------------------------


def test_begin_link_anonymous_returns_placeholder_without_network(monkeypatch):
    service = FakeService(auth_type="Anonymous")
    calls = patch_smapi_request(monkeypatch, {})
    manager = build_manager(monkeypatch, service)

    link = manager.begin_link()

    assert link.source_action == "anonymous"
    assert link.registration_url == ""
    assert link.link_code == ""
    assert not calls


def test_devicelink_falls_back_to_legacy_link_code(monkeypatch):
    service = FakeService(service_id=201, name="Amazon Music", auth_type="DeviceLink")
    calls = patch_smapi_request(
        monkeypatch,
        {
            "getAppLink": onboarding._BrowseSoapFault(
                "Server", "getAppLink unsupported", 500
            ),
            "getDeviceLinkCode": (
                "<getDeviceLinkCodeResult><regUrl>https://login.example/</regUrl>"
                "<linkCode>short-code</linkCode>"
                "<linkDeviceId>hidden-device</linkDeviceId>"
                "</getDeviceLinkCodeResult>"
            ),
        },
    )
    manager = build_manager(monkeypatch, service)

    link = manager.begin_link()

    assert link.source_action == "getDeviceLinkCode"
    assert link.registration_url == "https://login.example/"
    assert link.link_code == "short-code"
    assert link.link_device_id == "hidden-device"
    assert [call[0] for call in calls] == ["getAppLink", "getDeviceLinkCode"]


def test_applink_app_only_marker_raises_actionable_error(monkeypatch):
    service = FakeService()
    patch_smapi_request(
        monkeypatch,
        {
            "getAppLink": (
                "<getAppLinkResult><callToAction />"
                "<appUrlEncrypt>true</appUrlEncrypt></getAppLinkResult>"
            )
        },
    )
    manager = build_manager(monkeypatch, service)

    with pytest.raises(
        MusicServiceException, match="app-to-app linking only.*Sonos mobile app"
    ):
        manager.begin_link()


def test_applink_with_real_app_url_is_still_usable(monkeypatch):
    service = FakeService()
    patch_smapi_request(
        monkeypatch,
        {
            "getAppLink": (
                "<getAppLinkResult><appUrl>apple-music://authorize</appUrl>"
                "<appUrlEncrypt>true</appUrlEncrypt></getAppLinkResult>"
            )
        },
    )
    manager = build_manager(monkeypatch, service)

    link = manager.begin_link()

    assert link.app_url == "apple-music://authorize"


def test_devicelink_app_only_marker_still_falls_back_to_link_code(monkeypatch):
    service = FakeService(service_id=201, name="Amazon Music", auth_type="DeviceLink")
    patch_smapi_request(
        monkeypatch,
        {
            "getAppLink": (
                "<getAppLinkResult><callToAction />"
                "<appUrlEncrypt>true</appUrlEncrypt></getAppLinkResult>"
            ),
            "getDeviceLinkCode": (
                "<getDeviceLinkCodeResult><regUrl>https://login.example/</regUrl>"
                "<linkCode>short-code</linkCode></getDeviceLinkCodeResult>"
            ),
        },
    )
    manager = build_manager(monkeypatch, service)

    link = manager.begin_link()

    assert link.source_action == "getDeviceLinkCode"
    assert link.registration_url == "https://login.example/"


def test_applink_without_appurl_returns_plain_session(monkeypatch):
    service = FakeService()
    patch_smapi_request(
        monkeypatch,
        {"getAppLink": "<getAppLinkResult><callToAction /></getAppLinkResult>"},
    )
    manager = build_manager(monkeypatch, service)

    link = manager.begin_link()

    assert not link.standalone_supported
    assert link.registration_url == ""


def test_begin_link_rejects_legacy_credential_services(monkeypatch):
    service = FakeService(name="Legacy", auth_type="UserIdPassword")
    patch_smapi_request(monkeypatch, {})
    manager = build_manager(monkeypatch, service)

    with pytest.raises(MusicServiceException, match="call add_credentials instead"):
        manager.begin_link()


def test_non_web_registration_uri_is_not_openable():
    link = AccountLink(
        204,
        "Apple Music",
        "AppLink",
        "Sonos_hh",
        account_type(204),
        "dangerous://login",
        "code",
    )
    assert not link.standalone_supported


def test_link_redacted_dict_hides_secrets():
    link = make_link()
    value = link.redacted_dict()
    assert value["link_code"] == "<redacted>"
    assert value["link_device_id"] == "<redacted>"
    assert value["registration_url"] == "https://login.example/"


def test_get_device_auth_token_exchanges_link_code_and_parses_user_info(monkeypatch):
    service = FakeService()
    calls = patch_smapi_request(
        monkeypatch,
        {
            "getDeviceAuthToken": (
                "<getDeviceAuthTokenResult><authToken>BQBJ-token</authToken>"
                "<privateKey>priv-key</privateKey>"
                "<userInfo><userIdHashCode>Fi0Z-hash</userIdHashCode>"
                "<accountTier>1</accountTier>"
                "<nickname>BookCatKid</nickname></userInfo>"
                "</getDeviceAuthTokenResult>"
            )
        },
    )
    manager = build_manager(monkeypatch, service)
    # No linkDeviceId from the provider: the fallback must be exercised.
    link = AccountLink(
        204,
        "Apple Music",
        "AppLink",
        "Sonos_hh",
        account_type(204),
        "https://login.example/",
        "code",
        link_device_id="",
    )

    credential = manager.get_device_auth_token(link)

    assert credential.auth_token == "BQBJ-token"
    assert credential.private_key == "priv-key"
    assert credential.user_id_hash_code == "Fi0Z-hash"
    # The provider's deprecated accountTier string is deliberately NOT carried
    # (it must never reach AddOAuthAccountX); nickname is kept.
    assert not hasattr(credential, "account_tier")
    assert credential.nickname == "BookCatKid"
    action, fields, mode, bearer = calls[0]
    assert action == "getDeviceAuthToken"
    assert mode == "base"
    assert bearer == ""
    assert fields["householdId"] == "Sonos_hh"
    assert fields["linkCode"] == "code"
    # Providers that omit linkDeviceId fall back to the controller's own
    # R_TrialZPSerial.
    assert fields["linkDeviceId"] == "player-device-id"


def test_get_device_auth_token_translates_provider_fault(monkeypatch):
    service = FakeService()
    patch_smapi_request(
        monkeypatch,
        {
            "getDeviceAuthToken": onboarding._BrowseSoapFault(
                "Client.AuthTokenExpired", "Token Expired", 500
            )
        },
    )
    manager = build_manager(monkeypatch, service)

    # A provider rejection at the exchange step must surface as the public
    # exception, never the internal SMAPI fault type.
    with pytest.raises(MusicServiceException, match="getDeviceAuthToken failed"):
        manager.get_device_auth_token(make_link())


def test_get_device_auth_token_rejects_incomplete_credential_pair(monkeypatch):
    service = FakeService()
    patch_smapi_request(
        monkeypatch,
        {
            "getDeviceAuthToken": (
                "<getDeviceAuthTokenResult><authToken>only</authToken>"
                "</getDeviceAuthTokenResult>"
            )
        },
    )
    manager = build_manager(monkeypatch, service)

    with pytest.raises(MusicServiceException, match="no authToken/privateKey pair"):
        manager.get_device_auth_token(make_link())


# ---------------------------------------------------------------------------
# Commit link (player SystemProperties)
# ---------------------------------------------------------------------------


def test_commit_link_uses_captured_add_oauth_contract(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    exchange_calls = []

    def fake_exchange(link):
        exchange_calls.append(link)
        return DeviceAuthCredential(
            auth_token="BQBJ-token",
            private_key="priv-key",
            user_id_hash_code="Fi0Z-hash",
            nickname="BookCatKid",
        )

    monkeypatch.setattr(manager, "get_device_auth_token", fake_exchange)
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    added = manager.commit_link(make_link())

    assert added.account_udn == "SA_RINCON52231_X_#Svc52231-1-Token"
    # The link code is exchanged with the provider first, never sent to the
    # player (which rejects it with UPnP 402).
    assert len(exchange_calls) == 1
    action, fields = sp_calls[0]
    assert action == "AddOAuthAccountX"
    assert fields["AccountType"] == "52231"
    # Every account value is wrapped in the household 2: envelope and the
    # authorization code / redirect URI stay empty -- the provider credential
    # package is what is installed.
    assert fields["AuthorizationCode"] == ""
    assert fields["RedirectURI"] == ""
    assert fields["AccountTier"] == "1"
    assert (
        browser._decrypt_account_payload(fields["AccountToken"], "Sonos_hh")
        == b"BQBJ-token"
    )
    # The provider's key already carries its own epoch stamp, so it is
    # enveloped verbatim.
    assert (
        browser._decrypt_account_payload(fields["AccountKey"], "Sonos_hh")
        == b"priv-key"
    )
    assert (
        browser._decrypt_account_payload(fields["OAuthDeviceID"], "Sonos_hh")
        == b"Sonos_hh"
    )
    assert (
        browser._decrypt_account_payload(fields["UserIdHashCode"], "Sonos_hh")
        == b"Fi0Z-hash"
    )


def test_commit_link_surfaces_provider_nickname_for_prefill(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    monkeypatch.setattr(
        manager,
        "get_device_auth_token",
        lambda link: DeviceAuthCredential(
            auth_token="BQBJ-token", private_key="priv-key", nickname="BookCatKid"
        ),
    )
    patch_sp_call(monkeypatch, [SUCCESS])

    added = manager.commit_link(make_link())

    # The provider's userInfo.nickname is surfaced separately so the caller
    # can pre-fill its nickname prompt; the player's own stored nickname comes
    # back from AddOAuthAccountX unchanged.
    assert added.provider_nickname == "BookCatKid"
    assert added.nickname == "Person"


def test_link_for_wrong_service_is_rejected_before_network(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [])

    with pytest.raises(MusicServiceException, match="different service"):
        manager.commit_link(make_link(service_id=37, name="SiriusXM"))

    assert not sp_calls


def test_link_with_wrong_account_type_is_rejected_before_network(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [])
    link = make_link()
    link = AccountLink(
        link.service_id,
        link.service_name,
        link.auth_type,
        link.household_id,
        52232,
        link.registration_url,
        link.link_code,
    )

    with pytest.raises(MusicServiceException, match="account type does not match"):
        manager.commit_link(link)

    assert not sp_calls


def test_link_cannot_be_committed_to_another_household(monkeypatch):
    service = FakeService()
    manager = build_manager(
        monkeypatch, service, device=FakeDevice(live_household="Sonos_other")
    )
    sp_calls = patch_sp_call(monkeypatch, [])

    with pytest.raises(
        MusicServiceException, match="player 192.0.2.1 belongs to Sonos_other"
    ):
        manager.commit_link(make_link())

    assert not sp_calls


def test_commit_link_omits_empty_user_id_hash(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    monkeypatch.setattr(
        manager,
        "get_device_auth_token",
        lambda link: DeviceAuthCredential(
            auth_token="BQBJ-token", private_key="priv-key"
        ),
    )
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    manager.commit_link(make_link())

    action, fields = sp_calls[0]
    # Providers whose getDeviceAuthToken returns no userIdHashCode must not
    # produce an enveloped empty blob; the field is simply left empty.
    assert fields["UserIdHashCode"] == ""
    assert fields["AccountTier"] == "1"


def test_commit_link_converts_hex_user_id_hash_to_base64(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    monkeypatch.setattr(
        manager,
        "get_device_auth_token",
        lambda link: DeviceAuthCredential(
            auth_token="BQBJ-token",
            private_key="priv-key/1786401533373",
            user_id_hash_code="1b406fc7825ba31162c8ed926084b4b5",
        ),
    )
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    manager.commit_link(make_link())

    action, fields = sp_calls[0]
    stored_hash = browser._decrypt_account_payload(
        fields["UserIdHashCode"], "Sonos_hh"
    ).decode()
    # Verified live: the player accepts UserIdHashCode only as base64. The
    # provider currently returns the hash as hex (32 hex chars); the same
    # bytes committed as base64 return 200 while the raw hex form is rejected
    # with 402.
    assert stored_hash == "G0Bvx4JboxFiyO2SYIS0tQ=="


def test_commit_link_always_commits_record_flag_tier(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    monkeypatch.setattr(
        manager,
        "get_device_auth_token",
        lambda link: DeviceAuthCredential(
            auth_token="BQBJ-token",
            private_key="priv-key/1786401533373",
            user_id_hash_code="1b406fc7825ba31162c8ed926084b4b5",
        ),
    )
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    manager.commit_link(make_link())

    action, fields = sp_calls[0]
    # The provider's deprecated userInfo.accountTier string must never reach
    # the player -- sending it raw is rejected with UPnP 402. The player's
    # AccountTier is a record flag, so the commit always sends ``1``.
    assert fields["AccountTier"] == "1"
    # The provider key already carries its epoch stamp; it is stored verbatim.
    assert browser._decrypt_account_payload(fields["AccountKey"], "Sonos_hh") == (
        b"priv-key/1786401533373"
    )


def test_commit_link_failed_exchange_never_mutates_player(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)

    def raise_expired(link):
        raise MusicServiceException("the link code may have expired")

    monkeypatch.setattr(manager, "get_device_auth_token", raise_expired)
    sp_calls = patch_sp_call(monkeypatch, [])

    with pytest.raises(MusicServiceException, match="link code may have expired"):
        manager.commit_link(make_link())

    # If the provider exchange fails, the player must not be touched: only the
    # read-only household check runs, never AddOAuthAccountX.
    assert not sp_calls
    assert manager.device.deviceProperties.calls == ["GetHouseholdID"]


def test_commit_link_explains_existing_duplicate_account(monkeypatch):
    service = FakeService(service_id=12, name="Spotify")
    manager = build_manager(monkeypatch, service)
    monkeypatch.setattr(
        manager,
        "get_device_auth_token",
        lambda link: DeviceAuthCredential(
            auth_token="BQBJ-token", private_key="priv-key"
        ),
    )
    monkeypatch.setattr(
        ConfiguredMusicServiceAccount,
        "get_accounts",
        lambda *_args, **_kwargs: [
            ConfiguredMusicServiceAccount(
                12,
                50,
                "SA_RINCON3079_X_#Svc3079-0-Token",
                username="X_#Svc3079-0-Token",
                nickname="Spotify 50",
            )
        ],
    )
    sp_calls = patch_sp_call(
        monkeypatch,
        [
            onboarding._SystemPropertiesFault(
                "AddOAuthAccountX", 500, "s:Client", "UPnPError", upnp_code=402
            )
        ],
    )

    with pytest.raises(
        MusicServiceException,
        match="already linked.*Spotify 50.*Reauthorize the existing account in place",
    ):
        manager.commit_link(make_link(service_id=12, name="Spotify"))

    assert sp_calls[0][0] == "AddOAuthAccountX"


def test_commit_link_replace_path_replaces_in_place(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    monkeypatch.setattr(
        manager,
        "get_device_auth_token",
        lambda link: DeviceAuthCredential(
            auth_token="BQBJ-fresh",
            private_key="priv-key/1786401533373",
            nickname="BookCatKid",
        ),
    )
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    added = manager.commit_link(
        make_link(), replace_account_udn="SA_RINCON52231_X_#Svc52231-1-Token"
    )

    # Re-linking an existing account mirrors the desktop controller's commit
    # dispatcher: the record keeps its UDN and ReplaceAccountX swaps only the
    # credential package, instead of committing a duplicate AddOAuthAccountX
    # record (which the player rejects with 402).
    assert sp_calls[0][0] == "ReplaceAccountX"
    assert added.account_udn == "SA_RINCON52231_X_#Svc52231-1-Token"
    assert added.provider_nickname == "BookCatKid"


def test_replace_account_credentials_uses_native_replace_contract(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])
    credential = DeviceAuthCredential(
        auth_token="BQBJ-fresh", private_key="priv-key/1786401533373"
    )

    added = manager.replace_account_credentials(
        "SA_RINCON52231_X_#Svc52231-1-Token", credential
    )

    action, fields = sp_calls[0]
    assert action == "ReplaceAccountX"
    # ReplaceAccountX's argument list matches the player's SystemProperties
    # SCPD: AccountUDN, NewAccountID, NewAccountPassword, AccountToken,
    # AccountKey, OAuthDeviceID, NewAccountUDN.
    assert list(fields) == [
        "AccountUDN",
        "NewAccountID",
        "NewAccountPassword",
        "AccountToken",
        "AccountKey",
        "OAuthDeviceID",
        "NewAccountUDN",
    ]
    # OAuth-style services leave the legacy credential pair and the new UDN
    # empty, exactly like the desktop's own replace commit.
    assert fields["NewAccountID"] == ""
    assert fields["NewAccountPassword"] == ""
    assert fields["NewAccountUDN"] == ""
    # Credential values follow the AddOAuthAccountX envelope contract.
    assert browser._decrypt_account_payload(fields["AccountUDN"], "Sonos_hh") == (
        b"SA_RINCON52231_X_#Svc52231-1-Token"
    )
    assert (
        browser._decrypt_account_payload(fields["AccountToken"], "Sonos_hh")
        == b"BQBJ-fresh"
    )
    assert browser._decrypt_account_payload(fields["AccountKey"], "Sonos_hh") == (
        b"priv-key/1786401533373"
    )
    assert (
        browser._decrypt_account_payload(fields["OAuthDeviceID"], "Sonos_hh")
        == b"Sonos_hh"
    )
    # ReplaceAccountX has no output arguments (SCPD); the existing UDN is
    # reported unchanged.
    assert added.account_udn == "SA_RINCON52231_X_#Svc52231-1-Token"


def test_replace_account_credentials_normalizes_blob_udn(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])
    blob = browser._encrypt_account_payload(
        b"SA_RINCON52231_X_#Svc52231-1-Token", "Sonos_hh"
    )
    credential = DeviceAuthCredential(auth_token="BQBJ-fresh", private_key="priv-key")

    manager.replace_account_credentials(blob, credential)

    action, fields = sp_calls[0]
    # The 2: blob from the inventory must be decoded first so the sent
    # AccountUDN decrypts to the plaintext UDN (no double encoding).
    assert browser._decrypt_account_payload(fields["AccountUDN"], "Sonos_hh") == (
        b"SA_RINCON52231_X_#Svc52231-1-Token"
    )


def test_replace_account_credentials_rejects_incomplete_package(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [])
    credential = DeviceAuthCredential(auth_token="", private_key="")

    with pytest.raises(MusicServiceException, match="complete credential package"):
        manager.replace_account_credentials(
            "SA_RINCON52231_X_#Svc52231-1-Token", credential
        )

    assert not sp_calls


# ---------------------------------------------------------------------------
# Legacy credentials
# ---------------------------------------------------------------------------


def test_anonymous_service_commits_with_empty_key(monkeypatch):
    service = FakeService(service_id=511, name="90s90s Radio", auth_type="Anonymous")
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    manager.add_credentials("", "")

    action, fields = sp_calls[0]
    assert action == "AddAccountX"
    assert fields["AccountType"] == str(account_type(511))
    assert fields["AccountID"] == ""


def test_legacy_credentials_use_add_account(monkeypatch):
    service = FakeService(service_id=9, name="Legacy", auth_type="UserIdPassword")
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    manager.add_credentials("user", "pass")

    action, fields = sp_calls[0]
    assert action == "AddAccountX"
    assert fields["AccountID"] == "user"
    assert fields["AccountPassword"] == "pass"


def test_legacy_account_rejects_stale_household_before_mutation(monkeypatch):
    service = FakeService(service_id=9, name="Legacy", auth_type="UserIdPassword")
    manager = build_manager(
        monkeypatch, service, device=FakeDevice(live_household="Sonos_other")
    )
    sp_calls = patch_sp_call(monkeypatch, [])

    with pytest.raises(MusicServiceException, match="player .* belongs to Sonos_other"):
        manager.add_credentials("user", "pass")

    assert not sp_calls


def test_missing_legacy_credentials_are_rejected_before_network(monkeypatch):
    user_id = FakeService(service_id=8, name="User service", auth_type="UserId")
    manager = build_manager(monkeypatch, user_id)
    sp_calls = patch_sp_call(monkeypatch, [])

    with pytest.raises(MusicServiceException, match="requires a username"):
        manager.add_credentials("", "")
    assert not sp_calls

    password = FakeService(
        service_id=9, name="Password service", auth_type="UserIdPassword"
    )
    manager = build_manager(monkeypatch, password)
    sp_calls = patch_sp_call(monkeypatch, [])

    with pytest.raises(MusicServiceException, match="requires a password"):
        manager.add_credentials("user", "")
    assert not sp_calls


# ---------------------------------------------------------------------------
# Account management
# ---------------------------------------------------------------------------


def test_remove_account_uses_native_remove_contract(monkeypatch):
    service = FakeService(service_id=9, name="Legacy", auth_type="UserIdPassword")
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    manager.remove_account("SA_RINCON2311_X_#Svc2311-1-Token")

    action, fields = sp_calls[0]
    assert action == "RemoveAccount"
    assert fields["AccountType"] == str(account_type(9))
    assert fields["AccountID"] == "SA_RINCON2311_X_#Svc2311-1-Token"


def test_remove_keyless_account_uses_empty_key_contract(monkeypatch):
    service = FakeService(service_id=511, name="90s90s Radio", auth_type="Anonymous")
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    manager.remove_account("SA_RINCON130823_")

    action, fields = sp_calls[0]
    assert action == "RemoveAccount"
    assert fields["AccountType"] == str(account_type(511))
    assert fields["AccountID"] == ""


def test_remove_account_rejects_missing_udn_before_network(monkeypatch):
    service = FakeService(service_id=9, name="Legacy", auth_type="UserIdPassword")
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [])

    with pytest.raises(MusicServiceException, match="account UDN is required"):
        manager.remove_account("")

    assert not sp_calls


def test_edit_password_uses_native_contract(monkeypatch):
    service = FakeService(service_id=9, name="Legacy", auth_type="UserIdPassword")
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    manager.edit_account_password("SA_RINCON2311_X_#Svc2311-1-Token", "new-pass")

    action, fields = sp_calls[0]
    assert action == "EditAccountPasswordX"
    # AccountID is the account key (Username0), not the full UDN: the player
    # rejects the full UDN for edits (UPnP 806).
    assert fields["AccountID"] == "X_#Svc2311-1-Token"
    assert fields["NewAccountPassword"] == "new-pass"


def test_edit_password_rejects_oauth_service_before_network(monkeypatch):
    linked = FakeService(service_id=37, name="Linked", auth_type="AppLink")
    manager = build_manager(monkeypatch, linked)
    sp_calls = patch_sp_call(monkeypatch, [])

    with pytest.raises(MusicServiceException, match="applies to UserIdPassword"):
        manager.edit_account_password("SA_RINCON9479_X_#Svc9479-1-Token", "new-pass")
    assert not sp_calls

    user_id = FakeService(service_id=8, name="User service", auth_type="UserId")
    manager = build_manager(monkeypatch, user_id)
    sp_calls = patch_sp_call(monkeypatch, [])

    with pytest.raises(MusicServiceException, match="applies to UserIdPassword"):
        manager.edit_account_password("SA_RINCON2055_X_#Svc2055-1-Token", "new-pass")
    assert not sp_calls


def test_edit_md_uses_native_contract(monkeypatch):
    service = FakeService(service_id=37, name="Linked", auth_type="AppLink")
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    manager.edit_account_md("SA_RINCON9479_X_#Svc9479-1-Token", "provider-md")

    action, fields = sp_calls[0]
    assert action == "EditAccountMd"
    assert fields["AccountID"] == "X_#Svc9479-1-Token"
    assert fields["NewAccountMd"] == "provider-md"


def test_set_nickname_encodes_values_in_household_envelope(monkeypatch):
    service = FakeService(service_id=37, name="Linked", auth_type="AppLink")
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    manager.set_nickname("SA_RINCON9479_X_#Svc9479-1-Token", "New name")

    action, fields = sp_calls[0]
    assert action == "SetAccountNicknameX"
    # Plaintext values are rejected (UPnP 402); the player wants both the UDN
    # and the nickname wrapped in the household 2: envelope.
    assert fields["AccountUDN"].startswith("2:")
    assert fields["AccountNickname"].startswith("2:")
    assert browser._decrypt_account_payload(fields["AccountUDN"], "Sonos_hh") == (
        b"SA_RINCON9479_X_#Svc9479-1-Token"
    )
    assert (
        browser._decrypt_account_payload(fields["AccountNickname"], "Sonos_hh")
        == b"New name"
    )


def test_set_nickname_normalizes_blob_udn_before_encoding(monkeypatch):
    service = FakeService(service_id=37, name="Linked", auth_type="AppLink")
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])
    blob = browser._encrypt_account_payload(
        b"SA_RINCON9479_X_#Svc9479-1-Token", "Sonos_hh"
    )

    manager.set_nickname(blob, "New name")

    action, fields = sp_calls[0]
    # The 2: blob from AddAccountX must be decoded first so it is not
    # double-encoded; the sent AccountUDN decrypts to the plaintext UDN.
    assert browser._decrypt_account_payload(fields["AccountUDN"], "Sonos_hh") == (
        b"SA_RINCON9479_X_#Svc9479-1-Token"
    )


def test_set_nickname_translates_player_rejection(monkeypatch):
    service = FakeService(service_id=37, name="Linked", auth_type="AppLink")
    manager = build_manager(monkeypatch, service)
    patch_sp_call(
        monkeypatch,
        [
            onboarding._SystemPropertiesFault(
                "SetAccountNicknameX", 500, "s:Client", "UPnPError", upnp_code=402
            )
        ],
    )

    with pytest.raises(
        MusicServiceException, match="UPnP error 402.*No account state was changed"
    ):
        manager.set_nickname("SA_RINCON9479_X_#Svc9479-1-Token", "New name")


def test_refresh_credentials_uses_native_contract(monkeypatch):
    service = FakeService(service_id=37, name="Linked", auth_type="AppLink")
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [SUCCESS])

    manager.refresh_account_credentials(7, "fresh-token", "fresh-key")

    action, fields = sp_calls[0]
    assert action == "RefreshAccountCredentialsX"
    assert fields["AccountType"] == str(account_type(37))
    assert fields["AccountUID"] == "7"
    assert fields["AccountToken"] == "fresh-token"
    assert fields["AccountKey"] == "fresh-key"


def test_refresh_credentials_rejects_incomplete_pair_before_network(monkeypatch):
    service = FakeService(service_id=37, name="Linked", auth_type="AppLink")
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [])

    with pytest.raises(MusicServiceException, match="Both a token and a key"):
        manager.refresh_account_credentials(7, "token", "")
    with pytest.raises(MusicServiceException, match="positive numeric AccountUID"):
        manager.refresh_account_credentials(0, "token", "key")
    assert not sp_calls


def test_commit_link_non_402_fault_translates_to_public_error(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    monkeypatch.setattr(
        manager,
        "get_device_auth_token",
        lambda link: DeviceAuthCredential(
            auth_token="BQBJ-token", private_key="priv-key"
        ),
    )
    patch_sp_call(
        monkeypatch,
        [
            onboarding._SystemPropertiesFault(
                "AddOAuthAccountX", 500, "s:Client", "UPnPError", upnp_code=501
            )
        ],
    )

    # Even an unexplained player rejection must surface as the public
    # exception carrying the UPnP details -- never the internal fault type.
    with pytest.raises(MusicServiceException, match="UPnP error 501"):
        manager.commit_link(make_link())


def test_add_credentials_translates_player_rejection(monkeypatch):
    service = FakeService(service_id=511, name="90s90s Radio", auth_type="Anonymous")
    manager = build_manager(monkeypatch, service)
    patch_sp_call(
        monkeypatch,
        [
            onboarding._SystemPropertiesFault(
                "AddAccountX", 500, "s:Client", "UPnPError", upnp_code=402
            )
        ],
    )

    with pytest.raises(MusicServiceException, match="UPnP error 402"):
        manager.add_credentials("", "")


def test_add_credentials_service_cap_is_actionable(monkeypatch):
    service = FakeService(service_id=512, name="SomaFM", auth_type="Anonymous")
    manager = build_manager(monkeypatch, service)
    patch_sp_call(
        monkeypatch,
        [
            onboarding._SystemPropertiesFault(
                "AddAccountX", 500, "s:Client", "UPnPError", upnp_code=802
            )
        ],
    )

    with pytest.raises(
        MusicServiceException,
        match="maximum number of connected music services reached",
    ) as error:
        manager.add_credentials("", "")
    assert "remove an unused account" in str(error.value)


def test_commit_without_link_code_is_rejected_before_network(monkeypatch):
    service = FakeService()
    manager = build_manager(monkeypatch, service)
    sp_calls = patch_sp_call(monkeypatch, [])
    link = AccountLink(
        204,
        "Apple Music",
        "AppLink",
        "Sonos_hh",
        account_type(204),
        "https://login.example/",
        "",
    )

    with pytest.raises(
        MusicServiceException, match="did not provide a standalone link code"
    ):
        manager.commit_link(link)

    assert not sp_calls


def test_system_properties_client_extracts_upnp_fault_code():
    fault_xml = b"""\
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
      <s:Body><s:Fault>
        <faultcode>s:Client</faultcode><faultstring>UPnPError</faultstring>
        <detail><UPnPError xmlns="urn:schemas-upnp-org:control-1-0">
          <errorCode>402</errorCode><errorDescription>Invalid Args</errorDescription>
        </UPnPError></detail>
      </s:Fault></s:Body>
    </s:Envelope>
    """
    client = onboarding._SystemPropertiesClient(FakeDevice())

    fault = client._fault_from_response(
        "AddOAuthAccountX", FakeResponse(500, fault_xml)
    )

    assert fault.action == "AddOAuthAccountX"
    assert fault.http_status == 500
    assert fault.upnp_code == 402
    assert fault.upnp_description == "Invalid Args"
    assert "UPnP error 402" in str(fault)


def test_system_properties_client_handles_non_xml_fault_body():
    client = onboarding._SystemPropertiesClient(FakeDevice())

    fault = client._fault_from_response("RemoveAccount", FakeResponse(500, b"not xml"))

    assert fault.upnp_code is None
    assert "not xml" in fault.message


def test_accounts_property_filters_by_service(monkeypatch):
    service = FakeService(service_id=204)
    manager = build_manager(monkeypatch, service)
    other = ConfiguredMusicServiceAccount(12, 1, "SA_RINCON3079_X_#Svc12-1-Token")
    own = ConfiguredMusicServiceAccount(204, 2, "SA_RINCON52231_X_#Svc204-2-Token")
    monkeypatch.setattr(
        ConfiguredMusicServiceAccount,
        "get_accounts",
        lambda *_args, **_kwargs: [other, own],
    )

    assert manager.accounts == [own]
