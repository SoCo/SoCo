"""Tests for the alarms module."""

from datetime import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError
from soco.alarms import Alarm, Alarms, is_valid_recurrence, remove_alarm_by_id
from soco.core import _ArgsSingleton
from soco.exceptions import SoCoException


@pytest.fixture(autouse=True)
def reset_alarms_singleton():
    """Reset the Alarms singleton between tests to prevent state leakage."""
    _ArgsSingleton._instances.pop("Alarms", None)
    yield
    _ArgsSingleton._instances.pop("Alarms", None)


def test_recurrence():
    for recur in ("DAILY", "WEEKDAYS", "WEEKENDS", "ONCE"):
        assert is_valid_recurrence(recur)

    assert is_valid_recurrence("ON_1")
    assert is_valid_recurrence("ON_123412")
    assert not is_valid_recurrence("on_1")
    assert not is_valid_recurrence("ON_123456789")
    assert not is_valid_recurrence("ON_")
    assert not is_valid_recurrence(" ON_1")


def test_alarms(moco):
    """Test loading and processing of alarms for an existing zone."""
    alarm_list_response = {
        "CurrentAlarmListVersion": "RINCON_test:14",
        "CurrentAlarmList": "<Alarms>"
        '<Alarm ID="14" StartTime="07:00:00" Duration="02:00:00" Recurrence="DAILY" '
        'Enabled="1" RoomUUID="RINCON_test" ProgramURI="x-rincon-buzzer:0" '
        'ProgramMetaData="" PlayMode="SHUFFLE_NOREPEAT" Volume="25" '
        'IncludeLinkedZones="0"/>'
        "</Alarms>",
    }
    moco.alarmClock.ListAlarms = MagicMock(return_value=alarm_list_response)
    # Create a mock zone with the correct uid
    mock_zone = MagicMock()
    mock_zone.uid = "RINCON_test"
    with patch.object(
        type(moco), "all_zones", new_callable=PropertyMock
    ) as mock_all_zones:
        mock_all_zones.return_value = [mock_zone]
        alarms = Alarms()
        alarms.update(moco)

    assert len(alarms.alarms) == 1
    assert len(alarms.alarms_skipped) == 0
    alarm = alarms.alarms["14"]
    assert alarm.zone == mock_zone
    assert alarm.start_time == time(7, 0, 0)
    assert alarm.duration == time(2, 0, 0)
    assert alarm.recurrence == "DAILY"
    assert alarm.enabled is True
    assert alarm.program_uri is None  # x-rincon-buzzer:0 is mapped to None in the code
    assert alarm.program_metadata == ""
    assert alarm.play_mode == "SHUFFLE_NOREPEAT"
    assert int(alarm.volume) == 25
    assert alarm.include_linked_zones is False
    assert alarm.room_uuid == "RINCON_test"


def test_alarms_skipped(moco):
    """Test loading and processing of alarms for a missing zone."""
    alarm_list_response = {
        "CurrentAlarmListVersion": "RINCON_test:14",
        "CurrentAlarmList": "<Alarms>"
        '<Alarm ID="14" StartTime="07:00:00" Duration="02:00:00" Recurrence="DAILY" '
        'Enabled="1" RoomUUID="RINCON_test_missing" ProgramURI="x-rincon-buzzer:0" '
        'ProgramMetaData="" PlayMode="SHUFFLE_NOREPEAT" Volume="25" '
        'IncludeLinkedZones="0"/>'
        "</Alarms>",
    }
    moco.alarmClock.ListAlarms = MagicMock(return_value=alarm_list_response)
    # Create a mock zone that does not match the RoomUUID in the alarm
    mock_zone = MagicMock()
    mock_zone.uid = "RINCON_test"
    with patch.object(
        type(moco), "all_zones", new_callable=PropertyMock
    ) as mock_all_zones:
        mock_all_zones.return_value = [mock_zone]
        alarms = Alarms()
        alarms.update(moco)

    # Verify that the alarm is skipped due to missing zone and stored in alarms_skipped
    assert len(alarms.alarms) == 0
    assert len(alarms.alarms_skipped) == 1
    alarm = alarms.alarms_skipped["14"]
    assert alarm.zone is None
    assert alarm.start_time == time(7, 0, 0)
    assert alarm.duration == time(2, 0, 0)
    assert alarm.recurrence == "DAILY"
    assert alarm.enabled is True
    assert alarm.program_uri is None  # x-rincon-buzzer:0 is mapped to None in the code
    assert alarm.program_metadata == ""
    assert alarm.play_mode == "SHUFFLE_NOREPEAT"
    assert int(alarm.volume) == 25
    assert alarm.include_linked_zones is False
    assert alarm.room_uuid == "RINCON_test_missing"

    # Add the missing zone and update skipped alarms
    mock_missing_zone = MagicMock()
    mock_missing_zone.uid = "RINCON_test_missing"
    alarms.update_skipped(mock_missing_zone)
    assert len(alarms.alarms) == 1
    assert len(alarms.alarms_skipped) == 0
    alarm = alarms.alarms["14"]
    assert alarm.zone == mock_missing_zone


