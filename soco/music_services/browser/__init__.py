"""Account-aware browsing of configured Sonos music services.

The older :class:`soco.music_services.music_service.MusicService` API
remains unchanged; this package implements the desktop controller's newer
account-aware browse flow alongside it. Account state is never mutated
here: this package does not add, remove, rename, or authorize
music-service accounts (see :mod:`soco.music_services.onboarding` for
that).

Playback is resolved by the player, never by this package:
:meth:`~MusicServiceBrowser.play` builds the player-resolved URI and DIDL
metadata for a browsed item (track, stream, program, show or audiobook) and
hands them to :meth:`SoCo.play_uri`. :meth:`~MusicServiceBrowser.sonos_uri_from_id`
exposes the lower-level ``x-sonosapi-stream:`` URI for services whose radio
streams resolve that scheme.

Playing favorites and containers: favorites store a res URI. Pure radio
URIs (``x-sonosapi-stream:``, ``x-rincon-mp3radio:``, …) and track URIs
(``x-sonos-http:``) can be handed straight to a player; container URIs
(``x-rincon-cpcontainer:``) cannot be played raw - decode the embedded
item id (percent-decode, strip the 8-hex service prefix and any
``#fragment``), then browse to a track with :meth:`~MusicServiceBrowser.get_metadata`
and play that. Track URIs carry signed URLs that expire; re-resolving the
embedded id through the player is the reliable fallback.

A favorite remembers the account it was saved from: the ``cdudn`` in its
reference carries the account UID that appears in the account UDN
(``SA_RINCON…-<uid>-Token``). That account can later disappear or break
(it is removed, re-authorized, or its provider starts rejecting playback
with ``LoginDisabled``). A client should detect when a favorite's account
is missing or broken and prompt the user to switch the favorite to a
different configured account, rather than guessing which one to use.
"""

from __future__ import unicode_literals

import logging
import uuid
from collections.abc import Mapping
from urllib.parse import quote as quote_url

import requests

from ... import discovery
from ...exceptions import MusicServiceAuthException, MusicServiceException
from ..music_service import MusicService
from .catalog import (
    _fetch_presentation_map,
    _fetch_string_tables,
    _resolve_strings_uri,
    PresentationMap,
    StringTables,
)
from .content import (
    _content_endpoint,
    _content_headers,
    _content_item,
    _service_manifest,
)
from .credentials import (
    _account_content_device_id,
    _local_time_zone,
    ConfiguredMusicServiceAccount,
)
from .models import _legacy_item, MusicServiceBrowseItem, MusicServiceBrowseResult
from .playback import build_metadata, build_uri, resolve_item
from .transport import _ConfiguredSmapiClient
from .util import _as_list, _as_mapping, _as_string

# Names re-exported for callers which import this package as a module.
from .credentials import (  # noqa: F401
    _ACCOUNT_SALT,
    _capture_account_event,
    _decrypt_account_payload,
    _encrypt_account_payload,
    _aes_128_cbc_decrypt,
    _aes_128_cbc_encrypt,
)
from .transport import _BrowseSoapFault  # noqa: F401
from .util import (  # noqa: F401
    DESKTOP_USER_AGENT,
    SMAPI_NS,
    SOAP_ENV,
    _artwork_uri,
    _child_text,
    _children,
    _element_value,
    _explicit_bool,
    _legacy_item_kind,
    _local_name,
)

_LOG = logging.getLogger(__name__)


