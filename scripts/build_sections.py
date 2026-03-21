#!/usr/bin/env python3
"""
Transform library YAML files into markdown section references.

Usage:
  python3 scripts/build_sections.py

Reads from: code_insights/library/{topic}.yaml
Writes to: configured sections_output_dir (see config.yaml)
"""

import sys

from utils import get_data_dir, get_project_root, load_config, load_yaml, validate_safe_name


def format_topic_title(topic: str) -> str:
    """Convert topic slug to title case (e.g., 'error_handling' -> 'Error Handling')."""
    return topic.replace("_", " ").title()


def format_sources(sources: list[int]) -> str:
    """Format PR sources as italicized list."""
    if not sources:
        return ""
    pr_list = ", ".join([f"PR #{pr}" for pr in sources])
    return f"_Sources: {pr_list}_"


def build_section(topic: str, scope: str, practices: list[dict]) -> str:
    """Build markdown section content from practices."""
    lines = []

    lines.append("---")
    lines.append(f"scope: {scope}")
    lines.append("---")
    lines.append("")

    lines.append(f"# {format_topic_title(topic)}")
    lines.append("")

    for practice in practices:
        title = practice.get("title", "").strip()
        content = practice.get("content", "").strip()
        sources = practice.get("sources", [])

        if not title or not content:
            continue

        lines.append(f"### {title}")
        lines.append("")
        lines.append(content)
        lines.append("")

        if sources:
            lines.append(format_sources(sources))
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    project_root = get_project_root()
    library_dir = get_data_dir() / "library"
    config = load_config()
    output_dir = project_root / config.get("sections_output_dir", "rules/sections")

    if not library_dir.exists():
        print(f"Error: Library directory not found: {library_dir}")
        print("No library YAML files to process.")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    yaml_files = sorted(library_dir.glob("*.yaml"))

    if not yaml_files:
        print(f"No library YAML files found in {library_dir}")
        sys.exit(0)

    print("\n" + "=" * 60)
    print("Building Section References from Library")
    print("=" * 60 + "\n")

    processed_count = 0
    skipped_count = 0

    for yaml_file in yaml_files:
        topic = validate_safe_name(yaml_file.stem, "topic")
        print(f"Processing {topic}...")

        data = load_yaml(yaml_file)

        if "topic" not in data:
            print("  Warning: Missing 'topic' field, skipping")
            skipped_count += 1
            continue

        practices = data.get("practices", [])
        scope = data.get("scope", config.get("default_scope", "all"))

        if not practices:
            print("  Skipped: No practices defined")
            skipped_count += 1
            continue

        section_content = build_section(topic, scope, practices)

        output_file = output_dir / f"{topic}.md"
        output_file.write_text(section_content)

        print(f"  Created: {output_file}")
        processed_count += 1

    print("\n" + "=" * 60)
    print(f"Processed: {processed_count} topics")
    print(f"Skipped: {skipped_count} topics")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
