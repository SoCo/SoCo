"""Tests for the alarms module."""


from soco.alarms import is_valid_recurrence


def test_recurrence():
    for recur in ("DAILY", "WEEKDAYS", "WEEKENDS", "ONCE"):
        assert is_valid_recurrence(recur)

    assert is_valid_recurrence("ON_1")
    assert is_valid_recurrence("ON_123412")
    assert not is_valid_recurrence("on_1")
    assert not is_valid_recurrence("ON_123456789")
    assert not is_valid_recurrence("ON_")
    assert not is_valid_recurrence(" ON_1")
