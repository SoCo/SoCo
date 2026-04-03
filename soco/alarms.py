"""This module contains classes relating to Sonos Alarms."""

import logging
import re
from datetime import datetime, timedelta

from . import discovery
from .core import _SocoSingletonBase, PLAY_MODES
from .exceptions import SoCoException
from .xml import XML

log = logging.getLogger(__name__)
TIME_FORMAT = "%H:%M:%S"
RECURRENCE_KEYWORD_EQUIVALENT = {
    "DAILY": "ON_0123456",
    "ONCE": "ON_",  # Never reoccurs
    "WEEKDAYS": "ON_12345",
    "WEEKENDS": "ON_06",
}


def is_valid_recurrence(text):
    """Check that ``text`` is a valid recurrence string.

    A valid recurrence string is  ``DAILY``, ``ONCE``, ``WEEKDAYS``,
    ``WEEKENDS`` or of the form ``ON_DDDDDD`` where ``D`` is a number from 0-6
    representing a day of the week (Sunday is 0), e.g. ``ON_034`` meaning
    Sunday, Wednesday and Thursday

    Args:
        text (str): the recurrence string to check.

    Returns:
        bool: `True` if the recurrence string is valid, else `False`.

    Examples:

        >>> from soco.alarms import is_valid_recurrence
        >>> is_valid_recurrence('WEEKENDS')
        True
        >>> is_valid_recurrence('')
        False
        >>> is_valid_recurrence('ON_132')  # Mon, Tue, Wed
        True
        >>> is_valid_recurrence('ON_666')  # Sat
        True
        >>> is_valid_recurrence('ON_3421') # Mon, Tue, Wed, Thur
        True
        >>> is_valid_recurrence('ON_123456789') # Too many digits
        False
    """
    if text in ("DAILY", "ONCE", "WEEKDAYS", "WEEKENDS"):
        return True
    return re.search(r"^ON_[0-6]{1,7}$", text) is not None


