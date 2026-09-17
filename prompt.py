"""The one place a prompt is assembled.

Training (Phase 4) imports `build_user_turn` from here and so does the inference server, on
purpose. A model fine-tuned on one prompt layout and served with a slightly different one
degrades quietly — output that is still plausible, just worse — which is close to impossible
to spot from logs. Sharing the function makes the two physically incapable of drifting.
"""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are a technical recruiting assistant. Analyze the resume against the job "
    "description and output only valid JSON matching the required schema."
)

MAX_CONTEXT_CHARS = 2400


def format_context(chunks: list[dict]) -> str:
    """Retrieved chunks as the model sees them, truncated to a sane budget.

    The context window is 2048 tokens and the resume and JD have first claim on it, so
    retrieval gets a fixed char budget rather than however much the database returned.
    """
    lines: list[str] = []
    used = 0

    for chunk in chunks:
        line = f"- {chunk['content'].strip()} (source: {chunk['source']})"
        if used + len(line) > MAX_CONTEXT_CHARS:
            break
        lines.append(line)
        used += len(line)

    return "\n".join(lines)


def build_user_turn(resume: str, jd: str, chunks: list[dict] | None = None) -> str:
    """The user message content. Identical at training time and at request time."""
    sections = []

    if chunks:
        sections.append(f"RELEVANT REFERENCE MATERIAL:\n{format_context(chunks)}")

    sections.append(f"RESUME:\n{resume.strip()}")
    sections.append(f"JOB DESCRIPTION:\n{jd.strip()}")

    return "\n\n".join(sections)


def build_chat_prompt(resume: str, jd: str, chunks: list[dict] | None = None) -> str:
    """Qwen2.5's chat template, written out rather than imported.

    llama.cpp's completion API takes a raw string, so the template has to be applied by hand.
    These exact tags are what Qwen was trained on; a generic template produces noticeably
    worse output for reasons that are invisible unless you go looking.
    """
    return (
        f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{build_user_turn(resume, jd, chunks)}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
