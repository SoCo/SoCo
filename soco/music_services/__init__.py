# -*- coding: utf-8 -*-

""" This package provides the MusicService class and related functionality,
which allows access to the various third party music services which can be used
with Sonos.

"""

from .music_service import MusicService, MusicAccount, desc_from_uri


__all__ = [
    'MusicService',
    'MusicAccount',
    'desc_from_uri'
    ]
