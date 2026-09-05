#!/usr/bin/env python3
"""Verify every Sonos music service and record what works.

This script exercises the :mod:`soco.music_services.browser` API against the
live household:

* writes a JSON catalogue of **every** music service the speaker advertises,
* for each service that has an account configured on the household it tests
  browsing, searching, media-metadata retrieval and playback (one item per
  item type the service exposes), and
* for services without a configured account it records the failure mode (an
  auth error for account-backed services; a browse-only result for anonymous
  services, whose playback usually fails without stored credentials).

Results are written to two files:

* ``music_services.json`` -- the full service catalogue plus per-household
  test results. Re-runs merge into the file keyed by a non-reversible
  household hash, so one household's results never overwrite another's, and
* ``soco/music_services/browser/VERIFIED.md`` -- a human-readable matrix of
  what works and what does not yet work.

Usage::

    python examples/verify_music_services.py            # prompts for a speaker
    python examples/verify_music_services.py --ip 192.168.1.51
    python examples/verify_music_services.py --no-play  # skip playback tests
    python examples/verify_music_services.py --volume 3 --play-seconds 3
"""

from __future__ import unicode_literals

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

# Prefer this repository's SoCo checkout over any installed copy, so the
# script runs from anywhere without PYTHONPATH gymnastics.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from soco import discovery  # noqa: E402
from soco.exceptions import MusicServiceException  # noqa: E402
from soco.music_services.browser import (  # noqa: E402
    ConfiguredMusicServiceAccount,
    MusicServiceBrowser,
)
from soco.music_services.browser.playback import normalize_item_type  # noqa: E402
from soco.music_services.music_service import MusicService  # noqa: E402
from soco.snapshot import Snapshot  # noqa: E402

# How long to wait for a playback attempt to reach a terminal state.
PLAY_WAIT_SECONDS = 8
DEFAULT_TEST_VOLUME = 3
DEFAULT_PLAY_SECONDS = 3.0
# Bounds for the recursive browse that hunts for playable item types.
MAX_BROWSE_DEPTH = 5
MAX_BROWSE_ITEMS = 20
# Wall-clock budget for one configured service's browse/search/metadata phase.
# Some services never answer; this keeps the whole run bounded.
SERVICE_DEADLINE_SECONDS = 30
# Stop browsing once this many distinct item types have been found.
TYPES_TO_FIND = 4

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VERIFIED_MD = REPO_ROOT / "soco" / "music_services" / "browser" / "VERIFIED.md"
DEFAULT_JSON = REPO_ROOT / "soco" / "music_services" / "browser" / "music_services.json"

# Item types the playback builder understands (see browser/playback.py).
PLAYABLE_TYPES = ("track", "stream", "program", "show", "episode", "audiobook")
# Item types to prefer when exercising getMediaMetadata: radio-station
# ``program`` items often are not resolvable even though tracks/streams are.
_METADATA_PREFERENCE = ("track", "stream", "episode", "show", "program", "audiobook")

_RESULT_FIELDS = ("configured", "accounts", "item_types", "tests", "per_account_tests")
_HOUSEHOLD_HASH_CHARS = 12


def _household_key(speaker):
    """Return a short, non-reversible key identifying the household."""
    digest = hashlib.sha256(speaker.household_id.encode("utf-8")).hexdigest()
    return digest[:_HOUSEHOLD_HASH_CHARS]


def _result_fields(entry):
    """Extract the per-service test outcome from a tested catalogue entry."""
    return {key: entry[key] for key in _RESULT_FIELDS if key in entry}


def _merge_household_results(previous, run_results):
    """Merge a run's results into previous results without downgrades.

    A service that is not currently added is recorded as not-added, but a
    previously recorded configured result must not be overwritten by that
    (the account may simply have been removed between runs, e.g. while
    cycling services to stay under the household's connected-service cap).
    Only a service the run actually exercised with an account replaces the
    prior result.
    """
    merged = dict(previous)
    for service_id, new in run_results.items():
        prior = merged.get(service_id)
        new_was_added = new.get("accounts", 0) > 0
        prior_was_added = bool(prior and prior.get("accounts", 0) > 0)
        if not new_was_added and prior_was_added:
            # Never downgrade a previously-working result to not-added.
            continue
        merged[service_id] = new
    return merged


