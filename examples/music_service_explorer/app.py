"""Music-service explorer: a showcase of every soco music-service feature.

This is a deliberately thin Flask app. Every route is a one-to-one demo of a
soco music-service API call - the equivalent soco snippet is shown in the UI
next to each feature so the app doubles as runnable documentation.

No playback happens anywhere in this app. Browsing, searching and metadata
inspection are all read-only, and most of the UI stays that way. The one
mutating part is the ``Accounts`` tab, which uses
:class:`soco.music_services.MusicServiceAccountManager` to add, re-link,
rename, and remove household music-service accounts - every one of those
actions asks for explicit confirmation first.

Run it from the repository root with the checked-out soco on the path::

    pip install -r requirements.txt
    python examples/music_service_explorer/app.py
    # open http://127.0.0.1:5050
"""

from __future__ import annotations

import os
import secrets
import sys
import time

# Prefer this repository's SoCo checkout over any installed copy: the
# music-service features this app demonstrates (MusicServiceBrowser, search
# variants, configured-account browsing) only exist on the music-services
# branch. This makes `python examples/music_service_explorer/app.py` work
# from anywhere without PYTHONPATH gymnastics.
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from flask import Flask, jsonify, render_template, request  # noqa: E402

from soco.discovery import any_soco  # noqa: E402
from soco.exceptions import MusicServiceAuthException  # noqa: E402
from soco.music_services import (  # noqa: E402
    ConfiguredMusicServiceAccount,
    MusicService,
    MusicServiceAccountManager,
    MusicServiceBrowser,
    MusicServiceBrowseItem,
)

app = Flask(__name__)

# The music services data is fetched once from the speaker and cached for a
# few minutes - calling ListAvailableServices on every page view is wasteful.
SERVICES_TTL = 300  # seconds

# The configured-account payload arrives as the initial ZoneGroupTopology
# event. Subscribing for it is comparatively slow and can occasionally miss
# the event, so the app caches the fetched accounts and only re-subscribes
# after the TTL - otherwise every search/browse call would hit the network.
ACCOUNTS_TTL = 600  # seconds

# Authorized link sessions are held server-side (the link code is a
# short-lived secret that should not round-trip through the browser) and are
# only ever committed by the same server that created them.
LINK_SESSION_TTL = 900  # seconds


def _device():
    """The speaker that drives the app (a SoCo instance), cached briefly.

    soco caches the first discovery result per process, so a fresh SSDP scan
    is forced only when the cached speaker has gone stale (or was missing
    because the scan raced the first request).
    """
    key = "_device"
    now = time.time()
    cached = getattr(app, key, None)
    if cached and now - cached[1] < SERVICES_TTL:
        return cached[0]
    device = any_soco(allow_network_scan=True)
    if device is None:
        raise RuntimeError("No Sonos speaker found on the network")
    setattr(app, key, (device, now))
    return device


def _service_data():
    """The raw ListAvailableServices descriptor data, cached briefly."""
    key = "_services_data"
    now = time.time()
    cached = getattr(app, key, None)
    if cached and now - cached[1] < SERVICES_TTL:
        return cached[0]
    data = MusicService._get_music_services_data()  # pylint: disable=protected-access
    setattr(app, key, (data, now))
    return data


def _get_service(name):
    """A legacy MusicService instance for a named service."""
    return MusicService(name, device=_device())


def _accounts_for(name):
    """The configured household accounts for one service.

    ``MusicServiceBrowser`` refuses to pick when several accounts exist for
    the same service (eg two Amazon Music logins), so the app resolves them
    itself and passes the chosen one explicitly.
    """
    service_id = int(MusicService(name, device=_device()).service_id)
    accounts = _cached_accounts()
    return [a for a in accounts if a.service_id == service_id]


def _invalidate_caches():
    """Drop caches whose content a household mutation just made stale.

    Every account mutation (add, re-link, rename, remove, credential
    refresh) invalidates the cached account payload, the per-service
    browsers (which hold a copy of the account record), and the account
    managers. The next request re-fetches everything from the players.
    """
    app._accounts_cache = None
    app._browsers = {}
    app._managers = {}


