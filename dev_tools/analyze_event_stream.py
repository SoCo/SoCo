# -*- coding: utf-8 -*-

"""Small utility to nicely format events"""

from __future__ import print_function, unicode_literals

import sys
import textwrap
import argparse
import xml.dom.minidom
import traceback

try:
    import pygments
    # pylint: disable=no-name-in-module
    from pygments.lexers import XmlLexer
    from pygments.formatters import TerminalFormatter
except ImportError:
    print('Module "pygments" could not be imported. Please install it. '\
        'Exiting!')
    sys.exit(100)

PLATFORM = sys.platform.lower()
if PLATFORM == 'win32':
    COLOR = False
else:
    COLOR = True

from soco.xml import XML
from soco.events import parse_event_xml


def get_numbered_event_from_stream(filename, event_number):
    """Return a numbered event from an event stream file"""
    event_file = open(filename, 'rb')
    message = 0
    while True:
        try:
            size_bytes = event_file.read(20)
            if len(size_bytes) != 20:
                break
            size = int(size_bytes)
            xml_event = event_file.read(size)
            if message == event_number:
                event_file.close()
                return xml_event, None, message
            message += 1
        except IOError:
            break

    event_file.close()
    print('Event number {} not found'.format(event_number))
    return None, None, None


def get_first_event_with_exception(filename):
    """Get the first event that produces an exception when parsed"""
    event_file = open(filename, 'rb')
    message_no = 0
    while True:
        try:
            size_bytes = event_file.read(20)
            if len(size_bytes) != 20:
                break
            size = int(size_bytes)
            xml_event = event_file.read(size)
            try:
                parse_event_xml(xml_event)
            except Exception:  # pylint: disable=broad-except
                exception_string = traceback.format_exc()
                return xml_event, exception_string, message_no
        except IOError:
            break
        message_no += 1

    event_file.close()
    print('No events with exceptions found')
    return None, None, None


def extract_didl(event, didl_parts=None):
    """Extract the DIDL content

    Recursive substitute DIDL content with a placeholder and put the content
    in a list
    """
    if didl_parts is None:
        didl_parts = []

    content = event.text
    if event.text is not None and content.startswith('<'):
        didl_parts.append(content)
        event.text = '=== DIDL REPLACEMENT {} ==='.format(len(didl_parts) - 1)

    content = event.attrib.get('val')
    if content is not None and content.startswith('<'):
        didl_parts.append(content)
        event.attrib['val'] = '=== DIDL REPLACEMENT {} ==='.format(
            len(didl_parts) - 1)

    for element in event:
        extract_didl(element, didl_parts)

    return event, didl_parts


def indent_and_color_xml(elementtree, color=False):
    """Indent and color an elementtree and return as str"""
    reparsed = xml.dom.minidom.parseString(XML.tostring(elementtree))
    indented = reparsed.toprettyxml(indent="  ", newl="\n")
    if indented.find('\n') > -1:
        indented = indented[indented.find('\n') + 1:]
    if color:
        return pygments.highlight(indented, XmlLexer(), TerminalFormatter())
    else:
        return indented


def __build_option_parser():
    """ Build the option parser for this script """
    description = """
    Tool to output and nicely format single event from an event stream.
    """
    description = textwrap.dedent(description).strip()

    parser = \
        argparse.ArgumentParser(description=description,
                                formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('file_', metavar='FILE', type=str, nargs=1,
                        help='the file to analyze')
    parser.add_argument('event_number', metavar='EVENT_NUMBER', type=int,
                        help='the event number to output, -1 means first '\
                        'event that produces and exception when parsed')
    parser.add_argument('-o', '--output-file', type=str,
                        help='the output filename')
    return parser


def main():
    """ Main method of the script """
    parser = __build_option_parser()
    args = parser.parse_args()
    if args.event_number == -1:
        event, exception, message_no = \
            get_first_event_with_exception(args.file_[0])
    else:
        event, exception, message_no = \
            get_numbered_event_from_stream(args.file_[0], args.event_number)
    if event is None:
        return

    # First extract the didl parts from the main event
    event, didl_parts = extract_didl(XML.fromstring(event))
    didl_parts = [XML.fromstring(part) for part in didl_parts]
    # Then extract DIDL parts from other DIDL parts
    more_didl_parts = []
    for didl_part in list(didl_parts):
        _, more_didl_parts = extract_didl(didl_part, more_didl_parts)
    more_didl_parts = [XML.fromstring(part) for part in more_didl_parts]

    didl_parts += more_didl_parts

    # Format and color the XML
    use_color = COLOR and args.output_file is None
    event = indent_and_color_xml(event, use_color)
    didl_parts = [indent_and_color_xml(e, use_color) for e in didl_parts]

    # Form output string
    output_string = '##### EVENT {}\n{}\n'.format(message_no, event)

    for didl_number, didl_part in enumerate(didl_parts):
        output_string += '### DIDL REPLACEMENT {}\n{}\n'.format(didl_number,
                                                                didl_part)
    if exception is not None:
        output_string += '### EXCEPTION\n{}'.format(exception)

    if args.output_file is not None:
        with open(args.output_file, 'wb') as file_:
            file_.write(output_string.encode('ascii'))
    else:
        print(output_string)


if __name__ == '__main__':
    main()
