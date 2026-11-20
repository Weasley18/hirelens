"""The hosted backend: a general-purpose model behind a provider API, no fine-tuning.

It gets the same untrusted-document framing, retrieved reference material and output
validation as the self-hosted model, plus HOSTED_GUIDANCE, which spells out the scoring
conventions a fine-tuned model would have learned from its training data.

OpenAI is the default, with gpt-6-luna: the efficiency tier of GPT-6 ($0.10 input / $0.50 output
per million tokens in November 2026, ~10x cheaper than gpt-6.1-terra), built for focused,
high-volume structured tasks like this one. Medium reasoning effort (OpenAI's default) gives the
small model room for the judgment parts at about $0.002 per analysis. It is a reasoning model,
so it takes `reasoning_effort` instead of `temperature`, and `max_completion_tokens` (which also
covers hidden reasoning tokens). Strict Structured Outputs guarantee the JSON shape; length and
count limits are stated in the prompt and enforced by our own validator, because the strict-mode
schema subset may not accept every JSON Schema keyword.
Anthropic uses forced tool use with the full schema; Gemini uses JSON mode with the schema in the
prompt. Every answer is validated; an invalid one is retried once, then rejected.

Candidate documents leave this service for the provider's API. The privacy notice
(VITE_INFERENCE_PROVIDER at web build time) must say so. Nothing from the documents or the
provider's response body is put in exceptions or logs.
"""

from __future__ import annotations

import contextvars
import http.client
import json
import os
import time
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any

from jsonschema import Draft7Validator

from common import extract_json, load_schema, validate_analysis
from inference.citations import removed_upstream, verify
from inference.telemetry import Call, anthropic_usage, gemini_usage, openai_usage, record_call, span
from inference.progress import FieldReader, publish_field
from inference.prompt import HOSTED_GUIDANCE, SYSTEM_PROMPT, build_user_turn

PROVIDERS = ("openai", "anthropic", "gemini")
DEFAULT_PROVIDER = "openai"
DEFAULT_MODELS = {
    "openai": "gpt-6-luna",
    "anthropic": "claude-sonnet-5-5",
    "gemini": "gemini-2.0-flash",
}
# OpenAI reasoning effort. Hidden reasoning tokens are billed as output. "medium" suits a small model
# on judgment-heavy output; try "low" if latency matters more. "none" re-enables temperature.
REASONING_EFFORTS = ("none", "low", "medium", "high")
DEFAULT_REASONING_EFFORT = "medium"
KEY_VARIABLES = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
TEMPERATURE = 0.2
MAX_OUTPUT_TOKENS = 2000
# Reasoning models spend part of max_completion_tokens on hidden reasoning before the answer.
OPENAI_MAX_COMPLETION_TOKENS = 6000
ATTEMPTS = 2  # one retry if the answer fails schema validation or cites text the documents lack
TOOL_NAME = "record_analysis"


class HostedModelError(RuntimeError):
    """A provider call failed. The message never contains document text or response bodies."""


def provider() -> str:
    name = os.environ.get("HOSTED_PROVIDER", DEFAULT_PROVIDER).strip().lower()
    if name not in PROVIDERS:
        raise HostedModelError(f"HOSTED_PROVIDER must be one of {', '.join(PROVIDERS)}")
    return name


def model_name() -> str:
    return os.environ.get("HOSTED_MODEL", "").strip() or DEFAULT_MODELS[provider()]


def timeout_seconds() -> float:
    """Total time for one analysis, across every attempt (not per attempt).

    A second attempt only starts if at least MIN_ATTEMPT_SECONDS remain, so the whole call
    always finishes inside this budget and the Lambda timeout only needs a small margin over it.
    """
    value = float(os.environ.get("HOSTED_TIMEOUT_SECONDS", "60"))
    if not 10 <= value <= 120:
        raise HostedModelError("HOSTED_TIMEOUT_SECONDS must be between 10 and 120")
    return value


MIN_ATTEMPT_SECONDS = 10
_deadline: contextvars.ContextVar[float] = contextvars.ContextVar("hosted_deadline", default=0.0)


