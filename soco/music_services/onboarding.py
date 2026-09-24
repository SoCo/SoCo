"""Add, link, rename, and remove music-service accounts in a household.

This is the write side of configured accounts: the browse flow
(:class:`soco.music_services.browser.MusicServiceBrowser`) never mutates the
household, while this module provisions new accounts (OAuth links and legacy
credentials), re-links existing ones, and manages their stored records.

Two transports are used: provider calls (``getAppLink``,
``getDeviceAuthToken``, ...) go through the desktop-controller SMAPI flow,
and player mutations go through the local ``SystemProperties`` UPnP service
with account values wrapped in the household ``2:`` envelope (plaintext is
rejected with UPnP 402).

The link flow separates authorization from mutation: an :class:`AccountLink`
can be inspected and opened without changing the household, and the caller
must explicitly call :meth:`MusicServiceAccountManager.commit_link` to
install the resulting credentials.
"""

from __future__ import unicode_literals

import base64
import re
import uuid
from urllib.parse import urlsplit

import requests

from .. import discovery
from ..exceptions import MusicServiceException
from ..xml import XML
from .browser.credentials import (
    ConfiguredMusicServiceAccount,
    _decrypt_account_payload,
    _encrypt_account_payload,
    _local_time_zone,
)
from .browser.transport import _BrowseSoapFault, _ConfiguredSmapiClient
from .browser.util import SOAP_ENV, _child_text, _children, _element_value
from .music_service import MusicService

#: The SystemProperties UPnP service namespace.
SYSTEM_PROPERTIES_NS = "urn:schemas-upnp-org:service:SystemProperties:1"
SYSTEM_PROPERTIES_CONTROL_URL = "/SystemProperties/Control"

#: The auth-type to player-action mapping. DeviceLink and AppLink accounts are
#: provisioned through the OAuth path; the others through the plain credential
#: path.
AUTH_OPERATIONS = {
    "Anonymous": "AddAccountX",
    "UserId": "AddAccountX",
    "UserIdPassword": "AddAccountX",
    "DeviceLink": "AddOAuthAccountX",
    "AppLink": "AddOAuthAccountX",
}

#: The AccountTier committed with AddOAuthAccountX. The player stores a fixed
#: 0/1 flag here (not the provider's free/premium/trial level), and the
#: desktop controller's OAuth commit always sends "1", which we mirror.
ACCOUNT_TIER = "1"

#: Human-readable hints for the UPnP error codes the player embeds in
#: SystemProperties faults. Codes not listed fall back to the player's own
#: errorDescription.
UPNP_ERROR_TEXT = {
    402: "invalid arguments",
    501: "action failed",
    701: "no such object",
    702: "invalid arguments",
    714: "illegal value for argument",
    800: "action not supported for this service/account on this player",
    802: "maximum number of connected music services reached",
    806: "account could not be resolved",
}

#: The maximum schema revision the player accepts in an encoded account type.
_MAX_SCHEMA_REVISION = 255


def account_type(service_id, schema_revision=7):
    """Encode a service id and schema revision into the player's account type.

    The player addresses accounts with ``service_id * 256 + schema_revision``
    (SCPD type ``ui4``). The schema revision is 7 on current firmware; it is
    exposed for completeness rather than because callers should vary it.

    Args:
        service_id (int): The Sonos service id from the descriptor.
        schema_revision (int): The account-record schema revision. Default 7.

    Returns:
        int: The encoded account type.

    Raises:
        ValueError: If ``service_id`` is not positive or ``schema_revision``
            is outside the player's 0-255 range.
    """
    if service_id <= 0:
        raise ValueError("service_id must be positive")
    if not 0 <= schema_revision <= _MAX_SCHEMA_REVISION:
        raise ValueError("schema_revision must be between 0 and 255")
    return service_id * 256 + schema_revision


