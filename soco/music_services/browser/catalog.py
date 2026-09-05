"""Manifest, presentation-map and strings data for configured services.

Every music service advertises a JSON ``manifest`` (when it has one) through
its descriptor, and most services describe their search, display, artwork,
ratings and menu rules in an XML presentation map.  The presentation map
references localized strings by id; the manifest advertises the ``strings``
document which resolves them.  This module parses all three into usable
structures.  The browser keeps the parsed results cached in memory, so the
documents are only fetched once per :class:`MusicServiceBrowser` instance.
"""

from __future__ import unicode_literals

import requests

from ...exceptions import MusicServiceException
from ...xml import XML
from .util import _as_mapping, _as_string


def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


class StringTables:
    """Parsed localized string tables for one music service.

    The presentation map references strings by id (``StringId``,
    ``PromptStringId``, ``OnSuccessStringId``, ...).  The strings document
    resolves those ids to display text per language.  :attr:`tables` maps a
    language tag (``en-US``, ``de-DE``, ...) to a ``{string_id: text}`` dict.
    """

    def __init__(self, uri="", version=None, tables=None, raw_xml=""):
        self.uri = uri
        self.version = version
        self.tables = {lang: dict(entries) for lang, entries in (tables or {}).items()}
        self.raw_xml = raw_xml

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} uri={self.uri!r} version="
            f"{self.version} languages={len(self.tables)} at {hex(id(self))}>"
        )

    @property
    def languages(self):
        """tuple: The language tags with a table, in document order."""
        return tuple(self.tables)

    def localized(self, lang="en-US"):
        """Return the ``{string_id: text}`` table for a language.

        Falls back to any available table when the requested language is not
        present.
        """
        if lang in self.tables:
            return self.tables[lang]
        if self.tables:
            return next(iter(self.tables.values()))
        return {}

    def resolve(self, string_id, lang="en-US", default=None):
        """Return the display text for a string id in a language.

        Args:
            string_id (str): The id referenced by the presentation map.
            lang (str): The desired language tag.
            default: Returned when the id is unknown; ``string_id`` itself
                when ``None``.
        """
        if not string_id:
            return default
        text = self.localized(lang).get(string_id)
        if text is None:
            return string_id if default is None else default
        return text


