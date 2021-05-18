# pylint: disable=star-args, too-many-arguments, fixme, import-outside-toplevel

# Disable while we have Python 2.x compatability
# pylint: disable=useless-object-inheritance,bad-mcs-classmethod-argument

"""
This module contains classes for handling DIDL-Lite metadata.

`DIDL`_ is the Digital Item Declaration Language , an XML schema which is
part of MPEG21. `DIDL-Lite`_ is a cut-down version of the schema which is part
of the UPnP ContentDirectory specification. It is the XML schema used by Sonos
for carrying metadata representing many items such as tracks, playlists,
composers, albums etc. Although Sonos uses
ContentDirectory v1, the `document for v2 [pdf]`_ is more
helpful.

.. _DIDL: http://xml.coverpages.org/mpeg21-didl.html
.. _DIDL-Lite: http://www.upnp.org/schemas/av/didl-lite-v2.xsd
.. _document for v2 [pdf]: _http://upnp.org/specs/av/UPnP
     -av-ContentDirectory-v2-Service

"""

# It tries to follow the class hierarchy provided by the DIDL-Lite schema
# described in the UPnP Spec, especially that for the ContentDirectory Service

# Although Sonos uses ContentDirectory v1, the document for v2 is more helpful:
# http://upnp.org/specs/av/UPnP-av-ContentDirectory-v2-Service.pdf


import textwrap
import warnings

from .exceptions import DIDLMetadataError
from .utils import really_unicode, first_cap
from .xml import XML, ns_tag
from .data_structure_quirks import apply_resource_quirks

# Due to cyclic import problems, we only import from_didl_string at runtime.
# from data_structures_entry import from_didl_string
_FROM_DIDL_STRING_FUNCTION = None


###############################################################################
# MISC HELPER FUNCTIONS                                                       #
###############################################################################


def to_didl_string(*args):
    """Convert any number of `DidlObjects <DidlObject>` to a unicode xml
    string.

    Args:
        *args (DidlObject): One or more `DidlObject` (or subclass) instances.

    Returns:
        str: A unicode string representation of DIDL-Lite XML in the form
        ``'<DIDL-Lite ...>...</DIDL-Lite>'``.
    """
    didl = XML.Element(
        "DIDL-Lite",
        {
            "xmlns": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
            "xmlns:dc": "http://purl.org/dc/elements/1.1/",
            "xmlns:upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/",
            "xmlns:r": "urn:schemas-rinconnetworks-com:metadata-1-0/",
        },
    )
    for arg in args:
        didl.append(arg.to_element())
    return XML.tostring(didl, encoding="unicode")


def didl_class_to_soco_class(didl_class):
    """Translate a DIDL-Lite class to the corresponding SoCo data structures class"""
    # Certain music services have been observed to sub-class via a .# or # syntax.
    # We simply remove these subclasses.
    for separator in (".#", "#"):
        if separator in didl_class:
            didl_class = didl_class[: didl_class.find(separator)]

    try:
        cls = _DIDL_CLASS_TO_CLASS[didl_class]
    except KeyError:
        # Unknown class, automatically create subclass
        new_class_name = form_name(didl_class)
        base_class = didl_class_to_soco_class(".".join(didl_class.split(".")[:-1]))
        cls = type(
            new_class_name,
            (base_class,),
            {
                "item_class": didl_class,
                __doc__: "Class that represents a {}".format(didl_class),
            },
        )
        _DIDL_CLASS_TO_CLASS[didl_class] = cls

    return cls


_OFFICIAL_CLASSES = {
    "object",
    "object.item",
    "object.item.audioItem",
    "object.item.audioItem.musicTrack",
    "object.item.audioItem.audioBroadcast",
    "object.item.audioItem.audioBook",
    "object.container",
    "object.container.person",
    "object.container.person.musicArtist",
    "object.container.playlistContainer",
    "object.container.album",
    "object.container.musicAlbum",
    "object.container.genre",
    "object.container.musicGenre",
}


def form_name(didl_class):
    """Return an improvised name for vendor extended classes"""
    if not didl_class.startswith("object."):
        raise DIDLMetadataError("Unknown UPnP class: %s" % didl_class)

    # We know that the string starts with "object." so -1 indexing is safe
    parts = didl_class.split(".")
    # If it is a Sonos favorite, form the name as the class component
    # before with "Favorite" added. So:
    # object.item.audioItem.audioBroadcast.sonos-favorite
    # turns into
    # DidlAudioBroadcastFavorite
    if parts[-1] == "sonos-favorite" and len(parts) >= 2:
        return "Didl" + first_cap(parts[-2]) + "Favorite"

    # For any other class, for the name as the concatenation of all
    # the class components that are not UPnP core classes. So:
    # object.container.playlistContainer.sameArtist
    # Turns into:
    # DidlSameArtist
    search_parts = parts[:]
    new_parts = []
    # Strip the components one by one and check whether the base is known
    while search_parts:
        new_parts.append(search_parts[-1])
        search_parts = search_parts[:-1]
        search_class = ".".join(search_parts)
        if search_class in _OFFICIAL_CLASSES:
            break

    # For class path last parts that contain the word list, capitalize it
    if new_parts[0].endswith("list"):
        new_parts[0] = new_parts[0].replace("list", "List")
    new_parts = reversed(new_parts)

    return "Didl" + "".join(first_cap(s) for s in new_parts)


