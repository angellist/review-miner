"""Parse PR diff from GitHub API and apply size/skip filters."""

import fnmatch

import utils

# Default skip patterns for generated/vendored files
DEFAULT_SKIP_PATTERNS = ["*.lock", "*.generated.*", "*.snap", "vendor/*", "__generated__/*"]


def get_bot_config() -> dict:
    """Get bot config section from config.yaml."""
    return utils.load_config().get("bot", {})


def get_skip_patterns() -> list[str]:
    """Get file skip patterns from config, with defaults."""
    return get_bot_config().get("skip_patterns", DEFAULT_SKIP_PATTERNS)


def get_max_diff_bytes() -> int:
    """Get max diff size in bytes from config."""
    return get_bot_config().get("max_diff_bytes", 100_000)


def should_skip_file(filename: str) -> bool:
    """Check if a file should be skipped based on skip patterns.

    Args:
        filename: File path relative to repo root

    Returns:
        True if the file matches any skip pattern
    """
    patterns = get_skip_patterns()
    for pattern in patterns:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


def parse_pr_files(pr_files: list[dict]) -> list[dict]:
    """Parse and filter PR files from GitHub API response.

    Each file dict from the API has: filename, status, additions, deletions,
    changes, patch (the diff text), etc.

    Args:
        pr_files: Raw file list from GitHub API /pulls/{n}/files

    Returns:
        Filtered list of file dicts with only relevant files
    """
    filtered = []
    for f in pr_files:
        filename = f.get("filename", "")
        if not filename:
            continue

        try:
            utils.sanitize_path(filename)
        except ValueError:
            continue

        if should_skip_file(filename):
            continue

        # Skip removed files — nothing to review
        if f.get("status") == "removed":
            continue

        filtered.append(f)

    return filtered


def build_diff_text(files: list[dict], max_bytes: int | None = None) -> str:
    """Build a unified diff string from parsed PR files.

    Truncates individual large files to fit within the byte budget.

    Args:
        files: Parsed PR files (from parse_pr_files)
        max_bytes: Maximum total diff size in bytes. None uses config default.

    Returns:
        Formatted diff string
    """
    if max_bytes is None:
        max_bytes = get_max_diff_bytes()

    parts = []
    total_bytes = 0

    for f in files:
        filename = f.get("filename", "")
        patch = f.get("patch", "")
        status = f.get("status", "modified")

        if not patch:
            continue

        header = f"## {filename} ({status})\n"
        file_diff = header + "```diff\n" + patch + "\n```\n"
        file_bytes = len(file_diff.encode("utf-8"))

        if total_bytes + file_bytes > max_bytes:
            # Try to fit a truncated version, cutting on line boundaries
            remaining = max_bytes - total_bytes
            header_bytes = len(header.encode("utf-8"))
            overhead = 50  # "```diff\n" + "\n... (truncated)\n```\n"
            if remaining > header_bytes + overhead + 100:
                budget = remaining - header_bytes - overhead
                lines = patch.split("\n")
                kept_lines = []
                used = 0
                for line in lines:
                    line_bytes = len(line.encode("utf-8")) + 1  # +1 for newline
                    if used + line_bytes > budget:
                        break
                    kept_lines.append(line)
                    used += line_bytes
                if kept_lines:
                    truncated = header + "```diff\n" + "\n".join(kept_lines) + "\n... (truncated)\n```\n"
                    parts.append(truncated)
                    total_bytes += len(truncated.encode("utf-8"))
            break

        parts.append(file_diff)
        total_bytes += file_bytes

    return "\n".join(parts)


def check_pr_size(pr_files: list[dict]) -> str | None:
    """Check if a PR is too large to review.

    Args:
        pr_files: Raw file list from GitHub API

    Returns:
        None if OK, or a reason string if the PR should be skipped
    """
    if len(pr_files) > 200:
        return f"PR has {len(pr_files)} files (max 200). Too large for automated review."

    total_changes = sum(f.get("changes", 0) for f in pr_files)
    if total_changes > 10_000:
        return f"PR has {total_changes} line changes (max 10,000). Too large for automated review."

    return None
