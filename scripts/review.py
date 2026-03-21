#!/usr/bin/env python3
"""Generate a code review prompt for a GitHub PR or local changes using mined review rules.

Usage:
    # Review a GitHub PR
    python3 scripts/review.py https://github.com/angellist/nova/pull/7342
    python3 scripts/review.py angellist/nova 7342

    # Review local changes (committed + uncommitted) vs main
    python3 scripts/review.py --local
    python3 scripts/review.py --local --base origin/main
    python3 scripts/review.py --local --base origin/develop

    # Options
    python3 scripts/review.py --list-rules https://github.com/angellist/nova/pull/7342
    python3 scripts/review.py --print-rules --local

Outputs a review prompt to stdout with:
1. The diff (from PR or local)
2. Relevant rule sections (selected by file path analysis)
3. Review instructions
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from utils import get_project_root


# ─── File extension → rule section mapping ───────────────────────────────────
# Each file extension maps to a set of rule sections that are likely relevant.
# "always" sections are included regardless of file type.

ALWAYS_SECTIONS = [
    "error_handling",
    "naming_conventions",
    "code_reuse",
    "code_hygiene",
]

EXTENSION_MAP: dict[str, list[str]] = {
    # TypeScript / JavaScript frontend
    ".ts": ["typescript_patterns", "api_design", "performance"],
    ".tsx": ["typescript_patterns", "react_components", "react_state", "design_system", "performance"],
    ".js": ["typescript_patterns", "performance"],
    ".jsx": ["typescript_patterns", "react_components", "react_state"],

    # Ruby backend
    ".rb": ["rails_patterns", "data_integrity", "performance", "auth_permissions"],

    # GraphQL
    ".graphql": ["graphql_schema"],
    ".gql": ["graphql_schema"],

    # SQL / Prisma migrations
    ".sql": ["migration_safety", "data_integrity", "performance"],
    ".prisma": ["migration_safety", "data_integrity"],

    # Config / DevOps
    ".yaml": ["devops_config"],
    ".yml": ["devops_config"],
    ".toml": ["devops_config"],
    ".json": ["devops_config"],
}

# Path pattern → rule section mapping (checked via substring match)
PATH_PATTERN_MAP: dict[str, list[str]] = {
    "graphql": ["graphql_schema"],
    "migration": ["migration_safety"],
    "test": ["testing_patterns"],
    "spec": ["testing_patterns"],
    "datadog": ["logging_observability"],
    "sentry": ["logging_observability"],
    "logger": ["logging_observability"],
    "temporal": ["temporal_workflows"],
    "workflow": ["temporal_workflows"],
    "auth": ["auth_permissions", "security"],
    "permission": ["auth_permissions"],
    "policy": ["auth_permissions"],
    "pundit": ["auth_permissions"],
    "carry": ["financial_correctness", "fund_lifecycle"],
    "distribution": ["financial_correctness", "fund_lifecycle"],
    "allocation": ["financial_correctness"],
    "money": ["financial_correctness"],
    "ledger": ["financial_correctness"],
    "accounting": ["financial_correctness"],
    "investment": ["financial_correctness"],
    "async": ["async_patterns"],
    "worker": ["async_patterns"],
    "sidekiq": ["async_patterns"],
    "job": ["async_patterns"],
}


# ─── Local diff helpers ───────────────────────────────────────────────────────


def get_local_diff(base: str) -> str:
    """Get combined diff of committed + uncommitted changes vs base branch."""
    # Committed changes on this branch vs base
    committed = subprocess.run(
        ["git", "diff", f"{base}...HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout

    # Uncommitted staged + unstaged changes
    uncommitted = subprocess.run(
        ["git", "diff", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout

    # Combine: committed changes first, then any uncommitted on top
    if uncommitted:
        return committed + "\n" + uncommitted
    return committed


def get_local_changed_files(base: str) -> list[dict]:
    """Get list of changed files (committed + uncommitted) vs base."""
    # Committed changes
    committed_files = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().splitlines()

    # Uncommitted changes
    uncommitted_files = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().splitlines()

    # Deduplicate
    all_files = sorted(set(committed_files + uncommitted_files))
    return [{"path": f, "additions": 0, "deletions": 0} for f in all_files if f]


def get_local_metadata(base: str) -> dict:
    """Build metadata dict for local changes."""
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    # Get repo name from git remote
    try:
        remote_url = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        repo_match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote_url)
        repo = repo_match.group(1) if repo_match else "local"
    except subprocess.CalledProcessError:
        repo = "local"

    # Count additions/deletions
    stat = subprocess.run(
        ["git", "diff", "--shortstat", f"{base}...HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    additions = 0
    deletions = 0
    add_match = re.search(r"(\d+) insertion", stat)
    del_match = re.search(r"(\d+) deletion", stat)
    if add_match:
        additions = int(add_match.group(1))
    if del_match:
        deletions = int(del_match.group(1))

    # Get commit messages for context
    log = subprocess.run(
        ["git", "log", "--oneline", f"{base}..HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    files = get_local_changed_files(base)

    return {
        "title": f"Local changes on {branch}",
        "body": f"Commits:\n{log}" if log else "(no commits yet)",
        "author": {"login": "local"},
        "additions": additions,
        "deletions": deletions,
        "state": "LOCAL",
        "files": files,
    }


# ─── PR helpers ───────────────────────────────────────────────────────────────


def parse_pr_url(pr_input: str) -> tuple[str, int]:
    """Parse a PR URL or repo+number into (repo, pr_number)."""
    # Full URL: https://github.com/angellist/nova/pull/7342
    url_match = re.match(r"https?://github\.com/([^/]+/[^/]+)/pull/(\d+)", pr_input)
    if url_match:
        return url_match.group(1), int(url_match.group(2))

    # Short form: angellist/nova 7342 (handled via two args)
    raise ValueError(f"Cannot parse PR reference: {pr_input}")


def fetch_pr_metadata(repo: str, pr_number: int) -> dict:
    """Fetch PR metadata via gh CLI."""
    result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--repo", repo,
         "--json", "title,body,files,additions,deletions,author,state"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def fetch_pr_diff(repo: str, pr_number: int) -> str:
    """Fetch PR diff via gh CLI."""
    result = subprocess.run(
        ["gh", "pr", "diff", str(pr_number), "--repo", repo],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def select_rule_sections(files: list[dict]) -> list[str]:
    """Given PR file list, select relevant rule sections."""
    sections: set[str] = set(ALWAYS_SECTIONS)

    for file_info in files:
        path = file_info.get("path", "")
        path_lower = path.lower()

        # Extension-based matching
        ext = Path(path).suffix.lower()
        if ext in EXTENSION_MAP:
            sections.update(EXTENSION_MAP[ext])

        # Path pattern matching
        for pattern, rule_sections in PATH_PATTERN_MAP.items():
            if pattern in path_lower:
                sections.update(rule_sections)

    return sorted(sections)


def load_rule_section(section_name: str) -> str | None:
    """Load a rule section markdown file."""
    root = get_project_root()
    path = root / "rules" / "sections" / f"{section_name}.md"
    if path.exists():
        return path.read_text()
    return None


def build_review_prompt(
    repo: str,
    pr_number: int,
    metadata: dict,
    diff: str,
    rule_sections: dict[str, str],
) -> str:
    """Build the full review prompt."""

    files_summary = "\n".join(
        f"  {f['path']} (+{f['additions']}/-{f['deletions']})"
        for f in metadata.get("files", [])
    )

    rules_block = ""
    for name, content in sorted(rule_sections.items()):
        # Strip frontmatter
        content_stripped = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL).strip()
        rules_block += f"\n{content_stripped}\n\n"

    prompt = f"""# Code Review: {metadata.get('title', f'{repo}#{pr_number}')}

