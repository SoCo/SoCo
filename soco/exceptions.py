# -*- coding: utf-8 -*-

"""Exceptions that are used by SoCo."""

from __future__ import unicode_literals

import collections


class SoCoException(Exception):

    """Base class for all SoCo exceptions."""


class UnknownSoCoException(SoCoException):

    """An unknown UPnP error.

    The exception object will contain the raw response sent back from
    the speaker as the first of its args.
    """


class SoCoUPnPException(SoCoException):

    """A UPnP Fault Code, raised in response to actions sent over the
    network.

    """

    def __init__(self, message, error_code, error_xml, error_description=""):
        """
        Args:
            message (str): The message from the server.
            error_code (str): The UPnP Error Code as a string.
            error_xml (str): The xml containing the error, as a utf-8
                encoded string.
            error_description (str): A description of the error. Default is ""
        """
        super(SoCoUPnPException, self).__init__()
        self.message = message
        self.error_code = error_code
        self.error_description = error_description
        self.error_xml = error_xml

    def __str__(self):
        return self.message


class CannotCreateDIDLMetadata(SoCoException):

    """
    ..  deprecated:: 0.11
        Use `DIDLMetadataError` instead.
    """


class DIDLMetadataError(CannotCreateDIDLMetadata):

    """Raised if a data container class cannot create the DIDL metadata due to
    missing information.

    For backward compatibility, this is currently a subclass of
    `CannotCreateDIDLMetadata`. In a future version, it will likely become
    a direct subclass of `SoCoException`.
    """


class MusicServiceException(SoCoException):

    """An error relating to a third party music service."""


class UnknownXMLStructure(SoCoException):

    """Raised if XML with an unknown or unexpected structure is returned."""


class SoCoSlaveException(SoCoException):
    """Raised when a master command is called on a slave."""


class NotSupportedException(SoCoException):
    """Raised when something is not supported by the device"""


# pylint: disable=too-many-ancestors
class ErrorDict(collections.Mapping, dict):
    """A dict which supports seterror() to raise an exception on object
    retrieval."""

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self._errors = {}

    def seterror(self, key, error):
        """Set an exception to raise when a key is retrieved."""
        if error:
            self._errors[key] = error
        else:
            del self._errors

    def __getitem__(self, key):
        if key in self._errors:
            raise self._errors[key]
        return dict.__getitem__(self, key)

    def __iter__(self):
        return dict.__iter__(self)

    def __len__(self):
        return dict.__len__(self)
