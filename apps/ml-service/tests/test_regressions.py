import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from common import pair_fingerprint
from data_gen.curate import review
from inference.skills import extract_skills, jd_only_skills
from rag.chunking import chunk_markdown, MAX_CHARS
from training.evaluate import evaluate_generations
from training import prepare_dataset

FIXTURE = json.loads((Path(__file__).resolve().parents[3] / "packages/shared/fixtures/sample-analysis.json").read_text())

@pytest.mark.parametrize("broken", [{"fitScore": "bad"}, {**FIXTURE, "gaps": ["wrong"]}, {**FIXTURE, "interviewQuestions": [None]}])
def test_malformed_teacher_output_is_rejected_without_crash(broken):
    assert review({"resume": "Python", "jd": "Python", "output": broken})


def test_complete_pair_deduplication():
    prefix = "same opening " * 30
    assert pair_fingerprint(prefix + "Python", "JD") != pair_fingerprint(prefix + "Rust", "JD")
    assert pair_fingerprint(prefix, "Python") != pair_fingerprint(prefix, "Rust")
    assert pair_fingerprint("same  resume\n", "same JD") == pair_fingerprint("same resume", "same JD")


def test_skill_overlap_go_and_negation():
    assert extract_skills("React Native") == ["React Native"]
    assert extract_skills("React.js Docker Docker")[0] == "Docker"
    assert "Go" in extract_skills("We need a Go engineer")
    assert "Go" not in extract_skills("We go to work")
    assert "Kubernetes" in jd_only_skills("No Kubernetes experience; used Python", "Kubernetes required")
    assert "Python" in extract_skills("No Kubernetes experience; used Python")
    assert "Kubernetes" not in extract_skills("Kubernetes is not required")


def test_hard_chunk_limit_including_long_heading():
    chunks = chunk_markdown("# Doc\n## " + "heading" * 150 + "\n" + "x" * 5000, "test.md")
    assert all(len(chunk["content"]) <= MAX_CHARS for chunk in chunks)
    assert sum(chunk["content"].count("x") for chunk in chunks) == 5000


def test_evaluation_rejects_missing_outputs():
    with pytest.raises(ValueError):
        evaluate_generations([], [{"output": FIXTURE}])


def test_split_keeps_same_resume_out_of_training_and_saves_context(tmp_path, monkeypatch):
    rows = [{"resume": "one resume", "jd": "Python"}, {"resume": "one resume", "jd": "Rust"},
            {"resume": "second resume", "jd": "Python"}, {"resume": "third resume", "jd": "Go"}]
    rows = [{**row, "output": FIXTURE} for row in rows]
    clean = tmp_path / "clean.jsonl"; clean.write_text("\n".join(json.dumps(row) for row in rows))
    monkeypatch.setattr(prepare_dataset, "CLEAN", clean)
    monkeypatch.setattr(prepare_dataset, "TRAIN", tmp_path / "train.jsonl")
    monkeypatch.setattr(prepare_dataset, "HELDOUT", tmp_path / "heldout.jsonl")
    monkeypatch.setattr("sys.argv", ["prepare", "--heldout", "1", "--context", "none"])
    prepare_dataset.main()
    heldout = [json.loads(line) for line in (tmp_path / "heldout.jsonl").read_text().splitlines()]
    training = (tmp_path / "train.jsonl").read_text()
    assert heldout and all("chunks" in row for row in heldout)
    assert all(row["resume"] not in training for row in heldout)
