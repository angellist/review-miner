#!/usr/bin/env python3
"""
Apply topic assignments to insights and dispatch synthesis subagent tasks per topic.

Usage:
  python3 scripts/dispatch_synthesis.py {identifier}

Example:
  python3 scripts/dispatch_synthesis.py backend_2025-01-29
"""

import argparse
import sys

from utils import (
    get_data_dir,
    get_project_root,
    get_working_dir,
    load_config,
    load_insights,
    load_template,
    load_yaml,
    save_insights,
    save_yaml,
    validate_safe_name,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply topic assignments and dispatch synthesis tasks")
    parser.add_argument("identifier", help="Mining run identifier (e.g., backend_2025-01-29)")
    args = parser.parse_args()

    identifier = args.identifier
    working_dir = get_working_dir(identifier)
    topics_file = working_dir / "topics.yaml"

    if not topics_file.exists():
        print(f"Error: Topics file not found: {topics_file}")
        print("Run topic assignment subagent first to generate topics.yaml")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"Applying Topic Assignments - {identifier}")
    print("=" * 60 + "\n")

    # Load topic assignments
    topics_data = load_yaml(topics_file)
    assignments = topics_data.get("assignments", [])

    if not assignments:
        print("No topic assignments found in topics.yaml")
        sys.exit(1)

    print(f"Found {len(assignments)} topic assignments")

    # Load existing insights
    insights = load_insights()
    insights_by_id = {insight["id"]: insight for insight in insights}

    new_topics: dict[str, dict] = {}
    topics_with_new_insights: dict[str, list[str]] = {}

    applied_count = 0
    missing_count = 0

    for assignment in assignments:
        insight_id = assignment.get("insight_id")
        topic = assignment.get("topic")

        if not insight_id or not topic:
            print("Warning: Invalid assignment missing insight_id or topic, skipping")
            continue

        if insight_id not in insights_by_id:
            print(f"Warning: Insight {insight_id} not found in insights.yaml, skipping")
            missing_count += 1
            continue

        insight = insights_by_id[insight_id]

        if topic.startswith("__new__:"):
            topic_name = validate_safe_name(topic[len("__new__:"):], "topic")
            new_topics[topic_name] = insight
            topic = topic_name
            print(f"  New topic detected: {topic_name}")
        else:
            validate_safe_name(topic, "topic")

        insight["topic"] = topic
        applied_count += 1

        if topic not in topics_with_new_insights:
            topics_with_new_insights[topic] = []
        topics_with_new_insights[topic].append(insight_id)

    print("\nTopic assignments applied:")
    print(f"  Applied: {applied_count}")
    print(f"  Missing insights: {missing_count}")
    print(f"  New topics: {len(new_topics)}")

    # Create new topic library files
    library_dir = get_data_dir() / "library"
    library_dir.mkdir(parents=True, exist_ok=True)

    for topic_name, sample_insight in new_topics.items():
        library_file = library_dir / f"{topic_name}.yaml"
        if library_file.exists():
            print(f"  Warning: Library file {topic_name}.yaml already exists, skipping creation")
            continue

        scope = _infer_scope_from_insight(sample_insight)

        new_library = {"topic": topic_name, "scope": scope, "practices": []}

        save_yaml(library_file, new_library)
        print(f"  Created library/{topic_name}.yaml (scope: {scope})")

    # Save updated insights
    save_insights(insights)
    print("\nUpdated insights.yaml with topic assignments")

    # Dispatch synthesis tasks
    print("\n" + "=" * 60)
    print("Step 4: Launch synthesis subagents (per topic)")
    print("=" * 60 + "\n")

    if not topics_with_new_insights:
        print("No topics with new insights to synthesize.")
        print("\nTopic assignment and synthesis dispatch complete!")
        return

    print(f"Found {len(topics_with_new_insights)} topics with new insights:")
    for topic, insight_ids in sorted(topics_with_new_insights.items()):
        print(f"  {topic}: {len(insight_ids)} insights")

    template = load_template("synthesis_task.md")
    project_root = get_project_root()
    insights_file = get_data_dir() / "insights.yaml"
    threads_file = get_data_dir() / "threads.yaml"

    print("\nCopy and launch these Task prompts (can be run in parallel):\n")

    for topic, insight_ids in sorted(topics_with_new_insights.items()):
        library_file = library_dir / f"{topic}.yaml"

        filled = template.format(
            topic=topic,
            prompt_file=project_root / "references" / "prompts" / "synthesis_prompt.md",
            library_file=library_file,
            insights_file=insights_file,
            threads_file=threads_file,
            insight_count=len(insight_ids),
        )

        print("-" * 60)
        print(filled)
        print("-" * 60)
        print()

    print("After all synthesis subagents complete:")
    print("  1. Review library file changes")
    print(f"  2. Run: python3 scripts/aggregate_synthesis.py {identifier}")
    print("  3. Run: python3 scripts/build_sections.py")
    print("  4. Run: python3 scripts/build_bugbot.py")
    print()


def _infer_scope_from_insight(insight: dict) -> str:
    """Infer scope from thread's file path using config scopes."""
    config = load_config()
    scopes = config.get("scopes", [])
    default_scope = config.get("default_scope", scopes[0]["name"] if scopes else "all")

    thread_id = insight.get("thread_id")
    if not thread_id:
        return default_scope

    threads_file = get_data_dir() / "threads.yaml"
    threads_data = load_yaml(threads_file)
    threads = threads_data.get("threads", [])

    for thread in threads:
        if thread.get("thread_id") == thread_id:
            path = thread.get("root", {}).get("path", "")
            for scope in scopes:
                if path.startswith(scope["path_prefix"]):
                    return scope["name"]
            break

    return default_scope


if __name__ == "__main__":
    main()