class Alarms(_SocoSingletonBase):
    """A class representing all known Sonos Alarms.

    Is a singleton and every `Alarms()` object will return the same instance.

    Example use:

        >>> get_alarms()
        {469: <Alarm id:469@22:07:41 at 0x7f5198797dc0>,
         470: <Alarm id:470@22:07:46 at 0x7f5198797d60>}
        >>> alarms = Alarms()
        >>> alarms.update()
        >>> alarms.alarms
        {469: <Alarm id:469@22:07:41 at 0x7f5198797dc0>,
         470: <Alarm id:470@22:07:46 at 0x7f5198797d60>}
        >>> for alarm in alarms:
        ...     alarm
        ...
        <Alarm id:469@22:07:41 at 0x7f5198797dc0>
        <Alarm id:470@22:07:46 at 0x7f5198797d60>
        >>> alarms[470]
        <Alarm id:470@22:07:46 at 0x7f5198797d60>
        >>> new_alarm = Alarm(zone)
        >>> new_alarm.save()
        471
        >>> new_alarm.recurrence = "ONCE"
        >>> new_alarm.save()
        471
        >>> alarms.alarms
        {469: <Alarm id:469@22:07:41 at 0x7f5198797dc0>,
         470: <Alarm id:470@22:07:46 at 0x7f5198797d60>,
         471: <Alarm id:471@22:08:40 at 0x7f51987f1b50>}
        >>> alarms[470].remove()
        >>> alarms.alarms
        {469: <Alarm id:469@22:07:41 at 0x7f5198797dc0>,
         471: <Alarm id:471@22:08:40 at 0x7f51987f1b50>}
        >>> for alarm in alarms:
        ...     alarm.remove()
        ...
        >>> a.alarms
        {}
    """

    _class_group = "Alarms"

    def __init__(self):
        """Initialize the instance."""
        self.alarms = {}
        self._last_zone_used = None
        self._last_alarm_list_version = None
        self.last_uid = None
        self.last_id = 0

    @property
    def last_alarm_list_version(self):
        """Return last seen alarm list version."""
        return self._last_alarm_list_version

    @last_alarm_list_version.setter
    def last_alarm_list_version(self, alarm_list_version):
        """Store alarm list version and store UID/ID values."""
        self.last_uid, last_id = alarm_list_version.split(":")
        self.last_id = int(last_id)
        self._last_alarm_list_version = alarm_list_version

    def __iter__(self):
        """Return an interator for all alarms."""
        yield from list(self.alarms.values())

    def __len__(self):
        """Return the number of alarms."""
        return len(self.alarms)

    def __getitem__(self, alarm_id):
        """Return the alarm by ID."""
        return self.alarms[alarm_id]

    def get(self, alarm_id):
        """Return the alarm by ID or None."""
        return self.alarms.get(alarm_id)

    def update(self, zone=None):
        """Update all alarms and current alarm list version.

        Raises:
            SoCoException: If the 'CurrentAlarmListVersion' value is unexpected.
                May occur if the provided zone is from a different household.
        """
        if zone is None:
            zone = self._last_zone_used or discovery.any_soco()

        self._last_zone_used = zone

        response = zone.alarmClock.ListAlarms()
        current_alarm_list_version = response["CurrentAlarmListVersion"]

        if self.last_alarm_list_version:
            alarm_list_uid, alarm_list_id = current_alarm_list_version.split(":")
            if self.last_uid != alarm_list_uid:
                matching_zone = next(
                    (z for z in zone.all_zones if z.uid == alarm_list_uid), None
                )
                if not matching_zone:
                    raise SoCoException(
                        "Alarm list UID {} does not match {}".format(
                            current_alarm_list_version, self.last_alarm_list_version
                        )
                    )

            if int(alarm_list_id) <= self.last_id:
                return

        self.last_alarm_list_version = current_alarm_list_version

        new_alarms = parse_alarm_payload(response, zone)

        # Update existing and create new Alarm instances
        for alarm_id, kwargs in new_alarms.items():
            existing_alarm = self.alarms.get(alarm_id)
            if existing_alarm:
                existing_alarm.update(**kwargs)
            else:
                new_alarm = Alarm(**kwargs)
                new_alarm._alarm_id = alarm_id  # pylint: disable=protected-access
                self.alarms[alarm_id] = new_alarm

        # Prune alarms removed externally
        for alarm_id in list(self.alarms):
            if not new_alarms.get(alarm_id):
                self.alarms.pop(alarm_id)

    def get_next_alarm_datetime(
        self, from_datetime=None, include_disabled=False, zone_uid=None
    ):
        """Get the next alarm trigger datetime.

        Args:
            from_datetime (datetime, optional): a datetime to reference next
                alarms from. This argument filters by alarms on or after this
                exact time. Since alarms do not store timezone information,
                the output timezone will match this input argument. Defaults
                to `datetime.now()`.
            include_disabled (bool, optional): If `True` then disabled alarms
                will be included in searching for the next alarm. Defaults to
                `False`.
            zone_uid (str, optional): If set the alarms will be filtered by
                zone with this UID. Defaults to `None`.

        Returns:
            datetime: The next alarm trigger datetime or None if disabled
        """
        if from_datetime is None:
            from_datetime = datetime.now()

        next_alarm_datetime = None
        for alarm_id in self.alarms:
            this_alarm = self.alarms.get(alarm_id)
            if zone_uid is not None and this_alarm.zone.uid != zone_uid:
                continue
            this_next_datetime = this_alarm.get_next_alarm_datetime(
                from_datetime, include_disabled
            )
            if (next_alarm_datetime is None) or (
                this_next_datetime is not None
                and this_next_datetime < next_alarm_datetime
            ):
                next_alarm_datetime = this_next_datetime
        return next_alarm_datetime


