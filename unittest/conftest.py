""" py.test hooks

Add the --ip command line option, and skip all tests marked the with
'integration' marker unless the option is included

"""
import pytest


def pytest_addoption(parser):
    """ Add the --ip commandline option """
    parser.addoption(
        '--ip',
        type=str,
        default=None,
        action='store',
        dest='IP',
        help='the IP address for the zone to be used for the integration tests'
        )


def pytest_runtest_setup(item):
    """ Skip tests marked 'integration' unless an ip address is given """
    if "integration" in item.keywords and not item.config.getoption("--ip"):
        pytest.skip("use --ip and an ip address to run integration tests.")
