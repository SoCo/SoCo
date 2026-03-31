"""Tests for the alarms module."""

import datetime
from datetime import time
from unittest.mock import MagicMock, patch, PropertyMock
from soco.alarms import Alarms, is_valid_recurrence


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
    with patch.object(type(moco), "all_zones", new_callable=PropertyMock) as mock_all_zones:
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
    # Create a mock zone with the correct uid
    mock_zone = MagicMock()
    mock_zone.uid = "RINCON_test"
    with patch.object(type(moco), "all_zones", new_callable=PropertyMock) as mock_all_zones:
        mock_all_zones.return_value = [mock_zone]
        alarms = Alarms()
        alarms.update(moco)
    
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