def load_households(path):
    """Load previously recorded per-household results, or an empty dict.

    A legacy flat ``music_services.json`` (results embedded in the service
    list, from before multi-household support) is migrated under a
    ``"legacy"`` placeholder key so its results are preserved.
    """
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    households = data.get("households")
    if isinstance(households, dict):
        return households
    results = {
        str(entry["id"]): _result_fields(entry)
        for entry in data.get("services", [])
        if "id" in entry
    }
    return {"legacy": {"generated_at": data.get("generated_at"), "results": results}}


def pick_speaker(ip):
    """Return the SoCo instance to test against, prompting when needed."""
    zones = discovery.discover(timeout=8)
    if not zones:
        print("No Sonos zones found on the network.")
        sys.exit(1)

    zones = sorted(zones, key=lambda zone: zone.player_name)
    if ip:
        for zone in zones:
            if zone.ip_address == ip:
                return zone
        print("No zone at %s. Available zones:" % ip)
        for zone in zones:
            print("  %-16s %s" % (zone.player_name, zone.ip_address))
        sys.exit(1)

    if len(zones) == 1:
        print("Using speaker: %s" % zones[0].player_name)
        return zones[0]

    print("Select a speaker to test on:")
    for index, zone in enumerate(zones, start=1):
        print("  %d) %-20s %s" % (index, zone.player_name, zone.ip_address))
    while True:
        choice = input("Choice [1-%d]: " % len(zones)).strip()
        try:
            selected = zones[int(choice) - 1]
            print("Using speaker: %s" % selected.player_name)
            return selected
        except (ValueError, IndexError):
            print("Please enter a number between 1 and %d." % len(zones))


def service_catalogue():
    """Return every advertised service as a list of dicts, sorted by id."""
    catalogue = []
    for service in MusicService._get_music_services_data().values():
        catalogue.append(
            {
                "id": int(service["Id"]),
                "name": service["Name"],
                "auth": service.get("Auth", ""),
                "version": service.get("Version", ""),
                "capabilities": service.get("Capabilities", ""),
                "uri": service.get("SecureUri", service.get("Uri", "")),
                "container_type": service.get("ContainerType", ""),
            }
        )
    return sorted(catalogue, key=lambda entry: entry["id"])


def _filter_catalogue(catalogue, services, accounts_by_service):
    """Restrict the catalogue to the services named in ``services``.

    ``services`` is a comma-separated string of service names (matched
    case-insensitively), plus the special tokens ``configured`` (every service
    with a configured account) and ``anonymous`` (every anonymous service).
    """
    if not services:
        return catalogue
    tokens = {token.strip().lower() for token in services.split(",") if token.strip()}
    names = set(tokens)
    if "configured" in tokens:
        names.discard("configured")
        names.update(
            entry["name"].lower()
            for entry in catalogue
            if entry["id"] in accounts_by_service
        )
    if "anonymous" in tokens:
        names.discard("anonymous")
        names.update(
            entry["name"].lower() for entry in catalogue if entry["auth"] == "Anonymous"
        )
    filtered = [entry for entry in catalogue if entry["name"].lower() in names]
    if not filtered:
        print("No services matched %r." % services)
        sys.exit(1)
    return filtered


def _terminal_state(speaker):
    """Poll until the transport reaches a terminal state or times out."""
    deadline = time.time() + PLAY_WAIT_SECONDS
    state = speaker.get_current_transport_info()["current_transport_state"]
    while state not in ("PLAYING", "STOPPED", "PAUSED_PLAYBACK"):
        if time.time() > deadline:
            break
        time.sleep(1.5)
        state = speaker.get_current_transport_info()["current_transport_state"]
    return state


def _group_signature(speaker):
    """Return a stable signature of the speaker's current group topology."""
    group = speaker.group
    if group is None:
        return speaker.uid, (speaker.uid,)
    coordinator = group.coordinator or speaker
    return coordinator.uid, tuple(sorted(member.uid for member in group.members))


