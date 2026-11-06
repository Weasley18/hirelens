import json
from pathlib import Path

import pytest

from common import SCHEMA_PATH, extract_json, load_schema, validate_analysis
from rag.chunking import chunk_markdown, chunk_directory

FIXTURE = Path(__file__).resolve().parents[3] / "packages" / "shared" / "fixtures" / "sample-analysis.json"


class TestExtractJson:
    def test_plain_object(self):
        assert extract_json('{"fitScore": 80}') == {"fitScore": 80}

    def test_markdown_fenced(self):
        assert extract_json('```json\n{"fitScore": 80}\n```') == {"fitScore": 80}

    def test_with_surrounding_prose(self):
        text = 'Here is the analysis:\n{"fitScore": 80}\nHope that helps!'
        assert extract_json(text) == {"fitScore": 80}

    def test_nested_objects(self):
        text = '{"gaps": [{"skill": "Go", "severity": "minor"}], "fitScore": 60}'
        assert extract_json(text)["gaps"][0]["skill"] == "Go"

    def test_braces_inside_strings_do_not_confuse_the_scanner(self):
        text = '{"verdict": "uses {curly} braces", "fitScore": 1}'
        assert extract_json(text)["verdict"] == "uses {curly} braces"

    def test_escaped_quote_inside_string(self):
        text = '{"verdict": "said \\"hi\\" loudly", "fitScore": 1}'
        assert extract_json(text)["fitScore"] == 1

    def test_empty_output_raises(self):
        with pytest.raises(ValueError):
            extract_json("")

    def test_no_object_raises(self):
        with pytest.raises(ValueError):
            extract_json("I'm sorry, I can't help with that.")

    def test_truncated_output_raises(self):
        with pytest.raises(ValueError):
            extract_json('{"fitScore": 80, "gaps": [')


class TestSchema:
    def test_schema_file_is_where_both_sides_expect_it(self):
        assert SCHEMA_PATH.exists(), f"shared schema missing at {SCHEMA_PATH}"

    def test_shared_fixture_is_valid(self):
        assert validate_analysis(json.loads(FIXTURE.read_text())) == []

    def test_missing_required_field_is_reported(self):
        analysis = json.loads(FIXTURE.read_text())
        del analysis["verdict"]
        assert any("verdict" in issue for issue in validate_analysis(analysis))

    def test_bad_enum_is_reported(self):
        analysis = json.loads(FIXTURE.read_text())
        analysis["gaps"][0]["severity"] = "catastrophic"
        assert validate_analysis(analysis) != []

    def test_out_of_range_score_is_reported(self):
        analysis = json.loads(FIXTURE.read_text())
        analysis["fitScore"] = 140
        assert validate_analysis(analysis) != []

    def test_extra_field_is_reported(self):
        analysis = json.loads(FIXTURE.read_text())
        analysis["confidence"] = 0.9
        assert validate_analysis(analysis) != []

    def test_enums_match_the_typescript_mirror(self):
        schema = load_schema()
        severity = schema["properties"]["gaps"]["items"]["properties"]["severity"]["enum"]
        difficulty = schema["properties"]["interviewQuestions"]["items"]["properties"]["difficulty"]["enum"]
        assert severity == ["minor", "moderate", "severe"]
        assert difficulty == ["junior", "mid", "senior"]


SAMPLE_MD = """# Test Document

Intro text that belongs to no section.

## First topic

A paragraph long enough to clear the minimum chunk size, describing something specific
about one topic so that its embedding is not a blurry average of five different subjects.

## Too short

Nope.

## Second topic

Another paragraph that is comfortably over the minimum length threshold and discusses a
single coherent idea worth retrieving on its own merits in a search.
"""


class TestChunking:
    def test_one_chunk_per_section(self):
        chunks = chunk_markdown(SAMPLE_MD, "test.md")
        assert len(chunks) == 2

    def test_sections_below_the_minimum_are_dropped(self):
        assert all("Nope" not in c["content"] for c in chunk_markdown(SAMPLE_MD, "test.md"))

    def test_source_names_document_and_section(self):
        assert chunk_markdown(SAMPLE_MD, "test.md")[0]["source"] == "Test Document: First topic"

    def test_heading_is_kept_in_the_content(self):
        assert chunk_markdown(SAMPLE_MD, "test.md")[0]["content"].startswith("First topic.")

    def test_oversized_section_splits_on_paragraph_boundaries(self):
        body = "\n\n".join(["Sentence about a topic that carries real content. " * 6] * 4)
        chunks = chunk_markdown(f"# Doc\n\n## Big\n\n{body}\n", "big.md")
        assert len(chunks) > 1
        assert all(len(c["content"]) < 1100 for c in chunks)

    def test_document_without_a_title_falls_back_to_the_filename(self):
        chunks = chunk_markdown("## Topic\n\n" + "x" * 200, "fallback.md")
        assert chunks[0]["source"].startswith("fallback:")

    def test_real_knowledge_base_produces_usable_chunks(self):
        chunks = chunk_directory(Path(__file__).resolve().parents[1] / "rag" / "knowledge")
        assert len(chunks) >= 50, "knowledge base is too thin to improve retrieval"
        assert all(120 <= len(c["content"]) <= 1000 for c in chunks)
        assert len({c["source"] for c in chunks}) == len(chunks), "duplicate source labels"
