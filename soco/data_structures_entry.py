
"""This module is for parsing and conversion functions that needs
objects from both music library and music service data structures

"""

from __future__ import absolute_import

from .xml import (
    XML, ns_tag
)
from .data_structures import _DIDL_CLASS_TO_CLASS
from .exceptions import DIDLMetadataError
from .compat import urlparse
from .music_services.data_structures import get_class
from .music_services.music_service import desc_from_uri


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
    root = XML.fromstring(string.encode('utf-8'))
    for elt in root:
        if elt.tag.endswith('item') or elt.tag.endswith('container'):
            item_class = elt.findtext(ns_tag('upnp', 'class'))

            # In case this class has an # specified unofficial
            # subclass, ignore it by stripping it from item_class
            if '.#' in item_class:
                item_class = item_class[:item_class.find('.#')]

            try:
                cls = _DIDL_CLASS_TO_CLASS[item_class]
            except KeyError:
                raise DIDLMetadataError("Unknown UPnP class: %s" % item_class)
            item = cls.from_element(elt)
            item = attempt_datastructure_upgrade(item)
            items.append(item)
        else:
            # <desc> elements are allowed as an immediate child of <DIDL-Lite>
            # according to the spec, but I have not seen one there in Sonos, so
            # we treat them as illegal. May need to fix this if this
            # causes problems.
            raise DIDLMetadataError("Illegal child of DIDL element: <%s>"
                                    % elt.tag)
    return items


# FIXME, Obviously imcomplete
DIDL_NAME_TO_QUALIFIED_MS_NAME = {
    'DidlMusicTrack': 'MediaMetadataTrack'
}


def attempt_datastructure_upgrade(didl_item):
    """Attempt to upgrade a didl_item to a music services data structure
    if it originates from a music services

    """
    try:
        resource = didl_item.resources[0]
    except IndexError:
        return didl_item

    # FIXME are we guarantied that there are resources and that they
    # have a uri????
    if resource.uri.startswith('x-sonos-http'):
        # Get data
        uri = resource.uri
        # Now we need to create a DIDL item id. It seems to be based on the uri
        path = urlparse(uri).path
        # Strip any extensions, eg .mp3, from the end of the path
        path = path.rsplit('.', 1)[0]
        # The ID has an 8 (hex) digit prefix. But it doesn't seem to
        # matter what it is!
        item_id = '11111111{0}'.format(path)

        # FIXME Ignore other metadata for now, in future ask ms data
        # structure to upgrade metadata from the service
        metadata = {}
        try:
            metadata['title'] = didl_item.title
        except AttributeError:
            pass

        # Get class and instantiate
        cls = get_class(DIDL_NAME_TO_QUALIFIED_MS_NAME[
            didl_item.__class__.__name__
        ])
        return cls(
            item_id=item_id,
            desc=desc_from_uri(resource.uri),
            resources=didl_item.resources,
            uri=uri,
            metadata_dict=metadata,
        )
    return didl_item
