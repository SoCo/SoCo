# -*- coding: utf-8 -*-

""" Provides general utility functions to be used across modules """

from __future__ import unicode_literals, absolute_import, print_function

import re
import threading
import functools
import warnings
from time import time
from .compat import StringType, UnicodeType, dumps
from .xml import XML


def really_unicode(in_string):
    """
    Ensures s is returned as a unicode string and not just a string through
    a series of progressively relaxed decodings

    """
    if type(in_string) is StringType:
        for args in (('utf-8',), ('latin-1',), ('ascii', 'replace')):
            try:
                # pylint: disable=star-args
                in_string = in_string.decode(*args)
                break
            except UnicodeDecodeError:
                continue
    if type(in_string) is not UnicodeType:
        raise ValueError('%s is not a string at all.' % in_string)
    return in_string


def really_utf8(in_string):
    """ First decodes s via really_unicode to ensure it can successfully be
    encoded as utf-8 This is required since just calling encode on a string
    will often cause python to perform a coerced strict auto-decode as ascii
    first and will result in a UnicodeDecodeError being raised After
    really_unicode returns a safe unicode string, encode as 'utf-8' and return
    the utf-8 encoded string.

    """
    return really_unicode(in_string).encode('utf-8')


FIRST_CAP_RE = re.compile('(.)([A-Z][a-z]+)')
ALL_CAP_RE = re.compile('([a-z0-9])([A-Z])')


def camel_to_underscore(string):
    """ Convert camelcase to lowercase and underscore
    Recipy from http://stackoverflow.com/a/1176023
    """
    string = FIRST_CAP_RE.sub(r'\1_\2', string)
    return ALL_CAP_RE.sub(r'\1_\2', string).lower()


def prettify(unicode_text):
    """Return a pretty-printed version of a unicode XML string. Useful for
    debugging.

    """
    import xml.dom.minidom
    reparsed = xml.dom.minidom.parseString(unicode_text.encode('utf-8'))
    return reparsed.toprettyxml(indent="  ", newl="\n")


def show_xml(xml):
    """Pretty print an ElementTree XML object

    Args:
        xml (ElementTree): The :py:class:`xml.etree.ElementTree` to pretty
            print

    NOTE: This function is a convenience function used during development, it
    is not used anywhere in the main code base
    """
    string = XML.tostring(xml)
    print(prettify(string))


class TimedCache(object):

    """ A simple thread-safe cache for caching method return values

    At present, the cache can theoretically grow and grow, since entries are
    not automatically purged, though in practice this is unlikely since there
    are not that many different combinations of arguments in the places where
    it is used in SoCo, so not that many different cache entries will be
    created. If this becomes a problem, use a thread and timer to purge the
    cache, or rewrite this to use LRU logic!

    """

    def __init__(self, default_timeout=0):
        super(TimedCache, self).__init__()
        self._cache = {}
        # A thread lock for the cache
        self._cache_lock = threading.Lock()
        #: The default caching interval in seconds. Set to 0
        #: to disable the cache by default
        self.default_timeout = default_timeout

    @staticmethod
    def make_key(args, kwargs):
        """
        Generate a unique, hashable, representation of the args and kwargs

        """
        # This is not entirely straightforward, since args and kwargs may
        # contain mutable items and unicode. Possibiities include using
        # __repr__, frozensets, and code from Py3's LRU cache. But pickle
        # works, and although it is not as fast as some methods, it is good
        # enough at the moment
        cache_key = dumps((args, kwargs))
        return cache_key

    def get(self, *args, **kwargs):

        """

        Get an item from the cache for this combination of args and kwargs.

        Return None if no unexpired item is found. This means that there is no
        point storing an item in the cache if it is None.

        """
        # Look in the cache to see if there is an unexpired item. If there is
        # we can just return the cached result.
        cache_key = self.make_key(args, kwargs)
        # Lock and load
        with self._cache_lock:
            if cache_key in self._cache:
                expirytime, item = self._cache[cache_key]

                if expirytime >= time():
                    return item
                else:
                    # An expired item is present - delete it
                    del self._cache[cache_key]
        # Nothing found
        return None

    def put(self, item, *args, **kwargs):

        """ Put an item into the cache, for this combination of args and
        kwargs.

        If `timeout` is specified as one of the keyword arguments, the item
        will remain available for retrieval for `timeout` seconds. If `timeout`
        is None or not specified, the default cache timeout for this cache will
        be used. Specify a `timeout` of 0 (or ensure that the default timeout
        for this cache is 0) if this item is not to be cached."""

        # Check for a timeout keyword, store and remove it.
        timeout = kwargs.pop('timeout', None)
        if timeout is None:
            timeout = self.default_timeout
        cache_key = self.make_key(args, kwargs)
        # Store the item, along with the time at which it will expire
        with self._cache_lock:
            self._cache[cache_key] = (time() + timeout, item)

    def delete(self, *args, **kwargs):
        """Delete an item from the cache for this combination of args and
        kwargs"""
        cache_key = self.make_key(args, kwargs)
        with self._cache_lock:
            try:
                del self._cache[cache_key]
            except KeyError:
                pass

    def clear(self):
        """Empty the whole cache"""
        with self._cache_lock:
            self._cache.clear()


class deprecated(object):
    """ A decorator to mark deprecated objects.

    Causes a warning to be issued when the object is used, and marks the object
    as deprecated in the Sphinx docs.

    args:
        since (str): The version in which the object is deprecated
        alternative (str, optional): The name of an alternative object to use

    Example:

        ::

            @deprecated(since="0.7", alternative="new_function")
            def old_function(args):
                pass


    """
    # pylint really doesn't like decorators!
    # pylint: disable=invalid-name, too-few-public-methods
    # pylint: disable=no-member, missing-docstring
    def __init__(self, since, alternative=None, will_be_removed_in=None):
        self.since_version = since
        self.alternative = alternative
        self.will_be_removed_in = will_be_removed_in

    def __call__(self, deprecated_fn):

        @functools.wraps(deprecated_fn)
        def decorated(*args, **kwargs):

            message = "Call to deprecated function {0}.".format(
                deprecated_fn.__name__)
            if self.will_be_removed_in is not None:
                message += " Will be removed in version {0}.".format(
                    self.will_be_removed_in)
            if self.alternative is not None:
                message += " Use {0} instead.".format(self.alternative)
            warnings.warn(message, stacklevel=2)

            return deprecated_fn(*args, **kwargs)

        docs = "\n\n  .. deprecated:: {0}\n".format(self.since_version)
        if self.will_be_removed_in is not None:
            docs += "\n     Will be removed in version {0}.".format(
                self.will_be_removed_in)
        if self.alternative is not None:
            docs += "\n     Use {0} instead.".format(self.alternative)
        if decorated.__doc__ is None:
            decorated.__doc__ = ''
        decorated.__doc__ += docs
        return decorated
