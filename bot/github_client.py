"""Post PR reviews and manage previous bot reviews via GitHub API."""

import json
import subprocess
import sys

# Timeout for all gh CLI calls (seconds)
_SUBPROCESS_TIMEOUT = 60

BOT_REVIEW_TAG = "<!-- al-pr-review-bot -->"
BOT_BRIEF_TAG = "<!-- al-pr-review-brief -->"


def gh_api(endpoint: str, method: str = "GET", body: dict | None = None) -> dict | list:
    """Call GitHub API via gh CLI.

    Args:
        endpoint: API endpoint path (e.g. "repos/owner/repo/pulls/1/reviews")
        method: HTTP method
        body: JSON body for POST/PUT/PATCH requests

    Returns:
        Parsed JSON response
    """
    cmd = ["gh", "api", endpoint, "--method", method]
    if body is not None:
        cmd.extend(["--input", "-"])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=_SUBPROCESS_TIMEOUT,
            input=json.dumps(body) if body else None,
        )
        if not result.stdout.strip():
            return {}
        return json.loads(result.stdout)
    except FileNotFoundError:
        print("Error: gh CLI not found. Install: https://cli.github.com/")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        if "authentication" in e.stderr.lower():
            print("Error: GitHub authentication failed. Run: gh auth login")
            sys.exit(1)
        raise


def fetch_pr_files(github_repo: str, pr_number: int) -> list[dict]:
    """Fetch the list of changed files for a PR.

    Args:
        github_repo: Full repo name (e.g. "angellist/venture")
        pr_number: PR number

    Returns:
        List of file dicts from GitHub API
    """
    # Paginate to handle PRs with many files
    cmd = ["gh", "api", f"repos/{github_repo}/pulls/{pr_number}/files",
           "--paginate"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True,
                                timeout=_SUBPROCESS_TIMEOUT)
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
    except FileNotFoundError:
        print("Error: gh CLI not found. Install: https://cli.github.com/")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        if "authentication" in e.stderr.lower():
            print("Error: GitHub authentication failed. Run: gh auth login")
            sys.exit(1)
        raise


def get_pr_head_sha(github_repo: str, pr_number: int) -> str:
    """Get the HEAD commit SHA of a PR."""
    pr_data = gh_api(f"repos/{github_repo}/pulls/{pr_number}")
    try:
        return pr_data["head"]["sha"]
    except (KeyError, TypeError) as e:
        raise RuntimeError(f"Unexpected PR response structure from GitHub API: {e}")


def build_review_comments(findings: list[dict], commit_sha: str) -> list[dict]:
    """Convert bot findings to GitHub review comment format.

    Args:
        findings: List of comment dicts from Claude
        commit_sha: HEAD commit SHA of the PR

    Returns:
        List of GitHub review comment dicts
    """
    comments = []
    for finding in findings:
        severity_icon = {"critical": "\u2757", "warning": "\u26a0\ufe0f", "suggestion": "\ud83d\udca1"}.get(
            finding["severity"], ""
        )

        body = (
            f"{severity_icon} **{finding['severity'].upper()}** — {finding['rule_topic']}: "
            f"{finding['rule_title']}\n\n{finding['comment']}"
        )

        comments.append({
            "path": finding["file"],
            "line": finding["line"],
            "body": body,
        })

    return comments


def post_review(
    github_repo: str,
    pr_number: int,
    findings: list[dict],
    commit_sha: str,
) -> dict:
    """Post a PR review with inline comments.

    Posts a single review with COMMENT event (advisory, non-blocking).

    Args:
        github_repo: Full repo name
        pr_number: PR number
        findings: List of comment dicts from Claude
        commit_sha: HEAD commit SHA

    Returns:
        GitHub API response dict
    """
    comments = build_review_comments(findings, commit_sha)

    summary_lines = [f"- **{f['severity']}**: {f['file']} L{f['line']} — {f['rule_title']}" for f in findings]
    summary = "\n".join(summary_lines)

    body = {
        "commit_id": commit_sha,
        "event": "COMMENT",
        "body": f"{BOT_REVIEW_TAG}\n\n**AL PR Review Bot** found {len(findings)} issue(s):\n\n{summary}",
        "comments": comments,
    }

    return gh_api(f"repos/{github_repo}/pulls/{pr_number}/reviews", method="POST", body=body)