class AccountLink:
    """A provider authorization link awaiting the user's browser sign-in.

    Returned by :meth:`MusicServiceAccountManager.begin_link`. Opening
    :attr:`registration_url` (and, for some services, showing
    :attr:`link_code`) lets the user authorize; the resulting
    :class:`AccountLink` is then passed to
    :meth:`MusicServiceAccountManager.commit_link` to install the account.
    No player state is changed while this object merely exists.
    """

    def __init__(
        self,
        service_id,
        service_name,
        auth_type,
        household_id,
        account_type,  # pylint: disable=redefined-outer-name
        registration_url,
        link_code,
        link_device_id="",
        callback_path="",
        app_url="",
        show_link_code=False,
        source_action="",
    ):
        #: int: The Sonos service id.
        self.service_id = service_id
        #: str: The service name.
        self.service_name = service_name
        #: str: The descriptor auth type (DeviceLink, AppLink, ...).
        self.auth_type = auth_type
        #: str: The household the link was created for.
        self.household_id = household_id
        #: int: The encoded account type (:func:`account_type`).
        self.account_type = account_type
        #: str: The provider's browser authorization URL.
        self.registration_url = registration_url
        #: str: The short link code to display when ``showLinkCode`` is set.
        self.link_code = link_code
        #: str: The provider's link device identifier, when returned.
        self.link_device_id = link_device_id
        #: str: The sonos:// callback path sent with getAppLink.
        self.callback_path = callback_path
        #: str: A provider app URL (eg ``apple-music://authorize``), when the
        #: service offers app-to-app authorization.
        self.app_url = app_url
        #: bool: Whether the provider wants the link code shown on screen.
        self.show_link_code = show_link_code
        #: str: The SMAPI action that produced this link
        #: (``getAppLink``/``getDeviceLinkCode``, or ``anonymous``).
        self.source_action = source_action

    @property
    def standalone_supported(self):
        """bool: Whether the link can be completed in a desktop browser.

        A link is standalone when it carries both a link code and an
        ``http(s)`` registration URL. App-only links (an ``appUrl`` but no
        browser path) are not standalone.
        """
        return bool(
            self.link_code
            and urlsplit(self.registration_url).scheme.lower() in ("http", "https")
        )

    def redacted_dict(self):
        """Return a JSON-able dict with secrets replaced by ``<redacted>``.

        The registration URL is kept for opening (some providers embed the
        link code in its query), so it is not itself secret-free.
        """
        return {
            "service_id": self.service_id,
            "service_name": self.service_name,
            "auth_type": self.auth_type,
            "household_id": self.household_id,
            "account_type": self.account_type,
            "registration_url": self.registration_url,
            "link_code": "<redacted>" if self.link_code else "",
            "link_device_id": "<redacted>" if self.link_device_id else "",
            "callback_path": self.callback_path,
            "app_url": self.app_url,
            "show_link_code": self.show_link_code,
            "source_action": self.source_action,
        }

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} service_id={self.service_id} "
            f"source_action={self.source_action!r} at {hex(id(self))}>"
        )


class DeviceAuthCredential:
    """The provider credential package AddOAuthAccountX installs.

    Obtained by the controller itself through the provider's SMAPI
    ``getDeviceAuthToken`` after the user finishes the browser authorization.
    The player does NOT exchange the link code; it receives this result.

    Note:
        The provider's accountTier string is not carried: the player's field
        is numeric; see :data:`ACCOUNT_TIER`.
    """

    def __init__(self, auth_token, private_key, user_id_hash_code="", nickname=""):
        #: str: The provider auth token.
        self.auth_token = auth_token
        #: str: The provider private key (carries its own ``/<epoch>`` stamp).
        self.private_key = private_key
        #: str: The provider's userIdHashCode, when returned.
        self.user_id_hash_code = user_id_hash_code
        #: str: The provider's userInfo.nickname (the account holder's screen
        #: name). Informational only: the official app pre-fills its nickname
        #: prompt with this; the player never sees it inside AddOAuthAccountX.
        self.nickname = nickname

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} service credential package "
            f"at {hex(id(self))}>"
        )


class AddedAccount:
    """The account record committed to the household."""

    def __init__(
        self, service_id, service_name, account_udn, nickname="", provider_nickname=""
    ):
        #: int: The Sonos service id.
        self.service_id = service_id
        #: str: The service name.
        self.service_name = service_name
        #: str: The canonical ``SA_RINCON...`` account UDN.
        self.account_udn = account_udn
        #: str: The nickname stored by the player (empty unless set).
        self.nickname = nickname
        #: str: The provider's userInfo.nickname, when a link was committed.
        #: The official app uses it to pre-fill its nickname prompt; the player
        #: itself never stores it.
        self.provider_nickname = provider_nickname

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} service_id={self.service_id} "
            f"account_udn={self.account_udn!r} at {hex(id(self))}>"
        )


class _SystemPropertiesFault(Exception):
    """Internal representation of a player-side SystemProperties fault."""

    def __init__(
        self,
        action,
        http_status,
        code="",
        message="",
        detail=None,
        upnp_code=None,
        upnp_description="",
    ):
        self.action = action
        self.http_status = http_status
        self.code = code
        self.message = message
        self.detail = detail
        self.upnp_code = upnp_code
        self.upnp_description = upnp_description
        super().__init__(action, http_status)

    def __str__(self):
        suffix = ""
        if self.upnp_code is not None:
            meaning = (
                self.upnp_description
                or UPNP_ERROR_TEXT.get(self.upnp_code, "")
                or "unspecified UPnP error"
            )
            suffix = f" (UPnP error {self.upnp_code}: {meaning})"
        return (
            f"SystemProperties {self.action} failed with HTTP "
            f"{self.http_status}{suffix}"
        )


