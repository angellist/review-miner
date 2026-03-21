"""Tests for the validation merge logic in aggregate_validation."""

from pathlib import Path

import pytest
import yaml

from aggregate_validation import main


class TestAggregateValidation:
    """Tests for the insight status update logic in main()."""

    def _setup(self, monkeypatch, tmp_path, insights, batch_results):
        """Set up filesystem and mocks, then run main().

        Args:
            insights: list of insight dicts (the "pending" pool)
            batch_results: list of dicts, each written as a batch_N.yaml file.
                           Pass None to skip creating batch result files.

        Returns the insights list (mutated in place by main()) and a dict
        tracking whether save_insights was called.
        """
        working_dir = tmp_path / "working" / "test_run"
        validation_dir = working_dir / "validation"
        validation_dir.mkdir(parents=True)

        # Always create input files so completeness check passes
        num_batches = len(batch_results) if batch_results is not None else 1
        for i in range(1, num_batches + 1):
            input_file = validation_dir / f"batch_{i}_input.yaml"
            input_file.write_text(yaml.dump({"batch_number": i, "insight_ids": []}))

        # Create batch result files
        if batch_results is not None:
            for i, batch_data in enumerate(batch_results, 1):
                result_file = validation_dir / f"batch_{i}.yaml"
                result_file.write_text(yaml.dump(batch_data))

        monkeypatch.setattr(
            "aggregate_validation.get_working_dir", lambda identifier: working_dir
        )
        monkeypatch.setattr("aggregate_validation.load_insights", lambda: insights)

        save_tracker = {"called": False, "data": None}

        def fake_save(data):
            save_tracker["called"] = True
            save_tracker["data"] = data

        monkeypatch.setattr("aggregate_validation.save_insights", fake_save)

        # Stub out template/topic machinery so main() doesn't crash after save
        monkeypatch.setattr(
            "aggregate_validation.load_template", lambda name: "{batch_number}{total_batches}{prompt_file}{insights_file}{input_file}{existing_topics}{output_file}"
        )
        monkeypatch.setattr(
            "aggregate_validation.get_project_root", lambda: tmp_path
        )
        monkeypatch.setattr(
            "aggregate_validation.get_data_dir", lambda: tmp_path / "data"
        )
        monkeypatch.setattr(
            "aggregate_validation.load_library_topics", lambda: ["topic_a"]
        )
        monkeypatch.setattr(
            "aggregate_validation.save_yaml", lambda path, data: None
        )

        monkeypatch.setattr("sys.argv", ["aggregate_validation.py", "test_run"])

        return save_tracker

    def test_all_pending_validated_when_no_rejections(self, monkeypatch, tmp_path):
        insights = [
            {"id": "ins-1", "status": "pending"},
            {"id": "ins-2", "status": "pending"},
        ]
        batch_results = [{"batch_number": 1, "rejections": []}]

        self._setup(monkeypatch, tmp_path, insights, batch_results)
        main()

        assert insights[0]["status"] == "validated"
        assert insights[1]["status"] == "validated"

    def test_rejected_insights_get_status_and_reason(self, monkeypatch, tmp_path):
        insights = [
            {"id": "ins-1", "status": "pending"},
            {"id": "ins-2", "status": "pending"},
            {"id": "ins-3", "status": "pending"},
        ]
        batch_results = [
            {
                "batch_number": 1,
                "rejections": [
                    {"insight_id": "ins-1", "reason": "Too vague"},
                    {"insight_id": "ins-3", "reason": "Duplicate"},
                ],
            }
        ]

        self._setup(monkeypatch, tmp_path, insights, batch_results)
        main()

        assert insights[0]["status"] == "rejected"
        assert insights[0]["reason"] == "Too vague"
        assert insights[1]["status"] == "validated"
        assert insights[2]["status"] == "rejected"
        assert insights[2]["reason"] == "Duplicate"

    def test_non_pending_insights_untouched(self, monkeypatch, tmp_path):
        insights = [
            {"id": "ins-1", "status": "validated"},
            {"id": "ins-2", "status": "rejected", "reason": "old reason"},
            {"id": "ins-3", "status": "pending"},
        ]
        batch_results = [
            {
                "batch_number": 1,
                "rejections": [{"insight_id": "ins-1", "reason": "Should not apply"}],
            }
        ]

        self._setup(monkeypatch, tmp_path, insights, batch_results)
        main()

        # Already-validated insight stays validated (not re-rejected)
        assert insights[0]["status"] == "validated"
        # Already-rejected insight keeps its old reason
        assert insights[1]["status"] == "rejected"
        assert insights[1]["reason"] == "old reason"
        # The pending one gets validated (ins-1 rejection doesn't match pending)
        assert insights[2]["status"] == "validated"

    def test_missing_batch_files_exits_with_error(self, monkeypatch, tmp_path):
        working_dir = tmp_path / "working" / "test_run"
        validation_dir = working_dir / "validation"
        validation_dir.mkdir(parents=True)

        # Create 2 input files but only 1 result file -> incomplete
        (validation_dir / "batch_1_input.yaml").write_text(yaml.dump({"batch_number": 1}))
        (validation_dir / "batch_2_input.yaml").write_text(yaml.dump({"batch_number": 2}))
        (validation_dir / "batch_1.yaml").write_text(yaml.dump({"batch_number": 1, "rejections": []}))

        monkeypatch.setattr(
            "aggregate_validation.get_working_dir", lambda identifier: working_dir
        )
        monkeypatch.setattr("sys.argv", ["aggregate_validation.py", "test_run"])

        with pytest.raises(SystemExit):
            main()

    def test_no_pending_insights_skips_save(self, monkeypatch, tmp_path):
        insights = [
            {"id": "ins-1", "status": "validated"},
            {"id": "ins-2", "status": "rejected", "reason": "stale"},
        ]
        batch_results = [{"batch_number": 1, "rejections": []}]

        save_tracker = self._setup(monkeypatch, tmp_path, insights, batch_results)
        main()

        assert save_tracker["called"] is False

    def test_rejections_across_multiple_batches(self, monkeypatch, tmp_path):
        insights = [
            {"id": "ins-1", "status": "pending"},
            {"id": "ins-2", "status": "pending"},
            {"id": "ins-3", "status": "pending"},
        ]
        batch_results = [
            {"batch_number": 1, "rejections": [{"insight_id": "ins-1", "reason": "Batch 1 reject"}]},
            {"batch_number": 2, "rejections": [{"insight_id": "ins-3", "reason": "Batch 2 reject"}]},
        ]

        self._setup(monkeypatch, tmp_path, insights, batch_results)
        main()

        assert insights[0]["status"] == "rejected"
        assert insights[0]["reason"] == "Batch 1 reject"
        assert insights[1]["status"] == "validated"
        assert insights[2]["status"] == "rejected"
        assert insights[2]["reason"] == "Batch 2 reject"

    def test_rejection_without_reason_gets_default(self, monkeypatch, tmp_path):
        insights = [{"id": "ins-1", "status": "pending"}]
        batch_results = [
            {"batch_number": 1, "rejections": [{"insight_id": "ins-1"}]}
        ]

        self._setup(monkeypatch, tmp_path, insights, batch_results)
        main()

        assert insights[0]["status"] == "rejected"
        assert insights[0]["reason"] == "No reason provided"