def _snapshot_playback_group(speaker):
    """Snapshot transport plus per-zone audio state immediately before a test.

    Playback on a grouped player affects the group coordinator and can be
    audible on every member, so every member is snapshotted. ``Snapshot``
    restores the coordinator's URI/metadata, queue position, transport state,
    volume and mute, while member snapshots restore their individual audio
    settings.
    """
    group = speaker.group
    coordinator = (group.coordinator if group is not None else None) or speaker
    members = list(group.members) if group is not None else [speaker]
    snapshots = []
    # Restore the coordinator first; keep the remaining member snapshots only
    # for their individual volume/mute/EQ state.
    members.sort(key=lambda member: member.uid != coordinator.uid)
    for member in members:
        snapshot = Snapshot(member)
        snapshot.snapshot()
        # Snapshot already preserves queue position. For a seekable URI played
        # outside the queue, keep the current relative position as well so a
        # playback test does not silently restart the user's track at 0:00.
        snapshot.verifier_track_position = None
        if snapshot.is_coordinator and not snapshot.is_playing_queue:
            try:
                track = member.get_current_track_info()
            except Exception:  # pylint: disable=broad-except
                track = None
            if track:
                position = track.get("position") or ""
                duration = track.get("duration") or ""
                if position not in (
                    "",
                    "0:00:00",
                    "NOT_IMPLEMENTED",
                ) and duration not in (
                    "",
                    "0:00:00",
                    "NOT_IMPLEMENTED",
                ):
                    snapshot.verifier_track_position = position
        snapshots.append(snapshot)
    return coordinator, snapshots, _group_signature(speaker)


def _unsafe_restore_reason(coordinator_snapshot):
    """Explain why replacing the current transport would not be reversible."""
    uri = coordinator_snapshot.media_uri or ""
    if coordinator_snapshot.is_playing_cloud_queue:
        return "current cloud queue cannot be reconstructed safely"
    if uri.startswith("x-sonos-vli:"):
        return (
            "current provider-controlled/DirectControl session cannot be "
            "reconstructed safely"
        )
    return ""


def _cap_group_volume(snapshots, volume):
    """Cap every audible group member without ever increasing its volume."""
    changed = []
    for snapshot in snapshots:
        if snapshot.volume is None or snapshot.volume <= volume:
            continue
        try:
            snapshot.device.volume = volume
            changed.append(snapshot.device.player_name)
        except Exception as error:  # pylint: disable=broad-except
            raise MusicServiceException(
                "could not cap %s at volume %d: %s"
                % (snapshot.device.player_name, volume, _scrub(error))
            ) from error
    return changed


def _restore_playback_group(speaker, coordinator, snapshots, group_signature):
    """Stop the test and restore the state captured immediately before it."""
    errors = []
    try:
        coordinator.stop()
    except Exception as error:  # pylint: disable=broad-except
        errors.append("stop: %s" % _scrub(error))

    # Keep the whole group muted while reinstating its transport. Snapshot
    # restores PLAYING sources by calling play(), and muting first prevents a
    # loud burst at the old track's beginning before its saved position is
    # reinstated. Original mute states are restored after every source/state
    # operation below is complete.
    original_mutes = []
    for snapshot in snapshots:
        original_mutes.append((snapshot, snapshot.mute))
        try:
            snapshot.device.mute = True
        except Exception as error:  # pylint: disable=broad-except
            errors.append(
                "mute %s for restore: %s" % (snapshot.device.player_name, _scrub(error))
            )
        snapshot.mute = True

    # Coordinator first so the old transport is back before member volumes.
    for snapshot in snapshots:
        try:
            snapshot.restore()
            if snapshot.is_coordinator and snapshot.verifier_track_position:
                snapshot.device.seek(snapshot.verifier_track_position)
            # Snapshot restores PLAYING and STOPPED explicitly. Recreate a
            # paused transport as well instead of leaving the restored source
            # merely stopped.
            if (
                snapshot.is_coordinator
                and snapshot.transport_state == "PAUSED_PLAYBACK"
            ):
                snapshot.device.play()
                snapshot.device.pause()
        except Exception as error:  # pylint: disable=broad-except
            errors.append(
                "restore %s: %s" % (snapshot.device.player_name, _scrub(error))
            )

    for snapshot, original_mute in original_mutes:
        snapshot.mute = original_mute
        try:
            snapshot.device.mute = original_mute
        except Exception as error:  # pylint: disable=broad-except
            errors.append(
                "restore mute %s: %s" % (snapshot.device.player_name, _scrub(error))
            )

    try:
        current_group = _group_signature(speaker)
    except Exception as error:  # pylint: disable=broad-except
        errors.append("verify group: %s" % _scrub(error))
    else:
        if current_group != group_signature:
            # This verifier never changes grouping. A mismatch therefore
            # means topology changed externally while the test was running;
            # do not overwrite a user's concurrent grouping action.
            errors.append("group topology changed during playback test")
    return errors


