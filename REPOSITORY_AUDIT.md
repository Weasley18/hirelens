# HireLens repository audit

Reviewed 2026-11-06 against the working tree, including its uncommitted restructuring. This is a code and local-verification audit, not a claim that every possible defect has been discovered. No application code was changed.

The apps/api, apps/web, apps/ml-service, packages/shared split is sensible. The project is not ready for public use with real candidate data: access control, inference deployment, request lifecycles, persistence, and model evaluation need work. Several comments describe guarantees that the implementation does not provide.

**Validation performed**

- `npm test`: 14 passing API/schema unit tests.
- `python3 -m pytest -q` in apps/ml-service: 59 passing tests. The local `.venv` lacks pytest; these ran with the system Python environment.
- API TypeScript build and Next.js production build both pass.
- Isolated Fastify injection reproduced HTTP 429 on poll 20 after one submission.
- Direct calls reproduced the stub IndexError, curation TypeError/AttributeError, schema disagreement, missed Go extraction, overlapping React aliases, and oversized chunks.
- Importing the shared package succeeds on installed Node 22.19 with native TypeScript stripping, but fails with stripping disabled. This is a runtime portability issue, not a failure of this machine's default build.
- AWS base-image and gateway constraints and Next.js advisories were checked against official documentation.
- No real GGUF inference, training, AWS deployment, complete database/Redis integration run, browser interaction audit, or exhaustive dependency vulnerability scan was performed. Latency, model memory consumption, and hiring-quality claims remain unverified. Secret values were not included in the review output.

Priority: P1 = fix before public deployment or relying on results; P2 = correctness/reliability/maintainability; P3 = smaller operational and UX improvements. Findings marked reproduced were executed locally; other findings follow from code inspection unless explicitly qualified.

**Security and deployment blockers**

1. **P1 — Anyone can retrieve another user's analysis.** `apps/api/src/routes/analyze.ts:20,28`: jobs use BullMQ's default incrementing IDs, and GET accepts any ID without authentication or ownership. Enumerating IDs exposes candidate assessments and model-produced information. UUID database IDs do not protect Redis job IDs. Add authenticated ownership, or an appropriately scoped unguessable capability for an explicitly anonymous demo, and enforce it on reads.

2. **P1 — Public inference bypasses API controls.** `apps/ml-service/scripts/deploy_aws.sh:73` creates a public HTTP API; `inference/server.py:36` has no caller authentication, and `worker.ts:19` sends none. A caller can bypass Fastify's rate limit and invoke expensive inference directly. Protect the service with authenticated service-to-service calls and restrict its public exposure; add workload limits at the actual inference boundary.

3. **P1 — Normal polling exceeds the global rate limit (reproduced).** `apps/api/src/server.ts:13` allows 20 requests/minute globally. `apps/web/lib/api.ts:5,44` polls every 1.5 seconds. POST plus 19 polls consumes the allowance; poll 20 fails around 30 seconds and the client abandons the job. Scope expensive-submission limits separately from status reads, and handle 429/Retry-After. The evaluator has the same conflict.

