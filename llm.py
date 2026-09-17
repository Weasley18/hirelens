"""Producing an analysis, with two backends.

`gguf` is the real one: the fine-tuned, quantized model from Phase 5.

`stub` exists because Phases 4 and 5 need a GPU and several hours, while Phases 2, 6, 7, 9
and 10 are all testable without them. It is a test double, not a fallback — it derives its
answer deterministically from the actual resume, JD and retrieved chunks, so it exercises
skill extraction, retrieval and the full request path, and it never pretends to be the model:
/health reports which backend is live and the UI says so.

Set MODEL_BACKEND=gguf once hirelens-q4.gguf exists.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from common import extract_json
from inference.prompt import build_chat_prompt
from inference.skills import extract_skills, jd_only_skills

BACKEND = os.environ.get("MODEL_BACKEND", "stub")
MODEL_PATH = os.environ.get("MODEL_PATH", "./hirelens-q4.gguf")
N_CTX = 2048
MAX_TOKENS = 800

# Low, not zero: the task needs one reliable JSON object, not creative variety.
TEMPERATURE = 0.2


@lru_cache(maxsize=1)
def get_llm():
    from llama_cpp import Llama

    return Llama(
        model_path=MODEL_PATH,
        n_ctx=N_CTX,
        n_threads=int(os.environ.get("LLAMA_THREADS", "4")),
        verbose=False,
    )


def _generate_gguf(resume: str, jd: str, chunks: list[dict]) -> dict[str, Any]:
    prompt = build_chat_prompt(resume, jd, chunks)

    output = get_llm()(
        prompt,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        stop=["<|im_end|>"],
    )

    return extract_json(output["choices"][0]["text"])


_SEVERITIES = ["severe", "moderate", "minor"]


def _generate_stub(resume: str, jd: str, chunks: list[dict]) -> dict[str, Any]:
    resume_skills = extract_skills(resume, limit=8)
    jd_skills = extract_skills(jd, limit=8)
    missing = jd_only_skills(resume, jd, limit=3)

    overlap = len(set(resume_skills) & set(jd_skills))
    required = max(len(jd_skills), 1)
    fit_score = max(35, min(95, round(35 + 60 * overlap / required)))

    gaps = [
        {
            "skill": skill,
            "severity": _SEVERITIES[min(i, len(_SEVERITIES) - 1)],
            "note": f"The job description asks for {skill}; the resume does not evidence it.",
        }
        for i, skill in enumerate(missing)
    ]

    strengths = [
        f"{skill} experience, evidenced in the resume" for skill in resume_skills[:4]
    ] or ["Relevant experience described in the resume"]

    questions = [
        {
            "question": chunk["content"].split(". ", 1)[-1][:340].strip(),
            "targets": chunk["source"].split(": ")[-1][:80],
            "difficulty": "mid",
        }
        for chunk in chunks[:4]
    ]

    while len(questions) < 2:
        skill = (missing + resume_skills + ["your recent work"])[len(questions)]
        questions.append(
            {
                "question": f"Walk me through a decision you made involving {skill}, "
                "and what you would do differently now.",
                "targets": skill[:80],
                "difficulty": "mid",
            }
        )

    verdict = (
        f"Overlaps on {overlap} of {required} required areas"
        + (f"; main gap is {missing[0]}." if missing else "; no obvious gaps against the JD.")
    )

    return {
        "fitScore": fit_score,
        "verdict": verdict[:240],
        "gaps": gaps,
        "strengths": strengths,
        "interviewQuestions": questions,
    }


def generate_analysis(resume: str, jd: str, chunks: list[dict]) -> dict[str, Any]:
    if BACKEND == "gguf":
        return _generate_gguf(resume, jd, chunks)
    if BACKEND == "stub":
        return _generate_stub(resume, jd, chunks)
    raise RuntimeError(f"Unknown MODEL_BACKEND: {BACKEND!r} (expected 'gguf' or 'stub')")
