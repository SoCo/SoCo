# -*- coding: utf-8 -*-
""" Tests for the utils module """

from __future__ import unicode_literals
from soco.utils import TimedCache, deprecated

def test_cache_put_get():
    "Test putting items into, and getting them from, the cache"
    from time import sleep
    cache = TimedCache()
    cache.put("item", 'some', kw='args', timeout=3)
    assert not cache.get('some', 'otherargs') == "item"
    assert cache.get('some', kw='args') == "item"
    sleep(2)
    assert cache.get('some', kw='args') == "item"
    sleep(2)
    assert not cache.get('some', kw='args') == "item"


    cache.put("item", 'some', 'args', and_a='keyword', timeout=3)
    assert cache.get('some', 'args', and_a='keyword') == "item"
    assert not cache.get(
        'some', 'otherargs', and_a='keyword') == "item"

def test_cache_clear_del():
    "Test removal of items and clearing the cache"
    cache = TimedCache()
    cache.put("item", "some", kw="args", timeout=2)
    # Check it's there
    assert cache.get('some', kw='args') == "item"
    # delete it
    cache.delete('some', kw='args')
    assert not cache.get('some', kw='args') == "item"
    # put it back
    cache.put("item", "some", kw="args", timeout=3)
    cache.clear()
    assert not cache.get('some', kw='args') == "item"

def test_with_typical_args():
    cache = TimedCache()
    cache.put ("result", 'SetAVTransportURI', [
            ('InstanceID', 1),
            ('CurrentURI', 'URI2'),
            ('CurrentURIMetaData', 'abcd'),
            ('Unicode', 'μИⅠℂ☺ΔЄ💋')
            ], timeout=3)
    assert cache.get('SetAVTransportURI', [
            ('InstanceID', 1),
            ('CurrentURI', 'URI2'),
            ('CurrentURIMetaData', 'abcd'),
            ('Unicode', 'μИⅠℂ☺ΔЄ💋')
            ]) == "result"

# Deprecation decorator
def test_deprecation(recwarn):

    @deprecated('0.7')
    def dummy(args):
        """My docs"""
        pass

    @deprecated('0.8', 'better_function', '0.12')
    def dummy2(args):
        """My docs"""
        pass

    assert dummy.__doc__ == "My docs\n\n  .. deprecated:: 0.7\n"
    assert dummy2.__doc__ == "My docs\n\n  .. deprecated:: 0.8\n\n"\
                             "     Will be removed in version 0.12.\n" \
                             "     Use better_function instead."
    dummy(3)
    w = recwarn.pop()
    assert str(w.message) == 'Call to deprecated function dummy.'
    dummy2(4)
    w = recwarn.pop()
    assert str(w.message) == "Call to deprecated function dummy2. Will be " \
                             "removed in version 0.12. Use " \
                             "better_function instead."
    assert w.filename
    assert w.lineno





