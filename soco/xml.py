
""" Module that contains XML related utility functions """

# pylint: disable=unused-import, invalid-name, no-member

from __future__ import absolute_import

try:
    import xml.etree.cElementTree as XML
except ImportError:
    import xml.etree.ElementTree as XML

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
        " Registers a namespace prefix to assist in serialization"
        # pylint: disable=protected-access
        XML2._namespace_map[a_uri] = a_prefix

for prefix, uri in NAMESPACES.items():
    register_namespace(prefix, uri)


def ns_tag(ns_id, tag):
    """Return a namespace/tag item. The ns_id is translated to a full name
    space via the NAMESPACES variable.

    """
    return '{{{0}}}{1}'.format(NAMESPACES[ns_id], tag)
