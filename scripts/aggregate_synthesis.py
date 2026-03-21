#!/usr/bin/env python3
"""Aggregate synthesis results and mark insights as synthesized.

Run this AFTER reviewing synthesis output and confirming library updates are correct.

Usage:
    python3 scripts/aggregate_synthesis.py {identifier}

Example:
    python3 scripts/aggregate_synthesis.py backend_2025-01-29
"""

import sys

from utils import get_data_dir, load_yaml, save_yaml


def aggregate_synthesis(identifier: str) -> None:
    """Mark all validated insights with topics as synthesized."""
    print("\n" + "=" * 60)
    print(f"Aggregating Synthesis Results - {identifier}")
    print("=" * 60 + "\n")

    # Load insights
    insights_file = get_data_dir() / "insights.yaml"
    if not insights_file.exists():
        print("Error: insights.yaml not found")
        sys.exit(1)

    data = load_yaml(insights_file)
    insights = data.get("insights", [])

    # Find validated insights with topics assigned
    updated = 0
    for insight in insights:
        if insight.get("status") in ("validated", "topic_assigned") and insight.get("topic"):
            insight["status"] = "synthesized"
            updated += 1

    if updated == 0:
        print("No insights to mark as synthesized.")
        print("(All validated insights either have no topic or are already synthesized)")
        return

    # Save updated insights
    save_yaml(insights_file, data)
    print(f"Marked {updated} insights as synthesized")

    # Show summary by topic
    by_topic: dict[str, int] = {}
    for insight in insights:
        if insight.get("status") == "synthesized":
            topic = insight.get("topic", "unknown")
            by_topic[topic] = by_topic.get(topic, 0) + 1

    print("\nSynthesized insights by topic:")
    for topic in sorted(by_topic.keys()):
        print(f"  {topic}: {by_topic[topic]}")

    print("\n" + "=" * 60)
    print("Step 10: Build markdown files")
    print("=" * 60)
    print("\nRun:")
    print("  python3 scripts/build_sections.py")
    print("  python3 scripts/build_bugbot.py")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/aggregate_synthesis.py {identifier}")
        print("Example: python3 scripts/aggregate_synthesis.py backend_2025-01-29")
        sys.exit(1)

    identifier = sys.argv[1]
    aggregate_synthesis(identifier)


if __name__ == "__main__":
    main()
