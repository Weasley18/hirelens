# Deploying HireLens

One supported layout. Other hosts work if they meet the same constraints (see SECURITY.md and OPERATIONS.md).

| Piece | Where | How |
|---|---|---|
| Postgres + pgvector | Managed (Neon, Supabase or RDS) | Connection string in `DATABASE_URL` |
| Inference (ML service) | AWS Lambda container, private | `apps/ml-service/scripts/deploy_aws.sh` |
| API + worker + Redis | One small VM with Docker | `deploy/docker-compose.prod.yml` (Caddy terminates TLS) |
| Web | Static host that honours `_headers` (Cloudflare Pages or Netlify) | `npm run build:web`, publish `apps/web/dist` |

Deploy all four from the same git commit. Use synthetic resumes only until the staging checks in OPERATIONS.md pass.

## 1. Database

Create a Postgres 16 database with the `vector` extension available. Keep the direct (non-pooled) URL for migrations.
Ingest the knowledge corpus once per corpus change, from your machine:

```sh
DATABASE_URL="postgresql://…" npm run ml -- -m rag.ingest
```

## 2. Inference on Lambda

Needs the trained model at `apps/ml-service/hirelens-q4.gguf` (see `apps/ml-service/training/README.md`),
Docker, and the AWS CLI signed in to your account.

```sh
export AWS_REGION=ap-south-1
export DATABASE_URL="postgresql://…"
export ML_SERVICE_TOKEN="$(openssl rand -hex 32)"   # keep it: the worker needs the same value
LAMBDA_TIMEOUT=80 bash apps/ml-service/scripts/deploy_aws.sh
```

The script prints `ML_LAMBDA_FUNCTION` and the one IAM permission the worker needs.
Measure a cold and a warm invocation with a near-maximum-length input before going further. If inference takes
longer than the timeout, raise `LAMBDA_TIMEOUT` (≤135) and the worker's `INFERENCE_TIMEOUT_SECONDS` (≤140, and above
the Lambda timeout) together.

## 3. API, worker and Redis on a VM

On a Linux VM with Docker (2 vCPU / 2 GB is enough: inference is not on this machine), with DNS for your
API domain pointing at it and ports 80/443 open:

```sh
git clone https://github.com/Weasley18/hirelens && cd hirelens
cp deploy/production.env.example deploy/production.env   # fill in every value
export APP_REVISION="$(git rev-parse --short HEAD)"
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/production.env build
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/production.env run --rm migrate
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/production.env up -d
curl https://$API_DOMAIN/ready
```

Give the VM an instance role (or a dedicated IAM user) with only `lambda:InvokeFunction` on the inference function.
Redis is private to the compose network and keeps nothing on disk, by design: a restart loses in-flight analyses,
and users resubmit.

To roll back, check out the previous revision, set `APP_REVISION` to it and run `up -d` again. Migrations are
forward-only; read OPERATIONS.md before rolling back across one.

## 4. Web

Build with the public API origin baked in, then publish `apps/web/dist`:

```sh
VITE_API_URL="https://api.example.com" npm run build:web
```

On Cloudflare Pages or Netlify, set build command `npm ci && npm run build:web`, output directory `apps/web/dist`,
and the `VITE_API_URL` build variable. Both honour the generated `dist/_headers` security policy. Add the site's exact
origin to `CORS_ORIGIN` on the API and restart it.

## 5. Before real users

Work through "Staging rollout checks" in OPERATIONS.md, run `python -m eval.run_eval` against the deployed API
(`API_URL=https://api.example.com`), and set up the alerts listed there.