###############################################################################
# DIDL RESOURCE                                                               #
###############################################################################


class DidlResource:

    """Identifies a resource, typically some type of a binary asset, such as a
    song.

    It is represented in XML by a ``<res>`` element, which contains a uri that
    identifies the resource.
    """

    # Adapted from a class taken from the Python Brisa project - MIT licence.

    # pylint: disable=too-many-instance-attributes
    def __init__(
        self,
        uri,
        protocol_info,
        import_uri=None,
        size=None,
        duration=None,
        bitrate=None,
        sample_frequency=None,
        bits_per_sample=None,
        nr_audio_channels=None,
        resolution=None,
        color_depth=None,
        protection=None,
    ):
        """
        Args:
            uri (str): value of the ``<res>`` tag, typically a URI. It
                **must** be properly escaped (percent encoded) as
                described in :rfc:`3986`
            protocol_info (str):  a string in the form a:b:c:d that
                identifies the streaming or transport protocol for
                transmitting the resource. A value is required. For more
                information see section 2.5.2 of the `UPnP specification [
                pdf]
                <http://upnp.org/specs/av/UPnP-av-ConnectionManager-v1-
                Service.pdf>`_
            import_uri (str, optional): uri locator for resource update.
            size (int, optional): size in bytes.
            duration (str, optional): duration of the playback of the res
                at normal speed (``H*:MM:SS:F*`` or ``H*:MM:SS:F0/F1``)
            bitrate (int, optional): bitrate in bytes/second.
            sample_frequency (int, optional): sample frequency in Hz.
            bits_per_sample (int, optional): bits per sample.
            nr_audio_channels (int, optional): number of audio channels.
            resolution (str, optional): resolution of the resource (X*Y).
            color_depth (int, optional): color depth in bits.
            protection (str, optional): statement of protection type.

        Note:
            Not all of the parameters are used by Sonos. In general, only
            ``uri``, ``protocol_info`` and ``duration`` seem to be important.
        """
        # Of these attributes, only uri, protocol_info and duration have been
        # spotted 'in the wild'
        #: (str): a percent encoded URI
        self.uri = uri
        # Protocol info is in the form a:b:c:d - see
        # sec 2.5.2 at
        # http://upnp.org/specs/av/UPnP-av-ConnectionManager-v1-Service.pdf
        #: (str): protocol information.
        self.protocol_info = protocol_info
        self.import_uri = import_uri
        self.size = size
        #: str: playback duration
        self.duration = duration
        self.bitrate = bitrate
        self.sample_frequency = sample_frequency
        self.bits_per_sample = bits_per_sample
        self.nr_audio_channels = nr_audio_channels
        self.resolution = resolution
        self.color_depth = color_depth
        self.protection = protection

    @classmethod
    def from_element(cls, element):
        """Set the resource properties from a ``<res>`` element.

        Args:
            element (~xml.etree.ElementTree.Element): The ``<res>``
                element

        """

        def _int_helper(name):
            """Try to convert the name attribute to an int, or None."""
            result = element.get(name)
            if result is not None:
                try:
                    return int(result)
                except ValueError as error:
                    raise DIDLMetadataError(
                        "Could not convert {} to an integer".format(name)
                    ) from error
            else:
                return None

        # Check for and fix non-spec compliant behavior in the incoming data
        element = apply_resource_quirks(element)

        content = {}
        # required
        content["protocol_info"] = element.get("protocolInfo")
        if content["protocol_info"] is None:
            raise DIDLMetadataError(
                "Could not create Resource from Element: "
                "protocolInfo not found (required)."
            )
        # Optional
        content["import_uri"] = element.get("importUri")
        content["size"] = _int_helper("size")
        content["duration"] = element.get("duration")
        content["bitrate"] = _int_helper("bitrate")
        content["sample_frequency"] = _int_helper("sampleFrequency")
        content["bits_per_sample"] = _int_helper("bitsPerSample")
        content["nr_audio_channels"] = _int_helper("nrAudioChannels")
        content["resolution"] = element.get("resolution")
        content["color_depth"] = _int_helper("colorDepth")
        content["protection"] = element.get("protection")
        content["uri"] = element.text
        return cls(**content)

    def __repr__(self):
        return "<{} '{}' at {}>".format(
            self.__class__.__name__, self.uri, hex(id(self))
        )

    def __str__(self):
        return self.__repr__()

    def to_element(self):
        """Return an ElementTree Element based on this resource.

        Returns:
            ~xml.etree.ElementTree.Element: an Element.
        """
        if not self.protocol_info:
            raise DIDLMetadataError(
                "Could not create Element for this"
                "resource:"
                "protocolInfo not set (required)."
            )
        root = XML.Element("res")

        # Required
        root.attrib["protocolInfo"] = self.protocol_info
        # Optional
        if self.import_uri is not None:
            root.attrib["importUri"] = self.import_uri
        if self.size is not None:
            root.attrib["size"] = str(self.size)
        if self.duration is not None:
            root.attrib["duration"] = self.duration
        if self.bitrate is not None:
            root.attrib["bitrate"] = str(self.bitrate)
        if self.sample_frequency is not None:
            root.attrib["sampleFrequency"] = str(self.sample_frequency)
        if self.bits_per_sample is not None:
            root.attrib["bitsPerSample"] = str(self.bits_per_sample)
        if self.nr_audio_channels is not None:
            root.attrib["nrAudioChannels"] = str(self.nr_audio_channels)
        if self.resolution is not None:
            root.attrib["resolution"] = self.resolution
        if self.color_depth is not None:
            root.attrib["colorDepth"] = str(self.color_depth)
        if self.protection is not None:
            root.attrib["protection"] = self.protection

        root.text = self.uri
        return root

    def to_dict(self, remove_nones=False):
        """Return a dict representation of the `DidlResource`.

        Args:
            remove_nones (bool, optional): Optionally remove dictionary
                elements when their value is `None`.

        Returns:
            dict: a dict representing the `DidlResource`
        """
        content = {
            "uri": self.uri,
            "protocol_info": self.protocol_info,
            "import_uri": self.import_uri,
            "size": self.size,
            "duration": self.duration,
            "bitrate": self.bitrate,
            "sample_frequency": self.sample_frequency,
            "bits_per_sample": self.bits_per_sample,
            "nr_audio_channels": self.nr_audio_channels,
            "resolution": self.resolution,
            "color_depth": self.color_depth,
            "protection": self.protection,
        }
        if remove_nones:
            # delete any elements that have a value of None to optimize size
            # of the returned structure
            nones = [k for k in content if content[k] is None]
            for k in nones:
                del content[k]
        return content

    @classmethod
    def from_dict(cls, content):
        """Create an instance from a dict.

        An alternative constructor. Equivalent to ``DidlResource(**content)``.

        Args:
            content (dict): a dict containing metadata information. Required.
                Valid keys are the same as the parameters for
                `DidlResource`.
        """
        return cls(**content)

    def __eq__(self, resource):
        """Compare with another ``DidlResource``.

        Returns:
            (bool): `True` if all items are equal, else `False`.
        """
        if not isinstance(resource, DidlResource):
            return False
        return self.to_dict() == resource.to_dict()


