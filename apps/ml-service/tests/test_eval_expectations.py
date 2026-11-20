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
        return {"result": {"fitScore": 70 + len(calls) * 20, "verdict": "Solid match with one gap.", "gaps": [],
                "strengths": [{"text": "Python services", "evidence": "Python services"}], "interviewQuestions": [
                    {"question": "Describe a service you scaled.", "targets": "Python", "difficulty": "mid"},
                    {"question": "How do you test a migration?", "targets": "PostgreSQL", "difficulty": "mid"}]},
                "metadata": {"backend": "stub", "grounded": False, "citations": {"checked": 1, "removed": 0}}}

    monkeypatch.setattr(run_eval, "analyse_direct", fake_direct)
    out = tmp_path / "results.json"
    with pytest.raises(SystemExit):  # scores 90 then 110-range spread > 10 must be flagged
        run_eval.main(["--direct", "--only", "clean-match", "--repeat", "2", "--save", str(out)])
    saved = _json.loads(out.read_text())
    assert len(calls) == 2 and saved[0]["id"] == "clean-match" and saved[0]["scores"] == [90, 110]


def test_groups_compare_average_scores_across_repeats():
    cases = [{"id": "a", "assert": {"group": "g", "tolerance": 5}}, {"id": "b", "assert": {"group": "g", "tolerance": 5}}]
    # The run that triggered a false alarm: first runs 84 vs 78, but identical 78-84 ranges.
    assert group_issues(cases, {"a": [84, 80, 78], "b": [78, 82, 84]}) == []
    issues = group_issues(cases, {"a": [90, 92, 91], "b": [80, 82, 81]})
    assert issues and "average spread 10.0" in issues[0]


def test_must_not_gap_and_word_start_matching():
    rules = {"assert": {"must_gap": ["go"], "must_not_gap": ["break", "tenure"]}}
    ok = _result(40, ["Production Go services", "Kubernetes"])
    assert expectation_issues(rules, ok) == []
    # "go" must not be satisfied by "algorithms"; listing a career break as a gap is flagged.
    issues = expectation_issues(rules, _result(40, ["Algorithms", "Career break", "Short tenure"]))
    assert any("expected a gap for 'go'" in i for i in issues)
    assert sum("should not be treated as a skills gap" in i for i in issues) == 2


def test_every_case_assertion_uses_known_rules():
    known = {"min_score", "max_score", "min_gaps", "must_gap", "must_not_gap", "group", "tolerance"}
    for case in CASES:
        assert set(case.get("assert", {})) <= known, case["id"]


def test_grounding_accepts_a_term_ending_a_sentence():
    from data_gen.curate import grounding_issues

    jd = "Familiarity with automotive protocols such as CAN and LIN. Node.js is a plus."
    gaps = [{"skill": "LIN"}, {"skill": "Node.js"}, {"skill": "Zephyr"}]
    assert grounding_issues({"jd": jd, "output": {"gaps": gaps}}) == [
        "gap 'Zephyr' is not mentioned in the job description"
    ]


def _envelope(score, checked=6, removed=0, cost=0.001):
    return {"result": {"fitScore": score}, "metadata": {"backend": "hosted", "citations": {"checked": checked, "removed": removed}},
            "telemetry": {"model": "gpt-6-luna", "inputTokens": 3000, "outputTokens": 1000, "costUsd": cost}}


def _records():
    return [
        {"id": "counterfactual-name-a", "scores": [70, 72], "problems": [], "seconds": [8.0, 9.0],
         "envelopes": [_envelope(70), _envelope(72)]},
        {"id": "counterfactual-name-b", "scores": [71, 71], "problems": [], "seconds": [10.0, 30.0],
         "envelopes": [_envelope(71, removed=1), _envelope(71)]},
    ]


def test_run_summary_tracks_quality_citations_latency_and_cost():
    from eval.run_eval import gate_failures, summarize
    cases = [c for c in CASES if c["id"] in ("counterfactual-name-a", "counterfactual-name-b")]
    summary = summarize(_records(), cases, mode="direct", repeat=2, subset="ci")
    assert (summary["passed"], summary["passRate"], summary["analyses"]) == (2, 1.0, 4)
    assert summary["citations"] == {"checked": 24, "removed": 1, "supportRate": 0.9583}
    assert summary["latencySeconds"] == {"p50": 9.0, "p95": 30.0}
    assert summary["costUsd"] == {"total": 0.004, "perAnalysis": 0.001}
    assert summary["fairness"] == {"spreads": {"name": 0.0}, "failures": []}
    assert summary["model"] == "gpt-6-luna" and gate_failures(summary) == []
    assert "resume" not in json.dumps(summary).lower()


def test_gate_fails_on_errors_flags_and_unquoted_claims():
    from eval.run_eval import gate_failures, markdown, summarize
    cases = [c for c in CASES if c["id"] in ("counterfactual-name-a", "counterfactual-name-b")]
    records = _records()
    records[0]["envelopes"] = [_envelope(70, checked=10, removed=4)] * 2
    records[1].update(error="TimeoutError: slow", envelopes=[], scores=[])
    summary = summarize(records, cases, mode="direct", repeat=2, subset="ci")
    reasons = gate_failures(summary)
    assert any("could not be analysed" in r for r in reasons)
    assert any("quoted the documents" in r for r in reasons)
    assert any("no result for counterfactual-name-b" in r for r in reasons)
    page = markdown(summary, baseline=summarize(_records(), cases, mode="direct", repeat=2, subset="ci"))
    assert page.startswith("### HireLens evaluation: failed")
    assert "| Claims backed by a quote | 60% | 96% |" in page


def test_dashboard_renders_history_charts_and_fairness():
    from eval.dashboard import render
    from eval.run_eval import summarize
    cases = [c for c in CASES if c["id"] in ("counterfactual-name-a", "counterfactual-name-b")]
    first = {**summarize(_records(), cases, mode="direct", repeat=2, subset="all"), "timestamp": "2026-11-20T00:00:00+00:00"}
    second = {**first, "timestamp": "2026-11-27T00:00:00+00:00", "commit": "abcdef123456"}
    fairness = {"timestamp": "2026-11-27T00:00:00+00:00", "model": "gpt-6-luna", "variants": 132, "bases": 4,
                "attributes": [{"name": "Perceived gender (name)", "maxMeanDifference": 0.4, "pValue": 0.61,
                                "verdict": "no significant difference"}]}
    page = render([first, second], fairness)
    assert "## Latest full run" in page and "| Cases passing every automated check | 2/2 (100%) |" in page
    assert page.count("xychart-beta") == 3
    assert "| 2026-11-27 | `abcdef1` | all ×2 | gpt-6-luna | 2/2 | 96% | 9.0s | 30.0s | $0.00100 | 0.0 |" in page
    assert "| Perceived gender (name) | 0.40 points | 0.610 | no significant difference |" in page
