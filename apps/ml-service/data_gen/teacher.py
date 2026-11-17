"""The teacher model used to generate training data (Phase 3).

Only used locally, only during data generation. Production never calls this — that is the
whole point of distilling into a small model. Swapping providers means replacing the body
of `call_teacher` and nothing else.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from common import extract_json, load_schema

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
except ImportError:
    pass

_RETRIES = 5

ANALYSIS_SYSTEM_PROMPT = """You are a senior technical recruiter with a strong engineering background.

Given a resume and a job description, output ONLY valid JSON matching this schema:

{schema}

Rules:
- Ground every claim in the actual resume text. Never credit a skill that is not there.
- A gap is something the job description asks for that the resume does not evidence.
- fitScore must be consistent with the gaps: severe gaps mean a score well below 80.
- Interview questions must be specific to this candidate's actual experience, not generic.
- Output the JSON object and nothing else. No prose, no markdown fences."""


def _provider() -> str:
    explicit = os.environ.get("TEACHER_PROVIDER", "").strip().lower()
    if explicit:
        return explicit
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    raise RuntimeError(
        "Set GEMINI_API_KEY, OPENAI_API_KEY or ANTHROPIC_API_KEY — see .env.example"
    )


_PROVIDERS = ("gemini", "openai", "anthropic")
_DEFAULT_MODELS = {
    "gemini": "gemini-2.0-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-5-5",
}


def _model_name() -> str:
    if os.environ.get("TEACHER_MODEL"):
        return os.environ["TEACHER_MODEL"]
    return _DEFAULT_MODELS[_provider()]


def _call_gemini(prompt: str, temperature: float) -> str:
    import google.generativeai as genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set — see .env.example")
    genai.configure(api_key=api_key)
    response = genai.GenerativeModel(_model_name()).generate_content(
        prompt,
        generation_config={"temperature": temperature, "max_output_tokens": 2048},
    )
    return response.text


def _call_openai(prompt: str, temperature: float) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set — see .env.example")

    body = json.dumps(
        {
            "model": _model_name(),
            "temperature": temperature,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail}") from exc

    return payload["choices"][0]["message"]["content"]


def _call_anthropic(prompt: str, temperature: float) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set — see .env.example")

    body = json.dumps(
        {
            "model": _model_name(),
            "max_tokens": 2048,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise RuntimeError(f"Anthropic HTTP {exc.code}: {detail}") from exc

    return "".join(
        block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"
    )


_CALLERS = {"gemini": _call_gemini, "openai": _call_openai, "anthropic": _call_anthropic}


def call_teacher(prompt: str, temperature: float = 0.7) -> str:
    """One call to the teacher model, with retries for transient/rate-limit failures."""
    provider = _provider()
    # Validate once: a typo in TEACHER_PROVIDER is not a transient failure worth retrying.
    if provider not in _CALLERS:
        raise RuntimeError(f"Unknown TEACHER_PROVIDER: {provider!r}; use one of {_PROVIDERS}")
    caller = _CALLERS[provider]
    last_error: Exception | None = None

    for attempt in range(_RETRIES):
        try:
            return caller(prompt, temperature)
        except Exception as exc:  # noqa: BLE001 - free tiers fail in many shapes
            last_error = exc
            time.sleep(2**attempt)

    raise RuntimeError(f"teacher model failed after {_RETRIES} attempts: {last_error}")


def analyse_pair(resume: str, jd: str) -> dict:
    """Produce one training label: the analysis JSON for a (resume, JD) pair."""
    system = ANALYSIS_SYSTEM_PROMPT.format(schema=json.dumps(load_schema(), indent=2))
    prompt = f"{system}\n\nRESUME:\n{resume}\n\nJOB DESCRIPTION:\n{jd}"
    return extract_json(call_teacher(prompt, temperature=0.4))