###############################################################################
# BASE OBJECTS                                                                #
###############################################################################

# a mapping which will be used to look up the relevant class from the
# DIDL item class
_DIDL_CLASS_TO_CLASS = {}


class DidlMetaClass(type):

    """Meta class for all Didl objects."""

    def __new__(cls, name, bases, attrs):
        """Create a new instance.

        Args:
            name (str): Name of the class.
            bases (tuple): Base classes.
            attrs (dict): attributes defined for the class.
        """
        new_cls = super().__new__(cls, name, bases, attrs)
        # Register all subclasses with the global _DIDL_CLASS_TO_CLASS mapping
        item_class = attrs.get("item_class", None)
        if item_class is not None:
            _DIDL_CLASS_TO_CLASS[item_class] = new_cls
        return new_cls


class DidlObject(metaclass=DidlMetaClass):
    """Abstract base class for all DIDL-Lite items.

    You should not need to instantiate this. Its XML representation looks
    like this:

    ..  code-block:: xml

        <DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"
         xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">
          <item id="...self.item_id..." parentID="...cls.parent_id..."
            restricted="true">
            <dc:title>...self.title...</dc:title>
            <upnp:class>...self.item_class...</upnp:class>
            <desc id="cdudn"
              nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">
              RINCON_AssociatedZPUDN
            </desc>
          </item>
        </DIDL-Lite>
    """

    # the DIDL Lite class for this object.
    item_class = "object"
    tag = "item"
    # key: attribute_name: (ns, tag)
    _translation = {
        "creator": ("dc", "creator"),
        "write_status": ("upnp", "writeStatus"),
    }

    def __init__(
        self,
        title,
        parent_id,
        item_id,
        restricted=True,
        resources=None,
        desc="RINCON_AssociatedZPUDN",
        **kwargs
    ):
        """
        Args:
            title (str): the title for the item.
            parent_id (str): the parent ID for the item.
            item_id (str): the ID for the item.
            restricted (bool): whether the item can be modified. Default `True`
            resources (list, optional): a list of resources for this object.
            Default `None`.
            desc (str): A DIDL descriptor, default
                ``'RINCON_AssociatedZPUDN'``. This is not the same as
                "description". It is used for identifying the relevant
                third party music service.
            **kwargs: Extra metadata. What is allowed depends on the
                ``_translation`` class attribute, which in turn depends on the
                DIDL class.



        ..  autoattribute:: item_class

            str - the DIDL Lite class for this object.

        ..  autoattribute:: tag

            str - the XML element tag name used for this instance.

        ..  autoattribute:: _translation

            dict - A dict used to translate between instance attribute
            names and XML tags/namespaces. It also serves to define the
            allowed tags/attributes for this instance. Each key an attribute
            name and each key is a ``(namespace, tag)`` tuple.

        """
        # All didl objects *must* have a title, a parent_id and an item_id
        # so we specify these as required args in the constructor signature
        # to ensure that we get them. Other didl object properties are
        # optional, so can be passed as kwargs.
        # The content of _translation is adapted from the list in table C at
        # http://upnp.org/specs/av/UPnP-av-ContentDirectory-v2-Service.pdf
        # Not all properties referred to there are catered for, since Sonos
        # does not use some of them.

        # pylint: disable=super-on-old-class
        super().__init__()
        self.title = title
        self.parent_id = parent_id
        self.item_id = item_id
        # Restricted is a compulsory attribute, but is almost always True for
        # Sonos. (Only seen it 'false' when browsing favorites)
        self.restricted = restricted

        # Resources is multi-valued, and dealt with separately
        self.resources = [] if resources is None else resources

        # According to the spec, there may be one or more desc values. Sonos
        # only seems to use one, so we won't bother with a list
        self.desc = desc

        for key, value in kwargs.items():
            # For each attribute, check to see if this class allows it
            if key not in self._translation:
                raise ValueError(
                    "The key '{}' is not allowed as an argument. Only "
                    "these keys are allowed: parent_id, item_id, title, "
                    "restricted, resources, desc"
                    " {}".format(key, ", ".join(self._translation.keys()))
                )
            # It is an allowed attribute. Set it as an attribute on self, so
            # that it can be accessed as Classname.attribute in the normal
            # way.
            setattr(self, key, value)

    # pylint: disable=too-many-locals, too-many-branches
    @classmethod
    def from_element(cls, element):  # pylint: disable=R0914
        """Create an instance of this class from an ElementTree xml Element.

        An alternative constructor. The element must be a DIDL-Lite <item> or
        <container> element, and must be properly namespaced.

        Args:
            xml (~xml.etree.ElementTree.Element): An
                :class:`~xml.etree.ElementTree.Element` object.
        """
        # We used to check here that we have the right sort of element,
        # ie a container or an item. But Sonos seems to use both
        # indiscriminately, eg a playlistContainer can be an item or a
        # container. So we now just check that it is one or the other.
        tag = element.tag
        if not (tag.endswith("item") or tag.endswith("container")):
            raise DIDLMetadataError(
                "Wrong element. Expected <item> or <container>,"
                " got <{}> for class {}'".format(tag, cls.item_class)
            )
        # and that the upnp matches what we are expecting
        item_class = element.find(ns_tag("upnp", "class")).text

        # In case this class has an # specified unofficial
        # subclass, ignore it by stripping it from item_class
        for separator in (".#", "#"):
            if separator in item_class:
                item_class = item_class[: item_class.find(separator)]

        if item_class != cls.item_class:
            raise DIDLMetadataError(
                "UPnP class is incorrect. Expected '{}',"
                " got '{}'".format(cls.item_class, item_class)
            )

        # parent_id, item_id  and restricted are stored as attributes on the
        # element
        item_id = element.get("id", None)
        if item_id is None:
            raise DIDLMetadataError("Missing id attribute")
        item_id = really_unicode(item_id)
        parent_id = element.get("parentID", None)
        if parent_id is None:
            raise DIDLMetadataError("Missing parentID attribute")
        parent_id = really_unicode(parent_id)

        # CAUTION: This implementation deviates from the spec.
        # Elements are normally required to have a `restricted` tag, but
        # Spotify Direct violates this. To make it work, a missing restricted
        # tag is interpreted as `restricted = True`.
        restricted = element.get("restricted", None)
        restricted = restricted not in [0, "false", "False"]

        # Similarily, all elements should have a title tag, but Spotify Direct
        # does not comply
        title_elt = element.find(ns_tag("dc", "title"))
        if title_elt is None or not title_elt.text:
            title = ""
        else:
            title = really_unicode(title_elt.text)

        # Deal with any resource elements
        resources = []
        for res_elt in element.findall(ns_tag("", "res")):
            # Not all Favorits have resources, so in case the "res"
            # tage has no attributes, just skip it
            if cls is DidlFavorite and not res_elt.attrib:
                continue
            resources.append(DidlResource.from_element(res_elt))

        # and the desc element (There is only one in Sonos)
        desc = element.findtext(ns_tag("", "desc"))

        # Get values of the elements listed in _translation and add them to
        # the content dict
        content = {}
        for key, value in cls._translation.items():
            result = element.findtext(ns_tag(*value))
            if result is not None:
                # We store info as unicode internally.
                content[key] = really_unicode(result)

        # Convert type for original track number
        if content.get("original_track_number") is not None:
            content["original_track_number"] = int(content["original_track_number"])

        # Now pass the content dict we have just built to the main
        # constructor, as kwargs, to create the object
        return cls(
            title=title,
            parent_id=parent_id,
            item_id=item_id,
            restricted=restricted,
            resources=resources,
            desc=desc,
            **content
        )

    @classmethod
    def from_dict(cls, content):
        """Create an instance from a dict.

        An alternative constructor. Equivalent to ``DidlObject(**content)``.

        Args:
            content (dict): a dict containing metadata information. Required.
                Valid keys are the same as the parameters for `DidlObject`.

        """
        # Do we really need this constructor? Could use DidlObject(**content)
        # instead.  -- We do now
        if "resources" in content:
            content["resources"] = [
                DidlResource.from_dict(x) for x in content["resources"]
            ]
        return cls(**content)

    def __eq__(self, playable_item):
        """Compare with another ``playable_item``.

        Returns:
            (bool): `True` if all items are equal, else `False`.
        """
        if not isinstance(playable_item, DidlObject):
            return False
        return self.to_dict() == playable_item.to_dict()

    def __ne__(self, playable_item):
        """Compare with another ``playable_item``.

        Returns:
            (bool): `True` if any items is unequal, else `False`.
        """
        if not isinstance(playable_item, DidlObject):
            return True
        return self.to_dict() != playable_item.to_dict()

    def __repr__(self):
        """Get the repr value for the item.

        Returns:
            str: A string representation of the instance in the form
            ``<class_name 'middle_part[0:40]' at id_in_hex>`` where
            middle_part is either the title item in content, if it is set, or
            ``str(content)``. The output is also cleared of non-ascii
            characters.
        """
        # 40 originates from terminal width (78) - (15) for address part and
        # (19) for the longest class name and a little left for buffer
        if self.title is not None:
            middle = self.title.encode("ascii", "replace")[0:40]
        else:
            middle = str(self.to_dict).encode("ascii", "replace")[0:40]
        return "<{} '{}' at {}>".format(self.__class__.__name__, middle, hex(id(self)))

    def __str__(self):
        """Get the str value for the item.

        Returns:
            str: a string representation in the form
            ``<class_name 'middle_part[0:40]' at id_in_hex>`` where
            middle_part is either the title item in content, if it is set, or
            ``str(content)``. The output is also cleared of non-ascii
            characters.
        """
        return self.__repr__()

    def to_dict(self, remove_nones=False):
        """Return the dict representation of the instance.

        Args:
             remove_nones (bool, optional): Optionally remove dictionary
                 elements when their value is `None`.

         Returns:
             dict: a dict representation of the `DidlObject`.
        """
        content = {}
        # Get the value of each attribute listed in _translation, and add it
        # to the content dict
        for key in self._translation:
            if hasattr(self, key):
                content[key] = getattr(self, key)
        # also add parent_id, item_id, restricted, title and resources because
        # they are not listed in _translation
        content["parent_id"] = self.parent_id
        content["item_id"] = self.item_id
        content["restricted"] = self.restricted
        content["title"] = self.title
        if self.resources != []:
            content["resources"] = [
                resource.to_dict(remove_nones=remove_nones)
                for resource in self.resources
            ]
        content["desc"] = self.desc
        return content

    def to_element(self, include_namespaces=False):
        """Return an ElementTree Element representing this instance.

        Args:
            include_namespaces (bool, optional): If True, include xml
                namespace attributes on the root element

        Return:
            ~xml.etree.ElementTree.Element: an Element.
        """
        elt_attrib = {}
        if include_namespaces:
            elt_attrib.update(
                {
                    "xmlns": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
                    "xmlns:dc": "http://purl.org/dc/elements/1.1/",
                    "xmlns:upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/",
                }
            )
        elt_attrib.update(
            {
                "parentID": self.parent_id,
                "restricted": "true" if self.restricted else "false",
                "id": self.item_id,
            }
        )
        elt = XML.Element(self.tag, elt_attrib)

        # Add the title, which should always come first, according to the spec
        XML.SubElement(elt, "dc:title").text = self.title

        # Add in any resources
        for resource in self.resources:
            elt.append(resource.to_element())

        # Add the rest of the metadata attributes (i.e all those listed in
        # _translation) as sub-elements of the item element.
        for key, value in self._translation.items():
            if hasattr(self, key):
                # Some attributes have a namespace of '', which means they
                # are in the default namespace. We need to handle those
                # carefully
                tag = "%s:%s" % value if value[0] else "%s" % value[1]
                XML.SubElement(elt, tag).text = "%s" % getattr(self, key)
        # Now add in the item class
        XML.SubElement(elt, "upnp:class").text = self.item_class

        # And the desc element
        desc_attrib = {
            "id": "cdudn",
            "nameSpace": "urn:schemas-rinconnetworks-com:metadata-1-0/",
        }
        desc_elt = XML.SubElement(elt, "desc", desc_attrib)
        desc_elt.text = self.desc

        return elt

    def get_uri(self, resource_nr=0):
        """Return the uri to use for playing this item.

        Args:
            resource_nr (int): The index of the resource. Note that there is no
                known object with more than one resource, so you can probably
                keep the default value (0).
        Returns:
            str: The uri.
        """
        return self.resources[resource_nr].uri

    def set_uri(self, uri, resource_nr=0, protocol_info=None):
        """Set a resource uri for this instance. If no resource exists, create
        a new one with the given protocol info.

        Args:
            uri (str): The resource uri.
            resource_nr (int): The index of the resource on which to set the
                uri. If it does not exist, a new resource is added to the list.
                Note that by default, only the uri of the first resource is
                used for playing the item.
            protocol_info (str): Protocol info for the resource. If none is
                given and the resource does not exist yet, a default protocol
                info is constructed as ``'[uri prefix]:*:*:*'``.
        """
        try:
            self.resources[resource_nr].uri = uri
            if protocol_info is not None:
                self.resources[resource_nr].protocol_info = protocol_info
        except IndexError:
            if protocol_info is None:
                # create default protcol info
                protocol_info = uri[: uri.index(":")] + ":*:*:*"
            self.resources.append(DidlResource(uri, protocol_info))


