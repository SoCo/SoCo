"""This module implements 'quirks' for the DIDL-Lite data structures

A quirk, in this context, means that a specific music service does not follow
a specific part of the DIDL-Lite specification. In order not to clutter the
primary implementation of DIDL-Lite for SoCo (in :mod:`soco.data_structures`)
up with all these service specific exception, they are implemented separately
in this module. Besides from keeping the main implementation clean and
following the specification, this has the added advantage of making it easier
to track how many quiks are out there.

The implementation of the quirks at this point is just a single function which
applies quirks to the DIDL-Lite resources, with the options of adding one that
applies them to DIDL-Lite objects.

"""

import logging


_LOG = logging.getLogger(__name__)


def apply_resource_quirks(resource):
    """Apply DIDL-Lite resource quirks"""
    # At least two music service (Spotify Direct and Amazon in conjunction
    # with Alexa) has been known not to supply the mandatory protocolInfo, so
    # if it is missing supply a dummy one
    if "protocolInfo" not in resource.attrib:
        protocol_info = "DUMMY_ADDED_BY_QUIRK"
        # For Spotify direct we have a better idea what it should be, since it
        # is included in the main element text
        if resource.text and resource.text.startswith("x-sonos-spotify"):
            protocol_info = "sonos.com-spotify:*:audio/x-spotify.*"

        _LOG.debug(
            "Resource quirk applied for missing protocolInfo, setting to '%s'",
            protocol_info,
        )
        resource.set("protocolInfo", protocol_info)

        if not resource.text:
            resource.text = ""
    return resource
