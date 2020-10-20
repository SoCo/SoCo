# -*- coding: utf-8 -*-
# pylint: disable = star-args, too-many-arguments, unsupported-membership-test
# pylint: disable = not-an-iterable

# Disable while we have Python 2.x compatability
# pylint: disable=useless-object-inheritance

"""This module contains all the data structures for music service plugins."""

# This needs to be integrated with Music Library data structures

from __future__ import unicode_literals

from .exceptions import DIDLMetadataError
from .utils import camel_to_underscore
from .xml import NAMESPACES, XML, ns_tag


def get_ms_item(xml, service, parent_id):
    """Return the music service item that corresponds to xml.

    The class is identified by getting the type from the 'itemType' tag
    """
    cls = MS_TYPE_TO_CLASS.get(xml.findtext(ns_tag("ms", "itemType")))
    out = cls.from_xml(xml, service, parent_id)
    return out


def tags_with_text(xml, tags=None):
    """Return a list of tags that contain text retrieved recursively from an
    XML tree."""
    if tags is None:
        tags = []
    for element in xml:
        if element.text is not None:
            tags.append(element)
        elif len(element) > 0:  # pylint: disable=len-as-condition
            tags_with_text(element, tags)
        else:
            message = "Unknown XML structure: {}".format(element)
            raise ValueError(message)
    return tags


