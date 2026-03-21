"""Tests for review brief posting in bot.github_client."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import github_client


SAMPLE_BRIEF = {
    "summary": "- Added error boundary\n- Updated GraphQL fragment",
    "why": "Dashboard crashes for empty portfolios.",
    "risk_rationale": "UI-only change, low risk.",
    "reviewer_focus": ["Verify fallback UI", "Check fragment doesn't over-fetch"],
    "rules_checked": ["react_components", "graphql_schema"],
}


class TestFormatBriefComment:
    def test_formats_correctly(self):
        """Verify the brief comment has all required sections."""
        result = github_client.format_brief_comment(SAMPLE_BRIEF, "Low", 3)
        assert github_client.BOT_BRIEF_TAG in result
        assert "**Risk:** Low" in result
        assert "**Files:** 3" in result
        assert "Added error boundary" in result
        assert "Dashboard crashes" in result
        assert "- [ ] Verify fallback UI" in result
        assert "react_components" in result

    def test_risk_icons(self):
        """Verify correct icons for each risk level."""
        high = github_client.format_brief_comment(SAMPLE_BRIEF, "High", 1)
        medium = github_client.format_brief_comment(SAMPLE_BRIEF, "Medium", 1)
        low = github_client.format_brief_comment(SAMPLE_BRIEF, "Low", 1)
        assert "\u2757" in high  # ❗
        assert "\u26a0\ufe0f" in medium  # ⚠️
        assert "\u2705" in low  # ✅


class TestFindExistingBrief:
    def test_finds_existing(self):
        """T16 helper: Finds a comment with the brief tag."""
        comments = [
            {"id": 100, "body": "some other comment"},
            {"id": 200, "body": f"prefix {github_client.BOT_BRIEF_TAG} suffix"},
        ]
        with patch.object(github_client, "gh_api", return_value=comments):
            result = github_client.find_existing_brief("owner/repo", 1)
        assert result == 200

    def test_returns_none_when_not_found(self):
        """T15 helper: Returns None when no brief exists."""
        comments = [
            {"id": 100, "body": "some other comment"},
        ]
        with patch.object(github_client, "gh_api", return_value=comments):
            result = github_client.find_existing_brief("owner/repo", 1)
        assert result is None

    def test_returns_none_for_non_list_response(self):
        """Handles unexpected API response gracefully."""
        with patch.object(github_client, "gh_api", return_value={}):
            result = github_client.find_existing_brief("owner/repo", 1)
        assert result is None


class TestPostBrief:
    def test_first_post_creates_new_comment(self):
        """T15: First brief posts a new comment."""
        api_calls = []

        def mock_gh_api(endpoint, method="GET", body=None):
            api_calls.append((endpoint, method))
            if method == "GET":
                return []  # no existing comments
            return {"id": 300}

        with patch.object(github_client, "gh_api", side_effect=mock_gh_api):
            result = github_client.post_brief("owner/repo", 1, SAMPLE_BRIEF, "Low", 3)

        assert result == {"id": 300}
        # Should have: GET comments, POST new comment
        assert api_calls[0] == ("repos/owner/repo/issues/1/comments", "GET")
        assert api_calls[1][1] == "POST"

    def test_update_existing_patches(self):
        """T16: Existing brief is updated via PATCH."""
        existing_comments = [
            {"id": 200, "body": f"{github_client.BOT_BRIEF_TAG}\nold brief"},
        ]

        api_calls = []

        def mock_gh_api(endpoint, method="GET", body=None):
            api_calls.append((endpoint, method))
            if method == "GET":
                return existing_comments
            return {"id": 200}

        with patch.object(github_client, "gh_api", side_effect=mock_gh_api):
            result = github_client.post_brief("owner/repo", 1, SAMPLE_BRIEF, "Medium", 5)

        assert result == {"id": 200}
        # Should have: GET comments, PATCH existing
        assert api_calls[1] == ("repos/owner/repo/issues/comments/200", "PATCH")

    def test_patch_404_falls_back_to_post(self):
        """T17: If PATCH fails (deleted comment), falls back to POST."""
        existing_comments = [
            {"id": 200, "body": f"{github_client.BOT_BRIEF_TAG}\nold brief"},
        ]

        call_count = {"get": 0, "patch": 0, "post": 0}

        def mock_gh_api(endpoint, method="GET", body=None):
            if method == "GET":
                call_count["get"] += 1
                return existing_comments
            elif method == "PATCH":
                call_count["patch"] += 1
                raise subprocess.CalledProcessError(1, "gh", stderr="Not Found")
            elif method == "POST":
                call_count["post"] += 1
                return {"id": 301}

        with patch.object(github_client, "gh_api", side_effect=mock_gh_api):
            result = github_client.post_brief("owner/repo", 1, SAMPLE_BRIEF, "High", 2)

        assert result == {"id": 301}
        assert call_count["patch"] == 1  # tried PATCH
        assert call_count["post"] == 1  # fell back to POST