def test_alarms_skipped_reuse_object_on_update(moco):
    """Verify that a skipped alarm's existing object is reused when update() is
    called again and the zone is now available, preserving object identity."""
    missing_uuid = "RINCON_test_missing"
    alarm_list_response = {
        "CurrentAlarmListVersion": "RINCON_test:14",
        "CurrentAlarmList": "<Alarms>"
        '<Alarm ID="14" StartTime="07:00:00" Duration="02:00:00" Recurrence="DAILY" '
        'Enabled="1" RoomUUID="{}" ProgramURI="x-rincon-buzzer:0" '
        'ProgramMetaData="" PlayMode="SHUFFLE_NOREPEAT" Volume="25" '
        'IncludeLinkedZones="0"/>'.format(missing_uuid) + "</Alarms>",
    }
    mock_present_zone = MagicMock()
    mock_present_zone.uid = "RINCON_test"
    mock_missing_zone = MagicMock()
    mock_missing_zone.uid = missing_uuid

    moco.alarmClock.ListAlarms = MagicMock(return_value=alarm_list_response)

    # First update: zone is missing, alarm goes to alarms_skipped
    with patch.object(
        type(moco), "all_zones", new_callable=PropertyMock
    ) as mock_all_zones:
        mock_all_zones.return_value = [mock_present_zone]
        alarms = Alarms()
        alarms.update(moco)

    assert len(alarms.alarms_skipped) == 1
    skipped_alarm_obj = alarms.alarms_skipped["14"]

    # Second update: version is higher, zone is now present
    alarm_list_response_v2 = dict(alarm_list_response)
    alarm_list_response_v2["CurrentAlarmListVersion"] = "RINCON_test:15"
    moco.alarmClock.ListAlarms = MagicMock(return_value=alarm_list_response_v2)

    with patch.object(
        type(moco), "all_zones", new_callable=PropertyMock
    ) as mock_all_zones:
        mock_all_zones.return_value = [mock_present_zone, mock_missing_zone]
        alarms.update(moco)

    assert len(alarms.alarms) == 1
    assert len(alarms.alarms_skipped) == 0
    resolved_alarm = alarms.alarms["14"]
    # The same object should have been updated in place, not replaced
    assert resolved_alarm is skipped_alarm_obj
    assert resolved_alarm.zone == mock_missing_zone


def test_save_raises_when_zone_is_none(moco):
    """Verify that save() raises SoCoException when zone is None."""
    alarm = Alarm(zone=None, room_uuid="RINCON_test_missing")
    alarm._alarm_id = None  # pylint: disable=protected-access
    with pytest.raises(SoCoException, match="zone is not set"):
        alarm.save()


def _alarm_list(version, alarm_id, room_uuid):
    return {
        "CurrentAlarmListVersion": version,
        "CurrentAlarmList": "<Alarms>"
        f'<Alarm ID="{alarm_id}" StartTime="07:00:00" Duration="" Recurrence="DAILY" '
        f'Enabled="1" RoomUUID="{room_uuid}" ProgramURI="x-rincon-buzzer:0" '
        'ProgramMetaData="" PlayMode="NORMAL" Volume="25" '
        'IncludeLinkedZones="0"/>'
        "</Alarms>",
    }


