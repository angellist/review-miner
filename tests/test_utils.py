"""Unit tests for scripts/utils.py."""

from datetime import datetime
from pathlib import Path

import pytest
import yaml

import utils


# --- sanitize_path ---

class TestSanitizePath:
    def test_valid_path(self):
        assert utils.sanitize_path("src/components/Button.tsx") == "src/components/Button.tsx"

    def test_empty_path(self):
        assert utils.sanitize_path("") == ""

    def test_rejects_null_byte(self):
        with pytest.raises(ValueError, match="null byte"):
            utils.sanitize_path("src/\x00evil")

    def test_rejects_traversal(self):
        with pytest.raises(ValueError, match="traversal"):
            utils.sanitize_path("src/../../etc/passwd")

    def test_allows_double_dots_in_filename(self):
        # "..hidden" is not a traversal component — ".." must be a standalone segment
        assert utils.sanitize_path("src/..hidden/file") == "src/..hidden/file"

    def test_rejects_dangerous_characters(self):
        for char in ";|&$`\\!#":
            with pytest.raises(ValueError, match="dangerous characters"):
                utils.sanitize_path(f"src/{char}bad")


# --- validate_safe_name ---

class TestValidateSafeName:
    def test_valid_name(self):
        assert utils.validate_safe_name("my_scope_1", "scope") == "my_scope_1"

    def test_rejects_uppercase(self):
        with pytest.raises(SystemExit):
            utils.validate_safe_name("MyScope", "scope")

    def test_rejects_leading_number(self):
        with pytest.raises(SystemExit):
            utils.validate_safe_name("1scope", "scope")

    def test_rejects_empty(self):
        with pytest.raises(SystemExit):
            utils.validate_safe_name("", "scope")

    def test_rejects_too_long(self):
        with pytest.raises(SystemExit):
            utils.validate_safe_name("a" * 82, "scope")

    def test_accepts_max_length(self):
        name = "a" * 81
        assert utils.validate_safe_name(name, "scope") == name

    def test_rejects_hyphens(self):
        with pytest.raises(SystemExit):
            utils.validate_safe_name("my-scope", "scope")


# --- generate_identifier ---

class TestGenerateIdentifier:
    def test_with_repo(self):
        result = utils.generate_identifier("my_repo", "frontend")
        date_str = datetime.now().strftime("%Y-%m-%d")
        assert result == f"my_repo_frontend_{date_str}"

    def test_without_repo(self):
        result = utils.generate_identifier(None, "backend")
        date_str = datetime.now().strftime("%Y-%m-%d")
        assert result == f"all_backend_{date_str}"


# --- _thread_date ---

class TestThreadDate:
    def test_uses_merged_at(self):
        thread = {"merged_at": "2024-06-15T10:00:00Z"}
        assert utils._thread_date(thread) == datetime(2024, 6, 15, 10, 0, 0)

    def test_falls_back_to_created_at(self):
        thread = {"root": {"created_at": "2024-06-10T08:30:00Z"}}
        assert utils._thread_date(thread) == datetime(2024, 6, 10, 8, 30, 0)

    def test_merged_at_takes_precedence(self):
        thread = {
            "merged_at": "2024-06-15T10:00:00Z",
            "root": {"created_at": "2024-06-10T08:30:00Z"},
        }
        assert utils._thread_date(thread) == datetime(2024, 6, 15, 10, 0, 0)

    def test_returns_min_when_no_dates(self):
        assert utils._thread_date({}) == datetime.min

    def test_handles_iso_offset(self):
        thread = {"merged_at": "2024-06-15T10:00:00+05:00"}
        assert utils._thread_date(thread) == datetime(2024, 6, 15, 10, 0, 0)


# --- load_yaml / save_yaml round-trip ---

