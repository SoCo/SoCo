"""Live-network verification of the events_asyncio EventListener fix.

Exercises the deferred-stop refcounting path against a real Sonos zone
and asserts the structural invariants that the fix guarantees:

  1. After ``subscription.unsubscribe()``, ``stop_listening`` schedules a
     deferred stop. The listener's runtime resources (``site``, ``sock``,
     ``runner``, ``session``) remain alive during the grace window.

  2. A resubscribe within the grace window cancels the deferred stop and
     resumes the listener — the site/sock object identity is preserved
     and the "Event Listener resumed (deferred stop cancelled)" debug log
     fires. No teardown/rebuild churn.

  3. After a final unsubscribe with no resubscribe, the deferred stop
     runs once the grace window expires; listener resources are released
     and ``is_running`` returns to ``False``.

This script uses ``renderingControl`` rather than ``avTransport`` so it
does not interfere with consumer applications that may have an
``avTransport`` subscription active against the same zone (e.g. a
"now playing" orchestrator).

Pass a zone name (any zone on your local network) via ``--zone`` or set
``SOCO_ZONE``. Discovery uses SSDP, so the host must be on the same
LAN/VLAN as the Sonos players.

Usage:

    python examples/events_asyncio_verify_listener_fix.py --zone "Office"
    SOCO_ZONE="Living Room" python examples/events_asyncio_verify_listener_fix.py

Exit code 0 on PASS, non-zero on FAIL.
"""

import argparse
import asyncio
import logging
import os
import sys

import soco
from soco import config as soco_config
from soco import events_asyncio

# Must be set BEFORE any subscription is created so SoCo uses the asyncio
# event module rather than the threaded one.
soco_config.EVENTS_MODULE = events_asyncio


# Keep the test fast — production default is 5.0s.
SHORT_GRACE = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify events_asyncio EventListener fix against a live Sonos zone."
    )
    parser.add_argument(
        "--zone",
        default=os.environ.get("SOCO_ZONE"),
        help="Sonos zone name to bind against (default: $SOCO_ZONE).",
    )
    parser.add_argument(
        "--discover-timeout",
        type=float,
        default=3.0,
        help="SSDP discovery timeout in seconds (default: 3.0).",
    )
    return parser.parse_args()


async def main(zone_name: str | None, discover_timeout: float) -> int:
    if not zone_name:
        print("ERROR: --zone (or $SOCO_ZONE) is required", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Silence aiohttp's chatter; keep soco at DEBUG so the
    # "resumed (deferred stop cancelled)" line is visible.
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Shorten the grace window so the test runs quickly.
    events_asyncio.event_listener._stop_grace_seconds = SHORT_GRACE

    # Capture log records emitted by soco.events_asyncio so we can assert
    # on the structural log lines the patch emits.
    captured: list[str] = []

    class _RecordCapture(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    logging.getLogger("soco.events_asyncio").addHandler(_RecordCapture())

    zones = soco.discover(timeout=discover_timeout) or set()
    zone = next((z for z in zones if z.player_name == zone_name), None)
    if zone is None:
        print(
            f"ERROR: zone {zone_name!r} not found via SSDP. "
            f"Visible zones: {[z.player_name for z in zones] or 'none'}",
            file=sys.stderr,
        )
        return 1
    print(f"Using zone: {zone.player_name} @ {zone.ip_address}")

    listener = events_asyncio.event_listener

    print("\n--- Phase 1: initial subscribe ---")
    sub = await zone.renderingControl.subscribe(auto_renew=False)
    sub.callback = lambda ev: None
    site1 = listener.site
    sock1 = listener.sock
    print(f"sid={sub.sid} site={id(site1):x} sock={id(sock1):x}")
    assert listener.is_running, "listener should be running after subscribe"
    assert site1 is not None and sock1 is not None

    print("\n--- Phase 2: unsubscribe + immediate resubscribe (inside grace) ---")
    await sub.unsubscribe()
    pending = listener._stop_grace_task
    print(
        f"deferred task: {pending} "
        f"done={pending.done() if pending else 'n/a'}"
    )
    assert pending is not None and not pending.done(), (
        "stop_listening should have scheduled a deferred stop"
    )
    # Resources must still be alive during grace.
    assert listener.site is site1, "site should not be replaced during grace"
    assert listener.sock is sock1, "sock should not be replaced during grace"

    sub2 = await zone.renderingControl.subscribe(auto_renew=False)
    sub2.callback = lambda ev: None
    print(f"sid={sub2.sid} site={id(listener.site):x} sock={id(listener.sock):x}")
    assert listener.site is site1, "site identity must be preserved on resume"
    assert listener.sock is sock1, "sock identity must be preserved on resume"
    assert listener.is_running, "listener should be running after resume"
    assert any("resumed (deferred stop cancelled)" in m for m in captured), (
        "expected the 'resumed (deferred stop cancelled)' log line"
    )
    print("PASS: resubscribe inside grace reused the running listener")

    print("\n--- Phase 3: final unsubscribe, wait past grace, expect teardown ---")
    captured.clear()
    await sub2.unsubscribe()
    pending2 = listener._stop_grace_task
    assert pending2 is not None and not pending2.done()
    await asyncio.sleep(SHORT_GRACE + 0.3)
    assert not listener.is_running, "listener should have stopped after grace"
    assert listener.site is None, "site should be cleared"
    assert listener.sock is None, "sock should be cleared"
    print("PASS: deferred stop fired after grace expired")

    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main(args.zone, args.discover_timeout)))
