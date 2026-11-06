"""Step 1 of Phase 3: invent the (resume, JD) inputs.

Run: python -m data_gen.make_pairs --count 400
Writes data/pairs.jsonl. Re-running appends only what is missing, so a crashed run
halfway through a free-tier quota is not wasted.
"""

from __future__ import annotations

import argparse
import itertools
import random
import time
from pathlib import Path

from common import extract_json, read_jsonl, write_jsonl
from data_gen.archetypes import ROLES, SENIORITIES, TWISTS
from data_gen.generate import document_as_text
from data_gen.teacher import call_teacher

OUT = Path("data/pairs.jsonl")

PAIR_PROMPT = """Invent one realistic (resume, job description) pair for testing a recruiting tool.

Role: {role}
Typical stack: {stack}
Candidate seniority: {seniority} ({seniority_note})
Situation: {twist}

The resume should read like a real resume: a summary line, 1-3 roles with company names,
bullet points with concrete systems and numbers, an education line, a skills line.
The job description should read like a real posting: responsibilities and requirements,
including 2-4 specific technologies.

Neither document should mention the other. Do not make them artificially matched or
artificially mismatched beyond the situation described above.

Output ONLY a JSON object: {{"resume": "...", "jd": "..."}}"""


def combinations() -> list[dict]:
    combos = [
        {"role": role, "stack": stack, "seniority": level, "seniority_note": note, "twist": twist}
        for (role, stack), (level, note), twist in itertools.product(ROLES, SENIORITIES, TWISTS)
    ]
    random.shuffle(combos)
    return combos


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=400)
    parser.add_argument("--sleep", type=float, default=1.0, help="stay under free-tier rate limits")
    args = parser.parse_args()

    existing = read_jsonl(OUT) if OUT.exists() else []
    print(f"{len(existing)} pairs already generated", flush=True)

    combos = combinations()
    attempts = 0
    i = len(existing)
    while len(existing) < args.count:
        spec = combos[i % len(combos)]
        i += 1
        attempts += 1
        if attempts > args.count * 3:
            print("too many failed attempts, stopping", flush=True)
            break
        try:
            pair = extract_json(call_teacher(PAIR_PROMPT.format(**spec), temperature=1.0))
            resume = document_as_text(pair.get("resume"))
            jd = document_as_text(pair.get("jd"))
            if len(resume) < 80 or len(jd) < 60:
                raise ValueError("missing resume or jd")
            existing.append({"resume": resume, "jd": jd, "meta": spec})
        except Exception as exc:  # noqa: BLE001
            print(f"  skipped {i}: {exc}", flush=True)
            continue

        if len(existing) % 20 == 0:
            write_jsonl(OUT, existing)
            print(f"  {len(existing)} pairs", flush=True)
        time.sleep(args.sleep)

    write_jsonl(OUT, existing)
    print(f"wrote {len(existing)} pairs to {OUT}", flush=True)


if __name__ == "__main__":
    main()
