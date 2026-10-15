"""Tests for dev_tools/release.py."""

import importlib.util
import io
import json
import os
import pathlib
import re
import shutil
import sys
import urllib.error

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "soco_release", REPO_ROOT / "dev_tools" / "release.py"
)
release = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release)

ReleaseError = release.ReleaseError

TAGS = ["v0.30.0", "v0.31.0", "v0.31.4", "v0.31.5", "v0.31.5rc1"]


class TestVersions:
    def test_parse_version(self):
        assert release.parse_version("0.32.0") == (0, 32, 0)
        assert release.parse_version("v0.31.6") == (0, 31, 6)

    @pytest.mark.parametrize("bad", ["0.32", "0.32.0-dev", "x.y.z", ""])
    def test_parse_version_rejects(self, bad):
        with pytest.raises(ReleaseError, match="expected X.Y.Z"):
            release.parse_version(bad)

    def test_derived_names(self):
        assert release.normalise_version("v0.32.0") == "0.32.0"
        assert release.fixes_branch("0.32.0") == "v0.32.fixes"
        assert release.previous_fixes_branch("0.32.0") == "v0.31.fixes"
        assert release.next_dev_version("0.32.0") == "0.33.0-dev"

    @pytest.mark.parametrize("current", ["0.32.0-dev", "0.32.0", "0.33.0-dev"])
    def test_validate_main_accepts(self, current):
        release.validate_main("0.32.0", current)

    def test_validate_main_rejects_patch(self):
        with pytest.raises(ReleaseError, match="use 'fix'"):
            release.validate_main("0.32.1", "0.32.0-dev")

    def test_validate_main_rejects_wrong_dev_version(self):
        with pytest.raises(ReleaseError, match="expects 0.33.0-dev"):
            release.validate_main("0.33.0", "0.32.0-dev")

    @pytest.mark.parametrize("version", ["0.31.6", "0.31.5"])
    def test_validate_fix_accepts(self, version):
        release.validate_fix(version, TAGS)

    def test_validate_fix_rejects_gap(self):
        with pytest.raises(ReleaseError, match="is 0.31.6, not 0.31.7"):
            release.validate_fix("0.31.7", TAGS)

    def test_validate_fix_rejects_unreleased_minor(self):
        with pytest.raises(ReleaseError, match="has not been released"):
            release.validate_fix("0.32.1", TAGS)


def real_file(name):
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def current_fixes_branch(workflow_text):
    return re.search(r"'(v\d+\.\d+\.fixes)'", workflow_text).group(1)


INDEX = ".. toctree::\n   :maxdepth: 1\n\n   0.31.0\n   0.30\n"


class TestFileEdits:
    def test_set_version_round_trip_on_real_file(self):
        text = real_file(release.INIT_FILE)
        updated = release.set_version(text, "9.9.9")
        assert release.read_version(updated) == "9.9.9"
        changed = [
            pair
            for pair in zip(text.splitlines(), updated.splitlines())
            if pair[0] != pair[1]
        ]
        assert len(changed) == 1

    @pytest.mark.parametrize("count", [0, 2])
    def test_read_version_needs_exactly_one_line(self, count):
        text = '__version__ = "1.0.0"\n' * count
        with pytest.raises(ReleaseError, match=f"found {count}"):
            release.read_version(text)

    def test_add_release_to_index(self):
        updated = release.add_release_to_index(INDEX, "0.32.0")
        assert release.index_entries(updated) == ["0.32.0", "0.31.0", "0.30"]
        assert release.add_release_to_index(updated, "0.32.0") == updated

    def test_add_release_to_real_index(self):
        updated = release.add_release_to_index(real_file(release.INDEX_FILE), "9.9.0")
        assert release.index_entries(updated)[0] == "9.9.0"

    def test_add_release_to_index_without_entries(self):
        with pytest.raises(ReleaseError, match="No release entries"):
            release.add_release_to_index(".. toctree::\n", "0.32.0")

    def test_missing_index_entries(self):
        assert release.missing_index_entries(INDEX, ["0.31.0.rst", "index.rst"]) == [
            "0.30"
        ]

    def test_replace_fixes_branch_on_real_workflow(self):
        text = real_file(release.WORKFLOW_FILE)
        old = current_fixes_branch(text)
        updated = release.replace_fixes_branch(text, old, "v9.9.fixes")
        assert f"'{old}'" not in updated
        assert updated.count("'v9.9.fixes'") == 2

    def test_replace_fixes_branch_is_idempotent(self):
        text = "branches:\n  - 'v0.32.fixes'\n"
        assert release.replace_fixes_branch(text, "v0.31.fixes", "v0.32.fixes") == text

    def test_replace_fixes_branch_with_neither_branch(self):
        with pytest.raises(ReleaseError, match="neither"):
            release.replace_fixes_branch("branches: []\n", "v0.31.fixes", "v0.32.fixes")

    def test_release_notes_template(self):
        text = release.release_notes_template("0.32.0")
        title, underline = text.splitlines()[:2]
        assert title == "SoCo 0.32 Release Notes"
        assert underline == "*" * len(title)
        assert "**SoCo 0.32.0**" in text
        assert "https://github.com/SoCo/SoCo/releases/tag/v0.32.0" in text


