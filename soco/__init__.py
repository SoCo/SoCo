# -*- coding: utf-8 -*-

"""SoCo (Sonos Controller) is a simple library to control Sonos speakers."""

# There is no need for all strings here to be unicode, and Py2 cannot import
# modules with unicode names so do not use from __future__ import
# unicode_literals
# https://github.com/SoCo/SoCo/issues/98
#


import logging
import warnings
import sys

from .core import SoCo
from .discovery import discover
from .exceptions import SoCoException, UnknownSoCoException

# Will be parsed by setup.py to determine package metadata
__author__ = 'The SoCo-Team <python-soco@googlegroups.com>'
# Please add the suffix "+" to the version after release, to make it
# possible infer whether in development code from the version string
__version__ = '0.19'
__website__ = 'https://github.com/SoCo/SoCo'
__license__ = 'MIT License'

# You really should not `import *` - it is poor practice
# but if you do, here is what you get:
__all__ = [
    'discover',
    'SoCo',
    'SoCoException',
    'UnknownSoCoException',
]

# http://docs.python.org/2/howto/logging.html#library-config
# Avoids spurious error messages if no logger is configured by the user

logging.getLogger(__name__).addHandler(logging.NullHandler())

if sys.version_info.major < 3:
    warnings.warn(
        "Version 0.19 of SoCo is the last to support Python 2.7",
        stacklevel=2,
    )