## Instructions

You are reviewing a pull request. Use the review rules below — mined from thousands of prior PR reviews on this codebase — to identify issues. Focus on:

1. **Bugs and correctness issues** — logic errors, race conditions, missing error handling
2. **Rule violations** — patterns the team has explicitly flagged as problematic in past reviews
3. **Security concerns** — auth gaps, data leaks, injection risks
4. **Financial correctness** — if the code touches money, carry, or allocations

For each issue found:
- State the file and line
- Describe the problem concisely
- Reference the specific rule being violated (if applicable)
- Suggest a fix

Also note positives — good patterns worth calling out.

Do NOT flag: style nits, minor naming preferences, or issues already covered by linters.

## PR Metadata

- **Repo**: {repo}
- **PR**: #{pr_number}
- **Title**: {metadata.get('title', 'N/A')}
- **Author**: {metadata.get('author', {}).get('login', 'N/A')}
- **Size**: +{metadata.get('additions', 0)}/-{metadata.get('deletions', 0)}
- **State**: {metadata.get('state', 'N/A')}

### Files Changed
{files_summary}

### PR Description
{metadata.get('body', '(no description)') or '(no description)'}

## Review Rules

The following rules were mined from {len(rule_sections)} relevant topic areas based on the files changed in this PR.

{rules_block}

