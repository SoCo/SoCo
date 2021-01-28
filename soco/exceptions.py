# Disable while we have Python 2.x compatability
# pylint: disable=useless-object-inheritance

"""Exceptions that are used by SoCo."""


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
        super().__init__()
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


class SoCoNotVisibleException(SoCoException):
    """Raised when a command intended for a visible speaker is called
    on an invisible one."""


class NotSupportedException(SoCoException):
    """Raised when something is not supported by the device"""


class EventParseException(SoCoException):
    """Raised when a parsing exception occurs during event handling.

    Attributes:
        tag (str): The tag for which the exception occured
        metadata (str): The metadata which failed to parse
        __cause__ (Exception): The original exception
    """

    def __init__(self, tag, metadata, cause):
        """
        Args:
            tag (str): The tag for which the exception occured
            metadata (str): The metadata which failed to parse
            cause (Exception): The original exception
        """
        super().__init__()
        self.tag = tag
        self.metadata = metadata
        self.__cause__ = cause

    def __str__(self):
        return "Invalid metadata for '{}'".format(self.tag)


class SoCoFault:
    """Class to represent a failed object instantiation.

    It rethrows the exception on common use.

    Attributes:
        exception: The exception which will be thrown on use
    """

    def __init__(self, exception):
        """
        Args:
            exception (Exception): The exception which should be thrown on use
        """
        self.__dict__["exception"] = exception

    def __getattr__(self, name):
        raise self.exception

    def __setattr__(self, name, value):
        raise self.exception

    def __getitem__(self, item):
        raise self.exception

    def __setitem__(self, key, value):
        raise self.exception

    def __repr__(self):
        return "<{}: {} at {}>".format(
            self.__class__.__name__, repr(self.exception), hex(id(self))
        )

    def __str__(self):
        return "<{}: {}>".format(self.__class__.__name__, repr(self.exception))