def _mock_zone(uid, household_id, alarm_id="1"):
    zone = MagicMock()
    zone.uid = uid
    zone.household_id = household_id
    zone.is_visible = True
    zone.all_zones = {zone}
    zone.alarmClock.ListAlarms.return_value = _alarm_list(f"{uid}:5", alarm_id, uid)
    zone.alarmClock.CreateAlarm.return_value = {"AssignedID": "6"}
    return zone


def test_alarms_singleton_per_household():
    """Alarms instances are singletons per household and Alarms() is separate."""
    assert Alarms() is Alarms()
    assert Alarms(household_id=None) is Alarms()
    assert Alarms("HH_A") is Alarms("HH_A")
    assert Alarms(household_id="HH_A") is Alarms("HH_A")
    assert Alarms("HH_A") is not Alarms("HH_B")
    assert Alarms("HH_A") is not Alarms()
    assert Alarms("HH_A").household_id == "HH_A"
    assert Alarms().household_id is None


def test_alarms_households_are_independent():
    """Households with the same alarm IDs update without affecting each other."""
    zone_a = _mock_zone("RINCON_A", "HH_A")
    zone_b = _mock_zone("RINCON_B", "HH_B")

    Alarms("HH_A").update(zone_a)
    Alarms("HH_B").update(zone_b)
    zone_a.alarmClock.ListAlarms.return_value = _alarm_list(
        "RINCON_A:7", "1", "RINCON_A"
    )
    Alarms("HH_A").update(zone_a)

    assert Alarms("HH_A")["1"].zone is zone_a
    assert Alarms("HH_A").last_alarm_list_version == "RINCON_A:7"
    assert Alarms("HH_B")["1"].zone is zone_b
    assert Alarms("HH_B").last_alarm_list_version == "RINCON_B:5"
    assert len(Alarms()) == 0


def test_alarms_update_rejects_other_household():
    """A household instance refuses to update from another household's zone."""
    zone_b = _mock_zone("RINCON_B", "HH_B")
    with pytest.raises(SoCoException, match="belongs to household HH_B, not HH_A"):
        Alarms("HH_A").update(zone_b)
    zone_b.alarmClock.ListAlarms.assert_not_called()


def test_alarms_update_without_zone_uses_household_zone():
    """update() without a zone picks a known zone from its own household."""
    zone_a = _mock_zone("RINCON_A", "HH_A")
    zone_b = _mock_zone("RINCON_B", "HH_B")
    with patch.dict(
        _ArgsSingleton._instances, {"SoCo": {("b",): zone_b, ("a",): zone_a}}
    ):
        Alarms("HH_A").update()
        with pytest.raises(SoCoException, match="No known zone in household HH_C"):
            Alarms("HH_C").update()

    zone_a.alarmClock.ListAlarms.assert_called_once()
    zone_b.alarmClock.ListAlarms.assert_not_called()


def test_alarm_save_and_remove_update_household_instance():
    """save() and remove() only update the household instance when it exists."""
    zone_a = _mock_zone("RINCON_A", "HH_A")
    household = Alarms("HH_A")
    household.update(zone_a)

    alarm = Alarm(zone_a)
    alarm.save()
    assert household["6"] is alarm
    assert household.last_alarm_list_version == "RINCON_A:6"

    alarm.remove()
    assert household.get("6") is None
    assert set(_ArgsSingleton._instances["Alarms"]) == {("HH_A",)}


def test_alarm_save_without_household_instance_skips_household_lookup():
    """save() does not query the household ID when only Alarms() is in use."""
    zone = MagicMock()
    type(zone).household_id = PropertyMock(side_effect=AssertionError)
    zone.uid = "RINCON_A"
    zone.alarmClock.CreateAlarm.return_value = {"AssignedID": "6"}

    alarm = Alarm(zone)
    alarm.save()

    assert Alarms()["6"] is alarm
    assert set(_ArgsSingleton._instances["Alarms"]) == {()}


