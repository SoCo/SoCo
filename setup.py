#!/usr/bin/env python

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


# Retain for compatibility with legacy builds or build tool versions.
setup()
