"""Did the fine-tune actually work? (Phase 4.8)

Training loss going down proves the model memorised something. It does not prove the model
produces valid JSON on a resume it has never seen, which is the only thing this system needs
from it. This runs the held-out examples — never seen during training — and reports the
numbers that decide whether to move on to Phase 5 or go back and fix the dataset.

Run in Colab after training: python -m training.evaluate
"""

from __future__ import annotations

from typing import Any, Callable

from common import extract_json, validate_analysis
from data_gen.curate import consistency_issues


def evaluate_generations(raw_outputs: list[str], references: list[dict]) -> dict[str, Any]:
    """Build the report. Pure, so the report logic is testable without a GPU.

    json_valid   — did it produce parseable JSON at all
    schema_valid — did that JSON have the right fields, types and enums
    coherent     — did it avoid contradicting itself (score vs gaps)
    score_mae    — mean absolute difference from the teacher's score, in points
    """
    total = len(raw_outputs)
    json_valid = 0
    schema_valid = 0
    coherent = 0
    score_errors: list[float] = []
    failures: list[dict[str, Any]] = []

    for raw, reference in zip(raw_outputs, references):
        try:
            parsed = extract_json(raw)
        except ValueError as exc:
            failures.append({"reason": f"unparseable: {exc}", "raw": raw[:300]})
            continue

        json_valid += 1

        issues = validate_analysis(parsed)
        if issues:
            failures.append({"reason": f"schema: {issues[0]}", "raw": raw[:300]})
            continue

        schema_valid += 1

        if not consistency_issues(parsed):
            coherent += 1

        expected = reference.get("output", {}).get("fitScore")
        if isinstance(expected, int):
            score_errors.append(abs(parsed["fitScore"] - expected))

    return {
        "total": total,
        "json_valid_rate": json_valid / total if total else 0.0,
        "schema_valid_rate": schema_valid / total if total else 0.0,
        "coherent_rate": coherent / total if total else 0.0,
        "score_mae": sum(score_errors) / len(score_errors) if score_errors else None,
        "failures": failures[:5],
    }


def print_report(report: dict[str, Any]) -> None:
    print(f"held-out examples: {report['total']}")
    print(f"  parseable JSON:  {report['json_valid_rate']:.0%}")
    print(f"  matches schema:  {report['schema_valid_rate']:.0%}")
    print(f"  self-consistent: {report['coherent_rate']:.0%}")
    if report["score_mae"] is not None:
        print(f"  score MAE vs teacher: {report['score_mae']:.1f} points")

    if report["failures"]:
        print("\nfirst failures:")
        for failure in report["failures"]:
            print(f"  - {failure['reason']}\n    {failure['raw'][:160]}")

    print("\nRule of thumb before moving to Phase 5: schema_valid_rate above 0.95.")
    print("Below that, the fix is almost always the dataset, not more epochs.")


def generate_with_unsloth(model, tokenizer, prompts: list[str]) -> list[str]:
    """Colab-side helper: run the fine-tuned model over the held-out prompts."""
    from unsloth import FastLanguageModel

    FastLanguageModel.for_inference(model)
    outputs: list[str] = []

    for prompt in prompts:
        inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
        generated = model.generate(**inputs, max_new_tokens=800, temperature=0.2, do_sample=False)
        text = tokenizer.decode(generated[0], skip_special_tokens=True)
        outputs.append(text[len(tokenizer.decode(inputs["input_ids"][0], skip_special_tokens=True)):])

    return outputs


def main(generate: Callable[[list[str]], list[str]] | None = None) -> None:
    from pathlib import Path

    from common import read_jsonl
    from inference.prompt import build_chat_prompt

    references = read_jsonl(Path("data/heldout.jsonl"))
    prompts = [build_chat_prompt(r["resume"], r["jd"]) for r in references]

    if generate is None:
        from unsloth import FastLanguageModel

        model, tokenizer = FastLanguageModel.from_pretrained("hirelens-qwen-lora", max_seq_length=2048)
        raw_outputs = generate_with_unsloth(model, tokenizer, prompts)
    else:
        raw_outputs = generate(prompts)

    print_report(evaluate_generations(raw_outputs, references))


if __name__ == "__main__":
    main()
