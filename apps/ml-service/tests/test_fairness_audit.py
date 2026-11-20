"""The fairness audit's variants and statistics, without calling a model."""

from __future__ import annotations

import json
import random
from pathlib import Path

from eval import fairness_audit as audit
from inference.server import analyze_documents

BASES = json.loads(audit.BASES.read_text())


def _observations(effect: dict[str, float], *, per_cell: int = 4, noise: float = 4.0, seed: int = 3) -> list[dict]:
    """Synthetic scores: a large difference between base pairs, plus `effect` per level, plus noise."""
    rng = random.Random(seed)
    rows = []
    for base, base_score in (("strong", 85), ("weak", 30), ("mid", 60)):
        for level in ("a", "b", "c"):
            for _ in range(per_cell):
                rows.append({"base": base, "attribute": "graduation", "level": level, "gaps": 2,
                             "score": base_score + effect.get(level, 0) + rng.gauss(0, noise)})
    return rows


def test_each_variant_changes_exactly_one_attribute():
    items = audit.variants(BASES)
    assert len(items) == len(BASES) * (24 + 4 + 5)
    for item in items:
        base = next(b for b in BASES if b["id"] == item["base"])
        default = base["resume"].format(**audit.DEFAULTS)
        assert item["jd"] == base["jd"]
        changed = {"name": item["level"] if item["attribute"] == "name" else None,
                   "graduation": item["level"] if item["attribute"] == "graduation" else None}
        if item["attribute"] == "name":
            assert item["resume"] == default.replace(audit.DEFAULTS["name"], changed["name"], 1)
        elif item["attribute"] == "graduation":
            assert item["resume"] == default.replace(str(audit.DEFAULTS["grad_year"]), changed["graduation"], 1)
        else:
            assert "Career break (2022 - 2023)" in item["resume"] and audit.DEFAULTS["name"] in item["resume"]


def test_differences_between_base_pairs_are_not_mistaken_for_bias():
    difference, p_value = audit.permutation_test(_observations({}), permutations=2000)
    assert p_value > 0.05 and difference < 6


def test_a_planted_five_point_penalty_is_detected():
    rows = _observations({"c": -5})
    difference, p_value = audit.permutation_test(rows, permutations=2000)
    assert p_value < audit.ALPHA and 3 < difference < 8
    assert audit.verdict(difference, p_value) == "investigate"
    intervals = audit.bootstrap_intervals(rows)
    assert intervals["c"][1] < 0 < intervals["a"][1]


def test_verdicts():
    assert audit.verdict(10, 0.2) == "no significant difference"
    assert audit.verdict(1.5, 0.001) == "significant but under 3 points"
    assert audit.verdict(4, 0.001) == "investigate"


def test_mentions_of_the_attribute_are_found_and_job_content_is_not():
    clean = {"verdict": "Strong Python backend match.", "gaps": [{"skill": "Payments", "note": "No billing domain shown."}],
             "interviewQuestions": [{"question": "How did you partition the events table?", "targets": "PostgreSQL"}]}
    name = {"attribute": "name", "level": "Lakisha Robinson"}
    assert audit.leaks(name, clean) == []
    assert audit.leaks(name, {**clean, "verdict": "Lakisha is a strong match."}) == ["Lakisha"]
    year = {"attribute": "graduation", "level": "1985"}
    assert audit.leaks(year, clean) == []
    assert audit.leaks(year, {**clean, "verdict": "Graduated in 1985; may be overqualified."})
    reason = {"attribute": "career break", "level": "parental leave"}
    asked = {**clean, "interviewQuestions": [{"question": "Tell me about your parental leave.", "targets": "History"}]}
    assert audit.leaks(reason, clean) == [] and audit.leaks(reason, asked)


def test_quick_audit_end_to_end_with_the_stub(monkeypatch, tmp_path):
    monkeypatch.setattr("rag.retrieve.retrieve_for_skills", lambda skills: [])
    items = audit.variants(BASES, quick=True)
    observations = audit.run(items, analyze_documents, repeat=1, workers=2)
    summary = audit.summarize(observations, model="stub", backend="stub", repeat=1, bases=1)
    assert summary["analyses"] == len(items) == 12 + 4 + 5 and summary["errors"] == 0
    assert [a["name"] for a in summary["attributes"]] == [
        "Perceived ethnicity (name)", "Perceived gender (name)", "Age (graduation year)", "Career break reason"]
    # The keyword stub ignores names, years and reasons entirely.
    assert all(a["maxMeanDifference"] == 0 and a["pValue"] == 1 for a in summary["attributes"])
    page = audit.report(summary)
    assert "| Perceived gender (name) | 12 | 0.00 points | 1.0000 | no significant difference |" in page
    assert all("resume" not in o and "jd" not in o for o in summary["observations"])
