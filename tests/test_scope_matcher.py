"""Tests for bot.scope_matcher."""

import sys
from pathlib import Path

import pytest
import yaml

# Ensure bot/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import scope_matcher


@pytest.fixture
def sample_config(tmp_path, monkeypatch):
    """Create a temporary config and rule sections for testing."""
    config = {
        "repos": [
            {
                "name": "venture",
                "github_repo": "angellist/venture",
                "scopes": [
                    {"name": "backend", "path_prefix": "app/"},
                    {"name": "graphql", "path_prefix": "app/graphql/"},
                    {"name": "frontend", "path_prefix": "client/"},
                ],
            },
            {
                "name": "nova",
                "github_repo": "angellist/nova",
                "scopes": [
                    {"name": "components", "path_prefix": "src/components/"},
                    {"name": "pages", "path_prefix": "src/pages/"},
                ],
            },
        ],
        "sections_output_dir": "rules/sections",
    }

    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    # Create rule section files
    sections_dir = tmp_path / "rules" / "sections"
    sections_dir.mkdir(parents=True)

    (sections_dir / "error_handling.md").write_text(
        "---\nscope: all\n---\n\n# Error Handling\n\n### Rule 1\nContent"
    )
    (sections_dir / "api_design.md").write_text(
        "---\nscope: fullstack\n---\n\n# API Design\n\n### Rule 1\nContent"
    )
    (sections_dir / "react_components.md").write_text(
        "---\nscope: frontend\n---\n\n# React Components\n\n### Rule 1\nContent"
    )
    (sections_dir / "rails_patterns.md").write_text(
        "---\nscope: backend\n---\n\n# Rails Patterns\n\n### Rule 1\nContent"
    )
    (sections_dir / "no_frontmatter.md").write_text(
        "# No Frontmatter\n\nContent without frontmatter"
    )

    # Patch utils to use our tmp config
    import utils
    utils._config = config
    monkeypatch.setattr(utils, "get_project_root", lambda: tmp_path)

    return config


class TestMatchFileScopes:
    def test_matches_backend(self, sample_config):
        assert scope_matcher.match_file_scopes("app/models/user.rb", "venture") == {"backend"}

    def test_matches_graphql_and_backend(self, sample_config):
        # graphql prefix is under app/, so both match
        scopes = scope_matcher.match_file_scopes("app/graphql/types/user.rb", "venture")
        assert scopes == {"backend", "graphql"}

    def test_matches_frontend(self, sample_config):
        assert scope_matcher.match_file_scopes("client/src/App.tsx", "venture") == {"frontend"}

    def test_no_match(self, sample_config):
        assert scope_matcher.match_file_scopes("README.md", "venture") == set()

    def test_wrong_repo(self, sample_config):
        # nova scopes shouldn't match venture paths
        assert scope_matcher.match_file_scopes("app/models/user.rb", "nova") == set()

    def test_nova_components(self, sample_config):
        assert scope_matcher.match_file_scopes("src/components/Button.tsx", "nova") == {"components"}


class TestCollectScopesForDiff:
    def test_multiple_files(self, sample_config):
        files = ["app/models/user.rb", "client/src/App.tsx", "README.md"]
        scopes = scope_matcher.collect_scopes_for_diff(files, "venture")
        assert scopes == {"backend", "frontend"}

    def test_empty_files(self, sample_config):
        assert scope_matcher.collect_scopes_for_diff([], "venture") == set()


class TestSelectSections:
    def test_all_scope_always_included(self, sample_config):
        sections = scope_matcher.select_sections(set())
        names = {s.name for s in sections}
        assert "error_handling.md" in names
        assert "no_frontmatter.md" in names  # no frontmatter defaults to "all"

    def test_fullstack_included_when_scopes_matched(self, sample_config):
        sections = scope_matcher.select_sections({"backend"})
        names = {s.name for s in sections}
        assert "api_design.md" in names  # fullstack
        assert "rails_patterns.md" in names  # backend
        assert "error_handling.md" in names  # all

    def test_fullstack_excluded_when_no_scopes(self, sample_config):
        sections = scope_matcher.select_sections(set())
        names = {s.name for s in sections}
        assert "api_design.md" not in names

    def test_specific_scope_included(self, sample_config):
        sections = scope_matcher.select_sections({"frontend"})
        names = {s.name for s in sections}
        assert "react_components.md" in names
        assert "rails_patterns.md" not in names

    def test_multiple_scopes(self, sample_config):
        sections = scope_matcher.select_sections({"backend", "frontend"})
        names = {s.name for s in sections}
        assert "rails_patterns.md" in names
        assert "react_components.md" in names
        assert "api_design.md" in names  # fullstack


