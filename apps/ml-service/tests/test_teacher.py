"""Teacher provider selection and the Anthropic request shape, with no network access."""

from __future__ import annotations

import io
import json

import pytest

from data_gen import teacher

_KEYS = ("TEACHER_PROVIDER", "TEACHER_MODEL", "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(teacher.time, "sleep", lambda _seconds: None)


def test_anthropic_key_selects_anthropic_with_default_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert teacher._provider() == "anthropic"
    assert teacher._model_name() == "claude-sonnet-5-5"


def test_existing_provider_precedence_is_unchanged(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    assert teacher._provider() == "openai"


def test_missing_keys_name_every_option():
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        teacher._provider()


def test_unknown_provider_fails_immediately_without_retrying(monkeypatch):
    monkeypatch.setenv("TEACHER_PROVIDER", "anthropicc")
    calls = []
    monkeypatch.setattr(teacher.time, "sleep", lambda s: calls.append(s))
    with pytest.raises(RuntimeError, match="Unknown TEACHER_PROVIDER"):
        teacher.call_teacher("hi")
    assert calls == []


def test_anthropic_request_and_response_parsing(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-key")
    monkeypatch.setenv("TEACHER_MODEL", "claude-haiku-5-5")
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["headers"] = {k.lower(): v for k, v in request.header_items()}
        seen["body"] = json.loads(request.data)
        payload = {"content": [{"type": "text", "text": '{"ok": '}, {"type": "text", "text": "true}"}]}
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(teacher.urllib.request, "urlopen", fake_urlopen)
    assert teacher.call_teacher("prompt text", temperature=0.4) == '{"ok": true}'
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "secret-key"
    assert seen["headers"]["anthropic-version"] == "2023-06-01"
    assert seen["body"]["model"] == "claude-haiku-5-5"
    assert seen["body"]["temperature"] == 0.4
    assert seen["body"]["messages"] == [{"role": "user", "content": "prompt text"}]