class PresentationMap:
    """A parsed music-service presentation map.

    The presentation map is the XML document which tells controllers how to
    present a service: which search categories and variants exist, which
    display types to use for each container, how artwork and browse icons
    scale, and which quality badges streams may carry.  Every attribute is
    parsed into plain dicts/lists so the document is easy to inspect and
    serialize; the original XML is retained in :attr:`raw_xml`.
    """

    def __init__(
        self,
        uri="",
        version=None,
        page_size=None,
        artwork_size_map=None,
        browse_icon_size_map=None,
        display_types=None,
        search_categories=None,
        menu_item_overrides=None,
        stream_quality_badges=None,
        now_playing_ratings=None,
        quick_skips=None,
        raw_xml="",
    ):
        self.uri = uri
        self.version = version
        self.page_size = page_size
        self.artwork_size_map = dict(artwork_size_map or {})
        self.browse_icon_size_map = dict(browse_icon_size_map or {})
        self.display_types = dict(display_types or {})
        self.search_categories = {
            variant: list(entries)
            for variant, entries in (search_categories or {}).items()
        }
        self.menu_item_overrides = list(menu_item_overrides or [])
        self.stream_quality_badges = dict(stream_quality_badges or {})
        self.now_playing_ratings = list(now_playing_ratings or [])
        self.quick_skips = {
            skip_type: dict(entry) for skip_type, entry in (quick_skips or {}).items()
        }
        self.raw_xml = raw_xml

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} uri={self.uri!r} version="
            f"{self.version} at {hex(id(self))}>"
        )

    def search_variants(self):
        """dict: The legacy ``{category: [(variant, mapped_id)]}`` mapping.

        This is the same structure used by
        :meth:`MusicService._get_search_variants`, so parsed presentation-map
        data can feed search directly.  Categories which appear in several
        ``<SearchCategories>`` blocks keep every ``(variant, mapped_id)``
        pair, in document order.
        """
        variants = {}
        for variant, entries in self.search_categories.items():
            for entry in entries:
                variants.setdefault(entry["id"], []).append(
                    (variant, entry["mapped_id"])
                )
        return variants

    def resolve_strings(self, string_tables, lang="en-US"):
        """Return a copy with presentation-map string ids resolved to text.

        The presentation map references localized strings by id
        (``StringId``, ``PromptStringId``, ``SuccessStringId``,
        ``FailureStringId``, ``InProgressStringId`` on menu-item overrides;
        ``StringId``/``OnSuccessStringId`` on ratings; ``string_id`` on
        display lines).  This returns a plain dict in the same shape as
        :attr:`menu_item_overrides`, :attr:`now_playing_ratings` and
        :attr:`display_types`, with each id resolved into its own text field
        (``text``, ``prompt_text``, ``success_text``, ``failure_text``,
        ``in_progress_text``) plus ``raw_<attr>`` keys keeping the original
        ids.

        Args:
            string_tables (:class:`StringTables`): The service strings.
            lang (str): The desired language tag.

        Returns:
            dict: ``{"menu_item_overrides": [...], "now_playing_ratings":
            [...], "display_types": {...}}`` with string ids resolved.
        """
        def resolve(string_id):
            return string_tables.resolve(string_id, lang)

        # Map a presentation-map string-id attribute to its resolved field
        # name.  Menu entries can carry separate prompt/success/failure/
        # in-progress texts, so each id is resolved into its own field rather
        # than collapsing them all into a single "text" (which would lose
        # information for entries carrying more than one id).
        text_fields = {
            "StringId": "text",
            "PromptStringId": "prompt_text",
            "SuccessStringId": "success_text",
            "FailureStringId": "failure_text",
            "InProgressStringId": "in_progress_text",
        }

        def resolved_override(override):
            result = dict(override)
            for raw_key, text_key in text_fields.items():
                if result.get(raw_key):
                    result[text_key] = resolve(result[raw_key])
                    result["raw_{}".format(raw_key)] = result[raw_key]
            return result

        def resolved_rating(entry):
            result = {
                key: dict(value) if isinstance(value, dict) else value
                for key, value in entry.items()
            }
            rating = result["rating"]
            # Mirror the menu-override treatment: a rating can carry both a
            # button label (StringId) and a success message
            # (OnSuccessStringId); resolve each into its own field instead of
            # taking the first and discarding the other.
            for raw_key, text_key in (
                ("string_id", "text"),
                ("on_success_string_id", "success_text"),
            ):
                raw_id = rating.get(raw_key)
                if raw_id:
                    rating[text_key] = resolve(raw_id)
                    rating["raw_{}".format(raw_key)] = raw_id
            return result

        def resolved_display_type(node):
            result = dict(node)
            for line in result.get("lines", []):
                if line.get("string_id"):
                    line["text"] = resolve(line["string_id"])
                    line["raw_id"] = line["string_id"]
            return result

        return {
            "menu_item_overrides": [
                resolved_override(override) for override in self.menu_item_overrides
            ],
            "now_playing_ratings": [
                resolved_rating(entry) for entry in self.now_playing_ratings
            ],
            "display_types": {
                key: resolved_display_type(node)
                for key, node in self.display_types.items()
            },
        }


