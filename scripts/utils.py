"""Shared utilities for al-pr-review scripts."""

import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

# Cached config
_config: dict | None = None


def get_project_root() -> Path:
    """Get the al-pr-review project root (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def load_config() -> dict:
    """Load config.yaml from the project root."""
    global _config
    if _config is not None:
        return _config

    root = get_project_root()
    config_path = root / "config.yaml"
    if not config_path.exists():
        print(f"Error: No config.yaml found in {root}")
        print("Copy config.yaml.example to config.yaml and configure it.")
        sys.exit(1)

    with open(config_path) as f:
        _config = yaml.safe_load(f) or {}
    return _config


# =============================================================================
# Multi-repo helpers
# =============================================================================


def get_repo_names() -> list[str]:
    """Get list of all configured repo names."""
    config = load_config()
    return [r["name"] for r in config.get("repos", [])]


def get_repo_config(repo_name: str) -> dict:
    """Get config for a specific repo. Exits if not found."""
    config = load_config()
    for r in config.get("repos", []):
        if r["name"] == repo_name:
            return r
    print(f"Error: Repo '{repo_name}' not found in config.yaml")
    print(f"Available repos: {', '.join(get_repo_names())}")
    sys.exit(1)


def get_all_scopes() -> list[dict]:
    """Get all scopes across all repos, with repo name attached."""
    config = load_config()
    scopes = []
    for r in config.get("repos", []):
        for s in r.get("scopes", []):
            scopes.append({**s, "repo": r["name"]})
    return scopes


def get_data_dir() -> Path:
    """Get the shared library data directory (insights, library)."""
    config = load_config()
    return get_project_root() / config.get("library_dir", "code_insights")


def get_repo_data_dir(repo_name: str) -> Path:
    """Get the per-repo data directory (threads)."""
    return get_data_dir() / repo_name


# =============================================================================
# YAML I/O
# =============================================================================


def load_yaml(path: Path) -> dict:
    """Load YAML file. Returns empty dict if file doesn't exist."""
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: Path, data: dict) -> None:
    """Save data to YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# =============================================================================
# Thread loading
# =============================================================================


def load_threads(
    *,
    repo: str | None = None,
    since: str | None = None,
    until: str | None = None,
    scope: str | None = None,
) -> list[dict]:
    """Load and filter threads from threads.yaml.

    Args:
        repo: Repo name to load threads from. If None, loads from all repos.
        since: Only threads after this date (YYYY-MM-DD)
        until: Only threads before this date (YYYY-MM-DD)
        scope: Filter by scope name from config.yaml, or 'all'

    Returns:
        List of thread dicts matching filters
    """
    if repo:
        repos = [repo]
    else:
        repos = get_repo_names()

    all_threads = []
    for repo_name in repos:
        data = load_yaml(get_repo_data_dir(repo_name) / "threads.yaml")
        threads = data.get("threads", [])
        # Tag each thread with its repo for provenance
        for t in threads:
            if "repo" not in t:
                t["repo"] = repo_name
        all_threads.extend(threads)

    # Date filtering
    if since:
        since_dt = datetime.strptime(since, "%Y-%m-%d")
        all_threads = [t for t in all_threads if _thread_date(t) >= since_dt]

    if until:
        until_dt = datetime.strptime(until, "%Y-%m-%d") + timedelta(days=1) - timedelta(microseconds=1)
        all_threads = [t for t in all_threads if _thread_date(t) <= until_dt]

    # Scope filtering
    if scope and scope != "all":
        all_threads = [t for t in all_threads if _matches_scope(t, scope)]

    return all_threads


def _thread_date(thread: dict) -> datetime:
    """Extract date from thread. Prefers merged_at, falls back to comment creation date."""
    merged_at = thread.get("merged_at", "")
    if merged_at:
        return datetime.fromisoformat(merged_at.replace("Z", "+00:00")).replace(tzinfo=None)
    created_at = thread.get("root", {}).get("created_at", "")
    if created_at:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None)
    return datetime.min


def _matches_scope(thread: dict, scope: str) -> bool:
    """Check if thread matches scope filter using config scopes across all repos."""
    path = thread.get("root", {}).get("path", "")
    thread_repo = thread.get("repo")

    config = load_config()
    for r in config.get("repos", []):
        # If thread has a repo tag, only check scopes from that repo
        if thread_repo and r["name"] != thread_repo:
            continue
        for s in r.get("scopes", []):
            if s["name"] == scope:
                return path.startswith(s["path_prefix"])

    return False


# =============================================================================
# Insights (shared across repos)
# =============================================================================


def load_insights() -> list[dict]:
    """Load insights from insights.yaml."""
    data = load_yaml(get_data_dir() / "insights.yaml")
    return data.get("insights", [])


def save_insights(insights: list[dict]) -> None:
    """Save insights to insights.yaml."""
    save_yaml(get_data_dir() / "insights.yaml", {"insights": insights})


def get_processed_thread_ids() -> set[int]:
    """Get thread IDs that have already been processed."""
    insights = load_insights()
    return {i["thread_id"] for i in insights}


def load_library_topics() -> list[str]:
    """Get list of existing library topics."""
    library_dir = get_data_dir() / "library"
    if not library_dir.exists():
        return []
    return [f.stem for f in library_dir.glob("*.yaml")]


# =============================================================================
# Working directory / identifiers
# =============================================================================


def get_working_dir(identifier: str) -> Path:
    """Get the temporary working directory for a mining run."""
    config = load_config()
    return get_project_root() / config.get("tmp_dir", "tmp") / f"mining_{identifier}"


_SAFE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,80}$")


def validate_safe_name(name: str, label: str) -> str:
    """Validate that a name is safe for use in file paths (lowercase alphanumeric + underscores)."""
    if not _SAFE_NAME_RE.match(name):
        print(f"Error: Invalid {label} name: {name!r}. Must match {_SAFE_NAME_RE.pattern}")
        sys.exit(1)
    return name


def generate_identifier(repo: str | None, scope: str) -> str:
    """Generate a run identifier from repo, scope, and current date."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    prefix = repo or "all"
    return f"{prefix}_{scope}_{date_str}"


def load_template(name: str) -> str:
    """Load a template file from references/templates/."""
    template_path = get_project_root() / "references" / "templates" / name
    return template_path.read_text()


# =============================================================================
# Preflight / security
# =============================================================================


def preflight_check() -> None:
    """Verify prerequisites: gh CLI authenticated, ANTHROPIC_API_KEY set."""
    import subprocess

    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            print("Error: gh CLI not authenticated. Run: gh auth login")
            sys.exit(1)
    except FileNotFoundError:
        print("Error: gh CLI not found. Install: https://cli.github.com/")
        sys.exit(1)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Warning: ANTHROPIC_API_KEY not set. Subagent stages will fail.")


def sanitize_path(path: str) -> str:
    """Sanitize a file path from GitHub API to prevent shell injection.

    Rejects paths with shell metacharacters, null bytes, or path traversal.
    """
    if not path:
        return path

    if "\x00" in path:
        raise ValueError(f"Path contains null byte: {path!r}")

    if ".." in path.split("/"):
        raise ValueError(f"Path contains traversal: {path!r}")

    dangerous = set(";|&$`\\!#")
    found = dangerous & set(path)
    if found:
        raise ValueError(f"Path contains dangerous characters {found}: {path!r}")

    return path