class MusicServiceItem(object):

    """Class that represents a music service item."""

    # These fields must be overwritten in the sub classes
    item_class = None
    valid_fields = None
    required_fields = None

    def __init__(self, **kwargs):
        super().__init__()
        self.content = kwargs

    @classmethod
    def from_xml(cls, xml, service, parent_id):
        """Return a Music Service item generated from xml.

        :param xml: Object XML. All items containing text are added to the
            content of the item. The class variable ``valid_fields`` of each of
            the classes list the valid fields (after translating the camel
            case to underscore notation). Required fields are listed in the
            class variable by that name (where 'id' has been renamed to
            'item_id').
        :type xml: :py:class:`xml.etree.ElementTree.Element`
        :param service: The music service (plugin) instance that retrieved the
            element. This service must contain ``id_to_extended_id`` and
            ``form_uri`` methods and ``description`` and ``service_id``
            attributes.
        :type service: Instance of sub-class of
            :class:`soco.plugins.SoCoPlugin`
        :param parent_id: The parent ID of the item, will either be the
            extended ID of another MusicServiceItem or of a search
        :type parent_id: str

        For a track the XML can e.g. be on the following form:

        .. code :: xml

         <mediaMetadata xmlns="http://www.sonos.com/Services/1.1">
           <id>trackid_141359</id>
           <itemType>track</itemType>
           <mimeType>audio/aac</mimeType>
           <title>Teacher</title>
           <trackMetadata>
             <artistId>artistid_10597</artistId>
             <artist>Jethro Tull</artist>
             <composerId>artistid_10597</composerId>
             <composer>Jethro Tull</composer>
             <albumId>albumid_141358</albumId>
             <album>MU - The Best Of Jethro Tull</album>
             <albumArtistId>artistid_10597</albumArtistId>
             <albumArtist>Jethro Tull</albumArtist>
             <duration>229</duration>
             <albumArtURI>http://varnish01.music.aspiro.com/sca/
              imscale?h=90&amp;w=90&amp;img=/content/music10/prod/wmg/
              1383757201/094639008452_20131105025504431/resources/094639008452.
              jpg</albumArtURI>
             <canPlay>true</canPlay>
             <canSkip>true</canSkip>
             <canAddToFavorites>true</canAddToFavorites>
           </trackMetadata>
         </mediaMetadata>
        """
        # Add a few extra pieces of information
        content = {
            "description": service.description,
            "service_id": service.service_id,
            "parent_id": parent_id,
        }
        # Extract values from the XML
        all_text_elements = tags_with_text(xml)
        for item in all_text_elements:
            tag = item.tag[len(NAMESPACES["ms"]) + 2 :]  # Strip namespace
            tag = camel_to_underscore(tag)  # Convert to nice names
            if tag not in cls.valid_fields:
                message = "The info tag '{}' is not allowed for this item".format(tag)
                raise ValueError(message)
            content[tag] = item.text

        # Convert values for known types
        for key, value in content.items():
            if key == "duration":
                content[key] = int(value)
            if key in ["can_play", "can_skip", "can_add_to_favorites", "can_enumerate"]:
                content[key] = value == "true"
        # Rename a single item
        content["item_id"] = content.pop("id")
        # And get the extended id
        content["extended_id"] = service.id_to_extended_id(content["item_id"], cls)
        # Add URI if there is one for the relevant class
        uri = service.form_uri(content, cls)
        if uri:
            content["uri"] = uri

        # Check for all required values
        for key in cls.required_fields:
            if key not in content:
                message = (
                    "An XML field that correspond to the key '{}' "
                    "is required. See the docstring for help.".format(key)
                )

        return cls.from_dict(content)

    @classmethod
    def from_dict(cls, dict_in):
        """Initialize the class from a dict.

        :param dict_in: The dictionary that contains the item content. Required
            fields are listed class variable by that name
        :type dict_in: dict
        """
        kwargs = dict_in.copy()
        args = [kwargs.pop(key) for key in cls.required_fields]
        return cls(*args, **kwargs)

    def __eq__(self, playable_item):
        """Return the equals comparison result to another ``playable_item``."""
        if not isinstance(playable_item, MusicServiceItem):
            return False
        return self.content == playable_item.content

    def __ne__(self, playable_item):
        """Return the not equals comparison result to another
        ``playable_item``"""
        if not isinstance(playable_item, MusicServiceItem):
            return True
        return self.content != playable_item.content

    def __repr__(self):
        """Return the repr value for the item.

        The repr is on the form::

          <class_name 'middle_part[0:40]' at id_in_hex>

        where middle_part is either the title item in content, if it is set,
        or ``str(content)``. The output is also cleared of non-ascii
        characters.
        """
        # 40 originates from terminal width (78) - (15) for address part and
        # (19) for the longest class name and a little left for buffer
        if self.content.get("title") is not None:
            middle = self.content["title"].encode("ascii", "replace")[0:40]
        else:
            middle = str(self.content).encode("ascii", "replace")[0:40]
        return "<{} '{}' at {}>".format(self.__class__.__name__, middle, hex(id(self)))

    def __str__(self):
        """Return the str value for the item::

         <class_name 'middle_part[0:40]' at id_in_hex>

        where middle_part is either the title item in content, if it is set, or
        ``str(content)``. The output is also cleared of non-ascii characters.

        """
        return self.__repr__()

    @property
    def to_dict(self):
        """Return a copy of the content dict."""
        return self.content.copy()

    @property
    def didl_metadata(self):
        """Return the DIDL metadata for a Music Service Track.

        The metadata is on the form:

        .. code :: xml

         <DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"
              xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
              xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"
              xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
           <item id="...self.extended_id..."
              parentID="...self.parent_id..."
              restricted="true">
             <dc:title>...self.title...</dc:title>
             <upnp:class>...self.item_class...</upnp:class>
             <desc id="cdudn"
                nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">
               self.content['description']
             </desc>
           </item>
         </DIDL-Lite>
        """
        # Check if this item is meant to be played
        if not self.can_play:
            message = (
                "This item is not meant to be played and therefore "
                "also not to create its own didl_metadata"
            )
            raise DIDLMetadataError(message)
        # Check if we have the attributes to create the didl metadata:
        for key in ["extended_id", "title", "item_class"]:
            if not hasattr(self, key):
                message = (
                    "The property '{}' is not present on this item. "
                    "This indicates that this item was not meant to create "
                    "didl_metadata".format(key)
                )
                raise DIDLMetadataError(message)
        if "description" not in self.content:
            message = (
                "The item for 'description' is not present in "
                "self.content. This indicates that this item was not meant "
                "to create didl_metadata"
            )
            raise DIDLMetadataError(message)

        # Main element, ugly? yes! but I have given up on using namespaces
        # with xml.etree.ElementTree
        xml = XML.Element("{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}DIDL-Lite")
        # Item sub element
        item_attrib = {"parentID": "", "restricted": "true", "id": self.extended_id}
        # Only add the parent_id if we have it
        if self.parent_id:
            item_attrib["parentID"] = self.parent_id
        item = XML.SubElement(
            xml,
            "{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item",
            item_attrib,
        )

        # Add title and class
        XML.SubElement(
            item,
            "{http://purl.org/dc/elements/1.1/}title",
        ).text = self.title
        XML.SubElement(
            item,
            "{urn:schemas-upnp-org:metadata-1-0/upnp/}class",
        ).text = self.item_class
        # Add the desc element
        desc_attrib = {
            "id": "cdudn",
            "nameSpace": "urn:schemas-rinconnetworks-com:metadata-1-0/",
        }
        desc = XML.SubElement(
            item,
            "{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}desc",
            desc_attrib,
        )
        desc.text = self.content["description"]

        return xml

    @property
    def item_id(self):
        """Return the item id."""
        return self.content["item_id"]

    @property
    def extended_id(self):
        """Return the extended id."""
        return self.content["extended_id"]

    @property
    def title(self):
        """Return the title."""
        return self.content["title"]

    @property
    def service_id(self):
        """Return the service ID."""
        return self.content["service_id"]

    @property
    def can_play(self):
        """Return a boolean for whether the item can be played."""
        return bool(self.content.get("can_play"))

    @property
    def parent_id(self):
        """Return the extended parent_id, if set, otherwise return None."""
        return self.content.get("parent_id")

    @property
    def album_art_uri(self):
        """Return the album art URI if set, otherwise return None."""
        return self.content.get("album_art_uri")