def parse_presentation_map(payload, uri="", version=None):
    """Parse presentation-map XML bytes into a :class:`PresentationMap`.

    Args:
        payload (bytes): The raw presentation-map document.
        uri (str): Where the document was fetched from, kept for reference.
        version: The version advertised by the manifest, if any.

    Returns:
        :class:`PresentationMap`: The parsed model.

    Raises:
        XML.ParseError: If ``payload`` is not well-formed XML.
    """
    root = XML.fromstring(payload)

    page_size = None
    browse_options = next(
        (element for element in root if _local_name(element.tag) == "BrowseOptions"),
        None,
    )
    if browse_options is not None and browse_options.get("PageSize"):
        try:
            page_size = int(browse_options.get("PageSize"))
        except ValueError:
            pass

    artwork_size_map = {}
    browse_icon_size_map = {}
    display_types = {}
    search_categories = {}
    menu_item_overrides = []
    stream_quality_badges = {}
    now_playing_ratings = []
    quick_skips = {}

    for block in root:
        if _local_name(block.tag) != "PresentationMap":
            continue
        block_type = block.get("type", "")
        if block_type == "ArtWorkSizeMap":
            artwork_size_map = _parse_size_entries(block)
        elif block_type == "BrowseIconSizeMap":
            browse_icon_size_map = _parse_size_entries(block)
        elif block_type == "DisplayType":
            display_types = _parse_display_types(block)
        elif block_type == "Search":
            search_categories = _parse_search_categories(block)
        elif block_type == "InfoView":
            menu_item_overrides = _parse_menu_item_overrides(block)
        elif block_type == "StreamQualityBadgeDictionary":
            stream_quality_badges = _parse_quality_badges(block)
        elif block_type in ("NowPlayingRatings", "NowPlayingRatings_v2"):
            now_playing_ratings.extend(_parse_now_playing_ratings(block))
        elif block_type == "QuickSkips":
            quick_skips = _parse_quick_skips(block)

    return PresentationMap(
        uri=uri,
        version=version,
        page_size=page_size,
        artwork_size_map=artwork_size_map,
        browse_icon_size_map=browse_icon_size_map,
        display_types=display_types,
        search_categories=search_categories,
        menu_item_overrides=menu_item_overrides,
        stream_quality_badges=stream_quality_badges,
        now_playing_ratings=now_playing_ratings,
        quick_skips=quick_skips,
        raw_xml=payload.decode("utf-8", "replace"),
    )


def _parse_size_entries(block):
    """Parse an ``imageSizeMap``/``browseIconSizeMap`` block into {size: sub}."""
    result = {}
    for entry in block.iter():
        if _local_name(entry.tag) != "sizeEntry":
            continue
        size = entry.get("size")
        substitution = entry.get("substitution")
        if not size or not substitution:
            continue
        try:
            result[int(size)] = substitution
        except ValueError:
            continue
    return result


def _parse_display_types(block):
    """Parse a ``DisplayType`` block into {id: {display_mode, lines, ...}}."""
    result = {}
    for node in block:
        name = _local_name(node.tag)
        if name == "RootNodeDisplayType":
            result["__root__"] = _parse_display_node(node)
        elif name == "DisplayType" and node.get("id"):
            result[node.get("id")] = _parse_display_node(node)
    return result


def _parse_display_node(node):
    parsed = {}
    for child in node:
        name = _local_name(child.tag)
        if name == "DisplayMode":
            parsed["display_mode"] = (child.text or "").strip()
        elif name in ("Lines", "Header"):
            lines = [
                parsed_line
                for line in child
                if _local_name(line.tag) == "Line"
                for parsed_line in [_parse_line(line)]
                if parsed_line is not None
            ]
            if lines:
                parsed["lines" if name == "Lines" else "header"] = lines
        elif name == "ItemThumbnails":
            parsed["item_thumbnails"] = child.get("source", "")
    return parsed


def _parse_line(line):
    if line.get("token"):
        return {"token": line.get("token")}
    if line.get("stringId"):
        return {"string_id": line.get("stringId")}
    return None


