# -*- coding: utf-8 -*-
from __future__ import unicode_literals

""" Provides general utility functions to be used across modules """

import re

try:
    from types import StringType, UnicodeType

except ImportError:
    StringType = bytes
    UnicodeType = str


def really_unicode(in_string):
    """
    Ensures s is returned as a unicode string and not just a string through
    a series of progressively relaxed decodings

    """
    if type(in_string) is StringType:
        for args in (('utf-8',), ('latin-1',), ('ascii', 'replace')):
            try:
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
