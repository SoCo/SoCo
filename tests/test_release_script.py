"""Tests for dev_tools/release.py."""

import importlib.util
import pathlib
import re

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
