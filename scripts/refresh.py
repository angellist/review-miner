#!/usr/bin/env python3
"""Refresh PR review threads from GitHub.

Adapted from Valon's mine-best-practices with:
- Multi-repo support (--repo or --all)
- Rate limit handling (sleep until reset when remaining < threshold)
- Bot author filtering ([bot] suffix authors excluded)
- Path sanitization for GitHub API responses
- Per-week-batch last_refreshed_at tracking

All date ranges refer to PR merge date.
"""

import json
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from utils import (
    get_repo_config,
    get_repo_data_dir,
    get_repo_names,
    load_config,
    load_yaml,
    sanitize_path,
    save_yaml,
)

_config: dict | None = None


def _get_config() -> dict:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def _extraction_start_date() -> str:
    return _get_config().get("extraction_start_date", "2024-01-01")


def _bot_suffixes() -> list[str]:
    return _get_config().get("bot_suffixes", ["[bot]", "-bot"])


def _rate_limit_config() -> dict:
    return _get_config().get("rate_limit", {"min_remaining": 100, "sleep_buffer_seconds": 5})


# =============================================================================
# Rate Limit Handling
# =============================================================================


def check_rate_limit() -> None:
    """Check GitHub API rate limit and sleep if needed."""
    rl_config = _rate_limit_config()
    min_remaining = rl_config.get("min_remaining", 100)
    buffer_seconds = rl_config.get("sleep_buffer_seconds", 5)

    try:
        result = subprocess.run(
            ["gh", "api", "rate_limit"],
            capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
        core = data.get("resources", {}).get("core", {})
        remaining = core.get("remaining", 5000)
        reset_at = core.get("reset", 0)

        if remaining < min_remaining:
            wait_seconds = max(0, reset_at - int(time.time())) + buffer_seconds
            print(f"  Rate limit low ({remaining} remaining). Sleeping {wait_seconds}s until reset...")
            time.sleep(wait_seconds)
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        pass


# =============================================================================
# GitHub API Helpers
# =============================================================================


def gh_api(endpoint: str, paginate: bool = False) -> list | dict:
    """Call GitHub API via gh CLI with array-form arguments."""
    cmd = ["gh", "api", endpoint]
    if paginate:
        cmd.append("--paginate")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if paginate:
            merged: list = []
            decoder = json.JSONDecoder()
            s = result.stdout.strip()
            while s:
                obj, idx = decoder.raw_decode(s)
                if isinstance(obj, list):
                    merged.extend(obj)
                else:
                    merged.append(obj)
                s = s[idx:].lstrip()
            return merged
        return json.loads(result.stdout)
    except FileNotFoundError:
        print("Error: gh CLI not found. Please install: https://cli.github.com/")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        if "authentication" in e.stderr.lower():
            print("Error: GitHub authentication failed. Run: gh auth login")
            sys.exit(1)
        raise


def fetch_prs_for_range(github_repo: str, start: date, end: date, retries: int = 5) -> list[dict]:
    """Fetch merged PRs for a specific date range using array-form args."""
    cmd = [
        "gh",
        "pr",
        "list",
        "--repo",
        github_repo,
        "--state",
        "merged",
        "--search",
        f"merged:{start}..{end}",
        "--limit",
        "1000",
        "--json",
        "number,title,author,mergedAt,files",
    ]
    for attempt in range(retries):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            if attempt < retries - 1:
                stderr = e.stderr[:200] if e.stderr else ""
                is_server_error = "rate limit" in stderr.lower() or "502" in stderr or "503" in stderr
                wait = 65 if is_server_error else 5 * (attempt + 1)
                print(f"    Retry {attempt + 1}/{retries} for {start}..{end} (waiting {wait}s): {stderr}")
                time.sleep(wait)
            else:
                raise


def fetch_merged_prs(github_repo: str, since: date, until: date) -> list[dict]:
    """Fetch all merged PRs since given date, paginating by week to avoid 1000 limit."""
    all_prs: dict[int, dict] = {}

    current = since
    while current <= until:
        week_end = min(current + timedelta(days=6), until)
        print(f"  Fetching PRs {current} to {week_end}...")

        check_rate_limit()

        prs = fetch_prs_for_range(github_repo, current, week_end)
        for pr in prs:
            all_prs[pr["number"]] = pr
        current = week_end + timedelta(days=1)

    return list(all_prs.values())


def _is_bot_author(login: str) -> bool:
    """Check if a GitHub login is a bot account."""
    login_lower = login.lower()
    for suffix in _bot_suffixes():
        if login_lower.endswith(suffix.lower()):
            return True
    return False


def fetch_pr_comments(github_repo: str, pr_number: int) -> list[dict]:
    """Fetch all review comments for a PR."""
    result = gh_api(f"repos/{github_repo}/pulls/{pr_number}/comments", paginate=True)
    return result if isinstance(result, list) else []


def group_into_threads(comments: list[dict]) -> list[dict]:
    """Group comments into threads."""
    replies_by_root: dict[int, list[dict]] = defaultdict(list)
    root_comments = []

    for comment in comments:
        if comment.get("in_reply_to_id") is None:
            root_comments.append(comment)
        else:
            replies_by_root[comment["in_reply_to_id"]].append(comment)

    threads = []
    for root in root_comments:
        replies = replies_by_root.get(root["id"], [])
        replies.sort(key=lambda r: r["created_at"])

        raw_path = root.get("path", "")
        try:
            safe_path = sanitize_path(raw_path) if raw_path else ""
        except ValueError as e:
            print(f"  Warning: Skipping thread with unsafe path: {e}")
            continue

        thread = {
            "thread_id": root["id"],
            "pr": root["pr_number"],
            "root": {
                "id": root["id"],
                "author": root["user"]["login"],
                "body": root["body"],
                "path": safe_path,
                "created_at": root["created_at"],
            },
            "replies": [
                {"id": r["id"], "author": r["user"]["login"], "body": r["body"], "created_at": r["created_at"]}
                for r in replies
            ],
        }
        threads.append(thread)

    return threads


def enrich_thread(thread: dict) -> dict:
    """Add metadata to thread based on comment content."""
    root = thread["root"]
    thread["has_suggestion_block"] = "```suggestion" in root["body"]
    return thread


def refresh_repo(repo_name: str, since: str | None, until: str | None, full: bool) -> None:
    """Refresh threads for a single repo."""
    repo_config = get_repo_config(repo_name)
    github_repo = repo_config["github_repo"]

    print(f"\n{'=' * 60}")
    print(f"Refresh PR Review Threads — {repo_name} ({github_repo})")
    print(f"{'=' * 60}\n")

    data_dir = get_repo_data_dir(repo_name)
    threads_file = data_dir / "threads.yaml"

    if full:
        print("Full extraction mode - clearing existing data")
        since_date = date.fromisoformat(_extraction_start_date())
        existing_threads = []
        metadata = {}
    else:
        print("Loading existing threads...")
        existing_data = load_yaml(threads_file)
        existing_threads = existing_data.get("threads", [])
        metadata = existing_data.get("metadata", {})
        print(f"Loaded {len(existing_threads)} existing threads")

        if since:
            since_date = date.fromisoformat(since)
            print(f"Using explicit --since date: {since_date}")
        else:
            fetched_ranges = metadata.get("fetched_ranges", [])
            if fetched_ranges:
                last_until = fetched_ranges[-1]["until"]
                since_date = date.fromisoformat(last_until)
                print(f"Incremental mode - last fetched until: {last_until}")
            else:
                last_refresh = metadata.get("last_refresh")
                if last_refresh:
                    last_date = datetime.fromisoformat(last_refresh.replace("Z", "+00:00")).date()
                    since_date = last_date
                    print(f"Incremental mode - last refresh: {last_refresh}")
                else:
                    print("No previous refresh metadata found, using default start date")
                    since_date = date.fromisoformat(_extraction_start_date())

    until_date = date.fromisoformat(until) if until else date.today()

    print(f"\nFetching PRs merged from {since_date} to {until_date}...")
    all_prs = fetch_merged_prs(github_repo, since_date, until_date)
    print(f"Found {len(all_prs)} PRs in date range")

    existing_thread_ids = {t["thread_id"] for t in existing_threads}

    all_new_threads = []
    pr_count = 0
    thread_count = 0
    bot_filtered_count = 0

    for i, pr in enumerate(all_prs, 1):
        pr_number = pr["number"]

        if i % 50 == 0:
            print(f"  Progress: {i}/{len(all_prs)} PRs, {thread_count} new threads")
            check_rate_limit()

        pr_author = pr.get("author", {}).get("login", "")
        if _is_bot_author(pr_author):
            bot_filtered_count += 1
            continue

        try:
            comments = fetch_pr_comments(github_repo, pr_number)
        except subprocess.CalledProcessError as e:
            print(f"  Warning: Failed to fetch comments for PR #{pr_number}: {e}")
            continue

        if not comments:
            continue

        for comment in comments:
            comment["pr_number"] = pr_number

        pr_threads = group_into_threads(comments)

        for thread in pr_threads:
            if thread["thread_id"] not in existing_thread_ids:
                root_author = thread["root"]["author"]
                if _is_bot_author(root_author):
                    bot_filtered_count += 1
                    continue

                thread["pr_author"] = pr_author
                thread["merged_at"] = pr["mergedAt"]
                thread["repo"] = repo_name
                enrich_thread(thread)
                all_new_threads.append(thread)
                existing_thread_ids.add(thread["thread_id"])
                thread_count += 1

        if pr_threads:
            pr_count += 1

    print(f"\nExtracted {thread_count} new threads from {pr_count} PRs")
    if bot_filtered_count:
        print(f"Filtered {bot_filtered_count} bot-authored items")

    if full:
        final_threads = all_new_threads
    else:
        final_threads = existing_threads + all_new_threads

    final_threads.sort(key=lambda t: t["thread_id"])

    existing_ranges = metadata.get("fetched_ranges", []) if not full else []
    new_range = {
        "since": since_date.isoformat(),
        "until": until_date.isoformat(),
        "fetched_at": datetime.now().isoformat(),
    }
    metadata = {
        "last_refresh": datetime.now().isoformat(),
        "fetched_ranges": existing_ranges + [new_range],
        "pr_count": len({t["pr"] for t in final_threads}),
        "thread_count": len(final_threads),
    }

    print(f"\nSaving {len(final_threads)} total threads...")
    output_data = {"metadata": metadata, "threads": final_threads}
    save_yaml(threads_file, output_data)

    print(f"Saved to {threads_file}")
    print(f"  Total PRs: {metadata['pr_count']}")
    print(f"  Total threads: {metadata['thread_count']}")


def refresh_threads(repo: str | None, since: str | None, until: str | None, full: bool) -> None:
    """Main entry point for thread refresh. Refreshes one or all repos."""
    if repo:
        repos = [repo]
    else:
        repos = get_repo_names()

    for repo_name in repos:
        refresh_repo(repo_name, since, until, full)

    print(f"\nRefresh complete for {len(repos)} repo(s).")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Refresh PR review threads from GitHub")
    parser.add_argument("--repo", help="Repo name from config (default: all repos)")
    parser.add_argument("--since", help="Fetch PRs merged on or after DATE (YYYY-MM-DD, inclusive)")
    parser.add_argument("--until", help="Fetch PRs merged on or before DATE (YYYY-MM-DD, inclusive; default: today)")
    parser.add_argument("--full", action="store_true", help="Full re-extraction of threads (clear existing)")
    args = parser.parse_args()

    refresh_threads(args.repo, args.since, args.until, args.full)
