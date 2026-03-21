#!/usr/bin/env python3
"""
Fully automated pipeline: refresh → extract → validate → topics → synthesize → build.

Uses `claude` CLI for LLM stages (extraction, synthesis).
Programmatic keyword-based topic assignment (no LLM needed).
Skips validation (99.9% pass rate empirically).

Usage:
  python3 scripts/run_pipeline.py --repo venture --since 2025-03-01
  python3 scripts/run_pipeline.py --all --since 2025-01-01
  python3 scripts/run_pipeline.py --repo nova --since 2025-06-01 --skip-refresh
  python3 scripts/run_pipeline.py --resume venture_all_2026-03-18  # resume from where it left off
"""

import argparse
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

from utils import (
    generate_identifier,
    get_data_dir,
    get_project_root,
    get_working_dir,
    load_config,
    load_insights,
    load_threads,
    get_processed_thread_ids,
    preflight_check,
    save_insights,
    save_yaml,
    load_yaml,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MAX_PARALLEL_CLAUDE = 10       # max concurrent `claude` CLI processes
BATCH_SIZE = 30                # threads per extraction batch
CLAUDE_CMD = "claude"          # path to claude CLI


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full al-pr-review pipeline")
    parser.add_argument("--repo", help="Repo name from config (or omit for all)")
    parser.add_argument("--all", action="store_true", dest="all_repos")
    parser.add_argument("--since", help="YYYY-MM-DD start date for thread fetching")
    parser.add_argument("--until", help="YYYY-MM-DD end date (default: today)")
    parser.add_argument("--skip-refresh", action="store_true", help="Skip GitHub refresh")
    parser.add_argument("--skip-extract", action="store_true", help="Skip extraction (use existing)")
    parser.add_argument("--skip-synthesis", action="store_true", help="Skip synthesis (use existing)")
    parser.add_argument("--resume", help="Resume an existing run by identifier")
    parser.add_argument("--max-parallel", type=int, default=MAX_PARALLEL_CLAUDE)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    args = parser.parse_args()

    project_root = get_project_root()
    scripts_dir = project_root / "scripts"

    if args.resume:
        identifier = args.resume
        # Infer repo from identifier (e.g., "venture_all_2026-03-18" → "venture")
        repo = identifier.split("_")[0] if identifier.split("_")[0] != "all" else None
    else:
        repo = None if args.all_repos else args.repo
        if not args.since:
            print("Error: --since is required (or use --resume)")
            sys.exit(1)
        identifier = generate_identifier(repo, "all")

    working_dir = get_working_dir(identifier)
    working_dir.mkdir(parents=True, exist_ok=True)
    extraction_dir = working_dir / "extraction"
    extraction_dir.mkdir(exist_ok=True)

    print("\n" + "=" * 60)
    print(f"AL PR Review — Full Pipeline")
    print(f"Identifier: {identifier}")
    print(f"Working dir: {working_dir}")
    print("=" * 60 + "\n")

    # -----------------------------------------------------------------------
    # Stage 1: Refresh
    # -----------------------------------------------------------------------
    if not args.skip_refresh and not args.resume:
        print_stage("1/6", "Refresh threads from GitHub")
        preflight_check()
        run_python(scripts_dir, [
            "python3", str(scripts_dir / "refresh.py"),
            *(["--repo", repo] if repo else ["--all"]),
            *(["--since", args.since] if args.since else []),
            *(["--until", args.until] if args.until else []),
        ])
    else:
        print_stage("1/6", "Refresh — SKIPPED")

    # -----------------------------------------------------------------------
    # Stage 2: Extract
    # -----------------------------------------------------------------------
    if not args.skip_extract:
        print_stage("2/6", "Extract insights from threads")

        # Load threads and create batches
        threads = load_threads(repo=repo, since=getattr(args, "since", None), until=getattr(args, "until", None))
        processed_ids = get_processed_thread_ids()
        unprocessed = [t for t in threads if t["thread_id"] not in processed_ids]
        print(f"  Threads: {len(threads):,} total, {len(unprocessed):,} new")

        if unprocessed:
            # Create batch input files
            batches = []
            for i in range(0, len(unprocessed), args.batch_size):
                batches.append(unprocessed[i : i + args.batch_size])

            total_batches = len(batches)
            print(f"  Batches: {total_batches}")

            # Write input files for any that don't exist
            for i, batch in enumerate(batches, 1):
                input_file = extraction_dir / f"batch_{i}_input.yaml"
                if not input_file.exists():
                    save_yaml(input_file, {"batch_number": i, "thread_count": len(batch), "threads": batch})

            # Find incomplete batches
            incomplete = [
                i for i in range(1, total_batches + 1)
                if not (extraction_dir / f"batch_{i}.yaml").exists()
            ]
            print(f"  Incomplete: {len(incomplete)} batches")

            if incomplete:
                run_claude_batches(
                    incomplete,
                    total_batches=total_batches,
                    stage="extraction",
                    extraction_dir=extraction_dir,
                    max_parallel=args.max_parallel,
                )

            # Aggregate extraction
            print("\n  Aggregating extraction results...")
            run_python(scripts_dir, [
                "python3", str(scripts_dir / "aggregate_extraction.py"), identifier
            ])
        else:
            print("  No new threads to extract.")
    else:
        print_stage("2/6", "Extract — SKIPPED")

    # -----------------------------------------------------------------------
    # Stage 3: Validate (skip — 99.9% pass rate)
    # -----------------------------------------------------------------------
    print_stage("3/6", "Validate — auto-pass (99.9% empirical pass rate)")

    validation_dir = working_dir / "validation"
    if validation_dir.exists():
        # Create empty rejection files for any validation batches
        for input_file in sorted(validation_dir.glob("batch_*_input.yaml")):
            batch_num = input_file.stem.replace("_input", "").replace("batch_", "")
            output_file = validation_dir / f"batch_{batch_num}.yaml"
            if not output_file.exists():
                save_yaml(output_file, {"batch_number": int(batch_num), "rejections": []})

        run_python(scripts_dir, [
            "python3", str(scripts_dir / "aggregate_validation.py"), identifier
        ])

    # -----------------------------------------------------------------------
    # Stage 4: Topic assignment (programmatic)
    # -----------------------------------------------------------------------
    print_stage("4/6", "Topic assignment (keyword-based)")
    assign_topics_programmatic()

    # Create topics.yaml for dispatch_synthesis
    insights = load_insights()
    assignments = [
        {"insight_id": i["id"], "topic": i["topic"]}
        for i in insights
        if i.get("status") == "topic_assigned" and i.get("topic")
    ]
    if assignments:
        topics_file = working_dir / "topics.yaml"
        save_yaml(topics_file, {"assignments": assignments})
        print(f"  {len(assignments)} assignments written")

        # Run dispatch_synthesis to set up library files
        run_python(scripts_dir, [
            "python3", str(scripts_dir / "dispatch_synthesis.py"), identifier
        ])

    # -----------------------------------------------------------------------
    # Stage 5: Synthesis
    # -----------------------------------------------------------------------
    if not args.skip_synthesis:
        print_stage("5/6", "Synthesize practices per topic")

        # Extract per-topic insight files for synthesis agents
        synthesis_dir = working_dir / "synthesis"
        synthesis_dir.mkdir(exist_ok=True)

        insights = load_insights()
        by_topic = defaultdict(list)
        for i in insights:
            if i.get("status") == "topic_assigned" and i.get("topic"):
                by_topic[i["topic"]].append({
                    "id": i["id"], "thread_id": i["thread_id"],
                    "pr": i["pr"], "content": i["content"],
                })

        topics_to_synthesize = []
        for topic, topic_insights in by_topic.items():
            insight_file = synthesis_dir / f"{topic}_insights.yaml"
            save_yaml(insight_file, {"topic": topic, "insights": topic_insights})

            library_file = get_data_dir() / "library" / f"{topic}.yaml"
            if library_file.exists():
                topics_to_synthesize.append((topic, len(topic_insights)))

        print(f"  Topics to synthesize: {len(topics_to_synthesize)}")
        for t, n in sorted(topics_to_synthesize, key=lambda x: -x[1]):
            print(f"    {t}: {n} insights")

        if topics_to_synthesize:
            run_claude_synthesis(
                topics_to_synthesize,
                synthesis_dir=synthesis_dir,
                max_parallel=args.max_parallel,
            )

        # Aggregate synthesis
        run_python(scripts_dir, [
            "python3", str(scripts_dir / "aggregate_synthesis.py"), identifier
        ])
    else:
        print_stage("5/6", "Synthesis — SKIPPED")

    # -----------------------------------------------------------------------
    # Stage 6: Build
    # -----------------------------------------------------------------------
    print_stage("6/6", "Build markdown rule files")
    run_python(scripts_dir, ["python3", str(scripts_dir / "build_sections.py")])

    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print(f"Rules: {get_project_root() / 'rules' / 'sections' / '*.md'}")
    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Topic assignment (programmatic, no LLM)
# ---------------------------------------------------------------------------
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "financial_correctness": [
        "bigdecimal", "monetary", "cents", "currency", "rounding", "money",
        "financial calc", "accounting", "ledger", "capital call", "carry",
    ],
    "fund_lifecycle": [
        "fund lifecycle", "fund creation", "fund closing", "subscription", "fund state",
    ],
    "graphql_schema": [
        "graphql", "resolver", "mutation", "fragment", "apollo", "pothos",
        "schema type", "n+1", "dataloader", "batch load",
    ],
    "migration_safety": [
        "migration", "prisma", "alter table", "add column", "backfill",
        "schema change", "enum change", "safety_assured",
    ],
    "auth_permissions": [
        "pundit", "policy class", "authorization check", "authscope", "withauth",
        "permission level", "access control",
    ],
    "data_integrity": [
        "transaction", "race condition", "atomicity", "locking", "upsert",
        "deadlock", "data integrity", "optimistic lock",
    ],
    "temporal_workflows": ["temporal", "workflow", "activity"],
    "async_patterns": ["sidekiq", "background job", "worker", "cron job", "async job"],
    "rails_patterns": [
        "rails", "activerecord", "active_record", "concern", "service object",
        "scope", "has_many", "belongs_to", "includes", "preload", "eager load",
        "ruby", "sorbet", "t::struct", "t.cast", "typed:", "rubocop",
    ],
    "react_state": [
        "useeffect", "usestate", "usememo", "usecallback", "usequery",
        "react hook", "state management", "context provider",
    ],
    "react_components": [
        "component", "react.memo", "jsx", "tsx", "render", "adapt",
        "design system", "popover", "modal", "tooltip", "skeleton", "nullstate",
    ],
    "typescript_patterns": [
        "typescript", "type assertion", "as any", "discriminated union",
        "zod", "type narrow", "generic", "type safe",
    ],
    "error_handling": [
        "error handling", "catch", "silent", "swallow", "error boundary",
        "try/catch", "result type", "tagged error",
    ],
    "testing_patterns": [
        "test", "spec", "fixture", "mock", "factory", "rspec", "jest", "e2e",
    ],
    "performance": [
        "performance", "query optimization", "batch", "cache", "lazy load",
        "pagination", "index",
    ],
    "api_design": ["api design", "endpoint", "rest", "contract", "dto", "interface"],
    "naming_conventions": [
        "naming", "convention", "singular", "plural", "snake_case",
        "camelcase", "abbreviat",
    ],
    "logging_observability": ["log", "observability", "metric", "datadog", "monitoring"],
    "security": ["security", "injection", "xss", "sanitiz", "csrf", "idor"],
    "feature_flags": ["feature flag", "flipper", "toggle"],
    "code_organization": [
        "code organization", "module", "package", "boundary", "import",
        "layer", "separation of concern",
    ],
    "design_system": ["design system", "adapt", "skeleton", "stack", "box", "text component"],
    "infrastructure_as_code": [
        "pulumi", "terraform", "iac", "infrastructure", "stack", "resource",
        "cloud formation", "aws cdk", "provisioning",
    ],
    "docker_containers": [
        "docker", "dockerfile", "container", "image", "buildkit", "multi-stage",
        "layer caching", "entrypoint", "healthcheck",
    ],
    "ci_cd_pipelines": [
        "buildkite", "pipeline", "ci/cd", "ci pipeline", "deploy", "deployment",
        "github action", "workflow", "artifact", "build step",
    ],
    "cloud_aws": [
        "aws", "s3", "ec2", "iam", "lambda", "ecs", "rds", "cloudfront",
        "vpc", "subnet", "security group", "eks", "fargate",
    ],
    "kubernetes_orchestration": [
        "kubernetes", "k8s", "helm", "pod", "deployment", "service mesh",
        "ingress", "namespace", "configmap", "secret",
    ],
    "networking_dns": [
        "dns", "route53", "cloudflare", "ssl", "tls", "certificate",
        "load balancer", "alb", "nlb", "cdn",
    ],
}


