# -*- coding: utf-8 -*-

""" Provides general utility functions to be used across modules """

from __future__ import unicode_literals, absolute_import, print_function

import re
import functools
import warnings

from .compat import StringType, UnicodeType, quote_url
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


def url_escape_path(path):
    """ Escape a string value for a URL request path

    >>> url_escape_path("Foo, bar & baz / the hackers")
    u'Foo%2C%20bar%20%26%20baz%20%2F%20the%20hackers'

    """
    # Using 'safe' arg does not seem to work for python 2.6
    return quote_url(path.encode('utf-8')).replace('/', '%2F')
