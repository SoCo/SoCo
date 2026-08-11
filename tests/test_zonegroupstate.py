"""ZoneGroupState set mutations and snapshots must be mutually exclusive."""

import threading
from unittest import mock

import pytest

import soco.zonegroupstate as zgs_module
from soco.core import SoCo
from soco.zonegroupstate import ZoneGroupState

ZGS_PAYLOAD = """<ZoneGroups>
  <ZoneGroup Coordinator="RINCON_000XXX1400" ID="RINCON_000XXX1400:46">
    <ZoneGroupMember UUID="RINCON_000XXX1400"
        Location="http://192.168.1.101:1400/xml/device_description.xml"
        ZoneName="Living Room"/>
  </ZoneGroup>
</ZoneGroups>"""


def test_get_groups_blocks_while_payload_is_being_processed():
    """get_groups() must block while process_payload() is mutating the sets."""
    zgs = ZoneGroupState()
    zgs.poll = lambda soco: None  # Isolate the snapshot logic from polling

    update_started = threading.Event()
    release_writer = threading.Event()
    original_update = zgs.update_soco_instances

    def slow_update(tree):
        update_started.set()
        assert release_writer.wait(timeout=5)
        original_update(tree)

    zgs.update_soco_instances = slow_update

    writer = threading.Thread(
        target=zgs.process_payload,
        kwargs={"payload": ZGS_PAYLOAD, "source": "event", "source_ip": "192.168.1.1"},
    )
    writer.start()
    assert update_started.wait(timeout=5), "writer thread never started"

    # Writer is mid-mutation (holding the lock with the fix in place).
    reader_started = threading.Event()
    reader_finished = threading.Event()
    result = []

    def read_groups():
        reader_started.set()
        result.append(zgs.get_groups(None))
        reader_finished.set()

    reader = threading.Thread(target=read_groups)
    reader.start()
    try:
        assert reader_started.wait(timeout=5), "reader never started"
        # The reader is executing; it must not be able to finish.
        assert not reader_finished.wait(timeout=0.1), (
            "get_groups() returned while the ZGS was being mutated"
        )
    finally:
        release_writer.set()  # Don't leave the writer thread blocked on failure.
    writer.join(timeout=5)
    reader.join(timeout=5)
    assert not writer.is_alive(), "writer thread did not finish"
    assert not reader.is_alive(), "reader thread did not finish after release"
    assert result
    assert result[0] == zgs.groups


def test_poll_discards_result_when_subscription_becomes_active():
    """A poll result fetched before a subscription became active is discarded.

    Once eventing is live, events own the topology state, so the stale poll
    result must not be applied.
    """
    zgs = ZoneGroupState()
    soco = mock.Mock()
    soco.ip_address = "192.168.1.100"
    soco._is_satellite = False
    soco.zoneGroupTopology.GetZoneGroupState.return_value = {
        "ZoneGroupState": "<ZoneGroups/>"
    }

    with mock.patch.object(
        type(zgs),
        "has_subscriptions",
        new_callable=mock.PropertyMock,
        side_effect=[False, True],  # pre-fetch: none; post-fetch: active
    ):
        with mock.patch.object(zgs, "process_payload") as process:
            zgs.poll(soco)

    soco.zoneGroupTopology.GetZoneGroupState.assert_called_once()
    process.assert_not_called()
    assert zgs.total_requests == 1  # The discarded poll is still counted.


def test_process_payload_is_atomic():
    """A second payload must not interleave with one being processed."""
    zgs = ZoneGroupState()
    first_started = threading.Event()
    release_first = threading.Event()
    original_normalize = zgs_module.normalize_zgs_xml

    def blocking_normalize(payload):
        if not first_started.is_set():
            first_started.set()
            assert release_first.wait(timeout=5)
        return original_normalize(payload)

    with mock.patch.object(
        zgs_module, "normalize_zgs_xml", side_effect=blocking_normalize
    ):
        writer = threading.Thread(
            target=zgs.process_payload,
            kwargs={"payload": ZGS_PAYLOAD, "source": "event", "source_ip": "1"},
        )
        writer.start()
        assert first_started.wait(timeout=5), "first payload never started parsing"

        # The first payload is mid-normalize (holding the lock with the fix).
        second_started = threading.Event()
        second_done = threading.Event()

        def run_second():
            second_started.set()
            zgs.process_payload(ZGS_PAYLOAD, "event", "2")
            second_done.set()

        second = threading.Thread(target=run_second)
        second.start()
        try:
            assert second_started.wait(timeout=5), "second payload never started"
            # It must be blocked on the lock until the first payload finishes.
            assert not second_done.wait(timeout=0.2)
        finally:
            release_first.set()  # Don't leave the writer blocked on failure.
        writer.join(timeout=5)
        second.join(timeout=5)
        assert not writer.is_alive(), "writer thread did not finish"
        assert not second.is_alive(), "second thread did not finish"
    assert zgs.processed_count == 1  # Same payload: applied once, second deduped.


@pytest.mark.parametrize(
    ("property_name", "getter"),
    [
        ("all_groups", "get_groups"),
        ("all_zones", "get_all_zones"),
        ("visible_zones", "get_visible_zones"),
    ],
)
def test_zone_properties_use_synchronized_getters(property_name, getter):
    """SoCo's zone properties must use the lock-protected getters."""
    soco = SoCo("192.168.1.200")
    zgs = mock.Mock()
    with mock.patch.object(
        SoCo, "zone_group_state", new_callable=mock.PropertyMock, return_value=zgs
    ):
        getattr(soco, property_name)
    getattr(zgs, getter).assert_called_once_with(soco)