def _parse_search_categories(block):
    """Parse a ``Search`` block into {variant: [{id, mapped_id, custom}]}."""
    result = {}
    for categories in block.iter():
        if _local_name(categories.tag) != "SearchCategories":
            continue
        variant = categories.get("stringId", "default")
        entries = result.setdefault(variant, [])
        for category in categories:
            name = _local_name(category.tag)
            if name == "Category":
                entries.append(
                    {
                        "id": category.get("id", ""),
                        "mapped_id": category.get("mappedId") or category.get("id", ""),
                        "custom": False,
                    }
                )
            elif name == "CustomCategory":
                entries.append(
                    {
                        "id": category.get("stringId", ""),
                        "mapped_id": category.get("mappedId", ""),
                        "custom": True,
                    }
                )
    return result


def _parse_menu_item_overrides(block):
    """Parse an ``InfoView`` block into the menu-item override attributes."""
    return [
        dict(item.attrib)
        for item in block.iter()
        if _local_name(item.tag) == "MenuItem"
    ]


def _parse_quality_badges(block):
    """Parse a ``StreamQualityBadgeDictionary`` block into {id: text}."""
    result = {}
    for badge in block.iter():
        if _local_name(badge.tag) != "QualityBadgeMap":
            continue
        if badge.get("id"):
            result[badge.get("id")] = badge.get("text", "")
    return result


def _parse_now_playing_ratings(block):
    """Parse a ``NowPlayingRatings`` block into per-rating entries.

    Each ``<Match>`` groups one vote/rating state (``propname``/``value``) and
    every ``<Rating>`` under it carries its ids, skip behavior and one icon
    URL per controller.  ``NowPlayingRatings_v2`` additionally carries
    ``type``/``state`` attributes on both the match and the rating.
    """
    result = []
    for match in block.iter():
        if _local_name(match.tag) != "Match":
            continue
        for rating in match.iter():
            if _local_name(rating.tag) != "Rating":
                continue
            icons = {}
            for icon in rating:
                if _local_name(icon.tag) != "Icon":
                    continue
                if icon.get("Controller") and icon.get("Uri"):
                    icons[icon.get("Controller")] = icon.get("Uri")
            result.append(
                {
                    "propname": match.get("propname", ""),
                    "value": match.get("value", ""),
                    "type": match.get("type"),
                    "rating": {
                        "id": rating.get("Id", ""),
                        "string_id": rating.get("StringId", ""),
                        "auto_skip": rating.get("AutoSkip", ""),
                        "on_success_string_id": rating.get("OnSuccessStringId", ""),
                        "type": rating.get("Type"),
                        "state": rating.get("State"),
                        "icons": icons,
                    },
                }
            )
    return result


def _parse_quick_skips(block):
    """Parse a ``QuickSkips`` block into {type: {forward, backward seconds}}."""
    result = {}
    for skip in block.iter():
        if _local_name(skip.tag) != "QuickSkip":
            continue
        skip_type = skip.get("type", "")
        if not skip_type:
            continue
        entry = {}
        for attr, key in (
            ("forwardSeconds", "forward_seconds"),
            ("backwardSeconds", "backward_seconds"),
        ):
            raw = skip.get(attr)
            if raw:
                try:
                    entry[key] = int(raw)
                except ValueError:
                    pass
        result[skip_type] = entry
    return result


def parse_string_tables(payload, uri="", version=None):
    """Parse a strings document into a :class:`StringTables`.

    The document is the ``<stringtables>`` XML advertised by the manifest's
    ``strings`` entry: one ``<stringtable xml:lang="...">`` per language,
    each holding ``<string stringId="...">text</string>`` entries.

    Args:
        payload (bytes): The raw strings document.
        uri (str): Where the document was fetched from, kept for reference.
        version: The version advertised by the manifest, if any.

    Returns:
        :class:`StringTables`: The parsed model.
    """
    root = XML.fromstring(payload)
    tables = {}
    # ``xml:lang`` is a namespaced attribute: ElementTree exposes it under the
    # XML namespace URI, so both spellings are handled here.
    lang_keys = ("xml:lang", "lang", "{http://www.w3.org/XML/1998/namespace}lang")
    for table in root.iter():
        if _local_name(table.tag) != "stringtable":
            continue
        lang = next(
            (table.get(key) for key in lang_keys if table.get(key)),
            None,
        )
        if not lang:
            continue
        entries = {}
        for entry in table:
            if _local_name(entry.tag) != "string":
                continue
            string_id = entry.get("stringId")
            if string_id:
                entries[string_id] = entry.text or ""
        tables[lang] = entries
    return StringTables(
        uri=uri,
        version=version,
        tables=tables,
        raw_xml=payload.decode("utf-8", "replace"),
    )


