# Deploying HireLens

One supported layout. Other hosts work if they meet the same constraints (see SECURITY.md and OPERATIONS.md).

| Piece | Where | How |
|---|---|---|
| Postgres + pgvector | Managed (Neon, Supabase or RDS) | Connection string in `DATABASE_URL` |
| API + worker + ML service + Redis | One VM with Docker, ~2 GB RAM (e.g. Oracle Always Free Ampere A1) | `deploy/update.sh` (Caddy terminates TLS) |
| Web | Static host that honours `_headers` (Cloudflare Pages or Netlify) | `npm run build:web`, publish `apps/web/dist` |

The ML service calls the model provider (OpenAI by default) and is only reachable on the VM's private
Docker network. Alternatives: run it on AWS Lambda (step 2b), or use a 1 GB VM for the rest (step 3b).

Deploy everything from the same git commit. Use synthetic resumes only until the staging checks in OPERATIONS.md pass.

## 1. Database

Create a Postgres 16 database with the `vector` extension available. Keep the direct (non-pooled) URL for migrations.
Ingest the knowledge corpus once per corpus change, from your machine:

```sh
DATABASE_URL="postgresql://…" npm run ml -- -m rag.ingest
```

## 2. Model provider

The default model is `gpt-6-luna` with medium reasoning effort. At about 4,000 input and up to ~3,000
output tokens (answer plus hidden reasoning) per analysis, that is roughly $0.002 per analysis at
November 2026 list prices ($0.10 / $0.50 per million tokens); re-check current pricing before launch.
If the evaluation shows Luna missing gaps or scoring inconsistently, switch to `gpt-6.1-terra`
($1 / $5) before raising reasoning effort further.

Use a separate API key for production with a monthly spending limit set in the provider's console:
the worker processes one analysis at a time, which bounds request rate, not spend. Check the provider's API data
retention and training terms and make sure your privacy notice matches them (step 4).

### 2b. Alternative: inference on AWS Lambda

Only needed with the 1 GB VM layout (step 3b). Needs Docker and the AWS CLI signed in to your account.

```sh
export AWS_REGION=ap-south-1
export DATABASE_URL="postgresql://…"
export ML_SERVICE_TOKEN="$(openssl rand -hex 32)"   # keep it: the worker needs the same value
export OPENAI_API_KEY="sk-…"                        # stored as an encrypted Lambda variable
# Optional: HOSTED_MODEL=gpt-6.1-terra, HOSTED_REASONING_EFFORT=low|high, HOSTED_PROVIDER=anthropic|gemini
MODEL_BACKEND=hosted bash apps/ml-service/scripts/deploy_aws.sh
```

The script prints `ML_LAMBDA_FUNCTION` and the one IAM permission the worker needs.
`HOSTED_TIMEOUT_SECONDS` (default 60) is the total provider time for one analysis, including a retry;
a retry only starts if at least 10 seconds remain. It must be at least 10 seconds below
`LAMBDA_TIMEOUT` (default 80), which must stay below the worker's `INFERENCE_TIMEOUT_SECONDS`
(default 90). The script checks the first relationship.

*Self-hosted model alternative:* train `hirelens-q4.gguf` (see `apps/ml-service/training/README.md`),
place it in `apps/ml-service/`, and deploy with `MODEL_BACKEND=gguf`.

## 3. Everything else on one VM

These steps use an Oracle Cloud Always Free **Ampere A1** VM (1 OCPU, 6 GB, Ubuntu 24.04); any Ubuntu VM
with about 2 GB of RAM works the same way. Replace `<VM_IP>` and the key path with yours.

1. **Open ports 80 and 443 in Oracle's network.** *Networking → Virtual cloud networks →* the VM's VCN
   *→ Security → Default security list → Add ingress rules*: source CIDR `0.0.0.0/0`, IP protocol TCP,
   destination port `80`. Repeat for `443`.
2. **DNS:** an A record for your API domain (e.g. `api.yourdomain.com`) pointing at the VM's public IP.
   Caddy uses it to get the HTTPS certificate on first start.