def reasoning_effort() -> str:
    effort = os.environ.get("HOSTED_REASONING_EFFORT", DEFAULT_REASONING_EFFORT).strip().lower()
    if effort not in REASONING_EFFORTS:
        raise HostedModelError(f"HOSTED_REASONING_EFFORT must be one of {', '.join(REASONING_EFFORTS)}")
    return effort


def _api_key() -> str:
    key = os.environ.get(KEY_VARIABLES[provider()], "").strip()
    if not key:
        raise HostedModelError(f"{KEY_VARIABLES[provider()]} is not set")
    return key


def check_configuration() -> None:
    """Fail fast on missing or invalid settings, without calling (or paying for) the provider."""
    provider()
    _api_key()
    timeout_seconds()
    if provider() == "openai":
        reasoning_effort()


@lru_cache(maxsize=1)
def output_schema() -> dict[str, Any]:
    """The shared analysis schema, minus draft metadata that tool-input schemas do not need."""
    return {k: v for k, v in load_schema().items() if k not in ("$schema", "$id", "title", "description")}


_STRICT_UNSUPPORTED = ("minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems")


def _limits_text(node: dict) -> str:
    """The dropped constraints, restated as the field description the model reads."""
    parts = []
    if "minLength" in node or "maxLength" in node:
        parts.append(f"{node.get('minLength', 0)}-{node['maxLength']} characters" if "maxLength" in node
                     else f"at least {node['minLength']} characters")
    if "minimum" in node or "maximum" in node:
        parts.append(f"integer {node.get('minimum', 0)}-{node.get('maximum')}")
    if "minItems" in node or "maxItems" in node:
        parts.append(f"{node.get('minItems', 0)}-{node.get('maxItems', 'any')} items")
    return ("Must be " + ", ".join(parts) + ".") if parts else ""


def strict_schema(node: Any = None) -> Any:
    """The output schema reduced to the keywords every strict Structured Outputs schema accepts.

    Shape, types, enums, required fields and additionalProperties: false stay, so the API
    guarantees the structure. Length and count limits are dropped here, restated in each
    field's description (read by the model as it writes that field), and enforced by
    validate_analysis after the call.
    """
    if node is None:
        node = output_schema()
    if isinstance(node, dict):
        reduced = {k: strict_schema(v) for k, v in node.items() if k not in _STRICT_UNSUPPORTED}
        limits = _limits_text(node)
        if limits:
            reduced["description"] = (node.get("description", "") + " " + limits).strip()
        return reduced
    if isinstance(node, list):
        return [strict_schema(v) for v in node]
    return node


def system_prompt(include_schema: bool) -> str:
    parts = [SYSTEM_PROMPT, HOSTED_GUIDANCE]
    if include_schema:
        parts.append("Return exactly one JSON object matching this JSON Schema, with no other text:\n"
                     + json.dumps(output_schema(), separators=(",", ":")))
    return "\n\n".join(parts)


_USAGE_READERS = {
    "openai": lambda payload: openai_usage(payload.get("usage")),
    "anthropic": lambda payload: anthropic_usage(payload.get("usage")),
    "gemini": lambda payload: gemini_usage(payload.get("usageMetadata")),
}


def _post(url: str, body: dict, headers: dict[str, str]) -> dict:
    """One provider call, recorded with its tokens, time and outcome (never its content)."""
    usage: dict[str, int] = {}
    outcome = "ok"
    started = time.monotonic()
    with span("provider.call", **{"gen_ai.system": provider(), "gen_ai.request.model": model_name()}):
        try:
            return _send(url, body, headers, usage)
        except HostedModelError as exc:
            outcome = str(exc)
            raise
        finally:
            record_call(Call(provider(), model_name(), time.monotonic() - started, outcome, **usage))


