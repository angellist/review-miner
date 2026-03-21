"""Tests for aggregate_synthesis module."""

from pathlib import Path

import pytest

from aggregate_synthesis import aggregate_synthesis


class TestAggregateSynthesis:
    def _run(self, monkeypatch, tmp_path, insights_data, file_exists=True):
        """Helper: sets up a fake insights.yaml and runs aggregate_synthesis.

        Returns the data that was passed to save_yaml (or None if save wasn't called).
        """
        insights_file = tmp_path / "data" / "insights.yaml"

        if file_exists:
            insights_file.parent.mkdir(parents=True, exist_ok=True)
            insights_file.touch()

        monkeypatch.setattr("aggregate_synthesis.get_data_dir", lambda: tmp_path / "data")

        loaded = {"called": False}
        saved = {"data": None}

        def fake_load_yaml(path):
            loaded["called"] = True
            return insights_data

        def fake_save_yaml(path, data):
            saved["data"] = data
            saved["path"] = path

        monkeypatch.setattr("aggregate_synthesis.load_yaml", fake_load_yaml)
        monkeypatch.setattr("aggregate_synthesis.save_yaml", fake_save_yaml)

        return saved

    def test_exits_when_insights_file_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr("aggregate_synthesis.get_data_dir", lambda: tmp_path / "data")
        with pytest.raises(SystemExit):
            aggregate_synthesis("test_run")

    def test_marks_validated_with_topic_as_synthesized(self, monkeypatch, tmp_path):
        data = {"insights": [
            {"id": 1, "status": "validated", "topic": "rails_patterns"},
            {"id": 2, "status": "validated", "topic": "graphql_schema"},
        ]}
        saved = self._run(monkeypatch, tmp_path, data)
        aggregate_synthesis("test_run")

        assert saved["data"] is not None
        for insight in saved["data"]["insights"]:
            assert insight["status"] == "synthesized"

    def test_skips_validated_without_topic(self, monkeypatch, tmp_path):
        data = {"insights": [
            {"id": 1, "status": "validated"},  # no topic
            {"id": 2, "status": "validated", "topic": "rails_patterns"},
        ]}
        saved = self._run(monkeypatch, tmp_path, data)
        aggregate_synthesis("test_run")

        insights = saved["data"]["insights"]
        assert insights[0]["status"] == "validated"  # unchanged
        assert insights[1]["status"] == "synthesized"

    def test_skips_non_validated_insights(self, monkeypatch, tmp_path):
        data = {"insights": [
            {"id": 1, "status": "draft", "topic": "rails_patterns"},
            {"id": 2, "status": "topic_assigned", "topic": "graphql_schema"},
        ]}
        saved = self._run(monkeypatch, tmp_path, data)
        aggregate_synthesis("test_run")

        # Nothing was updated, so save_yaml should NOT have been called
        assert saved["data"] is None

    def test_no_save_when_nothing_to_update(self, monkeypatch, tmp_path):
        data = {"insights": [
            {"id": 1, "status": "synthesized", "topic": "rails_patterns"},
        ]}
        saved = self._run(monkeypatch, tmp_path, data)
        aggregate_synthesis("test_run")
        assert saved["data"] is None

    def test_preserves_other_data_keys(self, monkeypatch, tmp_path):
        data = {
            "metadata": {"version": 2},
            "insights": [
                {"id": 1, "status": "validated", "topic": "testing_patterns"},
            ],
        }
        saved = self._run(monkeypatch, tmp_path, data)
        aggregate_synthesis("test_run")

        assert saved["data"]["metadata"] == {"version": 2}

    def test_empty_insights_list(self, monkeypatch, tmp_path):
        data = {"insights": []}
        saved = self._run(monkeypatch, tmp_path, data)
        aggregate_synthesis("test_run")
        assert saved["data"] is None