class _SystemPropertiesClient:
    """Player-side SystemProperties SOAP client for account management."""

    def __init__(self, device, session=None):
        self.device = device
        self.session = session or requests.Session()

    def call(self, action, fields, timeout=35):
        """POST one SystemProperties action and return the raw response body.

        Args:
            action (str): The action name (eg ``AddOAuthAccountX``).
            fields (dict): The action arguments.
            timeout (float): HTTP timeout in seconds.

        Returns:
            bytes: The SOAP response body.

        Raises:
            _SystemPropertiesFault: On a player rejection, with the embedded
                UPnP error code when the player supplied one.
            MusicServiceException: On a network failure.
        """
        envelope = XML.Element("{%s}Envelope" % SOAP_ENV)
        body = XML.SubElement(envelope, "{%s}Body" % SOAP_ENV)
        operation = XML.SubElement(body, "{%s}%s" % (SYSTEM_PROPERTIES_NS, action))
        for name, value in fields.items():
            XML.SubElement(operation, name).text = str(value)
        payload = XML.tostring(envelope, encoding="utf-8")
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": f'"{SYSTEM_PROPERTIES_NS}#{action}"',
        }
        url = f"http://{self.device.ip_address}:1400{SYSTEM_PROPERTIES_CONTROL_URL}"
        try:
            response = self.session.post(
                url, data=payload, headers=headers, timeout=timeout
            )
        except requests.RequestException as error:
            raise MusicServiceException(
                f"SystemProperties {action} request failed: {error}"
            ) from error
        if response.status_code != 200:
            raise self._fault_from_response(action, response)
        return response.content

    def _fault_from_response(self, action, response):
        content = response.content
        try:
            root = XML.fromstring(content)
        except XML.ParseError:
            preview = content.decode("utf-8", "replace").strip()[:200]
            return _SystemPropertiesFault(action, response.status_code, message=preview)
        fault_nodes = _children(root, "Fault")
        fault = fault_nodes[0] if fault_nodes else root
        upnp_code, upnp_description = _upnp_fault_fields(fault)
        detail_nodes = _children(fault, "detail")
        return _SystemPropertiesFault(
            action,
            response.status_code,
            _child_text(fault, "faultcode") or _child_text(root, "errorCode"),
            _child_text(fault, "faultstring") or _child_text(root, "errorDescription"),
            _element_value(detail_nodes[0]) if detail_nodes else _element_value(fault),
            upnp_code=upnp_code,
            upnp_description=upnp_description,
        )


