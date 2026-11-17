"""Merge the LoRA adapter into the base weights (Phase 5.2).

The adapter alone is not a model — it is a set of adjustments that only mean anything
alongside the frozen base weights. Merging produces one standalone set of weights that
llama.cpp's converter can read.

Run in Colab (needs the GPU and the base model): python -m training.merge_and_export
"""

from __future__ import annotations

from inference.limits import CONTEXT_TOKENS

ADAPTER_DIR = "hirelens-qwen-lora"
MERGED_DIR = "hirelens-merged"


def main() -> None:
    from unsloth import FastLanguageModel
    from pathlib import Path
    import shutil
    if not Path(ADAPTER_DIR, "training-manifest.json").exists():
        raise ValueError("Adapter lacks training provenance; regenerate it with training.train")

    # Unsloth's documented merge path: load the adapter as trained (on the 4-bit base) and let
    # save_pretrained_merged fetch the 16-bit base weights to merge into. A hand-rolled
    # merge_and_unload onto 4-bit weights would bake quantization error into the export.
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=ADAPTER_DIR,
        max_seq_length=CONTEXT_TOKENS,
        load_in_4bit=True,
    )
    model.save_pretrained_merged(MERGED_DIR, tokenizer, save_method="merged_16bit")
    for name in ("training-manifest.json", "requirements.lock"):
        shutil.copyfile(Path(ADAPTER_DIR, name), Path(MERGED_DIR, name))

    print(f"merged model written to {MERGED_DIR}/")
    print("Next: scripts/quantize.sh converts this to GGUF and quantizes it.")


if __name__ == "__main__":
    main()
