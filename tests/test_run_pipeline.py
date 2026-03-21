"""Tests for run_pipeline module — specifically assign_topics_programmatic and classify logic."""

from run_pipeline import TOPIC_KEYWORDS, assign_topics_programmatic


class TestTopicKeywords:
    def test_all_keys_are_lowercase_snake_case(self):
        for topic in TOPIC_KEYWORDS:
            assert topic == topic.lower(), f"{topic} is not lowercase"
            assert " " not in topic, f"{topic} contains spaces"

    def test_all_keyword_lists_are_nonempty(self):
        for topic, keywords in TOPIC_KEYWORDS.items():
            assert len(keywords) > 0, f"{topic} has no keywords"

    def test_known_topics_present(self):
        expected = {
            "financial_correctness",
            "graphql_schema",
            "migration_safety",
            "rails_patterns",
            "react_state",
            "react_components",
            "testing_patterns",
            "code_organization",
        }
        assert expected.issubset(TOPIC_KEYWORDS.keys())


class TestAssignTopicsProgrammatic:
    """Tests for assign_topics_programmatic, which exercises the inner classify() function."""

    def _run(self, monkeypatch, insights):
        """Helper: monkeypatches load/save and runs assign_topics_programmatic.

        Returns the list that was passed to save_insights.
        """
        saved = {}
        monkeypatch.setattr("run_pipeline.load_insights", lambda: insights)
        monkeypatch.setattr("run_pipeline.save_insights", lambda data: saved.update({"data": data}))
        assign_topics_programmatic()
        return saved.get("data")

    def test_skips_when_no_pending_insights(self, monkeypatch):
        result = self._run(monkeypatch, [
            {"id": 1, "status": "synthesized", "content": "graphql resolver"},
        ])
        # save_insights should not have been called
        assert result is None

    def test_skips_insights_that_already_have_topic(self, monkeypatch):
        result = self._run(monkeypatch, [
            {"id": 1, "status": "validated", "topic": "rails_patterns", "content": "rails stuff"},
        ])
        assert result is None

    def test_assigns_topic_by_keyword_match(self, monkeypatch):
        insights = [
            {"id": 1, "status": "validated", "content": "Use BigDecimal for monetary calculations"},
        ]
        result = self._run(monkeypatch, insights)
        assert result is not None
        assert insights[0]["topic"] == "financial_correctness"
        assert insights[0]["status"] == "topic_assigned"

    def test_graphql_keyword(self, monkeypatch):
        insights = [
            {"id": 1, "status": "validated", "content": "The GraphQL resolver should batch requests"},
        ]
        self._run(monkeypatch, insights)
        assert insights[0]["topic"] == "graphql_schema"

    def test_migration_keyword(self, monkeypatch):
        insights = [
            {"id": 1, "status": "validated", "content": "Prisma migration needs safety_assured"},
        ]
        self._run(monkeypatch, insights)
        assert insights[0]["topic"] == "migration_safety"

    def test_react_state_keyword(self, monkeypatch):
        insights = [
            {"id": 1, "status": "validated", "content": "Avoid useEffect for derived state"},
        ]
        self._run(monkeypatch, insights)
        assert insights[0]["topic"] == "react_state"

    def test_fallback_ruby_goes_to_rails_patterns(self, monkeypatch):
        """Content with 'ruby' that doesn't match TOPIC_KEYWORDS should hit the fallback."""
        # "ruby" is actually in TOPIC_KEYWORDS for rails_patterns, so it matches directly.
        # Use a term that only hits the fallback: "active" (not "activerecord" or "active_record").
        insights = [
            {"id": 1, "status": "validated", "content": "The active model validates presence"},
        ]
        self._run(monkeypatch, insights)
        assert insights[0]["topic"] == "rails_patterns"

    def test_fallback_react_goes_to_react_components(self, monkeypatch):
        """Content with 'hook' that doesn't match any TOPIC_KEYWORDS entry hits react fallback."""
        # "hook" is not in TOPIC_KEYWORDS (only "react hook" is in react_state).
        # So bare "hook" should fall through to the fallback.
        insights = [
            {"id": 1, "status": "validated", "content": "Custom hook for form validation"},
        ]
        self._run(monkeypatch, insights)
        # "hook" is not a keyword match (keywords have "react hook" not bare "hook"),
        # but the fallback checks "hook" in c => react_components
        assert insights[0]["topic"] == "react_components"

    def test_fallback_default_is_code_organization(self, monkeypatch):
        insights = [
            {"id": 1, "status": "validated", "content": "This is something completely unrelated to any keyword"},
        ]
        self._run(monkeypatch, insights)
        assert insights[0]["topic"] == "code_organization"

    def test_only_processes_validated_without_topic(self, monkeypatch):
        """Non-validated insights and those with topics already set are left alone."""
        insights = [
            {"id": 1, "status": "draft", "content": "graphql resolver"},
            {"id": 2, "status": "validated", "topic": "existing", "content": "graphql resolver"},
            {"id": 3, "status": "validated", "content": "graphql resolver"},
        ]
        self._run(monkeypatch, insights)
        assert insights[0]["status"] == "draft"  # unchanged
        assert "topic" not in insights[0]
        assert insights[1]["topic"] == "existing"  # unchanged
        assert insights[1]["status"] == "validated"  # unchanged
        assert insights[2]["topic"] == "graphql_schema"  # assigned
        assert insights[2]["status"] == "topic_assigned"

    def test_multiple_insights_get_different_topics(self, monkeypatch):
        insights = [
            {"id": 1, "status": "validated", "content": "Use BigDecimal for money"},
            {"id": 2, "status": "validated", "content": "Add a Prisma migration"},
            {"id": 3, "status": "validated", "content": "Write an rspec test"},
        ]
        self._run(monkeypatch, insights)
        topics = {i["id"]: i["topic"] for i in insights}
        assert topics[1] == "financial_correctness"
        assert topics[2] == "migration_safety"
        assert topics[3] == "testing_patterns"

    def test_saves_full_insights_list(self, monkeypatch):
        """save_insights receives the full list, not just the pending ones."""
        insights = [
            {"id": 1, "status": "synthesized", "content": "old stuff"},
            {"id": 2, "status": "validated", "content": "Use BigDecimal"},
        ]
        result = self._run(monkeypatch, insights)
        assert result is not None
        assert len(result) == 2
        assert result[0]["status"] == "synthesized"  # untouched

    def test_empty_content_falls_to_default(self, monkeypatch):
        insights = [
            {"id": 1, "status": "validated", "content": ""},
        ]
        self._run(monkeypatch, insights)
        assert insights[0]["topic"] == "code_organization"

    def test_missing_content_key_falls_to_default(self, monkeypatch):
        insights = [
            {"id": 1, "status": "validated"},
        ]
        self._run(monkeypatch, insights)
        assert insights[0]["topic"] == "code_organization"

    def test_case_insensitive_matching(self, monkeypatch):
        insights = [
            {"id": 1, "status": "validated", "content": "GRAPHQL RESOLVER handles queries"},
        ]
        self._run(monkeypatch, insights)
        assert insights[0]["topic"] == "graphql_schema"

    def test_first_matching_topic_wins(self, monkeypatch):
        """TOPIC_KEYWORDS is iterated in order; the first match wins."""
        # "bigdecimal" matches financial_correctness, even if content also has "test"
        insights = [
            {"id": 1, "status": "validated", "content": "Test that BigDecimal handles rounding"},
        ]
        self._run(monkeypatch, insights)
        assert insights[0]["topic"] == "financial_correctness"
