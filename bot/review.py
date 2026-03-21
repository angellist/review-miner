#!/usr/bin/env python3
"""Main orchestrator for the AL PR Review Bot.

Usage:
    python -m bot.review --pr 123 --repo venture
    python -m bot.review --pr 123 --repo venture --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure scripts/ is importable (for direct execution; __main__.py also does this)
_scripts_dir = str(Path(__file__).resolve().parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from bot import claude_client, diff_parser, github_client, scope_matcher

import utils


def resolve_github_repo(repo_name: str) -> str:
    """Resolve a config repo name to its full GitHub repo path."""
    repo_config = utils.get_repo_config(repo_name)
    return repo_config["github_repo"]


def review_pr(
    pr_number: int,
    repo_name: str,
    dry_run: bool = False,
    dismiss_previous: bool = True,
    min_severity: str = "suggestion",
) -> dict:
    """Run the full review pipeline for a PR.

    Args:
        pr_number: PR number to review
        repo_name: Repo name from config (e.g. "venture")
        dry_run: If True, print findings but don't post review
        dismiss_previous: If True, dismiss previous bot reviews on synchronize
        min_severity: Minimum severity to post ("critical", "warning", or "suggestion")

    Returns:
        Dict with review results: {posted, findings, skipped, reason}
    """
    github_repo = resolve_github_repo(repo_name)
    print(f"\nReviewing PR #{pr_number} on {github_repo}...")

    # 1. Fetch PR files
    print("  Fetching PR files...")
    pr_files = github_client.fetch_pr_files(github_repo, pr_number)
    print(f"  Found {len(pr_files)} files")

    # 2. Check PR size
    skip_reason = diff_parser.check_pr_size(pr_files)
    if skip_reason:
        print(f"  Skipping: {skip_reason}")
        return {"posted": False, "findings": [], "skipped": True, "reason": skip_reason}

    # 3. Parse and filter files
    filtered_files = diff_parser.parse_pr_files(pr_files)
    print(f"  After filtering: {len(filtered_files)} files to review")

    if not filtered_files:
        print("  No reviewable files. Skipping.")
        return {"posted": False, "findings": [], "skipped": True, "reason": "No reviewable files"}

    # 4. Match scopes
    changed_paths = [f["filename"] for f in filtered_files]
    matched_scopes = scope_matcher.collect_scopes_for_diff(changed_paths, repo_name)
    print(f"  Matched scopes: {matched_scopes or '{none}'}")

    # 5. Select relevant rule sections
    sections = scope_matcher.select_sections(matched_scopes)
    print(f"  Selected {len(sections)} rule sections")

    if not sections:
        print("  No matching rules found. Skipping.")
        return {"posted": False, "findings": [], "skipped": True, "reason": "No matching rules"}

    rules_text = scope_matcher.load_section_content(sections)

    # 5a. Classify risk
    risk_level = scope_matcher.classify_risk(sections)
    print(f"  Risk level: {risk_level}")

    # 6. Build diff text
    diff_text = diff_parser.build_diff_text(filtered_files)
    if not diff_text:
        print("  Empty diff after building. Skipping.")
        return {"posted": False, "findings": [], "skipped": True, "reason": "Empty diff"}

    # 6a. Generate and post review brief
    if not dry_run:
        try:
            pr_data = github_client.gh_api(f"repos/{github_repo}/pulls/{pr_number}")
            pr_description = pr_data.get("body", "") or ""
            section_names = [s.stem for s in sections]

            print("  Generating review brief...")
            brief = claude_client.generate_brief(
                diff_text=diff_text,
                pr_description=pr_description,
                risk_level=risk_level,
                matched_scopes=matched_scopes,
                section_names=section_names,
            )

            print("  Posting review brief...")
            github_client.post_brief(
                github_repo, pr_number, brief, risk_level, len(filtered_files)
            )
            print("  Brief posted successfully")
        except Exception as e:
            print(f"  Warning: Brief generation failed (non-fatal): {e}")

    # 7. Build prompt
    system_prompt, user_prompt = claude_client.build_prompt(rules_text, diff_text)

    if dry_run:
        print("\n  --- DRY RUN: Prompt Stats ---")
        print(f"  System prompt: {len(system_prompt)} chars")
        print(f"  User prompt: {len(user_prompt)} chars")
        print(f"  Rules: {len(rules_text)} chars across {len(sections)} sections")
        print(f"  Diff: {len(diff_text)} chars across {len(filtered_files)} files")
        print("\n  Skipping Claude API call (dry run).")
        return {"posted": False, "findings": [], "skipped": False, "reason": "Dry run"}

    # 8. Call Claude
    print("  Calling Claude for review...")
    findings = claude_client.call_claude(system_prompt, user_prompt)
    print(f"  Claude returned {len(findings)} findings")

    # Filter by minimum severity
    severity_rank = {"critical": 0, "warning": 1, "suggestion": 2}
    min_rank = severity_rank.get(min_severity, 2)
    total_before = len(findings)
    findings = [f for f in findings if severity_rank.get(f["severity"], 2) <= min_rank]
    if len(findings) < total_before:
        print(f"  After severity filter (>= {min_severity}): {len(findings)} findings")

    if not findings:
        print("  No issues found. Clean PR!")
        return {"posted": False, "findings": [], "skipped": False, "reason": "No issues found"}

    # Dismiss previous bot reviews
    if dismiss_previous:
        dismissed = github_client.dismiss_previous_reviews(github_repo, pr_number)
        if dismissed:
            print(f"  Dismissed {dismissed} previous bot review(s)")

    # Post new review
    print("  Posting review...")
    commit_sha = github_client.get_pr_head_sha(github_repo, pr_number)
    github_client.post_review(github_repo, pr_number, findings, commit_sha)
    print(f"  Posted review with {len(findings)} comments")

    return {"posted": True, "findings": findings, "skipped": False, "reason": None}


def main():
    parser = argparse.ArgumentParser(description="AL PR Review Bot")
    parser.add_argument("--pr", type=int, required=True, help="PR number to review")
    parser.add_argument("--repo", required=True, help="Repo name from config (e.g. venture)")
    parser.add_argument("--dry-run", action="store_true", help="Print findings without posting")
    parser.add_argument("--no-dismiss", action="store_true", help="Don't dismiss previous bot reviews")
    parser.add_argument(
        "--min-severity", default="suggestion",
        choices=["critical", "warning", "suggestion"],
        help="Minimum severity to post (default: suggestion)",
    )
    args = parser.parse_args()

    result = review_pr(
        pr_number=args.pr,
        repo_name=args.repo,
        dry_run=args.dry_run,
        dismiss_previous=not args.no_dismiss,
        min_severity=args.min_severity,
    )

    if result["skipped"]:
        print(f"\nSkipped: {result['reason']}")
    elif result["posted"]:
        print(f"\nReview posted with {len(result['findings'])} comment(s).")
    else:
        print(f"\nDone: {result['reason']}")


if __name__ == "__main__":
    main()
