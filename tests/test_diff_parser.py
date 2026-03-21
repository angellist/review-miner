"""Tests for bot.diff_parser."""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import diff_parser


@pytest.fixture
def bot_config(tmp_path, monkeypatch):
    """Set up config with bot section."""
    config = {
        "repos": [],
        "bot": {
            "max_comments": 10,
            "max_diff_bytes": 1000,
            "skip_patterns": ["*.lock", "*.generated.*", "*.snap", "vendor/*"],
        },
    }
    import utils
    utils._config = config
    return config


class TestShouldSkipFile:
    def test_skip_lock_files(self, bot_config):
        assert diff_parser.should_skip_file("package-lock.json") is False  # doesn't match *.lock
        assert diff_parser.should_skip_file("yarn.lock") is True
        assert diff_parser.should_skip_file("Gemfile.lock") is True

    def test_skip_generated(self, bot_config):
        assert diff_parser.should_skip_file("types.generated.ts") is True
        assert diff_parser.should_skip_file("schema.generated.graphql") is True

    def test_skip_snapshots(self, bot_config):
        assert diff_parser.should_skip_file("Button.test.snap") is True

    def test_skip_vendor(self, bot_config):
        assert diff_parser.should_skip_file("vendor/bundle/gems/foo.rb") is True

    def test_normal_files_pass(self, bot_config):
        assert diff_parser.should_skip_file("app/models/user.rb") is False
        assert diff_parser.should_skip_file("client/src/App.tsx") is False

    def test_default_patterns_without_config(self, monkeypatch):
        """When no bot config exists, use defaults."""
        import utils
        utils._config = {"repos": []}
        assert diff_parser.should_skip_file("yarn.lock") is True


class TestParsePrFiles:
    def test_filters_skipped_files(self, bot_config):
        files = [
            {"filename": "app/models/user.rb", "status": "modified", "patch": "+code"},
            {"filename": "yarn.lock", "status": "modified", "patch": "+lock"},
            {"filename": "schema.generated.ts", "status": "added", "patch": "+gen"},
        ]
        result = diff_parser.parse_pr_files(files)
        assert len(result) == 1
        assert result[0]["filename"] == "app/models/user.rb"

    def test_filters_removed_files(self, bot_config):
        files = [
            {"filename": "app/old.rb", "status": "removed", "patch": "-old code"},
            {"filename": "app/new.rb", "status": "added", "patch": "+new code"},
        ]
        result = diff_parser.parse_pr_files(files)
        assert len(result) == 1
        assert result[0]["filename"] == "app/new.rb"

    def test_filters_empty_filename(self, bot_config):
        files = [{"filename": "", "status": "modified"}]
        assert diff_parser.parse_pr_files(files) == []

    def test_filters_unsafe_paths(self, bot_config):
        files = [
            {"filename": "app/../etc/passwd", "status": "modified", "patch": "+bad"},
            {"filename": "app/safe.rb", "status": "modified", "patch": "+good"},
        ]
        result = diff_parser.parse_pr_files(files)
        assert len(result) == 1
        assert result[0]["filename"] == "app/safe.rb"


class TestBuildDiffText:
    def test_builds_formatted_diff(self, bot_config):
        files = [
            {"filename": "app/user.rb", "status": "modified", "patch": "+  def name\n+    @name\n+  end"},
        ]
        text = diff_parser.build_diff_text(files)
        assert "## app/user.rb (modified)" in text
        assert "```diff" in text
        assert "+  def name" in text

    def test_truncates_large_files(self, bot_config):
        large_patch = "+" + "x" * 2000
        files = [
            {"filename": "small.rb", "status": "modified", "patch": "+small"},
            {"filename": "large.rb", "status": "modified", "patch": large_patch},
        ]
        text = diff_parser.build_diff_text(files, max_bytes=500)
        assert "small.rb" in text
        # large file should be truncated or excluded
        assert len(text.encode("utf-8")) <= 600  # some overhead tolerance

    def test_skips_files_without_patch(self, bot_config):
        files = [
            {"filename": "binary.png", "status": "modified"},
            {"filename": "app/user.rb", "status": "modified", "patch": "+code"},
        ]
        text = diff_parser.build_diff_text(files)
        assert "binary.png" not in text
        assert "app/user.rb" in text

    def test_empty_files(self, bot_config):
        assert diff_parser.build_diff_text([]) == ""


class TestCheckPrSize:
    def test_ok_pr(self, bot_config):
        files = [{"changes": 50} for _ in range(10)]
        assert diff_parser.check_pr_size(files) is None

    def test_too_many_files(self, bot_config):
        files = [{"changes": 1} for _ in range(201)]
        result = diff_parser.check_pr_size(files)
        assert result is not None
        assert "201 files" in result

    def test_too_many_changes(self, bot_config):
        files = [{"changes": 5001} for _ in range(3)]
        result = diff_parser.check_pr_size(files)
        assert result is not None
        assert "Too large" in result
