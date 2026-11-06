"""Step 3 of Phase 3: throw away most of what the teacher produced.

Curation quality beats volume for small-model fine-tuning. A teacher mistake that survives
into the training set does not stay a single bad example — the student learns the mistake as
a pattern. So every example is checked three ways before it is allowed in:

  1. Does it match the schema exactly?
  2. Is it internally coherent (a 95 fit score alongside three severe gaps is not)?
  3. Are the gaps grounded in the job description, or did the teacher invent requirements?

Run: python -m data_gen.curate --sample 300
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from common import read_jsonl, validate_analysis, write_jsonl
from inference.skills import extract_skills

RAW = Path("data/dataset_raw.jsonl")
CLEAN = Path("data/dataset_clean.jsonl")
REJECTED = Path("data/dataset_rejected.jsonl")

SEVERITY_WEIGHT = {"minor": 1, "moderate": 2, "severe": 4}


def consistency_issues(analysis: dict[str, Any]) -> list[str]:
    """Internal contradictions a human reviewer would catch immediately."""
    issues: list[str] = []
    score = analysis.get("fitScore", 0)
    gaps = analysis.get("gaps", []) or []
    questions = analysis.get("interviewQuestions", []) or []

    severities = [g.get("severity") for g in gaps]
    weight = sum(SEVERITY_WEIGHT.get(s, 0) for s in severities)

    if score >= 85 and "severe" in severities:
        issues.append(f"score {score} despite a severe gap")
    if score >= 90 and len(gaps) >= 3:
        issues.append(f"score {score} despite {len(gaps)} listed gaps")
    if score <= 40 and not gaps:
        issues.append(f"score {score} with no gaps listed")
    if score >= 70 and weight >= 8:
        issues.append(f"score {score} does not reflect gap severity (weight {weight})")

    texts = [q.get("question", "").strip().lower() for q in questions]
    if len(set(texts)) != len(texts):
        issues.append("duplicate interview questions")

    return issues


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]{3,}", text.lower()))


def grounding_issues(example: dict[str, Any]) -> list[str]:
    """A gap is something the job description asked for. If the JD never mentions it, the
    teacher invented a requirement, and training on that teaches the student to invent too.

    The check is deliberately narrow, because the obvious version is wrong. Comparing the
    gap's words against the JD's words rejects every correctly-identified gap that is phrased
    differently from the posting — a JD asking for "mentoring junior engineers" would see the
    gap "Team leadership" as invented. Those are not rare; they are most of the semantically
    interesting gaps, so lexical matching would systematically strip soft-skill gaps out of
    the dataset and teach the model never to produce them.

    So: resolve the gap through the skill vocabulary first, which knows that k8s and
    Kubernetes are one thing. Only fall back to word matching for single-word terms the
    vocabulary does not recognise, which are almost always technology names. Multi-word
    phrases it cannot resolve are left alone — a missed invention costs one example, while a
    false positive costs a whole category of them.
    """
    jd = example.get("jd", "")
    jd_skills = set(extract_skills(jd, limit=100))
    jd_tokens = _tokens(jd)
    issues: list[str] = []

    for gap in example.get("output", {}).get("gaps", []) or []:
        skill = gap.get("skill", "")
        resolved = set(extract_skills(skill, limit=10))

        if resolved:
            if not resolved & jd_skills:
                issues.append(f"gap '{skill}' is not mentioned in the job description")
        elif " " not in skill.strip():
            if _tokens(skill) and not (_tokens(skill) & jd_tokens):
                issues.append(f"gap '{skill}' is not mentioned in the job description")

    return issues


def review(example: dict[str, Any]) -> list[str]:
    """All problems with one example, in one list. Empty means it can be trained on."""
    output = example.get("output")
    if not isinstance(output, dict):
        return ["output is not an object"]

    return validate_analysis(output) + consistency_issues(output) + grounding_issues(example)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=300, help="cap on kept examples")
    args = parser.parse_args()

    raw = read_jsonl(RAW)
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    kept_count = 0

    # Prefer variety over volume: bucket by role archetype, then round-robin, so the
    # final set is not dominated by whichever role happened to generate first.
    by_role: dict[str, list[dict[str, Any]]] = {}

    for example in raw:
        issues = review(example)
        fingerprint = example.get("resume", "")[:200]

        if fingerprint in seen:
            issues.append("duplicate resume")
        if issues:
            rejected.append({**example, "issues": issues})
            continue

        seen.add(fingerprint)
        kept_count += 1
        role = example.get("meta", {}).get("role", "unknown")
        by_role.setdefault(role, []).append(
            {k: example[k] for k in ("resume", "jd", "output") if k in example}
        )

    balanced: list[dict[str, Any]] = []
    while len(balanced) < args.sample and any(by_role.values()):
        for bucket in by_role.values():
            if bucket and len(balanced) < args.sample:
                balanced.append(bucket.pop(0))

    write_jsonl(CLEAN, balanced)
    write_jsonl(REJECTED, rejected)

    print(f"raw:      {len(raw)}")
    print(f"rejected: {len(rejected)}")
    print(f"passed:   {kept_count}")
    print(f"kept:     {len(balanced)} -> {CLEAN}")

    reasons: dict[str, int] = {}
    for row in rejected:
        for issue in row["issues"]:
            key = issue.split(":")[0].split("'")[0].strip()
            reasons[key] = reasons.get(key, 0) + 1
    print("\ntop rejection reasons:")
    for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {count:4d}  {reason}")
    print("\nNow read 10 random lines of dataset_clean.jsonl yourself before training.")


if __name__ == "__main__":
    main()
