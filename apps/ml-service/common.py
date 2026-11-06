"""Helpers shared by data generation, training, inference and evaluation.

Everything here is pure and dependency-light on purpose: the Lambda image imports it,
and so do the tests, which never have a model or a database available.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_SCHEMA = _HERE.parents[1] / "packages" / "shared" / "analysis.schema.json"
_BUNDLED_SCHEMA = _HERE / "analysis.schema.json"

# In the repo the schema lives in packages/shared. The Lambda image flattens the tree, so
# the Dockerfile copies it next to this file — checked first, since that is the deployed case.
SCHEMA_PATH = _BUNDLED_SCHEMA if _BUNDLED_SCHEMA.exists() else _REPO_SCHEMA


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """The same analysis.schema.json the TypeScript side mirrors in zod."""
    return json.loads(SCHEMA_PATH.read_text())


def extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of model output.

    Models wrap JSON in prose or ```json fences often enough that parsing the raw string
    fails on output that is otherwise perfectly good. This finds the outermost balanced
    object instead. Raises ValueError when there is nothing usable.
    """
    if not text:
        raise ValueError("empty model output")

    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in model output")

    depth = 0
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        char = text[i]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])

    raise ValueError("unterminated JSON object in model output")


def validate_analysis(analysis: dict[str, Any]) -> list[str]:
    """Return schema violations as readable strings. Empty list means valid."""
    from jsonschema import Draft7Validator

    validator = Draft7Validator(load_schema())
    return [
        f"{'.'.join(str(p) for p in error.path) or '(root)'}: {error.message}"
        for error in sorted(validator.iter_errors(analysis), key=lambda e: list(e.path))
    ]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n")
