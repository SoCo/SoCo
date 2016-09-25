# -*- coding: utf-8 -*-
# pylint: disable=unused-import,import-error,no-name-in-module,
# pylint: disable=ungrouped-imports

"""This module contains various compatibility definitions and imports.

It is used internally by SoCo to ensure compatibility with Python 2."""

from __future__ import unicode_literals

try:  # python 3
    from http.server import BaseHTTPRequestHandler  # noqa
    from urllib.request import urlopen  # noqa
    from urllib.error import URLError  # noqa
    from urllib.parse import quote_plus  # noqa
    import socketserver  # noqa
    from queue import Queue  # noqa
    StringType = bytes  # noqa
    UnicodeType = str  # noqa
    from urllib.parse import quote as quote_url  # noqa
    from urllib.parse import urlparse, parse_qs  # noqa

except ImportError:  # python 2.7
    from BaseHTTPServer import BaseHTTPRequestHandler  # noqa
    from urllib2 import urlopen, URLError  # noqa
    from urllib import quote_plus  # noqa
    import SocketServer as socketserver  # noqa
    from Queue import Queue  # noqa
    from types import StringType, UnicodeType  # noqa
    from urllib import quote as quote_url   # noqa
    from urlparse import urlparse, parse_qs  # noqa

try:  # python 2.7 - this has to be done the other way round
    from cPickle import dumps  # noqa
except ImportError:  # python 3
    from pickle import dumps  # noqa

# Support Python 2.6
try:  # Python 2.7+
    from logging import NullHandler  # noqa
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
