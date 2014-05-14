
""" Module that contains XML related utility functions """

# pylint: disable=unused-import

from __future__ import absolute_import

try:
    import xml.etree.cElementTree as XML  # nopep8
except ImportError:
    import xml.etree.ElementTree as XML  # nopep8