class MusicServiceBrowser:
    """Browse one configured music-service account without changing it.

    The existing :class:`MusicService` API remains the primary legacy SMAPI
    implementation. This class is an opt-in companion for applications which
    need to browse the accounts already configured by the Sonos controller,
    including services which use the newer manifest/content home page.

    Typical use::

        browser = MusicServiceBrowser("Apple Music", device=speaker)
        root = browser.get_metadata()
        child = browser.get_metadata(root.items[0])

    If more than one account for the service is configured, pass the desired
    :class:`ConfiguredMusicServiceAccount` explicitly.
    """

    def __init__(
        self,
        service_name,
        account=None,
        device=None,
        allow_credential_refresh=True,
        explicit_content=False,
        time_zone=None,
        session=None,
    ):
        self.device = device or discovery.any_soco()
        self.music_service = MusicService(service_name, device=self.device)
        self.session = session or requests.Session()
        self.account = account or self._single_configured_account()
        if self.account.service_id != int(self.music_service.service_id):
            raise MusicServiceException(
                f"Account belongs to service {self.account.service_id}, not "
                f"{self.music_service.service_id}"
            )

        self.allow_credential_refresh = allow_credential_refresh
        self.explicit_content = explicit_content
        self.time_zone = time_zone or _local_time_zone()
        self.device_id = self.device.systemProperties.GetString(
            [("VariableName", "R_TrialZPSerial")]
        )["StringValue"]
        self.controller_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"soco-music-service-browser:"
                f"{self.device.household_id}:{self.device_id}",
            )
        )
        self._client = self._make_client(self.device.household_id)
        self._manifest = None
        self._presentation_map = None
        self._strings = None
        self._content_endpoint = self._find_content_endpoint()
        self._content_views = {}

    @classmethod
    def get_accounts(cls, device=None, timeout=8):
        """Return configured accounts without constructing a browser."""
        return ConfiguredMusicServiceAccount.get_accounts(device, timeout)

    def _single_configured_account(self):
        accounts = [
            account
            for account in ConfiguredMusicServiceAccount.get_accounts(self.device)
            if account.service_id == int(self.music_service.service_id)
        ]
        if len(accounts) == 1:
            return accounts[0]
        if len(accounts) > 1:
            raise MusicServiceAuthException(
                f"Multiple {self.music_service.service_name} accounts are "
                "configured; pass an account explicitly"
            )
        if self.music_service.auth_type == "Anonymous":
            return ConfiguredMusicServiceAccount(self.music_service.service_id, 0, "")
        raise MusicServiceAuthException(
            f"No configured {self.music_service.service_name} account "
            "was found in this household"
        )

    def _make_client(self, household_id):
        return _ConfiguredSmapiClient(
            self.music_service,
            self.account,
            self.device,
            household_id,
            self.device_id,
            self.controller_id,
            self.time_zone,
            self.explicit_content,
            self.allow_credential_refresh,
            self.session,
        )

    def _find_content_endpoint(self):
        if not self.music_service.manifest_uri:
            return ""
        try:
            return _content_endpoint(
                self.music_service, self.session, manifest=self.get_manifest()
            )
        except MusicServiceException:
            # A manifest is optional browse metadata. If it does not advertise
            # a usable browse endpoint, preserve legacy SMAPI as the fallback.
            _LOG.debug(
                "%s has no usable content browse endpoint",
                self.music_service.service_name,
                exc_info=True,
            )
            return ""

    @property
    def root_transport(self):
        """str: ``'content'`` for a manifest home page, otherwise ``'smapi'``."""
        return "content" if self._content_endpoint else "smapi"

    @property
    def available_search_categories(self):
        """Delegate search-category discovery to the existing MusicService API."""
        return self.music_service.available_search_categories

    @property
    def available_search_variants(self):
        """Delegate search-variant discovery to the existing MusicService API."""
        return self.music_service.available_search_variants

    @property
    def service_name(self):
        """str: The service name."""
        return self.music_service.service_name

    @property
    def service_id(self):
        """The Sonos service id from the descriptor."""
        return self.music_service.service_id

    @property
    def service_type(self):
        """str: The Sonos service type."""
        return self.music_service.service_type

    @property
    def auth_type(self):
        """str: The auth type (Anonymous, UserId, DeviceLink, AppLink)."""
        return self.music_service.auth_type

    @property
    def capabilities(self):
        """The descriptor capability flags."""
        return self.music_service.capabilities

    @property
    def version(self):
        """str: The descriptor version."""
        return self.music_service.version

    @property
    def container_type(self):
        """str: The descriptor container type."""
        return self.music_service.container_type

    @property
    def uri(self):
        """str: The (insecure) SMAPI endpoint."""
        return self.music_service.uri

    @property
    def secure_uri(self):
        """str: The HTTPS SMAPI endpoint."""
        return self.music_service.secure_uri

    @property
    def presentation_map_uri(self):
        """str: The presentation-map URI, if advertised."""
        return self.music_service.presentation_map_uri

    @property
    def manifest_uri(self):
        """str: The manifest URI, if advertised."""
        return self.music_service.manifest_uri

    @property
    def strings_uri(self):
        """str: The strings-document URI, if advertised.

        Resolved from the descriptor's ``StringsUri`` when present, and
        otherwise from the manifest's ``strings.uri`` entry.
        """
        return _resolve_strings_uri(self.music_service, self.get_manifest())

    def get_manifest(self):
        """Return the service JSON manifest, fetching and caching it in memory.

        The manifest is already downloaded during construction whenever the
        service advertises one (it decides the content browse transport), so
        this normally costs nothing extra.  Services without a manifest return
        an empty dict.

        Returns:
            dict: The parsed manifest document.
        """
        if self._manifest is None:
            self._manifest = _service_manifest(self.music_service, self.session)
        return self._manifest

    @property
    def manifest_data(self):
        """dict: The parsed service manifest, fetched and cached on demand.

        Mirrors the attribute of the same name on :class:`MusicService`.
        """
        return self.get_manifest()

    def get_presentation_map(self):
        """Return the service presentation map, fetching and caching it in memory.

        The presentation map is the XML document which defines search
        categories and variants, display types, artwork/icon size maps and
        provider badges.  Its URI is taken from the descriptor's
        ``PresentationMapUri`` when advertised, and otherwise from the JSON
        manifest's ``presentationMap`` entry.

        Returns:
            :class:`PresentationMap` or ``None``: The parsed presentation
            map, or ``None`` when the service does not advertise one.

        Raises:
            MusicServiceException: If the presentation map cannot be fetched
                or parsed.
        """
        if self._presentation_map is None:
            self._presentation_map = _fetch_presentation_map(
                self.music_service, self.session, self.get_manifest()
            )
        return self._presentation_map

    def get_strings(self):
        """Return the service's localized string tables, fetching and caching.

        The strings document resolves the ``StringId``/``PromptStringId``/
        ``OnSuccessStringId``/... references carried by the presentation map
        (menu-item overrides, ratings, display-type lines) into display text
        per language.  Returns ``None`` when the service does not advertise a
        strings document.

        Returns:
            :class:`StringTables` or ``None`.

        Raises:
            MusicServiceException: If the strings document cannot be fetched
                or parsed.
        """
        if self._strings is None:
            self._strings = _fetch_string_tables(
                self.music_service, self.session, self.get_manifest()
            )
        return self._strings

    def localized_strings(self, lang="en-US"):
        """Return the ``{string_id: text}`` table for a language.

        Convenience over :meth:`get_strings`; returns ``{}`` when the service
        has no strings document.
        """
        tables = self.get_strings()
        if tables is None:
            return {}
        return tables.localized(lang)

    def _content_root(self):
        content_device_id = (
            _account_content_device_id(self.device.household_id, self.account)
            if self.account.udn
            else self.device_id
        )
        headers = _content_headers(
            self.music_service,
            self.account,
            content_device_id,
            self.controller_id,
            self.time_zone,
            self.explicit_content,
        )

        for attempt in range(2):
            try:
                response = self.session.get(
                    self._content_endpoint, headers=headers, timeout=20
                )
            except requests.RequestException as error:
                raise MusicServiceException(
                    f"{self.music_service.service_name} content browse failed: {error}"
                ) from error
            if response.status_code != 401 or attempt == 1:
                break
            if not self.allow_credential_refresh:
                raise MusicServiceAuthException(
                    f"{self.music_service.service_name} content browse "
                    "returned HTTP 401"
                )
            self._client.refresh_auth_token()
            headers = _content_headers(
                self.music_service,
                self.account,
                content_device_id,
                self.controller_id,
                self.time_zone,
                self.explicit_content,
            )

        if response.status_code != 200:
            raise MusicServiceException(
                f"{self.music_service.service_name} content browse returned "
                f"HTTP {response.status_code}"
            )
        try:
            page = response.json()
        except ValueError as error:
            raise MusicServiceException(
                f"{self.music_service.service_name} content browse returned "
                "invalid JSON"
            ) from error
        if not isinstance(page, Mapping):
            raise MusicServiceException("Content browse root was not an object")

        sections = []
        self._content_views = {}
        for view_value in _as_list(page.get("views")):
            view = _as_mapping(view_value)
            identity = _as_mapping(view.get("id"))
            content = _as_mapping(view.get("content"))
            container = _as_mapping(content.get("container"))
            object_id = _as_string(identity.get("objectId"))
            if not container or not object_id:
                continue
            embedded = [
                normalized
                for raw_item in _as_list(view.get("items"))
                for normalized in [_content_item(raw_item)]
                if normalized is not None
            ]
            title = str(container.get("name", object_id))
            section = MusicServiceBrowseItem(
                item_id=object_id,
                title=title,
                kind="mediaCollection",
                item_type="section",
                album_art_uri=embedded[0].album_art_uri if embedded else "",
                source_transport="content-section",
                display_type=view.get("displayType", ""),
                raw=dict(view),
            )
            sections.append(section)
            self._content_views[object_id] = MusicServiceBrowseResult(
                embedded,
                index=0,
                total=int(view.get("total", len(embedded)) or len(embedded)),
                transport="content",
                requested_id=object_id,
                endpoint=self._content_endpoint,
                raw=view,
            )

        return MusicServiceBrowseResult(
            sections,
            index=0,
            total=len(sections),
            transport="content",
            requested_id="root",
            endpoint=self._content_endpoint,
            raw=page,
        )

    def get_metadata(
        self,
        item="root",
        index=0,
        count=100,
        recursive=False,
        sort_order=None,
        sort_ascending=None,
    ):
        """Browse a root/container using the desktop controller's transport flow.

        Passing a :class:`MusicServiceBrowseItem` from a previous result keeps
        the transport provenance required by newer providers. A plain string ID
        is treated as an ordinary legacy SMAPI ID for backwards-predictable
        behavior. ``sort_order``/``sort_ascending`` are forwarded to the
        provider when given; not all containers support sorting.
        """
        if isinstance(item, MusicServiceBrowseItem):
            object_id = item.item_id
            from_content_page = item.source_transport in (
                "content",
                "content-section",
            )
        else:
            object_id = item
            from_content_page = False

        if object_id in self._content_views:
            return self._content_views[object_id]
        if object_id in ("", "root") and self._content_endpoint:
            return self._content_root()

        client = self._scoped_client(from_content_page)
        try:
            page = client.get_metadata(
                object_id, index, count, recursive, sort_order, sort_ascending
            )
        finally:
            if client is not self._client:
                self._client.session_id = client.session_id

        source_transport = "content" if from_content_page else "smapi"
        items = [_legacy_item(record, source_transport) for record in page["items"]]
        return MusicServiceBrowseResult(
            items,
            index=page["index"],
            total=page["total"],
            transport="smapi",
            requested_id=object_id,
            raw=page,
        )

    def _scoped_client(self, force_scoped=False):
        """Return the SMAPI client for the account's OAuth device identity.

        SMAPI requests identify the account through ``loginToken.householdId``.
        The desktop controller sends the account-scoped content device identity
        here, not the bare household ID: providers such as Apple reject SMAPI
        calls made under the plain household identity with
        ``InvalidTokenException`` even though their content home page accepts
        it.  Content-session objects are always handed back to SMAPI scoped;
        search is likewise scoped whenever the account carries a token UDN.

        The shared client is returned for anonymous services, which send no
        token: their account UDN is only a bare ``SA_RINCON…_`` identifier and
        carries no account UID to derive a device identity from.
        """
        if force_scoped or self.account.udn:
            try:
                return self._make_client(
                    _account_content_device_id(self.device.household_id, self.account)
                )
            except MusicServiceAuthException:
                # Not a token account (eg an anonymous service): no account
                # UID is encoded in the UDN, so there is nothing to scope to.
                pass
        return self._client

    def search(self, category, term="", index=0, count=100, variant="all"):
        """Search the service with the existing MusicService category mapping.

        Args:
            category (str): The search category (eg ``'artists'``). See
                :attr:`MusicService.available_search_categories`.
            term (str): The term to search for.
            index (int): The starting index. Default 0.
            count (int): The maximum number of items to return. Default 100.
            variant (str): Which search variant to use, or ``'all'`` (the
                default) to search every variant and merge the results.
                Available variants are listed per category by
                :attr:`MusicService.available_search_variants`.
        """
        # Reuse the existing MusicService presentation-map parser rather than
        # maintaining a second search-category implementation here.
        # pylint: disable=protected-access
        variants = self.music_service._get_search_variants().get(category)
        # pylint: enable=protected-access
        if variants is None:
            categories = ", ".join(
                sorted(self.music_service.available_search_categories)
            )
            raise MusicServiceException(
                f"Unknown search category {category!r}; available "
                f"categories: {categories}"
            )
        if variant != "all":
            variants = [entry for entry in variants if entry[0] == variant]
            if not variants:
                available = self.music_service.available_search_variants.get(
                    category, []
                )
                raise MusicServiceException(
                    f"Unknown search variant {variant!r} for {category!r}; "
                    f"available variants: {', '.join(sorted(available))}"
                )

        client = self._scoped_client()
        merged_items = []
        total = 0
        raw = []
        for _variant, mapped_id in variants:
            page = client.search(mapped_id, term, index, count)
            for record in page["items"]:
                item = _legacy_item(record)
                item.variant = _variant
                merged_items.append(item)
            total += page["total"]
            raw.append(page)
        return MusicServiceBrowseResult(
            merged_items,
            index=index,
            total=total,
            transport="smapi",
            requested_id=category,
            raw=raw,
        )

    def get_media_metadata(self, item):
        """Return provider metadata for one item without changing playback."""
        object_id = item.item_id if isinstance(item, MusicServiceBrowseItem) else item
        # SMAPI providers (Apple among them) reject calls under the plain
        # household identity with InvalidTokenException; use the account-
        # scoped device identity like every other SMAPI call here.
        return self._scoped_client().get_media_metadata(object_id)

    def sonos_uri_from_id(self, item_id):
        """Return a URI which can be sent to a player for playing.

        Accepts either a :class:`MusicServiceBrowseItem` or a raw item id.
        A browsed item is resolved MIME-aware (see
        :func:`soco.music_services.browser.playback.build_uri`): a Spotify
        track, for example, becomes an ``x-sonos-spotify:`` URI, never the
        ``x-sonosapi-stream:`` radio scheme.  A bare ``spotify:track:...`` id
        is unambiguous (only Spotify uses that namespace) and is mapped the
        same way; any other bare id carries no type or MIME information, so it
        falls back to the ``x-sonosapi-stream:`` scheme the player uses to
        resolve radio/stream content itself.

        This is deliberately a URI-only helper. It cannot carry the DIDL
        resource protocol information, title, or selected account descriptor
        required for complete Spotify metadata. Use :meth:`play` for normal
        playback; it sends the URI and DIDL together.
        """
        if isinstance(item_id, MusicServiceBrowseItem):
            _item_id, item_type, mime, _title = resolve_item(self, item_id)
            return build_uri(self, _item_id, item_type, mime)
        raw = str(item_id)
        if raw.startswith("spotify:track:") and int(self.service_id) == 12:
            return build_uri(self, raw, "track", "audio/x-spotify")
        encoded = quote_url(raw.encode("utf-8"))
        return (
            f"x-sonosapi-stream:{encoded}?sid={self.music_service.service_id}"
            f"&sn={self.account.serial_number}"
        )

    def play(self, item, device=None, **kwargs):
        """Play a browsed item on a Sonos device.

        Builds the player-resolved URI and DIDL metadata for one playable item
        and sends them with :meth:`SoCo.play_uri`. Track, stream, program,
        show and audiobook items are supported; containers must be browsed
        into first.

        Args:
            item (MusicServiceBrowseItem or str): A playable item from
                :meth:`get_metadata` or :meth:`search`, or a raw item id.
            device (SoCo, optional): The device to play on. Defaults to the
                device the browser was constructed with.
            kwargs: Additional arguments forwarded to :meth:`SoCo.play_uri`.

        Returns:
            The result of :meth:`SoCo.play_uri`.

        Raises:
            MusicServiceException: If the item cannot be played (for example
                a container, or an item type without a known URI mapping), or
                if the service is not added to this household.
        """
        player = device or self.device
        if self.auth_type == "Anonymous" and not self.account.udn:
            raise MusicServiceException(
                f"{self.service_name} is not added to this household, so its "
                "content cannot be played; add the service first"
            )
        item_id, item_type, mime, title = resolve_item(self, item)
        uri = build_uri(self, item_id, item_type, mime)
        metadata = build_metadata(self, item_id, title, item_type, mime=mime, uri=uri)
        return player.play_uri(uri, meta=metadata, **kwargs)

    def get_extended_metadata(self, item):
        """Return provider extended metadata (related items and text)."""
        object_id = item.item_id if isinstance(item, MusicServiceBrowseItem) else item
        data = self._scoped_client().get_extended_metadata(object_id)
        return {
            "items": [_legacy_item(record) for record in data["items"]],
            "text": data["text"],
            "raw": data["raw"],
        }

    def get_last_update(self):
        """Return provider catalog/favorites change timestamps."""
        return self._scoped_client().get_last_update()

    def get_scroll_indices(self, item):
        """Return the scroll index entries for one container (jump bars)."""
        object_id = item.item_id if isinstance(item, MusicServiceBrowseItem) else item
        return self._scoped_client().get_scroll_indices(object_id)

    def set_played_seconds(self, item, seconds):
        """Report listening progress for one item back to the provider."""
        object_id = item.item_id if isinstance(item, MusicServiceBrowseItem) else item
        self._scoped_client().set_played_seconds(object_id, seconds)


__all__ = [
    "ConfiguredMusicServiceAccount",
    "MusicServiceBrowseItem",
    "MusicServiceBrowseResult",
    "MusicServiceBrowser",
    "PresentationMap",
    "StringTables",
]