class FakeShell:
    """Answers queries from a dict of canned responses."""

    def __init__(self, responses=None, ok_commands=()):
        self.responses = responses or {}
        self.ok_commands = set(ok_commands)
        self.calls = []

    def query(self, *args):
        self.calls.append(args)
        if args not in self.responses:
            raise AssertionError(f"unexpected query: {args}")
        return self.responses[args]

    def ok(self, *args):
        self.calls.append(args)
        return args in self.ok_commands

    def run(self, *args):
        self.calls.append(args)


MILESTONES = (
    "gh",
    "api",
    "repos/SoCo/SoCo/milestones?state=all&per_page=100",
)


class TestShell:
    def test_query_returns_output(self):
        out = release.Shell().query(sys.executable, "-c", "print(' x ')")
        assert out == " x"

    def test_query_failure_includes_stderr(self):
        script = "import sys; sys.stderr.write('boom'); sys.exit(3)"
        with pytest.raises(ReleaseError, match="boom"):
            release.Shell().query(sys.executable, "-c", script)

    def test_query_missing_command(self):
        with pytest.raises(ReleaseError, match="Command not found"):
            release.Shell().query("no-such-command-soco-release")

    def test_ok(self):
        assert release.Shell().ok(sys.executable, "-c", "pass")
        assert not release.Shell().ok(sys.executable, "-c", "raise SystemExit(1)")

    def test_ok_missing_command(self):
        assert release.Shell().ok("no-such-command-soco-release") is False

    def test_run_failure(self):
        with pytest.raises(ReleaseError, match="exit code 2"):
            release.Shell().run(sys.executable, "-c", "raise SystemExit(2)")


