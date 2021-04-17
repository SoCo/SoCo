#!/usr/bin/env python

import io
import re
import sys

from setuptools import setup
from setuptools.command.test import test as TestCommand


class PyTest(TestCommand):
    # Code from here: https://pytest.org/latest/goodpractises.html

    def finalize_options(self):
        TestCommand.finalize_options(self)
        # We don't run integration tests which need an actual Sonos device
        self.test_args = ["-m", "not integration"]
        self.test_suite = True

    def run_tests(self):
        # Import here, because outside the eggs aren't loaded
        import pytest

        errno = pytest.main(self.test_args)
        sys.exit(errno)


src = open("soco/__init__.py", encoding="utf-8").read()
metadata = dict(re.findall('__([a-z]+)__ = "([^"]+)"', src))
docstrings = re.findall('"""(.*?)"""', src, re.MULTILINE | re.DOTALL)

NAME = "soco"

PACKAGES = (
    "soco",
    "soco.plugins",
    "soco.music_services",
)

TEST_REQUIREMENTS = list(open("requirements-dev.txt"))
AUTHOR_EMAIL = metadata["author"]
VERSION = metadata["version"]
WEBSITE = metadata["website"]
LICENSE = metadata["license"]
DESCRIPTION = docstrings[0]

CLASSIFIERS = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3.5",
    "Programming Language :: Python :: 3.6",
    "Programming Language :: Python :: 3.7",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: Implementation :: CPython",
    "Programming Language :: Python :: Implementation :: PyPy",
    "Topic :: Home Automation",
    "Topic :: Multimedia :: Sound/Audio",
    "Topic :: Multimedia :: Sound/Audio :: Players",
    "Topic :: Software Development :: Libraries :: Python Modules",
]

PYTHON_REQUIRES = ">=3.5"

with open("README.rst", encoding="utf-8") as file:
    LONG_DESCRIPTION = file.read()

# Extract name and e-mail ("Firstname Lastname <mail@example.org>")
AUTHOR, EMAIL = re.match(r"(.*) <(.*)>", AUTHOR_EMAIL).groups()

REQUIREMENTS = list(open("requirements.txt"))

# See https://github.com/SoCo/SoCo/issues/819
EXTRAS_REQUIRE = {"events_asyncio": ["aiohttp"]}

setup(
    name=NAME,
    version=VERSION,
    description=DESCRIPTION,
    author=AUTHOR,
    author_email=EMAIL,
    license=LICENSE,
    url=WEBSITE,
    packages=PACKAGES,
    install_requires=REQUIREMENTS,
    extras_require=EXTRAS_REQUIRE,
    tests_require=TEST_REQUIREMENTS,
    long_description=LONG_DESCRIPTION,
    cmdclass={"test": PyTest},
    classifiers=CLASSIFIERS,
    python_requires=PYTHON_REQUIRES,
)