def _send(url: str, body: dict, headers: dict[str, str], usage: dict[str, int]) -> dict:
    if publish_field.get():
        if provider() == "gemini":
            url = url.replace(":generateContent", ":streamGenerateContent?alt=sse")
        else:
            body["stream"] = True
            if provider() == "openai":
                body["stream_options"] = {"include_usage": True}  # token counts arrive in a last chunk
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    remaining = _deadline.get() - time.monotonic() if _deadline.get() else timeout_seconds()
    try:
        with urllib.request.urlopen(request, timeout=max(remaining, 1.0)) as response:
            if publish_field.get():
                return _stream_answer(response, usage)
            payload = json.loads(response.read().decode())
            if isinstance(payload, dict):
                usage.update(_USAGE_READERS[provider()](payload))
            return payload
    except urllib.error.HTTPError as exc:
        # The body is deliberately dropped: some providers echo parts of the request in errors.
        raise HostedModelError(f"HTTP {exc.code}") from None
    except (TimeoutError, OSError) as exc:
        # socket.timeout is only a TimeoutError from Python 3.10; on 3.9 it is a bare OSError.
        reason = "timeout" if "timed out" in str(exc).lower() or isinstance(exc, TimeoutError) else "network error"
        raise HostedModelError(reason) from None
    except (http.client.HTTPException, json.JSONDecodeError, UnicodeDecodeError):
        raise HostedModelError("unreadable response") from None


def _stream_answer(response, usage: dict[str, int]):
    reader = FieldReader()
    parts = []
    size = 0
    finished = False
    for line in response:
        if time.monotonic() >= _deadline.get():
            raise HostedModelError("timeout")
        if not line.startswith(b"data:"):
            continue
        data = line[5:].strip()
        if data == b"[DONE]":
            break
        event = json.loads(data)
        if "error" in event:
            raise HostedModelError("provider stream failed")
        if provider() == "openai":
            if event.get("usage"):
                usage.update(openai_usage(event["usage"]))
            choices = event.get("choices", [])
            if not choices:
                continue
            choice = choices[0]
            if choice.get("delta", {}).get("refusal"):
                raise HostedModelError("refused")
            chunk = choice.get("delta", {}).get("content") or ""
            finished = choice.get("finish_reason") == "stop"
        elif provider() == "anthropic":
            if event.get("type") == "message_start":
                usage.update(anthropic_usage(event.get("message", {}).get("usage")))
            elif event.get("type") == "message_delta" and event.get("usage"):
                usage["output_tokens"] = int(event["usage"].get("output_tokens") or 0)
            chunk = event.get("delta", {}).get("partial_json", "")
            if event.get("type") == "message_stop":
                finished = True
        else:
            if event.get("usageMetadata"):
                usage.update(gemini_usage(event["usageMetadata"]))  # cumulative: the last one wins
            candidate = (event.get("candidates") or [{}])[0]
            chunk = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", []) if not p.get("thought"))
            finished = candidate.get("finishReason") == "STOP"
        size += len(chunk)
        if size > 32000:
            raise HostedModelError("oversized answer")
        if chunk:
            parts.append(chunk)
            reader.feed(chunk)
    if not finished:
        raise HostedModelError("incomplete answer")
    try:
        return extract_json("".join(parts))
    except ValueError:
        raise HostedModelError("answer was not JSON") from None


def _call_anthropic(user_turn: str) -> dict:
    payload = _post(
        "https://api.anthropic.com/v1/messages",
        {
            "model": model_name(),
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": TEMPERATURE,
            "system": system_prompt(include_schema=False),
            "messages": [{"role": "user", "content": user_turn}],
            "tools": [{
                "name": TOOL_NAME,
                "description": "Record the structured resume-to-job analysis.",
                "input_schema": output_schema(),
            }],
            "tool_choice": {"type": "tool", "name": TOOL_NAME},
        },
        {"x-api-key": _api_key(), "anthropic-version": "2023-06-01"},
    )
    if publish_field.get():
        return payload
    for block in payload.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == TOOL_NAME:
            return block.get("input") or {}
    raise HostedModelError("no analysis in response")


