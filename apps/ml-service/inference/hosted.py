"""The hosted backend: a general-purpose model behind a provider API, no fine-tuning.

It gets the same untrusted-document framing, retrieved reference material and output
validation as the self-hosted model, plus HOSTED_GUIDANCE, which spells out the scoring
conventions a fine-tuned model would have learned from its training data.

Anthropic is the default. Its forced tool use returns arguments shaped by the JSON schema, so
format failures are rare. OpenAI and Gemini use their JSON modes, with the schema in the prompt.
Every answer is validated against the schema; an invalid one is retried once, then rejected.

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

PROVIDERS = ("anthropic", "openai", "gemini")
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
}
KEY_VARIABLES = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
TEMPERATURE = 0.2
MAX_OUTPUT_TOKENS = 2000
ATTEMPTS = 2  # one retry if the answer fails schema validation
TOOL_NAME = "record_analysis"


class HostedModelError(RuntimeError):
    """A provider call failed. The message never contains document text or response bodies."""


def provider() -> str:
    name = os.environ.get("HOSTED_PROVIDER", "anthropic").strip().lower()
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


@lru_cache(maxsize=1)
def output_schema() -> dict[str, Any]:
    """The shared analysis schema, minus draft metadata that tool-input schemas do not need."""
    return {k: v for k, v in load_schema().items() if k not in ("$schema", "$id", "title", "description")}


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
    payload = _post(
        "https://api.openai.com/v1/chat/completions",
        {
            "model": model_name(),
            "temperature": TEMPERATURE,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt(include_schema=True)},
                {"role": "user", "content": user_turn},
            ],
        },
        {"Authorization": f"Bearer {_api_key()}"},
    )
    try:
        return extract_json(payload["choices"][0]["message"]["content"])
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
