# HireLens

Compare a pasted resume with a job description to get supported strengths, gaps to explore,
and interview questions. HireLens is an anonymous assessment workspace: results are temporary,
and every assessment needs human review.

The application includes a React (JavaScript/JSX + Vite) frontend, Fastify API, Redis/BullMQ worker, PostgreSQL/pgvector
knowledge base, and Python inference service. The development backend is a clearly labeled,
deterministic **stub**. Real inference requires a separately trained and evaluated GGUF artifact.
Production refuses the stub. Model quality, cost, and cold-start latency must be measured on the
target deployment; no zero-cost or latency guarantee is made.

## Local setup

Requirements: Node >=22.19, Python **3.12**, Docker, and `redis-server` for API tests.
Run these commands from the repository root:

```sh
cp .env.example .env
# Set ML_SERVICE_TOKEN in .env to a random secret: openssl rand -hex 32
npm ci
npx prisma generate --schema apps/api/prisma/schema.prisma
docker compose up -d
npm run db:migrate
python3.12 -m venv apps/ml-service/.venv
apps/ml-service/.venv/bin/python -m pip install -r apps/ml-service/requirements-dev.txt
npm run ml -- -m rag.ingest
```

Run in separate terminals:

```sh
npm run dev:ml
npm run dev:api
npm run dev:worker
npm run dev:web
```

Open http://localhost:3001. The backend launchers and Vite load the root `.env`; shell/platform environment
values take precedence. `npm run ml -- ...` runs Python in the ML service directory. Direct
Python/Prisma invocations need their environment supplied separately. For a web production build
using local configuration, run `npm run build:web`; hosting providers should set
`VITE_API_URL` in their build environment. The former `NEXT_PUBLIC_API_URL` name is accepted
as a migration fallback; new configuration should use `VITE_API_URL`.

If an existing `.venv` was created with Python 3.9, create a separate Python 3.12 environment
rather than mixing installations. Python tests accept `PYTHON=/absolute/path/to/python`.

## Verification

```sh
# Lightweight test environment: no GPU, model downloads, or llama.cpp build needed.
apps/ml-service/.venv/bin/python -m pip install -r apps/ml-service/requirements-test.txt
npx playwright install chromium
npm run verify
```

`verify` runs API tests (including an isolated Redis/BullMQ worker), Python tests, both
production builds, and desktop/mobile Chromium tests. Browser tests use synthetic API responses;
they do not prove real model quality. On Linux, install browser system dependencies using
`npx playwright install --with-deps chromium`.

Set `TEST_DATABASE_URL` to a **disposable, migrated test database** to additionally verify worker
PostgreSQL persistence and transactional knowledge ingestion. CI provisions this database.
Do not point this variable at a production database. Ingestion tests use their own temporary schema.

```sh
docker build -f apps/ml-service/Dockerfile.smoke -t hirelens-smoke .
docker run --rm hirelens-smoke
```

The clean-container smoke test exercises the real stub and HTTP authentication in a fresh Python
runtime. It does not replace building and testing the production GGUF image.

## Behavior and limits

- Access requires a separate random token, held in browser memory only. Refreshing loses access.
- Raw inputs expire within 15 minutes. Results expire within one hour of submission.
- Delete revokes access immediately; active computation cannot restore a deleted result.
- Two analyses may be admitted at once across API replicas. The worker runs one at a time.
- Transient inference failures get one retry after five seconds; invalid results fail terminally.
- Polling tolerates temporary errors for ten minutes and can resume using **Check existing analysis**.
- PostgreSQL stores anonymous completion records, never candidate documents or assessments.
- The `KnowledgeChunk` table is exclusively the bundled knowledge corpus. Each ingestion atomically
  replaces its full snapshot, including deleted/renamed sections; do not store unrelated data there.
- Resumes are capped at 8,000 characters and job descriptions at 6,000, sized to fit the model's
  6,144-token context with 800 tokens reserved for the answer (`apps/ml-service/inference/limits.py`;
  the TypeScript caps must match, and a test enforces it). Unusually dense text can still exceed the
  budget; the tokenizer check then fails the job with a "shorten them" message instead of truncating.
  Changing the context size requires retraining and re-evaluating the model.

## Deployment and training

See [DEPLOYMENT.md](DEPLOYMENT.md) for a step-by-step production layout; [OPERATIONS.md](OPERATIONS.md) for readiness, monitoring, rollback, and rollout validation;
[SECURITY.md](SECURITY.md) for privacy and legacy migration;
[training instructions](apps/ml-service/training/README.md) and the [Colab notebook](apps/ml-service/training/hirelens_training.ipynb) for reproducible model artifacts;
and [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for verification and remaining release gates.

The historical [repository audit](REPOSITORY_AUDIT.md) contains findings from an earlier working
state. It is not the current unresolved-task list.

## React frontend

The frontend lives in `apps/web/src`: `main.jsx` mounts React, `App.jsx` contains the workspace,
`components/` contains the assessment and lens graphics, and `lib/api.js` talks to the unchanged
Fastify API. Client source is plain JavaScript/JSX; backend/shared contracts remain TypeScript.

```sh
npm run dev:web       # Vite at http://127.0.0.1:3001
npm run build:web     # Static production assets in apps/web/dist
npm run preview:web  # Local preview of the built assets on port 3001
```

Publish `apps/web/dist` with a static host. Vite preview is for local verification, not production
hosting. HTML metadata and CSP are included in the build; `dist/_headers` supplies the full HTTP
security policy for hosts that support that file. On other hosts, apply those headers in the host's
configuration, especially `frame-ancestors`/`X-Frame-Options`, which cannot be enforced by a meta tag.
Only public browser configuration belongs in `VITE_*` variables. The UI no longer requires a
Next.js server or App Router. The current one-page interface uses section anchors, so no client
routing dependency or SPA rewrite is required.
