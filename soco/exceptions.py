# -*- coding: utf-8 -*-

""" Exceptions that are used by SoCo """


class SoCoException(Exception):

    """ base exception raised by SoCo, containing the UPnP error code """


class UnknownSoCoException(SoCoException):

    """ raised if reason of the error can not be extracted

    The exception object will contain the raw response sent back from the
    speaker """


class SoCoUPnPException(SoCoException):

    """ encapsulates UPnP Fault Codes raised in response to actions sent over
    the network """

    def __init__(self, message, error_code, error_xml, error_description=""):
        super(SoCoUPnPException, self).__init__()
        self.message = message
        self.error_code = error_code
        self.error_description = error_description
        self.error_xml = error_xml

    def __str__(self):
        return self.message


class CannotCreateDIDLMetadata(SoCoException):

    """ Deprecated in v.0.11 and will be removed in a future version.

    Use DIDLMetadataError instead.
    """


class DIDLMetadataError(CannotCreateDIDLMetadata):

    """ Raised if a data container class cannot create the DIDL metadata due to
    missing information.

    For backward compatibility, this is currently a subclass of
    CannotCreateDIDLMetadata. In a future version, it will likely become a
    direct subclass of SoCoException.

    """


class MusicServiceException(SoCoException):

    """ An error relating to a third party music service """


class UnknownXMLStructure(SoCoException):

    """Raised if XML with and unknown or unexpected structure is returned"""


class SoCoSlaveException(SoCoException):
    """Raised when a master command is called on a slave"""
