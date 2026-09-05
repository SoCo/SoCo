"""Shared XML/item helpers for configured music-service browsing."""

from __future__ import unicode_literals

from collections.abc import Mapping

SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
SMAPI_NS = "http://www.sonos.com/Services/1.1"

# This is the user agent used by the desktop-controller flow on which the
# implementation is based. Some music services are surprisingly strict
# about Sonos controller identity strings, so this should not be replaced
# with requests' default user agent merely for tidiness.
DESKTOP_USER_AGENT = (
    "Linux UPnP/1.0 Sonos/90.0-77070 "
    "(WDCR:Microsoft Windows NT 10.0.19045 64-bit)"
)


def _as_mapping(value):
    """Return a provider mapping, or an empty mapping for a malformed value."""
    return value if isinstance(value, Mapping) else {}


def _as_list(value):
    """Return a provider list, or an empty list for a malformed value."""
    return value if isinstance(value, list) else []


def _as_string(value):
    """Return a provider string, or an empty string for a malformed value."""
    return value if isinstance(value, str) else ""


def _local_name(tag):
    """Return an XML tag name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _children(node, name):
    """Return descendants whose local XML name matches ``name``."""
    return [child for child in node.iter() if _local_name(child.tag) == name]


def _child_text(node, name, default=""):
    """Return the text of a direct child identified by local XML name."""
    for child in node:
        if _local_name(child.tag) == name:
            return child.text or default
    return default


def _element_value(node):
    """Convert a SMAPI result element without discarding nested metadata.

    Third-party services are not consistent enough for a fixed schema at this
    boundary. The conversion therefore preserves unknown fields and repeated
    elements, and the public browse models normalize only the small set of
    fields needed to navigate the result.
    """
    if not list(node):
        return node.text or ""

    result = {}
    for child in node:
        name = _local_name(child.tag)
        value = _element_value(child)
        if name not in result:
            result[name] = value
            continue
        if not isinstance(result[name], list):
            result[name] = [result[name]]
        result[name].append(value)
    return result


def _explicit_bool(value):
    """Return a provider boolean only when it is explicitly represented."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return None


def _artwork_uri(record):
    """Resolve the artwork shapes used by legacy SMAPI and content JSON."""
    record = _as_mapping(record)
    if not record:
        return ""

    for key in ("album_art_uri", "albumArtURI", "albumArtUri", "imageUrl", "logo"):
        value = _as_string(record.get(key))
        if value:
            return (
                value.replace("${width}", "400")
                .replace("${height}", "400")
                .replace("${ratio}", "1x1")
            )

    for key in (
        "streamMetadata",
        "trackMetadata",
        "metadata",
        "container",
        "track",
        "album",
    ):
        value = _artwork_uri(record.get(key))
        if value:
            return value
    return ""


def _legacy_item_kind(provider_kind, record):
    """Mirror the desktop controller's canPush distinction for SMAPI items.

    A provider ``mediaCollection`` element is a container unless it declares
    ``canEnumerate=false`` (a playable item the provider wrapped in a
    collection element, eg a Pandora station). ``itemType`` is not a reliable
    signal either way: JazzGroove sends its browsable playlists as
    ``mediaCollection`` with ``itemType=program`` and no ``canEnumerate``.
    """
    if provider_kind != "mediaCollection":
        return provider_kind

    object_id = str(record.get("id", "")).lower()
    # Upsell banners are controller actions, not browse containers.
    if object_id.startswith("upsell-banner/"):
        return "mediaMetadata"

    can_enumerate = _explicit_bool(record.get("canEnumerate"))
    if can_enumerate is False:
        return "mediaMetadata"
    return provider_kind
