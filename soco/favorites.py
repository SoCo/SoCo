"""Access to the Sonos favorites list.

The favorites list is stored by the speakers in the ``FV:2`` container of
the ContentDirectory service. It has a fixed capacity: once the list is
full, adding another favorite fails with UPnP error 805 and
`FavoritesFullError` is raised.
"""

import re

from xml.sax.saxutils import escape

from . import discovery
from .data_structures import (
    DidlContainer,
    DidlObject,
    DidlFavorite,
    DidlPerson,
    DidlResource,
    to_didl_string,
)
from .exceptions import (
    FavoritesAlreadyAddedError,
    FavoritesFullError,
    SoCoUPnPException,
)


def _escape_xml(value):
    """Escape a string for inclusion in DIDL XML, including double quotes."""
    return escape(value, {'"': "&quot;"})


class Favorites:
    """The Sonos favorites list.

    Write access to the favorites (:meth:`add`, :meth:`remove`,
    :meth:`update`, :meth:`rename`). For reading the list, use
    `MusicLibrary`, e.g. ``device.music_library.get_sonos_favorites()``.
    """

    # pylint: disable=invalid-name, protected-access
    def __init__(self, soco=None):
        """
        Args:
            soco (`SoCo`, optional): A `SoCo` instance to query for
                favorites information. If `None`, or not supplied, a
                random `SoCo` instance will be used.
        """
        self.soco = soco if soco is not None else discovery.any_soco()
        self.contentDirectory = self.soco.contentDirectory

    @staticmethod
    def _favorite_object_id(favorite):
        """Return the item id of a favorite from a `DidlFavorite` or id."""
        if isinstance(favorite, DidlFavorite):
            return favorite.item_id
        return str(favorite)

    def add(self, item, title=None, description=None):
        """Add an item to the Sonos favorites list.

        Args:
            item (DidlObject): The item to add, e.g. a track, album,
                playlist or radio station from the music library or a
                music service. Containers without a playable resource of
                their own (e.g. music service albums) are stored with a
                container URI derived from their item id, which is how the
                speakers play them; browsable-only containers (artists,
                composers) are stored as navigational shortcut favorites.
            title (str, optional): The title to show for the favorite.
                Defaults to the item's own title.
            description (str, optional): An optional description shown
                alongside the favorite, e.g. the artist name.

        Returns:
            DidlFavorite: The newly created favorite. Its resources are
                playable, including the synthesized container URI stored
                for resource-less service containers.

        Raises:
            TypeError: if ``item`` is not a `DidlObject`.
            ValueError: if ``item`` has no resource with a URI to add,
                or if ``title`` or ``description`` is an empty string;
                empty values are not supported by the speaker.
            FavoritesFullError: if the favorites list is at capacity.
            FavoritesAlreadyAddedError: if the item is already a favorite.
            SoCoUPnPException: if the item cannot be added for another
                reason.

        Example:
            Add the first track of an album to favorites::

                album = next(device.music_library.get_albums())
                track = next(album.get_tracks())
                device.favorites.add(track)
        """
        if not isinstance(item, DidlObject):
            raise TypeError(f"item must be a DidlObject, got {type(item)!r}")
        if (title if title is not None else item.title) == "":
            raise ValueError("title cannot be empty; dc:title is required")
        if description == "":
            raise ValueError("description cannot be emptied")
        if item.resources and item.resources[0].uri:
            uri = item.get_uri()
            protocol_info = item.resources[0].protocol_info
            favorite_type = "instantPlay"
            synthesized_uri = False
        elif isinstance(item, DidlContainer) and item.item_id:
            # Service containers carry no resource of their own. Playable
            # ones (albums, playlists) are stored as instantPlay favorites
            # with a container URI derived from the item id, which is how
            # the speakers play them. Browsable-only containers (artists,
            # composers) become navigational shortcut favorites with no
            # resource, matching how the Sonos app stores them.
            if isinstance(item, DidlPerson):
                uri = None
                protocol_info = None
                favorite_type = "shortcut"
                synthesized_uri = False
            else:
                uri = "x-rincon-cpcontainer:" + item.item_id
                protocol_info = "x-rincon-cpcontainer:*:*:*"
                favorite_type = "instantPlay"
                synthesized_uri = True
        else:
            raise ValueError(
                "item must have a resource with a URI to be added as a favorite"
            )
        # albumArtURI is emitted at favorite level (as real Sonos favorites
        # do) and stripped from resMD: the speaker silently truncates resMD
        # past a size limit, and double-escaped art URLs are its biggest
        # contributor.
        inner = re.sub(
            r"<upnp:albumArtURI>.*?</upnp:albumArtURI>", "", to_didl_string(item)
        )
        album_art_uri = getattr(item, "album_art_uri", None)
        new_title = _escape_xml(title if title is not None else item.title)
        res = ""
        if uri is not None:
            res = "<res"
            if protocol_info:
                res += f' protocolInfo="{_escape_xml(protocol_info)}"'
            res += ">" + escape(uri) + "</res>"
        elements = (
            '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
            'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
            'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            '<item id="" parentID="FV:2" restricted="false">'
            f"<dc:title>{new_title}</dc:title>"
            "<upnp:class>object.itemobject.item.sonos-favorite</upnp:class>"
            "<r:ordinal>0</r:ordinal>" + res + f"<r:type>{favorite_type}</r:type>"
        )
        if album_art_uri:
            elements += f"<upnp:albumArtURI>{escape(album_art_uri)}</upnp:albumArtURI>"
        if description:
            escaped_description = _escape_xml(description)
            elements += f"<r:description>{escaped_description}</r:description>"
        elements += f"<r:resMD>{escape(inner)}</r:resMD></item></DIDL-Lite>"

        try:
            result = self.contentDirectory.CreateObject(
                [("ContainerID", "FV:2"), ("Elements", elements)]
            )
        except SoCoUPnPException as exc:
            if exc.error_code == "805":
                raise FavoritesFullError(
                    f"The Sonos favorites list is full (UPnP error {exc.error_code})"
                ) from exc
            if exc.error_code == "803":
                raise FavoritesAlreadyAddedError(
                    "This item is already in the Sonos favorites list "
                    f"(UPnP error {exc.error_code})"
                ) from exc
            raise

        favorite = DidlFavorite(
            title if title is not None else item.title,
            "FV:2",
            result["ObjectID"],
            restricted=False,
        )
        favorite.reference = item
        if synthesized_uri:
            # Give the returned favorite the synthesized resource so it is playable.
            favorite.resources = [DidlResource(uri, protocol_info)]
        return favorite

    def remove(self, favorite):
        """Remove a favorite from the Sonos favorites list.

        Args:
            favorite: The favorite to remove. Either a `DidlFavorite`
                object (as returned by
                `MusicLibrary.get_sonos_favorites`) or its item id as a
                string, e.g. ``"FV:2/28"``.

        Raises:
            SoCoUPnPException: if the favorite does not exist (error 701).

        Example:
            Remove the first favorite::

                favorite = device.music_library.get_sonos_favorites()[0]
                device.favorites.remove(favorite)
        """
        object_id = self._favorite_object_id(favorite)
        self.contentDirectory.DestroyObject([("ObjectID", object_id)])

    @staticmethod
    def _extract_element(didl, tag):
        """Return the first ``<tag>...</tag>`` fragment found in ``didl``.

        Returns an empty string if the element is not present, which is
        the placeholder ``UpdateObject`` expects in ``CurrentTagValue``
        for a property that does not yet exist on the object.
        """
        match = re.search(f"(<{tag}>.*?</{tag}>)", didl, flags=re.DOTALL)
        return match.group(1) if match else ""

    def update(self, favorite, title=None, description=None):
        """Update the metadata of a favorite.

        Currently supports updating the ``title`` and ``description``
        fields. Only the fields supplied are changed; everything else
        (URI, artwork, metadata) is preserved. A ``description`` can be
        added to a favorite that does not have one; Sonos does not
        support deleting favorite properties once set.

        Args:
            favorite: The favorite to update. Either a `DidlFavorite`
                object or its item id as a string, e.g. ``"FV:2/28"``.
            title (str, optional): The new title for the favorite.
            description (str, optional): The new description shown
                alongside the favorite.

        Raises:
            ValueError: if ``title`` or ``description`` is an empty
                string; empty values are not supported by the speaker.
            SoCoUPnPException: if the favorite does not exist (error 701)
                or the metadata cannot be updated.

        Example:
            Rename the first favorite::

                favorite = device.music_library.get_sonos_favorites()[0]
                device.favorites.update(
                    favorite, title="My Fave", description="By Artist"
                )
        """
        # Sonos does not support deleting favorite properties: every form of
        # deletion (empty placeholder, empty element, bare tag name) is
        # rejected with UPnP error 712. Reject empty values up front.
        if title == "":
            raise ValueError("title cannot be empty; dc:title is required")
        if description == "":
            raise ValueError("description cannot be emptied")
        object_id = self._favorite_object_id(favorite)
        updates = []
        if title is not None:
            updates.append(("dc:title", title))
        if description is not None:
            updates.append(("r:description", description))
        if not updates:
            return
        result = self.contentDirectory.Browse(
            [
                ("ObjectID", object_id),
                ("BrowseFlag", "BrowseMetadata"),
                ("Filter", "*"),
                ("StartingIndex", 0),
                ("RequestedCount", 0),
                ("SortCriteria", ""),
            ]
        )["Result"]
        current_values = []
        new_values = []
        for tag, value in updates:
            escaped = _escape_xml(str(value))
            new_fragment = f"<{tag}>{escaped}</{tag}>"
            current_fragment = self._extract_element(result, tag)
            # Note: commas are sent unescaped. Sonos parses TagValueList as
            # XML fragments and stores the spec's \, escaping literally.
            if current_fragment != new_fragment:
                current_values.append(current_fragment)
                new_values.append(new_fragment)
        if not new_values:
            return
        self.contentDirectory.UpdateObject(
            [
                ("ObjectID", object_id),
                ("CurrentTagValue", ",".join(current_values)),
                ("NewTagValue", ",".join(new_values)),
            ]
        )

    def rename(self, favorite, new_title):
        """Rename a favorite in the Sonos favorites list.

        Convenience wrapper around :meth:`update`.

        Args:
            favorite: The favorite to rename. Either a `DidlFavorite`
                object or its item id as a string, e.g. ``"FV:2/28"``.
            new_title (str): The new title for the favorite.

        Raises:
            SoCoUPnPException: if the favorite does not exist (error 701)
                or the title cannot be updated.
        """
        self.update(favorite, title=new_title)
