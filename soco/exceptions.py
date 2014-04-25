# -*- coding: utf-8 -*-


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
        self.message = message
        self.error_code = error_code
        self.error_description = error_description
        self.error_xml = error_xml

    def __str__(self):
        return self.message


class CannotCreateDIDLMetadata(SoCoException):
    """ Raised if a data container class cannot create the DIDL metadata due to
    missing information

    """