###############################################################################
# OBJECT.ITEM HIERARCHY                                                       #
###############################################################################


class DidlItem(DidlObject):

    """A basic content directory item."""

    # The spec allows for an option 'refID' attribute, but we do not handle it

    # the DIDL Lite class for this object.
    item_class = "object.item"
    # _translation = DidlObject._translation.update({ ...})
    # does not work, but doing it in two steps does
    _translation = DidlObject._translation.copy()
    _translation.update(
        {
            "stream_content": ("r", "streamContent"),
            "radio_show": ("r", "radioShowMd"),
            "album_art_uri": ("upnp", "albumArtURI"),
        }
    )


class DidlAudioItem(DidlItem):

    """An audio item."""

    # the DIDL Lite class for this object.
    item_class = "object.item.audioItem"
    _translation = DidlItem._translation.copy()
    _translation.update(
        {
            "genre": ("upnp", "genre"),
            "description": ("dc", "description"),
            "long_description": ("upnp", "longDescription"),
            "publisher": ("dc", "publisher"),
            "language": ("dc", "language"),
            "relation": ("dc", "relation"),
            "rights": ("dc", "rights"),
        }
    )


class DidlMusicTrack(DidlAudioItem):

    """Class that represents a music library track."""

    # the DIDL Lite class for this object.
    item_class = "object.item.audioItem.musicTrack"
    # name: (ns, tag)
    _translation = DidlAudioItem._translation.copy()
    _translation.update(
        {
            "artist": ("upnp", "artist"),
            "album": ("upnp", "album"),
            "original_track_number": ("upnp", "originalTrackNumber"),
            "playlist": ("upnp", "playlist"),
            "contributor": ("dc", "contributor"),
            "date": ("dc", "date"),
        }
    )


