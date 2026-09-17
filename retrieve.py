"""Vector search against the knowledge base (Phase 6.5).

One query per skill rather than one query for the whole resume, deliberately. Embedding a
whole resume produces the average of everything in it, which is close to nothing in
particular and retrieves generic chunks. Embedding "Kubernetes" retrieves Kubernetes
material. The cost is several small queries instead of one, which at this corpus size is
irrelevant next to the model call.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg

# smaller cosine distance = closer meaning, so ascending order is most-relevant-first
SEARCH_SQL = """
SELECT id, content, source, 1 - (embedding <=> %s::vector) AS similarity
FROM "KnowledgeChunk"
WHERE embedding IS NOT NULL
ORDER BY embedding <=> %s::vector
LIMIT %s
"""

MIN_SIMILARITY = 0.3

_connection: psycopg.Connection | None = None


def get_connection() -> psycopg.Connection:
    """Reused across invocations so a warm Lambda does not reconnect per request."""
    global _connection

    if _connection is None or _connection.closed:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is not set")
        _connection = psycopg.connect(database_url, connect_timeout=10)

    return _connection


def search(query: str, limit: int = 3) -> list[dict[str, Any]]:
    from rag.embedder import embed_query

    vector = str(embed_query(query))

    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(SEARCH_SQL, (vector, vector, limit))
            rows = cur.fetchall()
    except psycopg.OperationalError:
        # A pooled connection can be closed under us between requests; one retry, then give up.
        global _connection
        _connection = None
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(SEARCH_SQL, (vector, vector, limit))
            rows = cur.fetchall()

    return [
        {"id": row[0], "content": row[1], "source": row[2], "similarity": float(row[3])}
        for row in rows
    ]


def retrieve_for_skills(skills: list[str], per_skill: int = 2, total: int = 6) -> list[dict[str, Any]]:
    """Context for a request, ordered by the skill list's own priority.

    `skills` arrives with likely gaps first (see inference/skills.jd_only_skills), so when the
    budget runs out it is the least important skill that loses its context, not an arbitrary one.
    """
    if not skills:
        return []

    collected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for skill in skills:
        for chunk in search(f"{skill} interview questions and evaluation signals", limit=per_skill):
            if chunk["id"] in seen or chunk["similarity"] < MIN_SIMILARITY:
                continue
            seen.add(chunk["id"])
            collected.append(chunk)
            if len(collected) >= total:
                return collected

    return collected


if __name__ == "__main__":
    import sys

    term = sys.argv[1] if len(sys.argv) > 1 else "Kubernetes"
    for result in search(f"{term} interview questions and evaluation signals"):
        print(f"[{result['similarity']:.3f}] {result['source']}")
        print(f"        {result['content'][:140]}...\n")
