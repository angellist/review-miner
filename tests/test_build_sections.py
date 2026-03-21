"""Tests for build_sections module."""

from build_sections import build_section, format_sources, format_topic_title


class TestFormatTopicTitle:
    def test_replaces_underscores_and_title_cases(self):
        assert format_topic_title("error_handling") == "Error Handling"

    def test_single_word(self):
        assert format_topic_title("testing") == "Testing"

    def test_multiple_underscores(self):
        assert format_topic_title("a_b_c") == "A B C"


class TestFormatSources:
    def test_empty_list_returns_empty_string(self):
        assert format_sources([]) == ""

    def test_single_source(self):
        assert format_sources([42]) == "_Sources: PR #42_"

    def test_multiple_sources(self):
        assert format_sources([1, 2, 3]) == "_Sources: PR #1, PR #2, PR #3_"


class TestBuildSection:
    def test_basic_section_with_one_practice(self):
        result = build_section("error_handling", "backend", [
            {"title": "Use exceptions", "content": "Always use exceptions.", "sources": [10]},
        ])
        assert result == (
            "---\n"
            "scope: backend\n"
            "---\n"
            "\n"
            "# Error Handling\n"
            "\n"
            "### Use exceptions\n"
            "\n"
            "Always use exceptions.\n"
            "\n"
            "_Sources: PR #10_\n"
        )

    def test_practice_without_sources_omits_source_line(self):
        result = build_section("testing", "all", [
            {"title": "Write tests", "content": "Cover edge cases."},
        ])
        assert "Sources" not in result
        assert "### Write tests" in result
        assert "Cover edge cases." in result

    def test_skips_practice_missing_title(self):
        result = build_section("topic", "all", [
            {"title": "", "content": "Some content"},
            {"title": "Valid", "content": "Valid content"},
        ])
        assert "Some content" not in result
        assert "### Valid" in result

    def test_skips_practice_missing_content(self):
        result = build_section("topic", "all", [
            {"title": "No Content", "content": ""},
        ])
        assert "No Content" not in result

    def test_skips_practice_with_whitespace_only_title(self):
        result = build_section("topic", "all", [
            {"title": "   ", "content": "Body"},
        ])
        assert "Body" not in result

    def test_empty_practices_list(self):
        result = build_section("topic", "all", [])
        assert result == "---\nscope: all\n---\n\n# Topic\n"

    def test_multiple_practices(self):
        practices = [
            {"title": "First", "content": "Content A", "sources": [1]},
            {"title": "Second", "content": "Content B"},
        ]
        result = build_section("topic", "all", practices)
        assert result.index("### First") < result.index("### Second")
        assert "_Sources: PR #1_" in result
