# -*- coding: utf-8 -*-
from types import StringType, UnicodeType

def really_unicode(s):
    """
    Ensures s is returned as a unicode string and not just a string through
    a serries of progressively relaxed decodings
    """
    if type(s) is StringType:
        for args in (('utf-8',), ('latin-1',), ('ascii', 'replace')):
            try:
                s = s.decode(*args)
                break
            except UnicodeDecodeError:
                continue
    if type(s) is not UnicodeType:
        raise ValueError("%s is not a string at all." % s)
    return s

def really_utf8(s):
    """
    First decodes s via really_unicode to ensure it can successfully be encoded as utf-8
    This is required since just calling encode on a string will often cause python to
    perform a coerced strict auto-decode as ascii first and will result in a
    UnicodeDecodeError being raised
    After really_unicode returns a safe unicode string, encode as 'utf-8' and return
    the utf-8 encoded string
    """
    return really_unicode(s).encode('utf-8')
