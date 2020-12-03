# -*- coding: utf-8 -*-

# Disable while we have Python 2.x compatability
# pylint: disable=useless-object-inheritance

"""This module contains classes relating to Sonos Alarms."""

from __future__ import unicode_literals

import logging
import re
import weakref
from datetime import datetime

from . import discovery
from .core import PLAY_MODES
from .xml import XML

log = logging.getLogger(__name__)  # pylint: disable=C0103
TIME_FORMAT = "%H:%M:%S"


def is_valid_recurrence(text):
    """Check that ``text`` is a valid recurrence string.

    A valid recurrence string is  ``DAILY``, ``ONCE``, ``WEEKDAYS``,
    ``WEEKENDS`` or of the form ``ON_DDDDDD`` where ``D`` is a number from 0-7
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
        >>> is_valid_recurrence('ON_777')  # Sat
        True
        >>> is_valid_recurrence('ON_3421') # Mon, Tue, Wed, Thur
        True
        >>> is_valid_recurrence('ON_123456789') # Too many digits
        False
    """
    if text in ("DAILY", "ONCE", "WEEKDAYS", "WEEKENDS"):
        return True
    return re.search(r"^ON_[0-7]{1,7}$", text) is not None


class Alarm(object):

    """A class representing a Sonos Alarm.

    Alarms may be created or updated and saved to, or removed from the Sonos
    system. An alarm is not automatically saved. Call `save()` to do that.

    Example:

        >>> device = discovery.any_soco()
        >>> # create an alarm with default properties
        >>> alarm = Alarm(device)
        >>> print alarm.volume
        20
        >>> print get_alarms()
        set([])
        >>> # save the alarm to the Sonos system
        >>> alarm.save()
        >>> print get_alarms()
        set([<Alarm id:88@15:26:15 at 0x107abb090>])
        >>> # update the alarm
        >>> alarm.recurrence = "ONCE"
        >>> # Save it again for the change to take effect
        >>> alarm.save()
        >>> # Remove it
        >>> alarm.remove()
        >>> print get_alarms()
        set([])
    """

    # pylint: disable=too-many-instance-attributes

    _all_alarms = weakref.WeakValueDictionary()

    # pylint: disable=too-many-arguments
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
                ``ON_DDDDDD`` where ``D`` is a number from 0-7 representing a
                day of the week (Sunday is 0), e.g. ``ON_034`` meaning Sunday,
                Wednesday and Thursday. Defaults to ``DAILY``.
            enabled (bool, optional): `True` if alarm is enabled, `False`
                otherwise. Defaults to `True`.
            program_uri(str, optional): The uri to play. If `None`, the
                built-in Sonos chime sound will be used. Defaults to `None`.
            program_metadata (str, optional): The metadata associated with
                `program_uri`. Defaults to ''.
            play_mode(str, optional): The play mode for the alarm. Can be one
                of ``NORMAL``, ``SHUFFLE_NOREPEAT``, ``SHUFFLE``,
                ``REPEAT_ALL``, ``REPEAT_ONE``, ``SHUFFLE_REPEAT_ONE``.
                Defaults to ``NORMAL``.
            volume (int, optional): The alarm's volume (0-100). Defaults to 20.
            include_linked_zones (bool, optional): `True` if the alarm should
                be played on the other speakers in the same group, `False`
                otherwise. Defaults to `False`.
        """

        super().__init__()
        self.zone = zone
        if start_time is None:
            start_time = datetime.now().time()
        #: `datetime.time`: The alarm's start time.
        self.start_time = start_time
        #: `datetime.time`: The alarm's duration.
        self.duration = duration
        self._recurrence = recurrence
        #: `bool`: `True` if the alarm is enabled, else `False`.
        self.enabled = enabled
        #:
        self.program_uri = program_uri
        #: `str`: The uri to play.
        self.program_metadata = program_metadata
        self._play_mode = play_mode
        self._volume = volume
        #: `bool`: `True` if the alarm should be played on the other speakers
        #: in the same group, `False` otherwise.
        self.include_linked_zones = include_linked_zones
        self._alarm_id = None

    def __repr__(self):
        middle = str(self.start_time.strftime(TIME_FORMAT))
        return "<{0} id:{1}@{2} at {3}>".format(
            self.__class__.__name__, self._alarm_id, middle, hex(id(self))
        )

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

        Raises:
            ~soco.exceptions.SoCoUPnPException: if the alarm cannot be created
                because there
                is already an alarm for this room at the specified time.
        """
        # pylint: disable=bad-continuation
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
        if self._alarm_id is None:
            response = self.zone.alarmClock.CreateAlarm(args)
            self._alarm_id = response["AssignedID"]
            Alarm._all_alarms[self._alarm_id] = self
        else:
            # The alarm has been saved before. Update it instead.
            args.insert(0, ("ID", self._alarm_id))
            self.zone.alarmClock.UpdateAlarm(args)

    def remove(self):
        """Remove the alarm from the Sonos system.

        There is no need to call `save`. The Python instance is not deleted,
        and can be saved back to Sonos again if desired.
        """
        self.zone.alarmClock.DestroyAlarm([("ID", self._alarm_id)])
        alarm_id = self._alarm_id
        try:
            del Alarm._all_alarms[alarm_id]
        except KeyError:
            pass
        self._alarm_id = None


def get_alarms(zone=None):
    """Get a set of all alarms known to the Sonos system.

    Args:
        zone (soco.SoCo, optional): a SoCo instance to query. If None, a random
            instance is used. Defaults to `None`.

    Returns:
        set: A set of `Alarm` instances

    Note:
        Any existing `Alarm` instance will have its attributes updated to those
        currently stored on the Sonos system.
    """
    # Get a soco instance to query. It doesn't matter which.
    if zone is None:
        zone = discovery.any_soco()
    response = zone.alarmClock.ListAlarms()
    alarm_list = response["CurrentAlarmList"]
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

    # pylint: disable=protected-access
    alarms = tree.findall("Alarm")
    result = set()
    for alarm in alarms:
        values = alarm.attrib
        alarm_id = values["ID"]
        # If an instance already exists for this ID, update and return it.
        # Otherwise, create a new one and populate its values
        if Alarm._all_alarms.get(alarm_id):
            instance = Alarm._all_alarms.get(alarm_id)
        else:
            instance = Alarm(None)
            instance._alarm_id = alarm_id
            Alarm._all_alarms[instance._alarm_id] = instance

        instance.start_time = datetime.strptime(
            values["StartTime"], "%H:%M:%S"
        ).time()  # NB StartTime, not
        # StartLocalTime, which is used by CreateAlarm
        instance.duration = (
            None
            if values["Duration"] == ""
            else datetime.strptime(values["Duration"], "%H:%M:%S").time()
        )
        instance.recurrence = values["Recurrence"]
        instance.enabled = values["Enabled"] == "1"
        instance.zone = next(
            (z for z in zone.all_zones if z.uid == values["RoomUUID"]), None
        )
        # some alarms are not associated to zones -> filter these out
        if instance.zone is None:
            continue
        instance.program_uri = (
            None
            if values["ProgramURI"] == "x-rincon-buzzer:0"
            else values["ProgramURI"]
        )
        instance.program_metadata = values["ProgramMetaData"]
        instance.play_mode = values["PlayMode"]
        instance.volume = values["Volume"]
        instance.include_linked_zones = values["IncludeLinkedZones"] == "1"

        result.add(instance)
    return result
