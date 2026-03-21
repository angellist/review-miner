"""Unit tests for refresh.py pure functions."""

from unittest.mock import patch

import refresh


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BOT_SUFFIXES = ["[bot]", "-bot"]


def _make_comment(id, body="comment", path="src/foo.py", pr_number=1, user="alice",
                  in_reply_to_id=None, created_at="2025-01-01T00:00:00Z"):
    c = {
        "id": id,
        "body": body,
        "path": path,
        "pr_number": pr_number,
        "user": {"login": user},
        "created_at": created_at,
    }
    if in_reply_to_id is not None:
        c["in_reply_to_id"] = in_reply_to_id
    return c


# ---------------------------------------------------------------------------
# _is_bot_author
# ---------------------------------------------------------------------------

class TestIsBotAuthor:
    @patch.object(refresh, "_bot_suffixes", return_value=BOT_SUFFIXES)
    def test_matches_bot_suffix(self, _):
        assert refresh._is_bot_author("dependabot[bot]") is True

    @patch.object(refresh, "_bot_suffixes", return_value=BOT_SUFFIXES)
    def test_matches_dash_bot_suffix(self, _):
        assert refresh._is_bot_author("renovate-bot") is True

    @patch.object(refresh, "_bot_suffixes", return_value=BOT_SUFFIXES)
    def test_case_insensitive(self, _):
        assert refresh._is_bot_author("MyApp[BOT]") is True

    @patch.object(refresh, "_bot_suffixes", return_value=BOT_SUFFIXES)
    def test_human_user(self, _):
        assert refresh._is_bot_author("alice") is False

    @patch.object(refresh, "_bot_suffixes", return_value=BOT_SUFFIXES)
    def test_empty_login(self, _):
        assert refresh._is_bot_author("") is False

    @patch.object(refresh, "_bot_suffixes", return_value=BOT_SUFFIXES)
    def test_partial_match_not_enough(self, _):
        # "bot" alone doesn't end with "[bot]" or "-bot"
        assert refresh._is_bot_author("bot") is False


# ---------------------------------------------------------------------------
# group_into_threads
# ---------------------------------------------------------------------------

class TestGroupIntoThreads:
    def test_single_root_no_replies(self):
        comments = [_make_comment(id=10, body="looks good")]
        threads = refresh.group_into_threads(comments)

        assert len(threads) == 1
        t = threads[0]
        assert t["thread_id"] == 10
        assert t["pr"] == 1
        assert t["root"]["author"] == "alice"
        assert t["root"]["body"] == "looks good"
        assert t["replies"] == []

    def test_root_with_replies_sorted_by_date(self):
        comments = [
            _make_comment(id=1, body="nit"),
            _make_comment(id=3, body="second reply", in_reply_to_id=1, created_at="2025-01-03T00:00:00Z"),
            _make_comment(id=2, body="first reply", in_reply_to_id=1, created_at="2025-01-02T00:00:00Z"),
        ]
        threads = refresh.group_into_threads(comments)

        assert len(threads) == 1
        replies = threads[0]["replies"]
        assert len(replies) == 2
        assert replies[0]["id"] == 2  # earlier date first
        assert replies[1]["id"] == 3

    def test_multiple_independent_threads(self):
        comments = [
            _make_comment(id=10, body="thread A"),
            _make_comment(id=20, body="thread B"),
        ]
        threads = refresh.group_into_threads(comments)
        assert len(threads) == 2
        thread_ids = {t["thread_id"] for t in threads}
        assert thread_ids == {10, 20}

    def test_empty_comments(self):
        assert refresh.group_into_threads([]) == []

    @patch("refresh.sanitize_path", side_effect=ValueError("bad path"))
    def test_unsafe_path_skips_thread(self, _):
        comments = [_make_comment(id=1, path="../../../etc/passwd")]
        threads = refresh.group_into_threads(comments)
        assert threads == []

    def test_empty_path_preserved(self):
        comments = [_make_comment(id=1, path="")]
        threads = refresh.group_into_threads(comments)
        assert len(threads) == 1
        assert threads[0]["root"]["path"] == ""

    def test_orphan_replies_ignored(self):
        """Replies whose root is missing should not appear as threads."""
        comments = [
            _make_comment(id=99, body="orphan reply", in_reply_to_id=999),
        ]
        threads = refresh.group_into_threads(comments)
        assert threads == []


# ---------------------------------------------------------------------------
# enrich_thread
# ---------------------------------------------------------------------------

class TestEnrichThread:
    def test_detects_suggestion_block(self):
        thread = {"root": {"body": "Try this:\n```suggestion\nfixed code\n```"}}
        result = refresh.enrich_thread(thread)
        assert result["has_suggestion_block"] is True
        assert result is thread  # mutates in place

    def test_no_suggestion_block(self):
        thread = {"root": {"body": "Looks good to me!"}}
        result = refresh.enrich_thread(thread)
        assert result["has_suggestion_block"] is False

    def test_regular_code_block_not_flagged(self):
        thread = {"root": {"body": "Example:\n```python\nprint('hi')\n```"}}
        result = refresh.enrich_thread(thread)
        assert result["has_suggestion_block"] is False