class MusicServiceAccountManager:
    """Provision and manage one music service's accounts in a household.

    The link flow performs no player mutation until :meth:`commit_link` is
    called; legacy credential services are added directly with
    :meth:`add_credentials`.

    Typical use::

        manager = MusicServiceAccountManager("Spotify", device=speaker)
        link = manager.begin_link()
        # The user opens link.registration_url and authorizes in their browser.
        added = manager.commit_link(link)
        manager.set_nickname(added.account_udn, "Living Room")

    Re-linking passes the existing account's UDN to :meth:`commit_link`'s
    ``replace_account_udn`` so only the credentials are swapped
    (:meth:`replace_account_credentials`) instead of committing a duplicate.
    """

    def __init__(
        self,
        service_name,
        device=None,
        session=None,
        callback_path="sonos://addAccount",
    ):
        """Create a manager for one music service.

        Args:
            service_name (str): The service name, as returned by
                :meth:`MusicService.get_all_music_services_names`.
            device (SoCo, optional): A device in the target household. A device
                returned by :func:`soco.discovery.any_soco` is used when
                omitted.
            session (requests.Session, optional): HTTP session for provider and
                player calls.
            callback_path (str): The ``sonos://`` callback path sent with
                ``getAppLink``. Defaults to ``sonos://addAccount``.
        """
        self.device = device or discovery.any_soco()
        self.music_service = MusicService(service_name, device=self.device)
        self.session = session or requests.Session()
        self.callback_path = callback_path
        self.household_id = self.device.household_id
        self.device_id = self.device.systemProperties.GetString(
            [("VariableName", "R_TrialZPSerial")]
        )["StringValue"]
        self.time_zone = _local_time_zone()
        self.controller_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"soco-music-service-account-manager:"
                f"{self.household_id}:{self.device_id}",
            )
        )
        self._sp = _SystemPropertiesClient(self.device, self.session)
        self._smapi = _ConfiguredSmapiClient(
            self.music_service,
            ConfiguredMusicServiceAccount(int(self.music_service.service_id), 0, ""),
            self.device,
            self.household_id,
            self.device_id,
            self.controller_id,
            self.time_zone,
            session=self.session,
        )

    @property
    def accounts(self):
        """list: This service's configured accounts in the household, including
        keyless records (see :meth:`ConfiguredMusicServiceAccount.get_accounts`).
        """
        return [
            account
            for account in ConfiguredMusicServiceAccount.get_accounts(self.device)
            if account.service_id == int(self.music_service.service_id)
        ]

    # ------------------------------------------------------------------
    # Household helpers
    # ------------------------------------------------------------------

    def _live_household(self):
        return self.device.deviceProperties.GetHouseholdID()["CurrentHouseholdID"]

    def _require_household(self, expected_household):
        """Return the live household, raising if it no longer matches.

        Every mutating operation re-checks the player's current household
        before writing, so a manager created against a household that has
        since changed (or a link created for a different household) fails
        before any account state is touched.
        """
        actual = self._live_household()
        if actual != expected_household:
            raise MusicServiceException(
                f"Target expects {expected_household}, but player "
                f"{self.device.ip_address} belongs to {actual}"
            )
        return actual

    @staticmethod
    def _account_key(service_id, account_udn):
        """Return the account-key identifier the player accepts for edits.

        Edits resolve the account by the key tail after the encoded-type
        prefix; the full ``SA_RINCON...`` UDN is rejected (UPnP 806). Passes
        the UDN through unchanged when the prefix does not match.
        """
        prefix = f"SA_RINCON{account_type(service_id)}_"
        return (
            account_udn[len(prefix) :]
            if account_udn.startswith(prefix)
            else account_udn
        )

    # ------------------------------------------------------------------
    # Link flow
    # ------------------------------------------------------------------

    def begin_link(self, callback_path=None):
        """Ask the provider for its browser/app authorization choices.

        Modern services use ``getAppLink``; older DeviceLink services that
        reject it are retried with ``getDeviceLinkCode``. No player state is
        changed by this method.

        Args:
            callback_path (str, optional): Overrides the manager's callback
                path for this link only.

        Returns:
            AccountLink: The authorization link (or an anonymous placeholder
            for anonymous services, which have no link flow).

        Raises:
            MusicServiceException: If the service uses unsupported auth, uses
                legacy credentials, offers app-to-app linking only, or cannot
                provide a usable authorization path.
        """
        auth = self.music_service.auth_type
        if auth not in AUTH_OPERATIONS:
            raise MusicServiceException(
                f"{self.music_service.service_name} uses unsupported "
                f"authentication type {auth!r}"
            )
        if auth == "Anonymous":
            return AccountLink(
                int(self.music_service.service_id),
                self.music_service.service_name,
                auth,
                self.household_id,
                account_type(int(self.music_service.service_id)),
                "",
                "",
                callback_path=callback_path or self.callback_path,
                source_action="anonymous",
            )
        if AUTH_OPERATIONS[auth] != "AddOAuthAccountX":
            raise MusicServiceException(
                f"{self.music_service.service_name} uses credentials; "
                "call add_credentials instead"
            )

        callback = callback_path or self.callback_path
        app_link_error = None
        try:
            root = self._smapi._request(  # pylint: disable=protected-access
                "getAppLink",
                {
                    "householdId": self.household_id,
                    # Match the installed desktop controller's getAppLink
                    # request so providers select their desktop/browser
                    # authorization path.
                    "hardware": "Windows",
                    "osVersion": "Microsoft Windows NT 10.0.19045 64-bit",
                    "sonosAppName": "Sonos",
                    "callbackPath": callback,
                },
                credential_mode="base",
                bearer_token="",
            )
        except (_BrowseSoapFault, MusicServiceException) as exc:
            # Legacy services commonly reject getAppLink entirely.
            app_link_error = exc
        else:
            value = _result_value(root, "getAppLinkResult")
            session = _link_from_result(
                self.music_service, self.household_id, callback, "getAppLink", value
            )
            # Only AppLink services hit the actionable app-only error: a
            # DeviceLink service returning this stub must still fall back to
            # getDeviceLinkCode.
            if _app_link_only_stub(value) and auth != "DeviceLink":
                raise MusicServiceException(
                    f"{self.music_service.service_name} offers app-to-app "
                    "linking only: getAppLink returned an encrypted app-link "
                    "marker (appUrlEncrypt=true) with no browser URL or link "
                    "code. Providers such as Apple Music restrict initial "
                    "authorization to the Sonos mobile app (iOS/Android); even "
                    "the official Sonos desktop app cannot add them. Link the "
                    "account once from the Sonos phone app, then browse, "
                    "manage, and rename it like any other account."
                )
            if session.standalone_supported or session.app_url or auth != "DeviceLink":
                return session

        if auth != "DeviceLink":
            if app_link_error:
                raise MusicServiceException(
                    f"{self.music_service.service_name} getAppLink failed: "
                    f"{app_link_error}"
                ) from app_link_error
            raise MusicServiceException(
                f"{self.music_service.service_name} returned no usable "
                "authorization path"
            )

        try:
            root = self._smapi._request(  # pylint: disable=protected-access
                "getDeviceLinkCode",
                {"householdId": self.household_id},
                credential_mode="base",
                bearer_token="",
            )
        except (_BrowseSoapFault, MusicServiceException) as exc:
            raise MusicServiceException(
                f"{self.music_service.service_name} supports neither "
                f"getAppLink nor getDeviceLinkCode: {exc}"
            ) from exc
        value = _result_value(root, "getDeviceLinkCodeResult")
        session = _link_from_result(
            self.music_service, self.household_id, callback, "getDeviceLinkCode", value
        )
        if not session.standalone_supported:
            raise MusicServiceException(
                f"{self.music_service.service_name} returned no browser URL "
                "or link code"
            )
        return session

    def get_device_auth_token(self, link):
        """Exchange an authorized link code for the provider credential package.

        The result -- authToken, privateKey, userInfo -- is what
        :meth:`commit_link` installs into the player; the player does not
        exchange the link code itself.

        Args:
            link (AccountLink): The link returned by :meth:`begin_link` whose
                code the user has authorized.

        Returns:
            DeviceAuthCredential: The provider credential package.

        Raises:
            MusicServiceException: If the provider rejects the exchange or
                returns no usable authToken/privateKey pair (eg the code
                expired or was already exchanged).
        """
        try:
            root = self._smapi._request(  # pylint: disable=protected-access
                "getDeviceAuthToken",
                {
                    "householdId": self.household_id,
                    "linkCode": link.link_code,
                    "linkDeviceId": link.link_device_id or self.device_id,
                },
                credential_mode="base",
                bearer_token="",
            )
        except _BrowseSoapFault as fault:
            raise MusicServiceException(
                f"{self.music_service.service_name} getDeviceAuthToken failed: {fault}"
            ) from fault
        value = _result_value(root, "getDeviceAuthTokenResult")
        result = value if isinstance(value, dict) else {}
        user_info = result.get("userInfo", {})
        user_info = user_info if isinstance(user_info, dict) else {}
        token = str(result.get("authToken", "") or "")
        key = str(result.get("privateKey", "") or "")
        if not token or not key:
            raise MusicServiceException(
                f"{self.music_service.service_name} getDeviceAuthToken returned "
                "no authToken/privateKey pair; the link code may have expired "
                "or already been exchanged."
            )
        return DeviceAuthCredential(
            auth_token=token,
            private_key=key,
            user_id_hash_code=str(user_info.get("userIdHashCode", "") or ""),
            # The provider's screen name; the official app pre-fills the
            # account nickname prompt with it (informational only, never sent
            # to the player).
            nickname=str(user_info.get("nickname", "") or ""),
        )

    # ------------------------------------------------------------------
    # Player mutations
    # ------------------------------------------------------------------

    def _call_player(self, action, fields, note="No account state was changed."):
        """POST a player action, translating rejections into a public error.

        The player's faults are always surfaced as
        :class:`MusicServiceException` (with the UPnP error code when the
        player supplied one); the internal fault type never leaks to callers.
        """
        try:
            return self._sp.call(action, fields, timeout=35)
        except _SystemPropertiesFault as fault:
            raise self._translate_upnp_fault(fault, action, note) from fault

    def commit_link(self, link, replace_account_udn=""):
        """Commit an authorized provider link to the household's players.

        A fresh account is installed with ``AddOAuthAccountX``; passing
        ``replace_account_udn`` swaps the credentials in place instead, with
        ``ReplaceAccountX``. The player does not exchange the link code: the
        provider's ``getDeviceAuthToken`` is called first and the resulting
        credential package is wrapped in the household ``2:`` envelope.

        Args:
            link (AccountLink): A link returned by :meth:`begin_link` whose
                code the user has authorized.
            replace_account_udn (str): When given, re-link in place: the
                record keeps this UDN and only the credentials are swapped.

        Returns:
            AddedAccount: The committed account record.

        Raises:
            MusicServiceException: If the link does not match this service or
                household, the provider exchange fails, or the player rejects
                the commit.
        """
        service_id = int(self.music_service.service_id)
        if link.service_id != service_id:
            raise MusicServiceException("Link session belongs to a different service")
        expected_account_type = account_type(service_id)
        if link.account_type != expected_account_type:
            raise MusicServiceException(
                "Link session account type does not match its service"
            )
        if AUTH_OPERATIONS.get(self.music_service.auth_type) != "AddOAuthAccountX":
            raise MusicServiceException(
                f"{self.music_service.service_name} does not use "
                "linked-account onboarding"
            )
        if not link.link_code:
            raise MusicServiceException(
                f"{self.music_service.service_name} did not provide a "
                "standalone link code; its app-only authorization cannot be "
                "committed here"
            )
        household = self._require_household(link.household_id)
        credential = self.get_device_auth_token(link)
        if replace_account_udn:
            # Re-link path: the record keeps its UDN and only the credential
            # package is swapped, exactly like the desktop's per-account
            # replace.
            return self.replace_account_credentials(replace_account_udn, credential)

        user_id_hash = _normalize_user_id_hash(credential.user_id_hash_code)
        encoded_hash = (
            _encrypt_account_payload(user_id_hash.encode("utf-8"), household)
            if user_id_hash
            else ""
        )
        # The privateKey carries its own epoch stamp; envelope it verbatim.
        try:
            response = self._sp.call(
                "AddOAuthAccountX",
                {
                    "AccountType": str(expected_account_type),
                    # Account values must be wrapped in the household 2:
                    # envelope; plaintext values are rejected (UPnP 402).
                    "AccountToken": _encrypt_account_payload(
                        credential.auth_token.encode("utf-8"), household
                    ),
                    "AccountKey": _encrypt_account_payload(
                        credential.private_key.encode("utf-8"), household
                    ),
                    "OAuthDeviceID": _encrypt_account_payload(
                        household.encode("utf-8"), household
                    ),
                    "AuthorizationCode": "",
                    "RedirectURI": "",
                    "UserIdHashCode": encoded_hash,
                    "AccountTier": ACCOUNT_TIER,
                },
                timeout=35,
            )
        except _SystemPropertiesFault as fault:
            translated = self._translate_commit_fault(fault)
            if translated is None:
                # Not a diagnosable duplicate-add: still surface a public
                # error carrying the player's UPnP details.
                translated = self._translate_upnp_fault(
                    fault, "AddOAuthAccountX", "No account state was changed."
                )
            raise translated from fault
        added = _parse_add_response(self.music_service, response, household)
        return AddedAccount(
            added.service_id,
            added.service_name,
            added.account_udn,
            added.nickname,
            provider_nickname=credential.nickname,
        )

    def replace_account_credentials(self, account_udn, credential):
        """Replace one existing account's stored credentials in place.

        This is the re-link path: the record keeps its UDN and only the
        credential package is swapped (``ReplaceAccountX``), so no duplicate
        record is created. A ``2:`` blob ``account_udn`` is decoded first and
        the legacy ID/password fields stay empty for OAuth services.

        Args:
            account_udn (str): The existing account's UDN, either the
                canonical ``SA_RINCON...`` form or the ``2:`` blob returned by
                an add/commit.
            credential (DeviceAuthCredential): The replacement credential
                package.

        Returns:
            AddedAccount: The account record with its UDN unchanged.
        """
        service_id = int(self.music_service.service_id)
        if service_id <= 0:
            raise MusicServiceException(
                f"{self.music_service.service_name} has no usable service ID"
            )
        if not account_udn:
            raise MusicServiceException(
                "An account UDN is required to replace an account"
            )
        if not credential.auth_token or not credential.private_key:
            raise MusicServiceException(
                "A complete credential package is required to replace an account"
            )
        household = self._require_household(self.household_id)
        if account_udn.startswith("2:"):
            account_udn = _decrypt_account_payload(account_udn, household).decode(
                "utf-8"
            )
        self._call_player(
            "ReplaceAccountX",
            {
                "AccountUDN": _encrypt_account_payload(
                    account_udn.encode("utf-8"), household
                ),
                "NewAccountID": "",
                "NewAccountPassword": "",
                "AccountToken": _encrypt_account_payload(
                    credential.auth_token.encode("utf-8"), household
                ),
                "AccountKey": _encrypt_account_payload(
                    credential.private_key.encode("utf-8"), household
                ),
                "OAuthDeviceID": _encrypt_account_payload(
                    household.encode("utf-8"), household
                ),
                "NewAccountUDN": "",
            },
        )
        return AddedAccount(
            service_id,
            self.music_service.service_name,
            account_udn,
            provider_nickname=credential.nickname,
        )

    def add_credentials(self, username="", password=""):
        """Add an anonymous or legacy username/password service account.

        Anonymous descriptors are committed with an empty account ID (the
        player rejects any other value, UPnP 402) and store a keyless record.

        Args:
            username (str): The account username, required for UserId and
                UserIdPassword services.
            password (str): The account password, required for UserIdPassword
                services.

        Returns:
            AddedAccount: The committed account record.
        """
        auth = self.music_service.auth_type
        service_id = int(self.music_service.service_id)
        if auth not in ("Anonymous", "UserId", "UserIdPassword"):
            raise MusicServiceException(
                f"{self.music_service.service_name} requires {auth}; "
                "use begin_link instead"
            )
        if auth in ("UserId", "UserIdPassword") and not username:
            raise MusicServiceException(
                f"{self.music_service.service_name} requires a username"
            )
        if auth == "UserIdPassword" and not password:
            raise MusicServiceException(
                f"{self.music_service.service_name} requires a password"
            )
        self._require_household(self.household_id)
        response = self._call_player(
            "AddAccountX",
            {
                "AccountType": str(account_type(service_id)),
                "AccountID": username,
                "AccountPassword": password,
            },
        )
        return _parse_add_response(self.music_service, response)

    def set_nickname(self, account_udn, nickname):
        """Rename one configured household account.

        Both arguments are wrapped in the household ``2:`` envelope (plaintext
        values are rejected with UPnP 402); a ``2:`` blob ``account_udn`` is
        decoded first so it is never double-encoded.

        Args:
            account_udn (str): The account's UDN (canonical or ``2:`` blob).
            nickname (str): The new nickname.

        Raises:
            MusicServiceException: If the player rejects the rename.
        """
        if not account_udn:
            raise MusicServiceException(
                "An account UDN is required to rename an account"
            )
        household = self._require_household(self.household_id)
        if account_udn.startswith("2:"):
            account_udn = _decrypt_account_payload(account_udn, household).decode(
                "utf-8"
            )
        self._call_player(
            "SetAccountNicknameX",
            {
                "AccountUDN": _encrypt_account_payload(
                    account_udn.encode("utf-8"), household
                ),
                "AccountNickname": _encrypt_account_payload(
                    nickname.encode("utf-8"), household
                ),
            },
        )

    def remove_account(self, account_udn):
        """Remove one configured account from every player in the household.

        Keyless records (truncated UDN) are removed with an empty AccountID
        (``RemoveAccount(type, "")``); the truncated UDN itself is rejected
        with UPnP error 806.

        Args:
            account_udn (str): The account's UDN.
        """
        service_id = int(self.music_service.service_id)
        if service_id <= 0:
            raise MusicServiceException(
                f"{self.music_service.service_name} has no usable service ID"
            )
        if not account_udn:
            raise MusicServiceException(
                "An account UDN is required to remove an account"
            )
        self._require_household(self.household_id)
        prefix = f"SA_RINCON{account_type(service_id)}_"
        key = (
            account_udn[len(prefix) :]
            if account_udn.startswith(prefix)
            else account_udn
        )
        account_id = account_udn if key else ""
        self._call_player(
            "RemoveAccount",
            {
                "AccountType": str(account_type(service_id)),
                "AccountID": account_id,
            },
        )

    def edit_account_password(self, account_udn, new_password):
        """Replace a legacy username/password account's stored password.

        Native contract: EditAccountPasswordX takes AccountType, the account
        key (Username0, the UDN tail after the encoded type) as AccountID,
        and NewAccountPassword.

        Args:
            account_udn (str): The account's UDN.
            new_password (str): The replacement password.

        Raises:
            MusicServiceException: If the service is not UserIdPassword or
                the player rejects the edit.
        """
        service_id = int(self.music_service.service_id)
        if service_id <= 0:
            raise MusicServiceException(
                f"{self.music_service.service_name} has no usable service ID"
            )
        if self.music_service.auth_type != "UserIdPassword":
            raise MusicServiceException(
                f"{self.music_service.service_name} uses "
                f"{self.music_service.auth_type}; EditAccountPasswordX applies "
                "to UserIdPassword services"
            )
        if not new_password:
            raise MusicServiceException(
                f"{self.music_service.service_name} requires a new password"
            )
        if not account_udn:
            raise MusicServiceException("An account UDN is required to edit an account")
        self._require_household(self.household_id)
        self._call_player(
            "EditAccountPasswordX",
            {
                "AccountType": str(account_type(service_id)),
                "AccountID": self._account_key(service_id, account_udn),
                "NewAccountPassword": new_password,
            },
        )

    def edit_account_md(self, account_udn, new_md):
        """Replace the provider metadata blob stored with an account.

        Native contract: EditAccountMd takes AccountType, the account key
        (Username0, the UDN tail after the encoded type) as AccountID, and
        NewAccountMd.

        Args:
            account_udn (str): The account's UDN.
            new_md (str): The replacement provider metadata.
        """
        service_id = int(self.music_service.service_id)
        if service_id <= 0:
            raise MusicServiceException(
                f"{self.music_service.service_name} has no usable service ID"
            )
        if not account_udn:
            raise MusicServiceException("An account UDN is required to edit an account")
        self._require_household(self.household_id)
        self._call_player(
            "EditAccountMd",
            {
                "AccountType": str(account_type(service_id)),
                "AccountID": self._account_key(service_id, account_udn),
                "NewAccountMd": new_md,
            },
        )

    def refresh_account_credentials(self, account_uid, token, key):
        """Push a freshly obtained token/key pair into the stored account record.

        This is the player-side persistence of a reauthorization, distinct
        from ``SmapiClient.refresh_auth_token`` (which asks the provider for a
        fresh token without writing to the player).

        Args:
            account_uid (int): The numeric AccountUID from the account UDN
                (see :attr:`ConfiguredMusicServiceAccount.account_uid`).
            token (str): The replacement token.
            key (str): The replacement key.

        Raises:
            MusicServiceException: If the arguments are incomplete.
        """
        service_id = int(self.music_service.service_id)
        if account_uid <= 0:
            raise MusicServiceException("A positive numeric AccountUID is required")
        if not token or not key:
            raise MusicServiceException(
                "Both a token and a key are required to refresh credentials"
            )
        self._require_household(self.household_id)
        self._call_player(
            "RefreshAccountCredentialsX",
            {
                "AccountType": str(account_type(service_id)),
                "AccountUID": str(account_uid),
                "AccountToken": token,
                "AccountKey": key,
            },
        )

    # ------------------------------------------------------------------
    # Fault translation
    # ------------------------------------------------------------------

    def _translate_commit_fault(self, fault):
        """Turn a player rejection of AddOAuthAccountX into an actionable error.

        A 402 can have several causes, but when the household already holds an
        account for this service a duplicate-add refusal is the most plausible
        one, so point at the existing account. Returns None when the fault
        cannot be explained, so the caller re-raises it unchanged.
        """
        if fault.upnp_code == 402:
            try:
                existing = self.accounts
            except Exception:  # pylint: disable=broad-except
                existing = []
            if existing:
                names = sorted(
                    {
                        account.nickname
                        or account.username
                        or str(account.serial_number)
                        for account in existing
                    }
                )
                return MusicServiceException(
                    f"{self.music_service.service_name} is already linked to "
                    f"this household as {', '.join(map(str, names))}. The player "
                    "most likely rejected the duplicate commit (UPnP error "
                    "402: invalid arguments). Reauthorize the existing account "
                    "in place (ReplaceAccountX) instead of adding a duplicate."
                )
        return None

    def _translate_upnp_fault(self, fault, action, note):
        """Return an actionable MusicServiceException for a player rejection."""
        if fault.upnp_code is not None:
            meaning = (
                fault.upnp_description
                or UPNP_ERROR_TEXT.get(fault.upnp_code, "")
                or "unspecified UPnP error"
            )
            message = (
                f"The player rejected {action} for the account (UPnP error "
                f"{fault.upnp_code}: {meaning}). {note}"
            )
            if fault.upnp_code == 802:
                message += (
                    " The household has reached its connected-service limit; "
                    "remove an unused account first, then retry."
                )
            return MusicServiceException(message)
        return MusicServiceException(
            f"The player rejected {action} (HTTP {fault.http_status}): {fault.message}"
        )


