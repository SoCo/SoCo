# -*- coding: utf-8 -*-
""" Configuration variables.

These may be set by your code as follows::

    from soco import config
    ...
    config.VARIABLE = value


"""
from __future__ import unicode_literals

#: The class object to use when SoCo instances are created. Specify the actual
#: callable class object here, not a string. If None, the default SoCo class
#: will be used. Must be set before any instances are created, or it will have
#: unpredictable effects.
SOCO_CLASS = None

#: Is the cache enabled? If True (the default), some caching of network
#: requests will take place.
CACHE_ENABLED = True