class DidlAudioBook(DidlAudioItem):

    """Class that represents an audio book."""

    # the DIDL Lite class for this object.
    item_class = "object.item.audioItem.audioBook"
    # name: (ns, tag)
    _translation = DidlAudioItem._translation.copy()
    _translation.update(
        {
            "storageMedium": ("upnp", "storageMedium"),
            "producer": ("upnp", "producer"),
            "contributor": ("dc", "contributor"),
            "date": ("dc", "date"),
        }
    )


class DidlAudioBroadcast(DidlAudioItem):

    """Class that represents an audio broadcast."""

    # the DIDL Lite class for this object.
    item_class = "object.item.audioItem.audioBroadcast"
    _translation = DidlAudioItem._translation.copy()
    _translation.update(
        {
            "region": ("upnp", "region"),
            "radio_call_sign": ("upnp", "radioCallSign"),
            "radio_station_id": ("upnp", "radioStationID"),
            "channel_nr": ("upnp", "channelNr"),
        }
    )


class DidlRecentShow(DidlMusicTrack):

    """Class that represents a recent radio show/podcast."""

    # the DIDL Lite class for this object.
    item_class = "object.item.audioItem.musicTrack.recentShow"


class DidlAudioBroadcastFavorite(DidlAudioBroadcast):

    """Class that represents an audio broadcast Sonos favorite."""

    # Note: The sonos-favorite part of the class spec obviously isn't part of
    # the DIDL spec, so just assume that it has the same definition as the
    # regular object.item.audioItem.audioBroadcast

    # the DIDL Lite class for this object.
    item_class = "object.item.audioItem.audioBroadcast.sonos-favorite"


