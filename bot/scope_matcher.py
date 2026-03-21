"""Map changed files to scopes and select relevant rule sections."""

import re
from pathlib import Path

import yaml

import utils


def match_file_scopes(filepath: str, repo_name: str) -> set[str]:
    """Match a file path to scope names from config.

    Args:
        filepath: File path relative to repo root (e.g. "app/models/user.rb")
        repo_name: Repo name from config (e.g. "venture")

    Returns:
        Set of matching scope names (e.g. {"backend", "graphql"})
    """
    config = utils.load_config()
    matched = set()
    for repo in config.get("repos", []):
        if repo["name"] != repo_name:
            continue
        for scope in repo.get("scopes", []):
            if filepath.startswith(scope["path_prefix"]):
                matched.add(scope["name"])
    return matched


def collect_scopes_for_diff(changed_files: list[str], repo_name: str) -> set[str]:
    """Collect all matched scopes across all changed files.

    Args:
        changed_files: List of file paths from the PR diff
        repo_name: Repo name from config

    Returns:
        Set of all matched scope names
    """
    all_scopes = set()
    for filepath in changed_files:
        all_scopes |= match_file_scopes(filepath, repo_name)
    return all_scopes


def select_sections(matched_scopes: set[str]) -> list[Path]:
    """Select rule section files relevant to the matched scopes.

    Rules with scope "all" are always included.
    Rules with scope "fullstack" are included when any scope matched.
    Rules with a specific scope name are included when that scope matched.

    Args:
        matched_scopes: Set of scope names matched from the diff

    Returns:
        List of Paths to matching rule section markdown files
    """
    sections_dir = utils.get_project_root() / utils.load_config().get(
        "sections_output_dir", "rules/sections"
    )
    if not sections_dir.exists():
        return []

    selected = []
    for section_path in sorted(sections_dir.glob("*.md")):
        scope = _read_section_scope(section_path)
        if scope == "all":
            selected.append(section_path)
        elif scope == "fullstack" and matched_scopes:
            selected.append(section_path)
        elif scope in matched_scopes:
            selected.append(section_path)

    return selected


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _read_section_meta(path: Path) -> dict:
    """Read all metadata from a rule section's YAML frontmatter.

    Returns:
        Dict of frontmatter fields. Defaults: {"scope": "all", "risk_weight": "medium"}
    """
    defaults = {"scope": "all", "risk_weight": "medium"}
    text = path.read_text()
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return defaults
    try:
        meta = yaml.safe_load(match.group(1))
        if not isinstance(meta, dict):
            return defaults
        return {**defaults, **meta}
    except yaml.YAMLError:
        return defaults


def _read_section_scope(path: Path) -> str:
    """Read the scope from a rule section's YAML frontmatter."""
    return _read_section_meta(path)["scope"]


def _read_section_risk_weight(path: Path) -> str:
    """Read the risk_weight from a rule section's YAML frontmatter."""
    return _read_section_meta(path)["risk_weight"]


# Risk weight priority: critical > high > medium > low
_RISK_WEIGHT_ORDER = {"critical": 3, "high": 2, "medium": 1, "low": 0}

# Map max risk weight to PR risk level
_RISK_LEVEL_MAP = {3: "High", 2: "High", 1: "Medium", 0: "Low"}


def classify_risk(sections: list[Path]) -> str:
    """Classify PR risk level based on the risk_weight of matched rule sections.

    Returns the highest risk level across all matched sections:
        critical/high weight → "High"
        medium weight → "Medium"
        low weight (or no sections) → "Low"

    Args:
        sections: List of matched rule section file paths

    Returns:
        Risk level string: "High", "Medium", or "Low"
    """
    if not sections:
        return "Low"

    max_weight = 0
    for section_path in sections:
        weight = _read_section_risk_weight(section_path)
        max_weight = max(max_weight, _RISK_WEIGHT_ORDER.get(weight, 1))

    return _RISK_LEVEL_MAP.get(max_weight, "Medium")


def load_section_content(paths: list[Path]) -> str:
    """Load and concatenate rule section content (without frontmatter).

    Args:
        paths: List of rule section file paths

    Returns:
        Concatenated markdown content with section separators
    """
    parts = []
    for path in paths:
        text = path.read_text()
        match = _FRONTMATTER_RE.match(text)
        content = text[match.end():] if match else text
        content = content.strip()
        if content:
            parts.append(content)
    return "\n\n---\n\n".join(parts)
