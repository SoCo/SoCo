# Disable while we have Python 2.x compatability
# pylint: disable=useless-object-inheritance

"""This module contains classes and functionality relating to Sonos Groups."""


class ZoneGroup:

    """
    A class representing a Sonos Group. It looks like this::

        ZoneGroup(
            uid='RINCON_000FD584236D01400:58',
            coordinator=SoCo("192.168.1.101"),
            members={SoCo("192.168.1.101"), SoCo("192.168.1.102")}
        )


    Any SoCo instance can tell you what group it is in::


        >>> device = soco.discovery.any_soco()
        >>> device.group
        ZoneGroup(
            uid='RINCON_000FD584236D01400:58',
            coordinator=SoCo("192.168.1.101"),
            members={SoCo("192.168.1.101"), SoCo("192.168.1.102")}
        )

    From there, you can find the coordinator for the current group::

        >>> device.group.coordinator
        SoCo("192.168.1.101")

    or, for example, its name::

        >>> device.group.coordinator.player_name
        Kitchen

    or a set of the members::

        >>> device.group.members
        {SoCo("192.168.1.101"), SoCo("192.168.1.102")}

    For convenience, ZoneGroup is also a container::

        >>> for player in device.group:
        ...   print player.player_name
        Living Room
        Kitchen

    If you need it, you can get an iterator over all groups on the network::

        >>> device.all_groups
        <generator object all_groups at 0x108cf0c30>

    A consistent readable label for the group members can be returned with
    the `label` and `short_label` properties.

    Properties are available to get and set the group `volume` and the group
    `mute` state, and the `set_relative_volume()` method can be used to make
    relative adjustments to the group volume, e.g.:

        >>> device.group.volume = 25
        >>> device.group.volume
        25
        >>> device.group.set_relative_volume(-10)
        15
        >>> device.group.mute
        >>> False
        >>> device.group.mute = True
        >>> device.group.mute
        True
    """

    def __init__(self, uid, coordinator, members=None):
        """
        Args:
            uid (str): The unique Sonos ID for this group, eg
                ``RINCON_000FD584236D01400:5``.
            coordinator (SoCo): The SoCo instance representing the coordinator
                of this group.
            members (Iterable[SoCo]): An iterable containing SoCo instances
                which represent the members of this group.
        """
        #: The unique Sonos ID for this group
        self.uid = uid
        #: The `SoCo` instance which coordinates this group
        self.coordinator = coordinator
        if members is not None:
            #: A set of `SoCo` instances which are members of the group
            self.members = set(members)
        else:
            self.members = set()

    def __iter__(self):
        return self.members.__iter__()

    def __contains__(self, member):
        return member in self.members

    def __repr__(self):
        return "{}(uid='{}', coordinator={!r}, members={!r})".format(
            self.__class__.__name__, self.uid, self.coordinator, self.members
        )

    @property
    def label(self):
        """str: A description of the group.

        >>> device.group.label
        'Kitchen, Living Room'
        """
        group_names = sorted([m.player_name for m in self.members])
        return ", ".join(group_names)

    @property
    def short_label(self):
        """str: A short description of the group.

        >>> device.group.short_label
        'Kitchen + 1'
        """
        group_names = sorted([m.player_name for m in self.members])
        group_label = group_names[0]
        if len(group_names) > 1:
            group_label += " + {}".format(len(group_names) - 1)
        return group_label

    @property
    def volume(self):
        """int: The volume of the group.

        An integer between 0 and 100.
        """
        response = self.coordinator.groupRenderingControl.GetGroupVolume(
            [("InstanceID", 0)]
        )
        return int(response["CurrentVolume"])

    @volume.setter
    def volume(self, group_volume):
        group_volume = int(group_volume)
        group_volume = max(0, min(group_volume, 100))  # Coerce in range
        self.coordinator.groupRenderingControl.SetGroupVolume(
            [("InstanceID", 0), ("DesiredVolume", group_volume)]
        )

    @property
    def mute(self):
        """bool: The mute state for the group.

        True or False.
        """
        response = self.coordinator.groupRenderingControl.GetGroupMute(
            [("InstanceID", 0)]
        )
        mute_state = response["CurrentMute"]
        return bool(int(mute_state))

    @mute.setter
    def mute(self, group_mute):
        mute_value = "1" if group_mute else "0"
        self.coordinator.groupRenderingControl.SetGroupMute(
            [("InstanceID", 0), ("DesiredMute", mute_value)]
        )

    def set_relative_volume(self, relative_group_volume):
        """Adjust the group volume up or down by a relative amount.

        If the adjustment causes the volume to overshoot the maximum value
        of 100, the volume will be set to 100. If the adjustment causes the
        volume to undershoot the minimum value of 0, the volume will be set
        to 0.

        Note that this method is an alternative to using addition and
        subtraction assignment operators (+=, -=) on the `volume` property
        of a `ZoneGroup` instance. These operators perform the same function
        as `set_relative_volume()` but require two network calls per
        operation instead of one.

        Args:
            relative_group_volume (int): The relative volume adjustment. Can be
                positive or negative.

        Returns:
            int: The new group volume setting.

        Raises:
            ValueError: If ``relative_group_volume`` cannot be cast as
                an integer.
        """
        relative_group_volume = int(relative_group_volume)
        # Sonos automatically handles out-of-range values.
        resp = self.coordinator.groupRenderingControl.SetRelativeGroupVolume(
            [("InstanceID", 0), ("Adjustment", relative_group_volume)]
        )
        return int(resp["NewVolume"])
