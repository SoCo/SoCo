#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable-msg=W0142

""" This file is a executable script that executes unit tests for different
parts of soco and provide statistics on the unit test coverage.

Exit codes are as follows:
0  Succesful execution
1  Unknown unit test module requested
2  Missing information argument for the unit tests
3  Unit test module init method raised an exception
"""

import re
import sys
import inspect
import argparse
import unittest
# Our own imports
import soco
import soco_unittest
from soco_unittest import SoCoUnitTestInitError

TERMINAL_COLORS = {'yellow': '1;33',
                   'green': '0;32',
                   'light red': '1;31',
                   'light green': '1;32',
                   'white': '1;37',
                   'red': '0;31'
                   }


def __get_ips_and_names():
    """ Return a list of zone ips and names """
    discovery = soco.SonosDiscovery()
    ips = discovery.get_speaker_ips()
    names = [soco.SoCo(ip).get_speaker_info()['zone_name'] for ip in ips]
    return zip(ips, names)


def __build_option_parser():
    """ Build the option parser for this script """
    description = ('Unit tests for SoCo.\n\nIn order to be able to control '
        'which zone the unit tests are\nperformed on, an IP address must be '
        'provided. For a list of all\npossible IP adresses use the --list '
        'argument.\n\nExamples: python soco_unittest.py --ip 192.168.0.110\n'
        '          python soco_unittest.py --list')
    parser = argparse.ArgumentParser(description=description,
                            formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--ip', type=str, default=None, help='the IP address '
                        'for the zone to be used for the unit tests')
    parser.add_argument('--modules', type=str, default=None, help='the '
                        'modules to run unit test for, can be \'soco\' or '
                        '\'all\'')
    parser.add_argument('--list', action='store_const', const=True,
                        dest='zone_list', help='lists all the available zones'
                        ' and their IP addresses')
    parser.add_argument('--coverage', action='store_const', const=True,
                        help='unit test coverage statistics')
    parser.add_argument('--wiki-format', action='store_const', const=True,
                        help='print coverage in wiki format')
    parser.add_argument('--color', action='store_const', const=True,
                        help='print coverage information in color')
    parser.add_argument('--verbose', type=int, default=1, help='Verbosity '
                        'level for the unit tests (1 or 2). 1 is default.')
    return parser


def __get_modules_to_run(args, unittest_modules):
    """ Form the list of unit test modules to run depending on the commandline
    input
    """
    modules_to_run = []
    if args.modules == 'all' or args.modules is None:
        modules_to_run = unittest_modules.values()
    else:
        for name in args.modules.split(','):
            try:
                modules_to_run.append(unittest_modules[name])
            except KeyError:
                sys.stdout.write('Unit test module "{0}" is not present in '
                    'the unit test definitions. Exiting!\n'.format(name))
                sys.exit(1)
    return modules_to_run


def __coverages(modules_to_run, args):
    """ Outputs coverage statistics """
    sys.stdout.write('\n')
    for current in modules_to_run:
        string = 'Coverage for module: {0}\n\n'.format(current['name'])
        sys.stdout.write(colorize(string, args.color, 'white'))

        # Get all the methods in the class to be tested
        methods = __get_methods_in_class(current['class'])
        # Get all the unittest classes
        classes = {}
        for name, obj in inspect.getmembers(current['unittest_module'],
                                            predicate=inspect.isclass):
            if issubclass(obj, unittest.TestCase):
                classes[name.lower()] = name

        # Print out stats for methods in the class
        if args.wiki_format:
            sys.stdout.write('Method'.ljust(28, ' ') + '| Status\n')
            sys.stdout.write('-' * 27 + ' | ------\n')
        for method in methods.keys():
            __print_coverage_line(methods, method, classes, args)

        # Check is there are unused tests in the unit test module
        for class_ in list(set(classes.keys()) - set(methods.keys())):
            print('WARNING: The unit test {0} is no longer used'\
                .format(classes[class_]))

        percentage = float(len(classes)) / len(methods) * 100
        string = '\n{0:.1f}% methods covered\n'.format(percentage)
        for number, color_ in zip([0, 50, 99],
                                  ['light red', 'yellow', 'light green']):
            if percentage > number:
                color = color_
        sys.stdout.write(colorize(string, args.color, color))