## Diff

```diff
{diff}
```
"""
    return prompt


def main():
    parser = argparse.ArgumentParser(description="Generate a code review prompt for a GitHub PR or local changes")
    parser.add_argument("pr_url", nargs="?", help="GitHub PR URL (e.g., https://github.com/org/repo/pull/123)")
    parser.add_argument("pr_number", nargs="?", type=int, help="PR number (if using repo + number form)")
    parser.add_argument("--local", action="store_true", help="Review local changes (committed + uncommitted) vs base branch")
    parser.add_argument("--base", default="origin/main", help="Base branch for --local mode (default: origin/main)")
    parser.add_argument("--print-rules", action="store_true", help="Print selected rule sections and exit")
    parser.add_argument("--list-rules", action="store_true", help="List which rule sections would be selected")
    parser.add_argument("-o", "--output", help="Write prompt to file instead of stdout")
    args = parser.parse_args()

    if args.local:
        # ── Local mode ──
        base = args.base
        print(f"Collecting local changes vs {base}...", file=sys.stderr)
        try:
            metadata = get_local_metadata(base)
            diff = get_local_diff(base)
        except subprocess.CalledProcessError as e:
            print(f"Error getting local diff: {e.stderr}", file=sys.stderr)
            sys.exit(1)

        if not diff.strip():
            print(f"No changes found vs {base}.", file=sys.stderr)
            sys.exit(0)

        repo = metadata.get("title", "local")
        pr_number = 0
    elif args.pr_url:
        # ── PR mode ──
        if args.pr_number:
            repo = args.pr_url
            pr_number = args.pr_number
        else:
            try:
                repo, pr_number = parse_pr_url(args.pr_url)
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)

        print(f"Fetching PR {repo}#{pr_number}...", file=sys.stderr)
        try:
            metadata = fetch_pr_metadata(repo, pr_number)
            diff = fetch_pr_diff(repo, pr_number)
        except subprocess.CalledProcessError as e:
            print(f"Error fetching PR: {e.stderr}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    # Select relevant rules
    files = metadata.get("files", [])
    selected = select_rule_sections(files)

    if args.list_rules:
        print(f"Changes touch {len(files)} files. Selected {len(selected)} rule sections:\n")
        for s in selected:
            print(f"  - {s}")
        return

    # Load rule content
    rule_sections: dict[str, str] = {}
    for section_name in selected:
        content = load_rule_section(section_name)
        if content:
            rule_sections[section_name] = content

    if args.print_rules:
        for name, content in sorted(rule_sections.items()):
            print(f"\n{'=' * 60}")
            print(f"  {name}")
            print(f"{'=' * 60}\n")
            print(content)
        return

    # Build prompt
    prompt = build_review_prompt(repo, pr_number, metadata, diff, rule_sections)

    if args.output:
        Path(args.output).write_text(prompt)
        print(f"Review prompt written to {args.output}", file=sys.stderr)
        print(f"  Rules: {len(rule_sections)} sections ({', '.join(sorted(rule_sections))})", file=sys.stderr)
        print(f"  Diff: {len(diff)} bytes", file=sys.stderr)
    else:
        print(prompt)

    print(f"\nSelected {len(rule_sections)} rule sections for {len(files)} changed files.", file=sys.stderr)


if __name__ == "__main__":
    main()
