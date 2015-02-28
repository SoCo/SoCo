
""" Module that contains various compatability definitions and imports """

# pylint: disable=unused-import,import-error,no-name-in-module


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

except ImportError:  # python 2.7
    from SimpleHTTPServer import SimpleHTTPRequestHandler  # nopep8
    from urllib2 import urlopen, URLError  # nopep8
    from urllib import quote_plus  # nopep8
    import SocketServer as socketserver  # nopep8
    from Queue import Queue  # nopep8
    from types import StringType, UnicodeType  # nopep8
    from urllib import quote as quote_url  # nopep8

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
