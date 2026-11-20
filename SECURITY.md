# Security implementation and rollout

The security findings from REPOSITORY_AUDIT.md have been addressed in code. These changes must be deployed together; they change the API/ML response contract, queue name, configuration, and database schema.

## Access and data lifecycle

This remains an anonymous demo, not a multi-user account system. Each POST /analyze returns a random UUID and a separate 256-bit accessToken. GET and DELETE /analyze/:id require `Authorization: Bearer <accessToken>`. IDs alone grant no access. Tokens are stored only as SHA-256 hashes on the server and kept only in browser memory. Anyone deliberately given the token has access until deletion/expiry. Reloading the page loses it; automatic expiry still applies.

Raw inputs are held in dedicated Redis keys for at most 15 minutes, and removed when processing finishes or the user deletes the analysis. Results and authorization expire no later than one hour after submission. Expiry uses Redis TTLs, not BullMQ's lazy job cleanup. Deleting an active job revokes access and removes its data; computation already in progress may finish in memory but cannot recreate the result. Queue records contain no candidate documents, result text, or upstream exception detail. Postgres stores only anonymous completion IDs/timestamps for statistics.

Use a private, access-controlled Redis instance. Disable persistence/backups for this ephemeral private-data store, or ensure provider backup retention matches the promised deletion policy; Redis key deletion cannot remove copies in external backups. The included local Compose file binds both databases to loopback and disables Redis snapshots/AOF. Keep Postgres backups containing legacy candidate data on an explicit expiry/deletion schedule too.

## Configuration

- Generate a secret with `openssl rand -hex 32`; set the same ML_SERVICE_TOKEN on the worker/API and inference service. There is no default secret. Never put this in VITE_* variables (or legacy NEXT_PUBLIC_* variables), URLs, source control, build arguments, or frontend code.
- API/worker: set NODE_ENV=production, DATABASE_URL, REDIS_URL, and exact comma-separated CORS_ORIGIN values. Wildcards are rejected. The API loads root .env for local development; explicitly supplied environment values take precedence.
- ML: set APP_ENV=production and MODEL_BACKEND=hosted or gguf. Production refuses stub output. With `hosted`, resume and job-description text is sent to the configured model provider (a third-party processor): build the web app with `VITE_INFERENCE_PROVIDER` so users are told before submitting, use a dedicated key with a spending limit, and confirm the provider's API retention terms match your privacy notice. Provider error bodies are discarded so they cannot carry document text into logs. The Docker image sets these, and the deploy script supplies the token at runtime. Non-Lambda service managers must use the ASGI lifespan/startup hooks.
- AWS worker: set ML_LAMBDA_FUNCTION and AWS_REGION; use an IAM role limited to lambda:InvokeFunction on that function ARN. Do not put permanent AWS credentials in the frontend. Local development instead uses ML_SERVICE_URL; non-Lambda production HTTP requires HTTPS plus the service token.
- Host the browser/API behind HTTPS. Set VITE_API_URL at web build time (Vite also reads root .env for local development). Public non-HTTPS API origins are rejected by the web configuration. Local localhost HTTP remains supported.
- Set TRUST_PROXY only to the actual trusted proxy IPs/CIDRs. The default trusts no forwarded IP header. Never trust arbitrary client-supplied forwarding headers.
- Node >=22.19 is required for the shared TypeScript source package. Use an actively patched Node release in deployment.

Submission limits: five per minute per IP, twenty per minute across API replicas, plus an atomic two-job capacity lease. Reads have a separate allowance. Limits use shared Redis and fail closed on Redis failure. Lambda deployment reserves at most two concurrent executions; the HTTP inference process permits one active generation. These limits bound compute but are not a complete anti-bot/product billing system.

## Deploying over an existing installation

Do these in a maintenance window. No live database or AWS environment was modified while implementing this change.

