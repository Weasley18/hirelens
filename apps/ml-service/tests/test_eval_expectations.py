"""The manual evaluation's automatic expectations, without a running stack."""

from __future__ import annotations

import json
from pathlib import Path

from eval.run_eval import expectation_issues, group_issues
from inference.limits import JD_MAX, JD_MIN, RESUME_MAX, RESUME_MIN

CASES = json.loads((Path(__file__).resolve().parents[1] / "eval" / "manual_pairs.json").read_text())


def _result(score, gaps=()):
    return {"fitScore": score, "gaps": [{"skill": g, "severity": "moderate", "note": "x" * 12} for g in gaps]}


def test_every_case_is_submittable_and_ids_are_unique():
    assert len({c["id"] for c in CASES}) == len(CASES)
    for case in CASES:
        assert RESUME_MIN <= len(case["resume"].strip()) <= RESUME_MAX, case["id"]
        assert JD_MIN <= len(case["jd"].strip()) <= JD_MAX, case["id"]
        assert "<|" not in case["resume"] + case["jd"]


def test_counterfactual_groups_have_at_least_two_members():
    groups = {}
    for case in CASES:
        if group := case.get("assert", {}).get("group"):
            groups.setdefault(group, []).append(case["id"])
    assert groups and all(len(members) >= 2 for members in groups.values())


def test_score_bounds_and_required_gaps():
    case = {"assert": {"max_score": 45, "min_gaps": 2, "must_gap": ["spark"]}}
    assert expectation_issues(case, _result(30, ["Apache Spark", "Airflow"])) == []
    issues = expectation_issues(case, _result(100, []))
    assert len(issues) == 3


def test_group_spread_and_missing_results():
    cases = [{"id": "a", "assert": {"group": "g", "tolerance": 5}}, {"id": "b", "assert": {"group": "g", "tolerance": 5}}]
    assert group_issues(cases, {"a": 70, "b": 74}) == []
    assert "spread 10" in group_issues(cases, {"a": 70, "b": 80})[0]
    assert "no result for b" in group_issues(cases, {"a": 70})[0]
