"""Text to 384-dimensional vectors.

bge-small-en-v1.5 is asymmetric: it was trained with a short instruction prefix on the query
side and none on the document side. Skipping that prefix still "works" — it returns results —
but measurably worse ones, and nothing about the output looks wrong. Hence the two functions.
"""

from __future__ import annotations

import os
from functools import lru_cache

MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
DIMENSIONS = 384


@lru_cache(maxsize=1)
def get_embedder():
    """Loaded once per process. In Lambda that means once per cold start."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def embed_documents(texts: list[str]) -> list[list[float]]:
    embeddings = get_embedder().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [vector.tolist() for vector in embeddings]


def embed_query(text: str) -> list[float]:
    embedding = get_embedder().encode(
        QUERY_PREFIX + text, normalize_embeddings=True, show_progress_bar=False
    )
    return embedding.tolist()