class TestRepo:
    def test_read_write_exists(self, tmp_path):
        repo = release.Repo(FakeShell(), str(tmp_path))
        assert not repo.exists("a/b.txt")
        (tmp_path / "a").mkdir()
        repo.write("a/b.txt", "text\n")
        assert repo.exists("a/b.txt")
        assert repo.read("a/b.txt") == "text\n"

    def test_committed_version(self):
        shell = FakeShell(
            {
                (
                    "git",
                    "show",
                    f"origin/master:{release.INIT_FILE}",
                ): '__version__ = "1.2.0"'
            }
        )
        assert release.Repo(shell).committed_version("origin/master") == "1.2.0"

    def test_remote_tag_exists(self):
        ref = "refs/tags/v1.2.0"
        query = ("git", "ls-remote", "--tags", "origin", ref)
        shell = FakeShell({query: "abc\t" + ref})
        assert release.Repo(shell).remote_tag_exists("v1.2.0")
        shell.responses[query] = ""
        assert not release.Repo(shell).remote_tag_exists("v1.2.0")

    def test_changed_tracked_files(self):
        status = " M soco/__init__.py\nM  doc/releases/index.rst\nR  old.py -> new.py"
        shell = FakeShell(
            {("git", "status", "--porcelain", "--untracked-files=no"): status}
        )
        assert release.Repo(shell).changed_tracked_files() == [
            "soco/__init__.py",
            "doc/releases/index.rst",
            "new.py",
        ]

    def test_milestone_matches_with_or_without_v(self):
        data = [{"title": "v0.31.0", "number": 28, "state": "closed"}]
        repo = release.Repo(FakeShell({MILESTONES: json.dumps(data)}))
        assert repo.milestone("0.31.0")["number"] == 28
        assert repo.milestone("0.32.0") is None

    def test_on_pypi(self, monkeypatch):
        monkeypatch.setattr(
            release.urllib.request, "urlopen", lambda url, timeout: io.BytesIO(b"{}")
        )
        assert release.Repo(FakeShell()).on_pypi("0.31.5")

    def test_on_pypi_not_found(self, monkeypatch):
        def not_found(url, timeout):
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

        monkeypatch.setattr(release.urllib.request, "urlopen", not_found)
        assert not release.Repo(FakeShell()).on_pypi("9.9.9")

    def test_on_pypi_timeout(self, monkeypatch):
        def timeout(url, timeout):
            raise TimeoutError("timed out")

        monkeypatch.setattr(release.urllib.request, "urlopen", timeout)
        with pytest.raises(ReleaseError, match="Cannot reach PyPI"):
            release.Repo(FakeShell()).on_pypi("0.31.5")

    def test_find_commit(self):
        query = ("git", "rev-list", "-1", "--grep=^Release v1.2.0$", "origin/master")
        shell = FakeShell({query: "abc123"})
        assert release.Repo(shell).find_commit("origin/master", "Release v1.2.0") == (
            "abc123"
        )
        shell.responses[query] = ""
        with pytest.raises(ReleaseError, match="No commit 'Release v1.2.0'"):
            release.Repo(shell).find_commit("origin/master", "Release v1.2.0")

    def test_github_release_uses_soco_repo(self):
        view = ("gh", "release", "view", "v1.2.0", "-R", "SoCo/SoCo")
        assert release.Repo(FakeShell(ok_commands=[view])).github_release_exists(
            "v1.2.0"
        )

    def test_on_pypi_unreachable(self, monkeypatch):
        def unreachable(url, timeout):
            raise urllib.error.URLError("no network")

        monkeypatch.setattr(release.urllib.request, "urlopen", unreachable)
        with pytest.raises(ReleaseError, match="Cannot reach PyPI"):
            release.Repo(FakeShell()).on_pypi("0.31.5")


def scripted(answers):
    """Return an ask() that gives each answer in turn; callables are called."""
    remaining = list(answers)

    def ask(prompt):
        assert remaining, f"unexpected prompt: {prompt}"
        answer = remaining.pop(0)
        return answer() if callable(answer) else answer

    return ask


def eof(prompt):
    raise EOFError


def statuses(said):
    return [line.rsplit(": ", 1)[1] for line in said if line.startswith("[")]


