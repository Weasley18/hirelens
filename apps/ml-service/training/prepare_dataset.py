"""Turn dataset_clean.jsonl into the exact text the model will be trained on.

One decision here is not in the build guide and matters more than it looks:

  At request time the prompt contains a RELEVANT REFERENCE MATERIAL block (Phase 6). If the
  model is trained on prompts that never contain that block, then at inference it meets an
  unfamiliar section sitting between the system turn and the resume. It does not crash — it
  quietly gets worse, which is the hardest kind of regression to notice.

  So retrieval runs here too, and training examples carry the same block. That means the
  knowledge base must be ingested (Phase 6) before training (Phase 4) — a reordering of the
  guide. `--context none` skips it if you want to train before the knowledge base exists,
  at the cost of that skew.

Run: python -m training.prepare_dataset --heldout 20
Writes data/train.jsonl and data/heldout.jsonl.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from common import read_jsonl, write_jsonl, document_fingerprint
from inference.prompt import build_chat_prompt
from inference.skills import extract_skills, jd_only_skills

CLEAN = Path("data/dataset_clean.jsonl")
TRAIN = Path("data/train.jsonl")
HELDOUT = Path("data/heldout.jsonl")


def format_example(example: dict, chunks: list[dict] | None) -> dict:
    """Prompt plus the target completion, as one training string."""
    prompt = build_chat_prompt(example["resume"], example["jd"], chunks)
    completion = json.dumps(example["output"], ensure_ascii=False)
    return {"text": f"{prompt}{completion}<|im_end|>"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--heldout", type=int, default=20)
    parser.add_argument("--context", choices=["retrieve", "none"], default="retrieve")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    examples = read_jsonl(CLEAN)
    random.Random(args.seed).shuffle(examples)

    retriever = None
    if args.context == "retrieve":
        from rag.retrieve import retrieve_for_skills

        retriever = retrieve_for_skills

    if args.heldout < 1 or args.heldout >= len(examples):
        raise ValueError("Held-out size must leave both evaluation and training examples")
    heldout_ids = set()
    heldout_count = 0
    for example in examples:
        if heldout_count >= args.heldout:
            break
        key = document_fingerprint(example["resume"])
        if key not in heldout_ids:
            heldout_ids.add(key)
            heldout_count += sum(document_fingerprint(row["resume"]) == key for row in examples)
    formatted = []
    heldout_rows = []
    for example in examples:
        chunks = None
        if retriever:
            skills = extract_skills(example["resume"], example["jd"], limit=6)
            gaps = jd_only_skills(example["resume"], example["jd"], limit=3)
            chunks = retriever(list(dict.fromkeys(gaps + skills)))
        if document_fingerprint(example["resume"]) in heldout_ids:
            heldout_rows.append({**example, "chunks": chunks or []})
        else:
            formatted.append(format_example(example, chunks))

    if not formatted:
        raise ValueError("Resume grouping leaves no training examples")
    write_jsonl(HELDOUT, heldout_rows)
    write_jsonl(TRAIN, formatted)

    print(f"train:   {len(formatted)} -> {TRAIN}")
    print(f"heldout: {len(heldout_rows)} -> {HELDOUT}  (never seen during training)")
    print("Prepared prompts and recorded held-out context; review the dataset locally before training.")


if __name__ == "__main__":
    main()
