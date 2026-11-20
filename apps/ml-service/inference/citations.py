"""Evidence citations: every strength quotes the resume, every gap quotes the job description.

The model copies a short excerpt for each claim; this module checks the excerpt really occurs in
the document it cites. A claim whose excerpt cannot be found is unsupported and is never shown:
the hosted backend retries once, and anything still unsupported is removed and counted.

Matching tolerates formatting, not content: case, whitespace and line breaks, curly versus
straight quotes, dash styles, bullet characters, and an excerpt shortened with "..." (each piece
must occur, in order). It does not tolerate paraphrase.
"""

from __future__ import annotations

import contextvars
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

MIN_FRAGMENT_CHARS = 8

# Claims a backend already removed before returning (the hosted backend, when its retry budget ran
# out). The server adds them to the count it reports, so removals are never hidden.
removed_upstream: contextvars.ContextVar[int] = contextvars.ContextVar("citations_removed_upstream", default=0)
_TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    "•": " ", "·": " ", "▪": " ", "●": " ", "‣": " ", " ": " ",
})
_ELLIPSIS = re.compile(r"\s*(?:\.\.\.+|…)\s*")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").translate(_TRANSLATE).lower()
    return re.sub(r"\s+", " ", text).strip()


def _fragments(excerpt: str) -> list[str]:
    cleaned = normalize(excerpt).strip(" \"'")
    pieces = [piece.strip(" \"'.,;:") for piece in _ELLIPSIS.split(cleaned)]
    return [piece for piece in pieces if piece]


def occurs_in(excerpt: str, document: str) -> bool:
    """True when every piece of the excerpt occurs in the document, in order."""
    pieces = _fragments(excerpt)
    if not pieces or sum(len(piece) for piece in pieces) < MIN_FRAGMENT_CHARS:
        return False
    haystack = normalize(document)
    position = 0
    for piece in pieces:
        found = haystack.find(piece, position)
        if found < 0:
            return False
        position = found + len(piece)
    return True


@dataclass
class CitationReport:
    checked: int = 0
    removed: list[str] = field(default_factory=list)

    @property
    def verified(self) -> int:
        return self.checked - len(self.removed)


def verify(analysis: dict[str, Any], resume: str, jd: str) -> tuple[dict[str, Any], CitationReport]:
    """Return a copy with unsupported strengths and gaps removed, and what was checked.

    Removal never invents anything: if no strength survives, the caller treats the answer as
    invalid (the schema requires at least one strength).
    """
    report = CitationReport()
    kept: dict[str, Any] = dict(analysis)
    for name, key, document in (("strengths", "evidence", resume), ("gaps", "requirement", jd)):
        items = analysis.get(name)
        if not isinstance(items, list):
            continue
        survivors = []
        for index, item in enumerate(items):
            report.checked += 1
            excerpt = item.get(key) if isinstance(item, dict) else None
            if isinstance(excerpt, str) and occurs_in(excerpt, document):
                survivors.append(item)
            else:
                report.removed.append(f"{name}.{index}")
        kept[name] = survivors
    return kept, report


def supported_items(name: str, items: Any, resume: str, jd: str) -> Any:
    """Streaming drafts: drop unsupported items before a partial field is shown."""
    if name not in ("strengths", "gaps") or not isinstance(items, list):
        return items
    key, document = ("evidence", resume) if name == "strengths" else ("requirement", jd)
    return [item for item in items
            if isinstance(item, dict) and isinstance(item.get(key), str) and occurs_in(item[key], document)]
