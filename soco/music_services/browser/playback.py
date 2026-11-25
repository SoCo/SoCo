"""Playback URI and DIDL metadata builders for configured music services.

The player resolves music-service streams itself. The URI it needs is keyed
on the item type (``track``, ``stream``, ``program``, ``show``, …) and MIME
type: each pair selects a scheme, a file extension and a ``flags`` value that
tell the player how to dereference the provider stream. The DIDL metadata
carries the account's service descriptor (``cdudn``) so the player knows which
account's credentials to use.

These builders back :meth:`MusicServiceBrowser.play` and are also usable on
their own together with :meth:`SoCo.play_uri` /
:meth:`SoCo.add_uri_to_queue`.
"""

from __future__ import unicode_literals

from xml.sax.saxutils import escape

from ...exceptions import MusicServiceException
from .models import MusicServiceBrowseItem

# MIME type -> file extension for ``x-sonos-http:`` track URIs.
_MIME_TO_EXT = {
    "audio/aac": "mp4",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mpeg3": "mp3",
    "audio/flac": "flac",
    "audio/x-ms-wma": "wma",
    "audio/wma": "wma",
    "audio/ogg": "ogg",
    "application/ogg": "ogg",
}

# DIDL ``upnp:class`` per normalized item type.
_ITEM_CLASSES = {
    "track": "object.item.audioItem.musicTrack",
    "stream": "object.item.audioItem.audioBroadcast",
    "program": "object.item.audioItem.audioBroadcast",
    "show": "object.item.audioItem.podcast",
    "episode": "object.item.audioItem.podcast",
    "audiobook": "object.item.audioItem.audioBook",
}

# DIDL item-id prefix per item type (mirrors the desktop controller).
_ITEM_ID_PREFIXES = {
    "track": "10030020",
    "stream": "00090000",
    "program": "000c0068",
    "show": "10156128",
    "episode": "10156128",
    "audiobook": "101340c8",
}

# ``flags`` for on-demand track URIs, keyed by service id where a service
# diverges from the common value. Apple Music rejects the generic 32 and needs
# 8224, the value the desktop controller sends for its tracks.
#
# Spotify ``x-sonos-spotify:`` resources sent *directly* to players were
# verified with flags=8224 across six speaker models by the music-services
# review. The ``flags=0`` seen in AVTransport event data is the current-track
# identity reported by the speaker, not the controller-sent resource.
_TRACK_FLAGS_OVERRIDES = {12: 8224, 204: 8224}
_DEFAULT_TRACK_FLAGS = 32


def escape_id(item_id):
    """Percent-encode the punctuation in a provider item id for a URI."""
    return (
        str(item_id)
        .replace(":", "%3a")
        .replace("/", "%2f")
        .replace("?", "%3f")
        .replace("=", "%3d")
        .replace("&", "%26")
        .replace("#", "%23")
    )


def normalize_item_type(item_type):
    """Return the base item type from a possibly-compound browse type.

    Sonos Radio, for example, advertises ``trackList.program`` and
    ``station.broadcast`` where the authoritative provider type is the part
    after the dot.
    """
    if not item_type:
        return ""
    return str(item_type).rsplit(".", 1)[-1].lower()


def resolve_item(browser, item):
    """Resolve the fields needed to build a playback URI and DIDL.

    Args:
        browser (MusicServiceBrowser): The service/account to play through.
        item (MusicServiceBrowseItem or str): A browsed item or raw item id.

    Returns:
        tuple: ``(item_id, item_type, mime, title)``. ``item_type`` is the
        normalized base type and ``mime`` is lowercased (both may be empty
        when the provider does not advertise them).
    """
    if isinstance(item, MusicServiceBrowseItem):
        item_id = item.item_id
        title = item.title
        item_type = normalize_item_type(item.item_type)
        mime = str((item.raw or {}).get("mimeType", "") or "").lower()
    else:
        item_id = str(item)
        title = ""
        item_type = ""
        mime = ""

    # Compound browse types (eg ``trackList.program``) and missing MIME
    # information need the provider's authoritative ``getMediaMetadata``.
    # The browse type already tells us the right shape for known types (a
    # ``trackList.program`` is a program, not the ``track`` some providers
    # report back), so only adopt the metadata's item type when the browse
    # type is unrecognised (eg ``station.broadcast`` -> ``stream``).
    if item_type not in _ITEM_CLASSES or not mime:
        try:
            metadata = browser.get_media_metadata(item_id)
        except MusicServiceException:
            metadata = None
        if metadata:
            metadata_type = normalize_item_type(metadata.get("itemType"))
            if item_type not in _ITEM_CLASSES:
                item_type = metadata_type or item_type
            mime = str(metadata.get("mimeType") or mime or "").lower()
            title = title or str(metadata.get("title") or "")

    return item_id, item_type, mime, title


