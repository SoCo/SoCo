"""Tests for dev_tools/release.py."""

import importlib.util
import pathlib

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
