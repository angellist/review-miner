#!/usr/bin/env python3
"""
Generate review rules from library YAML by producing subagent Task prompts.

Usage:
  python3 scripts/build_bugbot.py

Reads from: code_insights/library/{topic}.yaml
Targets: configured in config.yaml
"""

import sys
from pathlib import Path

from utils import get_data_dir, get_project_root, load_config, load_template, load_yaml

config = load_config()
TARGETS = {}
for scope in config.get("scopes", []):
    if scope.get("rules_target"):
        TARGETS[scope["name"]] = scope["rules_target"]


def count_practices_by_scope(library_dir: Path) -> dict[str, int]:
    """Count total practices per scope across all library files."""
    counts: dict[str, int] = {}
    for yaml_file in sorted(library_dir.glob("*.yaml")):
        data = load_yaml(yaml_file)
        scope = data.get("scope", config.get("default_scope", "all"))
        practices = data.get("practices", [])
        counts[scope] = counts.get(scope, 0) + len(practices)
    return counts


def main() -> None:
    project_root = get_project_root()
    library_dir = get_data_dir() / "library"

    if not library_dir.exists():
        print(f"Error: Library directory not found: {library_dir}")
        sys.exit(1)

    template = load_template("bugbot_build_task.md")
    prompt_file = project_root / "references" / "prompts" / "bugbot_build_prompt.md"

    scope_counts = count_practices_by_scope(library_dir)

    print("\n" + "=" * 60)
    print("Building Review Rules from Library")
    print("=" * 60 + "\n")

    print("Practices by target:")
    for scope, target_path in TARGETS.items():
        count = scope_counts.get(scope, 0)
        print(f"  {target_path}: {count} practices")

    print("\nCopy and launch these Task prompts (can be run in parallel):\n")

    for scope, target_path in TARGETS.items():
        target_file = project_root / target_path
        filled = template.format(
            scope=scope,
            prompt_file=prompt_file,
            library_dir=library_dir,
            target_file=target_file,
            root_bugbot_file=project_root / config.get("rules_dedup_file", "rules/ROOT.md"),
        )
        print("-" * 60)
        print(filled)
        print()

    print("-" * 60)
    print("\nAfter subagents complete, review the generated rules files.")
    print()


if __name__ == "__main__":
    main()