# ---------------------------------------------------------------------------
# fetch_merged_prs
# ---------------------------------------------------------------------------

from datetime import date, timedelta


class TestFetchMergedPrs:
    @patch("refresh.check_rate_limit")
    @patch("refresh.fetch_prs_for_range")
    def test_weekly_chunking_15_days(self, mock_fetch, mock_rate_limit):
        """A 15-day range should produce 3 weekly fetch calls."""
        mock_fetch.return_value = []

        since = date(2025, 1, 1)
        until = date(2025, 1, 15)
        refresh.fetch_merged_prs("org/repo", since, until)

        # Jan 1-7, Jan 8-14, Jan 15-15 = 3 calls
        assert mock_fetch.call_count == 3
        calls = mock_fetch.call_args_list
        assert calls[0].args == ("org/repo", date(2025, 1, 1), date(2025, 1, 7))
        assert calls[1].args == ("org/repo", date(2025, 1, 8), date(2025, 1, 14))
        assert calls[2].args == ("org/repo", date(2025, 1, 15), date(2025, 1, 15))

    @patch("refresh.check_rate_limit")
    @patch("refresh.fetch_prs_for_range")
    def test_single_day_range(self, mock_fetch, mock_rate_limit):
        """When since == until, exactly one fetch call is made."""
        mock_fetch.return_value = [{"number": 1, "title": "PR 1"}]

        result = refresh.fetch_merged_prs("org/repo", date(2025, 3, 5), date(2025, 3, 5))

        assert mock_fetch.call_count == 1
        assert len(result) == 1
        assert result[0]["number"] == 1

    @patch("refresh.check_rate_limit")
    @patch("refresh.fetch_prs_for_range")
    def test_dedup_by_pr_number(self, mock_fetch, mock_rate_limit):
        """PRs appearing in multiple weekly windows are deduplicated by number."""
        pr_a = {"number": 10, "title": "PR 10"}
        pr_b = {"number": 20, "title": "PR 20"}
        pr_a_dup = {"number": 10, "title": "PR 10 duplicate"}

        # Week 1 returns PR 10 and 20; week 2 returns PR 10 again
        mock_fetch.side_effect = [[pr_a, pr_b], [pr_a_dup]]

        since = date(2025, 1, 1)
        until = date(2025, 1, 10)  # 10 days = 2 week chunks
        result = refresh.fetch_merged_prs("org/repo", since, until)

        numbers = {pr["number"] for pr in result}
        assert numbers == {10, 20}
        assert len(result) == 2

    @patch("refresh.check_rate_limit")
    @patch("refresh.fetch_prs_for_range")
    def test_dedup_keeps_last_seen(self, mock_fetch, mock_rate_limit):
        """When a PR appears in multiple windows, the last occurrence wins."""
        pr_v1 = {"number": 5, "title": "v1"}
        pr_v2 = {"number": 5, "title": "v2"}

        mock_fetch.side_effect = [[pr_v1], [pr_v2]]

        result = refresh.fetch_merged_prs("org/repo", date(2025, 1, 1), date(2025, 1, 10))
        assert len(result) == 1
        assert result[0]["title"] == "v2"

    @patch("refresh.check_rate_limit")
    @patch("refresh.fetch_prs_for_range")
    def test_exact_week_boundary(self, mock_fetch, mock_rate_limit):
        """A 7-day range (exactly one week) produces exactly one call."""
        mock_fetch.return_value = []

        refresh.fetch_merged_prs("org/repo", date(2025, 1, 1), date(2025, 1, 7))

        assert mock_fetch.call_count == 1
        assert mock_fetch.call_args.args == ("org/repo", date(2025, 1, 1), date(2025, 1, 7))

    @patch("refresh.check_rate_limit")
    @patch("refresh.fetch_prs_for_range")
    def test_empty_range_returns_empty(self, mock_fetch, mock_rate_limit):
        """No PRs fetched returns an empty list."""
        mock_fetch.return_value = []

        result = refresh.fetch_merged_prs("org/repo", date(2025, 1, 1), date(2025, 1, 3))
        assert result == []

    @patch("refresh.check_rate_limit")
    @patch("refresh.fetch_prs_for_range")
    def test_rate_limit_checked_each_week(self, mock_fetch, mock_rate_limit):
        """check_rate_limit is called once per weekly chunk."""
        mock_fetch.return_value = []

        refresh.fetch_merged_prs("org/repo", date(2025, 1, 1), date(2025, 1, 15))

        assert mock_rate_limit.call_count == 3