class TestRunner:
    @staticmethod
    def run(steps, answers=(), dry_run=False, ask=None):
        said = []
        runner = release.Runner(
            steps, dry_run=dry_run, ask=ask or scripted(answers), say=said.append
        )
        return said, runner.run()

    def test_done_steps_are_skipped(self):
        ran = []
        step = release.Step(
            "a", release.AUTO, lambda: True, run=lambda: ran.append("a")
        )
        said, _ = self.run([step])
        assert ran == []
        assert said == ["[1/1] a: done"]

    def test_auto_step_runs_without_asking(self):
        ran = []
        step = release.Step(
            "a", release.AUTO, lambda: False, run=lambda: ran.append("a")
        )
        self.run([step])
        assert ran == ["a"]

    def test_dry_run_runs_and_asks_nothing(self):
        ran = []
        steps = [
            release.Step(
                "a",
                release.CONFIRM,
                lambda: False,
                run=lambda: ran.append("a"),
                commands=["git push"],
            ),
            release.Step(
                "b", release.MANUAL, lambda: False, run=lambda: ran.append("b")
            ),
        ]
        said, _ = self.run(steps, dry_run=True)
        assert ran == []
        assert said == ["[1/2] a: would run", "      $ git push", "[2/2] b: manual"]

    def test_confirm_yes_runs(self):
        ran = []
        step = release.Step(
            "a", release.CONFIRM, lambda: False, run=lambda: ran.append("a")
        )
        self.run([step], ["y"])
        assert ran == ["a"]

    def test_confirm_no_skips_and_continues(self):
        ran = []
        steps = [
            release.Step(
                "a", release.CONFIRM, lambda: False, run=lambda: ran.append("a")
            ),
            release.Step("b", release.AUTO, lambda: False, run=lambda: ran.append("b")),
        ]
        _, skipped = self.run(steps, ["n"])
        assert ran == ["b"]
        assert skipped == ["a"]

    def test_confirm_asks_again_after_unknown_answer(self):
        ran = []
        step = release.Step(
            "a", release.CONFIRM, lambda: False, run=lambda: ran.append("a")
        )
        self.run([step], ["maybe", "Y"])
        assert ran == ["a"]

    def test_quit(self):
        step = release.Step("a", release.CONFIRM, lambda: False, run=lambda: None)
        with pytest.raises(release.Quit):
            self.run([step], ["q"])

    def test_eof_quits(self):
        step = release.Step("a", release.CONFIRM, lambda: False, run=lambda: None)
        with pytest.raises(release.Quit):
            self.run([step], ask=eof)

    def test_manual_waits_until_ready(self):
        state = {"ready": False}
        prepared = []

        def finish():
            state["ready"] = True
            return ""

        step = release.Step(
            "m",
            release.MANUAL,
            lambda: False,
            run=lambda: prepared.append(1),
            ready=lambda: state["ready"],
            hint="do it",
        )
        said, _ = self.run([step], ["", finish])
        assert prepared == [1]
        assert "  Not done yet. do it" in said

    def test_manual_without_ready_continues_on_enter(self):
        step = release.Step("m", release.MANUAL, lambda: False)
        self.run([step], [""])

    def test_confirm_shows_preview(self):
        step = release.Step(
            "a",
            release.CONFIRM,
            lambda: False,
            run=lambda: None,
            commands=["git push"],
            preview=lambda: ["abc123 Fix a bug"],
        )
        said, _ = self.run([step], ["n"])
        assert said[:3] == ["[1/1] a", "      $ git push", "      abc123 Fix a bug"]

    def test_unmet_requirement_stops(self):
        ran = []
        first = release.Step("first", release.CONFIRM, lambda: False, run=lambda: None)
        second = release.Step(
            "second",
            release.AUTO,
            lambda: False,
            run=lambda: ran.append(2),
            requires=(first,),
        )
        with pytest.raises(ReleaseError, match="'second' needs 'first'"):
            self.run([first, second], ["n"])
        assert ran == []


class SimShell:
    """Stands in for Shell: records commands and applies their effects."""

    def __init__(self):
        self.repo = None
        self.calls = []
        self.runs = []
        self.ok_result = True

    def query(self, *args):
        self.calls.append(args)
        if args[:2] == ("git", "cherry"):
            return "+ abc123 Fix a bug\n- def456 Already picked"
        raise AssertionError(f"unexpected query: {args}")

    def ok(self, *args):
        self.calls.append(args)
        return self.ok_result

    def run(self, *args):
        self.runs.append(args)
        repo = self.repo
        if args[:2] == ("git", "commit"):
            repo.committed["HEAD"] = repo.working_version()
            repo.commits[args[3]] = f"{len(repo.commits) + 1:040x}"
        elif args[:3] == ("git", "tag", "-a"):
            repo.local_tags[args[3]] = args[-1]
        elif args[:4] == ("git", "push", "--set-upstream", "origin"):
            repo.remote_branches.add(args[4])
        elif args[:3] == ("git", "push", "origin") and args[3].startswith("refs/tags/"):
            repo.remote_tags.add(args[3][len("refs/tags/") :])
        elif args[:3] == ("git", "push", "origin"):
            repo.committed[f"origin/{args[3]}"] = repo.committed["HEAD"]
        elif args[1:3] == ("-m", "build"):
            version = repo.working_version()
            os.makedirs(repo.path("dist"), exist_ok=True)
            for name in (f"soco-{version}.tar.gz", f"soco-{version}-py3-none-any.whl"):
                with open(repo.path(f"dist/{name}"), "w", encoding="utf-8"):
                    pass
        elif args[1:3] == ("-m", "twine"):
            repo.pypi.add(repo.working_version())
        elif args[:3] == ("gh", "release", "create"):
            repo.gh_releases.add(args[3])
        elif args[:2] == ("gh", "api"):
            field = args[args.index("-f") + 1]
            if field.startswith("title="):
                repo.add_milestone(field[len("title=") :])
            else:
                number = int(args[args.index("-f") - 1].rsplit("/", 1)[1])
                for milestone in repo.milestones.values():
                    if milestone["number"] == number:
                        milestone["state"] = "closed"