def _result_value(root, name):
    """Return the parsed dict value of a SMAPI ``<name>`` result element."""
    nodes = _children(root, name)
    return _element_value(nodes[0] if nodes else root)


def _link_from_result(music_service, household_id, callback_path, action, value):
    """Build an AccountLink from a provider getAppLink/getDeviceLinkCode value."""
    result = value if isinstance(value, dict) else {}
    authorize = result.get("authorizeAccount", result)
    authorize = authorize if isinstance(authorize, dict) else {}
    device_link = authorize.get("deviceLink", authorize)
    device_link = device_link if isinstance(device_link, dict) else {}
    app_url = str(authorize.get("appUrl", result.get("appUrl", "")) or "")
    return AccountLink(
        int(music_service.service_id),
        music_service.service_name,
        music_service.auth_type,
        household_id,
        account_type(int(music_service.service_id)),
        str(device_link.get("regUrl", "") or ""),
        str(device_link.get("linkCode", "") or ""),
        link_device_id=str(device_link.get("linkDeviceId", "") or ""),
        callback_path=callback_path,
        app_url=app_url,
        show_link_code=str(device_link.get("showLinkCode", "")).lower() == "true",
        source_action=action,
    )


def _app_link_only_stub(value):
    """Detect a provider's encrypted app-link marker with no browser path.

    Apple Music's getAppLink returns only ``appUrlEncrypt=true`` with no
    appUrl, regUrl, or linkCode: app-to-app linking only, with no standalone
    browser authorization to open and commit.
    """
    if not isinstance(value, dict):
        return False
    authorize = value.get("authorizeAccount", value)
    authorize = authorize if isinstance(authorize, dict) else {}
    device_link = authorize.get("deviceLink", authorize)
    device_link = device_link if isinstance(device_link, dict) else {}
    has_browser_path = bool(device_link.get("regUrl") or device_link.get("linkCode"))
    has_app_url = bool(authorize.get("appUrl") or value.get("appUrl"))
    encrypted = (
        str(authorize.get("appUrlEncrypt", value.get("appUrlEncrypt", ""))).lower()
        == "true"
    )
    return encrypted and not has_browser_path and not has_app_url


