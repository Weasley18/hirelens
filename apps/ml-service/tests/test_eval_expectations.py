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


def test_direct_mode_runs_cases_in_process_and_saves_results(tmp_path, monkeypatch):
    import json as _json

    import pytest

    from eval import run_eval

    calls = []

    def fake_direct(resume, jd):
        calls.append(resume)
        return {"fitScore": 70 + len(calls) * 20, "verdict": "Solid match with one gap.", "gaps": [],
                "strengths": ["Python services"], "interviewQuestions": [
                    {"question": "Describe a service you scaled.", "targets": "Python", "difficulty": "mid"},
                    {"question": "How do you test a migration?", "targets": "PostgreSQL", "difficulty": "mid"}]}

    monkeypatch.setattr(run_eval, "analyse_direct", fake_direct)
    out = tmp_path / "results.json"
    with pytest.raises(SystemExit):  # scores 90 then 110-range spread > 10 must be flagged
        run_eval.main(["--direct", "--only", "clean-match", "--repeat", "2", "--save", str(out)])
    saved = _json.loads(out.read_text())
    assert len(calls) == 2 and saved[0]["id"] == "clean-match" and saved[0]["scores"] == [90, 110]
