# -*- coding: utf-8 -*-

""" SoCo (Sonos Controller) is a simple library to control Sonos speakers """

# Will be parsed by setup.py to determine package metadata
__author__ = 'Rahim Sonawalla <rsonawalla@gmail.com>'
__version__ = '0.5'
__website__ = 'https://github.com/rahims/SoCo'
__license__ = 'MIT License'


from core import SonosDiscovery, SoCo, SoCoException, UnknownSoCoException

__all__ = ['SonosDiscovery', 'SoCo', 'SoCoException', 'UnknownSoCoException']
