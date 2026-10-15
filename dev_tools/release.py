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

import json
import os
import re
import shlex
import subprocess
import urllib.error
import urllib.request

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


VERSION_LINE_RE = re.compile(r'^__version__ = "([^"]*)"$', re.MULTILINE)
INDEX_ENTRY_RE = re.compile(r"^   (\d\S*)$", re.MULTILINE)


def read_version(init_text):
    """Return the __version__ value from the text of INIT_FILE."""
    found = VERSION_LINE_RE.findall(init_text)
    if len(found) != 1:
        raise ReleaseError(
            f"Expected one __version__ line in {INIT_FILE}, found {len(found)}"
        )
    return found[0]


def set_version(init_text, version):
    """Return the text of INIT_FILE with __version__ set to version."""
    read_version(init_text)
    return VERSION_LINE_RE.sub(f'__version__ = "{version}"', init_text)


def index_entries(index_text):
    """Return the release entries in the INDEX_FILE toctree, in order."""
    return INDEX_ENTRY_RE.findall(index_text)


def add_release_to_index(index_text, name):
    """Return INDEX_FILE text with name as the first entry (if absent)."""
    if name in index_entries(index_text):
        return index_text
    first = INDEX_ENTRY_RE.search(index_text)
    if first is None:
        raise ReleaseError(f"No release entries found in {INDEX_FILE}")
    return index_text[: first.start()] + f"   {name}\n" + index_text[first.start() :]


def missing_index_entries(index_text, filenames):
    """Return the index entries that have no matching .rst file."""
    return [
        entry for entry in index_entries(index_text) if f"{entry}.rst" not in filenames
    ]


def replace_fixes_branch(workflow_text, old, new):
    """Return WORKFLOW_FILE text with the old fixes branch replaced.

    If the new branch is already there, the text is returned unchanged, so
    the edit can be repeated when a release is resumed.
    """
    old_quoted, new_quoted = f"'{old}'", f"'{new}'"
    if old_quoted in workflow_text:
        return workflow_text.replace(old_quoted, new_quoted)
    if new_quoted in workflow_text:
        return workflow_text
    raise ReleaseError(f"{WORKFLOW_FILE} mentions neither {old} nor {new}")


def release_notes_template(version):
    """Return the skeleton release notes for a main release."""
    major, minor, _ = parse_version(version)
    title = f"SoCo {major}.{minor} Release Notes"
    return (
        f"{title}\n"
        f"{'*' * len(title)}\n"
        "\n"
        f"**SoCo {version}** (Released on YYYY-MM-DD) contains new features as\n"
        "well as internal improvements.\n"
        "\n"
        "Please see the GitHub release page for further details:\n"
        f"https://github.com/SoCo/SoCo/releases/tag/v{version}\n"
    )


class Shell:
    """Runs external commands. query() and ok() only read; run() changes."""

    @staticmethod
    def _capture(args):
        try:
            return subprocess.run(args, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise ReleaseError(f"Command not found: {args[0]}") from exc

    def query(self, *args):
        """Return the output of a read-only command."""
        result = self._capture(args)
        if result.returncode != 0:
            raise ReleaseError(
                f"'{shlex.join(args)}' failed:\n{result.stderr.strip()}"
            )
        return result.stdout.rstrip()

    def ok(self, *args):
        """Return whether a read-only command succeeds."""
        try:
            return self._capture(args).returncode == 0
        except ReleaseError:
            return False

    def run(self, *args):
        """Run a command that changes something, showing its output."""
        print(f"  $ {shlex.join(args)}")
        try:
            result = subprocess.run(args, check=False)
        except FileNotFoundError as exc:
            raise ReleaseError(f"Command not found: {args[0]}") from exc
        if result.returncode != 0:
            raise ReleaseError(
                f"'{shlex.join(args)}' failed with exit code {result.returncode}"
            )


class Repo:
    """The state of the repository, its origin, GitHub and PyPI."""

    def __init__(self, shell, root="."):
        self.shell = shell
        self.root = root

    def path(self, name):
        """Return the path of a file in the repository."""
        return os.path.join(self.root, name)

    def read(self, name):
        """Return the text of a file in the repository."""
        with open(self.path(name), encoding="utf-8", newline="") as file:
            return file.read()

    def write(self, name, text):
        """Replace the text of a file in the repository."""
        with open(self.path(name), "w", encoding="utf-8", newline="") as file:
            file.write(text)

    def exists(self, name):
        """Return whether a file exists in the repository."""
        return os.path.exists(self.path(name))

    def working_version(self):
        """Return __version__ from the working copy of INIT_FILE."""
        return read_version(self.read(INIT_FILE))

    def committed_version(self, ref):
        """Return __version__ from INIT_FILE at a commit, e.g. 'HEAD'."""
        return read_version(self.shell.query("git", "show", f"{ref}:{INIT_FILE}"))

    def current_branch(self):
        """Return the name of the checked-out branch."""
        return self.shell.query("git", "rev-parse", "--abbrev-ref", "HEAD")

    def fetch(self):
        """Fetch branches and tags from origin."""
        self.shell.query("git", "fetch", "origin", "--tags")

    def tags(self, pattern):
        """Return the local tags matching a glob pattern."""
        return self.shell.query("git", "tag", "--list", pattern).split()

    def local_tag_exists(self, tag):
        """Return whether a tag exists locally."""
        return self.shell.ok("git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}")

    def local_branch_exists(self, branch):
        """Return whether a branch exists locally."""
        return self.shell.ok(
            "git", "rev-parse", "-q", "--verify", f"refs/heads/{branch}"
        )

    def remote_tag_exists(self, tag):
        """Return whether a tag exists on origin."""
        return bool(
            self.shell.query("git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}")
        )

    def remote_branch_exists(self, branch):
        """Return whether a branch exists on origin."""
        return bool(
            self.shell.query(
                "git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}"
            )
        )

    def commits_behind(self, branch):
        """Return how many commits HEAD is behind origin/branch."""
        return int(
            self.shell.query("git", "rev-list", "--count", f"HEAD..origin/{branch}")
        )

    def changed_tracked_files(self):
        """Return the tracked files with staged or unstaged changes."""
        status = self.shell.query(
            "git", "status", "--porcelain", "--untracked-files=no"
        )
        return [line[3:].split(" -> ")[-1] for line in status.splitlines()]

    def on_pypi(self, version):
        """Return whether this version of soco is on PyPI."""
        try:
            with urllib.request.urlopen(PYPI_URL.format(version), timeout=15):
                return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise ReleaseError(
                f"PyPI returned HTTP {exc.code} for soco {version}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ReleaseError(f"Cannot reach PyPI: {exc.reason}") from exc

    def github_release_exists(self, tag):
        """Return whether a GitHub release exists for a tag."""
        return self.shell.ok("gh", "release", "view", tag)

    def milestone(self, title):
        """Return the GitHub milestone named title or vtitle, or None."""
        milestones = json.loads(
            self.shell.query(
                "gh", "api", "repos/{owner}/{repo}/milestones?state=all&per_page=100"
            )
        )
        for milestone in milestones:
            if milestone["title"] in (title, f"v{title}"):
                return milestone
        return None
