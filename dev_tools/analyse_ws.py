#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=E0611,R0913

""" Script to analyse ws dumps """
from __future__ import print_function

import argparse
import codecs
import math
import os
import re
import subprocess
import sys
import textwrap

try:
    from configparser import ConfigParser, NoOptionError
    from io import StringIO
except ImportError:
    from ConfigParser import ConfigParser, NoOptionError
    from StringIO import StringIO

PLATFORM = sys.platform.lower()
if PLATFORM == "win32":
    import msvcrt

    COLOR = False
else:
    import tty
    import termios

    COLOR = True

try:
    import pygments
    from pygments.lexers import XmlLexer
    from pygments.formatters import TerminalFormatter
except ImportError:
    print('Module "pygments" could not be imported. Please install it. ' "Exiting!")
    sys.exit(100)
try:
    # Temporarily re-directing stderr to StringIO to prevent start-up message
    # from rdpcap import
    STDERR = sys.stderr
    sys.stderr = StringIO()
    from scapy.all import rdpcap

    sys.stderr = STDERR
except ImportError:
    print('Module "scapy" could not be imported. Please install it. Exiting!')
    sys.exit(101)
try:
    from lxml import etree

    PARSER = etree.XMLParser(remove_blank_text=True)
except ImportError:
    print('Module "lxml" could not be imported. Please install it. Exiting!')
    sys.exit(102)

# Text bits that starts and ends the Sonos UPnP content
STARTS = ["<s:Envelope", "<e:propertyset"]
ENDS = ["</s:Envelope>", "</e:propertyset>"]


