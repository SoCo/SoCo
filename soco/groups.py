# -*- coding: utf-8 -*-
# pylint: disable=too-few-public-methods
"""
Classes and functionality relating to Sonos Groups

"""

from __future__ import unicode_literals


class ZoneGroup(object):
    """
    A class representing a Sonos Group. It looks like this::

        ZoneGroup(
            uid='RINCON_000E5879136C01400:58',
            coordinator=SoCo("192.168.1.101"),
            members=set([SoCo("192.168.1.101"), SoCo("192.168.1.102")])
            )


    Any SoCo instance can tell you what group it is in::

        >>>my_player.group
        ZoneGroup(
            uid='RINCON_000E5879136C01400:58',
            coordinator=SoCo("192.168.1.101"),
            members=set([SoCo("192.168.1.101"), SoCo("192.168.1.102")])
        )

    From there, you can find the coordinator for the current group::

        >>>my_player.group.coordinator
        SoCo("192.168.1.101")

    or, for example, its name::

        >>>my_player.group.coordinator.player_name
        Kitchen

    or a set of the members::

        >>>my_player.group.members
        {SoCo("192.168.1.101"), SoCo("192.168.1.102")}

    For convenience, ZoneGroup is also a container::

        >>>for player in my_player.group:
        ...   print player.player_name
        Living Room
        Kitchen

    If you need it, you can get an iterator over all groups on the network::

        >>>my_player.all_groups
        <generator object all_groups at 0x108cf0c30>

    """
    def __init__(self, uid, coordinator, members=None):
        #: The unique Sonos ID for this group
        self.uid = uid
        #: The :class:`Soco` instance which coordiantes this group
        self.coordinator = coordinator
        if members is not None:
            #: A set of :class:`Soco` instances which are members
            #  of the group
            self.members = set(members)
        else:
            self.members = set()

    def __iter__(self):
        return self.members.__iter__()

    def __contains__(self, member):
        return member in self.members

    def __repr__(self):
        return "{}(uid='{}', coordinator={!r}, members={!r})".format(
            self.__class__.__name__, self.uid, self.coordinator, self.members)
            