def test_alarms_update_without_zone_skips_unreachable_zone():
    """update() without a zone skips known zones that cannot be reached."""
    stale = MagicMock()
    type(stale).household_id = PropertyMock(
        side_effect=RequestsConnectionError("offline")
    )
    zone_a = _mock_zone("RINCON_A", "HH_A")
    with patch.dict(
        _ArgsSingleton._instances, {"SoCo": {("s",): stale, ("a",): zone_a}}
    ):
        Alarms("HH_A").update()

    zone_a.alarmClock.ListAlarms.assert_called_once()


def test_alarm_remove_does_not_query_household():
    """remove() uses the instance that cached the alarm, before DestroyAlarm."""
    zone_a = _mock_zone("RINCON_A", "HH_A")
    household = Alarms("HH_A")
    household.update(zone_a)
    alarm = household["1"]
    type(zone_a).household_id = PropertyMock(
        side_effect=RequestsConnectionError("timeout")
    )

    alarm.remove()

    zone_a.alarmClock.DestroyAlarm.assert_called_once()
    assert household.get("1") is None
    assert alarm.alarm_id is None


def test_alarm_save_household_lookup_fails_before_create():
    """A failed household lookup in save() happens before CreateAlarm."""
    zone_a = _mock_zone("RINCON_A", "HH_A")
    household = Alarms("HH_A")
    household.update(zone_a)
    type(zone_a).household_id = PropertyMock(
        side_effect=RequestsConnectionError("timeout")
    )

    alarm = Alarm(zone_a)
    with pytest.raises(RequestsConnectionError):
        alarm.save()

    zone_a.alarmClock.CreateAlarm.assert_not_called()
    assert alarm.alarm_id is None


def test_remove_alarm_by_id_updates_shared_instance():
    """remove_alarm_by_id() removes the alarm from the shared Alarms()."""
    zone_a = _mock_zone("RINCON_A", "HH_A")
    Alarms("HH_A").update(zone_a)

    assert remove_alarm_by_id(zone_a, "1")

    assert Alarms().get("1") is None


def test_alarms_update_falls_back_when_last_zone_unreachable():
    """update() without a zone tries another household zone if the last fails."""
    zone_a1 = _mock_zone("RINCON_A1", "HH_A")
    zone_a2 = _mock_zone("RINCON_A2", "HH_A")
    household = Alarms("HH_A")
    household.update(zone_a1)
    zone_a1.alarmClock.ListAlarms.side_effect = RequestsConnectionError("offline")
    zone_a2.alarmClock.ListAlarms.return_value = _alarm_list(
        "RINCON_A1:7", "1", "RINCON_A1"
    )
    zone_a2.all_zones = {zone_a1, zone_a2}

    with patch.dict(
        _ArgsSingleton._instances, {"SoCo": {("a1",): zone_a1, ("a2",): zone_a2}}
    ):
        household.update()

    zone_a2.alarmClock.ListAlarms.assert_called_once()
    assert household.last_alarm_list_version == "RINCON_A1:7"
    assert household._last_zone_used is zone_a2  # pylint: disable=protected-access


def test_alarms_update_without_fallback_raises():
    """An unreachable zone still raises if it was passed in, or for Alarms()."""
    zone_a = _mock_zone("RINCON_A", "HH_A")
    Alarms("HH_A").update(zone_a)
    Alarms().update(zone_a)
    zone_a.alarmClock.ListAlarms.side_effect = RequestsConnectionError("offline")

    with pytest.raises(RequestsConnectionError):
        Alarms("HH_A").update(zone_a)
    with pytest.raises(RequestsConnectionError):
        Alarms().update()


def test_alarm_save_and_remove_after_reset_use_current_instance():
    """After a reset, save() and remove() do not use the cleared instance."""
    zone_a = _mock_zone("RINCON_A", "HH_A")
    old_household = Alarms("HH_A")
    old_household.update(zone_a)
    alarm = old_household["1"]

    # As soco_reset() does
    _ArgsSingleton._instances.pop("Alarms")
    household = Alarms("HH_A")
    household.update(zone_a)
    household.alarms["1"] = alarm

    alarm.remove()
    assert household.get("1") is None
    alarm.save()
    assert household["6"] is alarm
    assert old_household.get("6") is None
