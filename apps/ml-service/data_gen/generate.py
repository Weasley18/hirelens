"""Step 2 of Phase 3: label each pair with the teacher model.

Run: python -m data_gen.generate
Reads data/pairs.jsonl, writes data/dataset_raw.jsonl.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from common import read_jsonl, write_jsonl
from data_gen.teacher import analyse_pair

PAIRS = Path("data/pairs.jsonl")
OUT = Path("data/dataset_raw.jsonl")


def document_as_text(value: object) -> str:
    """Teachers sometimes emit resume/jd as nested objects. Flatten to prose."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, list):
                lines.append(f"{key}:")
                for entry in item:
                    if isinstance(entry, dict):
                        lines.append("- " + "; ".join(f"{k}: {v}" for k, v in entry.items()))
                    else:
                        lines.append(f"- {entry}")
            else:
                lines.append(f"{key}: {item}")
        return "\n".join(lines).strip()
    if value is None:
        return ""
    return str(value).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args()

    pairs = read_jsonl(PAIRS)
    done = read_jsonl(OUT) if OUT.exists() else []
    seen = {document_as_text(row["resume"])[:200] for row in done}

    for i, pair in enumerate(pairs):
        resume = document_as_text(pair.get("resume"))
        jd = document_as_text(pair.get("jd"))
        if resume[:200] in seen:
            continue
        try:
            output = analyse_pair(resume, jd)
            done.append({"resume": resume, "jd": jd, "output": output, "meta": pair.get("meta", {})})
            seen.add(resume[:200])
        except Exception as exc:  # noqa: BLE001
            print(f"  skipped {i}: {exc}", flush=True)
            continue

        if len(done) % 20 == 0:
            write_jsonl(OUT, done)
            print(f"  {len(done)}/{len(pairs)} labelled", flush=True)
        time.sleep(args.sleep)

    write_jsonl(OUT, done)
    print(f"wrote {len(done)} examples to {OUT}", flush=True)


if __name__ == "__main__":
    main()