def _normalize_user_id_hash(user_id_hash_code):
    """Return the player's required base64 form of the user-id hash.

    The player accepts ``UserIdHashCode`` only in base64; a 32-character hex
    value (as the provider currently returns) is converted, and any other
    form passes through unchanged.
    """
    value = user_id_hash_code.strip()
    if re.fullmatch(r"[0-9a-fA-F]{32}", value):
        return base64.b64encode(bytes.fromhex(value)).decode("ascii")
    return value


def _upnp_fault_fields(root):
    """Extract the numeric UPnP errorCode/errorDescription from a fault.

    The generic faultstring (``UPnPError``) hides the actual failure; the
    meaningful value lives in ``<detail><UPnPError><errorCode>`` on every
    player fault that has been observed. A missing/unnumbered detail yields
    ``(None, "")``.
    """
    for upnp_error in _children(root, "UPnPError"):
        code_text = _child_text(upnp_error, "errorCode").strip()
        if code_text.isdigit():
            return int(code_text), _child_text(upnp_error, "errorDescription").strip()
    return None, ""


def _parse_add_response(music_service, response, household_id=""):
    """Parse the player's AddAccountX/AddOAuthAccountX response.

    The player returns the AccountUDN in the household ``2:`` envelope (the
    same envelope as ThirdPartyMediaServersX). With the household ID known the
    UDN is decrypted to its canonical ``SA_RINCON...`` form so it matches the
    account inventory; without it the raw value is preserved.
    """
    root = XML.fromstring(response)
    udn_nodes = _children(root, "AccountUDN")
    nickname_nodes = _children(root, "AccountNickname")
    udn = (udn_nodes[0].text or "").strip() if udn_nodes else ""
    if not udn:
        raise MusicServiceException(
            "Player reported success but returned no AccountUDN"
        )
    if udn.startswith("2:") and household_id:
        udn = _decrypt_account_payload(udn, household_id).decode("utf-8")
    return AddedAccount(
        int(music_service.service_id),
        music_service.service_name,
        udn,
        (nickname_nodes[0].text or "").strip() if nickname_nodes else "",
    )