class MSTrack(MusicServiceItem):

    """Class that represents a music service track."""

    item_class = "object.item.audioItem.musicTrack"
    valid_fields = [
        "album",
        "can_add_to_favorites",
        "artist",
        "album_artist_id",
        "title",
        "album_id",
        "album_art_uri",
        "album_artist",
        "composer_id",
        "item_type",
        "composer",
        "duration",
        "can_skip",
        "artist_id",
        "can_play",
        "id",
        "mime_type",
        "description",
    ]
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = [
        "title",
        "item_id",
        "extended_id",
        "uri",
        "description",
        "service_id",
    ]

    def __init__(
        self, title, item_id, extended_id, uri, description, service_id, **kwargs
    ):
        """Initialize MSTrack item."""
        content = {
            "title": title,
            "item_id": item_id,
            "extended_id": extended_id,
            "uri": uri,
            "description": description,
            "service_id": service_id,
        }
        content.update(kwargs)
        super().__init__(**content)

    @property
    def album(self):
        """Return the album title if set, otherwise return None."""
        return self.content.get("album")

    @property
    def artist(self):
        """Return the artist if set, otherwise return None."""
        return self.content.get("artist")

    @property
    def duration(self):
        """Return the duration if set, otherwise return None."""
        return self.content.get("duration")

    @property
    def uri(self):
        """Return the URI."""
        # x-sonos-http:trackid_19356232.mp4?sid=20&amp;flags=32
        return self.content["uri"]


class MSAlbum(MusicServiceItem):

    """Class that represents a Music Service Album."""

    item_class = "object.container.album.musicAlbum"
    valid_fields = [
        "username",
        "can_add_to_favorites",
        "artist",
        "title",
        "album_art_uri",
        "can_play",
        "item_type",
        "service_id",
        "id",
        "description",
        "can_cache",
        "artist_id",
        "can_skip",
    ]
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = [
        "title",
        "item_id",
        "extended_id",
        "uri",
        "description",
        "service_id",
    ]

    def __init__(
        self, title, item_id, extended_id, uri, description, service_id, **kwargs
    ):
        content = {
            "title": title,
            "item_id": item_id,
            "extended_id": extended_id,
            "uri": uri,
            "description": description,
            "service_id": service_id,
        }
        content.update(kwargs)
        super().__init__(**content)

    @property
    def artist(self):
        """Return the artist if set, otherwise return None."""
        return self.content.get("artist")

    @property
    def uri(self):
        """Return the URI."""
        # x-rincon-cpcontainer:0004002calbumid_22757081
        return self.content["uri"]


class MSAlbumList(MusicServiceItem):

    """Class that represents a Music Service Album List."""

    item_class = "object.container.albumlist"
    valid_fields = [
        "id",
        "title",
        "item_type",
        "artist",
        "artist_id",
        "can_play",
        "can_enumerate",
        "can_add_to_favorites",
        "album_art_uri",
        "can_cache",
    ]
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = [
        "title",
        "item_id",
        "extended_id",
        "uri",
        "description",
        "service_id",
    ]

    def __init__(
        self, title, item_id, extended_id, uri, description, service_id, **kwargs
    ):
        content = {
            "title": title,
            "item_id": item_id,
            "extended_id": extended_id,
            "uri": uri,
            "description": description,
            "service_id": service_id,
        }
        content.update(kwargs)
        super().__init__(**content)

    @property
    def uri(self):
        """Return the URI."""
        # x-rincon-cpcontainer:000d006cplaylistid_26b18dbb-fd35-40bd-8d4f-
        # 8669bfc9f712
        return self.content["uri"]


