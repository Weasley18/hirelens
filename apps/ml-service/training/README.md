# Reproducible training and export

**Optional.** HireLens runs without training by using `MODEL_BACKEND=hosted` (a provider's model
API). Train only if you want the self-hosted `gguf` backend, for example to keep candidate
documents off third-party servers.

**Quick path:** prepare the dataset on your machine (below), upload `data/train.jsonl` and
`data/heldout.jsonl` to `MyDrive/hirelens/data/`, then open
[`hirelens_training.ipynb`](hirelens_training.ipynb) in Google Colab with a T4 GPU and run all cells.
The notebook does steps 4–5 and the export/evaluation below, saving every artifact to Drive.

## Prepare the dataset (local, no GPU)

Set one teacher key in the root `.env` (`GEMINI_API_KEY`, `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`;
see `.env.example`), start the local databases, then from the repository root:

```sh
docker compose up -d && npm run db:migrate
npm run ml -- -m rag.ingest
npm run ml -- -m data_gen.make_pairs --count 400      # invent resume/JD pairs
npm run ml -- -m data_gen.generate                    # teacher labels each pair
npm run ml -- -m data_gen.curate --sample 300         # reject malformed/incoherent labels
npm run ml -- -m training.prepare_dataset --heldout 20
```

Each data step resumes where it stopped. Skim `data/dataset_rejected.jsonl` and a sample of
`data/dataset_clean.jsonl` before training: label quality is the main factor in model quality.

## Full procedure

Use a dedicated GPU environment, separate from the inference/test environments. Training scripts
require an explicit immutable base-model revision and a dependency lock. This repository does
not yet include a GPU-validated training lock or a proven llama.cpp/runtime combination.

1. Ingest the knowledge base with `npm run ml -- -m rag.ingest` from the repository root.
2. Generate and curate synthetic data. Deduplication uses the complete normalized resume/JD pair.
3. Run `python -m training.prepare_dataset --heldout 20` inside the ML service with DATABASE_URL
   configured. It retrieves context and saves that context with held-out records. The same normalized
   resume cannot appear in both training and evaluation. Manually group near-duplicate candidate
   variants before splitting; exact-text grouping does not detect every paraphrase.
4. In your selected GPU environment, install compatible `unsloth`, `trl`, `datasets`, `transformers`,
   and the application's Python dependencies, then capture `python -m pip freeze > training.lock`.
   Review and retain this lock with the run. Subsequent runs must recreate that exact environment.
5. Obtain the immutable Hugging Face commit for the selected base-model snapshot and run:

```sh
python -m training.train --model-revision "$MODEL_REVISION" --lock-file training.lock
python -m training.evaluate
```

Training verifies the installed packages against the lock, refuses oversize examples instead of
silently truncating them, and records dataset/prompt hashes, parameters, Python version, and model
revision alongside the adapter. Evaluation uses recorded held-out retrieval context and exits
nonzero below 95% schema validity or coherence. These are minimum mechanical gates, not proof
of hiring quality. Inspect evidence quality and adversarial/counterfactual cases separately.

```sh
python -m training.merge_and_export
LLAMA_CPP_REVISION="$TESTED_LLAMA_COMMIT" bash scripts/quantize.sh hirelens-merged
```

Use llama.cpp commit `74d73dc85cc2057446bf63cc37ff649ae7cebd80`, the one vendored by the
runtime's `llama-cpp-python==0.3.2`, so converter and runtime match; change both together. Validate the exported model with the exact
`llama-cpp-python` version in runtime requirements. The exporter rebuilds safely after interruption,
records the converter commit, package snapshot, and GGUF SHA-256. Retain the model, manifest,
training lock, and quantization lock in an artifact store. Do not commit model binaries.

The production Docker build context is the repository root:

```sh
docker build --platform linux/amd64 -f apps/ml-service/Dockerfile -t hirelens-ml .
```

Evaluate the exported file with the serving runtime and settings:
`python -m training.evaluate --gguf hirelens-q4.gguf` (needs `llama-cpp-python==0.3.2`).

The context size (6,144 tokens) is defined once in `inference/limits.py` and used by training,
merging, evaluation and serving. Changing it means retraining.

Run the final GGUF through the deployed service and `python -m eval.run_eval`. Manual-case
expectations still require human review; command success only establishes its automated checks.
Re-evaluate whenever the prompt, retrieval corpus, runtime, or model changes. GPU training,
quantization, and real-model acceptance must be completed before release.