class SimRepo(release.Repo):
    """A Repo whose git/GitHub/PyPI state lives in memory; files are real."""

    def __init__(self, root, branch):
        shell = SimShell()
        super().__init__(shell, str(root))
        shell.repo = self
        self.branch = branch
        version = self.working_version()
        self.committed = {"HEAD": version, f"origin/{branch}": version}
        self.tag_list = []
        self.remote_tags = set()
        self.remote_branches = set()
        self.pypi = set()
        self.gh_releases = set()
        self.milestones = {}
        self.changed = []
        self.behind = 0
        self.commits = {}
        self.local_tags = {}
        self.origin = "git@github.com:SoCo/SoCo.git"
        self.unpushed_commits = []

    def add_milestone(self, title, state="open"):
        self.milestones[title] = {
            "title": title,
            "number": len(self.milestones) + 1,
            "state": state,
            "open_issues": 0,
            "closed_issues": 3,
            "html_url": "https://example.invalid/milestone",
        }

    def fetch(self):
        pass

    def current_branch(self):
        return self.branch

    def committed_version(self, ref):
        return self.committed[ref]

    def tags(self, pattern):
        return list(self.tag_list)

    def local_tag_exists(self, tag):
        return tag in self.local_tags

    def local_tag_commit(self, tag):
        return self.local_tags.get(tag)

    def find_commit(self, ref, subject):
        if subject not in self.commits:
            raise ReleaseError(f"No commit '{subject}' on {ref}")
        return self.commits[subject]

    def origin_url(self):
        return self.origin

    def unpushed(self, branch):
        return list(self.unpushed_commits)

    def local_branch_exists(self, branch):
        return branch in self.remote_branches

    def remote_tag_exists(self, tag):
        return tag in self.remote_tags

    def remote_branch_exists(self, branch):
        return branch in self.remote_branches

    def commits_behind(self, branch):
        return self.behind

    def changed_tracked_files(self):
        return list(self.changed)

    def on_pypi(self, version):
        return version in self.pypi

    def github_release_exists(self, tag):
        return tag in self.gh_releases

    def milestone(self, title):
        for name in (title, f"v{title}"):
            if name in self.milestones:
                return self.milestones[name]
        return None


def copy_repo_files(root):
    for name in (release.INIT_FILE, release.WORKFLOW_FILE):
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / name, dest)
    shutil.copytree(REPO_ROOT / release.RELEASES_DIR, root / release.RELEASES_DIR)


def set_file_version(root, version):
    init = root / release.INIT_FILE
    init.write_text(release.set_version(init.read_text(encoding="utf-8"), version))


def make_main_sim(root, version="5.7.0-dev"):
    """A master checkout at 5.7.0-dev whose CI tests v5.6.fixes."""
    copy_repo_files(root)
    set_file_version(root, version)
    workflow = root / release.WORKFLOW_FILE
    text = workflow.read_text(encoding="utf-8")
    workflow.write_text(
        release.replace_fixes_branch(text, current_fixes_branch(text), "v5.6.fixes")
    )
    return SimRepo(root, "master")


def make_fix_sim(root):
    """A v9.1.fixes checkout at 9.1.4."""
    copy_repo_files(root)
    set_file_version(root, "9.1.4")
    repo = SimRepo(root, "v9.1.fixes")
    repo.tag_list = ["v9.1.3", "v9.1.4"]
    return repo