3. **One-time VM setup** (swap, Docker, git, and ports 80/443 in Ubuntu's own firewall), from your machine:
   ```sh
   scp -i ~/.ssh/hirelens-vm.key deploy/micro/vm-setup.sh ubuntu@<VM_IP>:
   ssh -i ~/.ssh/hirelens-vm.key ubuntu@<VM_IP> 'bash vm-setup.sh'
   ```
4. **On the VM** (`ssh -i ~/.ssh/hirelens-vm.key ubuntu@<VM_IP>`):
   ```sh
   git clone https://github.com/Weasley18/hirelens && cd hirelens
   cp deploy/production.env.example deploy/production.env && nano deploy/production.env
   cp deploy/ml.env.example deploy/ml.env && nano deploy/ml.env
   bash deploy/update.sh
   curl https://api.yourdomain.com/ready
   ```
   In `production.env`, set `API_DOMAIN`, `DATABASE_URL` (direct, non-pooled URL), `ML_SERVICE_TOKEN`
   (`openssl rand -hex 32`) and `CORS_ORIGIN`; leave the Lambda lines commented out. In `ml.env`, set
   `OPENAI_API_KEY`. The first build takes 10–15 minutes on one OCPU.
5. **Updates:** `cd ~/hirelens && git pull && bash deploy/update.sh`. It rebuilds, applies new migrations
   and restarts only what changed.

Logs: `docker compose -f deploy/docker-compose.prod.yml logs -f worker ml` (from `~/hirelens`, with
`APP_REVISION` and `API_DOMAIN` exported as `update.sh` does, or use `docker logs <container>`).
Redis is private to the compose network and keeps nothing on disk, by design: a restart loses in-flight
analyses, and users resubmit.

To roll back, `git checkout <previous commit>` and run `bash deploy/update.sh`. Migrations are
forward-only; read OPERATIONS.md before rolling back across one.

### 3b. Alternative: a 1 GB Oracle Always Free VM (VM.Standard.E2.1.Micro)

Use this if you only have the 1 GB Micro VM. It runs the API, worker and Redis; the ML service needs
more memory, so it goes on AWS Lambda (step 2b). Nothing is built on the VM (1 GB is not enough to build):
`deploy/micro/ship.sh` builds the image on your machine, copies it over SSH and starts it, with
memory limits sized for 1 GB plus a 2 GB swap file.

1. **Oracle network:** *Networking → Virtual cloud networks →* your VCN *→ Security → Security
   lists → Default security list → Add ingress rules*: source `0.0.0.0/0`, TCP, destination port
   `80`; then the same for `443`.
2. **DNS:** create an A record for your API domain (e.g. `api.yourdomain.com`) pointing at the
   VM's public IP. Caddy needs it to get the HTTPS certificate.
3. **One-time VM setup** (swap, Docker, Ubuntu firewall ports 80/443), from your machine:
   ```sh
   scp -i ~/.ssh/hirelens-vm.key deploy/micro/vm-setup.sh ubuntu@<VM_IP>:
   ssh -i ~/.ssh/hirelens-vm.key ubuntu@<VM_IP> 'bash vm-setup.sh'
   ```
4. **Configuration:** `cp deploy/production.env.example deploy/production.env` and fill it in
   (`API_DOMAIN`, `DATABASE_URL`, `ML_SERVICE_TOKEN`, `CORS_ORIGIN`, and uncomment the
   `ML_LAMBDA_FUNCTION` and AWS lines). Leave `APP_REVISION` empty; the script sets it.
5. **Migrations** run from your machine against the production database:
   `DATABASE_URL="postgresql://…direct-host…" npm run db:migrate`
6. **Deploy** (and every later update, after committing):
   ```sh
   SSH_KEY=~/.ssh/hirelens-vm.key bash deploy/micro/ship.sh ubuntu@<VM_IP>
   curl https://api.yourdomain.com/ready
   ```
   On Apple Silicon the first build emulates x86 and takes several minutes.

Logs on the VM: `cd ~/hirelens && docker compose logs -f api worker`.

## 4. Web

Build with the public API origin baked in, then publish `apps/web/dist`:

```sh
VITE_API_URL="https://api.example.com" VITE_INFERENCE_PROVIDER="OpenAI" npm run build:web
```

`VITE_INFERENCE_PROVIDER` adds a notice, shown before submission, that documents are sent to that
provider. Set it whenever the ML service uses `MODEL_BACKEND=hosted`; leave it empty only for `gguf`.

On Cloudflare Pages or Netlify, set build command `npm ci && npm run build:web`, output directory `apps/web/dist`,
and the `VITE_API_URL` and `VITE_INFERENCE_PROVIDER` build variables. Both honour the generated `dist/_headers` security policy. Add the site's exact
origin to `CORS_ORIGIN` on the API and restart it.

## 5. Before real users

Work through "Staging rollout checks" in OPERATIONS.md, run `python -m eval.run_eval` against the deployed API
(`API_URL=https://api.example.com`), and set up the alerts listed there.
