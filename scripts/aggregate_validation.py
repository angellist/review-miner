#!/usr/bin/env python3
"""
Aggregate validation batch results into insights.yaml and output topic assignment prompt.

Usage:
  python3 scripts/aggregate_validation.py {identifier}

Example:
  python3 scripts/aggregate_validation.py backend_2025-01-29
"""

import argparse
import sys

from utils import (
    get_data_dir,
    get_project_root,
    get_working_dir,
    load_insights,
    load_library_topics,
    load_template,
    load_yaml,
    save_insights,
    save_yaml,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate validation batch results")
    parser.add_argument("identifier", help="Mining run identifier (e.g., backend_2025-01-29)")
    args = parser.parse_args()

    identifier = args.identifier
    working_dir = get_working_dir(identifier)
    validation_dir = working_dir / "validation"

    if not validation_dir.exists():
        print(f"Error: Validation directory not found: {validation_dir}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"Aggregating Validation Results - {identifier}")
    print("=" * 60 + "\n")

    # Load all batch files
    batch_files = sorted(validation_dir.glob("batch_*.yaml"))
    batch_files = [f for f in batch_files if "_input" not in f.stem]

    # Verify batch completeness
    input_files = sorted(validation_dir.glob("batch_*_input.yaml"))
    expected_batches = len(input_files)
    actual_batches = len(batch_files)

    if actual_batches < expected_batches:
        print("Error: Missing validation batches!")
        print(f"  Expected: {expected_batches} batches (from batch_*_input.yaml files)")
        print(f"  Found: {actual_batches} result files (batch_*.yaml)")
        missing = set(f.stem.replace("_input", "") for f in input_files) - set(f.stem for f in batch_files)
        for m in sorted(missing):
            print(f"  Missing: {m}.yaml")
        print("\nRun missing validation batches before aggregating.")
        sys.exit(1)

    if not batch_files:
        print(f"Error: No batch result files found in {validation_dir}")
        print("Expected files like: batch_1.yaml, batch_2.yaml, etc.")
        sys.exit(1)

    print(f"Found {len(batch_files)} batch files")

    # Load and collect rejections
    all_rejections = {}
    total_rejections = 0

    for batch_file in batch_files:
        print(f"  Loading {batch_file.name}...")
        batch_data = load_yaml(batch_file)

        batch_num = batch_data.get("batch_number", "?")
        rejections = batch_data.get("rejections", [])

        print(f"    Batch {batch_num}: {len(rejections)} rejections")
        total_rejections += len(rejections)

        for rejection in rejections:
            insight_id = rejection.get("insight_id")
            reason = rejection.get("reason", "No reason provided")
            if not insight_id:
                print("    Warning: Rejection missing insight_id, skipping")
                continue
            all_rejections[insight_id] = reason

    print(f"\nTotal rejections across all batches: {total_rejections}")

    # Load existing insights
    print("\nLoading insights.yaml...")
    insights = load_insights()
    print(f"  Found {len(insights)} total insights")

    # Update insights with validation results
    pending_count = 0
    validated_count = 0
    rejected_count = 0

    for insight in insights:
        if insight.get("status") == "pending":
            pending_count += 1
            insight_id = insight["id"]

            if insight_id in all_rejections:
                insight["status"] = "rejected"
                insight["reason"] = all_rejections[insight_id]
                rejected_count += 1
            else:
                insight["status"] = "validated"
                validated_count += 1

    print("\nValidation results:")
    print(f"  Insights processed: {pending_count}")
    print(f"  Validated: {validated_count}")
    print(f"  Rejected: {rejected_count}")

    if pending_count == 0:
        print("\nNo pending insights found. insights.yaml unchanged.")
        print("\nValidation aggregation complete!")
        return

    # Save updated insights
    save_insights(insights)
    print("\nUpdated insights.yaml with validation results")

    # Prepare topic assignment prompts
    print("\n" + "=" * 60)
    print("Step 3: Launch topic assignment subagent(s)")
    print("=" * 60 + "\n")

    pending_topics = [i for i in insights if i.get("status") == "validated" and i.get("topic") is None]

    if not pending_topics:
        print("No validated insights pending topic assignment.")
        print("\nValidation aggregation complete!")
        return

    print(f"Found {len(pending_topics)} validated insights pending topic assignment")

    template = load_template("topic_assignment_task.md")
    project_root = get_project_root()
    insights_file = get_data_dir() / "insights.yaml"
    existing_topics = ", ".join(sorted(load_library_topics()))

    # Batch insights (<=200 per batch)
    topic_batch_size = 200
    batches = []
    for i in range(0, len(pending_topics), topic_batch_size):
        batches.append(pending_topics[i : i + topic_batch_size])

    topics_dir = working_dir / "topics"
    topics_dir.mkdir(exist_ok=True)

    for i, batch in enumerate(batches, 1):
        batch_data = {"batch_number": i, "insight_ids": [insight["id"] for insight in batch]}
        save_yaml(topics_dir / f"batch_{i}_input.yaml", batch_data)

    print(f"Created {len(batches)} topic batch(es) of <={topic_batch_size} insights each")
    print(f"Existing topics: {existing_topics}")

    print("\nCopy and launch these Task prompts (can be run in parallel):\n")

    for i, batch in enumerate(batches, 1):
        filled = template.format(
            batch_number=i,
            total_batches=len(batches),
            prompt_file=project_root / "references" / "prompts" / "topic_assignment_prompt.md",
            insights_file=insights_file,
            input_file=topics_dir / f"batch_{i}_input.yaml",
            existing_topics=existing_topics,
            output_file=topics_dir / f"batch_{i}.yaml",
        )
        print("-" * 60)
        print(filled)
        print()

    print("-" * 60)
    if len(batches) == 1:
        print("\nAfter topic assignment subagent completes, copy its output to:")
        print(f"  {working_dir / 'topics.yaml'}")
    else:
        print("\nAfter all topic assignment subagents complete, merge their outputs into:")
        print(f"  {working_dir / 'topics.yaml'}")
        print("  (Deduplicate any overlapping __new__: topic proposals)")
    print("\nThen run:")
    print(f"  python3 scripts/dispatch_synthesis.py {identifier}")
    print()


if __name__ == "__main__":
    main()
