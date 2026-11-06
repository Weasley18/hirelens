"""Split the knowledge base into retrievable pieces.

Chunk size is the whole game in retrieval quality. A chunk covering five technologies has a
blurry average meaning and matches every query weakly; a chunk about exactly one thing
matches its own query strongly and everything else not at all — which is what you want,
because retrieval returns a fixed number of results either way.

The knowledge files are written with that in mind: one `##` section per topic, and a section
is one chunk. Sections that grow past the size ceiling are split on paragraph boundaries
rather than mid-sentence.
"""

from __future__ import annotations

import re
from pathlib import Path

MAX_CHARS = 900
MIN_CHARS = 120


def _split_oversized(body: str) -> list[str]:
    """Break a long section on paragraph boundaries, packing up to MAX_CHARS."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > MAX_CHARS and current:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def chunk_markdown(text: str, filename: str) -> list[dict[str, str]]:
    """One markdown document to a list of {content, source} chunks.

    `source` is carried all the way to the model's prompt and into the UI, so it names the
    document and the section rather than a file path — a recruiter reading "PostgreSQL:
    Indexing and query plans" learns something; "kb_0042" does not.
    """
    title_match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else Path(filename).stem

    sections = re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]
    chunks: list[dict[str, str]] = []

    for section in sections:
        lines = section.split("\n", 1)
        heading = lines[0].strip()
        body = (lines[1] if len(lines) > 1 else "").strip()

        if len(body) < MIN_CHARS:
            continue

        for piece in _split_oversized(body):
            chunks.append({"content": f"{heading}. {piece}", "source": f"{title}: {heading}"})

    return chunks


def chunk_directory(directory: Path) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    for path in sorted(directory.glob("*.md")):
        chunks.extend(chunk_markdown(path.read_text(), path.name))
    return chunks