class DidlFavorite(DidlItem):

    """Class that represents a Sonos favorite.

    Note that the favorite itself isn't playable in all cases, please use the
    object returned by :attr:`favorite.reference` instead."""

    # the DIDL Lite class for this object.
    item_class = "object.itemobject.item.sonos-favorite"
    _translation = DidlItem._translation.copy()
    _translation.update(
        {
            "type": ("r", "type"),
            "description": ("r", "description"),
            "favorite_nr": ("r", "ordinal"),
            "resource_meta_data": ("r", "resMD"),
        }
    )

    # The resMD tag contains the metadata of the Didl object referenced by this
    # favorite. For user convenience, we will parse this metadata and make the
    # object available via the 'reference' property.
    @property
    def reference(self):
        """The Didl object this favorite refers to."""

        # Import from_didl_string if it isn't present already. The import
        # happens here because it would cause cyclic import errors if the
        # import happened at load time.
        global _FROM_DIDL_STRING_FUNCTION  # pylint: disable=global-statement
        if not _FROM_DIDL_STRING_FUNCTION:
            from . import data_structures_entry

            _FROM_DIDL_STRING_FUNCTION = data_structures_entry.from_didl_string

        ref = _FROM_DIDL_STRING_FUNCTION(getattr(self, "resource_meta_data"))[0]
        # The resMD metadata lacks a <res> tag, so we use the resources from
        # the favorite to make 'reference' playable.
        ref.resources = self.resources
        return ref

    @reference.setter
    def reference(self, value):
        setattr(self, "resource_meta_data", to_didl_string(value))
        self.resources = value.resources


