# -*- coding: utf-8 -*-
""" Caching """

from __future__ import unicode_literals

import threading
from time import time

from .compat import dumps
from soco import config


class _BaseCache(object):

    """A base class for the cache.

    Does nothing by itself."""
    # pylint: disable=no-self-use, unused-argument

    def __init__(self, default_timeout=0):
        super(_BaseCache, self).__init__()
        self._cache = {}
        # : The default caching interval in seconds.
        self.default_timeout = default_timeout
        #: Is the cache enabled? True or False
        self.enabled = True

    def get(self, *args, **kwargs):
        """
        Get an item from the cache for this combination of args and kwargs.
        Returns None, indicating that no item has been found.
        """
        return None

    def put(self, *args, **kwargs):
        """
        Put an item into the cache, for this combination of args and
        kwargs.
        """
        pass

    def delete(self, *args, **kwargs):
        """
        Delete an item from the cache for this combination of args and
        kwargs.
        """
        pass

    def clear(self):
        """
        Empty the whole cache.
        """
        pass


class NullCache(_BaseCache):

    """A cache which does nothing. Useful for debugging."""
    pass


class TimedCache(_BaseCache):

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
        # A thread lock for the cache
        self._cache_lock = threading.Lock()

    def get(self, *args, **kwargs):
        """Get an item from the cache for this combination of args and kwargs.

        Return None if no unexpired item is found. This means that there is no
        point storing an item in the cache if it is None.

        """
        if not self.enabled:
            return None
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

        if not self.enabled:
            return
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

    @staticmethod
    def make_key(*args, **kwargs):
        """
        Generate a unique, hashable, representation of the args and kwargs

        """
        # This is not entirely straightforward, since args and kwargs may
        # contain mutable items and unicode. Possibilities include using
        # __repr__, frozensets, and code from Py3's LRU cache. But pickle
        # works, and although it is not as fast as some methods, it is good
        # enough at the moment
        cache_key = dumps((args, kwargs))
        return cache_key


class Cache(_BaseCache):

    """A factory class which returns an instance of a cache subclass.

    If config.CACHE_ENABLED is False, the dummy inactive cache will be returned
    """

    def __new__(cls, *args, **kwargs):
        if config.CACHE_ENABLED:
            new_cls = TimedCache
        else:
            new_cls = NullCache
        instance = super(Cache, cls).__new__(new_cls)
        instance.__init__(*args, **kwargs)
        return instance
