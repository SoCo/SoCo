"""Normalized browse models for configured music-service browsing."""

from __future__ import unicode_literals

from .util import _as_mapping, _as_string


class MusicServiceBrowseItem:
    """One normalized read-only item returned by a configured service."""

    def __init__(
        self,
        item_id,
        title,
        kind,
        item_type="",
        artist="",
        summary="",
        album_art_uri="",
        source_transport="smapi",
        section="",
        display_type="",
        variant="",
        raw=None,
    ):
        self.item_id = item_id
        self.title = title
        self.kind = kind
        self.item_type = item_type
        self.artist = artist
        self.summary = summary
        self.album_art_uri = album_art_uri
        self.source_transport = source_transport
        self.section = section
        self.display_type = display_type
        self.variant = variant
        self.raw = raw or {}

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} {self.title!r} "
            f"({self.item_id}) at {hex(id(self))}>"
        )

    @property
    def can_browse(self):
        """bool: Whether selecting this item should request child metadata."""
        return self.kind == "mediaCollection"


class MusicServiceBrowseResult:
    """A page of items returned by :class:`MusicServiceBrowser`."""

    def __init__(
        self,
        items,
        index=0,
        total=None,
        transport="smapi",
        requested_id="root",
        endpoint="",
        raw=None,
    ):
        self.items = list(items)
        self.index = int(index)
        self.count = len(self.items)
        self.total = self.count if total is None else int(total)
        self.transport = transport
        self.requested_id = requested_id
        self.endpoint = endpoint
        self.raw = raw

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} count={self.count} "
            f"total={self.total} transport={self.transport!r} "
            f"at {hex(id(self))}>"
        )


def _legacy_item(record, source_transport="smapi"):
    """Normalize one legacy SMAPI record."""
    metadata = _as_mapping(record.get("trackMetadata") or record.get("streamMetadata"))
    artist = _as_string(metadata.get("artist", record.get("artist", "")))
    title = record.get("title") or record.get("name") or record.get("id", "")
    return MusicServiceBrowseItem(
        item_id=str(record.get("id", "")),
        title=title,
        kind=record.get("kind", record.get("provider_kind", "mediaMetadata")),
        item_type=str(record.get("itemType", "")),
        artist=artist,
        summary=str(record.get("summary", "")),
        album_art_uri=record.get("album_art_uri", ""),
        source_transport=source_transport,
        raw=dict(record),
    )
