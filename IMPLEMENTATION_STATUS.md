# Readiness fixes and interface update — 2026-11-06

Implemented in the working tree. Existing unrelated/uncommitted work was preserved; no commit,
production deployment, cloud-policy update, or live-data migration was performed.

## High and medium items

| Area | Implemented | Remaining external validation |
|---|---|---|
| Training pipeline | Malformed schema short-circuit, complete-pair deduplication, resume-grouped held-out split, recorded retrieval context, evaluation failure exit codes | Review dataset quality and near-duplicate candidate families |
| Reproducibility | Required immutable model/toolchain commits, training package-lock verification, artifact hashes/manifests, resumable quantization build | Produce a GPU-validated training lock and prove converter/runtime compatibility |
| Queue reliability | Atomic two-job capacity leases, bounded transient retry, idempotent completion, no re-inference after saved-result retry, terminal malformed-output failure | Measure production throughput and failure recovery |
| Retrieval | Non-overlapping aliases, capitalized Go and contextual lowercase Go, conservative negation, hard chunk ceilings, transactional complete corpus replacement | Semantic extraction remains heuristic; evaluate real documents |
| Verification | CI, single verification command, real Redis/BullMQ processing, optional actual PostgreSQL persistence, transactional ingestion regression, desktop/mobile browser tests, clean-container smoke | Real GGUF container and full deployed pipeline |
| Operations | Dependency readiness, worker heartbeat and structured timing/queue/resource logs, deployment/rollback runbook | Connect host alerts; validate actual cloud secrets, TLS, IAM, backups, and topology |
| Privacy | Existing capability/TTL/deletion protections regression-tested; legacy migration applied only in disposable test DB | Live legacy purge/migration and provider backup retention, if applicable |
| UX/recovery | Retry polling without resubmission, abortable delays, clearer errors/limits, document/result binding, refresh/access disclosure | Wider device and assistive-technology acceptance |
| Setup/release | Root environment launchers, Python 3.12 documentation, repository-root Docker context, no source staging, corrected shallow container paths | Review and commit intended changes, then clean-clone rollout |

## Interface and motion

Rebuilt the page with ivory, deep green-black, and citron, custom overlapping-lens artwork,
responsive document panels, an alignment score visualization, and distinct strengths/gaps/question
sections. Motion follows Emil Kowalski's Animate skill, read directly from its upstream repository:
https://github.com/emilkowalski/skills/blob/main/skills/animate/SKILL.md

Button feedback, staged entrances, and processing-only lens motion share one timing system.
Reduced-motion mode removes rotation/translation, and mouse hover styling is pointer-gated.
See DESIGN.md for the implementation's visual and motion rules.

## Verification performed

- API: 23 passing tests, including isolated Redis/BullMQ with actual PostgreSQL completion writes.
- Python: 78 passing tests with PostgreSQL ingestion rename/delete/rollback coverage.
- Browser: 8 passing desktop/mobile Chromium tests covering sample results, deletion, overload,
  recovery without resubmission, keyboard entry, responsive overflow, and reduced motion.
- API TypeScript and Next.js production builds pass.
- Both migrations apply to a newly created disposable pgvector database.
- Fresh Python 3.12 Docker image builds and passes authentication/real-stub inference smoke tests.
- Desktop/mobile empty and populated states were captured; desktop and mobile empty states and
  desktop results were visually inspected. No claim of exhaustive accessibility certification.
- Shell syntax checks and git diff whitespace checks pass.

Python verification used a fresh Python 3.12 environment via PYTHON; the preexisting project .venv
is Python 3.9 and was not overwritten. Follow README to create the supported local environment.
Container tests caught and fixed two import-time assumptions about repository directory depth.
The initial approval-service limit cleared on a later review; container checks subsequently ran.

## Release gates still open

The original blocker-level work remains: real GGUF artifact training/evaluation, practical document
context sizing, evidence-quality acceptance, real-model performance/cost measurements, and a full
staging rollout. The shipped CI smoke uses the disclosed stub and cannot establish those outcomes.
Cloud monitoring/backup policies and live legacy-data cleanup cannot be proven from repository tests.


## React frontend migration — 2026-11-07

Replaced Next.js with React 19 + Vite 8. Client components and helpers are plain JavaScript/JSX
under apps/web/src, with an explicit React root and HTML entry. Removed Next.js dependencies,
App Router files, Next-specific TypeScript configuration, and the generated Next agent rules.
Shared contracts and the backend remain TypeScript.

The existing visual design, animations, polling, deletion, privacy behavior, and responsive layout
are retained. VITE_API_URL is now the public configuration variable; the former NEXT_PUBLIC_API_URL
is accepted as a compatibility fallback. Vite reads the root environment directly. Production
output is apps/web/dist, including CSP metadata and a generated _headers file for static hosts.

Validation: Vite production build and API TypeScript build pass; all 10 desktop/mobile browser
tests pass, including metadata/security-header checks. Public-origin validation rejects insecure
remote HTTP origins, credentials, and URL paths. Desktop screenshots were reviewed. No Next.js
dependency remains in the frontend dependency tree. Live-model/deployment release gates above
remain unchanged.


## Completion preparation — 2026-11-17

- **Model context and input caps aligned.** One setting (`apps/ml-service/inference/limits.py`: 6,144
  tokens, 800 reserved for output) now drives training, merge, evaluation and serving. Input caps
  dropped from 20,000 to 8,000 (resume) and 6,000 (job description) characters so a maximum-length
  request fits. A test keeps the Python and TypeScript caps identical.
