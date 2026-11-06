"""Load the knowledge base into Postgres (Phase 6.4).

Run: python -m rag.ingest [--reset]
Idempotent: re-running replaces chunks from the same source files rather than duplicating
them, so editing a knowledge file and re-ingesting is safe.
"""

from __future__ import annotations

import argparse
import os
import uuid
from pathlib import Path

import psycopg

from rag.chunking import chunk_directory
from rag.embedder import DIMENSIONS, embed_documents

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="delete all chunks first")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set — see .env.example")

    chunks = chunk_directory(KNOWLEDGE_DIR)
    print(f"{len(chunks)} chunks from {KNOWLEDGE_DIR}")

    print("embedding...")
    vectors = embed_documents([c["content"] for c in chunks])

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

        if args.reset:
            cur.execute('DELETE FROM "KnowledgeChunk"')
        else:
            sources = list({c["source"] for c in chunks})
            cur.execute('DELETE FROM "KnowledgeChunk" WHERE source = ANY(%s)', (sources,))

        for chunk, vector in zip(chunks, vectors):
            cur.execute(
                'INSERT INTO "KnowledgeChunk" (id, content, source, embedding) '
                "VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()), chunk["content"], chunk["source"], str(vector)),
            )

        # Exact search is fine at this size; the index matters past a few thousand rows.
        cur.execute(
            'CREATE INDEX IF NOT EXISTS knowledgechunk_embedding_idx ON "KnowledgeChunk" '
            "USING hnsw (embedding vector_cosine_ops)"
        )
        conn.commit()

        cur.execute('SELECT count(*) FROM "KnowledgeChunk"')
        print(f"knowledge base now holds {cur.fetchone()[0]} chunks ({DIMENSIONS}-dim)")


if __name__ == "__main__":
    main()
