#!/usr/bin/env python
"""Guided release script for SoCo.

Run from the repository root::

    python dev_tools/release.py main 0.32.0 [--dry-run]
    python dev_tools/release.py fix 0.31.6 [--dry-run]

``main`` makes a main release from master, creates the new fixes branch
and starts the next development version. ``fix`` makes a fix release from
the fixes branch. If a release is interrupted, re-run the same command:
steps that are already done are detected and skipped.

Requirements: git; the GitHub CLI ``gh`` (``brew install gh``, then
``gh auth login``); the ``build`` and ``twine`` packages from
requirements-dev.txt; PyPI credentials in ~/.pypirc or the keyring.
"""

import re

INIT_FILE = "soco/__init__.py"
INDEX_FILE = "doc/releases/index.rst"
RELEASES_DIR = "doc/releases"
WORKFLOW_FILE = ".github/workflows/soco-check-jobs.yaml"
PYPI_URL = "https://pypi.org/pypi/soco/{}/json"


class ReleaseError(Exception):
    """A problem that stops the release. Re-running the script resumes."""


class Quit(Exception):
    """The maintainer chose to stop."""


VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(text):
    """Return (major, minor, patch) for 'X.Y.Z'; a leading 'v' is allowed."""
    match = VERSION_RE.match(text.strip())
    if not match:
        raise ReleaseError(f"Invalid version {text!r}: expected X.Y.Z, e.g. 0.32.0")
    return tuple(int(part) for part in match.groups())


def normalise_version(text):
    """Return the version as 'X.Y.Z', without any leading 'v'."""
    return "{}.{}.{}".format(*parse_version(text))


def fixes_branch(version):
    """Return the fixes branch for a version, e.g. 'v0.32.fixes'."""
    major, minor, _ = parse_version(version)
    return f"v{major}.{minor}.fixes"


def previous_fixes_branch(version):
    """Return the fixes branch of the previous minor version."""
    major, minor, _ = parse_version(version)
    return f"v{major}.{minor - 1}.fixes"


def next_dev_version(version):
    """Return the development version that follows a main release."""
    major, minor, _ = parse_version(version)
    return f"{major}.{minor + 1}.0-dev"


def validate_main(version, current):
    """Check a main release version against the version in INIT_FILE.

    ``current`` may also be the released or next development version, so
    that an interrupted release can be resumed.
    """
    _, _, patch = parse_version(version)
    if patch != 0:
        raise ReleaseError(
            f"A main release must be X.Y.0, not {version}; use 'fix' instead"
        )
    if current not in (f"{version}-dev", version, next_dev_version(version)):
        raise ReleaseError(
            f"{INIT_FILE} holds {current!r}; a {version} release "
            f"expects {version}-dev"
        )


def validate_fix(version, tags):
    """Check that a fix release is the next (or current) patch release."""
    major, minor, patch = parse_version(version)
    prefix = f"v{major}.{minor}."
    released = [
        int(tag[len(prefix) :])
        for tag in tags
        if tag.startswith(prefix) and tag[len(prefix) :].isdigit()
    ]
    if not released:
        raise ReleaseError(
            f"No {prefix}* tags found: {major}.{minor} has not been released"
        )
    latest = max(released)
    if patch not in (latest, latest + 1):
        raise ReleaseError(
            f"The next fix release of {major}.{minor} is "
            f"{major}.{minor}.{latest + 1}, not {version}"
        )
