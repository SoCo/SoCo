# -*- coding: utf-8 -*-

""" Types used by pysimplesoap to unmarshall SOAP return values
"""

from __future__ import unicode_literals

TRACKMETADATA_TYPE = {
    'artistId': str,
    'artist': str,
    'composerId': str,
    'composer': str,
    'albumId': str,
    'album': str,
    'albumArtistId': str,
    'albumArtist': str,
    'genreId': str,
    'genre': str,
    'duration': int,
    'rating': int,
    'albumArtURI': str,
    'canPlay': bool,
    'canSkip': bool,
    'canAddToFavorites': bool
}

STREAMMETADATA_TYPE = {
    'currentHost': str,
    'currentShowId': str,
    'currentShow': str,
    'secondsRemaining': int,
    'secondsToNextShow': int,
    'bitrate': int,
    'logo': str
}

DYNAMIC_TYPE = {
    'property': [{
        'name': str,
        'value': str
    }]
}

MEDIAMETADATA_TYPE = {
    'id': str,
    'itemType': str,
    'title': str,
    'mimeType': str,
    'trackMetadata': TRACKMETADATA_TYPE,
    'streamMetadata': STREAMMETADATA_TYPE,
    'dynamic': DYNAMIC_TYPE
}

MEDIACOLLECTION_TYPE = {
    'id': str,
    # "artist", "album", "genre", "playlist", "track", "search", "stream",
    # "show", "program", "favorites", "favorite", "collection", "container",
    # "albumList", "trackList", "artistTrackList", "other"
    'itemType': str,
    'title': str,
    'artist': str,
    'artistId': str,
    'canScroll': bool,
    'canPlay': bool,
    'canEnumerate': bool,
    'canAddToFavorites': bool,
    'canCache': bool,
    'canSkip': bool,
    'albumArtURI': str,
    # Legacy properties - no longer used, but returned on occasion
    'authRequired': bool,
    'homogeneous': bool,
    'canAddToFavorite': bool,
    'readOnly': bool
}

MEDIALIST_TYPE = {
    'index': int,
    'count': int,
    'total': int,
    'mediaCollection': (MEDIACOLLECTION_TYPE,),
    'mediaMetadata': (MEDIAMETADATA_TYPE,)
}

EXTENDEDMETADATA_TYPE = {
    'mediaCollection': MEDIACOLLECTION_TYPE,
    'mediaMetadata': MEDIAMETADATA_TYPE,
    'relatedBrowse': ({
        'id': str,
        'type': str
    }),
    'relatedText': ({
        'id': str,
        'type': str
    })
}