def browse_items(browser, start="root", depth=0, budget=None, deadline=None):
    """Yield (depth, item) pairs by descending the browse tree, bounded."""
    if budget is None:
        budget = {"n": 0}
    if depth > MAX_BROWSE_DEPTH or budget["n"] > MAX_BROWSE_ITEMS:
        return
    if deadline is not None and time.time() > deadline:
        return
    budget["n"] += 1
    try:
        result = browser.get_metadata(start)
    except MusicServiceException:
        return
    collections = []
    for item in result.items:
        yield depth, item
        if item.kind == "mediaCollection" and item.can_browse:
            collections.append(item)
    for item in collections:
        for found in browse_items(browser, item, depth + 1, budget, deadline):
            yield found


def distinct_playable_items(browser, deadline=None):
    """Return one representative item per playable item type."""
    found = {}
    for _depth, item in browse_items(browser, deadline=deadline):
        item_type = normalize_item_type(item.item_type)
        if item.kind == "mediaMetadata" and item_type in PLAYABLE_TYPES:
            found.setdefault(item_type, item)
            if len(found) >= TYPES_TO_FIND:
                break
    return found


_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def _scrub(error):
    """Redact personally identifying details from an error message."""
    message = str(error)
    return _IP_RE.sub("x.x.x.x", message.strip())


def test_browse(browser):
    try:
        result = browser.get_metadata()
        return {"status": "ok", "detail": "%d items" % result.count}
    except MusicServiceException as error:
        return {"status": "error", "detail": _scrub(error)}


def test_search(browser):
    try:
        categories = browser.available_search_categories or []
    except MusicServiceException as error:
        return {"status": "error", "detail": _scrub(error)}
    if not categories:
        return {"status": "skipped", "detail": "no search categories"}
    # Exercise the first couple of categories; a category may legitimately
    # return no results, so only a raised fault is recorded as an error.
    for category in categories[:2]:
        try:
            browser.search(category, "a")
            return {"status": "ok", "detail": "category %r" % category}
        except MusicServiceException as error:
            return {"status": "error", "detail": _scrub(error)}
    return {"status": "skipped", "detail": "no searchable category"}


def _pick_metadata_item_type(items):
    """Pick the item type to exercise for the metadata test."""
    for item_type in _METADATA_PREFERENCE:
        if item_type in items:
            return item_type
    return sorted(items)[0]


def test_metadata(browser, item):
    try:
        metadata = browser.get_media_metadata(item)
        if not metadata:
            return {"status": "error", "detail": "empty result"}
        return {
            "status": "ok",
            "detail": "itemType=%s mime=%s"
            % (
                metadata.get("itemType"),
                metadata.get("mimeType"),
            ),
        }
    except MusicServiceException as error:
        return {"status": "error", "detail": _scrub(error)}


