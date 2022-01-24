"""This module is for parsing and conversion functions that needs
objects from both music library and music service data structures

"""

from functools import lru_cache
import logging

from .data_structures import didl_class_to_soco_class
from .exceptions import DIDLMetadataError
from .xml import XML, ns_tag

_LOG = logging.getLogger(__name__)
_LOG.addHandler(logging.NullHandler())
_LOG.debug("%s imported", __name__)


@lru_cache()
def from_didl_string(string):
    """Convert a unicode xml string to a list of `DIDLObjects <DidlObject>`.

    Args:
        string (str): A unicode string containing an XML representation of one
            or more DIDL-Lite items (in the form  ``'<DIDL-Lite ...>
            ...</DIDL-Lite>'``)

    Returns:
        list: A list of one or more instances of `DidlObject` or a subclass
    """
    items = []
    root = XML.fromstring(string.encode("utf-8"))
    for elt in root:
        if elt.tag.endswith("item") or elt.tag.endswith("container"):
            item_class = elt.findtext(ns_tag("upnp", "class"))
            cls = didl_class_to_soco_class(item_class)
            item = cls.from_element(elt)
            items.append(item)
        else:
            # <desc> elements are allowed as an immediate child of <DIDL-Lite>
            # according to the spec, but I have not seen one there in Sonos, so
            # we treat them as illegal. May need to fix this if this
            # causes problems.
            raise DIDLMetadataError("Illegal child of DIDL element: <%s>" % elt.tag)
    _LOG.debug(
        'Created data structures: %.20s (CUT) from Didl string "%.20s" (CUT)',
        items,
        string,
    )
    return items