def write_notes(root, version="5.7.0"):
    (root / release.RELEASES_DIR / f"{version}.rst").write_text("Real notes\n")
    index = root / release.INDEX_FILE
    index.write_text(release.add_release_to_index(index.read_text(), version))


def dry_run_statuses(steps):
    said = []
    release.Runner(steps, dry_run=True, say=said.append).run()
    return statuses(said)


class TestMainFlow:
    def test_fresh_main_release_dry_run(self, tmp_path):
        repo = make_main_sim(tmp_path)
        assert dry_run_statuses(release.main_release_steps(repo, "5.7.0")) == [
            "would run",  # create milestone v5.8.0
            "manual",  # review milestone
            "manual",  # release notes
            "would run",  # commit
            "would run",  # push master: HEAD == origin, but not yet released
            "would run",  # tag
            "would run",  # build
            "would run",  # upload
            "would run",  # GitHub release
            "done",  # close milestone: there is no 5.7.0 milestone
            "would run",  # fixes branch
            "would run",  # start next development
            "would run",  # push master
        ]
        assert repo.shell.runs == []

    def test_full_main_release(self, tmp_path):
        repo = make_main_sim(tmp_path)
        repo.add_milestone("v5.7.0")

        def write_the_notes():
            (tmp_path / release.RELEASES_DIR / "5.7.0.rst").write_text("Notes\n")
            return ""

        answers = ["y", "", write_the_notes, "y", "y", "y", "y", "y", "y", "y"]
        runner = release.Runner(
            release.main_release_steps(repo, "5.7.0"),
            ask=scripted(answers),
            say=lambda line: None,
        )
        assert runner.run() == []

        assert repo.committed["origin/master"] == "5.8.0-dev"
        assert "v5.7.0" in repo.remote_tags
        assert "5.7.0" in repo.pypi
        assert "v5.7.0" in repo.gh_releases
        assert repo.milestones["v5.7.0"]["state"] == "closed"
        assert "v5.8.0" in repo.milestones
        assert "v5.7.fixes" in repo.remote_branches
        workflow = repo.read(release.WORKFLOW_FILE)
        assert workflow.count("'v5.7.fixes'") == 2
        assert "'v5.6.fixes'" not in workflow
        assert release.index_entries(repo.read(release.INDEX_FILE))[0] == "5.7.0"
        assert (
            "git",
            "add",
            release.INIT_FILE,
            release.INDEX_FILE,
            "doc/releases/5.7.0.rst",
        ) in repo.shell.runs
        assert ("git", "commit", "-m", "Release v5.7.0") in repo.shell.runs
        assert ("git", "commit", "-m", "Start 5.8 development") in repo.shell.runs
        release_sha = repo.commits["Release v5.7.0"]
        assert (
            "git",
            "tag",
            "-a",
            "v5.7.0",
            "-m",
            "Version 5.7.0",
            release_sha,
        ) in repo.shell.runs
        worktree_adds = [
            r for r in repo.shell.runs if r[:3] == ("git", "worktree", "add")
        ]
        assert len(worktree_adds) == 1
        assert worktree_adds[0][-1] == "v5.7.0"
        builds = [r for r in repo.shell.runs if r[1:3] == ("-m", "build")]
        assert builds[0][3:5] == ("--outdir", repo.path("dist"))
        assert builds[0][5] == worktree_adds[0][-2]
        assert ("git", "worktree", "remove", "--force", worktree_adds[0][-2]) in (
            repo.shell.runs
        )
        gh_create = [r for r in repo.shell.runs if r[:3] == ("gh", "release", "create")]
        assert gh_create[0][-2:] == ("-R", "SoCo/SoCo")

    def test_stale_local_tag_rejected(self, tmp_path):
        repo = make_main_sim(tmp_path, version="5.7.0")
        write_notes(tmp_path)
        repo.add_milestone("v5.8.0")
        repo.commits["Release v5.7.0"] = "a" * 40
        repo.local_tags["v5.7.0"] = "b" * 40
        runner = release.Runner(
            release.main_release_steps(repo, "5.7.0"),
            ask=scripted(["y"]),
            say=lambda line: None,
        )
        with pytest.raises(ReleaseError, match="points at bbbbbbbbbbbb"):
            runner.run()
        assert "v5.7.0" not in repo.remote_tags

    def test_stale_dist_is_rebuilt(self, tmp_path):
        repo = make_main_sim(tmp_path, version="5.7.0")
        write_notes(tmp_path)
        repo.remote_tags.add("v5.7.0")
        (tmp_path / "dist").mkdir()
        for name in ("soco-5.7.0.tar.gz", "soco-5.7.0-py3-none-any.whl"):
            (tmp_path / "dist" / name).write_text("stale")
        statuses_ = dry_run_statuses(release.main_release_steps(repo, "5.7.0"))
        assert statuses_[6] == "would run"  # build

    def test_push_preview_lists_unpushed_commits(self, tmp_path):
        repo = make_main_sim(tmp_path)
        repo.unpushed_commits = ["abc123 Release v5.7.0", "def456 Stray commit"]
        push = release.main_release_steps(repo, "5.7.0")[4]
        assert push.preview() == [
            "Commits to push:",
            "abc123 Release v5.7.0",
            "def456 Stray commit",
        ]

    def test_resume_after_pypi_upload(self, tmp_path):
        repo = make_main_sim(tmp_path, version="5.7.0")
        write_notes(tmp_path)
        repo.remote_tags.add("v5.7.0")
        repo.pypi.add("5.7.0")
        assert dry_run_statuses(release.main_release_steps(repo, "5.7.0")) == [
            "would run",  # create milestone v5.8.0
            "done",
            "done",
            "done",
            "done",
            "done",
            "done",
            "done",
            "would run",  # GitHub release
            "done",
            "would run",  # fixes branch
            "would run",
            "would run",
        ]

    def test_resume_after_unpushed_dev_bump(self, tmp_path):
        repo = make_main_sim(tmp_path, version="5.8.0-dev")
        workflow = tmp_path / release.WORKFLOW_FILE
        workflow.write_text(workflow.read_text().replace("v5.6.fixes", "v5.7.fixes"))
        write_notes(tmp_path)
        repo.committed["origin/master"] = "5.7.0"
        repo.remote_tags.add("v5.7.0")
        repo.pypi.add("5.7.0")
        repo.gh_releases.add("v5.7.0")
        repo.remote_branches.add("v5.7.fixes")
        repo.add_milestone("v5.8.0")
        runner = release.Runner(
            release.main_release_steps(repo, "5.7.0"),
            ask=scripted(["y"]),
            say=lambda line: None,
        )
        runner.run()
        assert repo.committed["origin/master"] == "5.8.0-dev"