4. **P1 — Docker uses the wrong package manager.** `apps/ml-service/Dockerfile:3,7` selects Lambda Python 3.11 but executes `dnf`. AWS documents Python 3.11 as Amazon Linux 2 using yum; dnf belongs to the newer AL2023 images. Align the base image and build commands, then build and smoke-test the actual deployment image. [AWS base-image documentation](https://docs.aws.amazon.com/lambda/latest/dg/python-image.html).

5. **P1 — A required runtime dependency is declared only for development.** `common.py:73` imports jsonschema on every output-validation path. `requirements.txt` does not declare it, while `requirements-dev.txt:5` does; Docker installs only the former. Runtime success should not depend on an accidental transitive installation. Move jsonschema into runtime requirements and exercise `/infer` in a clean image.

6. **P1 — Gateway timeout contradicts the inference design.** `deploy_aws.sh:57,74` configures a 60-second Lambda behind an HTTP API; `worker.ts:10` allows 90 seconds. HTTP APIs permit at most 30 seconds of integration time. A cold/slow invocation can time out at the gateway while computation continues, and the queue job fails. The outer job queue does not remove this inner synchronous timeout. Use an invocation mechanism compatible with the measured inference duration. [AWS HTTP API quotas](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-quotas.html).

7. **P1 — Next.js is pinned to a release with published security fixes missing.** `apps/web/package.json:12` pins 14.2.15. The official December 2025 advisory lists 14.x App Router releases before 14.2.35 as affected by a denial-of-service issue. Upgrade to a currently supported, patched release and review subsequent advisories; 14.2.35 is a historical fix, not a claim about today's safest version. No exploit was attempted. [Next.js advisory](https://nextjs.org/blog/security-update-2025-12-11), [subsequent official security release](https://vercel.com/changelog/next-js-may-2026-security-release).

8. **P1 — Accepted input can greatly exceed the model context.** `packages/shared/src/analysis.ts:38` and `inference/server.py:26` accept 20,000 characters per document. `inference/llm.py:26` configures 2,048 tokens total and up to 800 output tokens, while `prompt.py:45` includes both complete documents plus context. There is no tokenizer-based budget or output-space reservation. Many accepted requests cannot fit; near-limit prompts also leave insufficient room for JSON. Validate the complete token budget before inference and apply the same policy to training.

9. **P1 — Raw candidate documents have indefinite database retention.** `worker.ts:30` stores full resumes and JDs; `schema.prisma:10` has no owner, expiry, or deletion workflow. Redis cleanup does not delete Postgres rows. Minimize stored data, define retention, and provide access-controlled deletion before accepting real resumes. The UI should explain what is retained.

**Request lifecycle and persistence**

10. **P2 — Redis outages can leave API requests waiting indefinitely.** `apps/api/src/queue.ts:6` gives the API producer the same unbounded retry configuration needed by the blocking worker. The installed Redis client also enables its offline queue. Split producer/worker connection policies, impose bounded submission deadlines, and return a recoverable service-unavailable response.

11. **P2 — The queue admits more work than the UI can wait for.** `worker.ts:42` has concurrency one; `analyze.ts:20` has no backlog admission control. `api.ts:6` gives a job approximately 90 seconds including queue wait, while a single inference may itself take 90 seconds. Several valid submissions can make later users time out before their jobs start. Expose durable job status, permit resuming, and set capacity/backlog policies based on measured latency.

12. **P2 — Client requests have no actual timeout or cancellation.** `apps/web/lib/api.ts:28,47` uses fetch without AbortSignal. Sixty polls do not bound elapsed time if one fetch hangs. A temporary polling failure discards the job ID, and retrying submits another job. Add request deadlines, cancellation/unmount cleanup, bounded transient retries, and job resumption.

13. **P2 — Transient failures have no job retry policy.** `analyze.ts:20` sets retention only; worker network/database failures fail the job immediately. Introduce selective retry/backoff after making processing idempotent. Do not retry schema-invalid outputs indefinitely.

14. **P2 — Processing is not idempotent.** `worker.ts:30` always creates a new Analysis row, and `schema.prisma:10` stores no unique job ID. If a worker dies after insertion but before job completion, stalled-job recovery can insert a second row and inflate `/stats`. Persist a unique job association and use idempotent writes; address the DB/Redis completion gap explicitly.

15. **P2 — Durable storage cannot reconstruct a complete result.** `worker.ts:30` and `schema.prisma:10` omit verdict and strengths, and the read endpoint serves only Redis return values. Once a job is removed by age/count, its complete result is unavailable even though sensitive source documents remain in Postgres. Store the complete validated result with lifecycle status, owner, job ID, and model/prompt version, and read durable results from that record.

16. **P2 — Health checks do not establish readiness.** `api/src/server.ts:21` always reports OK, and `inference/server.py:31` reports only the backend name. Neither establishes that dependencies/model are usable. A missing model or broken DB can coexist with healthy status. Add separate readiness checks and startup validation; retain lightweight liveness checks. The API also lacks graceful shutdown of Fastify/Prisma/queue connections.

17. **P2 — Rate limiting is process-local and proxy identity is unspecified.** `server.ts:8,13` configures neither shared rate-limit storage nor trusted proxy handling. Multiple replicas have separate allowances; behind a proxy, users may share its IP and exhaust one bucket. Configure known proxy hops explicitly and use a shared limiter where deployment topology requires it.

18. **P2 — Local infrastructure exposes databases broadly and the queue is not durable across recreation.** `docker-compose.yml:10,14` publishes Postgres and unauthenticated Redis without a loopback bind. Redis has no configured persistent volume/AOF policy. Host/network exposure depends on firewall configuration, but these are unsafe defaults for a development service intended to be local. Bind localhost and explicitly decide queue durability. Compose is labeled local-only; it is not a production deployment specification.

**Inference, retrieval, and contracts**

19. **P1 — The default backend produces fake assessments without a visible disclosure.** `inference/llm.py:24` defaults to stub, while `apps/web/app/page.tsx:30` displays every returned result identically. Contrary to the llm.py comment, the UI neither reads ML health nor shows the backend. Return backend/degraded-mode metadata and clearly label demo results; fail production startup if an unintended stub is selected.

20. **P2 — Valid inputs crash the stub (reproduced).** `inference/llm.py:92` indexes a fallback list with `len(questions)`. With no recognized resume skills, no detected gaps, and no retrieved context, the list has one item but the loop requires two questions: its second iteration raises IndexError. A valid pastry-chef resume/JD pair reproduces this. Ensure fallback generation covers every required question.

21. **P2 — Output validators do not agree (reproduced).** JSON Schema rejects additional properties, but the Zod objects in `packages/shared/src/analysis.ts:13,25` accept and strip them. Python also rejects score strings/missing gaps before API normalization can repair them. Shared-fixture tests cannot establish validator parity, and the named `test_schema_parity.py` file does not exist. Generate validators from one contract or run the same valid/invalid corpus through both; explicitly define where normalization occurs.

22. **P2 — Normalization invents a favorable interpretation of invalid results.** `apps/api/src/result.ts:36` clamps arbitrary out-of-range scores, and line 39 treats missing/null gaps as no gaps. Missing evidence is not evidence of no gaps; a malformed negative/huge score is not necessarily a rounding slip. Reject substantive defects, or expose a degraded result instead of silently presenting repaired claims as assessed facts.

23. **P2 — Retrieval leaves a long-lived transaction open.** `rag/retrieve.py:39,51` uses a cached default psycopg connection and runs SELECT without commit, rollback, or autocommit. This can leave idle transactions; non-OperationalError SQL failures can leave an aborted transaction that subsequent calls reuse. Use autocommit for these reads or scoped transactions, reset failed connections, and set query deadlines. [Psycopg transaction behavior](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).

24. **P2 — Ingestion does not remove renamed/deleted source material.** `rag/ingest.py:44` deletes only source labels present in the new chunk set. Renaming a heading/file title or deleting a section leaves the old chunks behind unless `--reset` is used. Track stable document IDs and replace all chunks for a document, including deleted ones, transactionally.

25. **P2 — Retrieval degradation is invisible to the user.** `inference/server.py:47` catches every retrieval exception and returns an ordinary analysis without sources or degraded-status metadata. `schema.prisma:10` also records no retrieved chunk/model versions. Users cannot distinguish grounded answers from fallback answers, and maintainers cannot reconstruct why a score was produced. Preserve provenance and expose fallback status; alert on persistent failures.

26. **P2 — Skill extraction changes the evidence incorrectly (reproduced).** `inference/skills.py:22` recognizes golang/go lang but not a JD saying Go; `:99` counts overlapping aliases independently. React Native also yields React, and overlapping aliases inflate mention rankings. Plain text such as “no Kubernetes experience” is still treated as Kubernetes evidence. Improve alias matching and contextual handling, and test missing-skill priorities against real phrasing.

27. **P2 — Chunk limits are not hard limits (reproduced).** `rag/chunking.py:28` leaves a single oversized paragraph intact; a 5,000-character paragraph yields a 5,007-character chunk. `prompt.py:30` breaks at the first chunk that does not fit, dropping even later smaller chunks. Add paragraph fallback splitting, account for headers/separators, and skip or truncate oversized context within a tokenizer-based budget.

28. **P2 — Untrusted document text is embedded directly into raw chat framing.** `inference/prompt.py:45,59` includes resume/JD text verbatim inside a hand-built template. There is no explicit instruction/data separation beyond section titles, special-token handling, or adversarial test suite. Instruction-like resume content can attempt to manipulate the assessment; actual model susceptibility was not measured. Add adversarial evaluation, evidence checks, and safe template handling. JSON validity alone cannot detect manipulated scores.

29. **P2 — Model validity is mostly syntax validity.** `inference/server.py:61` checks schema only; consistency checks used during curation are not applied at inference. The output has no evidence references or confidence/abstention mechanism. A schema-valid result may invent strengths, contradict its gaps, or apply irrelevant criteria. Define a scoring rubric, evidence requirements, and substantive evaluation before treating fitScore as reliable. No claim of measured discrimination is made: subgroup/counterfactual evaluation is currently absent.

**Training and evaluation**

30. **P2 — Curation crashes on the malformed outputs it should reject (reproduced).** `data_gen/curate.py:103` concatenates validation and heuristic results without short-circuiting. A string fitScore raises TypeError; a string in gaps raises AttributeError after schema validation has already identified the problem. Return schema failures first, then run typed semantic checks.

31. **P2 — Deduplication discards distinct training pairs.** `data_gen/generate.py:49` and `curate.py:122` use only the first 200 resume characters. Different resumes with the same opening, and one resume against different JDs, collapse into the same key. Hash normalized complete resume/JD pairs; handle train/test separation at candidate/document-family level separately.

32. **P2 — Evaluation does not match the deployed inference path.** `training/evaluate.py:107` constructs prompts without retrieval, while `prepare_dataset.py:61` normally trains with retrieved context. It evaluates the adapter rather than the final quantized GGUF. The training README's copy-paste path additionally chooses `--context none`. Preserve held-out context or retrieve using the same pipeline, and evaluate the actual exported model too.

33. **P2 — Evaluation can report failures and still succeed as a command.** `training/evaluate.py:117` only prints a report; `eval/run_eval.py:87` also exits normally after failed cases. Manual expectations are printed, not asserted; polling assumes every body contains status and omits an HTTP status check. Add explicit failure thresholds/exit codes and robust polling. Expand evaluation beyond 12 illustrative cases and teacher-score agreement to grounded quality, injection, domain coverage, and counterfactual behavior.

34. **P2 — Training and quantization are not reproducible or safely resumable.** `training/README.md:24` installs unpinned training dependencies; `scripts/quantize.sh:15` clones the moving llama.cpp head, while inference pins an older llama-cpp-python. There is no captured toolchain/model revision or artifact checksum. A failed initial build leaves llama.cpp present and later runs skip the build entirely. Pin a tested toolchain and model revisions, record artifact manifests, and check actual build outputs before skipping steps.

**Repository and product structure**

35. **P2 — Documented environment setup is inconsistent across services.** `README.md:50` creates only the root .env. API scripts execute in apps/api and `env.ts:1` uses default dotenv resolution; Prisma and Next also have their own project-root conventions. Python inference/ingestion never load dotenv, unlike the teacher module. The existing ignored apps/api/.env masks part of this locally. Establish explicit per-service configuration loading or a root launcher, and verify from a clean checkout. Do not copy teacher credentials into runtime environments.

36. **P2 — The shared package has an implicit Node runtime requirement.** `packages/shared/package.json:6` exports TypeScript source; the API production command is plain node and there is no engines/runtime pin. This works on the installed Node 22.19, but the import fails when native TypeScript stripping is unavailable/disabled. Publish/build JavaScript with explicit exports, or enforce and document the required runtime. A successful tsc run alone does not prove deployment portability.

37. **P2 — Verification does not cover the service boundaries.** Root `package.json:9` runs only API unit tests. There is no repository CI workflow, frontend behavior suite, HTTP route/authorization test, queue-worker persistence integration test, or clean-image inference smoke test. The Python tests called pipeline tests exercise pure helpers, not the deployed pipeline. Add targeted boundary tests for the failures above, and one root verification command that covers both languages and production builds.

38. **P2 — The current Git snapshot does not contain the working application.** At review time, apps/, packages/, root manifests and Compose were untracked, and the former root implementation files were deleted. This is a working-tree observation, not a request to discard or commit changes automatically. A clone of the current commit will not reproduce the reviewed application. Review and commit the intended migration. Remove the tracked stray `mnt/user-data/outputs/hirelens-src/apps/ml-service/training/README.md` duplicate when finalizing structure.

39. **P3 — UI can show results beside different input and cannot explain progress accurately.** `page.tsx:64,76` leaves inputs editable during inference, while the result corresponds to the submission snapshot. The onStatus callback is unused, so queued jobs get a misleading model-wakeup message. Inputs lack maxLength/counters and disabled-submit explanations. Bind results to a visible document snapshot, show real job state, reuse shared validation constants, and announce completion accessibly.

40. **P3 — Operational conventions remain incomplete.** `apps/web/package.json:8` starts production on Next's default 3000, colliding with the API default, despite dev using 3001. `/stats` orders by createdAt without an index. Deployment mutates a source directory to stage the schema, uses a mutable latest image tag, and does not define deployment for API/worker/web. README claims about zero cost and approximate cold-start latency are not backed by measurements/artifacts in this repository. Standardize ports and deployment configuration, add the small query index when warranted, build from an explicit context, track image digests, and document measured limits instead of guarantees.

**Recommended implementation order**

First fix unauthorized reads/direct inference access, dependency security, and candidate-data retention. Next repair the image, runtime dependencies, configuration loading, polling limits, timeout architecture, and token budgeting. Then establish a durable, idempotent job/result lifecycle with retry and resumption. Finally align contracts and training/evaluation, preserve provenance, and add integration checks that exercise the real deployment boundaries.

Keep the existing monorepo split. Add explicit ownership inside it: API routes orchestrate access-controlled application services; job processing persists lifecycle state through a repository layer; the ML runtime owns inference and retrieval; training dependencies stay separate; shared contracts are generated or checked against the same boundary-case corpus. Additional services or a large framework migration are not required to resolve these findings.
