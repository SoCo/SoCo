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

See dev_tools/README.md for the steps, prompts and troubleshooting.
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

INIT_FILE = "soco/__init__.py"
INDEX_FILE = "doc/releases/index.rst"
RELEASES_DIR = "doc/releases"
WORKFLOW_FILE = ".github/workflows/soco-check-jobs.yaml"
PYPI_URL = "https://pypi.org/pypi/soco/{}/json"
GITHUB_REPO = "SoCo/SoCo"
MILESTONES_API = f"repos/{GITHUB_REPO}/milestones"
ORIGIN_RE = re.compile(r"github\.com[:/]SoCo/SoCo(\.git)?/?$")


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
            raise ReleaseError(f"'{shlex.join(args)}' failed:\n{result.stderr.strip()}")
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

    def local_tag_commit(self, tag):
        """Return the commit a local tag points at, or None if there is none."""
        if not self.local_tag_exists(tag):
            return None
        return self.shell.query("git", "rev-parse", f"{tag}^{{commit}}")

    def find_commit(self, ref, subject):
        """Return the newest commit on ref whose subject is exactly subject."""
        sha = self.shell.query("git", "rev-list", "-1", f"--grep=^{subject}$", ref)
        if not sha:
            raise ReleaseError(f"No commit '{subject}' on {ref}")
        return sha

    def origin_url(self):
        """Return the URL of the origin remote."""
        return self.shell.query("git", "remote", "get-url", "origin")

    def unpushed(self, branch):
        """Return 'sha subject' lines for commits on HEAD not on origin/branch."""
        return self.shell.query(
            "git", "log", "--oneline", f"origin/{branch}..HEAD"
        ).splitlines()

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
        except OSError as exc:
            raise ReleaseError(f"Cannot reach PyPI: {exc}") from exc

    def github_release_exists(self, tag):
        """Return whether a GitHub release exists for a tag."""
        return self.shell.ok("gh", "release", "view", tag, "-R", GITHUB_REPO)

    def milestone(self, title):
        """Return the GitHub milestone named title or vtitle, or None."""
        milestones = json.loads(
            self.shell.query("gh", "api", f"{MILESTONES_API}?state=all&per_page=100")
        )
        for milestone in milestones:
            if milestone["title"] in (title, f"v{title}"):
                return milestone
        return None


AUTO = "auto"  # runs without asking
CONFIRM = "confirm"  # irreversible: asks y/n/q first
MANUAL = "manual"  # waits for the maintainer