class TestFixFlow:
    def test_full_fix_release(self, tmp_path):
        repo = make_fix_sim(tmp_path)
        runner = release.Runner(
            release.fix_release_steps(repo, "9.1.5"),
            ask=scripted(["", "y", "y", "y", "y"]),
            say=lambda line: None,
        )
        assert runner.run() == []
        assert repo.committed["origin/v9.1.fixes"] == "9.1.5"
        assert "v9.1.5" in repo.remote_tags
        assert "9.1.5" in repo.pypi
        assert "v9.1.5" in repo.gh_releases
        assert ("git", "commit", "-m", "Bump version to v9.1.5") in repo.shell.runs

    def test_cherry_pick_step_waits_for_clean_tree(self, tmp_path):
        repo = make_fix_sim(tmp_path)
        repo.changed = ["soco/core.py"]

        def resolve():
            repo.changed = []
            return ""

        said = []
        steps = release.fix_release_steps(repo, "9.1.5")[:1]
        release.Runner(steps, ask=scripted(["", resolve]), say=said.append).run()
        assert any(line.startswith("  Not done yet.") for line in said)


class TestPreflight:
    def test_origin_must_be_soco(self, tmp_path):
        repo = make_fix_sim(tmp_path)
        repo.origin = "git@github.com:someone/SoCo.git"
        problems = release.preflight(repo, "v9.1.fixes", check_index=False)
        assert problems == [
            "origin is git@github.com:someone/SoCo.git, not SoCo/SoCo on GitHub"
        ]

    def test_https_origin_accepted(self, tmp_path):
        repo = make_fix_sim(tmp_path)
        repo.origin = "https://github.com/SoCo/SoCo"
        assert release.preflight(repo, "v9.1.fixes", check_index=False) == []

    def test_clean(self, tmp_path):
        repo = make_fix_sim(tmp_path)
        assert release.preflight(repo, "v9.1.fixes", check_index=False) == []

    def test_own_files_allowed(self, tmp_path):
        repo = make_fix_sim(tmp_path)
        repo.changed = [release.INIT_FILE, release.INDEX_FILE, release.WORKFLOW_FILE]
        assert release.preflight(repo, "v9.1.fixes", check_index=False) == []

    def test_other_changes_flagged(self, tmp_path):
        repo = make_fix_sim(tmp_path)
        repo.changed = ["soco/core.py"]
        problems = release.preflight(repo, "v9.1.fixes", check_index=False)
        assert len(problems) == 1
        assert "soco/core.py" in problems[0]

    def test_wrong_branch(self, tmp_path):
        repo = make_fix_sim(tmp_path)
        problems = release.preflight(repo, "master", check_index=False)
        assert problems == ["On branch v9.1.fixes: switch to master first"]

    def test_behind_origin(self, tmp_path):
        repo = make_fix_sim(tmp_path)
        repo.behind = 2
        problems = release.preflight(repo, "v9.1.fixes", check_index=False)
        assert problems == ["v9.1.fixes is 2 commit(s) behind origin: pull first"]

    def test_missing_tools(self, tmp_path):
        repo = make_fix_sim(tmp_path)
        repo.shell.ok_result = False
        problems = release.preflight(repo, "v9.1.fixes", check_index=False)
        assert len(problems) == 3
        assert "gh auth login" in problems[0]
        assert "'build'" in problems[1]
        assert "'twine'" in problems[2]

    def test_index_entry_without_file(self, tmp_path):
        repo = make_fix_sim(tmp_path)
        (tmp_path / release.INDEX_FILE).write_text(
            ".. toctree::\n   :maxdepth: 1\n\n   9.9\n"
        )
        problems = release.preflight(repo, "v9.1.fixes", check_index=True)
        assert problems == [f"{release.INDEX_FILE} lists entries with no file: 9.9"]


