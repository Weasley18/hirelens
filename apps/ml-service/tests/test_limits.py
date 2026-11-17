"""Input caps must fit the model context, and the API and ML service must agree on them."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from inference import limits, llm
from inference.prompt import MAX_CONTEXT_CHARS, SYSTEM_PROMPT

SHARED_TS = Path(__file__).resolve().parents[3] / "packages" / "shared" / "src" / "analysis.ts"


def _ts_constant(name: str) -> int:
    match = re.search(rf"export const {name} = (\d+);", SHARED_TS.read_text())
    assert match, f"{name} not found in {SHARED_TS}"
    return int(match.group(1))


@pytest.mark.parametrize("name", ["RESUME_MIN", "RESUME_MAX", "JD_MIN", "JD_MAX"])
def test_typescript_and_python_caps_match(name):
    assert _ts_constant(name) == getattr(limits, name)


def test_maximum_inputs_leave_room_for_the_answer():
    template_overhead = 200  # chat tags, section labels, JSON quoting
    prompt_chars = (
        limits.RESUME_MAX + limits.JD_MAX + MAX_CONTEXT_CHARS + len(SYSTEM_PROMPT) + template_overhead
    )
    estimated_prompt_tokens = prompt_chars / limits.CHARS_PER_TOKEN_ESTIMATE
    assert estimated_prompt_tokens + limits.OUTPUT_TOKENS <= limits.CONTEXT_TOKENS


def test_serving_uses_the_shared_context():
    assert llm.N_CTX == limits.CONTEXT_TOKENS
    assert llm.MAX_TOKENS == limits.OUTPUT_TOKENS


def test_training_scripts_use_the_shared_context():
    root = Path(__file__).resolve().parents[1] / "training"
    for name in ("train.py", "merge_and_export.py", "evaluate.py"):
        source = (root / name).read_text()
        assert "2048" not in source, f"{name} hard-codes a context length"
        assert "CONTEXT_TOKENS" in source, f"{name} does not use inference.limits"
