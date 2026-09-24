"""Manifest-driven content home-page browsing."""

from __future__ import unicode_literals

import uuid
from collections.abc import Mapping

import requests

from ...exceptions import MusicServiceException
from .models import MusicServiceBrowseItem
from .util import (
    DESKTOP_USER_AGENT,
    _artwork_uri,
    _as_list,
    _as_mapping,
    _as_string,
)


def _service_manifest(music_service, session):
    """Fetch and decode the manifest advertised by ListAvailableServices."""
    if not music_service.manifest_uri:
        return {}
    try:
        response = session.get(
            music_service.manifest_uri,
            headers={"Accept": "application/json", "Accept-Language": "en-US"},
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise MusicServiceException(
            f"{music_service.service_name} manifest request failed: {error}"
        ) from error
    try:
        manifest = response.json()
    except ValueError as error:
        raise MusicServiceException(
            f"{music_service.service_name} manifest was not valid JSON"
        ) from error
    if not isinstance(manifest, Mapping):
        raise MusicServiceException(
            f"{music_service.service_name} manifest root was not an object"
        )
    return manifest


def _content_endpoint(music_service, session, endpoint_type="browse", manifest=None):
    """Return a manifest content endpoint of the requested type.

    ``manifest`` may be passed when it has already been fetched (and cached)
    by the caller; otherwise it is downloaded here.
    """
    if manifest is None:
        manifest = _service_manifest(music_service, session)
    for endpoint_value in _as_list(manifest.get("endpoints")):
        endpoint = _as_mapping(endpoint_value)
        if endpoint.get("type") != endpoint_type:
            continue
        uri = _as_string(endpoint.get("uri"))
        if uri:
            return uri
    raise MusicServiceException(
        f"{music_service.service_name} manifest has no {endpoint_type} endpoint"
    )


def _content_headers(
    music_service,
    account,
    device_id,
    controller_id,
    time_zone,
    explicit_content,
):
    headers = {
        "Accept-Language": "en-US",
        "X-Sonos-Device-Id": device_id,
        "X-Sonos-Corr-Id": str(uuid.uuid4()),
        "X-Sonos-Controller-ID": controller_id,
        "User-Agent": DESKTOP_USER_AGENT,
        "Connection": "keep-alive",
    }
    if account.token:
        headers["Authorization"] = f"Bearer {account.token}"
    capabilities = int(music_service.capabilities)
    if capabilities & (1 << 16) and time_zone:
        headers["X-Sonos-Context-TimeZone"] = time_zone
    if capabilities & (1 << 21) and explicit_content:
        headers["X-Sonos-Context-ContentFiltering"] = "explicit"
    return headers


def _content_item(item, section=""):
    """Normalize a modern content JSON item for the public browse model."""
    item = _as_mapping(item)
    identity = _as_mapping(item.get("id"))
    content = _as_mapping(item.get("content"))
    object_id = _as_string(identity.get("objectId"))
    if not object_id:
        return None

    record = _as_mapping(content.get("container"))
    content_kind = "container"
    if not record:
        record = _as_mapping(content.get("track"))
        content_kind = "track"
    if not record:
        return None

    item_type = str(record.get("type", content_kind))
    can_enumerate = record.get("canEnumerate")
    collection_types = {"album", "artist", "container", "playlist", "show"}
    kind = (
        "mediaCollection"
        if content_kind == "container"
        and (can_enumerate is True or item_type in collection_types)
        else "mediaMetadata"
    )
    artist_name = _as_string(_as_mapping(record.get("artist")).get("name"))
    return MusicServiceBrowseItem(
        item_id=object_id,
        title=record.get("name", object_id),
        kind=kind,
        item_type=item_type,
        artist=artist_name,
        summary=record.get("summary", ""),
        album_art_uri=_artwork_uri(record),
        source_transport="content",
        section=section,
        display_type=item.get("displayType", ""),
        raw=dict(item),
    )