class Step:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """One release step.

    ``is_done()`` checks the real state of the repository and remotes, so
    re-running the script skips steps that are already done. For a manual
    step, ``run`` prepares the step and ``ready()`` (if given) must be true
    before the release continues.
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        title,
        kind,
        is_done,
        *,
        run=None,
        commands=(),
        ready=None,
        hint="",
        requires=(),
        preview=None,
    ):
        self.title = title
        self.kind = kind
        self.is_done = is_done
        self.run = run
        self.commands = list(commands)
        self.ready = ready
        self.hint = hint
        self.requires = tuple(requires)
        self.preview = preview


class Runner:
    """Runs release steps in order, skipping those already done."""

    def __init__(self, steps, dry_run=False, ask=None, say=print):
        self.steps = steps
        self.dry_run = dry_run
        self.ask = ask or input
        self.say = say
        self.skipped = []

    def _ask(self, prompt):
        try:
            return self.ask(prompt).strip().lower()
        except EOFError as exc:
            raise Quit() from exc

    def _show_commands(self, step):
        for command in step.commands:
            self.say(f"      $ {command}")

    def run(self):
        """Run the steps; return the titles of any the maintainer skipped."""
        total = len(self.steps)
        for number, step in enumerate(self.steps, 1):
            label = f"[{number}/{total}] {step.title}"
            if step.is_done():
                self.say(f"{label}: done")
                continue
            if self.dry_run:
                self.say(f"{label}: {'manual' if step.kind == MANUAL else 'would run'}")
                self._show_commands(step)
                continue
            self.say(label)
            for required in step.requires:
                if not required.is_done():
                    raise ReleaseError(
                        f"'{step.title}' needs '{required.title}', which is not done"
                    )
            if step.kind == CONFIRM:
                self._confirm_and_run(step)
            elif step.kind == AUTO:
                step.run()
            else:
                self._wait_for_manual(step)
        return self.skipped

    def _confirm_and_run(self, step):
        self._show_commands(step)
        if step.preview:
            for line in step.preview():
                self.say(f"      {line}")
        while True:
            answer = self._ask("  Run this step? [y/n/q] ")
            if answer == "y":
                step.run()
                return
            if answer == "n":
                self.say("  Skipped.")
                self.skipped.append(step.title)
                return
            if answer == "q":
                raise Quit()

    def _wait_for_manual(self, step):
        if step.run:
            step.run()
        if step.hint:
            self.say(f"  {step.hint}")
        while True:
            if self._ask("  Press Enter when done (q to quit) ") == "q":
                raise Quit()
            if step.ready is None or step.ready():
                return
            self.say(f"  Not done yet. {step.hint}")


def unpushed_preview(repo, branch):
    """Return lines listing the commits a push of branch would publish."""
    return ["Commits to push:", *repo.unpushed(branch)]


def publish_steps(repo, version, after, branch, subject):
    """Steps shared by both flows: tag, build, upload, GitHub release.

    The tag goes on the commit on origin/branch whose subject is
    ``subject`` (the release or version bump commit), never on whatever
    HEAD happens to be, and the build is made from a clean checkout of
    the tag.
    """
    tag = f"v{version}"
    dist = [f"dist/soco-{version}.tar.gz", f"dist/soco-{version}-py3-none-any.whl"]

    def release_commit():
        return repo.find_commit(f"origin/{branch}", subject)

    def tag_and_push():
        sha = release_commit()
        existing = repo.local_tag_commit(tag)
        if existing is None:
            repo.shell.run("git", "tag", "-a", tag, "-m", f"Version {version}", sha)
        elif existing != sha:
            raise ReleaseError(
                f"Local tag {tag} points at {existing[:12]}, not the release "
                f"commit {sha[:12]}; delete it with 'git tag -d {tag}'"
            )
        repo.shell.run("git", "push", "origin", f"refs/tags/{tag}")

    tag_step = Step(
        f"Tag {tag} and push the tag",
        CONFIRM,
        lambda: repo.remote_tag_exists(tag),
        run=tag_and_push,
        commands=[
            shlex.join(("git", "tag", "-a", tag, "-m", f"Version {version}"))
            + f" <'{subject}' commit on origin/{branch}>",
            f"git push origin refs/tags/{tag}",
        ],
        preview=lambda: [f"Release commit: {release_commit()} {subject}"],
        requires=(after,),
    )

    def build():
        shutil.rmtree(repo.path("dist"), ignore_errors=True)
        scratch = tempfile.mkdtemp(prefix="soco-release-")
        checkout = os.path.join(scratch, "src")
        repo.shell.run("git", "worktree", "add", "--detach", checkout, tag)
        try:
            repo.shell.run(
                sys.executable, "-m", "build", "--outdir", repo.path("dist"), checkout
            )
        finally:
            repo.shell.run("git", "worktree", "remove", "--force", checkout)
            shutil.rmtree(scratch, ignore_errors=True)

    # Always rebuild unless the release is already on PyPI: files left in
    # dist/ may not have been built from the tag.
    build_step = Step(
        f"Build the distributions from a clean checkout of {tag}",
        AUTO,
        lambda: repo.on_pypi(version),
        run=build,
        requires=(tag_step,),
    )
    upload_args = (
        sys.executable,
        "-m",
        "twine",
        "upload",
        "--repository",
        "pypi",
        *[repo.path(name) for name in dist],
    )
    upload = Step(
        f"Upload soco {version} to PyPI",
        CONFIRM,
        lambda: repo.on_pypi(version),
        run=lambda: repo.shell.run(*upload_args),
        commands=[shlex.join(upload_args)],
        requires=(tag_step,),
    )
    gh_args = (
        "gh",
        "release",
        "create",
        tag,
        "--title",
        f"SoCo {tag} Release Notes",
        "--generate-notes",
        "--verify-tag",
        "-R",
        GITHUB_REPO,
    )
    github_release = Step(
        f"Create the GitHub release for {tag}",
        CONFIRM,
        lambda: repo.github_release_exists(tag),
        run=lambda: repo.shell.run(*gh_args),
        commands=[shlex.join(gh_args)],
        requires=(tag_step,),
    )
    return [tag_step, build_step, upload, github_release]


def main_release_steps(repo, version):  # pylint: disable=too-many-locals
    """Steps for a main release X.Y.0 from master."""
    major, minor, _ = parse_version(version)
    tag = f"v{version}"
    next_minor = f"{major}.{minor + 1}.0"
    next_dev = next_dev_version(version)
    old_branch = previous_fixes_branch(version)
    new_branch = fixes_branch(version)
    notes_file = f"{RELEASES_DIR}/{version}.rst"
    push_args = ("git", "push", "origin", "master")

    def released():
        return repo.remote_tag_exists(tag) or repo.committed_version("HEAD") == version

    create_args = ("gh", "api", MILESTONES_API, "-f", f"title=v{next_minor}")
    create_milestone = Step(
        f"Create milestone v{next_minor}",
        CONFIRM,
        lambda: repo.milestone(next_minor) is not None,
        run=lambda: repo.shell.run(*create_args),
        commands=[shlex.join(create_args)],
    )

    def show_milestone():
        milestone = repo.milestone(version)
        if milestone is None:
            print(f"  There is no {version} milestone.")
            return
        print(
            f"  Milestone {milestone['title']}: {milestone['open_issues']} open, "
            f"{milestone['closed_issues']} closed issues"
        )
        print(f"  {milestone['html_url']}")

    review = Step(
        f"Review the {version} milestone",
        MANUAL,
        released,
        run=show_milestone,
        hint=f"Move unfinished issues to v{next_minor} or later.",
    )

    def notes_ready():
        return (
            repo.exists(notes_file)
            and repo.read(notes_file) != release_notes_template(version)
            and version in index_entries(repo.read(INDEX_FILE))
        )

    def prepare_notes():
        if not repo.exists(notes_file):
            repo.write(notes_file, release_notes_template(version))
            print(f"  Created {notes_file} from the template.")
        index = repo.read(INDEX_FILE)
        updated = add_release_to_index(index, version)
        if updated != index:
            repo.write(INDEX_FILE, updated)
            print(f"  Added {version} to {INDEX_FILE}.")

    notes = Step(
        f"Write the release notes in {notes_file}",
        MANUAL,
        notes_ready,
        run=prepare_notes,
        ready=notes_ready,
        hint=f"Edit {notes_file}; it must differ from the template.",
    )

    def commit_release():
        repo.write(INIT_FILE, set_version(repo.read(INIT_FILE), version))
        repo.shell.run("git", "add", INIT_FILE, INDEX_FILE, notes_file)
        repo.shell.run("git", "commit", "-m", f"Release {tag}")

    commit = Step(
        f"Set version {version} and commit",
        AUTO,
        released,
        run=commit_release,
        requires=(notes,),
    )
    push = Step(
        "Push master",
        CONFIRM,
        lambda: repo.remote_tag_exists(tag)
        or repo.committed_version("origin/master") == version,
        run=lambda: repo.shell.run(*push_args),
        commands=[shlex.join(push_args)],
        preview=lambda: unpushed_preview(repo, "master"),
        requires=(commit,),
    )
    tag_step, build, upload, github_release = publish_steps(
        repo, version, push, "master", f"Release {tag}"
    )

    def milestone_closed():
        milestone = repo.milestone(version)
        return milestone is None or milestone["state"] == "closed"

    def close_milestone():
        number = repo.milestone(version)["number"]
        repo.shell.run(
            "gh",
            "api",
            "--method",
            "PATCH",
            f"{MILESTONES_API}/{number}",
            "-f",
            "state=closed",
        )

    close = Step(
        f"Close the {version} milestone",
        CONFIRM,
        milestone_closed,
        run=close_milestone,
        commands=[f"gh api --method PATCH {MILESTONES_API}/<number> -f state=closed"],
        requires=(github_release,),
    )

    def create_branch():
        if not repo.local_branch_exists(new_branch):
            repo.shell.run("git", "branch", new_branch, tag)
        repo.shell.run("git", "push", "--set-upstream", "origin", new_branch)

    branch = Step(
        f"Create and push {new_branch}",
        CONFIRM,
        lambda: repo.remote_branch_exists(new_branch),
        run=create_branch,
        commands=[
            f"git branch {new_branch} {tag}",
            f"git push --set-upstream origin {new_branch}",
        ],
        requires=(tag_step,),
    )

    def start_next():
        workflow = repo.read(WORKFLOW_FILE)
        repo.write(
            WORKFLOW_FILE, replace_fixes_branch(workflow, old_branch, new_branch)
        )
        repo.write(INIT_FILE, set_version(repo.read(INIT_FILE), next_dev))
        repo.shell.run("git", "add", WORKFLOW_FILE, INIT_FILE)
        repo.shell.run("git", "commit", "-m", f"Start {major}.{minor + 1} development")

    start = Step(
        f"Set version {next_dev}, test {new_branch} in CI, and commit",
        AUTO,
        lambda: repo.committed_version("HEAD") == next_dev,
        run=start_next,
        requires=(branch,),
    )
    push_next = Step(
        "Push master",
        CONFIRM,
        lambda: repo.committed_version("origin/master") == next_dev,
        run=lambda: repo.shell.run(*push_args),
        commands=[shlex.join(push_args)],
        preview=lambda: unpushed_preview(repo, "master"),
        requires=(start,),
    )
    return [
        create_milestone,
        review,
        notes,
        commit,
        push,
        tag_step,
        build,
        upload,
        github_release,
        close,
        branch,
        start,
        push_next,
    ]


def fix_release_steps(repo, version):
    """Steps for a fix release X.Y.N from the X.Y fixes branch."""
    tag = f"v{version}"
    branch = fixes_branch(version)
    push_args = ("git", "push", "origin", branch)

    def bumped():
        return repo.remote_tag_exists(tag) or repo.committed_version("HEAD") == version

    def show_candidates():
        output = repo.shell.query("git", "cherry", "-v", "HEAD", "origin/master")
        candidates = [line[2:] for line in output.splitlines() if line.startswith("+ ")]
        print(
            f"  {len(candidates)} commit(s) on master have no equivalent on {branch}:"
        )
        for line in candidates:
            print(f"    {line}")

    cherry = Step(
        "Cherry-pick fixes from master",
        MANUAL,
        bumped,
        run=show_candidates,
        ready=lambda: not repo.changed_tracked_files(),
        hint="Cherry-pick each fix with 'git cherry-pick <sha>'; "
        "the working tree must be clean to continue.",
    )

    def bump():
        repo.write(INIT_FILE, set_version(repo.read(INIT_FILE), version))
        repo.shell.run("git", "add", INIT_FILE)
        repo.shell.run("git", "commit", "-m", f"Bump version to {tag}")

    bump_step = Step(f"Set version {version} and commit", AUTO, bumped, run=bump)
    push = Step(
        f"Push {branch}",
        CONFIRM,
        lambda: repo.remote_tag_exists(tag)
        or repo.committed_version(f"origin/{branch}") == version,
        run=lambda: repo.shell.run(*push_args),
        commands=[shlex.join(push_args)],
        preview=lambda: unpushed_preview(repo, branch),
        requires=(bump_step,),
    )
    publish = publish_steps(repo, version, push, branch, f"Bump version to {tag}")
    return [cherry, bump_step, push, *publish]


def preflight(repo, branch, check_index):
    """Return a list of problems that should stop the release."""
    problems = []
    origin = repo.origin_url()
    if not ORIGIN_RE.search(origin):
        problems.append(f"origin is {origin}, not {GITHUB_REPO} on GitHub")
    own_files = {INIT_FILE, INDEX_FILE, WORKFLOW_FILE}
    other = [name for name in repo.changed_tracked_files() if name not in own_files]
    if other:
        problems.append("Uncommitted changes to tracked files: " + ", ".join(other))
    current = repo.current_branch()
    if current != branch:
        problems.append(f"On branch {current}: switch to {branch} first")
    else:
        behind = repo.commits_behind(branch)
        if behind:
            problems.append(f"{branch} is {behind} commit(s) behind origin: pull first")
    if not repo.shell.ok("gh", "auth", "status"):
        problems.append(
            "gh is missing or not logged in: brew install gh, then gh auth login"
        )
    for module in ("build", "twine"):
        if not repo.shell.ok(sys.executable, "-m", module, "--version"):
            problems.append(
                f"Python package '{module}' is missing: "
                "pip install -r requirements-dev.txt"
            )
    if check_index:
        missing = missing_index_entries(
            repo.read(INDEX_FILE), os.listdir(repo.path(RELEASES_DIR))
        )
        if missing:
            problems.append(
                f"{INDEX_FILE} lists entries with no file: {', '.join(missing)}"
            )
    return problems


def parse_args(argv):
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        description="Make a SoCo release. Re-run the same command to resume.",
        epilog="Requires git, gh (logged in), and build and twine from "
        "requirements-dev.txt.",
    )
    parser.add_argument(
        "kind",
        choices=("main", "fix"),
        help="'main' for X.Y.0 from master; 'fix' for X.Y.N from vX.Y.fixes",
    )
    parser.add_argument("version", help="the version to release, e.g. 0.32.0")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be done without changing anything",
    )
    return parser.parse_args(argv)


def main(argv=None, repo=None):
    """Run a release; return the exit status."""
    args = parse_args(argv)
    repo = repo or Repo(Shell())
    resume = f"python dev_tools/release.py {args.kind} {args.version}"
    try:
        version = normalise_version(args.version)
        repo.fetch()
        if args.kind == "main":
            branch = "master"
            validate_main(version, repo.working_version())
            steps = main_release_steps(repo, version)
        else:
            branch = fixes_branch(version)
            major, minor, _ = parse_version(version)
            validate_fix(version, repo.tags(f"v{major}.{minor}.*"))
            steps = fix_release_steps(repo, version)
        problems = preflight(repo, branch, check_index=args.kind == "main")
        for problem in problems:
            print(f"Pre-flight: {problem}")
        if problems and not args.dry_run:
            raise ReleaseError("Pre-flight checks failed")
        skipped = Runner(steps, dry_run=args.dry_run).run()
    except Quit:
        print(f"Stopped. Re-run '{resume}' to continue.")
        return 0
    except KeyboardInterrupt:
        print(f"\nStopped. Re-run '{resume}' to continue.")
        return 130
    except ReleaseError as exc:
        print(f"Error: {exc}")
        print(f"Fix the problem, then re-run '{resume}'.")
        return 1
    if args.dry_run:
        print("Dry run: nothing was changed.")
    elif skipped:
        print("Finished, but these steps were skipped: " + "; ".join(skipped))
        print(f"Re-run '{resume}' to do them.")
    else:
        print(f"Release {version} is complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
