# -*- coding: utf-8 -*-


class SoCoException(Exception):
    """ base exception raised by SoCo, containing the UPnP error code """


class UnknownSoCoException(SoCoException):
    """ raised if reason of the error can not be extracted

    The exception object will contain the raw response sent back from the
    speaker """
