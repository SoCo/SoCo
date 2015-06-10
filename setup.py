#!/usr/bin/env python

import io
import sys
import re
import warnings
from setuptools import setup
from setuptools.command.test import test as TestCommand

class PyTest(TestCommand):
    # Code from here: https://pytest.org/latest/goodpractises.html
    def finalize_options(self):
        TestCommand.finalize_options(self)
        # we don't run integration tests which need an actual Sonos device
        self.test_args = ['-m', 'not integration']
        self.test_suite = True

    def run_tests(self):
        #import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(self.test_args)
        sys.exit(errno)


src = io.open('soco/__init__.py', encoding='utf-8').read()
metadata = dict(re.findall("__([a-z]+)__ = '([^']+)'", src))
docstrings = re.findall('"""(.*?)"""', src, re.MULTILINE | re.DOTALL)

NAME = 'soco'

PACKAGES = (
        'soco',
        'soco.plugins',
)

REQUIREMENTS = list(open('requirements.txt'))
TEST_REQUIREMENTS = list(open('requirements-dev.txt'))
AUTHOR_EMAIL = metadata['author']
VERSION = metadata['version']
WEBSITE = metadata['website']
LICENSE = metadata['license']
DESCRIPTION = docstrings[0]

CLASSIFIERS = [
      'Development Status :: 3 - Alpha',
      'Intended Audience :: Developers',
      'License :: OSI Approved :: MIT License',
      'Operating System :: OS Independent',
      'Programming Language :: Python :: 2',
      'Programming Language :: Python :: 2.6',
      'Programming Language :: Python :: 2.7',
      'Programming Language :: Python :: 3',
      'Programming Language :: Python :: 3.2',
      'Programming Language :: Python :: 3.3',
      'Programming Language :: Python :: 3.4',
      'Programming Language :: Python :: Implementation :: PyPy',
      'Topic :: Home Automation',
      'Topic :: Multimedia :: Sound/Audio',
      'Topic :: Multimedia :: Sound/Audio :: Players',
      'Topic :: Software Development :: Libraries :: Python Modules',
]

with io.open('README.rst', encoding='utf-8') as file:
    LONG_DESCRIPTION = file.read()

# Extract name and e-mail ("Firstname Lastname <mail@example.org>")
AUTHOR, EMAIL = re.match(r'(.*) <(.*)>', AUTHOR_EMAIL).groups()

# For some versions of python (2.6) we need the importlib
# as it is not in the standard install
try:
    import importlib
except ImportError:
    REQUIREMENTS.append('importlib')


setup(name=NAME,
      version=VERSION,
      description=DESCRIPTION,
      author=AUTHOR,
      author_email=EMAIL,
      license=LICENSE,
      url=WEBSITE,
      packages=PACKAGES,
      install_requires=REQUIREMENTS,
      tests_require=TEST_REQUIREMENTS,
      long_description=LONG_DESCRIPTION,
      cmdclass = {'test': PyTest},
      classifiers=CLASSIFIERS,
)
