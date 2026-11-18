"""Hosted backend: request shapes, validation, retries and privacy of errors. No network."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inference import hosted, llm, server

FIXTURE = json.loads((Path(__file__).resolve().parents[3] / "packages/shared/fixtures/sample-analysis.json").read_text())
RESUME = "Backend engineer, five years of Python and PostgreSQL services. SECRET-RESUME-MARKER"
JD = "Hiring a backend engineer with Python, PostgreSQL and Kubernetes experience."
TOKEN = "b" * 64


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for key in ("HOSTED_PROVIDER", "HOSTED_MODEL", "HOSTED_TIMEOUT_SECONDS",
                "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")


def _respond(monkeypatch, *payloads):
    """Queue provider responses (dicts, or exceptions to raise) and record each request."""
    seen, queue = [], list(payloads)

    def fake_urlopen(request, timeout):
        seen.append({"url": request.full_url, "timeout": timeout, "body": json.loads(request.data),
                     "headers": {k.lower(): v for k, v in request.header_items()}})
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return io.BytesIO(json.dumps(item).encode())

    monkeypatch.setattr(hosted.urllib.request, "urlopen", fake_urlopen)
    return seen


def _tool_reply(analysis):
    return {"content": [{"type": "tool_use", "name": hosted.TOOL_NAME, "input": analysis}]}


def test_anthropic_forces_schema_tool_and_sends_documents_as_data(monkeypatch):
    seen = _respond(monkeypatch, _tool_reply(FIXTURE))
    chunks = [{"content": "Ask about index design.", "source": "Interview guide: PostgreSQL"}]
    assert hosted.generate(RESUME, JD, chunks) == FIXTURE

    request = seen[0]
    assert request["url"] == "https://api.anthropic.com/v1/messages"
    assert request["headers"]["x-api-key"] == "test-anthropic-key"
    body = request["body"]
    assert body["model"] == "claude-sonnet-5-5"
    assert body["tool_choice"] == {"type": "tool", "name": hosted.TOOL_NAME}
    schema = body["tools"][0]["input_schema"]
    assert schema["required"] == ["fitScore", "verdict", "gaps", "strengths", "interviewQuestions"]
    assert "$schema" not in schema
    assert "untrusted data" in body["system"] and "Scoring" in body["system"]
    user = body["messages"][0]["content"]
    assert json.dumps(RESUME) in user and "Ask about index design." in user


def test_invalid_answer_is_retried_once_then_rejected(monkeypatch):
    bad = dict(FIXTURE, fitScore=140)
    seen = _respond(monkeypatch, _tool_reply(bad), _tool_reply(FIXTURE))
    assert hosted.generate(RESUME, JD, []) == FIXTURE
    assert len(seen) == 2

    _respond(monkeypatch, _tool_reply(bad), _tool_reply(bad))
    with pytest.raises(hosted.HostedModelError, match="valid analysis"):
        hosted.generate(RESUME, JD, [])


def test_rate_limit_is_retried_but_auth_errors_are_not(monkeypatch):
    def http_error(code):
        return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b'{"echo": "SECRET-RESUME-MARKER"}'))

    seen = _respond(monkeypatch, http_error(429), _tool_reply(FIXTURE))
    assert hosted.generate(RESUME, JD, []) == FIXTURE and len(seen) == 2

    seen = _respond(monkeypatch, http_error(401), _tool_reply(FIXTURE))
    with pytest.raises(hosted.HostedModelError) as excinfo:
        hosted.generate(RESUME, JD, [])
    assert len(seen) == 1
    assert "SECRET-RESUME-MARKER" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None and excinfo.value.__suppress_context__


def test_openai_and_gemini_use_json_mode_with_schema_in_prompt(monkeypatch):
    monkeypatch.setenv("HOSTED_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    seen = _respond(monkeypatch, {"choices": [{"message": {"content": json.dumps(FIXTURE)}}]})
    assert hosted.generate(RESUME, JD, []) == FIXTURE
    assert seen[0]["body"]["response_format"] == {"type": "json_object"}
    assert '"interviewQuestions"' in seen[0]["body"]["messages"][0]["content"]
    assert seen[0]["headers"]["authorization"] == "Bearer test-openai-key"

    monkeypatch.setenv("HOSTED_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("HOSTED_MODEL", "gemini-test")
    reply = {"candidates": [{"content": {"parts": [{"text": "```json\n" + json.dumps(FIXTURE) + "\n```"}]}}]}
    seen = _respond(monkeypatch, reply)
    assert hosted.generate(RESUME, JD, []) == FIXTURE
    assert seen[0]["url"].endswith("/models/gemini-test:generateContent")
    assert seen[0]["headers"]["x-goog-api-key"] == "test-gemini-key"
    assert "test-gemini-key" not in seen[0]["url"]


def test_configuration_errors_fail_fast_without_calling_the_provider(monkeypatch):
    seen = _respond(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(hosted.HostedModelError, match="ANTHROPIC_API_KEY"):
        hosted.generate(RESUME, JD, [])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("HOSTED_PROVIDER", "claude")
    with pytest.raises(hosted.HostedModelError, match="HOSTED_PROVIDER"):
        hosted.check_configuration()
    monkeypatch.setenv("HOSTED_PROVIDER", "anthropic")
    monkeypatch.setenv("HOSTED_TIMEOUT_SECONDS", "600")
    with pytest.raises(hosted.HostedModelError, match="TIMEOUT"):
        hosted.check_configuration()
    assert seen == []


def test_production_accepts_hosted_backend_and_requires_its_key(monkeypatch):
    monkeypatch.setenv("ML_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(server, "BACKEND", "hosted")
    monkeypatch.setattr(llm, "BACKEND", "hosted")
    _respond(monkeypatch, _tool_reply(FIXTURE))
    monkeypatch.setattr("rag.retrieve.retrieve_for_skills", lambda skills: [], raising=False)
    with TestClient(server.app) as client:
        response = client.post("/infer", json={"resume": RESUME * 2, "jd": JD * 2},
                               headers={"Authorization": "Bearer " + TOKEN})
    assert response.status_code == 200
    assert response.json()["metadata"]["backend"] == "hosted"

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(hosted.HostedModelError):
        with TestClient(server.app):
            pass
