# -*- coding: utf-8 -*-
# pylint: disable=unused-import,import-error,no-name-in-module

"""This module contains various compatibility definitions and imports.

It is used internally by SoCo to ensure compatibility with Python 2."""

from __future__ import unicode_literals

try:  # python 3
    from http.server import SimpleHTTPRequestHandler  # nopep8
    from urllib.request import urlopen  # nopep8
    from urllib.error import URLError  # nopep8
    from urllib.parse import quote_plus  # nopep8
    import socketserver  # nopep8
    from queue import Queue  # nopep8
    StringType = bytes  # nopep8
    UnicodeType = str  # nopep8
    from urllib.parse import quote as quote_url  # nopep8
    from urllib.parse import urlparse, parse_qs  # nopep8

except ImportError:  # python 2.7
    from SimpleHTTPServer import SimpleHTTPRequestHandler  # nopep8
    from urllib2 import urlopen, URLError  # nopep8
    from urllib import quote_plus  # nopep8
    import SocketServer as socketserver  # nopep8
    from Queue import Queue  # nopep8
    from types import StringType, UnicodeType  # nopep8
    from urllib import quote as quote_url   # nopep8
    from urlparse import urlparse, parse_qs  # nopep8

try:  # python 2.7 - this has to be done the other way round
    from cPickle import dumps  # nopep8
except ImportError:  # python 3
    from pickle import dumps  # nopep8

# Support Python 2.6
try:  # Python 2.7+
    from logging import NullHandler  # nopep8
except ImportError:
    import logging

    class NullHandler(logging.Handler):

        """Create a null handler if using Python 2.6"""

        def emit(self, record):
            pass


def with_metaclass(meta, *bases):
    """A Python 2/3 compatible way of declaring a metaclass.

    Taken from `Jinja 2 <https://github.com/mitsuhiko/jinja2/blob/master/jinja2
    /_compat.py>`_ via `python-future <http://python-future.org>`_. License:
    BSD.
    Use it like this::

        class MyClass(with_metaclass(MyMetaClass, BaseClass)):
                pass
    """
    class _Metaclass(meta):
        """Inner class"""
        __call__ = type.__call__
        __init__ = type.__init__

        def __new__(cls, name, this_bases, attrs):
            if this_bases is None:
                return type.__new__(cls, name, (), attrs)
            return meta(name, bases, attrs)

    return _Metaclass(str('temporary_class'), None, {})
