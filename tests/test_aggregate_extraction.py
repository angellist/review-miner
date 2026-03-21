"""Tests for aggregate_extraction.py merge/aggregation logic."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


def write_yaml(path: Path, data: dict) -> None:
    """Helper to write YAML files for test fixtures."""
    with open(path, "w") as f:
        yaml.dump(data, f)


def make_extraction_dir(tmp_path: Path, identifier: str = "test_run") -> Path:
    """Create working_dir/extraction structure and return extraction_dir."""
    extraction_dir = tmp_path / identifier / "extraction"
    extraction_dir.mkdir(parents=True)
    return extraction_dir


def run_aggregate(identifier, id_prefix="ext", working_dir_root=None,
                  existing_insights=None):
    """Run main() with mocked filesystem and capture saved insights.

    Returns (saved_insights, call_count) where saved_insights is the list
    passed to save_insights, or None if save_insights was never called.
    """
    saved = {}

    def fake_save_insights(insights):
        saved["insights"] = insights

    argv = ["aggregate_extraction.py", identifier]
    if id_prefix != "ext":
        argv += ["--id-prefix", id_prefix]

    with (
        patch("aggregate_extraction.get_working_dir",
              return_value=working_dir_root / identifier),
        patch("aggregate_extraction.load_insights",
              return_value=existing_insights or []),
        patch("aggregate_extraction.save_insights", side_effect=fake_save_insights),
        patch("aggregate_extraction.load_yaml", side_effect=yaml_loader),
        patch("aggregate_extraction.save_yaml"),
        patch("aggregate_extraction.load_template", return_value="{batch_number}"),
        patch("aggregate_extraction.get_project_root", return_value=Path("/fake")),
        patch("aggregate_extraction.get_data_dir", return_value=Path("/fake/data")),
        patch("sys.argv", argv),
    ):
        from aggregate_extraction import main
        main()

    return saved.get("insights")


def yaml_loader(path: Path) -> dict:
    """Load real YAML from tmp_path fixtures."""
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBasicAggregation:
    """Batch insights get merged into existing insights with correct structure."""

    def test_single_batch_merged_into_empty(self, tmp_path):
        extraction_dir = make_extraction_dir(tmp_path)

        write_yaml(extraction_dir / "batch_1_input.yaml", {
            "threads": [{"thread_id": 100, "repo": "acme/api"}],
        })
        write_yaml(extraction_dir / "batch_1.yaml", {
            "batch_number": 1,
            "insights": [
                {"thread_id": 100, "pr": "https://github.com/acme/api/pull/1",
                 "content": "Good error handling pattern"},
            ],
            "processed": 1, "insights_extracted": 1, "skipped": 0,
        })

        result = run_aggregate("test_run", working_dir_root=tmp_path)

        assert result is not None
        assert len(result) == 1
        insight = result[0]
        assert insight["id"] == "ext_100_0"
        assert insight["thread_id"] == 100
        assert insight["pr"] == "https://github.com/acme/api/pull/1"
        assert insight["status"] == "pending"
        assert insight["content"] == "Good error handling pattern"
        assert insight["topic"] is None
        assert insight["retry_count"] == 0
        assert insight["last_error"] is None

    def test_new_insights_appended_to_existing(self, tmp_path):
        extraction_dir = make_extraction_dir(tmp_path)

        write_yaml(extraction_dir / "batch_1_input.yaml", {
            "threads": [{"thread_id": 200}],
        })
        write_yaml(extraction_dir / "batch_1.yaml", {
            "batch_number": 1,
            "insights": [
                {"thread_id": 200, "pr": "pr-url", "content": "new insight"},
            ],
            "processed": 1, "insights_extracted": 1, "skipped": 0,
        })

        existing = [{"id": "ext_50_0", "thread_id": 50, "status": "pending"}]
        result = run_aggregate("test_run", working_dir_root=tmp_path,
                               existing_insights=existing)

        assert len(result) == 2
        assert result[0]["id"] == "ext_50_0"  # existing preserved
        assert result[1]["id"] == "ext_200_0"  # new appended


class TestDuplicateDetection:
    """Insights whose generated ID already exists are skipped."""

    def test_duplicate_id_not_added(self, tmp_path):
        extraction_dir = make_extraction_dir(tmp_path)

        write_yaml(extraction_dir / "batch_1_input.yaml", {
            "threads": [{"thread_id": 100}],
        })
        write_yaml(extraction_dir / "batch_1.yaml", {
            "batch_number": 1,
            "insights": [
                {"thread_id": 100, "pr": "pr-url", "content": "duplicate"},
            ],
            "processed": 1, "insights_extracted": 1, "skipped": 0,
        })

        existing = [{"id": "ext_100_0", "thread_id": 100, "status": "pending"}]
        result = run_aggregate("test_run", working_dir_root=tmp_path,
                               existing_insights=existing)

        # No new insights added, so save_insights is not called
        assert result is None


class TestMultipleInsightsPerThread:
    """Counter in ID increments for each insight from the same thread."""

    def test_counter_increments(self, tmp_path):
        extraction_dir = make_extraction_dir(tmp_path)

        write_yaml(extraction_dir / "batch_1_input.yaml", {
            "threads": [{"thread_id": 300}],
        })
        write_yaml(extraction_dir / "batch_1.yaml", {
            "batch_number": 1,
            "insights": [
                {"thread_id": 300, "pr": "pr-1", "content": "first"},
                {"thread_id": 300, "pr": "pr-1", "content": "second"},
                {"thread_id": 300, "pr": "pr-1", "content": "third"},
            ],
            "processed": 1, "insights_extracted": 3, "skipped": 0,
        })

        result = run_aggregate("test_run", working_dir_root=tmp_path)

        assert len(result) == 3
        assert result[0]["id"] == "ext_300_0"
        assert result[1]["id"] == "ext_300_1"
        assert result[2]["id"] == "ext_300_2"

    def test_counter_skips_past_duplicates(self, tmp_path):
        """When ext_300_0 exists, the first new insight from thread 300
        gets ID ext_300_0 (duplicate, skipped), then ext_300_1 is tried."""
        extraction_dir = make_extraction_dir(tmp_path)

        write_yaml(extraction_dir / "batch_1_input.yaml", {
            "threads": [{"thread_id": 300}],
        })
        write_yaml(extraction_dir / "batch_1.yaml", {
            "batch_number": 1,
            "insights": [
                {"thread_id": 300, "pr": "pr-1", "content": "dup"},
                {"thread_id": 300, "pr": "pr-1", "content": "new one"},
            ],
            "processed": 1, "insights_extracted": 2, "skipped": 0,
        })

        existing = [{"id": "ext_300_0", "thread_id": 300, "status": "pending"}]
        result = run_aggregate("test_run", working_dir_root=tmp_path,
                               existing_insights=existing)

        assert result is not None
        new_insights = [i for i in result if i["id"] != "ext_300_0"]
        assert len(new_insights) == 1
        assert new_insights[0]["id"] == "ext_300_1"


class TestSkippedThreads:
    """Skipped threads get recorded with status=skipped and are deduplicated."""

    def test_skipped_thread_recorded(self, tmp_path):
        extraction_dir = make_extraction_dir(tmp_path)

        write_yaml(extraction_dir / "batch_1_input.yaml", {
            "threads": [{"thread_id": 400}],
        })
        write_yaml(extraction_dir / "batch_1.yaml", {
            "batch_number": 1,
            "insights": [
                {"thread_id": 400, "skipped": True,
                 "reason": "No actionable insights"},
            ],
            "processed": 1, "insights_extracted": 0, "skipped": 1,
        })

        result = run_aggregate("test_run", working_dir_root=tmp_path)

        assert result is not None
        assert len(result) == 1
        skipped = result[0]
        assert skipped["id"] == "ext_400_skipped"
        assert skipped["status"] == "skipped"
        assert skipped["reason"] == "No actionable insights"
        assert skipped["thread_id"] == 400

    def test_skipped_thread_deduped_against_existing(self, tmp_path):
        extraction_dir = make_extraction_dir(tmp_path)

        write_yaml(extraction_dir / "batch_1_input.yaml", {
            "threads": [{"thread_id": 400}],
        })
        write_yaml(extraction_dir / "batch_1.yaml", {
            "batch_number": 1,
            "insights": [
                {"thread_id": 400, "skipped": True, "reason": "No insights"},
            ],
            "processed": 1, "insights_extracted": 0, "skipped": 1,
        })

        existing = [{"id": "ext_400_skipped", "thread_id": 400, "status": "skipped"}]
        result = run_aggregate("test_run", working_dir_root=tmp_path,
                               existing_insights=existing)

        # Duplicate skipped thread -> nothing new to save
        assert result is None


class TestMissingBatches:
    """Exits with error when result files are missing for input files."""

    def test_missing_batch_result_exits(self, tmp_path):
        extraction_dir = make_extraction_dir(tmp_path)

        # Two input files but only one result
        write_yaml(extraction_dir / "batch_1_input.yaml", {"threads": []})
        write_yaml(extraction_dir / "batch_2_input.yaml", {"threads": []})
        write_yaml(extraction_dir / "batch_1.yaml", {
            "batch_number": 1, "insights": [],
            "processed": 0, "insights_extracted": 0, "skipped": 0,
        })
        # batch_2.yaml intentionally missing

        with pytest.raises(SystemExit) as exc_info:
            run_aggregate("test_run", working_dir_root=tmp_path)
        assert exc_info.value.code == 1


class TestRepoMapping:
    """Repo field is populated from batch input thread data."""

    def test_repo_attached_from_input_threads(self, tmp_path):
        extraction_dir = make_extraction_dir(tmp_path)

        write_yaml(extraction_dir / "batch_1_input.yaml", {
            "threads": [
                {"thread_id": 500, "repo": "acme/backend"},
                {"thread_id": 501, "repo": "acme/frontend"},
            ],
        })
        write_yaml(extraction_dir / "batch_1.yaml", {
            "batch_number": 1,
            "insights": [
                {"thread_id": 500, "pr": "pr-500", "content": "backend insight"},
                {"thread_id": 501, "pr": "pr-501", "content": "frontend insight"},
            ],
            "processed": 2, "insights_extracted": 2, "skipped": 0,
        })

        result = run_aggregate("test_run", working_dir_root=tmp_path)

        assert result is not None
        by_thread = {i["thread_id"]: i for i in result}
        assert by_thread[500]["repo"] == "acme/backend"
        assert by_thread[501]["repo"] == "acme/frontend"

    def test_repo_none_when_not_in_input(self, tmp_path):
        extraction_dir = make_extraction_dir(tmp_path)

        write_yaml(extraction_dir / "batch_1_input.yaml", {
            "threads": [{"thread_id": 600}],  # no repo field
        })
        write_yaml(extraction_dir / "batch_1.yaml", {
            "batch_number": 1,
            "insights": [
                {"thread_id": 600, "pr": "pr-600", "content": "insight"},
            ],
            "processed": 1, "insights_extracted": 1, "skipped": 0,
        })

        result = run_aggregate("test_run", working_dir_root=tmp_path)

        assert result is not None
        assert result[0]["repo"] is None


class TestIdPrefix:
    """Custom --id-prefix changes the generated insight IDs."""

    def test_custom_prefix(self, tmp_path):
        extraction_dir = make_extraction_dir(tmp_path)

        write_yaml(extraction_dir / "batch_1_input.yaml", {
            "threads": [{"thread_id": 700}],
        })
        write_yaml(extraction_dir / "batch_1.yaml", {
            "batch_number": 1,
            "insights": [
                {"thread_id": 700, "pr": "pr-700", "content": "insight"},
            ],
            "processed": 1, "insights_extracted": 1, "skipped": 0,
        })

        result = run_aggregate("test_run", id_prefix="domain",
                               working_dir_root=tmp_path)

        assert result is not None
        assert result[0]["id"] == "domain_700_0"