def test_playback(browser, speaker, item, volume, play_seconds):
    try:
        coordinator, snapshots, group_signature = _snapshot_playback_group(speaker)
    except Exception as error:  # pylint: disable=broad-except
        return {
            "status": "skipped",
            "detail": "could not snapshot current playback safely: %s" % _scrub(error),
        }

    coordinator_snapshot = next(
        snapshot for snapshot in snapshots if snapshot.device.uid == coordinator.uid
    )
    unsafe_reason = _unsafe_restore_reason(coordinator_snapshot)
    if unsafe_reason:
        return {"status": "skipped", "detail": unsafe_reason}

    result = None
    try:
        _cap_group_volume(snapshots, volume)
        browser.play(item, device=coordinator)
    except MusicServiceException as error:
        result = {"status": "error", "detail": _scrub(error)}
    except Exception as error:  # pylint: disable=broad-except
        result = {"status": "error", "detail": _scrub(error)}
    else:
        state = _terminal_state(coordinator)
        result = {
            "status": "ok" if state == "PLAYING" else "error",
            "detail": state,
            "item_id": item.item_id,
            "title": item.title,
        }
        if state == "PLAYING" and play_seconds:
            time.sleep(play_seconds)
    finally:
        restore_errors = _restore_playback_group(
            speaker, coordinator, snapshots, group_signature
        )

    if restore_errors:
        detail = result.get("detail", "") if result else ""
        suffix = "restore warning: %s" % "; ".join(restore_errors)
        if detail:
            suffix = "%s; %s" % (detail, suffix)
        return {
            "status": "error",
            "detail": suffix,
            "item_id": item.item_id,
            "title": item.title,
        }
    return result


def test_configured_service(
    speaker, entry, account, run_playback, playback_volume=3, play_seconds=3.0
):
    results = {"tests": {}}
    try:
        browser = MusicServiceBrowser(entry["name"], account=account, device=speaker)
    except MusicServiceException as error:
        results["tests"]["construct"] = {"status": "error", "detail": _scrub(error)}
        return results

    deadline = time.time() + SERVICE_DEADLINE_SECONDS
    results["tests"]["browse"] = test_browse(browser)
    results["tests"]["search"] = test_search(browser)

    items = distinct_playable_items(browser, deadline)
    results["item_types"] = sorted(items)
    if items:
        metadata_type = _pick_metadata_item_type(items)
        results["tests"]["metadata"] = test_metadata(browser, items[metadata_type])
    else:
        results["tests"]["metadata"] = {"status": "skipped", "detail": "no items"}

    if run_playback:
        playback = {}
        for item_type in sorted(items):
            playback[item_type] = test_playback(
                browser,
                speaker,
                items[item_type],
                playback_volume,
                play_seconds,
            )
        results["tests"]["playback"] = playback
    return results


def test_unconfigured_service(speaker, entry, run_playback):
    """Record the failure mode for a service with no configured account.

    Every non-``Anonymous`` service needs a household account; without one the
    browser raises :class:`MusicServiceAuthException` at construction, so there
    is nothing to browse or play. That is recorded here without constructing a
    browser: fetching accounts re-subscribes to the topology for every service,
    which would be needlessly slow for the ~90 unconfigured providers.
    """
    return {
        "accounts": [],
        "tests": {
            "construct": {
                "status": "auth_required",
                "detail": "not added to this household",
            },
            "browse": {"status": "skipped", "detail": "not added"},
            "search": {"status": "skipped", "detail": "not added"},
            "metadata": {"status": "skipped", "detail": "not added"},
        },
    }


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("Wrote %s" % path)


# Status value -> emoji used in the VERIFIED.md matrix.
_STATUS_EMOJI = {
    "ok": "✅",
    "error": "❌",
    "failed": "❌",
    "auth_required": "🔒",
    "skipped": "⏭️",
    "mixed": "⚠️",
}


def _emoji(status):
    """Return the emoji for a status value, or the value unchanged."""
    return _STATUS_EMOJI.get(status, status or "-")


def _merge_statuses(statuses):
    """Merge per-household statuses into a single verdict.

    Only households that actually exercised a dimension decide between
    ``ok``/``error``/``mixed``; households where the service was not added
    are ignored for that dimension.
    """
    exercised = [s for s in statuses if s in ("ok", "error", "failed")]
    if exercised:
        if all(s == "ok" for s in exercised):
            return "ok"
        if all(s in ("error", "failed") for s in exercised):
            return "error"
        return "mixed"
    if any(s in ("auth_required", "not_added") for s in statuses):
        return "auth_required"
    return "skipped"