class MSPlaylist(MusicServiceItem):

    """Class that represents a Music Service Play List."""

    item_class = "object.container.albumlist"
    valid_fields = [
        "id",
        "item_type",
        "title",
        "can_play",
        "can_cache",
        "album_art_uri",
        "artist",
        "can_enumerate",
        "can_add_to_favorites",
        "artist_id",
    ]
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = [
        "title",
        "item_id",
        "extended_id",
        "uri",
        "description",
        "service_id",
    ]

    def __init__(
        self, title, item_id, extended_id, uri, description, service_id, **kwargs
    ):
        content = {
            "title": title,
            "item_id": item_id,
            "extended_id": extended_id,
            "uri": uri,
            "description": description,
            "service_id": service_id,
        }
        content.update(kwargs)
        super().__init__(**content)

    @property
    def uri(self):
        """Return the URI."""
        # x-rincon-cpcontainer:000d006cplaylistid_c86ddf26-8ec5-483e-b292-
        # abe18848e89e
        return self.content["uri"]


class MSArtistTracklist(MusicServiceItem):

    """Class that represents a Music Service Artist Track List."""

    item_class = "object.container.playlistContainer.sameArtist"
    valid_fields = ["id", "title", "item_type", "can_play", "album_art_uri"]
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = [
        "title",
        "item_id",
        "extended_id",
        "uri",
        "description",
        "service_id",
    ]

    def __init__(
        self, title, item_id, extended_id, uri, description, service_id, **kwargs
    ):
        content = {
            "title": title,
            "item_id": item_id,
            "extended_id": extended_id,
            "uri": uri,
            "description": description,
            "service_id": service_id,
        }
        content.update(kwargs)
        super().__init__(**content)

    @property
    def uri(self):
        """Return the URI."""
        # x-rincon-cpcontainer:100f006cartistpopsongsid_1566
        return "x-rincon-cpcontainer:100f006c{}".format(self.item_id)


class MSArtist(MusicServiceItem):

    """Class that represents a Music Service Artist."""

    valid_fields = [
        "username",
        "can_add_to_favorites",
        "artist",
        "title",
        "album_art_uri",
        "item_type",
        "id",
        "service_id",
        "description",
        "can_cache",
    ]
    # Since MSArtist cannot produce didl_metadata, they are not strictly
    # required, but it makes sense to require them anyway, since they are the
    # fields that that describe the item
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = ["title", "item_id", "extended_id", "service_id"]

    def __init__(self, title, item_id, extended_id, service_id, **kwargs):
        content = {
            "title": title,
            "item_id": item_id,
            "extended_id": extended_id,
            "service_id": service_id,
        }
        content.update(kwargs)
        super().__init__(**content)


class MSFavorites(MusicServiceItem):

    """Class that represents a Music Service Favorite."""

    valid_fields = [
        "id",
        "item_type",
        "title",
        "can_play",
        "can_cache",
        "album_art_uri",
    ]
    # Since MSFavorites cannot produce didl_metadata, they are not strictly
    # required, but it makes sense to require them anyway, since they are the
    # fields that that describe the item
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = ["title", "item_id", "extended_id", "service_id"]

    def __init__(self, title, item_id, extended_id, service_id, **kwargs):
        content = {
            "title": title,
            "item_id": item_id,
            "extended_id": extended_id,
            "service_id": service_id,
        }
        content.update(kwargs)
        super().__init__(**content)


class MSCollection(MusicServiceItem):

    """Class that represents a Music Service Collection."""

    valid_fields = [
        "id",
        "item_type",
        "title",
        "can_play",
        "can_cache",
        "album_art_uri",
    ]
    # Since MSCollection cannot produce didl_metadata, they are not strictly
    # required, but it makes sense to require them anyway, since they are the
    # fields that that describe the item
    # IMPORTANT. Keep this list, __init__ args and content in __init__ in sync
    required_fields = ["title", "item_id", "extended_id", "service_id"]

    def __init__(self, title, item_id, extended_id, service_id, **kwargs):
        content = {
            "title": title,
            "item_id": item_id,
            "extended_id": extended_id,
            "service_id": service_id,
        }
        content.update(kwargs)
        super().__init__(**content)


MS_TYPE_TO_CLASS = {
    "artist": MSArtist,
    "album": MSAlbum,
    "track": MSTrack,
    "albumList": MSAlbumList,
    "favorites": MSFavorites,
    "collection": MSCollection,
    "playlist": MSPlaylist,
    "artistTrackList": MSArtistTracklist,
}
