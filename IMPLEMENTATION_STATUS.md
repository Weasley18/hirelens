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