class TestYamlIO:
    def test_round_trip(self, tmp_path):
        path = tmp_path / "test.yaml"
        data = {"key": "value", "list": [1, 2, 3]}
        utils.save_yaml(path, data)
        assert utils.load_yaml(path) == data

    def test_load_nonexistent_returns_empty(self, tmp_path):
        assert utils.load_yaml(tmp_path / "missing.yaml") == {}

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "a" / "b" / "test.yaml"
        utils.save_yaml(path, {"x": 1})
        assert utils.load_yaml(path) == {"x": 1}

    def test_load_empty_file_returns_empty(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("")
        assert utils.load_yaml(path) == {}


# --- get_all_scopes ---

class TestGetAllScopes:
    def test_flattens_scopes_across_repos(self, monkeypatch):
        monkeypatch.setattr(utils, "load_config", lambda: {
            "repos": [
                {"name": "repo_a", "scopes": [{"name": "fe", "path_prefix": "src/"}]},
                {"name": "repo_b", "scopes": [{"name": "be", "path_prefix": "api/"}]},
            ]
        })
        scopes = utils.get_all_scopes()
        assert scopes == [
            {"name": "fe", "path_prefix": "src/", "repo": "repo_a"},
            {"name": "be", "path_prefix": "api/", "repo": "repo_b"},
        ]

    def test_empty_repos(self, monkeypatch):
        monkeypatch.setattr(utils, "load_config", lambda: {"repos": []})
        assert utils.get_all_scopes() == []

    def test_repo_without_scopes(self, monkeypatch):
        monkeypatch.setattr(utils, "load_config", lambda: {
            "repos": [{"name": "repo_a"}]
        })
        assert utils.get_all_scopes() == []


# --- _matches_scope ---

class TestMatchesScope:
    def test_matches_when_path_has_prefix(self, monkeypatch):
        monkeypatch.setattr(utils, "load_config", lambda: {
            "repos": [
                {"name": "myrepo", "scopes": [{"name": "frontend", "path_prefix": "src/ui/"}]},
            ]
        })
        thread = {"repo": "myrepo", "root": {"path": "src/ui/Button.tsx"}}
        assert utils._matches_scope(thread, "frontend") is True

    def test_no_match_wrong_prefix(self, monkeypatch):
        monkeypatch.setattr(utils, "load_config", lambda: {
            "repos": [
                {"name": "myrepo", "scopes": [{"name": "frontend", "path_prefix": "src/ui/"}]},
            ]
        })
        thread = {"repo": "myrepo", "root": {"path": "api/routes.py"}}
        assert utils._matches_scope(thread, "frontend") is False

    def test_no_match_unknown_scope(self, monkeypatch):
        monkeypatch.setattr(utils, "load_config", lambda: {
            "repos": [
                {"name": "myrepo", "scopes": [{"name": "frontend", "path_prefix": "src/"}]},
            ]
        })
        thread = {"repo": "myrepo", "root": {"path": "src/index.ts"}}
        assert utils._matches_scope(thread, "nonexistent") is False

    def test_scoped_to_thread_repo(self, monkeypatch):
        monkeypatch.setattr(utils, "load_config", lambda: {
            "repos": [
                {"name": "repo_a", "scopes": [{"name": "fe", "path_prefix": "src/"}]},
                {"name": "repo_b", "scopes": [{"name": "fe", "path_prefix": "lib/"}]},
            ]
        })
        thread = {"repo": "repo_b", "root": {"path": "src/index.ts"}}
        # repo_b's "fe" has prefix "lib/", so "src/index.ts" should NOT match
        assert utils._matches_scope(thread, "fe") is False

    def test_no_repo_field_matches_first_repo(self, monkeypatch):
        """Thread without repo field checks scopes across all repos."""
        monkeypatch.setattr(utils, "load_config", lambda: {
            "repos": [
                {"name": "repo_a", "scopes": [{"name": "fe", "path_prefix": "src/"}]},
                {"name": "repo_b", "scopes": [{"name": "fe", "path_prefix": "lib/"}]},
            ]
        })
        # No "repo" key — should check all repos and match repo_a's prefix
        thread = {"root": {"path": "src/index.ts"}}
        assert utils._matches_scope(thread, "fe") is True


# --- load_threads ---

class TestLoadThreads:
    @pytest.fixture
    def setup_threads(self, tmp_path, monkeypatch):
        """Set up two repos with thread YAML files."""
        repo_a_dir = tmp_path / "repo_a"
        repo_b_dir = tmp_path / "repo_b"
        repo_a_dir.mkdir()
        repo_b_dir.mkdir()

        threads_a = {
            "threads": [
                {"id": 1, "merged_at": "2024-06-10T00:00:00Z", "root": {"path": "src/a.py", "created_at": "2024-06-09T00:00:00Z"}},
                {"id": 2, "merged_at": "2024-06-20T00:00:00Z", "root": {"path": "src/b.py", "created_at": "2024-06-19T00:00:00Z"}},
            ]
        }
        threads_b = {
            "threads": [
                {"id": 3, "merged_at": "2024-06-15T00:00:00Z", "root": {"path": "api/c.py", "created_at": "2024-06-14T00:00:00Z"}},
            ]
        }
        utils.save_yaml(repo_a_dir / "threads.yaml", threads_a)
        utils.save_yaml(repo_b_dir / "threads.yaml", threads_b)

        config = {
            "library_dir": str(tmp_path),
            "repos": [
                {"name": "repo_a", "scopes": [{"name": "frontend", "path_prefix": "src/"}]},
                {"name": "repo_b", "scopes": [{"name": "backend", "path_prefix": "api/"}]},
            ],
        }
        monkeypatch.setattr(utils, "load_config", lambda: config)
        monkeypatch.setattr(utils, "get_data_dir", lambda: tmp_path)
        monkeypatch.setattr(utils, "get_repo_data_dir", lambda name: tmp_path / name)

        return config

    def test_loads_all_repos(self, setup_threads):
        threads = utils.load_threads()
        assert len(threads) == 3
        assert {t["id"] for t in threads} == {1, 2, 3}

    def test_single_repo_filter(self, setup_threads):
        threads = utils.load_threads(repo="repo_a")
        assert len(threads) == 2
        assert all(t["repo"] == "repo_a" for t in threads)

    def test_since_filter(self, setup_threads):
        threads = utils.load_threads(since="2024-06-15")
        assert {t["id"] for t in threads} == {2, 3}

    def test_until_filter(self, setup_threads):
        threads = utils.load_threads(until="2024-06-14")
        assert {t["id"] for t in threads} == {1}

    def test_since_and_until_combined(self, setup_threads):
        threads = utils.load_threads(since="2024-06-12", until="2024-06-18")
        assert {t["id"] for t in threads} == {3}

    def test_scope_filter(self, setup_threads):
        threads = utils.load_threads(scope="frontend")
        ids = {t["id"] for t in threads}
        assert 1 in ids
        assert 2 in ids
        assert 3 not in ids

    def test_scope_all_returns_everything(self, setup_threads):
        threads = utils.load_threads(scope="all")
        assert len(threads) == 3

    def test_adds_repo_field_to_threads(self, setup_threads):
        threads = utils.load_threads(repo="repo_b")
        assert threads[0]["repo"] == "repo_b"