class TestMain:
    def test_invalid_version(self, tmp_path, capsys):
        assert release.main(["fix", "9.1"], repo=make_fix_sim(tmp_path)) == 1
        out = capsys.readouterr().out
        assert "Invalid version" in out
        assert "re-run 'python dev_tools/release.py fix 9.1'" in out

    def test_preflight_failure_stops(self, tmp_path, capsys):
        repo = make_fix_sim(tmp_path)
        repo.branch = "master"
        assert release.main(["fix", "9.1.5"], repo=repo) == 1
        assert "Pre-flight checks failed" in capsys.readouterr().out
        assert repo.shell.runs == []

    def test_dry_run_reports_preflight_and_lists_steps(self, tmp_path, capsys):
        repo = make_fix_sim(tmp_path)
        repo.branch = "master"
        assert release.main(["fix", "9.1.5", "--dry-run"], repo=repo) == 0
        out = capsys.readouterr().out
        assert "Pre-flight: On branch master" in out
        assert "[7/7] Create the GitHub release for v9.1.5: would run" in out
        assert repo.shell.runs == []

    def test_keyboard_interrupt(self, tmp_path, capsys, monkeypatch):
        def interrupt(self):
            raise KeyboardInterrupt

        monkeypatch.setattr(release.Runner, "run", interrupt)
        assert release.main(["fix", "9.1.5"], repo=make_fix_sim(tmp_path)) == 130
        assert "Stopped. Re-run" in capsys.readouterr().out

    def test_complete_fix_release(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("builtins.input", scripted(["", "y", "y", "y", "y"]))
        assert release.main(["fix", "v9.1.5"], repo=make_fix_sim(tmp_path)) == 0
        assert "Release 9.1.5 is complete." in capsys.readouterr().out
