# -*- coding: utf-8 -*-

"""This package provides the MusicService class and related functionality,
which allows access to the various third party music services which can be used
with Sonos."""

from .music_service import MusicService, desc_from_uri
from .accounts import Account

__all__ = ["MusicService", "desc_from_uri", "Account"]
