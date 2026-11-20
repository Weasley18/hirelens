"""Token usage, cost and tracing: counted per provider call, never carrying document text."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inference import hosted, llm, server, telemetry

FIXTURE = json.loads((Path(__file__).resolve().parents[3] / "packages/shared/fixtures/sample-analysis.json").read_text())
DOCUMENTS = json.loads((Path(__file__).resolve().parents[3] / "packages/shared/fixtures/sample-documents.json").read_text())
RESUME = DOCUMENTS["resume"] + " SECRET-RESUME-MARKER"
JD = DOCUMENTS["jd"]
TOKEN = "c" * 64
OPENAI_USAGE = {"prompt_tokens": 3000, "completion_tokens": 1200,
                "completion_tokens_details": {"reasoning_tokens": 700}, "prompt_tokens_details": {"cached_tokens": 1024}}


@pytest.fixture(autouse=True)
def openai(monkeypatch):
    for key in ("HOSTED_MODEL", "HOSTED_TIMEOUT_SECONDS", "HOSTED_REASONING_EFFORT",
                "HOSTED_PRICE_INPUT_PER_MTOK", "HOSTED_PRICE_OUTPUT_PER_MTOK"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HOSTED_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("ML_SERVICE_TOKEN", TOKEN)
    monkeypatch.setattr(server, "BACKEND", "hosted")
    monkeypatch.setattr(llm, "BACKEND", "hosted")
    monkeypatch.setattr("rag.retrieve.retrieve_for_skills", lambda skills: [])


def _replies(monkeypatch, *answers, stream=False):
    pending, bodies = list(answers), []

    def urlopen(request, timeout):
        bodies.append(json.loads(request.data))
        answer = pending.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if not stream:
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(answer)}}],
                                          "usage": OPENAI_USAGE}).encode())
        text = json.dumps(answer)
        events = [{"choices": [{"delta": {"content": text[i:i + 50]}}]} for i in range(0, len(text), 50)]
        events += [{"choices": [{"delta": {}, "finish_reason": "stop"}]}, {"choices": [], "usage": OPENAI_USAGE}]
        return io.BytesIO(b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events) + b"data: [DONE]\n\n")

    monkeypatch.setattr(hosted.urllib.request, "urlopen", urlopen)
    return bodies


def test_usage_and_cost_are_reported_beside_the_envelope(monkeypatch):
    _replies(monkeypatch, FIXTURE)
    envelope = server.analyze_documents(RESUME, JD)
    usage = envelope["telemetry"]
    assert usage["model"] == "gpt-6-luna" and usage["attempts"] == 1
    assert (usage["inputTokens"], usage["outputTokens"], usage["reasoningTokens"], usage["cachedTokens"]) == (3000, 1200, 700, 1024)
    assert usage["costUsd"] == pytest.approx((3000 * 0.10 + 1200 * 0.50) / 1e6)
    assert set(usage["stages"]) == {"retrieve", "generate", "verify", "provider.call"}
    assert usage["totalMs"] >= 0
    assert "SECRET-RESUME-MARKER" not in json.dumps(usage)


def test_every_attempt_is_counted_including_failed_ones(monkeypatch):
    broken = dict(FIXTURE, fitScore=900)
    _replies(monkeypatch, broken, FIXTURE)
    usage = server.analyze_documents(RESUME, JD)["telemetry"]
    assert usage["attempts"] == 2 and usage["inputTokens"] == 6000


def test_streamed_answers_ask_for_usage_and_count_it(monkeypatch):
    bodies = _replies(monkeypatch, FIXTURE, stream=True)
    with TestClient(server.app) as client:
        res = client.post("/infer", json={"resume": RESUME, "jd": JD},
                          headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/x-ndjson"})
    done = json.loads(res.text.splitlines()[-1])["done"]
    assert bodies[0]["stream_options"] == {"include_usage": True}
    assert done["telemetry"]["outputTokens"] == 1200


@pytest.mark.parametrize("reader, payload, expected", [
    (telemetry.anthropic_usage, {"input_tokens": 100, "cache_read_input_tokens": 50, "output_tokens": 30},
     {"input_tokens": 150, "output_tokens": 30, "cached_tokens": 50}),
    (telemetry.gemini_usage, {"promptTokenCount": 100, "candidatesTokenCount": 30, "thoughtsTokenCount": 20},
     {"input_tokens": 100, "output_tokens": 50, "reasoning_tokens": 20, "cached_tokens": 0}),
    (telemetry.openai_usage, None, {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0}),
])
def test_provider_usage_shapes(reader, payload, expected):
    assert reader(payload) == expected


def test_unknown_models_have_no_cost_unless_priced(monkeypatch):
    usage = telemetry.Usage([telemetry.Call("anthropic", "some-model", 1.0, "ok", 1_000_000, 1_000_000)])
    assert usage.summary()["costUsd"] is None
    monkeypatch.setenv("HOSTED_PRICE_INPUT_PER_MTOK", "2")
    monkeypatch.setenv("HOSTED_PRICE_OUTPUT_PER_MTOK", "8")
    assert usage.summary()["costUsd"] == 10.0


def test_spans_continue_the_callers_trace_and_carry_no_document_text(monkeypatch):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer("test"))
    _replies(monkeypatch, dict(FIXTURE, fitScore=900), FIXTURE)
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    with TestClient(server.app) as client:
        res = client.post("/infer", json={"resume": RESUME, "jd": JD}, headers={
            "Authorization": "Bearer " + TOKEN, "traceparent": f"00-{trace_id}-00f067aa0ba902b7-01"})
    assert res.status_code == 200
    spans = {s.name: s for s in exporter.get_finished_spans()}
    assert {"ml.infer", "retrieve", "generate", "provider.call", "verify"} <= set(spans)
    assert all(format(s.context.trace_id, "032x") == trace_id for s in exporter.get_finished_spans())
    assert spans["ml.infer"].parent.span_id == 0x00f067aa0ba902b7
    calls = [s for s in exporter.get_finished_spans() if s.name == "provider.call"]
    assert [c.attributes["gen_ai.usage.input_tokens"] for c in calls] == [3000, 3000]
    dumped = json.dumps([dict(s.attributes) for s in exporter.get_finished_spans()] + [s.name for s in spans.values()])
    assert "SECRET-RESUME-MARKER" not in dumped and "Ledgerly" not in dumped


def test_tracing_stays_off_without_an_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setattr(telemetry, "_tracer", None)
    assert telemetry.setup_tracing() is False