def _cached_accounts():
    """All configured household accounts, fetched at most once per TTL.

    The account payload is the initial ZoneGroupTopology event, which is slow
    to subscribe to and can occasionally not arrive at all. Caching avoids
    doing that per request, and a failed capture degrades to an empty list so
    a single flaky event can never take the whole app down.
    """
    now = time.time()
    cached = getattr(app, "_accounts_cache", None)
    if cached and now - cached[1] < ACCOUNTS_TTL:
        return cached[0]
    try:
        accounts = ConfiguredMusicServiceAccount.get_accounts(_device(), timeout=10)
    except Exception:  # pylint: disable=broad-except
        app.logger.warning(
            "Configured-account event capture failed; continuing without accounts",
            exc_info=True,
        )
        accounts = []
    app._accounts_cache = (accounts, now)
    return accounts


def _get_manager(name):
    """A MusicServiceAccountManager for a named service, cached briefly.

    Constructing the manager performs a couple of local SOAP reads, so it is
    cached per service like the browsers. Managers are dropped by
    :func:`_invalidate_caches` after a mutation so their household state is
    never reused across a change.
    """
    cache = getattr(app, "_managers", {})
    if name in cache:
        return cache[name]
    manager = MusicServiceAccountManager(name, device=_device())
    cache[name] = manager
    if len(cache) > 12:
        cache.pop(next(iter(cache)))
    app._managers = cache
    return manager


def _get_browser(name, account=None):
    """A MusicServiceBrowser (account-aware) for a named service.

    This uses the account credentials Sonos already stores for the household,
    so search/browse work for authenticated services without any token dance.
    The browser is cached because constructing it performs an account event
    capture and a manifest fetch.

    Args:
        name (str): Service name.
        account (ConfiguredMusicServiceAccount, optional): The account to use.
            When omitted and the service has exactly one configured account,
            that account is used; when there are several, the first one is
            used so the demo never dies on the multi-account guard.
    """
    cache = getattr(app, "_browsers", {})
    key = (name, getattr(account, "serial_number", 0))
    if key in cache:
        return cache[key]
    if account is None:
        matches = _accounts_for(name)
        account = matches[0] if matches else None
    kwargs = {}
    if account is not None:
        kwargs["account"] = account
    browser = MusicServiceBrowser(
        name, device=_device(), allow_credential_refresh=True, **kwargs
    )
    cache[key] = browser
    # A demo app doesn't need to hold every service's browser forever.
    if len(cache) > 12:
        cache.pop(next(iter(cache)))
    app._browsers = cache
    return browser


# ---------------------------------------------------------------------------
# Feature: legacy MusicService search categories/variants
# ---------------------------------------------------------------------------


def _search_categories(name):
    service = _get_service(name)
    return {
        "categories": service.available_search_categories,
        "variants": service.available_search_variants,
    }


def _legacy_search(name, category, term, variant, index, count):
    service = _get_service(name)
    result = service.search(category, term, index=index, count=count, variant=variant)
    return {
        "items": [
            {
                "id": item.item_id,
                "title": item.title,
                "type": item.metadata.get("item_type", ""),
                "artist": item.metadata.get("artist", ""),
            }
            for item in result
        ],
        "number_returned": result.number_returned,
        "total_matches": result.total_matches,
    }


def _account_from_request(name):
    """Resolve the account a request wants, defaulting to the first one.

    The UI sends ``account=<nickname>`` when several accounts exist for a
    service; the first configured account is used as the default.
    """
    wanted = request.args.get("account", "")
    matches = _accounts_for(name)
    if not matches:
        return None
    if not wanted:
        return matches[0]
    for account in matches:
        if account.nickname == wanted or str(account.serial_number) == wanted:
            return account
    return matches[0]


def _browser_search(name, category, term, variant, index, count, account=None):
    browser = _get_browser(name, account=account)
    result = browser.search(category, term, index=index, count=count, variant=variant)
    return {
        "items": [
            {
                "id": item.item_id,
                "title": item.title,
                "type": item.item_type,
                "artist": item.artist,
                "variant": item.variant,
                "can_browse": item.can_browse,
            }
            for item in result.items
        ],
        "number_returned": len(result.items),
        "total_matches": result.total,
    }


# ---------------------------------------------------------------------------
# Feature: browse (get_metadata)
# ---------------------------------------------------------------------------