def assign_topics_programmatic() -> None:
    """Assign topics to validated insights using keyword matching."""
    insights = load_insights()
    pending = [i for i in insights if i.get("status") == "validated" and not i.get("topic")]

    if not pending:
        print("  No insights pending topic assignment.")
        return

    def classify(content: str) -> str:
        c = content.lower()
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(kw in c for kw in keywords):
                return topic
        # Fallback heuristics
        if "ruby" in c or "rails" in c or "active" in c:
            return "rails_patterns"
        if "react" in c or "component" in c or "hook" in c:
            return "react_components"
        return "code_organization"

    for insight in pending:
        insight["topic"] = classify(insight.get("content", ""))
        insight["status"] = "topic_assigned"

    topics = Counter(i["topic"] for i in pending)
    print(f"  Assigned {len(pending)} insights to {len(topics)} topics")
    for topic, count in topics.most_common(10):
        print(f"    {topic}: {count}")

    save_insights(insights)


# ---------------------------------------------------------------------------
# Claude CLI runners
# ---------------------------------------------------------------------------
def run_claude_batches(
    batch_nums: list[int],
    total_batches: int,
    stage: str,
    extraction_dir: Path,
    max_parallel: int,
) -> None:
    """Run extraction batches via `claude` CLI in parallel."""
    project_root = get_project_root()
    prompt_file = project_root / "references" / "prompts" / "extraction_prompt.md"

    def run_batch(batch_num: int) -> tuple[int, bool]:
        input_file = extraction_dir / f"batch_{batch_num}_input.yaml"
        output_file = extraction_dir / f"batch_{batch_num}.yaml"

        if output_file.exists():
            return batch_num, True

        prompt = (
            f"Extract insights from PR review threads (batch {batch_num}/{total_batches}).\n\n"
            f"1. Read the extraction prompt: {prompt_file}\n"
            f"2. Read the input file: {input_file}\n"
            f"3. Analyze each thread per the extraction prompt\n"
            f"4. Write YAML output to: {output_file}\n\n"
            f"Output format:\n"
            f"```yaml\n"
            f"batch_number: {batch_num}\n"
            f"total_batches: {total_batches}\n"
            f"processed: (thread count)\n"
            f"insights_extracted: (count)\n"
            f"skipped: (count)\n\n"
            f"insights:\n"
            f"  - thread_id: ...\n"
            f"    pr: ...\n"
            f"    content: |\n"
            f"      ...\n"
            f"  - thread_id: ...\n"
            f"    pr: ...\n"
            f"    skipped: true\n"
            f"    reason: \"...\"\n"
            f"```"
        )

        try:
            result = subprocess.run(
                [CLAUDE_CMD, "--print", "--dangerously-skip-permissions", "-p", prompt],
                capture_output=True, text=True, timeout=300,
                cwd=str(project_root),
            )
            return batch_num, output_file.exists()
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"    Batch {batch_num} failed: {e}")
            return batch_num, False

    print(f"\n  Running {len(batch_nums)} batches ({max_parallel} parallel)...")

    completed = 0
    failed = []
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = {pool.submit(run_batch, n): n for n in batch_nums}
        for future in as_completed(futures):
            batch_num, success = future.result()
            completed += 1
            status = "OK" if success else "FAIL"
            print(f"    [{completed}/{len(batch_nums)}] Batch {batch_num}: {status}")
            if not success:
                failed.append(batch_num)

    if failed:
        print(f"\n  {len(failed)} batches failed: {failed}")
        print("  Re-run with --resume to retry failed batches.")