- **Training runnable on Colab.** `apps/ml-service/training/hirelens_training.ipynb` runs train →
  adapter evaluation → merge → GGUF export → GGUF evaluation, saving artifacts to Google Drive.
  The merge uses Unsloth's `save_pretrained_merged`. The converter is pinned to llama.cpp
  `74d73dc8…`, the commit vendored by the runtime's `llama-cpp-python==0.3.2`.
- **Exported model evaluated directly.** `python -m training.evaluate --gguf hirelens-q4.gguf`
  evaluates the shipped file with the serving runtime, context and sampling settings.
- **Claude as a data-generation teacher.** `TEACHER_PROVIDER=anthropic` / `ANTHROPIC_API_KEY`, next to
  Gemini and OpenAI. Unknown providers now fail immediately instead of retrying.
- **Evaluation set expanded and asserted.** 24 cases (was 12): prompt injection in resume and JD,
  explicit negation, counterfactual pairs (name/pronouns, graduation year, career-break reason),
  mobile and security domains, and a near-cap resume. Score bounds, required gaps and
  counterfactual score spread now fail the run automatically.
- **Deployment layout.** `apps/api/Dockerfile` (API/worker/migrate targets), `deploy/` Compose with
  private Redis and Caddy TLS, and DEPLOYMENT.md. Inference timeouts are configurable
  (`INFERENCE_TIMEOUT_SECONDS`, `LAMBDA_TIMEOUT`).
- **Cleanup.** Removed the stray `mnt/` duplicate and the machine-specific `.codesight/` config.

Verified here: 23 API tests and 94 Python tests (1 PostgreSQL test skipped without
`TEST_DATABASE_URL`) pass; API and web production builds pass; the production-only dependency install
resolves the shared contract; the production Compose file validates. **Not** verified here (no GPU,
and Docker Hub and Hugging Face are unreachable from the environment used): container image builds,
the notebook on a GPU, Unsloth merge behaviour, and real-model quality or latency. Browser tests were
not re-run.

Release gates still open: train and evaluate the real model, measure CPU latency and memory at the
new context size, deploy to staging and complete the OPERATIONS.md checks.

## Hosted model backend — 2026-11-19

Decision: use a provider's model API instead of fine-tuning (training remains optional for a
self-hosted `gguf` backend).

- **`MODEL_BACKEND=hosted`** (`apps/ml-service/inference/hosted.py`). Same untrusted-document
  framing, retrieval and schema validation as before, plus explicit scoring and fairness guidance
  (`HOSTED_GUIDANCE` in `inference/prompt.py`). Anthropic (default, `claude-sonnet-5-5`) uses forced
  tool use with the shared JSON schema; OpenAI and Gemini use JSON mode with the schema in the prompt.
  Invalid answers and rate limits get one retry; auth/request errors fail immediately. Provider
  error bodies are discarded so they cannot carry document text into logs.
- Production accepts `hosted` or `gguf` in the ML service and the worker (`PRODUCTION_BACKENDS`),
  and still refuses `stub`. Startup and readiness check the configuration without calling the provider.
- **Lambda:** `Dockerfile.hosted` (no llama.cpp, compiler or model file); `deploy_aws.sh` defaults to
  `MODEL_BACKEND=hosted`, passes the provider settings and key, and checks that two provider attempts
  fit inside the Lambda timeout.
- **Privacy notice:** `VITE_INFERENCE_PROVIDER` at web build time tells users, before they submit,
  that documents are sent to that provider.
- **Evaluation:** `python -m eval.run_eval --direct` runs the 24 cases through the in-process
  analysis path (no API, worker or Redis); `--repeat N` flags score variation; `--save` writes results.

Verified here: 101 Python tests (1 PostgreSQL test skipped), 24 API tests and 10 browser tests pass;
both builds pass; deploy-script argument checks exercised. **Not** verified here: real provider calls
(no API key, and provider APIs are unreachable from this environment), the hosted Lambda image build,
and answer quality. Run the direct evaluation with a real key before deploying.

### Default provider: OpenAI GPT-6 Luna — 2026-11-19

Chosen from OpenAI's November 2026 price list for a ~4K-input, ~1K-output structured judgment task:
`gpt-6-luna` ($0.10 / $0.50 per million tokens), the GPT-6 efficiency tier for focused high-volume
work, with Structured Outputs and configurable reasoning; about $0.002 per analysis at medium effort.
`gpt-6.1-terra` ($1 / $5, mid tier) is the step up if evaluation shows Luna is not good enough;
the Sol tier ($2 / $10) is not needed for this task. The request follows reasoning-model rules:
`reasoning_effort` (default `medium`, configurable via `HOSTED_REASONING_EFFORT`), no `temperature`
unless effort is `none`, `max_completion_tokens` sized for hidden reasoning, strict `json_schema`
Structured Outputs (length/count limits enforced by our validator), `store: false`, and refusals
treated as invalid answers. Not verified against the live API from this environment.

## Single-VM deployment — 2026-11-20

The recommended layout is now one VM running the API, worker, ML service (`Dockerfile.server`,
uvicorn, hosted backend), Redis and Caddy, plus managed Postgres and a static web host; no AWS account
is needed. The worker reaches the ML service at `http://ml:8000` on the private Docker network;
production allows plain HTTP only for such single-label container names (`apps/api/src/ml-url.ts`).
The provider key is in `deploy/ml.env`, given only to the ML container. `deploy/update.sh` builds,
migrates and restarts on the VM. Lambda (step 2b) and a 1 GB VM (step 3b) remain documented
alternatives. Verified here: API tests, the ML server started with production settings (health 200,
unauthenticated /infer 401, missing provider key fails startup), Compose validation and shellcheck.
Not verified here: the image builds and a real VM run.
