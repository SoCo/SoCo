#!/usr/bin/env python

import sys
import re
import warnings
try:
    from setuptools import setup
    has_setuptools = True
except ImportError:
    from distutils.core import setup
    has_setuptools = False

src = open('soco.py').read()
metadata = dict(re.findall("__([a-z]+)__ = '([^']+)'", src))
docstrings = re.findall('"""([^"]*)"""', src, re.MULTILINE | re.DOTALL)

PACKAGE = 'soco'

MODULES = (
        'soco',
)

REQUIREMENTS = list(open('requirements.txt'))

if has_setuptools:
    OPTIONS = {
        'install_requires': REQUIREMENTS
    }
else:
    if sys.version_info < (2, 6):
        warnings.warn('No setuptools installed. Be sure that you have '
                      'all dependencies installed')
    OPTIONS = {}

AUTHOR_EMAIL = metadata['author']
VERSION = metadata['version']
WEBSITE = metadata['website']
LICENSE = metadata['license']
DESCRIPTION = docstrings[0]

# Extract name and e-mail ("Firstname Lastname <mail@example.org>")
AUTHOR, EMAIL = re.match(r'(.*) <(.*)>', AUTHOR_EMAIL).groups()

setup(name=PACKAGE,
      version=VERSION,
      description=DESCRIPTION,
      author=AUTHOR,
      author_email=EMAIL,
      license=LICENSE,
      url=WEBSITE,
      py_modules=MODULES,
      **OPTIONS
)