def _resolve_strings_uri(music_service, manifest=None):
    """Return the service strings URI, or ``""`` when none exists.

    The descriptor's ``StringsUri`` wins when advertised; otherwise the JSON
    manifest's ``strings.uri`` entry is used (Apple-style services deliver
    the strings document only through the manifest).
    """
    if getattr(music_service, "strings_uri", None):
        return music_service.strings_uri
    if manifest:
        entry = _as_mapping(manifest.get("strings"))
        return _as_string(entry.get("uri"))
    return ""


def _fetch_string_tables(music_service, session, manifest=None):
    """Fetch and parse a service's strings document.

    The URI is resolved from the descriptor or the (already fetched)
    ``manifest``.  Returns ``None`` when the service does not advertise one.
    Network and parse failures raise :class:`MusicServiceException`.

    Args:
        music_service: The legacy descriptor object.
        session: The shared requests session.
        manifest (dict, optional): The parsed service manifest, when already
            available.

    Returns:
        :class:`StringTables` or ``None``.
    """
    uri = _resolve_strings_uri(music_service, manifest)
    if not uri:
        return None
    version = None
    if manifest:
        entry = _as_mapping(manifest.get("strings"))
        version = entry.get("version")
    try:
        response = session.get(
            uri,
            headers={"Accept": "application/xml", "Accept-Language": "en-US"},
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        raise MusicServiceException(
            f"{music_service.service_name} strings request failed: {error}"
        ) from error
    try:
        return parse_string_tables(response.content, uri=uri, version=version)
    except XML.ParseError as error:
        raise MusicServiceException(
            f"{music_service.service_name} strings document was not valid XML"
        ) from error


def _resolve_presentation_map_uri(music_service, manifest=None):
    """Return the service presentation-map URI, or ``""`` when none exists.

    The descriptor's ``PresentationMapUri`` wins when advertised; otherwise
    the JSON manifest's ``presentationMap.uri`` entry is used (Apple-style
    services deliver the presentation map only through the manifest).
    """
    if music_service.presentation_map_uri:
        return music_service.presentation_map_uri
    if manifest:
        entry = _as_mapping(manifest.get("presentationMap"))
        return _as_string(entry.get("uri"))
    return ""


def _fetch_presentation_map(music_service, session, manifest=None):
    """Fetch and parse a service's presentation map.

    The URI is resolved from the descriptor or the (already fetched)
    ``manifest``.  Returns ``None`` when the service does not advertise a
    presentation map.  Network and parse failures raise
    :class:`MusicServiceException`; callers decide when to pay that cost.

    Args:
        music_service: The legacy descriptor object.
        session: The shared requests session.
        manifest (dict, optional): The parsed service manifest, when already
            available.

    Returns:
        :class:`PresentationMap` or ``None``.
    """
    uri = _resolve_presentation_map_uri(music_service, manifest)
    if not uri:
        return None
    version = None
    if manifest:
        entry = _as_mapping(manifest.get("presentationMap"))
        version = entry.get("version")
    try:
        response = session.get(uri, headers={"Accept": "application/xml"}, timeout=20)
        response.raise_for_status()
    except requests.RequestException as error:
        raise MusicServiceException(
            f"{music_service.service_name} presentation map request failed: {error}"
        ) from error
    try:
        return parse_presentation_map(response.content, uri=uri, version=version)
    except XML.ParseError as error:
        raise MusicServiceException(
            f"{music_service.service_name} presentation map was not valid XML"
        ) from error
