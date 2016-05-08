#!/usr/bin/env python
"""Settting up SoCo.

.. highlight:: sh

Installation
------------

To install the latest released version of **SoCo**, use `pip
<http://pip.readthedocs.org/en/stable/>`_.

Make sure you have up-to-date versions of ``pip`` and ``setuptools``::

    $ pip install -U pip setuptools

or, if you are using Windows::

    C:\> python -m pip install -U pip setuptools

then install like this::

    $ pip install soco

This will install **SoCo** and all of its dependencies for you.

It is also possible to install directly from a manually downloaded source
archive. Once the archive is downloaded (eg from `this page
<https://pypi.python.org/pypi/soco/>`_) and extracted, change into the
top-level directory and run::

    $ python setup.py install

You should then be able to run the tests::

    $ python setup.py test


Installing for development
--------------------------

If you want to install an editable version of the latest development code
from the source repository, together with all the dependencies needed for
development, try::

    $ pip install -e git+https://github.com/SoCo/SoCo.git#egg=soco[dev]

or, if you already have a copy of the source files, change into the
directory containing ``setup.py`` and run::

    $ pip install -e .[dev]

You really should do all of this in a `virtual environment <https
://virtualenv.pypa.io/en/latest/>`_.

"""

import io
import re
import sys

from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand


class PyTest(TestCommand):
    # Code from here: https://pytest.org/latest/goodpractises.html

    def finalize_options(self):
        TestCommand.finalize_options(self)
        # we don't run integration tests which need an actual Sonos device
        self.test_args = ['-m', 'not integration']
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(self.test_args)
        sys.exit(errno)


with io.open('soco/__init__.py', encoding='utf-8') as file:
    src = file.read()
    metadata = dict(re.findall("__([a-z]+)__ = '([^']+)'", src))
    docstrings = re.findall('"""(.*?)"""', src, re.MULTILINE | re.DOTALL)

with io.open('README.rst', encoding='utf-8') as file:
    LONG_DESCRIPTION = file.read()

NAME = 'soco'
AUTHOR_EMAIL = metadata['author']
VERSION = metadata['version']
WEBSITE = metadata['website']
LICENSE = metadata['license']
DESCRIPTION = docstrings[0]
# Extract name and e-mail ("Firstname Lastname <mail@example.org>")
AUTHOR, EMAIL = re.match(r'(.*) <(.*)>', AUTHOR_EMAIL).groups()

CLASSIFIERS = [
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: MIT License',
    'Operating System :: OS Independent',
    'Programming Language :: Python :: 2',
    'Programming Language :: Python :: 2.6',
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.3',
    'Programming Language :: Python :: 3.4',
    'Programming Language :: Python :: Implementation :: PyPy',
    'Topic :: Home Automation',
    'Topic :: Multimedia :: Sound/Audio',
    'Topic :: Multimedia :: Sound/Audio :: Players',
    'Topic :: Software Development :: Libraries :: Python Modules',
]

# Dependencies

# All general dependencies should be listed here
REQUIRES = ['requests', 'xmltodict']

# Python 2.6 specific dependencies.  Python 2.6 does not have importlib or
# OrderedDicts, so we need to use backports
PY26_REQUIRES = ['importlib', 'ordereddict']

# Development requirements. mock is a special case, and is handled
# separately later on.
DEV_REQUIRES = [
    'coveralls',
    'flake8',
    'graphviz',
    'pylint >= 1.4',
    'pytest >= 2.5',
    'pytest-cov',
    'setuptools >= 17.1',
    'sphinx >= 1.3.1',
    'wheel >= 0.24',
]

TESTS_REQUIRE = ['pytest >=2.5']
if sys.version_info < (3, 0):
    TESTS_REQUIRE.extend(['mock'])

extras_require = {
    ':python_version=="2.6"': PY26_REQUIRES,
    'dev': DEV_REQUIRES,
    # Mock is only needed for Python 2. Setuptools <17.1 cannot properly handle
    # PEP426 environment markers such as ':python_version < "3.3"' so this
    # is a little awkward. See
    # https://pythonhosted.org/setuptools/history.html
    'dev:python_version == "2.6"': ['mock'],
    'dev:python_version == "2.7"': ['mock'],
}

TEST_REQUIREMENTS = ['pytest >= 2.5', 'mock']

setup(
    # PyPi metadata
    name=NAME,
    version=VERSION,
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    author=AUTHOR,
    author_email=EMAIL,
    license=LICENSE,
    url=WEBSITE,
    classifiers=CLASSIFIERS,
    platforms=['all'],

    # Package data
    packages=find_packages(),
    include_package_data=True,

    # Dependencies
    extras_require=extras_require,
    install_requires=REQUIRES,
    tests_require=TESTS_REQUIRE,

    # other
    cmdclass={'test': PyTest},
    zip_safe=False,
)