###############################################################################
# OBJECT.CONTAINER HIERARCHY                                                  #
###############################################################################


class DidlContainer(DidlObject):

    """Class that represents a music library container."""

    # the DIDL Lite class for this object.
    item_class = "object.container"
    tag = "container"
    # We do not implement createClass or searchClass. Not used by Sonos??
    # TODO: handle the 'childCount' element.


class DidlAlbum(DidlContainer):

    """A content directory album."""

    # the DIDL Lite class for this object.
    item_class = "object.container.album"
    # name: (ns, tag)
    _translation = DidlContainer._translation.copy()
    _translation.update(
        {
            "description": ("dc", "description"),
            "long_description": ("upnp", "longDescription"),
            "publisher": ("dc", "publisher"),
            "contributor": ("dc", "contributor"),
            "date": ("dc", "date"),
            "relation": ("dc", "relation"),
            "rights": ("dc", "rights"),
        }
    )


class DidlMusicAlbum(DidlAlbum):

    """Class that represents a music library album."""

    # the DIDL Lite class for this object.
    item_class = "object.container.album.musicAlbum"
    # According to the spec, all musicAlbums should be represented in
    # XML by a <container> tag. Sonos sometimes uses <container> and
    # sometimes uses <item>. <container> seems to work here for the moment.
    tag = "container"
    # name: (ns, tag)
    # pylint: disable=protected-access
    #:
    _translation = DidlAlbum._translation.copy()
    _translation.update(
        {
            "artist": ("upnp", "artist"),
            "genre": ("upnp", "genre"),
            "producer": ("upnp", "producer"),
            "toc": ("upnp", "toc"),
            "album_art_uri": ("upnp", "albumArtURI"),
        }
    )


class DidlMusicAlbumFavorite(DidlMusicAlbum):

    """Class that represents a Sonos favorite music library album.

    This class is not part of the DIDL spec and is Sonos specific.
    """

    # the DIDL Lite class for this object.
    item_class = "object.container.album.musicAlbum.sonos-favorite"
    # Despite the fact that the item derives from object.container, it's
    # XML does not include a <container> tag, but an <item> tag. This seems
    # to be an error by Sonos.
    tag = "item"


class DidlMusicAlbumCompilation(DidlMusicAlbum):

    """Class that represents a Sonos favorite music library compilation.

    This class is not part of the DIDL spec and is Sonos specific.
    """

    # These classes appear when browsing the library and Sonos has been set
    # to group albums using compilations.
    # See https://github.com/SoCo/SoCo/issues/280
    # the DIDL Lite class for this object.
    item_class = "object.container.album.musicAlbum.compilation"
    tag = "container"


class DidlPerson(DidlContainer):

    """A content directory class representing a person."""

    # the DIDL Lite class for this object.
    item_class = "object.container.person"
    tag = "item"
    #: dfdf
    _translation = DidlContainer._translation.copy()
    _translation.update(
        {
            "language": ("dc", "language"),
        }
    )


class DidlComposer(DidlPerson):

    """Class that represents a music library composer."""

    # Not in the DIDL-Lite spec. Sonos specific??

    # the DIDL Lite class for this object.
    item_class = "object.container.person.composer"


class DidlMusicArtist(DidlPerson):

    """Class that represents a music library artist."""

    # the DIDL Lite class for this object.
    item_class = "object.container.person.musicArtist"
    # name: (ns, tag)
    _translation = DidlPerson._translation.copy()
    _translation.update(
        {
            "genre": ("upnp", "genre"),
            "artist_discography_uri": ("upnp", "artistDiscographyURI"),
        }
    )


class DidlAlbumList(DidlContainer):

    """Class that represents a music library album list."""

    # This does not appear (that I can find) in the DIDL-Lite specs.
    # Presumably Sonos specific
    # the DIDL Lite class for this object.
    item_class = "object.container.albumlist"


