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

import json
import os
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any

from common import extract_json, load_schema, validate_analysis
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
ATTEMPTS = 2  # one retry if the answer fails schema validation
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
    value = float(os.environ.get("HOSTED_TIMEOUT_SECONDS", "45"))
    if not 5 <= value <= 120:
        raise HostedModelError("HOSTED_TIMEOUT_SECONDS must be between 5 and 120")
    return value


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


def strict_schema(node: Any = None) -> Any:
    """The output schema reduced to the keywords every strict Structured Outputs schema accepts.

    Shape, types, enums, required fields and additionalProperties: false stay, so the API
    guarantees the structure. Length and count limits are dropped here and enforced by
    validate_analysis after the call (HOSTED_GUIDANCE states them to the model).
    """
    if node is None:
        node = output_schema()
    if isinstance(node, dict):
        return {k: strict_schema(v) for k, v in node.items() if k not in _STRICT_UNSUPPORTED}
    if isinstance(node, list):
        return [strict_schema(v) for v in node]
    return node


def system_prompt(include_schema: bool) -> str:
    parts = [SYSTEM_PROMPT, HOSTED_GUIDANCE]
    if include_schema:
        parts.append("Return exactly one JSON object matching this JSON Schema, with no other text:\n"
                     + json.dumps(output_schema(), separators=(",", ":")))
    return "\n\n".join(parts)


def _post(url: str, body: dict, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds()) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        # The body is deliberately dropped: some providers echo parts of the request in errors.
        raise HostedModelError(f"{provider()} returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise HostedModelError(f"{provider()} request failed") from None


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
    for block in payload.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == TOOL_NAME:
            return block.get("input") or {}
    raise HostedModelError("anthropic returned no analysis")


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
    try:
        message = payload["choices"][0]["message"]
        if message.get("refusal"):
            raise ValueError("refused")
        return extract_json(message["content"])
    except (KeyError, IndexError, TypeError, ValueError):
        raise HostedModelError("openai returned no analysis") from None


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
    try:
        text = "".join(p.get("text", "") for p in payload["candidates"][0]["content"]["parts"])
        return extract_json(text)
    except (KeyError, IndexError, TypeError, ValueError):
        raise HostedModelError("gemini returned no analysis") from None


_CALLERS = {"anthropic": _call_anthropic, "openai": _call_openai, "gemini": _call_gemini}


def generate(resume: str, jd: str, chunks: list[dict]) -> dict[str, Any]:
    check_configuration()
    user_turn = build_user_turn(resume, jd, chunks)
    caller = _CALLERS[provider()]
    for _attempt in range(ATTEMPTS):
        try:
            analysis = caller(user_turn)
        except HostedModelError as exc:
            if "HTTP 4" in str(exc) and "HTTP 429" not in str(exc):
                raise  # bad key, bad model name, bad request: retrying will not help
            continue
        if isinstance(analysis, dict) and not validate_analysis(analysis):
            return analysis
    raise HostedModelError(f"{provider()} did not return a valid analysis")
