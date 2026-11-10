# Operating HireLens

## Release boundary

Deploy web, API, worker, ML, and schema changes together. Use immutable application revisions and
retain the matching model manifest and image digest. Configure NODE_ENV=production on API/worker,
APP_ENV=production and MODEL_BACKEND=gguf on ML, exact browser origins, HTTPS, private Redis,
and a least-privilege worker role for Lambda. Supply secrets through the hosting platform.
Never put service tokens into VITE_* variables (or legacy NEXT_PUBLIC_* variables).

The Lambda script uses a repository-root build context without staging files into source folders.
API/worker/web hosting is provider-specific and must still be selected and validated in staging.

## Health and observation

- API `/health`: lightweight liveness only.
- API `/ready`: verifies PostgreSQL and a worker heartbeat in Redis. A missing worker heartbeat
  becomes unavailable within 30 seconds. Use this for API routing readiness.
- ML `/health`: liveness only. ML `/ready` requires the service bearer token and verifies model
  availability, embedding generation, database access, and nonempty knowledge storage.
- Production HTTP startup loads the GGUF and fails if unavailable. Private Lambda invocations also
  validate production backend in the request path. Probe `/ready` through private invocation before
  moving production traffic; do not publish inference just to make monitoring convenient.
- Worker JSON events include processing time, queue wait time, completion, retry, and retrieval
  grounding status. Never log documents, generated assessments, access tokens, or upstream errors.

Configure the host's log-based alerts for repeated terminal failures, absent worker heartbeat,
ML readiness failures, sustained retrieval degradation, and processing/queue waits approaching
client or input-expiry limits. Monitor CPU/RSS and Lambda duration/memory at the host/platform.
Measure baseline traffic before setting production latency objectives.

Admission is an atomic Redis lease: two jobs across replicas, expiring after 15 minutes if the
worker disappears. The worker runs one at a time, with at most two inference attempts. Do not
increase capacity without rechecking measured latency against the ten-minute browser polling
window and the fifteen-minute input lifetime. A deleted active job keeps its capacity slot until
processing ends so deletion cannot be used to bypass compute limits.

## Staging rollout checks

Use synthetic resumes only for rollout tests:

1. Build from a clean checkout, generate Prisma, migrate the isolated staging DB, ingest the corpus.
2. Verify API `/ready` and authenticated ML `/ready`. Wrong or missing inference credentials must fail.
3. Submit an analysis. An ID alone must not allow reading/deletion; the returned capability must work.
4. Verify real GGUF metadata, valid result shape, cold/warm latency, queue waits, and model memory.
5. Delete during processing: subsequent reads must fail and the result must not reappear.
6. Verify raw-input expiry, one-hour result/auth expiry, and Redis persistence/backup settings.
7. Briefly interrupt inference: bounded retry should recover. Invalid output must stop without leaking it.
8. Stop/restart worker and Redis in staging. Readiness must fail, and users must receive recoverable
   errors. Ephemeral Redis loss means pending assessments cannot be recovered; users resubmit.
9. Check actual proxy IP handling, CORS, HTTPS, build-time API origin, and private Lambda policy.
10. Retain sanitized test evidence, artifact hashes, measured costs, and rollback revision.

## Legacy privacy rollout and rollback

See SECURITY.md before changing an existing installation. Stop old processes first. The migration
that removes candidate columns is destructive: approve and execute it in an intentional maintenance
window, then run the legacy-queue purge. Provider backups need separate retention verification;
application deletion cannot erase backup copies. No live migration or cloud-policy change is
performed by the test suite.

Roll back only to a revision compatible with the minimized schema, capability authorization, and
`analysis-private-v2` queue. Never restore the old unauthenticated API or candidate-bearing backups
to recover availability. Stop submissions, restore a known-good compatible application/model pair,
verify readiness and synthetic lifecycle checks, then reopen traffic.

## React static hosting

Build with `npm run build:web` and publish `apps/web/dist`. Set VITE_API_URL before the build;
changing it requires rebuilding assets. Preserve the generated `_headers` policy at the host.
Use `npm run preview:web` only for local smoke checks. Frontend hosting no longer needs Next.js.
