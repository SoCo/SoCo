#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=E0611

""" Script to analyse ws dumps """

import argparse
import os
import sys
PLATFORM = sys.platform.lower()
if PLATFORM == 'win32':
    import msvcrt
    COLOR = False
else:
    import tty
    import termios
    COLOR = True
import re
import codecs
import ConfigParser
import StringIO
try:
    import pygments
    from pygments.lexers import XmlLexer
    from pygments.formatters import TerminalFormatter
except ImportError:
    print 'Module "pygment" could not be imported. Please install it. Exiting!'
    sys.exit(100)
try:
    STDERR = sys.stderr
    sys.stderr = StringIO.StringIO()
    from scapy.all import rdpcap
    sys.stderr = STDERR
except ImportError:
    print 'Module "scapy" could not be imported. Please install it. Exiting!'
    sys.exit(101)
try:
    from lxml import etree
except ImportError:
    print 'Module "lxml" could not be imported. Please install it. Exiting!'
    sys.exit(102)
import subprocess

# Text bits that starts and ends the Sonos UPnP content
STARTS = ['<s:Envelope', '<e:propertyset']
ENDS = ['</s:Envelope>', '</e:propertyset>']


class AnalyzeWS(object):
    """ Class for analysis of WireShark dumps. Also shows the parts of the
    WireShark dumps syntax highlighted in the terminal and/or writes them to
    files and shows them in a browser.
    """

    def __init__(self, args):
        self.messages = []
        self.args = args
        self.output_prefix = args.output_prefix
        try:
            with open('analyse_ws.ini') as file__:
                self.config = ConfigParser.ConfigParser()
                self.config.readfp(file__)
        except IOError:
            self.config = None

    def set_file(self, filename):
        """ Add a file to the captured content """
        # Use the file name as prefix if none is given
        if self.output_prefix is None:
            self.output_prefix = filename
        # Check if the file is present, since rdpcap will not do that
        if not (os.path.isfile(filename) and os.access(filename, os.R_OK)):
            print 'The file \'{0}\' is either not present or not readable. '\
                  'Exiting!'.format(filename)
            sys.exit(1)
        packets = rdpcap(filename)

        for packet in packets:
            # See if there is a field called load
            try:
                load = packet.getfieldval('load')
                # If there is a start in load
                if any([start in load for start in STARTS]):
                    self.messages.append(WSPart(load, self.args))
                    # and there is also an end
                    if any([end in load for end in ENDS]):
                        self.messages[-1].finalize_content()
                # If there is an end in load
                elif any([end in load for end in ENDS]):
                    # If there is an open WSPart
                    if len(self.messages) > 0 and not\
                            self.messages[-1].write_closed:
                        self.messages[-1].add_content(load)
                        self.messages[-1].finalize_content()
                    # Ignore ends before start
                    else:
                        pass
                else:
                    # If there is an open WSPart
                    if len(self.messages) > 0 and not\
                            self.messages[-1].write_closed:
                        self.messages[-1].add_content(load)
                    # else ignore
                    else:
                        pass
            except AttributeError:
                pass
        if len(self.messages) > 0 and not self.messages[-1].write_closed:
            del self.messages[-1]

    def to_file_mode(self):
        """ To file mode """
        for index in range(len(self.messages)):
            self.__to_file(index)

    def __to_file(self, index):
        """ Write a single message to file """
        filename = self.__create_file_name(index)
        try:
            with codecs.open(filename, mode='w', encoding='utf-8') as file__:
                file__.write(self.messages[index].output)
        except IOError as excep:
            print 'Unable for open the file \'{0}\' for writing. The '\
                  'following exception was raised:'.format(filename)
            print excep
            print 'Exiting!'
            sys.exit(2)
        return filename

    def __create_file_name(self, index):
        """ Create the filename to save to """
        return '{0}_{1}.xml'.format(self.output_prefix, index)

    def to_browser_mode(self):
        """ To browser mode """
        for index in range(len(self.messages)):
            self.__to_browser(index)

    def __to_browser(self, index):
        """ Write a single message to file and open the file in a
        browser
        """
        filename = self.__to_file(index)
        try:
            command = self.config.get('General', 'browser_command')
        except (ConfigParser.NoOptionError, AttributeError):
            print 'Incorrect or missing .ini file. See --help.'
            sys.exit(5)
        command = str(command).format(filename)
        command_list = command.split(' ')
        try:
            subprocess.Popen(command_list, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        except OSError:
            print 'Unable to execute the browsercommand:'
            print command
            print 'Exiting!'
            sys.exit(21)

    def interactive_mode(self):
        """ Interactive mode """
        position = 0
        action = None
        while action != 'q':
            self.__update_window(position)
            action = getch()
            if action == 'n':
                position = max(min(len(self.messages) - 1, position + 1), 0)
            elif action == 'p':
                position = max(min(len(self.messages) - 1, position - 1), 0)
            elif action == 'b':
                self.__to_browser(position)
            elif action == 'f':
                self.__to_file(position)

    def __update_window(self, position, status=''):
        """ Update the window with the menu and the new text """
        if PLATFORM == 'win32':
            # Defaulting to 80 on windows, better ideas are welcome, but the
            # solutions I found online are rather bulky
            width = 80
        else:
            _, width = os.popen('stty size', 'r').read().split()
            width = int(width)

        file_exists_label = 'FILE'
        if not os.path.exists(self.__create_file_name(position)):
            file_exists_label = ' ' * len(file_exists_label)
        # Clear the screen
        if PLATFORM == 'win32':
            # Ugly hack until someone figures out a better way for Windows
            # probably something with a cls command, but I cannot test it
            for _ in range(50):
                print
        else:
            print '\x1b[2J\x1b[H'  # Clear screen
        # Menu
        menu = ('(p)revious, (n)ext | (b)rowser | to (f)ile | {0} | (q)uit | '
                '{1}/{2} | {3}\n{4}\n').format(file_exists_label,
                                               position,
                                               len(self.messages) - 1,
                                               status, '-' * width)
        print menu
        # Content
        content = self.messages[position].output.encode('utf-8')
        out = content
        if self.args.color:
            out = pygments.highlight(content, XmlLexer(), TerminalFormatter())
        print out


class WSPart(object):  # pylint: disable=R0902
    """ This class parses and represents a single Sonos UPnP message """

    def __init__(self, captured, args):
        self.external_inner_xml = args.external_inner_xml
        self.inner_xml = []
        self.body_formatted = u''
        self.output = u''
        self.write_closed = False
        # Analyze initial xml part
        try:
            raw_head, raw_body = captured.split('\r\n\r\n')
        except ValueError:
            raw_head = ''
            raw_body = captured
        # Get encoding
        search = re.search(r'.*charset="(.*)"', raw_head)
        try:
            self.encoding = search.group(1)
        except AttributeError:
            self.encoding = 'utf-8'
        # Decode the body
        self.head = raw_head.decode(self.encoding)
        self.body = raw_body.decode(self.encoding)

    def add_content(self, captured):
        """ Adds content to the main UPnP message """
        self.body += captured.decode(self.encoding)

    def finalize_content(self):
        """ Finalize the additons """
        self.write_closed = True
        self._init_xml()
        self._form_output()

    def _init_xml(self):
        """ Parse the present body as xml """
        tree = etree.fromstring(self.body)
        # Extract and replace inner DIDL xml in tags
        for text in tree.xpath('.//text()[contains(., "DIDL")]'):
            item = text.getparent()
            didl_tree = etree.fromstring(item.text)
            if self.external_inner_xml:
                item.text = 'DIDL_REPLACEMENT_{0}'.format(len(self.inner_xml))
                self.inner_xml.append(didl_tree)
            else:
                item.text = None
                item.append(didl_tree)

        # Extract and replace inner DIDL xml in properties in inner xml
        for inner_tree in self.inner_xml:
            for item in inner_tree.xpath('//*[contains(@val, "DIDL")]'):
                if self.external_inner_xml:
                    didl_tree = etree.fromstring(item.attrib['val'])
                    item.attrib['val'] = 'DIDL_REPLACEMENT_{0}'.\
                        format(len(self.inner_xml))
                    self.inner_xml.append(didl_tree)

        self.body_formatted = etree.tostring(tree, pretty_print=True).decode(
            self.encoding)

    def _form_output(self):
        """ Form the output """
        self.output = u''
        if self.external_inner_xml:
            self.output += u'<Dummy_tag_to_create_valid_xml_on_external_inner'\
                           '_xml>\n'
        self.output += u'<!-- BODY -->\n{0}'.format(self.body_formatted)

        if self.external_inner_xml:
            for number, didl in enumerate(self.inner_xml):
                self.output += u'\n<!-- DIDL_{0} -->\n{1}'.\
                    format(number, etree.tostring(didl, pretty_print=True))
            self.output += u'</Dummy_tag_to_create_valid_xml_on_external_'\
                           'inner_xml>'


def __build_option_parser():
    """ Build the option parser for this script """
    description = (
        'Tool to analyze Wireshark dumps of Sonos traffic.\n'
        '\n'
        'The files that are input to this script must be in the '
        '"Wireshark/tcpdump/...-libpcap" format, which can be exported from '
        'Wireshark.'
        '\n'
        'To use the open in browser function, a configuration file must be '
        'written. It should be in the same directory as this script and have '
        'the name "analyse_ws.ini". An example of such a file is given '
        'below:\n'
        '[General]\n'
        'browser_command: epiphany\n'
        '\n'
        'The browser command should be any command that opens a new tab in '
        'the program you wish to read the Wireshark dumps in.')

    parser = \
        argparse.ArgumentParser(description=description,
                                formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('file_', metavar='FILE', type=str, nargs=1,
                        help='the file to analyze')
    parser.add_argument('--output-prefix', type=str,
                        help='the output filename prefix to use')
    parser.add_argument('--to-file', action='store_const', const=True,
                        help='output xml to files', default=False)
    parser.add_argument('--disable-color', action='store_const', const=False,
                        help='disable color in interactive mode',
                        default=COLOR, dest='color')
    parser.add_argument('--enable-color', action='store_const', const=True,
                        help='disable color in interactive mode',
                        default=COLOR, dest='color')
    parser.add_argument('--to-browser', action='store_const', const=True,
                        help='output xml to browser, implies --to-file',
                        default=False)
    parser.add_argument('--external-inner-xml', action='store_const',
                        const=True, help='show the internal separately '
                        'encoded xml externally instead of re-integrating it',
                        default=False)
    return parser


def getch():
    """ Read a single character non-echoed and return it. Recipy from:
    http://code.activestate.com/recipes/
    134892-getch-like-unbuffered-character-reading-from-stdin/
    """
    filedescriptor = sys.stdin.fileno()
    old_settings = termios.tcgetattr(filedescriptor)
    if PLATFORM == 'win32':
        character = msvcrt.getch()
    else:
        try:
            tty.setraw(sys.stdin.fileno())
            character = sys.stdin.read(1)
        finally:
            termios.tcsetattr(filedescriptor, termios.TCSADRAIN, old_settings)
    return character


def main():
    """ Main method of the script """
    parser = __build_option_parser()
    args = parser.parse_args()
    analyze_ws = AnalyzeWS(args)
    try:
        analyze_ws.set_file(args.file_[0])
    except IOError:
        pass

    # Start the chosen mode
    if args.to_file or args.to_browser:
        analyze_ws.to_file_mode()
        if args.to_browser:
            analyze_ws.to_browser_mode()
    else:
        analyze_ws.interactive_mode()

if __name__ == '__main__':
    main()