def build_uri(browser, item_id, item_type, mime=""):
    """Return the player URI for one playable item.

    Args:
        browser (MusicServiceBrowser): The service/account to play through.
        item_id (str): The provider item id (eg ``song:1844932150``).
        item_type (str): The normalized item type (``track``, ``stream``,
            ``program``, ``show``, ``episode`` or ``audiobook``).
        mime (str): The provider MIME type, when known.

    Returns:
        str: A URI to hand to :meth:`SoCo.play_uri` or
        :meth:`SoCo.add_uri_to_queue`.

    Raises:
        MusicServiceException: If ``item_type`` is not playable.
    """
    item_type = normalize_item_type(item_type)
    if item_type not in _ITEM_CLASSES:
        raise MusicServiceException(
            f"{browser.service_name} items of type "
            f"{item_type or 'unknown'!r} cannot be played directly; browse "
            "into the item to find a playable track or stream"
        )

    service_id = int(browser.service_id)
    serial = browser.account.serial_number
    encoded = escape_id(item_id)
    mime = (mime or "").lower()

    if item_type == "stream":
        if mime == "audio/aac":
            scheme, flags = "x-sonosapi-stream", 8224
        elif mime in (
            "application/x-mpegurl",
            "application/x-mpegURL",
            "audio/x-mpegurl",
            "audio/x-scpls",
        ):
            scheme, flags = "x-sonosapi-hls", 288
        else:
            scheme, flags = "x-sonosapi-stream", 32
        return f"{scheme}:{encoded}?sid={service_id}&flags={flags}&sn={serial}"

    if item_type == "program":
        return f"x-sonosapi-radio:{encoded}?sid={service_id}&flags=104&sn={serial}"

    if item_type in ("show", "episode"):
        return (
            f"x-sonosapi-hls-static:{encoded}"
            f"?sid={service_id}&flags=24616&sn={serial}"
        )

    if item_type == "audiobook":
        return (
            f"x-rincon-cpcontainer:101340c8{encoded}"
            f"?sid={service_id}&flags=16584&sn={serial}"
        )

    # track
    if mime == "audio/x-spotify":
        flags = _TRACK_FLAGS_OVERRIDES.get(service_id, _DEFAULT_TRACK_FLAGS)
        return f"x-sonos-spotify:{encoded}?sid={service_id}&flags={flags}&sn={serial}"
    if mime == "audio/flac":
        return f"x-sonos-http:{encoded}.flac?sid={service_id}&flags=0&sn={serial}"
    extension = _MIME_TO_EXT.get(mime, "mp3")
    flags = _TRACK_FLAGS_OVERRIDES.get(service_id, _DEFAULT_TRACK_FLAGS)
    return (
        f"x-sonos-http:{encoded}.{extension}"
        f"?sid={service_id}&flags={flags}&sn={serial}"
    )


def build_metadata(browser, item_id, title, item_type, mime="", uri=""):
    """Return the DIDL metadata for a playable item.

    The ``<desc>`` element carries the account's service descriptor (cdudn);
    the player uses it to pick the account whose credentials dereference the
    stream, so it is the one field that must be present. The stream URI is
    sent separately by :meth:`SoCo.play_uri`, so for ordinary items no
    ``<res>`` is emitted.

    Spotify resources are the exception: the player needs the resource
    protocol info (``sonos.com-spotify:*:audio/x-spotify:*``) in the DIDL to
    accept an ``x-sonos-spotify:`` track, as verified against real players.
    The literal appears verbatim in the desktop controller binary
    (``sclib-csharp.dll``) as ``sonos.com-spotify:*:audio/x-spotify:*``.
    """
    item_type = normalize_item_type(item_type)
    klass = _ITEM_CLASSES.get(item_type, _ITEM_CLASSES["track"])
    prefix = _ITEM_ID_PREFIXES.get(item_type, _ITEM_ID_PREFIXES["track"])
    encoded = escape_id(item_id)
    desc = browser.account.udn or browser.music_service.desc
    res = ""
    if (mime or "").lower() == "audio/x-spotify":
        res = (
            '<res protocolInfo="sonos.com-spotify:*:audio/x-spotify:*">'
            f"{escape(uri)}</res>"
        )
    return (
        '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
        'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
        'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
        f'<item id="{prefix}{encoded}" parentID="1004006c{encoded}" '
        'restricted="true">'
        f"<dc:title>{escape(title)}</dc:title>"
        f"<upnp:class>{klass}</upnp:class>"
        f"{res}"
        '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:'
        f'metadata-1-0/">{escape(desc)}</desc>'
        "</item></DIDL-Lite>"
    )