def _call_openai(user_turn: str) -> dict:
    effort = reasoning_effort()
    body: dict[str, Any] = {
        "model": model_name(),
        "max_completion_tokens": OPENAI_MAX_COMPLETION_TOKENS,
        "reasoning_effort": effort,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "analysis", "strict": True, "schema": strict_schema()},
        },
        "messages": [
            {"role": "system", "content": system_prompt(include_schema=False)},
            {"role": "user", "content": user_turn},
        ],
        # Do not save these completions in the account's stored-completions dashboard.
        "store": False,
    }
    if effort == "none":
        body["temperature"] = TEMPERATURE  # sampling settings are rejected while reasoning is on
    payload = _post("https://api.openai.com/v1/chat/completions", body,
                    {"Authorization": f"Bearer {_api_key()}"})
    if publish_field.get():
        return payload
    try:
        choice = payload["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError):
        raise HostedModelError("no answer in response") from None
    if message.get("refusal"):
        raise HostedModelError("refused")
    if choice.get("finish_reason") == "length":
        raise HostedModelError("answer cut off at the token limit")
    try:
        return extract_json(message.get("content") or "")
    except (TypeError, ValueError):
        raise HostedModelError("answer was not JSON") from None


def _call_gemini(user_turn: str) -> dict:
    payload = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name()}:generateContent",
        {
            "systemInstruction": {"parts": [{"text": system_prompt(include_schema=True)}]},
            "contents": [{"role": "user", "parts": [{"text": user_turn}]}],
            "generationConfig": {
                "temperature": TEMPERATURE,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
                "responseMimeType": "application/json",
            },
        },
        {"x-goog-api-key": _api_key()},
    )
    if publish_field.get():
        return payload
    try:
        text = "".join(p.get("text", "") for p in payload["candidates"][0]["content"]["parts"])
        return extract_json(text)
    except (KeyError, IndexError, TypeError, ValueError):
        raise HostedModelError("no analysis in response") from None


_CALLERS = {"anthropic": _call_anthropic, "openai": _call_openai, "gemini": _call_gemini}


def _invalid_fields(analysis: Any) -> str:
    """Which fields broke which rule, e.g. "strengths.2 maxLength". Never includes values."""
    if not isinstance(analysis, dict):
        return "not an object"
    errors = sorted(Draft7Validator(load_schema()).iter_errors(analysis), key=lambda e: list(e.path))
    return ", ".join(f"{'.'.join(map(str, e.path)) or 'root'} {e.validator}" for e in errors[:4])


def generate(resume: str, jd: str, chunks: list[dict]) -> dict[str, Any]:
    check_configuration()
    user_turn = build_user_turn(resume, jd, chunks)
    caller = _CALLERS[provider()]
    deadline = time.monotonic() + timeout_seconds()
    token = _deadline.set(deadline)
    reasons: list[str] = []
    fallback: dict[str, Any] | None = None  # valid once unsupported claims are removed
    fallback_removed = 0
    try:
        for attempt in range(1, ATTEMPTS + 1):
            if attempt > 1 and deadline - time.monotonic() < MIN_ATTEMPT_SECONDS:
                reasons.append("no time left to retry")
                break
            if attempt > 1 and publish_field.get():
                publish_field.get()(None, None)
            try:
                analysis = caller(user_turn)
            except HostedModelError as exc:
                reason = str(exc)
                if reason.startswith("HTTP 4") and reason != "HTTP 429":
                    # Bad key, unknown model, bad request: retrying will not help.
                    raise HostedModelError(f"{provider()} rejected the request ({reason})") from None
                reasons.append(f"attempt {attempt}: {reason}")
                continue
            if not isinstance(analysis, dict) or validate_analysis(analysis):
                reasons.append(f"attempt {attempt}: invalid {_invalid_fields(analysis)}")
                continue
            supported, report = verify(analysis, resume, jd)
            if not report.removed:
                return analysis
            reasons.append(f"attempt {attempt}: unsupported quotes in {', '.join(report.removed)}")
            if not validate_analysis(supported):
                fallback, fallback_removed = supported, len(report.removed)
    finally:
        _deadline.reset(token)
    if fallback is not None:
        # Out of attempts: keep what the documents support, and report what was removed.
        removed_upstream.set(fallback_removed)
        return fallback
    raise HostedModelError(f"{provider()} did not return a valid analysis ({'; '.join(reasons)})")
