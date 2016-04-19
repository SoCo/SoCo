# -*- coding: utf-8 -*-
# pylint: disable=invalid-name,wrong-import-position,redefined-builtin

"""This class contains XML related utility functions."""

from __future__ import (
    absolute_import, unicode_literals
)

import sys
import re

try:
    import xml.etree.cElementTree as XML
except ImportError:
    import xml.etree.ElementTree as XML

# This is a Python 2.6 compatbility hack. Pre 2.7 ElementTree raised
# SyntaxError !!! if it encountered invalid chars in the XML, which is what
# this exception is used for. It is only used one place in services. If we ever
# drop support for Python 2.6 this should be removed
try:
    PARSEERROR = XML.ParseError
except AttributeError:
    # .ParseError did not exist pre 2.7;
    # https://github.com/s3tools/s3cmd/issues/424
    PARSEERROR = SyntaxError


# Create regular expression for filtering invalid characters, from:
# http://stackoverflow.com/questions/1707890/
# fast-way-to-filter-illegal-xml-unicode-chars-in-python
if sys.version_info[0] >= 3:
    unichr = chr

illegal_unichrs = [
    (0x00, 0x08), (0x0B, 0x0C), (0x0E, 0x1F), (0x7F, 0x84),
    (0x86, 0x9F), (0xD800, 0xDFFF), (0xFDD0, 0xFDDF),
    (0xFFFE, 0xFFFF),
    (0x1FFFE, 0x1FFFF), (0x2FFFE, 0x2FFFF), (0x3FFFE, 0x3FFFF),
    (0x4FFFE, 0x4FFFF), (0x5FFFE, 0x5FFFF), (0x6FFFE, 0x6FFFF),
    (0x7FFFE, 0x7FFFF), (0x8FFFE, 0x8FFFF), (0x9FFFE, 0x9FFFF),
    (0xAFFFE, 0xAFFFF), (0xBFFFE, 0xBFFFF), (0xCFFFE, 0xCFFFF),
    (0xDFFFE, 0xDFFFF), (0xEFFFE, 0xEFFFF), (0xFFFFE, 0xFFFFF),
    (0x10FFFE, 0x10FFFF)
]

illegal_ranges = ["%s-%s" % (unichr(low), unichr(high))
                  for (low, high) in illegal_unichrs
                  if low < sys.maxunicode]

illegal_xml_re = re.compile(u'[%s]' % u''.join(illegal_ranges))


#: Commonly used namespaces, and abbreviations, used by `ns_tag`.
NAMESPACES = {
    'dc': 'http://purl.org/dc/elements/1.1/',
    'upnp': 'urn:schemas-upnp-org:metadata-1-0/upnp/',
    '': 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/',
    'ms': 'http://www.sonos.com/Services/1.1',
    'r': 'urn:schemas-rinconnetworks-com:metadata-1-0/'
}

# Register common namespaces to assist in serialisation (avoids the ns:0
# prefixes in XML output )
try:
    register_namespace = XML.register_namespace
except AttributeError:
    # Python 2.6: see http://effbot.org/zone/element-namespaces.htm
    import xml.etree.ElementTree as XML2

    def register_namespace(a_prefix, a_uri):
        """Registers a namespace prefix to assist in serialization."""
        # pylint: disable=protected-access
        XML2._namespace_map[a_uri] = a_prefix

for prefix, uri in NAMESPACES.items():
    register_namespace(prefix, uri)


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
    return '{{{0}}}{1}'.format(NAMESPACES[ns_id], tag)
