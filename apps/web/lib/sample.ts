/**
 * The one-click demo payload. Replace SAMPLE_RESUME with your own resume before you share
 * the link — a recruiter clicking this button is the main path through the whole system.
 */

export const SAMPLE_RESUME = `Ronak — Backend Engineer
Bengaluru, India

SUMMARY
Backend engineer focused on API design, relational data modelling, and the parts of a
system that only show up under load. Comfortable owning a service from schema to deploy.

EXPERIENCE

Backend Engineer, Field Service Platform (2024 – present)
- Designed PostgreSQL schemas for audit, training, and inventory modules, using UUID keys,
  soft deletes, and generated reference codes across roughly 40 tables.
- Built a Fastify + TypeScript API with request validation at the boundary, cutting a class
  of malformed-payload incidents to zero.
- Moved report generation onto a Redis-backed BullMQ queue, taking p95 request latency on
  the affected endpoints from 800ms to 120ms.
- Containerised the stack with Docker and shipped it through GitHub Actions.

Engineering Intern, Industrial Monitoring (2023 – 2024)
- Built ingestion for pump-room telemetry and the dashboards that consumed it.
- Wrote the migration that backfilled two years of readings without downtime.

PROJECTS
- A fine-tuned 3B language model serving structured hiring assessments, quantized to 4-bit
  and deployed to AWS Lambda behind API Gateway, with retrieval over a pgvector knowledge base.
- A conversational mystery game on FastAPI and Redis, deployed on Railway.

SKILLS
TypeScript, Node.js, Fastify, Python, FastAPI, PostgreSQL, Redis, BullMQ, Docker,
React, React Native, Git, GitHub Actions.

EDUCATION
B.E. Computer Science and Engineering (Cyber Security), RNS Institute of Technology.`;

export const SAMPLE_JD = `Backend Engineer (Platform)

We run the services that everything else at the company depends on. You would own one of
them end to end, including what happens when it breaks at 2am.

What you will do
- Design and build APIs in Node.js and TypeScript that other teams depend on.
- Model data in PostgreSQL, including the migrations that have to run against live tables.
- Operate your service on Kubernetes, with infrastructure defined in Terraform.
- Take part in the on-call rotation and lead incident reviews.
- Mentor one or two junior engineers as the team grows.

What we are looking for
- 3+ years building production backend services.
- Strong PostgreSQL: you should be able to read a query plan and explain what it is doing.
- 2+ years running services on Kubernetes in production.
- Experience with Terraform or comparable infrastructure-as-code.
- A track record of improving something measurable: latency, cost, or reliability.

Nice to have
- Experience with message queues and asynchronous processing.
- Exposure to observability tooling such as Prometheus, Grafana, or OpenTelemetry.`;
