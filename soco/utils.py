# -*- coding: utf-8 -*-

# Disable while we have Python 2.x compatability
# pylint: disable=useless-object-inheritance,import-outside-toplevel

"""This class contains utility functions used internally by SoCo."""

from __future__ import absolute_import, print_function, unicode_literals

import functools
import re
import warnings

from .compat import StringType, UnicodeType, quote_url
from .xml import XML


def really_unicode(in_string):
    """Make a string unicode. Really.

    Ensure ``in_string`` is returned as unicode through a series of
    progressively relaxed decodings.

    Args:
        in_string (str): The string to convert.

    Returns:
        str: Unicode.

    Raises:
        ValueError
    """
    if isinstance(in_string, StringType):
        for args in (("utf-8",), ("latin-1",), ("ascii", "replace")):
            try:
                # pylint: disable=star-args
                in_string = in_string.decode(*args)
                break
            except UnicodeDecodeError:
                continue
    if not isinstance(in_string, UnicodeType):
        raise ValueError("%s is not a string at all." % in_string)
    return in_string


def really_utf8(in_string):
    """Encode a string with utf-8. Really.

     First decode ``in_string`` via `really_unicode` to ensure it can
     successfully be encoded as utf-8. This is required since just calling
     encode on a string will often cause Python 2 to perform a coerced strict
     auto-decode as ascii first and will result in a `UnicodeDecodeError` being
     raised. After `really_unicode` returns a safe unicode string, encode as
     utf-8 and return the utf-8 encoded string.

    Args:
         in_string (str): The string to convert.

     Returns:
         str: utf-encoded data.
    """
    return really_unicode(in_string).encode("utf-8")


FIRST_CAP_RE = re.compile("(.)([A-Z][a-z]+)")
ALL_CAP_RE = re.compile("([a-z0-9])([A-Z])")


def camel_to_underscore(string):
    """Convert camelcase to lowercase and underscore.

    Recipe from http://stackoverflow.com/a/1176023

    Args:
        string (str): The string to convert.

    Returns:
        str: The converted string.
    """
    string = FIRST_CAP_RE.sub(r"\1_\2", string)
    return ALL_CAP_RE.sub(r"\1_\2", string).lower()


def prettify(unicode_text):
    """Return a pretty-printed version of a unicode XML string.

    Useful for debugging.

    Args:
        unicode_text (str): A text representation of XML (unicode,
            *not* utf-8).

    Returns:
        str: A pretty-printed version of the input.

    """
    import xml.dom.minidom

    reparsed = xml.dom.minidom.parseString(unicode_text.encode("utf-8"))
    return reparsed.toprettyxml(indent="  ", newl="\n")


def show_xml(xml):
    """Pretty print an :class:`~xml.etree.ElementTree.ElementTree` XML object.

    Args:
        xml (:class:`~xml.etree.ElementTree.ElementTree`): The
            :class:`~xml.etree.ElementTree.ElementTree` to pretty print

    Note:
        This is used a convenience function used during development. It
        is not used anywhere in the main code base.
    """
    string = XML.tostring(xml)
    print(prettify(string))


class deprecated(object):

    """A decorator for marking deprecated objects.

    Used internally by SoCo to cause a warning to be issued when the object
    is used, and marks the object as deprecated in the Sphinx documentation.

    Args:
        since (str): The version in which the object is deprecated.
        alternative (str, optional): The name of an alternative object to use
        will_be_removed_in (str, optional): The version in which the object is
            likely to be removed.
        alternative_not_referable (bool): (optional) Indicate that
            ``alternative`` cannot be used as a sphinx reference

    Example:
        ..  code-block:: python

            @deprecated(since="0.7", alternative="new_function")
            def old_function(args):
                pass
    """

    # pylint really doesn't like decorators!
    # pylint: disable=invalid-name, too-few-public-methods
    # pylint: disable=missing-docstring

    def __init__(
        self,
        since,
        alternative=None,
        will_be_removed_in=None,
        alternative_not_referable=False,
    ):
        self.since_version = since
        self.alternative = alternative
        self.will_be_removed_in = will_be_removed_in
        self.alternative_not_referable = alternative_not_referable

    def __call__(self, deprecated_fn):
        @functools.wraps(deprecated_fn)
        def decorated(*args, **kwargs):

            message = "Call to deprecated function {}.".format(deprecated_fn.__name__)
            if self.will_be_removed_in is not None:
                message += " Will be removed in version {}.".format(
                    self.will_be_removed_in
                )
            if self.alternative is not None:
                message += " Use {} instead.".format(self.alternative)
            warnings.warn(message, stacklevel=2)

            return deprecated_fn(*args, **kwargs)

        docs = "\n\n  .. deprecated:: {}\n".format(self.since_version)
        if self.will_be_removed_in is not None:
            docs += "\n     Will be removed in version {}.".format(
                self.will_be_removed_in
            )
        if self.alternative is not None:
            if self.alternative_not_referable:
                docs += "\n     Use ``{}`` instead.".format(self.alternative)
            else:
                docs += "\n     Use `{}` instead.".format(self.alternative)
        if decorated.__doc__ is None:
            decorated.__doc__ = ""
        decorated.__doc__ += docs
        return decorated


def url_escape_path(path):
    """Escape a string value for a URL request path.

    Args:
        str: The path to escape

    Returns:
        str: The escaped path

    >>> url_escape_path("Foo, bar & baz / the hackers")
    u'Foo%2C%20bar%20%26%20baz%20%2F%20the%20hackers'
    """
    # Using 'safe' arg does not seem to work for python 2.6
    return quote_url(path.encode("utf-8")).replace("/", "%2F")


def first_cap(string):
    """Return upper cased first character"""
    return string[0].upper() + string[1:]
