"""Tests for the alarms module."""

from datetime import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from soco.alarms import Alarm, Alarms, is_valid_recurrence
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