class DidlPlaylistContainer(DidlContainer):

    """Class that represents a music library play list."""

    # (str) The DIDL Lite class for this object
    item_class = "object.container.playlistContainer"
    # Yes, really. Sonos uses the item tag, not the container tag. But
    # sometimes it uses the container tag, eg:
    # >>> s=soco.SoCo('192.168.1.102')
    # >>> s.get_playlists()
    # See https://github.com/SoCo/SoCo/issues/353
    tag = "item"
    # name: (ns, tag)
    _translation = DidlContainer._translation.copy()
    _translation.update(
        {
            "artist": ("upnp", "artist"),
            "genre": ("upnp", "genre"),
            "long_description": ("upnp", "longDescription"),
            "producer": ("dc", "producer"),
            "contributor": ("dc", "contributor"),
            "description": ("dc", "description"),
            "date": ("dc", "date"),
            "language": ("dc", "language"),
            "rights": ("dc", "rights"),
        }
    )


class DidlSameArtist(DidlPlaylistContainer):

    """Class that represents all tracks by a single artist.

    This type is returned by browsing an artist or a composer
    """

    # Not in the DIDL-Lite spec. Sonos specific?
    # the DIDL Lite class for this object.
    item_class = "object.container.playlistContainer.sameArtist"


class DidlPlaylistContainerFavorite(DidlPlaylistContainer):

    """Class that represents a Sonos favorite play list."""

    item_class = "object.container.playlistContainer.sonos-favorite"


class DidlPlaylistContainerTracklist(DidlPlaylistContainer):

    """Class that represents a Sonos tracklist."""

    item_class = "object.container.playlistContainer.tracklist"


class DidlGenre(DidlContainer):

    """A content directory class representing a general genre."""

    # the DIDL Lite class for this object.
    item_class = "object.container.genre"
    # name: (ns, tag)

    #:
    _translation = DidlContainer._translation.copy()
    _translation.update(
        {
            "genre": ("upnp", "genre"),
            "long_description": ("upnp", "longDescription"),
            "description": ("dc", "description"),
        }
    )


class DidlMusicGenre(DidlGenre):

    """Class that represents a music genre."""

    # the DIDL Lite class for this object.
    item_class = "object.container.genre.musicGenre"
    tag = "item"


class DidlRadioShow(DidlContainer):
    """Class that represents a radio show."""

    # the DIDL Lite class for this object.
    item_class = "object.container.radioShow"
    # A radio show doesn't seem to have any special attributes


###############################################################################
# SPECIAL LISTS                                                               #
###############################################################################


class ListOfMusicInfoItems(list):

    """Abstract container class for a list of music information items.

    Instances of this class are returned from queries into the music library
    or to music services. The attributes :attr:`~total_matches` and
    :attr:`~number_returned` are used to ascertain whether paging is required
    in order to retrive all elements of the query. :attr:`~total_matches` is
    the total number of results to the query and :attr:`~number_returned` is
    the number of results actually returned. If the two differ, paging is
    required. Paging is typically performed with the ``start`` and
    ``max_items`` arguments to the query method. See e.g. the
    :meth:`~soco.music_library.MusicLibrary.get_music_library_information`
    method for details.
    """

    def __init__(self, items, number_returned, total_matches, update_id):
        super().__init__(items)
        self._metadata = {
            "item_list": list(items),
            "number_returned": number_returned,
            "total_matches": total_matches,
            "update_id": update_id,
        }

    def __getitem__(self, key):
        """Legacy get metadata by string key or list item(s) by index.

        .. deprecated:: 0.8

            This overriding form of __getitem__ will be removed in the 3rd
            release after 0.8. The metadata can be fetched via the named
            attributes.
        """
        if key in self._metadata:
            if key == "item_list":
                message = """
                Calling [\'item_list\'] on search results to obtain the objects
                is no longer necessary, since the object returned from searches
                now is a list. This deprecated way of getting the items will
                be removed from the third release after 0.8."""
            else:
                message = """
                Getting metadata items by indexing the search result like a
                dictionary [\'{0}\'] is deprecated. Please use the named
                attribute {1}.{0} instead. The deprecated way of retrieving the
                metadata will be removed from the third release after
                0.8""".format(
                    key, self.__class__.__name__
                )
            message = textwrap.dedent(message).replace("\n", " ").lstrip()
            warnings.warn(message, stacklevel=2)
            return self._metadata[key]
        else:
            return super().__getitem__(key)

    @property
    def number_returned(self):
        """str: the number of returned matches."""
        return self._metadata["number_returned"]

    @property
    def total_matches(self):
        """str: the number of total matches."""
        return self._metadata["total_matches"]

    @property
    def update_id(self):
        """str: the update ID."""
        return self._metadata["update_id"]


class SearchResult(ListOfMusicInfoItems):

    """Container class that represents a search or browse result.

    Browse is just a special case of search.
    """

    def __init__(self, items, search_type, number_returned, total_matches, update_id):
        super().__init__(items, number_returned, total_matches, update_id)
        self._metadata["search_type"] = search_type

    def __repr__(self):
        return "{}(items={}, search_type='{}')".format(
            self.__class__.__name__,
            super().__repr__(),
            self.search_type,
        )

    @property
    def search_type(self):
        """str: the search type."""
        return self._metadata["search_type"]


class Queue(ListOfMusicInfoItems):

    """Container class that represents a queue."""

    def __repr__(self):
        return "{}(items={})".format(
            self.__class__.__name__,
            super().__repr__(),
        )
