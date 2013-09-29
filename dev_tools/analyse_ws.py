#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Script to analyse ws dumps """

import argparse
import os
import sys
import re
import codecs
import ConfigParser
import curses
import pygments
from pygments.lexers import XmlLexer
from subprocess import call
from scapy.all import rdpcap
from lxml import etree

# Constants
# tokens types to use for color schemes
# Token.Comment, Token.Text, Token.Name.Attribute, Token.Name.Tag,
# Token.Name.Entity, Token.Comment.Preproc, Token.Literal.String


class AnalyzeWS(object):
    """ Class for analysis of WireShark dump """

    def __init__(self, args):
        self.screen = None
        self.messages = []
        self.args = args
        self.output_prefix = args.output_prefix
        try:
            with open('analyse_ws.ini') as file__:
                self.config = ConfigParser.ConfigParser()
                self.config.readfp(file__)
        except IOError:
            pass

    def add_file(self, filename):
        """ Add a file to the captured content """
        # Use the first file as prefix if none is given
        if self.output_prefix is None:
            self.output_prefix = filename
        # Check if the file is present, since rdpcap will not do that
        if not (os.path.isfile(filename) and os.access(filename, os.R_OK)):
            print 'The file \'{0}\' is either not present or not readable. '\
                  'Exiting!'.format(filename)
            sys.exit(1)
        packets = rdpcap(filename)
        for packet in packets[:10]:
            # See if there is a field called load
            try:
                load = packet.getfieldval('load')
                # If there is double newline it is a new message
                if '\r\n\r\n' in load:
                    self.messages.append(WSPart(load, self.args))
                elif len(self.messages) > 0:
                    self.messages[-1].add_content(load)
                else:
                    print 'First message skipped'
            except AttributeError:
                pass

    def complete_file_addition(self):
        """ Parse the body as xml for all the recieved messages """
        for message in self.messages:
            message.init_xml()
            message.form_output()

    def to_file_mode(self):
        """ To file mode """
        for index in range(len(self.messages)):
            self.__to_file(index)

    def __to_file(self, index):
        """ Write a single message to file """
        filename = '{0}_{1}.xml'.format(self.output_prefix, index)
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

    def to_browser_mode(self):
        """ To browser mode """
        for index in range(len(self.messages)):
            self.__to_browser(index)

    def __to_browser(self, index):
        """ Write a single message to file and open the file in a
        browser
        """
        filename = self.__to_file(index)
        command = self.config.get('General', 'browser_command').\
            format(filename)
        call(command, shell=True)

    def interactive_mode(self):
        """ Interactive mode """
        xml_types = []
        for val in XmlLexer().tokens.values():
            for regexp in val:
                if regexp[1] not in xml_types:
                    xml_types.append(regexp[1])
        print xml_types
        #tokens = pygments.lex(self.messages[0].output, XmlLexer())
        #types = []
        #for token in tokens:
        #    if token[0] not in types:
        #        types.append(token[0])
        #        print token
        return
        self.__curses_mode(True)
        self.__update_window(0)
        position = 0
        action = None
        while action != ord('q'):
            action = self.screen.getch()
            if action in [curses.KEY_DOWN, curses.KEY_RIGHT]:
                position = max(min(len(self.messages) - 1, position + 1), 0)
            elif action in [curses.KEY_UP, curses.KEY_LEFT]:
                position = max(min(len(self.messages) - 1, position - 1), 0)
            self.__update_window(position)

        self.__curses_mode(False)

    def __curses_mode(self, start):
        """ Convinience functionto initiate and close the curses window """
        if start:
            self.screen = curses.initscr()
            curses.noecho()
            curses.cbreak()
            self.screen.keypad(1)
        else:
            curses.echo()
            curses.nocbreak()
            self.screen.keypad(0)
            curses.endwin()

    def __update_window(self, position, status=''):
        """ Update the window with the menu and the new text """
        _, width = self.screen.getmaxyx()
        self.screen.clear()
        menu = 'LEFT, RIGHT | (b)rowser | to-(f)ile | {0}/{1} | {2}\n{3}\n'\
            .format(position, len(self.messages) - 1, status, '-' * width)
        self.screen.addstr(0, 0, menu)
        content = self.messages[position].output.encode('utf-8')
        
        # Use pygemtize, lexer xml, formatter raw
        #chunks = [content[i:i+100] for i in range(0, len(content), 100)]
        #for chunk in chunks:
        #    self.screen.addstr(chunk)
        self.screen.refresh()


class WSPart(object):
    """ This class parses and represents a single Sonos UPnP message """

    def __init__(self, captured, args):
        self.external_inner_xml = args.external_inner_xml
        self.inner_xml = []
        self.body_formatted = u''
        self.output = u''
        # Analyze initial xml part
        raw_head, raw_body = captured.split('\r\n\r\n')
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

    def init_xml(self):
        """ Parse the present body as xml """
        tree = etree.fromstring(self.body)
        for text in tree.xpath('.//text()[contains(., "DIDL")]'):
            item = text.getparent()
            didl_tree = etree.fromstring(item.text.decode('utf-8'))
            if self.external_inner_xml:
                item.text = 'DIDL_REPLACEMENT_{0}'.format(len(self.inner_xml))
                didl_string = etree.tostring(didl_tree, pretty_print=True)
                self.inner_xml.append(didl_string.decode(self.encoding))
            else:
                item.text = None
                item.append(didl_tree)

        self.body_formatted = etree.tostring(tree, pretty_print=True).decode(
            self.encoding)

    def form_output(self):
        """ Form the output """
        self.output = u''
        if self.external_inner_xml:
            self.output += u'<Dummy_tag_to_create_valid_xml_on_external_inner'\
                           '_xml>\n'
        self.output += u'<!-- BODY -->\n{0}'.format(self.body_formatted)

        if self.external_inner_xml:
            for number, didl in enumerate(self.inner_xml):
                self.output += u'\n<!-- DIDL_{0} -->\n{1}'.format(number, didl)
            self.output += u'</Dummy_tag_to_create_valid_xml_on_external_'\
                           'inner_xml>'


def __build_option_parser():
    """ Build the option parser for this script """
    description = ('Tool to analyze Wireshark dumps of Sonos traffic')
    parser = \
        argparse.ArgumentParser(description=description,
                                formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('files', metavar='FILES', type=str, nargs='+',
                        help='The files to analyze. If multiple files are '
                        'provided they will be considered part of a series.')
#    parser.add_argument('--output-prefix', type=str, nargs=1,
#                        help='The output filename prefix to use')
    parser.add_argument('--output-prefix', type=str,
                        help='The output filename prefix to use')
    parser.add_argument('--to-file', action='store_const', const=True,
                        help='Output xml to files', default=False)
    parser.add_argument('--to-browser', action='store_const', const=True,
                        help='Output xml to browser. Implies --to-file.',
                        default=False)
    parser.add_argument('--external-inner-xml', action='store_const',
                        const=True, help='Show the internal separately encoded'
                        'xml externally instead in re-integrating it',
                        default=False)
    return parser

if __name__ == '__main__':
    PARSER = __build_option_parser()
    ARGS = PARSER.parse_args()
    ANALYZE_WS = AnalyzeWS(ARGS)
    for file_ in ARGS.files:
        try:
            ANALYZE_WS.add_file(file_)
        except IOError:
            pass
    ANALYZE_WS.complete_file_addition()

    # Start the chosen mode
    if ARGS.to_file or ARGS.to_browser:
        ANALYZE_WS.to_file_mode()
        if ARGS.to_browser:
            ANALYZE_WS.to_browser_mode()
    else:
        ANALYZE_WS.interactive_mode()
