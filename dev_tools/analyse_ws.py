#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Script to analyse ws dumps """

import argparse
import sys
import re
from scapy.all import rdpcap
import binascii

# rdpcap('sonos_amazon_cloud_player_cap.s0i0.pcap')

class AnalyseWS(object):
    """ Class for analysis of WireShark dump """

    def __init__(self, content, args):
        self.content = self.split(content)
        self.args = args


def __build_option_parser():
    """ Build the option parser for this script """
    description = ('Tool to analyze Wireshark dumps of Sonos traffic')
    parser = argparse.ArgumentParser(description=description,
                                formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('files', metavar='FILES', type=str, nargs='+',
                        help='the files to analyze')
    parser.add_argument('--interactive', action='store_const', const=True,
                        help='start in interactive mode', default=False)
    parser.add_argument('--to-file', action='store_const', const=True,
                        help='start in interactive mode', default=False)
    return parser

if __name__ == '__main__':
    PARSER = __build_option_parser()
    ARGS = PARSER.parse_args()
    for file_ in ARGS.files:
        CONTENT = None
        if file_ == '-':
            print('Reading content from stdin, Ctrl-d to terminate')
            CONTENT = sys.stdin.read()
            # Add to StringIO and open
        else:
            try:
                with open(file_) as FILE:
                    CONTENT = FILE.read()
            except IOError as e:
                print 'The file {0} could not be read:'.format(file_)
                print e
                print 'Skipping it!'
        if CONTENT is not None:
            ANALYSER = AnalyseWS(CONTENT, ARGS)