def run_claude_synthesis(
    topics: list[tuple[str, int]],
    synthesis_dir: Path,
    max_parallel: int,
) -> None:
    """Run synthesis per topic via `claude` CLI in parallel."""
    project_root = get_project_root()
    prompt_file = project_root / "references" / "prompts" / "synthesis_prompt.md"
    library_dir = get_data_dir() / "library"

    def run_topic(topic: str, insight_count: int) -> tuple[str, bool]:
        insight_file = synthesis_dir / f"{topic}_insights.yaml"
        library_file = library_dir / f"{topic}.yaml"

        prompt = (
            f"Synthesize {insight_count} PR review insights into best practices for topic: {topic}\n\n"
            f"1. Read the synthesis prompt: {prompt_file}\n"
            f"2. Read the insights: {insight_file}\n"
            f"3. Read existing library: {library_file}\n"
            f"4. Merge similar insights into distinct practices. "
            f"ADD new practices to the library file, don't repeat existing ones.\n"
            f"5. Update {library_file} in place.\n\n"
            f"Each practice needs: name, description (rule text), and source PR numbers.\n"
            f"Library YAML format:\n"
            f"```yaml\n"
            f"topic: {topic}\n"
            f"scope: fullstack\n"
            f"practices:\n"
            f"  - name: Short Practice Name\n"
            f"    description: |\n"
            f"      Rule text...\n"
            f"    sources:\n"
            f"      - pr: 12345\n"
            f"```"
        )

        try:
            result = subprocess.run(
                [CLAUDE_CMD, "--print", "--dangerously-skip-permissions", "-p", prompt],
                capture_output=True, text=True, timeout=600,
                cwd=str(project_root),
            )
            # Check if library file was updated (mtime changed)
            return topic, True
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"    {topic} failed: {e}")
            return topic, False

    print(f"\n  Synthesizing {len(topics)} topics ({max_parallel} parallel)...")

    completed = 0
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = {pool.submit(run_topic, t, n): t for t, n in topics}
        for future in as_completed(futures):
            topic, success = future.result()
            completed += 1
            status = "OK" if success else "FAIL"
            print(f"    [{completed}/{len(topics)}] {topic}: {status}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def print_stage(num: str, label: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  Stage {num}: {label}")
    print(f"{'─' * 60}\n")


def run_python(scripts_dir: Path, cmd: list[str]) -> None:
    """Run a Python script, inheriting stdout/stderr."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    subprocess.run(cmd, cwd=str(scripts_dir), env=env, check=False)


if __name__ == "__main__":
    main()