def __get_methods_in_class(class_):
    """ Gets all the names of all the methods in a class """
    methods = {}
    for name, _ in inspect.getmembers(
            class_,
            predicate=inspect.ismethod
            ):
        if name != '__init__':
            # Replaces _ and the class name
            without_classname = re.sub('^_{0}'.format(class_.__name__), '',
                name)
            # Replaces 1 or 2 _ at the beginning of the line with the word
            # 'private'
            with_replacement = re.sub(r'^_{1,2}', 'private', without_classname)
            # Strips all remaining _
            with_replacement = with_replacement.replace('_', '')
            methods[with_replacement] = without_classname
    return methods


def __print_coverage_line(methods, method, classes, args):
    """ Prints out a single line of coverage information """
    if args.wiki_format:
        padding = ' '
        output_string = '{0}|{1}\n'
    else:
        padding = '.'
        output_string = '{0}{1}\n'
    string = methods[method].ljust(28, padding)
    if method in classes.keys():
        outcome = colorize(' COVERED', args.color, 'green')
        sys.stdout.write(output_string.format(string, outcome))
    else:
        outcome = colorize(' NOT COVERED', args.color, 'red')
        sys.stdout.write(output_string.format(string, outcome))


def colorize(string, use_colors=False, color=None):
    """ Colorizes the output"""
    if not use_colors or color is None:
        return string
    tokens = []
    for line in string.split('\n'):
        if len(line) > 0:
            line = '\x1b[{0}m{1}\x1b[0m'.format(TERMINAL_COLORS[color], line)
        tokens.append(line)
    return '\n'.join(tokens)


def __check_argument_present(current):
    """ Check if all the necessary information for this module is present """
    for arg_key, arg_val in current['arguments'].items():
        if arg_val is None:
            sys.stdout.write('Unit tests for the module {0} require '
                'the "{1}" command line argument. Exiting!\n'.format(
                current['name'], arg_key))
            sys.exit(2)


### MAIN SCRIPT
# Parse arguments
PARSER = __build_option_parser()
ARGS = PARSER.parse_args()

# Unit test group definitions
UNITTEST_MODULES = {'soco': {'name': 'SoCo',
                             'unittest_module': soco_unittest,
                             'class': soco.SoCo,
                             'arguments': {'ip': ARGS.ip}
                             }
                    }
MODULES_TO_RUN = __get_modules_to_run(ARGS, UNITTEST_MODULES)

# Switch execution depending on command line input
if ARGS.zone_list:
    # Print out a list of available zones
    PATTERN = '{0: <18}{1}\n'
    NAMES_AND_IPS = __get_ips_and_names()
    sys.stdout.write(PATTERN.format('IP', 'Name'))
    sys.stdout.write('{0}\n'.format('-' * 30))
    for items in NAMES_AND_IPS:
        sys.stdout.write(PATTERN.format(items[0], items[1]))
elif ARGS.coverage:
    # Print out the test coverage for the selected modules
    __coverages(MODULES_TO_RUN, ARGS)
else:
    sys.stdout.write('\n')
    for CURRENT in MODULES_TO_RUN:
        string_ = 'Running unit tests for module: {0}\n'\
                  '\n'.format(CURRENT['name'])
        sys.stdout.write(colorize(string_, ARGS.color, 'white'))

        # Check if all the necessary information for this module is present
        __check_argument_present(CURRENT)

        # Run the unit tests
        MODULE = CURRENT['unittest_module']
        if hasattr(MODULE, 'init'):
            try:
                MODULE.init(**CURRENT['arguments'])
            except SoCoUnitTestInitError as exception:
                string_ = 'The init method in the unit test module returned '\
                    'the following error:\n{0}\n'.format(str(exception))
                sys.stdout.write(colorize(string_, ARGS.color, 'light red'))
                sys.stdout.write('Exiting!\n')
                sys.exit(3)
        SUITE = unittest.TestLoader().loadTestsFromModule(MODULE)
        unittest.TextTestRunner(verbosity=ARGS.verbose).run(SUITE)
