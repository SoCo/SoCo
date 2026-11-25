"""SMAPI transport for configured household accounts."""

from __future__ import unicode_literals

import json
import re
from collections.abc import Mapping

import requests

from ...exceptions import MusicServiceAuthException, MusicServiceException
from ...xml import XML
from .util import (
    DESKTOP_USER_AGENT,
    SMAPI_NS,
    SOAP_ENV,
    _artwork_uri,
    _as_mapping,
    _child_text,
    _children,
    _element_value,
    _legacy_item_kind,
    _local_name,
)


class _ConfiguredSmapiClient:
    """SMAPI client using credentials already stored in the Sonos household."""

    def __init__(
        self,
        music_service,
        account,
        device,
        household_id,
        device_id,
        controller_id,
        time_zone,
        explicit_content=False,
        allow_credential_refresh=True,
        session=None,
    ):
        self.music_service = music_service
        self.account = account
        self.device = device
        self.household_id = household_id
        self.device_id = device_id
        self.controller_id = controller_id
        self.time_zone = time_zone
        self.explicit_content = explicit_content
        self.allow_credential_refresh = allow_credential_refresh
        self.session_id = ""
        self.session = session or requests.Session()

    @property
    def capabilities(self):
        """Return the provider capability bitmask."""
        return int(self.music_service.capabilities)

    def _credentials(self, parent, mode="normal"):
        """Append credentials for the selected authentication mode."""
        credentials = XML.SubElement(parent, "{%s}credentials" % SMAPI_NS)
        if self.capabilities & (1 << 18) and self.device.uid:
            XML.SubElement(credentials, "{%s}zonePlayerId" % SMAPI_NS).text = (
                self.device.uid
            )
        XML.SubElement(credentials, "{%s}deviceId" % SMAPI_NS).text = self.device_id
        XML.SubElement(credentials, "{%s}deviceProvider" % SMAPI_NS).text = "Sonos"

        if mode == "base" or self.music_service.auth_type == "Anonymous":
            return

        if mode == "normal" and self.music_service.auth_type in (
            "UserId",
            "UserIdPassword",
        ):
            login = XML.SubElement(credentials, "{%s}login" % SMAPI_NS)
            XML.SubElement(login, "{%s}username" % SMAPI_NS).text = (
                self.account.username
            )
            XML.SubElement(login, "{%s}password" % SMAPI_NS).text = (
                self.account.password
            )
            return

        # Auth=DeviceLink describes how an account is provisioned. Once Sonos
        # has stored Token0/Key0, the desktop controller browses with that pair
        # like an AppLink account. getSessionId is only the no-token fallback.
        if mode == "normal" and self.account.token:
            login_token = XML.SubElement(credentials, "{%s}loginToken" % SMAPI_NS)
            if not (self.capabilities & 8):
                XML.SubElement(login_token, "{%s}token" % SMAPI_NS).text = (
                    self.account.token
                )
                if self.account.key:
                    XML.SubElement(login_token, "{%s}key" % SMAPI_NS).text = (
                        self.account.key
                    )
            XML.SubElement(login_token, "{%s}householdId" % SMAPI_NS).text = (
                self.household_id
            )
            return

        if mode == "normal" and self.music_service.auth_type == "DeviceLink":
            if self.session_id:
                XML.SubElement(credentials, "{%s}sessionId" % SMAPI_NS).text = (
                    self.session_id
                )
            return

        if self.account.token or self.household_id:
            login_token = XML.SubElement(credentials, "{%s}loginToken" % SMAPI_NS)
            # Capability bit 3 moves the normal token into an HTTP Bearer
            # header. refreshAuthToken is the exception: the old token/key go
            # back into SOAP even when that capability is present.
            if not (self.capabilities & 8) or mode == "refresh":
                if self.account.token:
                    XML.SubElement(login_token, "{%s}token" % SMAPI_NS).text = (
                        self.account.token
                    )
                if self.account.key:
                    XML.SubElement(login_token, "{%s}key" % SMAPI_NS).text = (
                        self.account.key
                    )
            XML.SubElement(login_token, "{%s}householdId" % SMAPI_NS).text = (
                self.household_id
            )

    def _envelope(self, action, fields, credential_mode="normal"):
        envelope = XML.Element("{%s}Envelope" % SOAP_ENV)
        header = XML.SubElement(envelope, "{%s}Header" % SOAP_ENV)
        self._credentials(header, mode=credential_mode)

        # The desktop app keys SMAPI context inclusion from capability bit 16.
        if self.capabilities & (1 << 16):
            context = XML.SubElement(header, "{%s}context" % SMAPI_NS)
            XML.SubElement(context, "{%s}timeZone" % SMAPI_NS).text = self.time_zone
            if self.capabilities & (1 << 21) and self.explicit_content:
                filtering = XML.SubElement(context, "{%s}contentFiltering" % SMAPI_NS)
                XML.SubElement(filtering, "{%s}explicit" % SMAPI_NS).text = "true"

        body = XML.SubElement(envelope, "{%s}Body" % SOAP_ENV)
        operation = XML.SubElement(body, "{%s}%s" % (SMAPI_NS, action))
        for name, value in fields.items():
            XML.SubElement(operation, "{%s}%s" % (SMAPI_NS, name)).text = str(value)
        return XML.tostring(envelope, encoding="utf-8")

    def _request(self, action, fields, credential_mode="normal", bearer_token=None):
        endpoint = self.music_service.secure_uri
        if not endpoint.lower().startswith("https://"):
            raise MusicServiceException(f"SMAPI endpoint must use HTTPS: {endpoint}")

        current_bearer = self.account.token if bearer_token is None else bearer_token
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "Soapaction": f'"{SMAPI_NS}#{action}"',
            "Accept-Language": "en-US",
            "X-Sonos-Controller-ID": self.controller_id,
            "User-Agent": DESKTOP_USER_AGENT,
        }
        if credential_mode != "refresh" and self.capabilities & 8 and current_bearer:
            headers["Authorization"] = f"Bearer {current_bearer}"

        try:
            response = self.session.post(
                endpoint,
                data=self._envelope(action, fields, credential_mode),
                headers=headers,
                timeout=20,
            )
        except requests.RequestException as error:
            raise MusicServiceException(
                f"{self.music_service.service_name} request failed: {error}"
            ) from error

        payload = response.content
        try:
            root = XML.fromstring(payload)
        except XML.ParseError as error:
            # Sonos Radio has returned xsi:nil without declaring the xsi prefix.
            # The desktop parser tolerates that specific provider defect, so
            # repair only that case before treating the response as corrupt.
            repaired = payload
            if b"xsi:" in payload and b"xmlns:xsi" not in payload:
                repaired = re.sub(
                    rb"(<(?:[A-Za-z_][\w.-]*:)?Envelope)(\s)",
                    rb'\1 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\2',
                    payload,
                    count=1,
                )
            if repaired == payload:
                raise self._non_xml_response_error(
                    payload, response.status_code
                ) from error
            try:
                root = XML.fromstring(repaired)
            except XML.ParseError as repaired_error:
                raise self._non_xml_response_error(
                    payload, response.status_code
                ) from repaired_error

        faults = _children(root, "Fault")
        if faults:
            fault = faults[0]
            detail_nodes = _children(fault, "detail")
            detail = _element_value(detail_nodes[0]) if detail_nodes else None
            raise _BrowseSoapFault(
                _child_text(fault, "faultcode", "SMAPI.Fault"),
                _child_text(fault, "faultstring", "Unknown SMAPI fault"),
                response.status_code,
                detail,
            )
        if response.status_code != 200:
            raise _BrowseSoapFault(
                "HTTP",
                f"Unexpected status {response.status_code}",
                response.status_code,
            )
        return root

    @staticmethod
    def _is_expired_fault(fault):
        combined = f"{fault.code} {fault.message}".lower()
        return (
            "authtokenexpired" in combined
            or "invalidtoken" in combined
            or "tokenrefreshrequired" in combined
            or "token expired" in combined
            or "unauthorized" in combined
            or fault.http_status == 401
        )

    def _non_xml_response_error(self, payload, status_code):
        """Return the right exception for a response that is not XML.

        A few providers answer with plain text instead of a SOAP envelope;
        Sonos Radio, for example, responds ``Unauthorized`` when the token it
        was given is not usable.  Surfacing that as an auth-flavored fault
        gives a truthful error and lets the credential-refresh flow run.
        """
        stripped = payload.strip()
        if stripped and not stripped.startswith(b"<"):
            text = stripped.decode("utf-8", "replace")[:200]
            return _BrowseSoapFault("HTTP", text, status_code)
        return MusicServiceException(
            f"{self.music_service.service_name} returned malformed SMAPI XML"
        )

    @staticmethod
    def _is_invalid_session_fault(fault):
        combined = f"{fault.code} {fault.message}".lower()
        return "invalidsession" in combined or "invalid session" in combined

    @staticmethod
    def _is_transient_fault(fault):
        combined = f"{fault.code} {fault.message}".lower()
        provider_detail = (
            json.dumps(fault.detail, sort_keys=True).lower()
            if fault.detail is not None
            else ""
        )
        # Apple intermittently returns generic SonosError 999 for a valid
        # collection and succeeds immediately on the identical request.
        provider_retry = '"sonoserror": "999"' in provider_detail
        return (
            provider_retry
            or fault.http_status in {408, 429, 502, 503, 504}
            or any(
                marker in combined
                for marker in (
                    "read timed out",
                    "timed out reading",
                    "temporarily unavailable",
                    "try again",
                )
            )
        )

    @staticmethod
    def _replacement_credentials(detail):
        if isinstance(detail, Mapping):
            token = detail.get("authToken")
            key = detail.get("privateKey")
            if isinstance(token, str) and isinstance(key, str) and token and key:
                return token, key
            for child in detail.values():
                replacement = _ConfiguredSmapiClient._replacement_credentials(child)
                if replacement:
                    return replacement
        elif isinstance(detail, list):
            for child in detail:
                replacement = _ConfiguredSmapiClient._replacement_credentials(child)
                if replacement:
                    return replacement
        return None

    def _replace_credentials(self, token, key):
        self.account.token = token
        self.account.key = key
        self.session_id = ""

    def refresh_auth_token(self):
        """Refresh browse credentials in memory without writing the player.

        The desktop controller updates its active account model here; it does
        not call ``RefreshAccountCredentialsX`` on the Sonos player. Credential
        refresh is enabled by default on :class:`MusicServiceBrowser` because
        expired tokens are the common failure mode when browsing; pass
        ``allow_credential_refresh=False`` to opt out. It is not a pure
        metadata read from the provider.
        """
        if self.account.token == "needs_reauth":
            raise MusicServiceAuthException(
                "The Sonos household stores needs_reauth instead of a usable token"
            )
        root = self._request(
            "refreshAuthToken", {}, credential_mode="refresh", bearer_token=""
        )
        result_nodes = _children(root, "refreshAuthTokenResult")
        result = result_nodes[0] if result_nodes else root
        token = _child_text(result, "authToken")
        key = _child_text(result, "privateKey")
        if not token or not key:
            raise MusicServiceAuthException(
                "refreshAuthToken returned no authToken/privateKey pair"
            )
        self._replace_credentials(token, key)

    def _refresh_from_fault(self, fault):
        if self.capabilities & 8:
            self.refresh_auth_token()
            return
        replacement = self._replacement_credentials(fault.detail)
        if replacement:
            self._replace_credentials(*replacement)
            return
        self.refresh_auth_token()

    def get_session_id(self):
        """Obtain the legacy DeviceLink session used when no token is stored."""
        if self.music_service.auth_type != "DeviceLink":
            raise MusicServiceAuthException(
                "getSessionId is only valid for DeviceLink services"
            )
        root = self._request(
            "getSessionId",
            {
                "username": self.account.username,
                "password": self.account.password,
            },
            credential_mode="base",
        )
        results = _children(root, "getSessionIdResult")
        session_id = (results[0].text or "").strip() if results else ""
        if not session_id:
            raise MusicServiceAuthException(
                "getSessionId response did not contain a session ID"
            )
        self.session_id = session_id

    def _ensure_session(self):
        if (
            self.music_service.auth_type == "DeviceLink"
            and not self.account.token
            and not self.session_id
        ):
            self.get_session_id()

    def _request_with_refresh(self, action, fields):
        if self.account.token == "needs_reauth":
            raise MusicServiceAuthException(
                "The Sonos household stores needs_reauth instead of a usable token"
            )
        self._ensure_session()
        try:
            return self._request(action, fields)
        except _BrowseSoapFault as fault:
            if (
                self.music_service.auth_type == "DeviceLink"
                and self._is_invalid_session_fault(fault)
            ):
                self.session_id = ""
                self._ensure_session()
                return self._request(action, fields)
            if (
                self.music_service.auth_type == "Anonymous"
                or not self._is_expired_fault(fault)
            ):
                raise
            if not self.allow_credential_refresh:
                raise
            self._refresh_from_fault(fault)
            self._ensure_session()
            return self._request(action, fields)

    def get_metadata(
        self,
        object_id="root",
        index=0,
        count=100,
        recursive=False,
        sort_order=None,
        sort_ascending=None,
    ):
        """Return one page of provider metadata records."""
        fields = {"id": object_id, "index": str(index), "count": str(count)}
        if recursive:
            fields["recursive"] = "true"
        if sort_order:
            fields["sortOrder"] = str(sort_order)
        if sort_ascending is not None:
            fields["sortAscending"] = "true" if sort_ascending else "false"

        for attempt in range(3):
            try:
                root = self._request_with_refresh("getMetadata", fields)
                break
            except _BrowseSoapFault as fault:
                if attempt == 2 or not self._is_transient_fault(fault):
                    if self._is_expired_fault(fault):
                        raise MusicServiceAuthException(str(fault)) from fault
                    raise fault.as_music_service_exception() from fault
        else:  # pragma: no cover - both retry exits are explicit
            raise MusicServiceException("getMetadata retry exhausted")

        results = _children(root, "getMetadataResult")
        result = results[0] if results else root
        records = []
        for node in result:
            provider_kind = _local_name(node.tag)
            if provider_kind not in ("mediaCollection", "mediaMetadata"):
                continue
            record = _as_mapping(_element_value(node))
            if not record:
                continue
            record = dict(record)
            record["provider_kind"] = provider_kind
            record["kind"] = _legacy_item_kind(provider_kind, record)
            record["album_art_uri"] = _artwork_uri(record)
            records.append(record)

        return {
            "index": int(_child_text(result, "index", str(index))),
            "count": int(_child_text(result, "count", str(len(records)))),
            "total": int(_child_text(result, "total", str(len(records)))),
            "items": records,
        }

    def search(self, category_id, term, index=0, count=100):
        """Search a provider category and return normalized records."""
        count = min(count, max(0, 1000 - index))
        try:
            root = self._request_with_refresh(
                "search",
                {
                    "id": category_id,
                    "term": term,
                    "index": str(index),
                    "count": str(count),
                },
            )
        except _BrowseSoapFault as fault:
            if self._is_expired_fault(fault):
                raise MusicServiceAuthException(str(fault)) from fault
            raise fault.as_music_service_exception() from fault
        results = _children(root, "searchResult")
        result = results[0] if results else root
        records = []
        for node in result:
            provider_kind = _local_name(node.tag)
            if provider_kind not in ("mediaCollection", "mediaMetadata"):
                continue
            record = _as_mapping(_element_value(node))
            if not record:
                continue
            record = dict(record)
            record["provider_kind"] = provider_kind
            record["kind"] = _legacy_item_kind(provider_kind, record)
            record["album_art_uri"] = _artwork_uri(record)
            records.append(record)
        return {
            "index": index,
            "count": int(_child_text(result, "count", str(len(records)))),
            "total": min(1000, int(_child_text(result, "total", str(len(records))))),
            "items": records,
        }

    def get_media_metadata(self, object_id):
        """Return provider metadata for one item id."""
        try:
            root = self._request_with_refresh("getMediaMetadata", {"id": object_id})
        except _BrowseSoapFault as fault:
            if self._is_expired_fault(fault):
                raise MusicServiceAuthException(str(fault)) from fault
            raise fault.as_music_service_exception() from fault
        results = _children(root, "getMediaMetadataResult")
        if not results:
            raise MusicServiceException(
                "getMediaMetadata response did not contain a result"
            )
        value = _element_value(results[0])
        mapping = _as_mapping(value)
        if mapping:
            result = dict(mapping)
            result["album_art_uri"] = _artwork_uri(result)
            return result
        return {"value": value}

    def get_extended_metadata(self, object_id):
        """Return related items and text for one item."""
        try:
            root = self._request_with_refresh("getExtendedMetadata", {"id": object_id})
        except _BrowseSoapFault as fault:
            if self._is_expired_fault(fault):
                raise MusicServiceAuthException(str(fault)) from fault
            raise fault.as_music_service_exception() from fault
        results = _children(root, "getExtendedMetadataResult")
        if not results:
            raise MusicServiceException(
                "getExtendedMetadata response did not contain a result"
            )
        result = results[0]
        records = []
        text_entries = []
        for child in result:
            name = _local_name(child.tag)
            if name == "mediaCollection":
                for node in child:
                    provider_kind = _local_name(node.tag)
                    if provider_kind == "relatedText":
                        text_entries.append(
                            {
                                "type": _child_text(node, "type"),
                                "text": _child_text(node, "text"),
                            }
                        )
                    elif provider_kind in ("mediaCollection", "mediaMetadata"):
                        record = _as_mapping(_element_value(node))
                        if not record:
                            continue
                        record = dict(record)
                        record["provider_kind"] = provider_kind
                        record["kind"] = _legacy_item_kind(provider_kind, record)
                        record["album_art_uri"] = _artwork_uri(record)
                        records.append(record)
            elif name == "relatedText":
                text_entries.append(
                    {
                        "type": _child_text(child, "type"),
                        "text": _child_text(child, "text"),
                    }
                )
            elif name.startswith("related"):
                # Provider-specific related items (eg Apple's relatedPlay radio).
                record = _as_mapping(_element_value(child))
                if not record:
                    continue
                record = dict(record)
                record["provider_kind"] = "mediaMetadata"
                record["kind"] = _legacy_item_kind("mediaMetadata", record)
                record["album_art_uri"] = _artwork_uri(record)
                records.append(record)
        return {
            "items": records,
            "text": text_entries,
            "raw": _as_mapping(_element_value(result)),
        }

    def get_last_update(self):
        """Return catalog/favorites change timestamps from the provider."""
        try:
            root = self._request_with_refresh("getLastUpdate", {})
        except _BrowseSoapFault as fault:
            if self._is_expired_fault(fault):
                raise MusicServiceAuthException(str(fault)) from fault
            raise fault.as_music_service_exception() from fault
        results = _children(root, "getLastUpdateResult")
        if not results:
            raise MusicServiceException(
                "getLastUpdate response did not contain a result"
            )
        value = _as_mapping(_element_value(results[0]))
        return dict(value) if value else {"value": value}

    def get_scroll_indices(self, object_id):
        """Return the scroll index entries for one container.

        Providers use this to build alphabetical jump bars: the response lists
        the position and identity of the jump-point items in the container's
        sorted order. Entries are kept in the provider's own shape.
        """
        try:
            root = self._request_with_refresh("getScrollIndices", {"id": object_id})
        except _BrowseSoapFault as fault:
            if self._is_expired_fault(fault):
                raise MusicServiceAuthException(str(fault)) from fault
            raise fault.as_music_service_exception() from fault
        results = _children(root, "getScrollIndicesResult")
        result = results[0] if results else root
        entries = []
        total = None
        for child in result:
            name = _local_name(child.tag)
            if name == "index":
                value = _as_mapping(_element_value(child))
                if value:
                    entries.append(dict(value))
                else:
                    entries.append({"index": (child.text or "").strip()})
            elif name in ("total", "count") and (child.text or "").strip().isdigit():
                total = int(child.text.strip())
        return {"total": total, "indices": entries}

    def set_played_seconds(self, object_id, seconds):
        """Report listening progress for one item back to the provider.

        ``seconds`` is the number of seconds played so far; services that
        track progress (podcasts, audiobooks) use it to resume playback.
        """
        try:
            self._request_with_refresh(
                "setPlayedSeconds", {"id": object_id, "seconds": str(int(seconds))}
            )
        except _BrowseSoapFault as fault:
            if self._is_expired_fault(fault):
                raise MusicServiceAuthException(str(fault)) from fault
            raise fault.as_music_service_exception() from fault


class _BrowseSoapFault(Exception):
    """Internal representation of a provider SOAP fault."""

    def __init__(self, code, message, http_status, detail=None):
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail
        super().__init__(code, message, http_status)

    def __str__(self):
        return f"{self.code}: {self.message} (HTTP {self.http_status})"

    def as_music_service_exception(self):
        """Return the appropriate existing public SoCo exception."""
        combined = f"{self.code} {self.message}".lower()
        if (
            "token" in combined
            or "authorization" in combined
            or "unauthorized" in combined
            or self.http_status == 401
        ):
            return MusicServiceAuthException(str(self))
        return MusicServiceException(str(self))
