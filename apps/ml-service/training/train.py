"""QLoRA fine-tune of Qwen2.5-3B-Instruct (Phase 4).

Runs on a free Colab T4. Kept as a .py file rather than living only in a notebook so it is
reviewable in the repo and in version control; see training/README.md for how to run it
in Colab.

Run: python -m training.train
"""

from __future__ import annotations

import argparse

BASE_MODEL = "unsloth/Qwen2.5-3B-Instruct-bnb-4bit"
MAX_SEQ_LENGTH = 2048
OUTPUT_DIR = "hirelens-qwen-lora"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/train.jsonl")
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--rank", type=int, default=16)
    args = parser.parse_args()

    import torch
    from datasets import Dataset
    from transformers import TrainingArguments
    from trl import SFTTrainer
    from unsloth import FastLanguageModel

    from common import read_jsonl

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=args.rank,
        # Attention projections plus the feed-forward network. Adapting the FFN too matters
        # here because the task is largely about changing output *format*, not just emphasis.
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0,
        use_gradient_checkpointing="unsloth",
        random_state=7,
    )

    dataset = Dataset.from_list(read_jsonl(args.data))

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        args=TrainingArguments(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            warmup_steps=10,
            num_train_epochs=args.epochs,
            learning_rate=2e-4,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=10,
            optim="adamw_8bit",
            seed=7,
            output_dir="outputs",
            report_to="none",
        ),
    )

    stats = trainer.train()
    print(f"final training loss: {stats.training_loss:.4f}")

    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"adapter saved to {OUTPUT_DIR}/")
    print("Next: run training/evaluate.py on the held-out set before trusting this.")


if __name__ == "__main__":
    main()
