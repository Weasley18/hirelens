"""Usage, cost and tracing for one analysis. Nothing from the documents is ever recorded.

Every provider call adds a record (model, tokens, seconds, outcome) to the analysis that made
it. /infer returns the totals beside the envelope as "telemetry", the worker stores them with the
anonymous completion row, and the evaluation reports cost per analysis from them.

Tracing is off unless OTEL_EXPORTER_OTLP_ENDPOINT is set (and the OpenTelemetry packages are
installed). When on, /infer continues the trace the worker started (W3C traceparent header) and
adds a span per stage: retrieval, each provider attempt, and citation checking.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

log = logging.getLogger("hirelens")

# US dollars per million tokens: (input, output). Reasoning tokens are billed as output.
# Override for any model with HOSTED_PRICE_INPUT_PER_MTOK and HOSTED_PRICE_OUTPUT_PER_MTOK.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-6.1-terra": (1.00, 5.00),
}


def price(model: str) -> tuple[float, float] | None:
    try:
        override = (float(os.environ["HOSTED_PRICE_INPUT_PER_MTOK"]), float(os.environ["HOSTED_PRICE_OUTPUT_PER_MTOK"]))
    except (KeyError, ValueError):
        override = None
    return override or PRICES.get(model)


@dataclass
class Call:
    provider: str
    model: str
    seconds: float
    outcome: str  # "ok" or a short, content-free reason such as "timeout" or "HTTP 429"
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0


@dataclass
class Usage:
    calls: list[Call] = field(default_factory=list)
    stages: dict[str, float] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        cost: float | None = 0.0
        for call in self.calls:
            rates = price(call.model)
            if rates is None:
                cost = None
                break
            cost += (call.input_tokens * rates[0] + call.output_tokens * rates[1]) / 1_000_000
        models = sorted({c.model for c in self.calls})
        return {
            "model": models[-1] if models else None,
            "attempts": len(self.calls),
            "inputTokens": sum(c.input_tokens for c in self.calls),
            "outputTokens": sum(c.output_tokens for c in self.calls),
            "reasoningTokens": sum(c.reasoning_tokens for c in self.calls),
            "cachedTokens": sum(c.cached_tokens for c in self.calls),
            "costUsd": None if cost is None else round(cost, 6),
            "stages": {name: round(seconds * 1000) for name, seconds in self.stages.items()},
        }


_usage: ContextVar[Usage | None] = ContextVar("hirelens_usage", default=None)


@contextmanager
def collect() -> Iterator[Usage]:
    usage = Usage()
    token = _usage.set(usage)
    try:
        yield usage
    finally:
        _usage.reset(token)


def record_call(call: Call) -> None:
    usage = _usage.get()
    if usage is not None:
        usage.calls.append(call)
    span = _current_span()
    if span is not None:
        span.set_attributes({
            "gen_ai.system": call.provider, "gen_ai.request.model": call.model,
            "gen_ai.usage.input_tokens": call.input_tokens, "gen_ai.usage.output_tokens": call.output_tokens,
            "gen_ai.usage.reasoning_tokens": call.reasoning_tokens, "hirelens.outcome": call.outcome,
        })


def openai_usage(usage: Mapping[str, Any] | None) -> dict[str, int]:
    usage = usage or {}
    return {"input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
            "reasoning_tokens": int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0),
            "cached_tokens": int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)}


def anthropic_usage(usage: Mapping[str, Any] | None) -> dict[str, int]:
    usage = usage or {}
    return {"input_tokens": int(usage.get("input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0) + int(usage.get("cache_creation_input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cached_tokens": int(usage.get("cache_read_input_tokens") or 0)}


def gemini_usage(usage: Mapping[str, Any] | None) -> dict[str, int]:
    usage = usage or {}
    thoughts = int(usage.get("thoughtsTokenCount") or 0)
    return {"input_tokens": int(usage.get("promptTokenCount") or 0),
            "output_tokens": int(usage.get("candidatesTokenCount") or 0) + thoughts,
            "reasoning_tokens": thoughts,
            "cached_tokens": int(usage.get("cachedContentTokenCount") or 0)}


# --- tracing -------------------------------------------------------------------------------

_tracer = None


def setup_tracing(service_name: str = "hirelens-ml") -> bool:
    """Export spans over OTLP/HTTP when OTEL_EXPORTER_OTLP_ENDPOINT is set. Safe to call twice."""
    global _tracer
    if _tracer is not None or not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip():
        return _tracer is not None
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.warning("OTEL_EXPORTER_OTLP_ENDPOINT is set but OpenTelemetry is not installed")
        return False
    name = os.environ.get("OTEL_SERVICE_NAME", service_name)
    provider = TracerProvider(resource=Resource.create({"service.name": name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))  # reads the endpoint itself
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("hirelens")
    return True


def _current_span():
    if _tracer is None:
        return None
    from opentelemetry import trace
    span = trace.get_current_span()
    return span if span.is_recording() else None


@contextmanager
def span(name: str, headers: Mapping[str, str] | None = None, **attributes: Any) -> Iterator[None]:
    """A child span of the current one (or of the caller's trace, from `headers`), and stage timing.

    Without tracing this only times the stage for the usage summary.
    """
    started = time.monotonic()
    try:
        if _tracer is None:
            yield
            return
        from opentelemetry import propagate, trace
        from opentelemetry.trace import Status, StatusCode
        parent = propagate.extract(dict(headers)) if headers is not None else None
        with _tracer.start_as_current_span(name, context=parent, attributes=attributes,
                                           record_exception=False, set_status_on_exception=False) as current:
            try:
                yield
            except Exception as exc:
                # The exception type only: messages can contain provider or document text.
                current.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                raise
    finally:
        usage = _usage.get()
        if usage is not None:
            usage.stages[name] = usage.stages.get(name, 0.0) + time.monotonic() - started
