# Reproducible training and export

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

Choose a 40-character llama.cpp commit and validate the exported model with the exact
`llama-cpp-python` version in runtime requirements. The exporter rebuilds safely after interruption,
records the converter commit, package snapshot, and GGUF SHA-256. Retain the model, manifest,
training lock, and quantization lock in an artifact store. Do not commit model binaries.

The production Docker build context is the repository root:

```sh
docker build --platform linux/amd64 -f apps/ml-service/Dockerfile -t hirelens-ml .
```

Run the final GGUF through the deployed service and `python -m eval.run_eval`. Manual-case
expectations still require human review; command success only establishes its automated checks.
Re-evaluate whenever the prompt, retrieval corpus, runtime, or model changes. GPU training,
quantization, and real-model acceptance must be completed before release.
