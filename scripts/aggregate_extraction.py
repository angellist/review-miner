#!/usr/bin/env python3
"""
Aggregate extraction batch results into insights.yaml and output validation prompts.

Usage:
  python3 scripts/aggregate_extraction.py {identifier}

Example:
  python3 scripts/aggregate_extraction.py backend_2025-01-29
"""

import argparse
import sys
from collections import defaultdict

from utils import (
    get_data_dir,
    get_project_root,
    get_working_dir,
    load_insights,
    load_template,
    load_yaml,
    save_insights,
    save_yaml,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate extraction batch results")
    parser.add_argument("identifier", help="Mining run identifier (e.g., backend_2025-01-29)")
    parser.add_argument(
        "--id-prefix", default="ext", help="Insight ID prefix (default: ext) for domain-specific re-extraction"
    )
    args = parser.parse_args()

    identifier = args.identifier
    id_prefix = args.id_prefix
    working_dir = get_working_dir(identifier)
    extraction_dir = working_dir / "extraction"

    if not extraction_dir.exists():
        print(f"Error: Extraction directory not found: {extraction_dir}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"Aggregating Extraction Results - {identifier}")
    print("=" * 60 + "\n")

    # Load all batch files
    batch_files = sorted(extraction_dir.glob("batch_*.yaml"))
    batch_files = [f for f in batch_files if "_input" not in f.stem]

    # Verify batch completeness
    input_files = sorted(extraction_dir.glob("batch_*_input.yaml"))
    expected_batches = len(input_files)
    actual_batches = len(batch_files)

    if actual_batches < expected_batches:
        print("Error: Missing extraction batches!")
        print(f"  Expected: {expected_batches} batches (from batch_*_input.yaml files)")
        print(f"  Found: {actual_batches} result files (batch_*.yaml)")
        missing = set(f.stem.replace("_input", "") for f in input_files) - set(f.stem for f in batch_files)
        for m in sorted(missing):
            print(f"  Missing: {m}.yaml")
        print("\nRun missing extraction batches before aggregating.")
        sys.exit(1)

    if not batch_files:
        print(f"Error: No batch result files found in {extraction_dir}")
        print("Expected files like: batch_1.yaml, batch_2.yaml, etc.")
        sys.exit(1)

    print(f"Found {len(batch_files)} batch files")

    # Load and validate batches
    all_insights = []
    all_skipped = []
    total_processed = 0
    total_extracted = 0
    total_skipped = 0
    total_missing_threads = 0

    for batch_file in batch_files:
        print(f"  Loading {batch_file.name}...")
        batch_data = load_yaml(batch_file)

        if "insights" not in batch_data:
            print(f"    Warning: No 'insights' key in {batch_file.name}, skipping")
            continue

        batch_num = batch_data.get("batch_number", "?")
        processed = batch_data.get("processed", len(batch_data["insights"]))
        extracted = batch_data.get("insights_extracted", 0)
        skipped = batch_data.get("skipped", 0)

        print(f"    Batch {batch_num}: {processed} processed, {extracted} extracted, {skipped} skipped")

        total_processed += processed
        total_extracted += extracted
        total_skipped += skipped

        # Load batch input to verify thread completeness
        input_file = extraction_dir / f"batch_{batch_num}_input.yaml"
        expected_thread_ids = set()
        if input_file.exists():
            input_data = load_yaml(input_file)
            threads = input_data.get("threads", [])
            expected_thread_ids = set(t["thread_id"] for t in threads) if threads else set(input_data.get("thread_ids", []))

        # Build thread_id → repo lookup from batch input
        thread_repo_map = {}
        if input_file.exists():
            input_data_for_repo = load_yaml(input_file)
            for t in input_data_for_repo.get("threads", []):
                if "repo" in t:
                    thread_repo_map[t["thread_id"]] = t["repo"]

        seen_thread_ids = set()
        for insight in batch_data["insights"]:
            thread_id = insight.get("thread_id")
            if not thread_id:
                print("    Warning: Insight missing thread_id, skipping")
                continue

            seen_thread_ids.add(thread_id)

            # Attach repo from batch input thread data
            if thread_id in thread_repo_map:
                insight["repo"] = thread_repo_map[thread_id]

            if not insight.get("skipped") and not insight.get("pr"):
                print(f"    Warning: Insight {thread_id} missing pr field, skipping")
                continue

            if insight.get("skipped"):
                all_skipped.append(insight)
            else:
                all_insights.append(insight)

        if expected_thread_ids:
            missing_threads = expected_thread_ids - seen_thread_ids
            if missing_threads:
                print(f"    Warning: {len(missing_threads)} thread(s) missing from output!")
                for tid in sorted(missing_threads)[:5]:
                    print(f"      - {tid}")
                if len(missing_threads) > 5:
                    print(f"      ... and {len(missing_threads) - 5} more")
                total_missing_threads += len(missing_threads)

    print("\nTotals:")
    print(f"  Processed: {total_processed} threads")
    print(f"  Extracted: {total_extracted} insights")
    print(f"  Skipped: {total_skipped} threads")
    if total_missing_threads > 0:
        print(f"  Missing: {total_missing_threads} threads (not in batch output!)")

    # Load existing insights
    print("\nLoading existing insights.yaml...")
    existing_insights = load_insights()
    existing_ids = {i["id"] for i in existing_insights}
    print(f"  Found {len(existing_insights)} existing insights")

    # Merge new insights
    new_insights = []
    duplicate_count = 0
    thread_insight_counts: dict[int, int] = defaultdict(int)

    for insight in all_insights:
        thread_id = insight["thread_id"]
        pr = insight["pr"]
        content = insight.get("content", "")

        insight_id = f"{id_prefix}_{thread_id}_{thread_insight_counts[thread_id]}"

        if insight_id in existing_ids:
            duplicate_count += 1
            thread_insight_counts[thread_id] += 1
            continue

        new_insight = {
            "id": insight_id,
            "thread_id": thread_id,
            "pr": pr,
            "repo": insight.get("repo"),
            "status": "pending",
            "content": content,
            "topic": None,
            "retry_count": 0,
            "last_error": None,
        }
        new_insights.append(new_insight)
        thread_insight_counts[thread_id] += 1

    # Merge skipped threads
    existing_thread_ids = {i["thread_id"] for i in existing_insights if i.get("status") == "skipped"}
    for skipped in all_skipped:
        thread_id = skipped["thread_id"]
        reason = skipped.get("reason", "No reason provided")

        if thread_id in existing_thread_ids:
            duplicate_count += 1
            continue

        skipped_insight = {
            "id": f"{id_prefix}_{thread_id}_skipped",
            "thread_id": thread_id,
            "pr": skipped.get("pr"),
            "status": "skipped",
            "reason": reason,
        }
        new_insights.append(skipped_insight)
        existing_thread_ids.add(thread_id)

    print("\nMerging results:")
    print(f"  New insights to add: {len([i for i in new_insights if i.get('status') == 'pending'])}")
    print(f"  New skipped to add: {len([i for i in new_insights if i.get('status') == 'skipped'])}")
    print(f"  Duplicates (already in insights.yaml): {duplicate_count}")

    if not new_insights:
        print("\nNo new insights to add. insights.yaml unchanged.")
    else:
        merged_insights = existing_insights + new_insights
        save_insights(merged_insights)
        print(f"\nSaved {len(merged_insights)} total insights to insights.yaml")

    # Prepare validation prompts
    print("\n" + "=" * 60)
    print("Step 2: Launch validation subagents")
    print("=" * 60 + "\n")

    pending_insights = [i for i in (existing_insights + new_insights) if i.get("status") == "pending"]

    if not pending_insights:
        print("No pending insights to validate.")
        print("\nExtraction aggregation complete!")
        return

    print(f"Found {len(pending_insights)} insights pending validation")

    validation_batch_size = 20
    validation_batches = []
    for i in range(0, len(pending_insights), validation_batch_size):
        batch = pending_insights[i : i + validation_batch_size]
        validation_batches.append(batch)

    print(f"Created {len(validation_batches)} validation batches of ~{validation_batch_size} insights each")

    validation_dir = working_dir / "validation"
    validation_dir.mkdir(exist_ok=True)

    for i, batch in enumerate(validation_batches, 1):
        batch_data = {
            "batch_number": i,
            "insight_ids": [insight["id"] for insight in batch],
            "insight_count": len(batch),
        }
        save_yaml(validation_dir / f"batch_{i}_input.yaml", batch_data)

    print(f"\nValidation batch inputs saved to: {validation_dir}")

    # Output validation task prompts
    print("\nCopy and launch these Task prompts (can be run in parallel):\n")

    template = load_template("validation_task.md")
    project_root = get_project_root()
    insights_file = get_data_dir() / "insights.yaml"

    for i, batch in enumerate(validation_batches, 1):
        insight_ids = ", ".join([ins["id"] for ins in batch[:3]]) + ("..." if len(batch) > 3 else "")

        filled = template.format(
            batch_number=i,
            total_batches=len(validation_batches),
            identifier=identifier,
            insight_ids=insight_ids,
            insight_count=len(batch),
            input_file=validation_dir / f"batch_{i}_input.yaml",
            output_file=validation_dir / f"batch_{i}.yaml",
            prompt_file=project_root / "references" / "prompts" / "validation_prompt.md",
            insights_file=insights_file,
        )
        print("-" * 60)
        print(filled)
        print()

    print("-" * 60)
    print("\nAfter all validation subagents complete, run:")
    print(f"  python3 scripts/aggregate_validation.py {identifier}")
    print()


if __name__ == "__main__":
    main()
