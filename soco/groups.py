# -*- coding: utf-8 -*-
from __future__ import unicode_literals


class ZoneGroup(object):
    """docstring for Group"""
    def __init__(self, uid, coordinator, members = None):
        self.uid = uid
        self.coordinator = coordinator
        if members is not None:
            self.members = set(members)
        else:
            self.members = set()

    def __iter__(self):
        return self.members.__iter__()

    def __contains__(self, member):
        return member in self.members

    def __repr__(self):
        return "{}(uid='{}', coordinator='{!r}', members={!r})".format(
            self.__class__.__name__, self.uid, self.coordinator, self.members)

