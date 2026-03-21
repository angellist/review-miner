"""Tests for review brief generation in bot.claude_client."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import claude_client


class TestParseBriefResponse:
    """T11-T14: Tests for brief response parsing."""

    def test_valid_response(self):
        """T11: Valid JSON object is parsed correctly."""
        response = json.dumps({
            "summary": "- Changed auth flow\n- Updated tests",
            "why": "Fix login bug for SSO users.",
            "risk_rationale": "Touches auth middleware — critical path.",
            "reviewer_focus": ["Verify SSO redirect", "Check session handling"],
            "rules_checked": ["auth_permissions", "error_handling"],
        })
        result = claude_client.parse_brief_response(response)
        assert result["summary"] == "- Changed auth flow\n- Updated tests"
        assert result["why"] == "Fix login bug for SSO users."
        assert len(result["reviewer_focus"]) == 2
        assert "auth_permissions" in result["rules_checked"]

    def test_response_with_markdown_fences(self):
        """T11b: Response wrapped in markdown fences is still parsed."""
        inner = json.dumps({
            "summary": "- Updated config",
            "why": "New feature flag.",
            "risk_rationale": "Config only.",
            "reviewer_focus": ["Check flag name"],
            "rules_checked": ["devops_config"],
        })
        response = f"```json\n{inner}\n```"
        result = claude_client.parse_brief_response(response)
        assert result["summary"] == "- Updated config"

    def test_malformed_response_raises(self):
        """T13: Malformed JSON raises ValueError."""
        with pytest.raises(ValueError, match="Failed to parse"):
            claude_client.parse_brief_response("this is not json {{{")

    def test_missing_fields_raises(self):
        """T13b: Missing required fields raises ValueError."""
        response = json.dumps({"summary": "partial", "why": "incomplete"})
        with pytest.raises(ValueError, match="missing fields"):
            claude_client.parse_brief_response(response)

    def test_non_object_raises(self):
        """T13c: JSON array instead of object raises ValueError."""
        with pytest.raises(ValueError, match="Expected JSON object"):
            claude_client.parse_brief_response("[1, 2, 3]")


class TestGenerateBrief:
    """T11, T12, T14: Tests for the generate_brief function."""

    def _mock_claude_response(self, brief_dict):
        """Create a mock Anthropic client that returns the given brief."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(brief_dict))]
        mock_response.stop_reason = "end_turn"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        return mock_client

    def test_valid_generation(self, monkeypatch):
        """T11: Full brief generation with valid response."""
        brief_data = {
            "summary": "- Added error boundary",
            "why": "Dashboard crashes for empty portfolios.",
            "risk_rationale": "UI-only change, low risk.",
            "reviewer_focus": ["Verify fallback UI"],
            "rules_checked": ["react_components"],
        }
        mock_client = self._mock_claude_response(brief_data)

        import utils
        utils._config = {"bot": {"model": "claude-sonnet-4-20250514"}}
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        with patch.dict("sys.modules", {"anthropic": MagicMock(Anthropic=MagicMock(return_value=mock_client))}):

            result = claude_client.generate_brief(
                diff_text="diff content",
                pr_description="Fix dashboard crash",
                risk_level="Low",
                matched_scopes={"frontend"},
                section_names=["react_components"],
            )

        assert result["summary"] == "- Added error boundary"
        assert result["why"] == "Dashboard crashes for empty portfolios."

        # Verify the prompt was constructed correctly
        call_args = mock_client.messages.create.call_args
        user_msg = call_args[1]["messages"][0]["content"]
        assert "Fix dashboard crash" in user_msg
        assert "Low" in user_msg

    def test_no_pr_description(self, monkeypatch):
        """T12: PR with no description uses diff-only mode."""
        brief_data = {
            "summary": "- Updated config",
            "why": "Inferred from diff.",
            "risk_rationale": "Config only.",
            "reviewer_focus": ["Check values"],
            "rules_checked": ["devops_config"],
        }
        mock_client = self._mock_claude_response(brief_data)

        import utils
        utils._config = {"bot": {"model": "claude-sonnet-4-20250514"}}
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        with patch.dict("sys.modules", {"anthropic": MagicMock(Anthropic=MagicMock(return_value=mock_client))}):

            result = claude_client.generate_brief(
                diff_text="diff content",
                pr_description="",
                risk_level="Low",
                matched_scopes=set(),
                section_names=["devops_config"],
            )

        # Verify diff-only prompt was used
        call_args = mock_client.messages.create.call_args
        user_msg = call_args[1]["messages"][0]["content"]
        assert "No PR description provided" in user_msg

    def test_empty_response_raises(self, monkeypatch):
        """T14: Empty Claude response raises RuntimeError."""
        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "end_turn"

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        import utils
        utils._config = {"bot": {"model": "claude-sonnet-4-20250514"}}
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        with patch.dict("sys.modules", {"anthropic": MagicMock(Anthropic=MagicMock(return_value=mock_client))}):

            with pytest.raises(RuntimeError, match="Empty response"):
                claude_client.generate_brief(
                    diff_text="diff",
                    pr_description="desc",
                    risk_level="Low",
                    matched_scopes=set(),
                    section_names=[],
                )
