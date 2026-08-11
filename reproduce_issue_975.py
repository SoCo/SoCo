"""Live verification of the issue #975 fix (branch soco-fixes-1).

Drives the Sonos system itself - no manual interaction needed. It subscribes
to ZoneGroupTopology events, programmatically joins and unjoins two speakers,
and verifies that `soco.all_groups` tracks the changes *purely from events*:
while the subscription is active, the poll path is patched to raise, so any
topology update visible via `all_groups` must have come from a
zone_group_state event (via ZoneGroupTopology._update_cache_on_event).

Usage: python reproduce_issue_975.py
"""

import sys
import time

from soco import discovery
from soco.events import event_listener

FAILURES = []


def wait_for(predicate, what, timeout=20.0):
    """Wait up to `timeout` seconds for predicate() to return True."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    print(f"  TIMEOUT waiting for: {what}")
    return False


def groups_label(groups, device):
    """Human-readable description of the groups containing `device`."""
    labels = [f"    {g.label}" for g in groups if device in g]
    return "\n".join(labels) if labels else "    (not in any group)"


def main():
    print("== Step 1: discover Sonos system ==")
    devices = discovery.discover()
    if not devices:
        print("FAIL: no Sonos devices found on the network")
        sys.exit(1)
    print(f"  Found {len(devices)} device(s)")

    # Use the largest household
    households = {}
    for d in devices:
        households.setdefault(d.household_id, []).append(d)
    household = max(households.values(), key=len)
    print(f"  Using household with {len(household)} device(s):")
    for d in household:
        print(f"    {d.ip_address} {d.player_name}")
    if len(household) < 2:
        print("FAIL: need at least 2 speakers in one household to test grouping")
        sys.exit(1)

    # Populate the shared ZoneGroupState with one ordinary poll
    zgs = household[0].zone_group_state
    zgs.clear_cache()
    baseline = household[0].all_groups
    print(f"\n== Step 2: baseline topology ({len(baseline)} group(s)) ==")
    for g in sorted(baseline, key=lambda g: g.label):
        print(f"    {g.label}")

    # Event source and join target must be usable speakers
    usable = [
        d
        for d in household
        if not getattr(d, "_is_satellite", False) and not getattr(d, "_is_bridge", False)
    ]
    if len(usable) < 2:
        print("FAIL: need at least 2 non-satellite speakers in the household")
        sys.exit(1)
    soco = usable[0]

    # Prefer a plain member of another group, else a solo speaker
    other = None
    for d in usable[1:]:
        grp = next((g for g in baseline if d in g), None)
        if grp is not None and grp.coordinator is not d and grp.coordinator is not soco:
            other = d
            break
    if other is None:
        other = usable[1]
    print(f"\n  Event source: {soco.player_name} ({soco.ip_address})")
    print(f"  Join target:  {other.player_name} ({other.ip_address})")

    # Remember original membership for restoration
    other_group = next((g for g in baseline if other in g), None)
    restore_coordinator = None
    if other_group is not None and other_group.coordinator is not other:
        restore_coordinator = other_group.coordinator
        print(
            f"  (restore: rejoin {other.player_name} to "
            f"{restore_coordinator.player_name})"
        )

    print(f"\n== Step 3: subscribe to ZoneGroupTopology events ==")
    sub = soco.zoneGroupTopology.subscribe(auto_renew=True)
    print(f"  Subscribed (sid={sub.sid})")

    try:
        # With the subscription active, poll() short-circuits. The initial
        # event is the only possible source of the shared state.
        print("\n== Step 4: initial event must populate the shared ZoneGroupState ==")
        ok = wait_for(lambda: len(soco.all_groups) > 0, "initial zone_group_state event")
        if not ok:
            print("  FAIL: shared ZoneGroupState never populated from the initial event")
            FAILURES.append("initial event did not populate the shared ZoneGroupState")
        else:
            print(
                f"  PASS: shared state has {len(soco.all_groups)} group(s) "
                "from the initial event alone (no poll)"
            )

        # From here on, a poll would mean the fix is broken: any topology
        # change must arrive via the event hook.
        def _no_poll(*_args, **_kwargs):
            raise RuntimeError(
                "GetZoneGroupState() called during verification - topology "
                "changed via a poll, not via a zone_group_state event"
            )

        soco.zoneGroupTopology.GetZoneGroupState = _no_poll

        print(f"\n== Step 5: join {other.player_name} -> {soco.player_name} ==")
        other.unjoin()
        other.join(soco)
        ok = wait_for(
            lambda: any(soco in g and other in g for g in soco.all_groups),
            f"a group containing {soco.player_name} and {other.player_name}",
        )
        print("  all_groups after join:")
        print(groups_label(soco.all_groups, soco))
        if ok:
            print("  PASS: join event updated all_groups")
        else:
            print("  FAIL: all_groups did not reflect the join")
            FAILURES.append("join event did not update all_groups")

        print(f"\n== Step 6: unjoin {other.player_name} ==")
        other.unjoin()
        ok = wait_for(
            lambda: not any(soco in g and other in g for g in soco.all_groups)
            and any(other in g and len(g.members) == 1 for g in soco.all_groups),
            f"{other.player_name} to return to its own group",
        )
        print("  all_groups after unjoin:")
        print(groups_label(soco.all_groups, soco))
        if ok:
            print("  PASS: unjoin event updated all_groups")
        else:
            print("  FAIL: all_groups did not reflect the unjoin")
            FAILURES.append("unjoin event did not update all_groups")

    finally:
        print("\n== Step 7: restore original topology ==")
        try:
            other.unjoin()
            if restore_coordinator is not None:
                other.join(restore_coordinator)
                wait_for(
                    lambda: any(
                        other in g and restore_coordinator in g for g in soco.all_groups
                    ),
                    "restore rejoin",
                    timeout=10,
                )
            print("  Done")
        except Exception as exc:  # pylint: disable=broad-except
            print(f"  WARNING: restore failed: {exc}")
        try:
            sub.unsubscribe()
            event_listener.stop()
        except Exception as exc:  # pylint: disable=broad-except
            print(f"  WARNING: cleanup failed: {exc}")

    print("\n=============================================")
    if FAILURES:
        print("RESULT: FAIL")
        for failure in FAILURES:
            print(f"  - {failure}")
        sys.exit(1)
    print("RESULT: PASS - all_groups tracked every topology change from events")
    print("=============================================")


if __name__ == "__main__":
    main()
