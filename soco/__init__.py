# -*- coding: utf-8 -*-
from __future__ import unicode_literals

""" SoCo (Sonos Controller) is a simple library to control Sonos speakers """

# Will be parsed by setup.py to determine package metadata
__author__ = 'Rahim Sonawalla <rsonawalla@gmail.com>'
__version__ = '0.6'
__website__ = 'https://github.com/SoCo/SoCo'
__license__ = 'MIT License'


from .core import SonosDiscovery, SoCo
from .exceptions import SoCoException, UnknownSoCoException

__all__ = ['SonosDiscovery', 'SoCo', 'SoCoException', 'UnknownSoCoException']