1. Stop all old API/worker processes so they cannot serve unauthenticated results or write old records.
2. Review and apply `apps/api/prisma/migrations/20261106000000_minimize_candidate_data/migration.sql` using `npm run prisma:deploy --workspace apps/api`. It deliberately and irreversibly drops the old resume/JD/assessment columns, preserving completion counts. Prisma must receive DATABASE_URL in its environment or apps/api/.env when invoked directly.
3. Run `npm run privacy:purge-legacy --workspace apps/api`. This deletes only the old BullMQ `analysis` queue and its embedded private data. It refuses forced removal of active jobs. Existing backup copies need their own retention action.
4. Configure the service token, origins, TLS, trusted proxies, and worker IAM role. Regenerate Prisma with `npx prisma generate --schema apps/api/prisma/schema.prisma`.
5. Deploy ML, worker, API, and web together. `apps/ml-service/scripts/deploy_aws.sh` deploys a private Lambda, revokes the old script's `apigw-invoke` permission, removes a function URL if present, and no longer creates an API Gateway. Review any additional manually configured Lambda resource-policy grants; the script cannot infer ownership of unrelated grants. An obsolete gateway may remain provisioned, but its old invocation grant is removed.
6. Verify token rejection, authorized reads/deletion, production backend, queue processing, and real-model context limits in the target environment. Keep the ephemeral Redis store out of persistent snapshots.

The deployment script stores environment JSON temporarily with owner-only permissions and removes it on exit. Do not run deployment with shell tracing enabled. Supply credentials through the deployment platform's secret store.

## Model trust and abuse controls

Requests have byte and document-length caps. Unauthorized ML requests are rejected before parsing. Reserved chat delimiters in documents are rejected; document text is JSON-quoted, and the system prompt separates document data from instructions. The real model tokenizer enforces a full prompt-plus-output budget before generation. Error responses and application logs do not echo source documents or generated invalid content. Both validators reject extra fields and substantive malformed scores/missing evidence.

The UI labels simulated stub output and missing retrieval context, explains retention, and offers deletion. Assessments still require human review. These measures reduce prompt-injection risk; they do not establish that a language model can never follow a malicious instruction or make an unsupported hiring judgment. Adversarial evaluation of the actual GGUF model and evidence-quality testing remain necessary before production hiring use. The prompt changed; evaluate/retrain the model against the revised prompt before rollout.

## Verification

Verified locally: 19 API tests, 68 Python tests, both production builds, and zero vulnerabilities reported by npm audit. That earlier verification covered the former Next.js frontend. It has since been replaced by React/Vite; see IMPLEMENTATION_STATUS.md for migration checks. This is not a full audit of native/Python transitive dependencies.


API integration tests start an isolated, socket-only Redis, with no production connection. They exercise authorization, deletion during active work, TTL expiry, schema rejection, request caps, origin handling, submission/polling limits, and shared quota behavior. Python tests exercise authentication before parsing, private errors, body limits, chat delimiters, token budgeting, production stub rejection, and concurrent inference admission.

Current verification and rollout status are recorded in [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

Run:

```sh
npm test
npm run test:ml
npm run build --workspace apps/api
npm run build --workspace apps/web
npm audit
```

AWS deployment, the destructive migration, legacy-data purge, and real GGUF execution must be validated during rollout; they were not applied to a live environment here.

The React build emits `_headers` for static hosts and a CSP meta tag in HTML. Configure the full
HTTP headers on hosts that do not process `_headers`; framing protection requires HTTP headers.

## PDF reports

`POST /reports` renders finished analyses with headless Chromium (Puppeteer). Each item must carry
that analysis's access token, and the content comes from the stored, re-validated result, so the
endpoint cannot print arbitrary text. Labels are length-limited and every value is HTML-escaped.
The page runs with JavaScript disabled, all network requests aborted and a `default-src 'none'`
CSP; one page renders at a time with a 20-second limit, and the endpoint allows 10 requests a minute.
Chromium runs with `--no-sandbox` because the hardened, read-only, unprivileged container cannot
provide its sandbox; the measures above are what keep untrusted model output inert. PDFs are
streamed with `Cache-Control: no-store` and never written to disk.
