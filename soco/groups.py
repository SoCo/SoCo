# -*- coding: utf-8 -*-

"""This module contains classes and functionality relating to Sonos Groups."""

from __future__ import unicode_literals


class ZoneGroup(object):

    """
    A class representing a Sonos Group. It looks like this::

        ZoneGroup(
            uid='RINCON_000FD584236D01400:58',
            coordinator=SoCo("192.168.1.101"),
            members=set([SoCo("192.168.1.101"), SoCo("192.168.1.102")])
        )


    Any SoCo instance can tell you what group it is in::


        >>> device = soco.discovery.any_soco()
        >>> device.group
        ZoneGroup(
            uid='RINCON_000FD584236D01400:58',
            coordinator=SoCo("192.168.1.101"),
            members=set([SoCo("192.168.1.101"), SoCo("192.168.1.102")])
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
        return "{0}(uid='{1}', coordinator={2!r}, members={3!r})".format(
            self.__class__.__name__, self.uid, self.coordinator, self.members)

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
            group_label += " + {0}".format(len(group_names) - 1)
        return group_label
