#!/usr/bin/env python3
"""
Main entry point for al-pr-review pipeline.

Usage:
  python3 scripts/mine.py refresh --repo venture --since 2025-03-01
  python3 scripts/mine.py refresh --all --since 2025-03-01
  python3 scripts/mine.py extract --repo venture --since 2025-01-01 --scope backend
  python3 scripts/mine.py extract --all --since 2025-01-01
  python3 scripts/mine.py resume validate
  python3 scripts/mine.py status
  python3 scripts/mine.py pending
  python3 scripts/mine.py reset --stage extract --identifier venture_all_2025-03-01
"""

import argparse
import subprocess
import sys
from pathlib import Path

from utils import (
    generate_identifier,
    get_data_dir,
    get_processed_thread_ids,
    get_project_root,
    get_repo_names,
    get_working_dir,
    load_config,
    load_insights,
    load_library_topics,
    load_template,
    load_threads,
    preflight_check,
    save_insights,
    save_yaml,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine Best Practices from PR Review Threads")
    subparsers = parser.add_subparsers(dest="command")

    # Extract command
    extract_parser = subparsers.add_parser("extract", help="Start extraction pipeline")
    extract_parser.add_argument("--repo", help="Repo name from config (default: all repos)")
    extract_parser.add_argument("--all", action="store_true", dest="all_repos", help="Process all repos")
    extract_parser.add_argument(
        "--since", help="Process threads from PRs merged on or after DATE (YYYY-MM-DD, inclusive)"
    )
    extract_parser.add_argument(
        "--until", help="Process threads from PRs merged on or before DATE (inclusive; default: today)"
    )
    extract_parser.add_argument(
        "--scope", default="all", help="Filter by scope name from config.yaml, or 'all' (default)"
    )
    extract_parser.add_argument("--batch-size", type=int, default=30, help="Threads per batch (default: 30)")

    # Resume from stage
    resume_parser = subparsers.add_parser("resume", help="Resume from a stage")
    resume_parser.add_argument("stage", choices=["validate", "topics", "synthesize", "build"])
    resume_parser.add_argument("--identifier", help="Run identifier (default: most recent)")

    # Status commands
    subparsers.add_parser("status", help="Show overview of threads, insights, library")
    subparsers.add_parser("pending", help="Show what needs work at each stage")

    # Query command
    topic_parser = subparsers.add_parser("for-topic", help="Show all insights for a topic")
    topic_parser.add_argument("topic", help="Topic name")

    # Refresh command
    refresh_parser = subparsers.add_parser("refresh", help="Refresh threads from GitHub")
    refresh_parser.add_argument("--repo", help="Repo name from config (default: all repos)")
    refresh_parser.add_argument("--all", action="store_true", dest="all_repos", help="Refresh all repos")
    refresh_parser.add_argument("--since", help="Fetch PRs merged on or after DATE (YYYY-MM-DD, inclusive)")
    refresh_parser.add_argument("--until", help="Fetch PRs merged on or before DATE (inclusive; default: today)")
    refresh_parser.add_argument("--full", action="store_true", help="Full re-extraction (clear existing data)")

    # Run-all command (automated full pipeline)
    run_parser = subparsers.add_parser("run", help="Run full pipeline automatically")
    run_parser.add_argument("--repo", help="Repo name from config (default: all repos)")
    run_parser.add_argument("--all", action="store_true", dest="all_repos", help="Process all repos")
    run_parser.add_argument("--since", help="YYYY-MM-DD start date")
    run_parser.add_argument("--until", help="YYYY-MM-DD end date (default: today)")
    run_parser.add_argument("--skip-refresh", action="store_true", help="Skip GitHub refresh")
    run_parser.add_argument("--skip-extract", action="store_true", help="Skip extraction")
    run_parser.add_argument("--skip-synthesis", action="store_true", help="Skip synthesis")
    run_parser.add_argument("--resume", help="Resume existing run by identifier")
    run_parser.add_argument("--max-parallel", type=int, default=10, help="Max parallel claude processes")

    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset a stage for re-processing")
    reset_parser.add_argument("--stage", required=True, choices=["extract", "validate", "topics", "synthesize"],
                              help="Stage to reset")
    reset_parser.add_argument("--identifier", help="Run identifier (default: most recent)")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status()
    elif args.command == "pending":
        cmd_pending()
    elif args.command == "for-topic":
        cmd_for_topic(args.topic)
    elif args.command == "refresh":
        preflight_check()
        repo = None if args.all_repos else args.repo
        cmd_refresh(repo, args.since, args.until, args.full)
    elif args.command == "resume":
        cmd_resume(args.stage, args.identifier)
    elif args.command == "reset":
        cmd_reset(args.stage, args.identifier)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "extract" or args.command is None:
        since = getattr(args, "since", None)
        until = getattr(args, "until", None)
        scope = getattr(args, "scope", "all")
        batch_size = getattr(args, "batch_size", 30)
        repo = getattr(args, "repo", None)
        all_repos = getattr(args, "all_repos", False)
        if all_repos:
            repo = None
        cmd_extract(repo, since, until, scope, batch_size)


def cmd_status() -> None:
    """Show overview of threads, insights, library."""
    print("\n" + "=" * 60)
    print("AL PR Review - Status")
    print("=" * 60 + "\n")

    # Per-repo thread counts
    from utils import get_repo_data_dir
    for repo_name in get_repo_names():
        data_dir = get_repo_data_dir(repo_name)
        threads_file = data_dir / "threads.yaml"
        if threads_file.exists():
            from utils import load_yaml
            data = load_yaml(threads_file)
            count = len(data.get("threads", []))
            print(f"Threads ({repo_name}): {count:,}")
        else:
            print(f"Threads ({repo_name}): (not yet fetched)")

    # Shared insights
    insights = load_insights()
    if insights:
        by_status: dict[str, int] = {}
        by_repo: dict[str, int] = {}
        for i in insights:
            status = i.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1
            repo = i.get("repo", "unknown")
            by_repo[repo] = by_repo.get(repo, 0) + 1
        print(f"\nInsights: {len(insights):,} total")
        for status, count in sorted(by_status.items()):
            print(f"  - {status}: {count}")
        if len(by_repo) > 1:
            print("  By repo:")
            for repo, count in sorted(by_repo.items()):
                print(f"    - {repo}: {count}")
    else:
        print("\nInsights: (none yet)")

    # Library
    topics = load_library_topics()
    if topics:
        print(f"\nLibrary: {len(topics)} topics")
        for t in sorted(topics):
            print(f"  - {t}")
    else:
        print("\nLibrary: (no topics yet)")

    print()


def cmd_pending() -> None:
    """Show what needs work at each stage."""
    print("\n" + "=" * 60)
    print("AL PR Review - Pending Work")
    print("=" * 60 + "\n")

    insights = load_insights()

    pending_validation = [i for i in insights if i.get("status") == "pending"]
    print(f"Pending validation: {len(pending_validation)}")

    pending_topics = [i for i in insights if i.get("status") == "validated" and not i.get("topic")]
    print(f"Pending topic assignment: {len(pending_topics)}")

    with_topics = [i for i in insights if i.get("status") == "validated" and i.get("topic")]
    existing_topics = set(load_library_topics())

    insights_by_topic: dict[str, list] = {}
    for i in with_topics:
        topic = i["topic"]
        if topic not in insights_by_topic:
            insights_by_topic[topic] = []
        insights_by_topic[topic].append(i)

    new_topics = set(insights_by_topic.keys()) - existing_topics
    if new_topics:
        print(f"New topics to synthesize: {len(new_topics)}")
        for t in sorted(new_topics):
            print(f"  - {t} ({len(insights_by_topic[t])} insights)")

    existing_with_insights = set(insights_by_topic.keys()) & existing_topics
    if existing_with_insights:
        print(f"Existing topics with new insights: {len(existing_with_insights)}")
        for t in sorted(existing_with_insights):
            print(f"  - {t} ({len(insights_by_topic[t])} insights)")

    print()


def cmd_for_topic(topic: str) -> None:
    """Show all insights for a topic."""
    insights = load_insights()
    matching = [i for i in insights if i.get("topic") == topic]

    print(f"\nInsights for topic '{topic}': {len(matching)}\n")
    for i in matching:
        print(f"ID: {i['id']}")
        print(f"Repo: {i.get('repo', '?')}")
        print(f"PR: {i['pr']}")
        print(f"Status: {i['status']}")
        print(f"Content:\n{i.get('content', '(none)')[:200]}...")
        print("-" * 40)


def cmd_refresh(repo: str | None, since: str | None, until: str | None, full: bool) -> None:
    """Refresh threads from GitHub."""
    from refresh import refresh_threads

    refresh_threads(repo, since, until, full)


def cmd_resume(stage: str, identifier: str | None) -> None:
    """Resume from a specific stage."""
    if not identifier:
        config = load_config()
        tmp_dir = get_project_root() / config.get("tmp_dir", "tmp")
        mining_dirs = sorted(tmp_dir.glob("mining_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not mining_dirs:
            print("Error: No previous mining runs found. Use 'extract' to start.")
            sys.exit(1)
        identifier = mining_dirs[0].name.replace("mining_", "")
        print(f"Resuming most recent run: {identifier}")

    print(f"\nResume from stage: {stage}")
    print(f"Identifier: {identifier}")

    scripts_dir = Path(__file__).parent
    stage_scripts = {
        "validate": scripts_dir / "aggregate_extraction.py",
        "topics": scripts_dir / "aggregate_validation.py",
        "synthesize": scripts_dir / "dispatch_synthesis.py",
        "build": scripts_dir / "build_sections.py",
    }

    script = stage_scripts.get(stage)
    if script is None:
        print(f"\nCannot resume from '{stage}'.")
        sys.exit(1)

    print(f"\nRunning: python3 {script.name} {identifier}")
    print("-" * 60)
    subprocess.run(["python3", str(script), identifier], check=False)


def cmd_reset(stage: str, identifier: str | None) -> None:
    """Reset a stage for re-processing."""
    if not identifier:
        config = load_config()
        tmp_dir = get_project_root() / config.get("tmp_dir", "tmp")
        mining_dirs = sorted(tmp_dir.glob("mining_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not mining_dirs:
            print("Error: No previous mining runs found.")
            sys.exit(1)
        identifier = mining_dirs[0].name.replace("mining_", "")

    print(f"\nResetting stage '{stage}' for run: {identifier}")

    working_dir = get_working_dir(identifier)

    if stage == "extract":
        extraction_dir = working_dir / "extraction"
        if extraction_dir.exists():
            for f in extraction_dir.glob("batch_*.yaml"):
                if "_input" not in f.stem:
                    f.unlink()
                    print(f"  Removed {f.name}")
        print("  Extraction outputs cleared. Re-run extraction subagents.")

    elif stage == "validate":
        validation_dir = working_dir / "validation"
        if validation_dir.exists():
            for f in validation_dir.glob("batch_*.yaml"):
                if "_input" not in f.stem:
                    f.unlink()
                    print(f"  Removed {f.name}")

        insights = load_insights()
        reverted = 0
        for insight in insights:
            if insight.get("status") in ("validated", "rejected"):
                insight["status"] = "pending"
                insight.pop("reason", None)
                reverted += 1
        if reverted:
            save_insights(insights)
            print(f"  Reverted {reverted} insights back to 'pending'")

    elif stage == "topics":
        topics_dir = working_dir / "topics"
        if topics_dir.exists():
            for f in topics_dir.glob("*.yaml"):
                f.unlink()
                print(f"  Removed {f.name}")

        insights = load_insights()
        cleared = 0
        for insight in insights:
            if insight.get("topic") and insight.get("status") == "validated":
                insight["topic"] = None
                cleared += 1
        if cleared:
            save_insights(insights)
            print(f"  Cleared topic from {cleared} insights")

    elif stage == "synthesize":
        insights = load_insights()
        reverted = 0
        for insight in insights:
            if insight.get("status") == "synthesized":
                insight["status"] = "validated"
                reverted += 1
        if reverted:
            save_insights(insights)
            print(f"  Reverted {reverted} insights from 'synthesized' to 'validated'")

    print("  Reset complete.")


def cmd_run(args) -> None:
    """Run full automated pipeline."""
    scripts_dir = Path(__file__).parent
    cmd = ["python3", str(scripts_dir / "run_pipeline.py")]
    if args.repo:
        cmd += ["--repo", args.repo]
    if args.all_repos:
        cmd += ["--all"]
    if args.since:
        cmd += ["--since", args.since]
    if getattr(args, "until", None):
        cmd += ["--until", args.until]
    if args.skip_refresh:
        cmd += ["--skip-refresh"]
    if args.skip_extract:
        cmd += ["--skip-extract"]
    if args.skip_synthesis:
        cmd += ["--skip-synthesis"]
    if args.resume:
        cmd += ["--resume", args.resume]
    if args.max_parallel:
        cmd += ["--max-parallel", str(args.max_parallel)]

    env = {**__import__("os").environ, "PYTHONUNBUFFERED": "1"}
    subprocess.run(cmd, cwd=str(scripts_dir), env=env, check=False)


def cmd_extract(repo: str | None, since: str | None, until: str | None, scope: str, batch_size: int) -> None:
    """Start extraction pipeline."""
    print("\n" + "=" * 60)
    print("AL PR Review - Extraction")
    print("=" * 60 + "\n")

    if not since:
        print("Error: --since is required for extraction")
        print("Usage: python3 scripts/mine.py extract --repo venture --since 2025-01-01")
        sys.exit(1)

    print("Loading threads...")
    print(f"  --repo: {repo or 'all'}")
    print(f"  --since: {since}")
    print(f"  --until: {until or 'today'}")
    print(f"  --scope: {scope}")
    print()

    threads = load_threads(repo=repo, since=since, until=until, scope=scope)
    print(f"Found {len(threads):,} threads matching filters")

    # Filter out already processed
    processed_ids = get_processed_thread_ids()
    unprocessed = [t for t in threads if t["thread_id"] not in processed_ids]
    print(f"Already processed: {len(threads) - len(unprocessed):,}")
    print(f"New threads to process: {len(unprocessed):,}")

    if not unprocessed:
        print("\nNo new threads to process.")
        return

    # Create batches
    batches = []
    for i in range(0, len(unprocessed), batch_size):
        batch = unprocessed[i : i + batch_size]
        batches.append(batch)

    print(f"\nCreated {len(batches)} batches of ~{batch_size} threads each")

    # Generate identifier and working directory
    identifier = generate_identifier(repo, scope)
    working_dir = get_working_dir(identifier)
    working_dir.mkdir(parents=True, exist_ok=True)

    # Save batches
    extraction_dir = working_dir / "extraction"
    extraction_dir.mkdir(exist_ok=True)

    for i, batch in enumerate(batches, 1):
        batch_data = {"batch_number": i, "thread_count": len(batch), "threads": batch}
        save_yaml(extraction_dir / f"batch_{i}_input.yaml", batch_data)

    print(f"\nWorking directory: {working_dir}")
    print(f"Batch inputs saved to: {extraction_dir}")

    # Output extraction task prompts
    print("\n" + "=" * 60)
    print("Step 2: Launch extraction subagents")
    print("=" * 60 + "\n")

    print("Copy and launch these Task prompts (can be run in parallel):\n")

    template = load_template("extraction_task.md")
    project_root = get_project_root()

    for i, batch in enumerate(batches, 1):
        filled = template.format(
            batch_number=i,
            total_batches=len(batches),
            identifier=identifier,
            thread_ids=", ".join(str(t["thread_id"]) for t in batch[:5]) + ("..." if len(batch) > 5 else ""),
            thread_count=len(batch),
            input_file=extraction_dir / f"batch_{i}_input.yaml",
            output_file=extraction_dir / f"batch_{i}.yaml",
            prompt_file=project_root / "references" / "prompts" / "extraction_prompt.md",
        )
        print("-" * 60)
        print(filled)
        print()

    print("-" * 60)
    print("\nAfter all extraction subagents complete, run:")
    print(f"  python3 scripts/aggregate_extraction.py {identifier}")
    print()


if __name__ == "__main__":
    main()
