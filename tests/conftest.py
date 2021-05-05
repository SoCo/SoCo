"""py.test hooks.

Add the --ip command line option, and skip all tests marked the with
'integration' marker unless the option is included
"""
from os import path
import json
import codecs


import pytest

THISDIR = path.dirname(path.abspath(__file__))


def pytest_addoption(parser):
    """Add the --ip commandline option"""
    parser.addoption(
        "--ip",
        type=str,
        default=None,
        action="store",
        dest="IP",
        help="the IP address for the zone to be used for the integration tests",
    )


def pytest_runtest_setup(item):
    """Skip tests marked 'integration' unless an ip address is given."""
    if "integration" in item.keywords and not item.config.getoption("--ip"):
        pytest.skip("use --ip and an ip address to run integration tests.")


class Helpers:
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


class DataLoader:
    """A class that loads test data"""

    def __init__(self, data_sub_dir):
        self.data_dir = path.join(THISDIR, "data", data_sub_dir)

    def load_xml(self, filename):
        """Return XML string loaded from filename under ``self.data_sub_dir``"""
        xml_string = ""
        with codecs.open(path.join(self.data_dir, filename), encoding="utf-8") as file_:
            for line in file_:
                # Allow for indenting the XML source
                xml_string += line.lstrip(" ")
        return xml_string

    def load_json(self, filename):
        """Return parsed data from json file"""
        with open(path.join(self.data_dir, filename)) as file_:
            data = json.load(file_)
        return data

    def load_xml_and_json(self, filename_base):
        """Return XML string and parsed data from ``filename_base``.xml and .json"""
        return (
            self.load_xml(filename_base + ".xml"),
            self.load_json(filename_base + ".json"),
        )