def _effective_result(result):
    """Return one household's per-dimension statuses.

    An account-backed service that is not added never exercised browse,
    search, metadata or playback, so those dimensions are reported as
    ``auth_required``. Anonymous services that are not added still browse
    (through a synthetic account), so their recorded statuses are used.
    """
    tests = result.get("tests", {})
    if tests.get("construct", {}).get("status") == "auth_required":
        return {
            "browse": "auth_required",
            "search": "auth_required",
            "metadata": "auth_required",
            "playback": {},
        }
    return {
        "browse": tests.get("browse", {}).get("status", ""),
        "search": tests.get("search", {}).get("status", ""),
        "metadata": tests.get("metadata", {}).get("status", ""),
        "playback": tests.get("playback", {}),
    }


def write_verified_markdown(path, services, households):
    """Write the merged, multi-household VERIFIED.md matrix."""
    generated = datetime.datetime.now().isoformat(timespec="seconds")
    lines = [
        "# Music-service verification",
        "",
        "Generated %s. Results are merged across every recorded household and"
        % generated,
        "the firmware they were recorded against; re-run",
        "``python examples/verify_music_services.py`` to refresh.",
        "",
        "Legend: ✅ verified working · ❌ broken · 🔒 account required · "
        "⏭️ not exercised · ⚠️ warning",
        "",
        "| Service | Auth | Homes | Browse | Search | Metadata | Playback | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    households = households or {}
    for entry in services:
        service_id = str(entry["id"])
        results = [
            data["results"][service_id]
            for data in households.values()
            if service_id in data.get("results", {})
        ]
        if not results:
            lines.append(
                "| %s | %s | - | ⏭️ | ⏭️ | ⏭️ | ⏭️ | no results |"
                % (entry["name"], entry["auth"])
            )
            continue

        added = [r for r in results if r.get("accounts", 0) > 0]
        effective = [_effective_result(r) for r in results]
        browse = _merge_statuses([r["browse"] for r in effective])
        search = _merge_statuses([r["search"] for r in effective])
        metadata = _merge_statuses([r["metadata"] for r in effective])

        playback = {}
        for result in effective:
            for item_type, item_result in result["playback"].items():
                playback.setdefault(item_type, []).append(item_result.get("status"))
        if playback:
            parts = []
            for item_type, statuses in sorted(playback.items()):
                parts.append("%s=%s" % (item_type, _emoji(_merge_statuses(statuses))))
            playback_cell = ", ".join(parts)
        else:
            playback_cell = "⏭️"

        notes = []
        if not added:
            notes.append("🔒 not added")
        merged = [browse, search, metadata]
        merged += [_merge_statuses(statuses) for statuses in playback.values()]
        if "mixed" in merged:
            notes.append("⚠️ mixed across households")
        if added and not any(r.get("item_types") for r in results):
            notes.append("⚠️ no playable items")

        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                entry["name"],
                entry["auth"],
                len(results),
                _emoji(browse),
                _emoji(search),
                _emoji(metadata),
                playback_cell,
                "; ".join(notes) or "-",
            )
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print("Wrote %s" % path)


