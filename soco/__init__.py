# -*- coding: utf-8 -*-

""" SoCo (Sonos Controller) is a simple library to control Sonos speakers """

# There is no need for all strings here to be unicode, and Py2 cannot import
# modules with unicode names
# https://github.com/SoCo/SoCo/issues/98
# from __future__ import unicode_literals

# Will be parsed by setup.py to determine package metadata
__author__ = 'The SoCo-Team <python-soco@googlegroups.com>'
__version__ = '0.7'
__website__ = 'https://github.com/SoCo/SoCo'
__license__ = 'MIT License'


from .core import discover, SoCo, SonosDiscovery
from .exceptions import SoCoException, UnknownSoCoException

# You really should not `import *` - it is poor practice
# but if you do, here is what you get:
__all__ = [
    'discover',
    'SonosDiscovery',
    'SoCo',
    'SoCoException',
    'UnknownSoCoException',
    ]

# http://docs.python.org/2/howto/logging.html#library-config
# Avoids spurious error messages if no logger is configured by the user
import logging

# Support Python 2.6
try:  # Python 2.7+
    from logging import NullHandler
except ImportError:
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass

logging.getLogger(__name__).addHandler(NullHandler())