def format_brief_comment(brief: dict, risk_level: str, file_count: int) -> str:
    """Format a review brief dict into a markdown GitHub comment.

    Args:
        brief: Dict with summary, why, risk_rationale, reviewer_focus, rules_checked
        risk_level: Risk classification ("High", "Medium", "Low")
        file_count: Number of files in the PR

    Returns:
        Formatted markdown string
    """
    risk_icon = {"High": "\u2757", "Medium": "\u26a0\ufe0f", "Low": "\u2705"}.get(risk_level, "")

    focus_items = "\n".join(f"- [ ] {item}" for item in brief.get("reviewer_focus", []))
    rules_list = ", ".join(brief.get("rules_checked", []))

    return f"""{BOT_BRIEF_TAG}

## Review Brief
{risk_icon} **Risk:** {risk_level} | **Files:** {file_count}

### What changed
{brief['summary']}

### Why
{brief['why']}

### Risk rationale
{brief['risk_rationale']}

### Reviewer focus areas
{focus_items}

### Rules checked
{rules_list}

---
*Generated by al-pr-review bot*"""


def find_existing_brief(github_repo: str, pr_number: int) -> int | None:
    """Find an existing bot brief comment on a PR.

    Args:
        github_repo: Full repo name
        pr_number: PR number

    Returns:
        Comment ID if found, None otherwise
    """
    comments = gh_api(f"repos/{github_repo}/issues/{pr_number}/comments")
    if not isinstance(comments, list):
        return None

    for comment in comments:
        body = comment.get("body", "")
        if BOT_BRIEF_TAG in body:
            return comment["id"]

    return None


def post_brief(
    github_repo: str,
    pr_number: int,
    brief: dict,
    risk_level: str,
    file_count: int,
) -> dict:
    """Post or update a review brief comment on a PR.

    If an existing brief comment is found, it is updated in place.
    Otherwise, a new comment is created. If updating fails with a 404
    (comment was deleted), falls back to creating a new comment.

    Args:
        github_repo: Full repo name
        pr_number: PR number
        brief: Brief dict from generate_brief()
        risk_level: Risk classification
        file_count: Number of files in the PR

    Returns:
        GitHub API response dict
    """
    body = format_brief_comment(brief, risk_level, file_count)

    existing_id = find_existing_brief(github_repo, pr_number)

    if existing_id is not None:
        try:
            return gh_api(
                f"repos/{github_repo}/issues/comments/{existing_id}",
                method="PATCH",
                body={"body": body},
            )
        except subprocess.CalledProcessError:
            # Comment may have been deleted — fall back to creating a new one
            pass

    return gh_api(
        f"repos/{github_repo}/issues/{pr_number}/comments",
        method="POST",
        body={"body": body},
    )


def dismiss_previous_reviews(github_repo: str, pr_number: int) -> int:
    """Dismiss previous bot reviews on this PR.

    Looks for reviews containing the bot tag and dismisses them.

    Args:
        github_repo: Full repo name
        pr_number: PR number

    Returns:
        Number of reviews dismissed
    """
    reviews = gh_api(f"repos/{github_repo}/pulls/{pr_number}/reviews")
    if not isinstance(reviews, list):
        return 0

    dismissed = 0
    for review in reviews:
        body = review.get("body", "")
        state = review.get("state", "")
        if BOT_REVIEW_TAG in body and state != "DISMISSED":
            review_id = review["id"]
            try:
                gh_api(
                    f"repos/{github_repo}/pulls/{pr_number}/reviews/{review_id}/dismissals",
                    method="PUT",
                    body={"message": "Superseded by new review after push."},
                )
                dismissed += 1
            except subprocess.CalledProcessError as e:
                print(f"  Warning: Failed to dismiss review {review_id}: {e.stderr[:200] if e.stderr else e}")

    return dismissed
