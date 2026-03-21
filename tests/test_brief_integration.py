"""Integration tests for review brief in the full review pipeline."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import review as bot_review


SAMPLE_BRIEF = {
    "summary": "- Updated config",
    "why": "Feature flag change.",
    "risk_rationale": "Config only, low risk.",
    "reviewer_focus": ["Check flag value"],
    "rules_checked": ["devops_config"],
}

SAMPLE_FINDINGS = [
    {
        "file": "config.yaml",
        "line": 10,
        "severity": "warning",
        "rule_topic": "devops_config",
        "rule_title": "Validate Config Values",
        "comment": "Consider adding validation.",
    }
]


@pytest.fixture
def review_env(tmp_path, monkeypatch):
    """Set up a complete environment for review pipeline tests."""
    config = {
        "repos": [
            {
                "name": "venture",
                "github_repo": "angellist/venture",
                "scopes": [
                    {"name": "backend", "path_prefix": "app/"},
                ],
            },
        ],
        "sections_output_dir": "rules/sections",
        "bot": {
            "model": "claude-sonnet-4-20250514",
            "max_comments": 10,
        },
    }

    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    sections_dir = tmp_path / "rules" / "sections"
    sections_dir.mkdir(parents=True)
    (sections_dir / "error_handling.md").write_text(
        "---\nscope: all\nrisk_weight: medium\n---\n\n# Error Handling\nContent"
    )

    import utils
    utils._config = config
    monkeypatch.setattr(utils, "get_project_root", lambda: tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    return config


class TestBriefIntegration:
    def _mock_pr_files(self):
        """Sample PR files from GitHub API."""
        return [
            {
                "filename": "app/models/user.rb",
                "status": "modified",
                "additions": 5,
                "deletions": 2,
                "changes": 7,
                "patch": "@@ -10,6 +10,9 @@\n+new line 1\n+new line 2",
            },
        ]

    def test_brief_success_and_review_success(self, review_env, monkeypatch):
        """T18: Both brief and review post successfully."""
        pr_files = self._mock_pr_files()

        # Mock all external calls
        with patch("bot.review.github_client") as mock_gh, \
             patch("bot.review.claude_client") as mock_claude:

            mock_gh.fetch_pr_files.return_value = pr_files
            mock_gh.gh_api.return_value = {"body": "Fix user model"}
            mock_gh.post_brief.return_value = {"id": 1}
            mock_gh.get_pr_head_sha.return_value = "abc123"
            mock_gh.post_review.return_value = {"id": 2}
            mock_gh.dismiss_previous_reviews.return_value = 0

            mock_claude.generate_brief.return_value = SAMPLE_BRIEF
            mock_claude.build_prompt.return_value = ("system", "user")
            mock_claude.call_claude.return_value = SAMPLE_FINDINGS

            result = bot_review.review_pr(pr_number=1, repo_name="venture")

        assert result["posted"] is True
        assert len(result["findings"]) == 1

        # Brief was generated and posted
        mock_claude.generate_brief.assert_called_once()
        mock_gh.post_brief.assert_called_once()

        # Review was also posted
        mock_claude.call_claude.assert_called_once()
        mock_gh.post_review.assert_called_once()

    def test_brief_fails_review_succeeds(self, review_env, monkeypatch):
        """T19: Brief failure doesn't block the review."""
        pr_files = self._mock_pr_files()

        with patch("bot.review.github_client") as mock_gh, \
             patch("bot.review.claude_client") as mock_claude:

            mock_gh.fetch_pr_files.return_value = pr_files
            mock_gh.gh_api.return_value = {"body": "Fix user model"}
            mock_gh.get_pr_head_sha.return_value = "abc123"
            mock_gh.post_review.return_value = {"id": 2}
            mock_gh.dismiss_previous_reviews.return_value = 0

            # Brief generation raises an error
            mock_claude.generate_brief.side_effect = RuntimeError("API timeout")
            mock_claude.build_prompt.return_value = ("system", "user")
            mock_claude.call_claude.return_value = SAMPLE_FINDINGS

            result = bot_review.review_pr(pr_number=1, repo_name="venture")

        # Review still posted despite brief failure
        assert result["posted"] is True
        assert len(result["findings"]) == 1
        mock_gh.post_brief.assert_not_called()  # never reached
        mock_gh.post_review.assert_called_once()

    def test_dry_run_skips_brief(self, review_env, monkeypatch):
        """T20: Dry run skips both brief and review."""
        pr_files = self._mock_pr_files()

        with patch("bot.review.github_client") as mock_gh, \
             patch("bot.review.claude_client") as mock_claude:

            mock_gh.fetch_pr_files.return_value = pr_files
            mock_claude.build_prompt.return_value = ("system", "user")

            result = bot_review.review_pr(
                pr_number=1, repo_name="venture", dry_run=True
            )

        assert result["reason"] == "Dry run"
        # Neither brief nor review should call Claude
        mock_claude.generate_brief.assert_not_called()
        mock_claude.call_claude.assert_not_called()