def _legacy_browse(
    name, item_id, index, count, recursive, sort_order=None, sort_ascending=None
):
    service = _get_service(name)
    result = service.get_metadata(
        item_id,
        index=index,
        count=count,
        recursive=recursive,
        sort_order=sort_order,
        sort_ascending=sort_ascending,
    )
    return {
        "items": [
            {
                "id": item.item_id,
                "title": item.title,
                "type": item.metadata.get("item_type", ""),
                "artist": item.metadata.get("artist", ""),
                "can_browse": item.metadata.get("can_enumerate") == "true"
                or "collection" in item.metadata.get("item_type", "").lower(),
            }
            for item in result
        ],
        "number_returned": result.number_returned,
        "total_matches": result.total_matches,
    }


def _browser_browse(
    name, item_id, index, count, recursive, sort_order, sort_ascending, account=None
):
    browser = _get_browser(name, account=account)
    # Content-session children must be handed back to SMAPI with the account's
    # OAuth device identity. The browser only does that when it receives a
    # MusicServiceBrowseItem with a content source_transport, so rebuild the
    # wrapper from the transport the frontend carried over.
    transport = request.args.get("transport", "")
    kwargs = {
        "index": index,
        "count": count,
        "recursive": recursive,
        "sort_order": sort_order,
        "sort_ascending": sort_ascending,
    }
    if transport in ("content", "content-section"):
        item = MusicServiceBrowseItem(
            item_id,
            "",
            "mediaCollection",
            source_transport=transport,
        )
        result = browser.get_metadata(item, **kwargs)
    else:
        result = browser.get_metadata(item_id, **kwargs)
    return {
        "items": [
            {
                "id": item.item_id,
                "title": item.title,
                "type": item.item_type,
                "artist": item.artist,
                "variant": item.variant,
                "can_browse": item.can_browse,
                "transport": item.source_transport,
            }
            for item in result.items
        ],
        "number_returned": len(result.items),
        "total_matches": result.total,
    }


# ---------------------------------------------------------------------------
# Feature: per-item metadata
# ---------------------------------------------------------------------------


def _legacy_media_metadata(name, item_id):
    service = _get_service(name)
    return {"metadata": service.get_media_metadata(item_id)}


def _browser_media_metadata(name, item_id, account=None):
    browser = _get_browser(name, account=account)
    return {"metadata": browser.get_media_metadata(item_id)}


def _browser_extended_metadata(name, item_id, account=None):
    browser = _get_browser(name, account=account)
    data = browser.get_extended_metadata(item_id)
    return {
        "items": [
            {
                "id": item.item_id,
                "title": item.title,
                "type": item.item_type,
                "artist": item.artist,
                "can_browse": item.can_browse,
            }
            for item in data["items"]
        ],
        "text": data["text"],
    }


def _browser_media_uri(name, item_id, account=None):
    browser = _get_browser(name, account=account)
    return {
        "sonos_uri": browser.sonos_uri_from_id(item_id),
    }


def _browser_last_update(name, account=None):
    browser = _get_browser(name, account=account)
    return {"last_update": browser.get_last_update()}


# ---------------------------------------------------------------------------
# Feature: misc read-only service calls
# ---------------------------------------------------------------------------


