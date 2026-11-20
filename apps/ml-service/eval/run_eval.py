"""Run the hand-written edge cases through the deployed system (Phase 10.3).

This is not a statistical measure. It is the last thing between you and a recruiter finding
an embarrassing failure for you. Read the output yourself, fix what is wrong.

Cases with an "assert" block are also checked automatically: score bounds, gaps that must or
must not be listed, and counterfactual groups (pairs that differ only in non-job-relevant
details such as name, pronouns, age or the reason for a career break must score within a
tolerance of each other). With --repeat, every run is checked and groups compare average scores,
so run-to-run noise is not mistaken for bias.

Run against a local stack:   python -m eval.run_eval
Run against the deployed one: API_URL=https://your-api python -m eval.run_eval
Run the model directly, no API/worker/Redis (uses MODEL_BACKEND and its key from .env):
                              python -m eval.run_eval --direct --save data/eval-results.json
Add --repeat 3 to measure how much the score varies between runs of the same case.

Quality gate (CI runs this on pull requests that touch the prompt, model code or schema):
    python -m eval.run_eval --direct --cases ci --summary eval-summary.json --markdown eval-summary.md
Add --record to keep the run in eval/history/, which eval.dashboard turns into EVALUATION.md.
Besides the checks above, the gate fails when fewer than MIN_SUPPORT_RATE of the claims the
model made quoted the documents (unsupported claims are removed before anyone sees them, but
a falling rate means the prompt or model got worse).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from common import validate_analysis
from data_gen.curate import consistency_issues, grounding_issues

PAIRS = Path(__file__).parent / "manual_pairs.json"
HISTORY = Path(__file__).parent / "history"
# A quick, representative subset for pull requests: a strong and a non-match, prompt injection,
# a negated skill, an off-domain JD and one counterfactual pair. About a dozen model calls.
CI_CASES = ("clean-match", "total-mismatch", "adjacent-stack", "injection-score-override", "negated-skill",
            "domain-security", "counterfactual-name-a", "counterfactual-name-b")
MIN_SUPPORT_RATE = 0.9
API_URL = os.environ.get("API_URL", "http://localhost:3000")
POLL_SECONDS = 1.5
MAX_POLLS = 60


def analyse(client: httpx.Client, resume: str, jd: str) -> dict:
    """The envelope ({result, metadata}) the deployed API returns. Usage is not exposed there."""
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
                return {"result": polled["result"], "metadata": polled.get("metadata", {})}
            if polled["status"] == "failed":
                raise RuntimeError("job failed")
        raise TimeoutError("analysis did not finish in time")
    finally:
        client.delete(f"{API_URL}/analyze/{job_id}", headers=headers)


def analyse_direct(resume: str, jd: str) -> dict:
    """The same retrieval, generation and validation as /infer, called in-process, with usage."""
    from inference.server import analyze_documents

    return analyze_documents(resume.strip(), jd.strip())


MAX_SCORE_SPREAD = 10


def _mentions(term: str, text: str) -> bool:
    """Term at the start of a word: "go" matches "Go" and "Golang" but not "algorithms"."""
    return re.search(rf"\b{re.escape(term.lower())}", text) is not None


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
        if not any(_mentions(skill, gap) for gap in gaps):
            issues.append(f"expected a gap for {skill!r}")
    for term in rules.get("must_not_gap", []):
        listed = [gap for gap in gaps if _mentions(term, gap)]
        if listed:
            issues.append(f"gap {listed[0]!r} should not be treated as a skills gap")
    return issues


def group_issues(cases: list[dict], scores: dict[str, list[int] | int]) -> list[str]:
    """Counterfactual pairs must score alike, on average across repeats.

    Missing results are reported, not skipped.
    """
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
        means = {m["id"]: _mean(scores[m["id"]]) for m in members}
        spread = max(means.values()) - min(means.values())
        tolerance = min(m["assert"].get("tolerance", 5) for m in members)
        if spread > tolerance:
            detail = ", ".join(f"{case_id}={mean:.1f}" for case_id, mean in means.items())
            issues.append(f"group {group!r} average spread {spread:.1f} > {tolerance}: {detail}")
    return issues


def group_spreads(cases: list[dict], scores: dict[str, list[int] | int]) -> dict[str, float]:
    """Largest difference between average scores within each counterfactual group."""
    groups: dict[str, list[float]] = {}
    for case in cases:
        group = case.get("assert", {}).get("group")
        if group and case["id"] in scores:
            groups.setdefault(group, []).append(_mean(scores[case["id"]]))
    return {g: round(max(m) - min(m), 2) for g, m in sorted(groups.items()) if len(m) > 1}


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, -(-len(ordered) * p // 100) - 1))]


def _commit() -> str | None:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"][:12]
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True,
                              check=True, cwd=Path(__file__).parent).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def summarize(records: list[dict], cases: list[dict], *, mode: str, repeat: int, subset: str,
              backend: str | None = None) -> dict:
    """One run's quality, cost and latency, as tracked in eval/history and EVALUATION.md.

    records: one per case, {"id", "scores", "problems", "error", "envelopes", "seconds"}.
    """
    runs = [e for r in records for e in r.get("envelopes", [])]
    usage = [e["telemetry"] for e in runs if isinstance(e.get("telemetry"), dict)]
    checked = sum(e.get("metadata", {}).get("citations", {}).get("checked", 0) for e in runs)
    removed = sum(e.get("metadata", {}).get("citations", {}).get("removed", 0) for e in runs)
    costs = [u["costUsd"] for u in usage if u.get("costUsd") is not None]
    seconds = [t for r in records for t in r.get("seconds", [])]
    scores = {r["id"]: r["scores"] for r in records if r.get("scores")}
    spreads = [max(v) - min(v) for v in scores.values() if len(v) > 1]
    fairness = group_issues(cases, scores)
    passed = [r["id"] for r in records if not r.get("problems") and not r.get("error")]
    support = round((checked - removed) / checked, 4) if checked else None
    models = sorted({u.get("model") for u in usage if u.get("model")})
    return {
        "version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": _commit(),
        "mode": mode,
        "subset": subset,
        "repeat": repeat,
        "backend": backend or next((e.get("metadata", {}).get("backend") for e in runs), None),
        "model": ", ".join(models) or os.environ.get("HOSTED_MODEL") or None,
        "cases": len(cases),
        "passed": len(passed),
        "passRate": round(len(passed) / len(cases), 4) if cases else None,
        "analyses": len(runs),
        "errors": sum(1 for r in records if r.get("error")),
        "flagged": [{"id": r["id"], "problems": (r.get("problems") or [r.get("error")])[:3]}
                    for r in records if r.get("problems") or r.get("error")],
        "fairness": {"spreads": group_spreads(cases, scores), "failures": fairness},
        "scoreSpread": {"mean": round(statistics.fmean(spreads), 2), "max": max(spreads)} if spreads else None,
        "citations": {"checked": checked, "removed": removed, "supportRate": support},
        "latencySeconds": {"p50": _percentile(seconds, 50), "p95": _percentile(seconds, 95)},
        "costUsd": {"total": round(sum(costs), 6), "perAnalysis": round(statistics.fmean(costs), 6)} if costs else None,
        "tokens": {"inputPerAnalysis": round(statistics.fmean(u["inputTokens"] for u in usage)),
                   "outputPerAnalysis": round(statistics.fmean(u["outputTokens"] for u in usage))} if usage else None,
    }


def gate_failures(summary: dict) -> list[str]:
    """Why this run should fail CI, if it should."""
    reasons = []
    if summary["errors"]:
        reasons.append(f"{summary['errors']} case(s) could not be analysed")
    if summary["passed"] < summary["cases"]:
        reasons.append(f"{summary['cases'] - summary['passed']} case(s) failed their checks")
    reasons += summary["fairness"]["failures"]
    rate = summary["citations"]["supportRate"]
    if rate is not None and rate < MIN_SUPPORT_RATE:
        reasons.append(f"only {rate:.0%} of claims quoted the documents (minimum {MIN_SUPPORT_RATE:.0%})")
    return reasons


def _fmt(value, kind: str) -> str:
    if value is None:
        return "—"
    return {"pct": f"{value:.0%}", "usd": f"${value:.4f}", "s": f"{value:.1f}s", "pts": f"{value:.1f} pts"}.get(kind, str(value))


def markdown(summary: dict, baseline: dict | None = None) -> str:
    """A short report for the CI job summary and the pull request comment."""
    failures = gate_failures(summary)
    lines = [f"### HireLens evaluation: {'passed' if not failures else 'failed'}", "",
             f"`{summary['subset']}` cases · {summary['mode']} · backend `{summary['backend']}` · model "
             f"`{summary['model']}` · commit `{summary['commit']}`", ""]

    def row(name, kind, path):
        value = path(summary)
        before = path(baseline) if baseline else None
        lines.append(f"| {name} | {_fmt(value, kind)} | {_fmt(before, kind) if baseline else '—'} |")

    lines += ["| Metric | This run | Last recorded |", "|---|---|---|"]
    row("Cases passing", "pct", lambda s: s.get("passRate"))
    row("Claims backed by a quote", "pct", lambda s: (s.get("citations") or {}).get("supportRate"))
    row("Latency p50", "s", lambda s: (s.get("latencySeconds") or {}).get("p50"))
    row("Latency p95", "s", lambda s: (s.get("latencySeconds") or {}).get("p95"))
    row("Cost per analysis", "usd", lambda s: (s.get("costUsd") or {}).get("perAnalysis"))
    row("Largest counterfactual gap", "pts",
        lambda s: max((s.get("fairness") or {}).get("spreads", {}).values(), default=None))
    if failures:
        lines += ["", "**Gate failures**", *[f"- {reason}" for reason in failures]]
    if summary["flagged"]:
        lines += ["", "<details><summary>Flagged cases</summary>", ""]
        for case in summary["flagged"]:
            lines.append(f"- `{case['id']}`: " + "; ".join(str(p) for p in case["problems"]))
        lines += ["", "</details>"]
    return "\n".join(lines) + "\n"


def latest_recorded() -> dict | None:
    runs = sorted(HISTORY.glob("*.json"))
    return json.loads(runs[-1].read_text()) if runs else None


def record(summary: dict) -> Path:
    HISTORY.mkdir(exist_ok=True)
    stamp = summary["timestamp"].replace(":", "").replace("-", "")[:15]
    path = HISTORY / f"{stamp}-{summary['subset']}-{summary['commit'] or 'local'}.json"
    path.write_text(json.dumps(summary, indent=2) + "\n")
    return path


def _mean(value: list[int] | int) -> float:
    values = value if isinstance(value, list) else [value]
    return sum(values) / len(values)


def _scores(values: list[int]) -> str:
    return f"{values[0]:>3}" if len(values) == 1 else f"{min(values):>3}-{max(values):<3}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="run a single case by id")
    parser.add_argument("--cases", help='comma-separated case ids, or "ci" for the pull-request subset')
    parser.add_argument("--verbose", action="store_true", help="print the full analysis")
    parser.add_argument("--direct", action="store_true",
                        help="call the inference code in-process instead of the HTTP API")
    parser.add_argument("--repeat", type=int, default=1,
                        help="run each case N times and flag score spread above %d" % MAX_SCORE_SPREAD)
    parser.add_argument("--save", help="write every result to this JSON file (synthetic cases only)")
    parser.add_argument("--summary", help="write the run's metrics (no documents) to this JSON file")
    parser.add_argument("--markdown", help="write a short report to this Markdown file")
    parser.add_argument("--record", action="store_true", help="keep the summary in eval/history/")
    args = parser.parse_args(argv)
    if not 1 <= args.repeat <= 5:
        raise SystemExit("--repeat must be between 1 and 5")
    backend = None
    if args.direct:
        from inference.llm import BACKEND as backend
        print(f"Direct mode, backend: {backend}\n")

    cases = json.loads(PAIRS.read_text())
    subset = "all"
    if args.only:
        cases, subset = [c for c in cases if c["id"] == args.only], args.only
    elif args.cases:
        wanted = CI_CASES if args.cases == "ci" else tuple(i.strip() for i in args.cases.split(",") if i.strip())
        unknown = set(wanted) - {c["id"] for c in cases}
        if unknown:
            raise SystemExit(f"Unknown case(s): {', '.join(sorted(unknown))}")
        cases, subset = [c for c in cases if c["id"] in wanted], "ci" if args.cases == "ci" else "custom"
    if not cases:
        raise SystemExit("No evaluation cases selected")

    records: list[dict] = []
    saved: list[dict] = []
    with httpx.Client(timeout=120) as client:
        for case in cases:
            envelopes: list[dict] = []
            seconds: list[float] = []
            entry = {"id": case["id"], "envelopes": envelopes, "seconds": seconds, "scores": [], "problems": []}
            records.append(entry)
            try:
                for _ in range(args.repeat):
                    if not args.direct:
                        time.sleep(13)  # Respect the public five-submissions/minute budget.
                    started = time.monotonic()
                    envelopes.append(analyse_direct(case["resume"], case["jd"]) if args.direct
                                     else analyse(client, case["resume"], case["jd"]))
                    seconds.append(round(time.monotonic() - started, 2))
            except Exception as exc:  # noqa: BLE001
                entry["error"] = f"{type(exc).__name__}: {exc}"
                print(f"FAIL  {case['id']:<24} {entry['error']}")
                continue
            runs = [e["result"] for e in envelopes]
            result = runs[0]
            run_scores = entry["scores"] = [r["fitScore"] for r in runs]
            saved.append({"id": case["id"], "scores": run_scores, "results": runs})

            problems: list[str] = entry["problems"]
            for number, run in enumerate(runs, start=1):
                prefix = f"run {number}: " if len(runs) > 1 else ""
                for problem in (
                    validate_analysis(run)
                    + consistency_issues(run)
                    + grounding_issues({"jd": case["jd"], "output": run})
                    + expectation_issues(case, run)
                ):
                    problems.append(prefix + problem)
            if max(run_scores) - min(run_scores) > MAX_SCORE_SPREAD:
                problems.append(f"score varied {min(run_scores)}-{max(run_scores)} across {len(runs)} runs")
            elapsed = statistics.fmean(seconds)

            if problems:
                print(f"FLAG  {case['id']:<24} score {_scores(run_scores)}  {elapsed:.0f}s")
                for problem in problems[:3]:
                    print(f"        {problem}")
            else:
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
    summary = summarize(records, cases, mode="direct" if args.direct else "api", repeat=args.repeat,
                        subset=subset, backend=backend)
    for problem in summary["fairness"]["failures"]:
        print(f"FLAG  {problem}")
    citations = summary["citations"]
    if citations["checked"]:
        print(f"Claims backed by a quote: {citations['supportRate']:.0%} "
              f"({citations['removed']} of {citations['checked']} removed)")
    if summary["costUsd"]:
        print(f"Cost: ${summary['costUsd']['total']:.4f} in total, ${summary['costUsd']['perAnalysis']:.5f} per analysis")
    if args.markdown:
        Path(args.markdown).write_text(markdown(summary, latest_recorded()))
    if args.summary:
        Path(args.summary).write_text(json.dumps(summary, indent=2) + "\n")
    if args.record:
        print(f"Recorded in {record(summary)}")
    print(f"{summary['passed']}/{len(cases)} cases passed the automated checks"
          + (f"; {len(summary['fairness']['failures'])} counterfactual group(s) failed."
             if summary["fairness"]["failures"] else "."))
    print("Now read the verdicts above against the 'expected' lines yourself — that is the")
    print("part no checker does for you, and it is where the embarrassing failures show up.")
    if gate_failures(summary):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