class Alarm:
    """A class representing a Sonos Alarm.

    Alarms may be created or updated and saved to, or removed from the Sonos
    system. An alarm is not automatically saved. Call `save()` to do that.
    """

    def __init__(
        self,
        zone,
        start_time=None,
        duration=None,
        recurrence="DAILY",
        enabled=True,
        program_uri=None,
        program_metadata="",
        play_mode="NORMAL",
        volume=20,
        include_linked_zones=False,
    ):
        """
        Args:
            zone (`SoCo`): The soco instance which will play the alarm.
            start_time (datetime.time, optional): The alarm's start time.
                Specify hours, minutes and seconds only. Defaults to the
                current time.
            duration (datetime.time, optional): The alarm's duration. Specify
                hours, minutes and seconds only. May be `None` for unlimited
                duration. Defaults to `None`.
            recurrence (str, optional): A string representing how
                often the alarm should be triggered. Can be ``DAILY``,
                ``ONCE``, ``WEEKDAYS``, ``WEEKENDS`` or of the form
                ``ON_DDDDDD`` where ``D`` is a number from 0-6 representing a
                day of the week (Sunday is 0), e.g. ``ON_034`` meaning Sunday,
                Wednesday and Thursday. Defaults to ``DAILY``.
            enabled (bool, optional): `True` if alarm is enabled, `False`
                otherwise. Defaults to `True`.
            program_uri(str, optional): The uri to play. If `None`, the
                built-in Sonos chime sound will be used. Defaults to `None`.
            program_metadata (str, optional): The metadata associated with
                'program_uri'. Defaults to ''.
            play_mode(str, optional): The play mode for the alarm. Can be one
                of ``NORMAL``, ``SHUFFLE_NOREPEAT``, ``SHUFFLE``,
                ``REPEAT_ALL``, ``REPEAT_ONE``, ``SHUFFLE_REPEAT_ONE``.
                Defaults to ``NORMAL``.
            volume (int, optional): The alarm's volume (0-100). Defaults to 20.
            include_linked_zones (bool, optional): `True` if the alarm should
                be played on the other speakers in the same group, `False`
                otherwise. Defaults to `False`.
        """

        self.zone = zone
        if start_time is None:
            start_time = datetime.now().time().replace(microsecond=0)
        self.start_time = start_time
        self.duration = duration
        self.recurrence = recurrence
        self.enabled = enabled
        self.program_uri = program_uri
        self.program_metadata = program_metadata
        self.play_mode = play_mode
        self.volume = volume
        self.include_linked_zones = include_linked_zones
        self._alarm_id = None

    def __repr__(self):
        middle = str(self.start_time.strftime(TIME_FORMAT))
        return "<{} id:{}@{} at {}>".format(
            self.__class__.__name__, self.alarm_id, middle, hex(id(self))
        )

    def update(self, **kwargs):
        """Update an existing Alarm instance using the same arguments as __init__."""
        for attr, value in kwargs.items():
            if not hasattr(self, attr):
                raise SoCoException("Alarm does not have atttribute {}".format(attr))
            setattr(self, attr, value)

    @property
    def play_mode(self):
        """
        `str`: The play mode for the alarm.

            Can be one of ``NORMAL``, ``SHUFFLE_NOREPEAT``, ``SHUFFLE``,
            ``REPEAT_ALL``, ``REPEAT_ONE``, ``SHUFFLE_REPEAT_ONE``.
        """
        return self._play_mode

    @play_mode.setter
    def play_mode(self, play_mode):
        """See `playmode`."""
        play_mode = play_mode.upper()
        if play_mode not in PLAY_MODES:
            raise KeyError("'%s' is not a valid play mode" % play_mode)
        self._play_mode = play_mode

    @property
    def volume(self):
        """`int`: The alarm's volume (0-100)."""
        return self._volume

    @volume.setter
    def volume(self, volume):
        """See `volume`."""
        # max 100
        volume = int(volume)
        self._volume = max(0, min(volume, 100))  # Coerce in range

    @property
    def recurrence(self):
        """`str`: How often the alarm should be triggered.

        Can be ``DAILY``, ``ONCE``, ``WEEKDAYS``, ``WEEKENDS`` or of the form
        ``ON_DDDDDDD`` where ``D`` is a number from 0-7 representing a day of
        the week (Sunday is 0), e.g. ``ON_034`` meaning Sunday, Wednesday and
        Thursday.
        """
        return self._recurrence

    @recurrence.setter
    def recurrence(self, recurrence):
        """See `recurrence`."""
        if not is_valid_recurrence(recurrence):
            raise KeyError("'%s' is not a valid recurrence value" % recurrence)

        self._recurrence = recurrence

    def save(self):
        """Save the alarm to the Sonos system.

        Returns:
            str: The alarm ID, or `None` if no alarm was saved.

        Raises:
            ~soco.exceptions.SoCoUPnPException: if the alarm cannot be created
                because there
                is already an alarm for this room at the specified time.
        """
        args = [
            ("StartLocalTime", self.start_time.strftime(TIME_FORMAT)),
            (
                "Duration",
                "" if self.duration is None else self.duration.strftime(TIME_FORMAT),
            ),
            ("Recurrence", self.recurrence),
            ("Enabled", "1" if self.enabled else "0"),
            ("RoomUUID", self.zone.uid),
            (
                "ProgramURI",
                "x-rincon-buzzer:0" if self.program_uri is None else self.program_uri,
            ),
            ("ProgramMetaData", self.program_metadata),
            ("PlayMode", self.play_mode),
            ("Volume", self.volume),
            ("IncludeLinkedZones", "1" if self.include_linked_zones else "0"),
        ]
        if self.alarm_id is None:
            response = self.zone.alarmClock.CreateAlarm(args)
            self._alarm_id = response["AssignedID"]
            alarms = Alarms()
            if alarms.last_id == int(self.alarm_id) - 1:
                alarms.last_alarm_list_version = "{}:{}".format(
                    alarms.last_uid, self.alarm_id
                )
            alarms.alarms[self.alarm_id] = self
        else:
            # The alarm has been saved before. Update it instead.
            args.insert(0, ("ID", self.alarm_id))
            self.zone.alarmClock.UpdateAlarm(args)
        return self.alarm_id

    def remove(self):
        """Remove the alarm from the Sonos system.

        There is no need to call `save`. The Python instance is not deleted,
        and can be saved back to Sonos again if desired.

        Returns:
            bool: If the removal was sucessful.
        """
        result = self.zone.alarmClock.DestroyAlarm([("ID", self.alarm_id)])
        alarms = Alarms()
        alarms.alarms.pop(self.alarm_id, None)
        self._alarm_id = None
        return result

    @property
    def alarm_id(self):
        """`str`: The ID of the alarm, or `None`."""
        return self._alarm_id

    def get_next_alarm_datetime(self, from_datetime=None, include_disabled=False):
        """Get the next alarm trigger datetime.

        Args:
            from_datetime (datetime, optional): a datetime to reference next
                alarms from. This argument filters by alarms on or after this
                exact time. Since alarms do not store timezone information,
                the output timezone will match this input argument. Defaults
                to `datetime.now()`.
            include_disabled (bool, optional): If `True` then the next datetime
                will be computed even if the alarm is disabled. Defaults to
                `False`.

        Returns:
            datetime: The next alarm trigger datetime or None if disabled
        """
        if not self.enabled and not include_disabled:
            return None

        if from_datetime is None:
            from_datetime = datetime.now()

        # Convert helper words to number recurrences
        recurrence_on_str = RECURRENCE_KEYWORD_EQUIVALENT.get(
            self.recurrence, self.recurrence
        )

        # For the purpose of finding the next alarm a "once" trigger that has
        # yet to trigger is everyday (the next possible day)
        if recurrence_on_str == RECURRENCE_KEYWORD_EQUIVALENT["ONCE"]:
            recurrence_on_str = RECURRENCE_KEYWORD_EQUIVALENT["DAILY"]

        # Trim the 'ON_' prefix, convert to int, remove duplicates
        recurrence_set = set(map(int, recurrence_on_str[3:]))

        # Convert Sonos weekdays to Python weekdays
        # Sonos starts on Sunday, Python starts on Monday
        if 0 in recurrence_set:
            recurrence_set.remove(0)
            recurrence_set.add(7)
        recurrence_set = {x - 1 for x in recurrence_set}

        # Begin search from next day if it would have already triggered today
        offset = 0
        if self.start_time <= from_datetime.time():
            offset += 1

        # Find first day
        from_datetime_day = from_datetime.weekday()
        offset_weekday = (from_datetime_day + offset) % 7
        while offset_weekday not in recurrence_set:
            offset += 1
            offset_weekday = (from_datetime_day + offset) % 7

        return datetime.combine(
            from_datetime.date() + timedelta(days=offset),
            self.start_time,
            tzinfo=from_datetime.tzinfo,
        )