class AnalyzeWS(object):
    """ Class for analysis of WireShark dumps. Also shows the parts of the
    WireShark dumps syntax highlighted in the terminal and/or writes them to
    files and shows them in a browser.

    The order of processing a file with this class is the following. The
    class is initialized purely with options. All the content is added with
    the set_file method. This method will load the ws file with rdpcap. For
    each part in the ws file that has a load, it will look for Sonos
    content. If such content is present one of three things will happen. If
    it is the beginning of a Sonos message, it will initialize a WSPart. If
    it is the middle part, it will add it to the content of the current
    WSPart with WSPart.add_content. If it is the end, it will finalize the
    WSPart with WSPart.finalize_content. Finalizing the WSPart will, apart
    from closing it for writing also decode the body and parse the XML.

    """

    def __init__(self, args):
        self.messages = []
        self.args = args
        self.output_prefix = args.output_prefix
        try:
            this_dir = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(this_dir, "analyse_ws.ini")) as file__:
                self.config = ConfigParser()
                self.config.readfp(file__)
        except IOError:
            self.config = None
        self.pages = {}

    def set_file(self, filename):
        """ Analyse the file with the captured content """
        # Use the file name as prefix if none is given
        if self.output_prefix is None:
            _, self.output_prefix = os.path.split(filename)
        # Check if the file is present, since rdpcap will not do that
        if not (os.path.isfile(filename) and os.access(filename, os.R_OK)):
            print(
                "The file '{0}' is either not present or not readable. "
                "Exiting!".format(filename)
            )
            sys.exit(1)
        try:
            packets = rdpcap(filename)
        except NameError:
            # Due probably to a bug in rdpcap, this kind of error raises a
            # NameError, because the exception that is tried to raise, is not
            # defined
            print("The file '{}' is not a pcap capture file. Exiting!".format(filename))
            sys.exit(2)

        for number, packet in enumerate(packets):
            # See if there is a field called load
            self._debug("\nNUMBER {0}".format(number), no_prefix=True)
            try:
                # Will cause AttributeError if there is no load
                packet.getfieldval("load")
                # Get the full load
                load = packet.sprintf("%TCP.payload%")
                self._debug("PAYLOAD LENGTH {0}".format(len(load)), no_prefix=True)
                self._debug(load, load=True)
                self._parse_load(load)
            except AttributeError:
                self._debug("LOAD EXCEPTION", no_prefix=True)
        if len(self.messages) > 0 and not self.messages[-1].write_closed:
            self._debug("DELETE LAST OPEN FILE")
            del self.messages[-1]

        if self.args.debug_analysis:
            sys.exit(0)

    def _parse_load(self, load):
        """ Parse the load from a single packet """
        # If the load is ??
        if load in ["??"]:
            self._debug("IGNORING")
        # If there is a start in load
        elif any([start in load for start in STARTS]):
            self._debug("START")
            self.messages.append(WSPart(load, self.args))
            # and there is also an end
            if any([end in load for end in ENDS]):
                self.messages[-1].finalize_content()
                self._debug("AND END")
        # If there is an end in load
        elif any([end in load for end in ENDS]):
            # If there is an open WSPart
            if len(self.messages) > 0 and not self.messages[-1].write_closed:
                self._debug("END ON OPEN FILE")
                self.messages[-1].add_content(load)
                self.messages[-1].finalize_content()
            # Ignore ends before start
            else:
                self._debug("END BUT NO OPEN FILE")
        else:
            # If there is an open WSPart
            if len(self.messages) > 0 and not self.messages[-1].write_closed:
                self._debug("ADD TO OPEN FILE")
                self.messages[-1].add_content(load)
            # else ignore
            else:
                self._debug("NOTHING TO DO")

    def _debug(self, message, load=False, no_prefix=False):
        """ Output debug information """
        if self.args.debug_analysis:
            if load:
                message = "\r\n".join(
                    ["# " + line for line in message.strip().split("\r\n")]
                )
                print("{0}\n{1}\n{0}".format("#" * 78, message))
            else:
                # If open message and no_prefix is False
                if (
                    len(self.messages) > 0 and not self.messages[-1].write_closed
                ) and not no_prefix:
                    print("--OPEN--> {0}".format(message))
                else:
                    print(message)

    def to_file_mode(self):
        """ Write all the messages to files """
        for message_no in range(len(self.messages)):
            self.__to_file(message_no)

    def __to_file(self, message_no):
        """ Write a single message to file """
        filename = self.__create_file_name(message_no)
        try:
            with codecs.open(
                filename, mode="w", encoding=self.messages[message_no].encoding
            ) as file__:
                file__.write(self.messages[message_no].output)
        except IOError as excep:
            print(
                "Unable for open the file '{0}' for writing. The "
                "following exception was raised:".format(filename)
            )
            print(excep)
            print("Exiting!")
            sys.exit(2)
        return filename

    def __create_file_name(self, message_no):
        """ Create the filename to save to """
        cwd = os.getcwd()
        filename = "{0}_{1}.xml".format(self.output_prefix, message_no)
        return os.path.join(cwd, filename)

    def to_browser_mode(self):
        """ Write all the messages to files and open them in the browser """
        for message_no in range(len(self.messages)):
            self.__to_browser(message_no)

    def __to_browser(self, message_no):
        """ Write a single message to file and open the file in a
        browser

        """
        filename = self.__to_file(message_no)
        try:
            command = self.config.get("General", "browser_command")
        except (NoOptionError, AttributeError):
            print("Incorrect or missing .ini file. See --help.")
            sys.exit(5)
        command = str(command).format(filename)
        command_list = command.split(" ")
        try:
            subprocess.Popen(
                command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except OSError:
            print("Unable to execute the browsercommand:")
            print(command)
            print("Exiting!")
            sys.exit(21)

    def interactive_mode(self):
        """ Interactive mode """
        if PLATFORM == "win32":
            # Defaulting to 80 on windows, better ideas are welcome, but the
            # solutions I found online are rather bulky
            height = 20
            width = 80
        else:
            height, width = os.popen("stty size", "r").read().split()
            width = int(width)
            height = int(height)

        message_no = 0
        page_no = 0
        action = None
        while action != "q":
            page_no = self.__update_window(width, height, message_no, page_no)
            action = getch()
            if action == "s":
                # Coerce in range
                message_no = max(min(len(self.messages) - 1, message_no + 1), 0)
                page_no = 0
            elif action == "w":
                # Coerce in range
                message_no = max(min(len(self.messages) - 1, message_no - 1), 0)
                page_no = 0
            elif action == "a":
                page_no -= 1
            elif action == "d":
                page_no += 1
            elif action == "b":
                self.__to_browser(message_no)
            elif action == "f":
                self.__to_file(message_no)

    def __update_window(self, width, height, message_no, page_no):
        """ Update the window with the menu and the new text """
        file_exists_label = "-F-ILE"
        if not os.path.exists(self.__create_file_name(message_no)):
            file_exists_label = "(f)ile"

        # Clear the screen
        if PLATFORM == "win32":
            # Ugly hack until someone figures out a better way for Windows
            # probably something with a cls command, but I cannot test it
            for _ in range(50):
                print()
        else:
            sys.stdout.write("\x1b[2J\x1b[H")  # Clear screen

        # Content
        content = self.messages[message_no].output.rstrip("\n")
        out = content
        if self.args.color:
            out = pygments.highlight(content, XmlLexer(), TerminalFormatter())

        # Paging functionality
        if message_no not in self.pages:
            self._form_pages(message_no, content, out, height, width)
        # Coerce in range
        page_no = max(min(len(self.pages[message_no]) - 1, page_no), 0)
        page_content = self.pages[message_no][page_no]

        # Menu
        max_message = str(len(self.messages) - 1)
        position_string = u"{{0: >{0}}}/{{1: <{0}}}".format(len(max_message))
        position_string = position_string.format(message_no, max_message)
        # Assume less than 100 pages
        current_max_page = len(self.pages[message_no]) - 1
        pages_string = u"{0: >2}/{1: <2}".format(page_no, current_max_page)
        menu = (
            u"(b)rowser | {0} | Message {1} \u2193 (s)\u2191 (w) | "
            u"Page {2} \u2190 (a)\u2192 (d) | (q)uit\n{3}"
        ).format(file_exists_label, position_string, pages_string, "-" * width)

        print(menu)
        print(page_content)
        return page_no

    def _form_pages(self, message_no, content, out, height, width):
        """ Form the pages """
        self.pages[message_no] = []
        page_height = height - 4  # 2-3 for menu, 1 for cursor
        outline = u""
        no_lines_page = 0
        for original, formatted in zip(content.split("\n"), out.split("\n")):
            no_lines_original = int(math.ceil(len(original) / float(width)))

            # Blank line
            if len(original) == 0:
                if no_lines_page + 1 <= page_height:
                    outline += u"\n"
                    no_lines_page += 1
                else:
                    self.pages[message_no].append(outline)
                    outline = u"\n"
                    no_lines_page = 1
                original = formatted = u"\n"
            # Too large line
            elif no_lines_original > page_height:
                if len(outline) > 0:
                    self.pages[message_no].append(outline)
                    outline = u""
                    no_lines_page = 0
                self.pages[message_no].append(formatted)
            # The line(s) can be added to the current page
            elif no_lines_page + no_lines_original <= page_height:
                if len(outline) > 0:
                    outline += u"\n"
                outline += formatted
                no_lines_page += no_lines_original
            # End the page and start a new
            else:
                self.pages[message_no].append(outline)
                outline = formatted
                no_lines_page = no_lines_original
        # Add the remainder
        if len(outline) > 0:
            self.pages[message_no].append(outline)
        if len(self.pages[message_no]) == 0:
            self.pages[message_no].append(u"")


class WSPart(object):
    """ This class parses and represents a single Sonos UPnP message """

    def __init__(self, captured, args):
        self.external_inner_xml = args.external_inner_xml
        self.inner_xml = []
        self.body_formatted = u""
        self.output = u""
        self.write_closed = False
        # Analyze initial xml part
        try:
            raw_head, self.raw_body = captured.split("\r\n\r\n")
        except ValueError:
            raw_head = ""
            self.raw_body = captured
        # Get encoding
        search = re.search(r'.*charset="(.*)"', raw_head)
        try:
            self.encoding = search.group(1)
        except AttributeError:
            self.encoding = "utf-8"

    def add_content(self, captured):
        """ Adds content to the main UPnP message """
        self.raw_body += captured

    def finalize_content(self):
        """ Finalize the additons """
        self.write_closed = True
        body = self.raw_body.decode(self.encoding)
        self._init_xml(body)
        self._form_output()

    def _init_xml(self, body):
        """ Parse the present body as xml """
        tree = etree.fromstring(body.encode(self.encoding), PARSER)
        # Extract and replace inner DIDL xml in tags
        for text in tree.xpath('.//text()[contains(., "DIDL")]'):
            item = text.getparent()
            didl_tree = etree.fromstring(item.text)
            if self.external_inner_xml:
                item.text = "DIDL_REPLACEMENT_{0}".format(len(self.inner_xml))
                self.inner_xml.append(didl_tree)
            else:
                item.text = None
                item.append(didl_tree)

        # Extract and replace inner DIDL xml in properties in inner xml
        for inner_tree in self.inner_xml:
            for item in inner_tree.xpath('//*[contains(@val, "DIDL")]'):
                if self.external_inner_xml:
                    didl_tree = etree.fromstring(item.attrib["val"])
                    item.attrib["val"] = "DIDL_REPLACEMENT_{0}".format(
                        len(self.inner_xml)
                    )
                    self.inner_xml.append(didl_tree)

        self.body_formatted = etree.tostring(tree, pretty_print=True).decode(
            self.encoding
        )
        # print tree
        # print repr(self.body_formatted)
        # sys.exit(1)

    def _form_output(self):
        """ Form the output """
        self.output = u""
        if self.external_inner_xml:
            self.output += u"<Dummy_tag_to_create_valid_xml_on_external_inner" "_xml>\n"
        self.output += u"<!-- BODY -->\n{0}".format(self.body_formatted)

        if self.external_inner_xml:
            for number, didl in enumerate(self.inner_xml):
                self.output += u"\n<!-- DIDL_{0} -->\n{1}".format(
                    number, etree.tostring(didl, pretty_print=True)
                )
            self.output += u"</Dummy_tag_to_create_valid_xml_on_external_" "inner_xml>"


def __build_option_parser():
    """ Build the option parser for this script """
    description = """
    Tool to analyze Wireshark dumps of Sonos traffic.

    The files that are input to this script must be in the
    "Wireshark/tcpdump/...-libpcap" format, which can be exported from
    Wireshark.

    To use the open in browser function, a configuration file must be
    written. It should be in the same directory as this script and have the
    name "analyse_ws.ini". An example of such a file is given below ({0}
    indicates the file):
    [General]
    browser_command: epiphany {0}

    The browser command should be any command that opens a new tab in
    the program you wish to read the Wireshark dumps in.

    Separating Sonos traffic out from the rest of the network traffic is
    tricky. Therefore, it will in all likelyhood increase the succes of
    this tool, if the traffic is filtered in Wireshark to only show
    traffic to and from the Sonos unit. Still, if the analysis fails,
    then use the debug mode. This will show you the analysis of the
    traffic packet by packet and give you packet numbers so you can find
    and analyze problematic packets in Wireshark.
    """
    description = textwrap.dedent(description).strip()

    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "file_", metavar="FILE", type=str, nargs=1, help="the file to analyze"
    )
    parser.add_argument(
        "-o", "--output-prefix", type=str, help="the output filename prefix to use"
    )
    parser.add_argument(
        "-f",
        "--to-file",
        action="store_const",
        const=True,
        help="output xml to files",
        default=False,
    )
    parser.add_argument(
        "-d",
        "--debug-analysis",
        action="store_const",
        const=True,
        help="writes debug information to file.debug",
        default=False,
    )
    parser.add_argument(
        "-m",
        "--disable-color",
        action="store_const",
        const=False,
        help="disable color in interactive mode",
        default=COLOR,
        dest="color",
    )
    parser.add_argument(
        "-c",
        "--enable-color",
        action="store_const",
        const=True,
        help="disable color in interactive mode",
        default=COLOR,
        dest="color",
    )
    parser.add_argument(
        "-b",
        "--to-browser",
        action="store_const",
        const=True,
        help="output xml to browser, implies --to-file",
        default=False,
    )
    parser.add_argument(
        "-e",
        "--external-inner-xml",
        action="store_const",
        const=True,
        help="show the internal separately "
        "encoded xml externally instead of re-integrating it",
        default=False,
    )
    return parser


def getch():
    """ Read a single character non-echoed and return it. Recipe from:
    http://code.activestate.com/recipes/
    134892-getch-like-unbuffered-character-reading-from-stdin/
    """
    filedescriptor = sys.stdin.fileno()
    old_settings = termios.tcgetattr(filedescriptor)
    if PLATFORM == "win32":
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
        print("IOError raised while reading file. Exiting!")
        sys.exit(3)

    # Start the chosen mode
    if args.to_file or args.to_browser:
        analyze_ws.to_file_mode()
        if args.to_browser:
            analyze_ws.to_browser_mode()
    else:
        analyze_ws.interactive_mode()


if __name__ == "__main__":
    main()
