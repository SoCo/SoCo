# pylint: disable=invalid-name,wrong-import-position,redefined-builtin

"""This class contains XML related utility functions."""


import sys
import re

import xml.etree.ElementTree as XML


# Create regular expression for filtering invalid characters, from:
# http://stackoverflow.com/questions/1707890/
# fast-way-to-filter-illegal-xml-unicode-chars-in-python

illegal_unichrs = [
    (0x00, 0x08),
    (0x0B, 0x0C),
    (0x0E, 0x1F),
    (0x7F, 0x84),
    (0x86, 0x9F),
    (0xD800, 0xDFFF),
    (0xFDD0, 0xFDDF),
    (0xFFFE, 0xFFFF),
    (0x1FFFE, 0x1FFFF),
    (0x2FFFE, 0x2FFFF),
    (0x3FFFE, 0x3FFFF),
    (0x4FFFE, 0x4FFFF),
    (0x5FFFE, 0x5FFFF),
    (0x6FFFE, 0x6FFFF),
    (0x7FFFE, 0x7FFFF),
    (0x8FFFE, 0x8FFFF),
    (0x9FFFE, 0x9FFFF),
    (0xAFFFE, 0xAFFFF),
    (0xBFFFE, 0xBFFFF),
    (0xCFFFE, 0xCFFFF),
    (0xDFFFE, 0xDFFFF),
    (0xEFFFE, 0xEFFFF),
    (0xFFFFE, 0xFFFFF),
    (0x10FFFE, 0x10FFFF),
]

illegal_ranges = [
    "{}-{}".format(chr(low), chr(high))
    for (low, high) in illegal_unichrs
    if low < sys.maxunicode
]

illegal_xml_re = re.compile("[%s]" % "".join(illegal_ranges))


#: Commonly used namespaces, and abbreviations, used by `ns_tag`.
NAMESPACES = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/",
    "": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
    "ms": "http://www.sonos.com/Services/1.1",
    "r": "urn:schemas-rinconnetworks-com:metadata-1-0/",
}

# Register common namespaces to assist in serialisation (avoids the ns:0
# prefixes in XML output )
for prefix, uri in NAMESPACES.items():
    XML.register_namespace(prefix, uri)


def ns_tag(ns_id, tag):
    """Return a namespace/tag item.

    Args:
        ns_id (str): A namespace id, eg ``"dc"`` (see `NAMESPACES`)
        tag (str): An XML tag, eg ``"author"``

    Returns:
        str: A fully qualified tag.

    The ns_id is translated to a full name space via the :const:`NAMESPACES`
    constant::

        >>> xml.ns_tag('dc','author')
        '{http://purl.org/dc/elements/1.1/}author'
    """
    return "{{{}}}{}".format(NAMESPACES[ns_id], tag)