def _misc_service_info(name):
    service = _get_service(name)
    return {
        "service_name": service.service_name,
        "service_id": service.service_id,
        "service_type": service.service_type,
        "auth_type": service.auth_type,
        "capabilities": service.capabilities,
        "version": service.version,
        "container_type": service.container_type,
        "uri": service.uri,
        "secure_uri": service.secure_uri,
        "presentation_map_uri": service.presentation_map_uri,
        "manifest_uri": service.manifest_uri,
        "desc": service.desc,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    try:
        device = _device()
        services = [
            {
                "name": name,
                "id": data["Id"],
                "auth": data["Auth"],
                "capabilities": data["Capabilities"],
                "service_type": data["ServiceType"],
                "container_type": data["ContainerType"],
            }
            for name, data in sorted(
                ((d["Name"], d) for d in _service_data().values()), key=lambda x: x[0]
            )
        ]
        # Account capture subscribes to a ZoneGroupTopology event and can fail
        # or time out in some households. The cache degrades to an empty list
        # in that case so the service catalog still renders.
        raw_accounts = _cached_accounts()
        # Some auto-added accounts (eg TuneIn) have no per-account token UDN,
        # so account_uid can't be derived for them. Show what we can and skip
        # only those entries rather than failing the whole page.
        accounts = []
        for account in raw_accounts:
            try:
                account_uid = hex(account.account_uid)
            except Exception:  # pylint: disable=broad-except
                account_uid = "n/a"
            accounts.append(
                {
                    "service_id": account.service_id,
                    "nickname": account.nickname,
                    "tier": account.tier,
                    "username": account.username,
                    "account_uid": account_uid,
                }
            )
        # Services that have an account actually added to this household, so
        # the sidebar can filter to "accounts added to our system" only.
        # Service ids are strings in the descriptor and ints on the account,
        # so normalize before comparing.
        configured_service_ids = {str(a["service_id"]) for a in accounts}
        return render_template(
            "index.html",
            device={
                "name": device.player_name,
                "ip": device.ip_address,
                "uid": device.uid,
                "household_id": device.household_id,
            },
            services=services,
            accounts=accounts,
            configured_service_ids=configured_service_ids,
        )
    except Exception as error:  # pylint: disable=broad-except
        return render_template("index.html", error=str(error), services=[], accounts=[])


@app.route("/api/categories")
def api_categories():
    """Search categories + variants for one service (legacy API)."""
    try:
        return jsonify(_search_categories(request.args.get("service", "")))
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


@app.route("/api/accounts")
def api_accounts():
    """The configured household accounts for one service."""
    name = request.args.get("service", "")
    if not name:
        return jsonify({"error": "missing service"}), 400
    try:
        accounts = _accounts_for(name)
        return jsonify({"accounts": [_account_row(account) for account in accounts]})
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


@app.route("/api/search")
def api_search():
    """Search one service; demonstrates legacy and browser APIs side by side."""
    name = request.args.get("service", "")
    category = request.args.get("category", "")
    term = request.args.get("term", "")
    variant = request.args.get("variant", "all")
    api = request.args.get("api", "legacy")
    index = int(request.args.get("index", 0))
    count = int(request.args.get("count", 20))
    account = _account_from_request(name)
    try:
        if api == "browser":
            data = _browser_search(name, category, term, variant, index, count, account)
        else:
            data = _legacy_search(name, category, term, variant, index, count)
        return jsonify(data)
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


@app.route("/api/browse")
def api_browse():
    """Browse a container; both APIs, with recursive + paging options."""
    name = request.args.get("service", "")
    item_id = request.args.get("item", "root")
    api = request.args.get("api", "legacy")
    index = int(request.args.get("index", 0))
    count = int(request.args.get("count", 20))
    recursive = request.args.get("recursive", "0") == "1"
    sort_order = request.args.get("sort_order", "") or None
    sort_ascending = None
    if sort_order and request.args.get("sort_ascending", "") != "":
        sort_ascending = request.args.get("sort_ascending") == "1"
    account = _account_from_request(name)
    try:
        if api == "browser":
            data = _browser_browse(
                name,
                item_id,
                index,
                count,
                recursive,
                sort_order,
                sort_ascending,
                account,
            )
        else:
            data = _legacy_browse(
                name, item_id, index, count, recursive, sort_order, sort_ascending
            )
        return jsonify(data)
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


@app.route("/api/metadata")
def api_metadata():
    """get_media_metadata for one item, on both APIs."""
    name = request.args.get("service", "")
    item_id = request.args.get("item", "")
    api = request.args.get("api", "legacy")
    account = _account_from_request(name)
    try:
        if api == "browser":
            data = _browser_media_metadata(name, item_id, account)
        else:
            data = _legacy_media_metadata(name, item_id)
        return jsonify(data)
    except MusicServiceAuthException as error:
        # Token-based providers (eg Apple) refuse some metadata calls under
        # the shared client; the legacy path is the reliable fallback here.
        payload = {"error": str(error), "hint": "try the legacy API"}
        return jsonify(payload), 401
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


@app.route("/api/extended-metadata")
def api_extended_metadata():
    """get_extended_metadata for one item (related items + text)."""
    name = request.args.get("service", "")
    item_id = request.args.get("item", "")
    account = _account_from_request(name)
    try:
        return jsonify(_browser_extended_metadata(name, item_id, account))
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


@app.route("/api/media-uri")
def api_media_uri():
    """Player-resolved stream URI for one item (browser API)."""
    name = request.args.get("service", "")
    item_id = request.args.get("item", "")
    account = _account_from_request(name)
    try:
        return jsonify(_browser_media_uri(name, item_id, account))
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


@app.route("/api/last-update")
def api_last_update():
    """get_last_update for one service (browser API)."""
    name = request.args.get("service", "")
    account = _account_from_request(name)
    try:
        return jsonify(_browser_last_update(name, account))
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


@app.route("/api/info")
def api_info():
    """Everything soco exposes about a service descriptor."""
    try:
        return jsonify(_misc_service_info(request.args.get("service", "")))
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


# ---------------------------------------------------------------------------
# Feature: account onboarding (MusicServiceAccountManager)
# ---------------------------------------------------------------------------
#
# This is the one mutating part of the app. begin-link only asks the provider
# for its authorization choices (read-only); commit-link, add-credentials and
# the manage actions write to the household players. The frontend confirms
# every one of those before sending it.

# Authorized link sessions held server-side, keyed by an opaque token.
_LINK_SESSIONS = {}


def _store_link(link):
    """Hold an authorized link session and return its opaque token."""
    _purge_links()
    token = secrets.token_urlsafe(16)
    _LINK_SESSIONS[token] = (time.time(), link)
    return token


def _take_link(token):
    """Pop and return a stored link session, rejecting unknown/expired ones."""
    _purge_links()
    entry = _LINK_SESSIONS.pop(token, None)
    if entry is None:
        raise ValueError("Unknown link session; begin a new authorization")
    stamp, link = entry
    if time.time() - stamp > LINK_SESSION_TTL:
        raise ValueError(
            "Link session expired; begin a new authorization before committing"
        )
    return link


def _purge_links():
    now = time.time()
    expired = [
        token
        for token, (stamp, _link) in _LINK_SESSIONS.items()
        if now - stamp > LINK_SESSION_TTL
    ]
    for token in expired:
        del _LINK_SESSIONS[token]


def _account_row(account):
    """The JSON shape of one configured account for the onboarding UI."""
    try:
        account_uid = account.account_uid
    except Exception:  # pylint: disable=broad-except
        account_uid = None
    return {
        "nickname": account.nickname or "unnamed",
        "serial_number": account.serial_number,
        "tier": account.tier,
        "username": account.username,
        "udn": account.udn,
        "keyless": account.keyless,
        "account_uid": account_uid,
    }


def _onboard_status(name):
    """Auth path + configured accounts for one service."""
    service = _get_service(name)
    auth = service.auth_type
    if auth in ("DeviceLink", "AppLink"):
        add_path = "link"
    elif auth in ("Anonymous", "UserId", "UserIdPassword"):
        add_path = "credentials"
    else:
        add_path = "none"
    service_id = int(service.service_id)
    accounts = [
        _account_row(account)
        for account in _cached_accounts()
        if account.service_id == service_id
    ]
    return {
        "service": name,
        "auth_type": auth,
        "add_path": add_path,
        "accounts": accounts,
    }


@app.before_request
def _guard_cross_site_mutations():
    """Block cross-site requests to the mutating endpoints.

    The mutations are plain JSON POSTs with no auth, so a cross-origin fetch
    could trigger them without a CORS preflight. Requiring a custom header
    (which cross-origin requests cannot add without a preflight) and
    rejecting foreign Origins closes that hole.
    """
    if request.method != "POST":
        return None
    origin = request.headers.get("Origin", "")
    local_origin = origin in ("http://127.0.0.1:5050", "http://localhost:5050")
    # A foreign Origin is blocked outright, custom header or not: browsers
    # cannot add the header cross-origin without a CORS preflight, so the
    # header check below is the primary defense and the Origin check is
    # belt-and-suspenders.
    if origin and not local_origin:
        return jsonify({"error": "cross-site request blocked"}), 403
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or local_origin:
        return None
    # No Origin and no custom header: not a browser session, so reject.
    return jsonify({"error": "cross-site request blocked"}), 403


@app.route("/api/onboard/status")
def api_onboard_status():
    """The authorization path and configured accounts for one service."""
    name = request.args.get("service", "")
    if not name:
        return jsonify({"error": "missing service"}), 400
    try:
        return jsonify(_onboard_status(name))
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


@app.route("/api/onboard/begin-link", methods=["POST"])
def api_onboard_begin_link():
    """Ask the provider for its authorization choices (no player mutation).

    The authorized session is stored server-side; the browser only ever sees
    the registration URL (and the link code when the provider asks the user
    to enter one on the page).
    """
    data = request.get_json(force=True) or {}
    name = data.get("service", "")
    if not name:
        return jsonify({"error": "missing service"}), 400
    try:
        link = _get_manager(name).begin_link()
        token = _store_link(link)
        return jsonify(
            {
                "session_token": token,
                "source_action": link.source_action,
                "registration_url": link.registration_url,
                "app_url": link.app_url,
                "link_code": link.link_code if link.show_link_code else "",
                "show_link_code": link.show_link_code,
                "standalone": link.standalone_supported,
            }
        )
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


@app.route("/api/onboard/commit-link", methods=["POST"])
def api_onboard_commit_link():
    """Commit an authorized link to the household players (mutation)."""
    data = request.get_json(force=True) or {}
    name = data.get("service", "")
    token = data.get("session_token", "")
    replace_udn = data.get("replace_account_udn", "") or ""
    if not name or not token:
        return jsonify({"error": "missing service or session_token"}), 400
    try:
        manager = _get_manager(name)
        link = _take_link(token)
        try:
            added = manager.commit_link(link, replace_account_udn=replace_udn)
        except Exception:
            # A failed commit (provider exchange error, player rejection, ...)
            # must not burn the user's authorization: put the session back so
            # they can retry after fixing whatever went wrong.
            _LINK_SESSIONS[token] = (time.time(), link)
            raise
        _invalidate_caches()
        return jsonify(
            {
                "service_id": added.service_id,
                "account_udn": added.account_udn,
                "nickname": added.nickname,
                "provider_nickname": added.provider_nickname,
            }
        )
    except ValueError as error:
        # Unknown/expired session tokens are client mistakes, not server bugs.
        return jsonify({"error": str(error)}), 400
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


@app.route("/api/onboard/add-credentials", methods=["POST"])
def api_onboard_add_credentials():
    """Add an anonymous or legacy username/password account (mutation)."""
    data = request.get_json(force=True) or {}
    name = data.get("service", "")
    if not name:
        return jsonify({"error": "missing service"}), 400
    try:
        added = _get_manager(name).add_credentials(
            data.get("username", ""), data.get("password", "")
        )
        _invalidate_caches()
        return jsonify(
            {
                "service_id": added.service_id,
                "account_udn": added.account_udn,
                "nickname": added.nickname,
            }
        )
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


@app.route("/api/onboard/manage", methods=["POST"])
def api_onboard_manage():
    """Rename, remove, re-credential, or edit one household account (mutation).

    ``action`` is one of ``rename``, ``remove``, ``password``, ``md``, or
    ``refresh``. The account is identified by its ``account_udn`` (the
    canonical ``SA_RINCON...`` UDN from the status payload).
    """
    data = request.get_json(force=True) or {}
    name = data.get("service", "")
    action = data.get("action", "")
    udn = data.get("account_udn", "")
    if not name or not action:
        return jsonify({"error": "missing service or action"}), 400
    # Every manage action targets one account; a missing UDN is a client
    # mistake, so reject it here rather than letting it surface as a 500.
    if action != "refresh" and not udn:
        return jsonify({"error": "an account UDN is required"}), 400
    if action == "refresh" and not data.get("account_uid"):
        return jsonify({"error": "an account UID is required for refresh"}), 400
    try:
        manager = _get_manager(name)
        if action == "rename":
            manager.set_nickname(udn, data.get("nickname", ""))
        elif action == "remove":
            manager.remove_account(udn)
        elif action == "password":
            manager.edit_account_password(udn, data.get("new_password", ""))
        elif action == "md":
            manager.edit_account_md(udn, data.get("new_md", ""))
        elif action == "refresh":
            manager.refresh_account_credentials(
                int(data.get("account_uid", 0) or 0),
                data.get("token", ""),
                data.get("key", ""),
            )
        else:
            return jsonify({"error": f"unknown action {action!r}"}), 400
        _invalidate_caches()
        return jsonify({"ok": True, "action": action})
    except ValueError as error:
        # Malformed client input (eg a non-numeric account_uid).
        return jsonify({"error": str(error)}), 400
    except Exception as error:  # pylint: disable=broad-except
        return jsonify({"error": str(error)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
