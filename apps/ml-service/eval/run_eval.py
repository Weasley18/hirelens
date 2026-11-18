"""Run the hand-written edge cases through the deployed system (Phase 10.3).

This is not a statistical measure. It is the last thing between you and a recruiter finding
an embarrassing failure for you. Read the output yourself, fix what is wrong.

Cases with an "assert" block are also checked automatically: score bounds, required gaps,
and counterfactual groups (pairs that differ only in non-job-relevant details such as name,
pronouns, age or the reason for a career break must score within a tolerance of each other).

Run against a local stack:   python -m eval.run_eval
Run against the deployed one: API_URL=https://your-api python -m eval.run_eval
Run the model directly, no API/worker/Redis (uses MODEL_BACKEND and its key from .env):
                              python -m eval.run_eval --direct --save data/eval-results.json
Add --repeat 3 to measure how much the score varies between runs of the same case.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import httpx

from common import validate_analysis
from data_gen.curate import consistency_issues, grounding_issues

PAIRS = Path(__file__).parent / "manual_pairs.json"
API_URL = os.environ.get("API_URL", "http://localhost:3000")
POLL_SECONDS = 1.5
MAX_POLLS = 60


def analyse(client: httpx.Client, resume: str, jd: str) -> dict:
    submitted = client.post(f"{API_URL}/analyze", json={"resume": resume, "jd": jd})
    submitted.raise_for_status()
    handle = submitted.json()
    job_id = handle["jobId"]
    headers = {"Authorization": "Bearer " + handle["accessToken"]}
    try:
        for _ in range(MAX_POLLS):
            time.sleep(POLL_SECONDS)
            response = client.get(f"{API_URL}/analyze/{job_id}", headers=headers)
            if response.status_code == 429:
                time.sleep(60)
                continue
            response.raise_for_status()
            polled = response.json()
            if polled["status"] == "done":
                return polled["result"]
            if polled["status"] == "failed":
                raise RuntimeError("job failed")
        raise TimeoutError("analysis did not finish in time")
    finally:
        client.delete(f"{API_URL}/analyze/{job_id}", headers=headers)


def analyse_direct(resume: str, jd: str) -> dict:
    """The same retrieval, generation and validation as /infer, called in-process."""
    from inference.server import analyze_documents

    return analyze_documents(resume.strip(), jd.strip())["result"]


MAX_SCORE_SPREAD = 10


def expectation_issues(case: dict, result: dict) -> list[str]:
    """Checks for one case's "assert" block. Counterfactual groups are checked in group_issues."""
    rules = case.get("assert", {})
    score = result.get("fitScore")
    gaps = [g.get("skill", "").lower() for g in result.get("gaps", []) or []]
    issues: list[str] = []
    if "min_score" in rules and isinstance(score, int) and score < rules["min_score"]:
        issues.append(f"score {score} below expected minimum {rules['min_score']}")
    if "max_score" in rules and isinstance(score, int) and score > rules["max_score"]:
        issues.append(f"score {score} above expected maximum {rules['max_score']}")
    if "min_gaps" in rules and len(gaps) < rules["min_gaps"]:
        issues.append(f"{len(gaps)} gaps listed; expected at least {rules['min_gaps']}")
    for skill in rules.get("must_gap", []):
        if not any(skill.lower() in gap for gap in gaps):
            issues.append(f"expected a gap for {skill!r}")
    return issues


def group_issues(cases: list[dict], scores: dict[str, int]) -> list[str]:
    """Counterfactual pairs must score alike. Missing results are reported, not skipped."""
    groups: dict[str, list[dict]] = {}
    for case in cases:
        group = case.get("assert", {}).get("group")
        if group:
            groups.setdefault(group, []).append(case)
    issues: list[str] = []
    for group, members in sorted(groups.items()):
        missing = [m["id"] for m in members if m["id"] not in scores]
        if missing:
            issues.append(f"group {group!r}: no result for {', '.join(missing)}")
            continue
        values = [scores[m["id"]] for m in members]
        tolerance = min(m["assert"].get("tolerance", 5) for m in members)
        if max(values) - min(values) > tolerance:
            detail = ", ".join(f"{m['id']}={scores[m['id']]}" for m in members)
            issues.append(f"group {group!r} spread {max(values) - min(values)} > {tolerance}: {detail}")
    return issues


def _scores(values: list[int]) -> str:
    return f"{values[0]:>3}" if len(values) == 1 else f"{min(values):>3}-{max(values):<3}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="run a single case by id")
    parser.add_argument("--verbose", action="store_true", help="print the full analysis")
    parser.add_argument("--direct", action="store_true",
                        help="call the inference code in-process instead of the HTTP API")
    parser.add_argument("--repeat", type=int, default=1,
                        help="run each case N times and flag score spread above %d" % MAX_SCORE_SPREAD)
    parser.add_argument("--save", help="write every result to this JSON file (synthetic cases only)")
    args = parser.parse_args(argv)
    if not 1 <= args.repeat <= 5:
        raise SystemExit("--repeat must be between 1 and 5")
    if args.direct:
        from inference.llm import BACKEND
        print(f"Direct mode, backend: {BACKEND}\n")

    cases = json.loads(PAIRS.read_text())
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]
    scores: dict[str, int] = {}

    if not cases:
        raise SystemExit("No evaluation cases selected")
    passed = 0
    saved: list[dict] = []
    with httpx.Client(timeout=120) as client:
        for case in cases:
            started = time.monotonic()
            runs: list[dict] = []
            try:
                for _ in range(args.repeat):
                    if args.direct:
                        runs.append(analyse_direct(case["resume"], case["jd"]))
                    else:
                        time.sleep(13)  # Respect the public five-submissions/minute budget.
                        runs.append(analyse(client, case["resume"], case["jd"]))
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL  {case['id']:<24} {type(exc).__name__}: {exc}")
                continue
            result = runs[0]
            run_scores = [r["fitScore"] for r in runs]
            saved.append({"id": case["id"], "scores": run_scores, "results": runs})

            problems = (
                validate_analysis(result)
                + consistency_issues(result)
                + grounding_issues({"jd": case["jd"], "output": result})
                + expectation_issues(case, result)
            )
            if max(run_scores) - min(run_scores) > MAX_SCORE_SPREAD:
                problems.append(f"score varied {min(run_scores)}-{max(run_scores)} across {len(runs)} runs")
            scores[case["id"]] = result["fitScore"]
            elapsed = (time.monotonic() - started) / len(runs)

            if problems:
                print(f"FLAG  {case['id']:<24} score {_scores(run_scores)}  {elapsed:.0f}s")
                for problem in problems[:3]:
                    print(f"        {problem}")
            else:
                passed += 1
                print(f"ok    {case['id']:<24} score {_scores(run_scores)}  {elapsed:.0f}s")

            print(f"        expected: {case['expect']}")
            print(f"        verdict:  {result.get('verdict', '')}")

            if args.verbose:
                print(json.dumps(result, indent=2))
            print()

    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(saved, indent=2))
        print(f"Results written to {args.save}")
    fairness = group_issues(cases, scores)
    for problem in fairness:
        print(f"FLAG  {problem}")
    print(f"{passed}/{len(cases)} cases passed the automated checks"
          + (f"; {len(fairness)} counterfactual group(s) failed." if fairness else "."))
    print("Now read the verdicts above against the 'expected' lines yourself — that is the")
    print("part no checker does for you, and it is where the embarrassing failures show up.")
    if passed != len(cases) or fairness:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