def _summarize(entry):
    """Return a compact one-line result summary for an entry."""
    tests = entry.get("tests", {})
    browse = tests.get("browse", {}).get("status", "-")
    search = tests.get("search", {}).get("status", "-")
    metadata = tests.get("metadata", {}).get("status", "-")
    playback = tests.get("playback", {})
    if playback:
        play = ", ".join(
            "%s=%s" % (item_type, "OK" if result.get("status") == "ok" else "FAIL")
            for item_type, result in sorted(playback.items())
        )
    else:
        play = "SKIP"
    return "browse=%s search=%s metadata=%s playback={%s}" % (
        browse,
        search,
        metadata,
        play,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", help="Speaker IP address (skip the prompt)")
    parser.add_argument(
        "--no-play",
        action="store_true",
        help="Skip playback tests (browse/search/metadata only)",
    )
    parser.add_argument(
        "--volume",
        type=int,
        default=DEFAULT_TEST_VOLUME,
        help=(
            "Maximum volume for playback tests across every member of the "
            "selected speaker's group (default: %(default)s; never raises a "
            "member above its current volume)"
        ),
    )
    parser.add_argument(
        "--play-seconds",
        type=float,
        default=DEFAULT_PLAY_SECONDS,
        help="Seconds to leave each successful playback audible (default: %(default)s)",
    )
    parser.add_argument("--json", default=str(DEFAULT_JSON), help="JSON output path")
    parser.add_argument(
        "--verified", default=str(DEFAULT_VERIFIED_MD), help="VERIFIED.md output path"
    )
    parser.add_argument(
        "--services",
        help=(
            "Comma-separated service names to test (default: all). Also accepts "
            "'configured' (every service with an account) and 'anonymous' "
            "(every anonymous service)."
        ),
    )
    args = parser.parse_args()
    if not 0 <= args.volume <= 100:
        parser.error("--volume must be between 0 and 100")
    if args.play_seconds < 0:
        parser.error("--play-seconds must be >= 0")

    speaker = pick_speaker(args.ip)
    run_playback = not args.no_play

    full_catalogue = service_catalogue()
    configured_accounts = MusicServiceBrowser.get_accounts(device=speaker)
    accounts_by_service = {}
    for account in configured_accounts:
        accounts_by_service.setdefault(account.service_id, []).append(account)
    catalogue = _filter_catalogue(full_catalogue, args.services, accounts_by_service)
    # The loop below attaches per-household results to each entry; copy the
    # filtered list so the pristine catalogue survives for the report.
    catalogue = [dict(entry) for entry in catalogue]

    print(
        "Testing %d services (%d configured accounts)..."
        % (len(catalogue), len(configured_accounts)),
        flush=True,
    )
    for entry in catalogue:
        service_id = entry["id"]
        accounts = accounts_by_service.get(service_id, [])
        if accounts:
            # Any service with a household account (added), including added
            # anonymous services, is tested with that account.
            per_account = [
                test_configured_service(
                    speaker,
                    entry,
                    account,
                    run_playback,
                    playback_volume=args.volume,
                    play_seconds=args.play_seconds,
                )
                for account in accounts
            ]
            entry["configured"] = True
            entry["accounts"] = len(accounts)
            # Merge: a service is considered working if any account works.
            merged = {"tests": {}}
            for result in per_account:
                for key, value in result["tests"].items():
                    existing = merged["tests"].get(key)
                    if existing is None or existing.get("status") != "ok":
                        if value.get("status") == "ok" or existing is None:
                            merged["tests"][key] = value
            # Preserve item types from the first account that found any.
            for result in per_account:
                if result.get("item_types"):
                    merged["item_types"] = result["item_types"]
                    break
            entry["tests"] = merged["tests"]
            entry["item_types"] = merged.get("item_types", [])
            entry["per_account_tests"] = [
                {"account": index, "tests": result["tests"]}
                for index, result in enumerate(per_account, start=1)
            ]
        elif entry["auth"] == "Anonymous":
            # Anonymous but not added: a synthetic account still lets the
            # browser browse, but playback is expected to fail. Record the
            # empirical result so the report shows it is not added. The
            # synthetic account is passed explicitly to avoid re-fetching
            # the household accounts for every anonymous service.
            synthetic = ConfiguredMusicServiceAccount(entry["id"], 0, "")
            result = test_configured_service(
                speaker,
                entry,
                synthetic,
                run_playback,
                playback_volume=args.volume,
                play_seconds=args.play_seconds,
            )
            entry["configured"] = False
            entry["accounts"] = 0
            entry["tests"] = result["tests"]
            entry["tests"]["construct"] = {
                "status": "not_added",
                "detail": "not added to this household",
            }
            entry["item_types"] = result.get("item_types", [])
        else:
            entry["configured"] = False
            entry["accounts"] = 0
            result = test_unconfigured_service(speaker, entry, run_playback)
            entry["tests"] = result["tests"]
            entry["item_types"] = result.get("item_types", [])

        print("  %-28s %s" % (entry["name"], _summarize(entry)), flush=True)

    now = datetime.datetime.now().isoformat(timespec="seconds")
    households = load_households(args.json)
    key = _household_key(speaker)
    run_results = {str(entry["id"]): _result_fields(entry) for entry in catalogue}
    previous = households.get(key, {}).get("results", {})
    previous = _merge_household_results(previous, run_results)
    households[key] = {"generated_at": now, "results": previous}

    payload = {
        "generated_at": now,
        "services": full_catalogue,
        "households": households,
    }
    write_json(args.json, payload)
    write_verified_markdown(args.verified, full_catalogue, households)


if __name__ == "__main__":
    main()
