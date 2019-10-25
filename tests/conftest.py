"""py.test hooks.

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
    """Skip tests marked 'integration' unless an ip address is given."""
    if "integration" in item.keywords and not item.config.getoption("--ip"):
        pytest.skip("use --ip and an ip address to run integration tests.")


class Helpers(object):
    """Test helper functions"""

    @staticmethod
    def compare_xml(element1, element2):
        # print()
        # print(element1.tag, "TAG", element2.tag)
        # print(element1.attrib, element2.attrib)
        if element1.tag != element2.tag:
            return False

        # print(element1.attrib, element2.attrib)
        if element1.attrib != element2.attrib:
            return False

        # print(len(element1), len(element2))
        if len(element1) != len(element2):
            return False

        for subelement1, subelement2 in zip(element1, element2):
            if not Helpers.compare_xml(subelement1, subelement2):
                return False

        return True


@pytest.fixture
def helpers():
    return Helpers
