"""Evidence citations: matching rules, retries, reported counts and filtered drafts. No network."""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inference import hosted, llm, server
from inference.citations import occurs_in, removed_upstream, supported_items, verify

ROOT = Path(__file__).resolve().parents[3] / "packages/shared/fixtures"
FIXTURE = json.loads((ROOT / "sample-analysis.json").read_text())
DOCS = json.loads((ROOT / "sample-documents.json").read_text())
RESUME, JD = DOCS["resume"], DOCS["jd"]
TOKEN = "c" * 64


def invented(analysis: dict, *, strength: int | None = None, gap: int | None = None) -> dict:
    changed = copy.deepcopy(analysis)
    if strength is not None:
        changed["strengths"][strength]["evidence"] = "Led a team of forty engineers at Google"
    if gap is not None:
        changed["gaps"][gap]["requirement"] = "Must hold a PhD in distributed systems"
    return changed


@pytest.mark.parametrize("excerpt", [
    "partitioning on a 40M-row table by month",
    "PARTITIONING ON A 40M-ROW TABLE",
    "Built REST APIs with   Fastify\nand Node.js",
    "“Cut p95 latency from 800ms to 120ms”",
    "designed the PostgreSQL schema … partitioning on a 40M-row table",
    "Cut p95 latency from 800ms to 120ms.",
])
def test_formatting_differences_still_match(excerpt):
    assert occurs_in(excerpt, RESUME)


@pytest.mark.parametrize("excerpt", [
    "partitioned a 40-million-row table",              # paraphrase
    "Led a team of forty engineers",                    # invented
    "partitioning on a 40M-row table ... designed the PostgreSQL schema",  # fragments out of order
    "Node.js",                                          # too short to be evidence
    "",
])
def test_paraphrase_invention_and_trivial_quotes_do_not_match(excerpt):
    assert not occurs_in(excerpt, RESUME)


def test_verify_removes_only_unsupported_claims_and_counts_them():
    kept, report = verify(invented(FIXTURE, strength=1, gap=0), RESUME, JD)
    assert report.checked == len(FIXTURE["strengths"]) + len(FIXTURE["gaps"])
    assert report.removed == ["strengths.1", "gaps.0"]
    assert [s["text"] for s in kept["strengths"]] == [s["text"] for i, s in enumerate(FIXTURE["strengths"]) if i != 1]
    assert [g["skill"] for g in kept["gaps"]] == ["Terraform", "Team leadership"]
    assert kept["fitScore"] == FIXTURE["fitScore"] and kept["interviewQuestions"] == FIXTURE["interviewQuestions"]


def test_a_gap_must_quote_the_job_description_not_the_resume():
    resume_quote = copy.deepcopy(FIXTURE)
    resume_quote["gaps"][0]["requirement"] = "Services run in Docker Compose on a single VM"
    assert verify(resume_quote, RESUME, JD)[1].removed == ["gaps.0"]


def test_drafts_drop_unsupported_items():
    bad = invented(FIXTURE, strength=0)["strengths"]
    assert supported_items("strengths", bad, RESUME, JD) == FIXTURE["strengths"][1:]
    assert supported_items("verdict", "unchanged", RESUME, JD) == "unchanged"


@pytest.fixture
def openai_answers(monkeypatch):
    for key in ("HOSTED_MODEL", "HOSTED_TIMEOUT_SECONDS", "HOSTED_REASONING_EFFORT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HOSTED_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    calls = []

    def queue(*answers):
        pending = list(answers)

        def urlopen(request, timeout):
            calls.append(request)
            reply = {"choices": [{"message": {"content": json.dumps(pending.pop(0)), "refusal": None}}]}
            return io.BytesIO(json.dumps(reply).encode())

        monkeypatch.setattr(hosted.urllib.request, "urlopen", urlopen)
    return queue, calls


def test_hosted_retries_an_answer_that_cites_text_the_documents_lack(openai_answers):
    queue, calls = openai_answers
    queue(invented(FIXTURE, strength=2), FIXTURE)
    assert hosted.generate(RESUME, JD, []) == FIXTURE
    assert len(calls) == 2


def test_hosted_keeps_only_supported_claims_when_retries_run_out(openai_answers):
    queue, calls = openai_answers
    queue(invented(FIXTURE, strength=0), invented(FIXTURE, gap=2))
    token = removed_upstream.set(0)
    try:
        result = hosted.generate(RESUME, JD, [])
        assert removed_upstream.get() == 1
    finally:
        removed_upstream.reset(token)
    assert [g["skill"] for g in result["gaps"]] == ["Kubernetes", "Terraform"]
    assert result["strengths"] == FIXTURE["strengths"]


def test_hosted_fails_when_no_supported_strength_remains(openai_answers):
    queue, _ = openai_answers
    nothing = copy.deepcopy(FIXTURE)
    for strength in nothing["strengths"]:
        strength["evidence"] = "Invented achievement that is not in the resume"
    queue(nothing, nothing)
    with pytest.raises(hosted.HostedModelError, match="unsupported quotes in strengths.0"):
        hosted.generate(RESUME, JD, [])


def test_every_backend_reports_citation_counts(monkeypatch):
    monkeypatch.setattr(server, "generate_analysis", lambda resume, jd, chunks: invented(FIXTURE, gap=1))
    monkeypatch.setattr("rag.retrieve.retrieve_for_skills", lambda skills: [])
    envelope = server.analyze_documents(RESUME, JD)
    assert envelope["metadata"]["citations"] == {"checked": 7, "removed": 1}
    assert [g["skill"] for g in envelope["result"]["gaps"]] == ["Kubernetes", "Team leadership"]


def test_streamed_drafts_never_show_an_unsupported_quote(monkeypatch):
    monkeypatch.setenv("HOSTED_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("ML_SERVICE_TOKEN", TOKEN)
    monkeypatch.setattr(server, "BACKEND", "hosted")
    monkeypatch.setattr(llm, "BACKEND", "hosted")
    monkeypatch.setattr("rag.retrieve.retrieve_for_skills", lambda skills: [])
    answers = [invented(FIXTURE, strength=3), FIXTURE]

    def stream(request, timeout):
        text = json.dumps(answers.pop(0))
        events = [{"choices": [{"delta": {"content": text[i:i + 13]}}]} for i in range(0, len(text), 13)]
        events.append({"choices": [{"delta": {}, "finish_reason": "stop"}]})
        return io.BytesIO(b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events))

    monkeypatch.setattr(hosted.urllib.request, "urlopen", stream)
    with TestClient(server.app) as client:
        res = client.post("/infer", json={"resume": RESUME, "jd": JD},
                          headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/x-ndjson"})
    frames = [json.loads(line) for line in res.text.splitlines()]
    shown = [quote["evidence"] for frame in frames if frame.get("field") == "strengths" for quote in frame["value"]]
    assert "Led a team of forty engineers at Google" not in shown
    assert any(frame.get("reset") for frame in frames)  # the first attempt's draft was withdrawn
    assert frames[-1]["done"]["result"] == FIXTURE
    assert frames[-1]["done"]["metadata"]["citations"] == {"checked": 7, "removed": 0}