class TestLoadSectionContent:
    def test_strips_frontmatter(self, sample_config):
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        paths = [sections_dir / "error_handling.md"]
        content = scope_matcher.load_section_content(paths)
        assert "---" not in content.split("\n")[0]  # frontmatter stripped
        assert "# Error Handling" in content

    def test_concatenates_with_separator(self, sample_config):
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        paths = [sections_dir / "error_handling.md", sections_dir / "rails_patterns.md"]
        content = scope_matcher.load_section_content(paths)
        assert "# Error Handling" in content
        assert "# Rails Patterns" in content
        assert "\n\n---\n\n" in content

    def test_no_frontmatter_file(self, sample_config):
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        paths = [sections_dir / "no_frontmatter.md"]
        content = scope_matcher.load_section_content(paths)
        assert "# No Frontmatter" in content


class TestReadSectionScope:
    def test_reads_scope(self, sample_config):
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        assert scope_matcher._read_section_scope(sections_dir / "error_handling.md") == "all"
        assert scope_matcher._read_section_scope(sections_dir / "api_design.md") == "fullstack"
        assert scope_matcher._read_section_scope(sections_dir / "react_components.md") == "frontend"

    def test_defaults_to_all(self, sample_config):
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        assert scope_matcher._read_section_scope(sections_dir / "no_frontmatter.md") == "all"


class TestReadSectionMeta:
    """T1-T3: Tests for the generic frontmatter parser."""

    def test_parses_full_frontmatter(self, sample_config):
        """T1: Returns dict with all frontmatter fields."""
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        # Add a section with risk_weight
        (sections_dir / "auth.md").write_text(
            "---\nscope: all\nrisk_weight: critical\n---\n\n# Auth"
        )
        meta = scope_matcher._read_section_meta(sections_dir / "auth.md")
        assert meta["scope"] == "all"
        assert meta["risk_weight"] == "critical"

    def test_no_frontmatter_returns_defaults(self, sample_config):
        """T2: No frontmatter returns default scope and risk_weight."""
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        meta = scope_matcher._read_section_meta(sections_dir / "no_frontmatter.md")
        assert meta["scope"] == "all"
        assert meta["risk_weight"] == "medium"

    def test_malformed_yaml_returns_defaults(self, sample_config):
        """T3: Malformed YAML returns defaults without crashing."""
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        (sections_dir / "malformed.md").write_text(
            "---\n: invalid: yaml: [broken\n---\n\n# Malformed"
        )
        meta = scope_matcher._read_section_meta(sections_dir / "malformed.md")
        assert meta["scope"] == "all"
        assert meta["risk_weight"] == "medium"


class TestReadSectionRiskWeight:
    """T5-T6: Tests for risk weight extraction."""

    def test_extracts_risk_weight(self, sample_config):
        """T5: Returns correct risk_weight from frontmatter."""
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        (sections_dir / "migration.md").write_text(
            "---\nscope: backend\nrisk_weight: critical\n---\n\n# Migration"
        )
        assert scope_matcher._read_section_risk_weight(sections_dir / "migration.md") == "critical"

    def test_missing_risk_weight_defaults_to_medium(self, sample_config):
        """T6: Missing risk_weight returns 'medium'."""
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        # error_handling.md has no risk_weight in frontmatter
        assert scope_matcher._read_section_risk_weight(sections_dir / "error_handling.md") == "medium"


class TestClassifyRisk:
    """T7-T10: Tests for PR risk classification."""

    def test_single_critical_section(self, sample_config):
        """T7: A single critical section → High risk."""
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        (sections_dir / "auth.md").write_text(
            "---\nscope: all\nrisk_weight: critical\n---\n\n# Auth"
        )
        assert scope_matcher.classify_risk([sections_dir / "auth.md"]) == "High"

    def test_mixed_sections_returns_max(self, sample_config):
        """T8: Mixed sections → returns highest risk level."""
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        (sections_dir / "auth.md").write_text(
            "---\nscope: all\nrisk_weight: critical\n---\n\n# Auth"
        )
        (sections_dir / "style.md").write_text(
            "---\nscope: all\nrisk_weight: low\n---\n\n# Style"
        )
        result = scope_matcher.classify_risk([
            sections_dir / "auth.md",
            sections_dir / "style.md",
        ])
        assert result == "High"

    def test_all_low_sections(self, sample_config):
        """T9: All low sections → Low risk."""
        import utils
        sections_dir = utils.get_project_root() / "rules" / "sections"
        (sections_dir / "style.md").write_text(
            "---\nscope: all\nrisk_weight: low\n---\n\n# Style"
        )
        (sections_dir / "naming.md").write_text(
            "---\nscope: all\nrisk_weight: low\n---\n\n# Naming"
        )
        result = scope_matcher.classify_risk([
            sections_dir / "style.md",
            sections_dir / "naming.md",
        ])
        assert result == "Low"

    def test_empty_sections_returns_low(self, sample_config):
        """T10: Empty sections list → Low risk."""
        assert scope_matcher.classify_risk([]) == "Low"
