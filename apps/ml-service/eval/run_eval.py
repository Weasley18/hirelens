"""Run the hand-written edge cases through the deployed system (Phase 10.3).

This is not a statistical measure. It is the last thing between you and a recruiter finding
an embarrassing failure for you. Twelve cases, read the output yourself, fix what is wrong.

Run against a local stack:   python -m eval.run_eval
Run against the deployed one: API_URL=https://your-api python -m eval.run_eval
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="run a single case by id")
    parser.add_argument("--verbose", action="store_true", help="print the full analysis")
    args = parser.parse_args()

    cases = json.loads(PAIRS.read_text())
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]

    passed = 0
    with httpx.Client(timeout=120) as client:
        for case in cases:
            time.sleep(13)  # Respect the public five-submissions/minute budget.
            started = time.monotonic()
            try:
                result = analyse(client, case["resume"], case["jd"])
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL  {case['id']:<24} {exc}")
                continue

            problems = (
                validate_analysis(result)
                + consistency_issues(result)
                + grounding_issues({"jd": case["jd"], "output": result})
            )
            elapsed = time.monotonic() - started

            if problems:
                print(f"FLAG  {case['id']:<24} score {result['fitScore']:>3}  {elapsed:.0f}s")
                for problem in problems[:3]:
                    print(f"        {problem}")
            else:
                passed += 1
                print(f"ok    {case['id']:<24} score {result['fitScore']:>3}  {elapsed:.0f}s")

            print(f"        expected: {case['expect']}")
            print(f"        verdict:  {result.get('verdict', '')}")

            if args.verbose:
                print(json.dumps(result, indent=2))
            print()

    print(f"{passed}/{len(cases)} cases passed the automated checks.")
    print("Now read the verdicts above against the 'expected' lines yourself — that is the")
    print("part no checker does for you, and it is where the embarrassing failures show up.")


if __name__ == "__main__":
    main()