def get_alarms(zone=None):
    """Get a set of all alarms known to the Sonos system.

    Args:
        zone (soco.SoCo, optional): a SoCo instance to query. If None, a random
            instance is used. Defaults to `None`.

    Returns:
        set: A set of `Alarm` instances
    """
    alarms = Alarms()
    alarms.update(zone)
    return set(alarms.alarms.values())


def remove_alarm_by_id(zone, alarm_id):
    """Remove an alarm from the Sonos system by its ID.

    Args:
        zone (`SoCo`): A SoCo instance, which can be any zone that belongs
            to the Sonos system in which the required alarm is defined.
        alarm_id (str): The ID of the alarm to be removed.

    Returns:
        bool: `True` if the alarm is found and removed, `False` otherwise.
    """
    alarms = Alarms()
    alarms.update(zone)
    alarm = alarms.get(alarm_id)
    if not alarm:
        return False
    return alarm.remove()


def parse_alarm_payload(payload, zone):
    """Parse the XML payload response and return a dict of `Alarm` kwargs."""
    alarm_list = payload["CurrentAlarmList"]
    tree = XML.fromstring(alarm_list.encode("utf-8"))

    # An alarm list looks like this:
    # <Alarms>
    #     <Alarm ID="14" StartTime="07:00:00"
    #         Duration="02:00:00" Recurrence="DAILY" Enabled="1"
    #         RoomUUID="RINCON_000ZZZZZZ1400"
    #         ProgramURI="x-rincon-buzzer:0" ProgramMetaData=""
    #         PlayMode="SHUFFLE_NOREPEAT" Volume="25"
    #         IncludeLinkedZones="0"/>
    #     <Alarm ID="15" StartTime="07:00:00"
    #         Duration="02:00:00" Recurrence="DAILY" Enabled="1"
    #         RoomUUID="RINCON_000ZZZZZZ01400"
    #         ProgramURI="x-rincon-buzzer:0" ProgramMetaData=""
    #         PlayMode="SHUFFLE_NOREPEAT" Volume="25"
    #          IncludeLinkedZones="0"/>
    # </Alarms>

    alarms = tree.findall("Alarm")
    alarm_args = {}
    for alarm in alarms:
        values = alarm.attrib
        alarm_id = values["ID"]

        alarm_zone = next(
            (z for z in zone.all_zones if z.uid == values["RoomUUID"]), None
        )
        if alarm_zone is None:
            # Some alarms are not associated with a zone, ignore these
            continue

        args = {
            "zone": alarm_zone,
            # StartTime not StartLocalTime which is used by CreateAlarm
            "start_time": datetime.strptime(values["StartTime"], "%H:%M:%S").time(),
            "duration": (
                None
                if values["Duration"] == ""
                else datetime.strptime(values["Duration"], "%H:%M:%S").time()
            ),
            "recurrence": values["Recurrence"],
            "enabled": values["Enabled"] == "1",
            "program_uri": (
                None
                if values["ProgramURI"] == "x-rincon-buzzer:0"
                else values["ProgramURI"]
            ),
            "program_metadata": values["ProgramMetaData"],
            "play_mode": values["PlayMode"],
            "volume": values["Volume"],
            "include_linked_zones": values["IncludeLinkedZones"] == "1",
        }

        alarm_args[alarm_id] = args
    return alarm_args
