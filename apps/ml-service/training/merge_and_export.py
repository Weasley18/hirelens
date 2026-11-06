"""Merge the LoRA adapter into the base weights (Phase 5.2).

The adapter alone is not a model — it is a set of adjustments that only mean anything
alongside the frozen base weights. Merging produces one standalone set of weights that
llama.cpp's converter can read.

Run in Colab (needs the GPU and the base model): python -m training.merge_and_export
"""

from __future__ import annotations

ADAPTER_DIR = "hirelens-qwen-lora"
MERGED_DIR = "hirelens-merged"


def main() -> None:
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=ADAPTER_DIR,
        max_seq_length=2048,
        load_in_4bit=False,  # merging into 4-bit weights loses most of the point
    )

    model = model.merge_and_unload()
    model.save_pretrained(MERGED_DIR, safe_serialization=True)
    tokenizer.save_pretrained(MERGED_DIR)

    print(f"merged model written to {MERGED_DIR}/")
    print("Next: scripts/quantize.sh converts this to GGUF and quantizes it.")


if __name__ == "__main__":
    main()
