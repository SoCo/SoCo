#!/usr/bin/env python

import setuptools
from setuptools import setup

# The license is set here rather than in pyproject.toml because the SPDX
# license expression needs setuptools >= 77, which needs Python >= 3.9.
if int(setuptools.__version__.split(".")[0]) >= 77:
    setup(license_expression="MIT")
else:
    setup(license="MIT")
