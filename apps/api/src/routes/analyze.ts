import { randomUUID } from "node:crypto";
import type { FastifyInstance } from "fastify";
import type { Queue } from "bullmq";
import { AnalyzeRequestSchema, AnalysisResultSchema } from "@hirelens/shared";
import { newToken, RETENTION_SECONDS, type PrivateStore } from "../privacy.js";
import { mapJobState } from "../result.js";
import { inSpan, traceHeaders } from "../tracing.js";

export interface AnalysisDependencies {
  queue: Pick<Queue, "add" | "getJob" | "getJobCounts">;
  store: PrivateStore;
}
const validId = (id: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id);

export async function analyzeRoutes(app: FastifyInstance, { queue, store }: AnalysisDependencies) {
  app.post("/analyze", { config: { rateLimit: { max: 5, timeWindow: "1 minute" } } }, async (request, reply) => {
    const parsed = AnalyzeRequestSchema.safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: "Check the resume and job description" });
    const jobId = randomUUID();
    if (!(await store.admit()) || !(await store.reserve(jobId))) {
      return reply.header("Retry-After", "60").code(429).send({ error: "The service is busy. Try again in a minute." });
    }
    const accessToken = newToken();
    try {
      await inSpan("analysis.submit", { "hirelens.job.id": jobId }, async () => {
        await store.create(jobId, accessToken, parsed.data);
        // Queue data, return values, and failed reasons never contain candidate documents: at most
        // the W3C trace headers, so the worker's spans join this trace.
        const trace = traceHeaders();
        await queue.add("analyze", Object.keys(trace).length ? { trace } : {}, { jobId, attempts: 2,
          backoff: { type: "exponential", delay: 5000 }, removeOnComplete: true, removeOnFail: { age: 3600, count: 200 } });
      });
    } catch {
      await store.remove(jobId);
      await store.release(jobId);
      return reply.code(503).send({ error: "The service is temporarily unavailable." });
    }
    return reply.code(202).send({ jobId, accessToken, expiresIn: RETENTION_SECONDS });
  });

  app.post<{ Params: { jobId: string } }>("/analyze/:jobId/preview", async (request, reply) => {
    const id = request.params.jobId;
    const token = /^Bearer ([a-f0-9]{64})$/.exec(request.headers.authorization ?? "")?.[1];
    const preview = AnalysisResultSchema.partial().safeParse(request.body);
    if (!validId(id) || !token || !preview.success || !(await store.acceptPreview(id, token, preview.data))) {
      return reply.code(404).send({ error: "Analysis unavailable." });
    }
    return reply.code(204).send();
  });

  app.get<{ Params: { jobId: string } }>("/analyze/:jobId", async (request, reply) => {
    const id = request.params.jobId;
    if (!validId(id) || !(await store.authorized(id, request.headers.authorization))) {
      return reply.code(404).send({ error: "Analysis unavailable or expired." });
    }
    const result = await store.result(id);
    if (result) return { status: "done", ...result };
    const job = await queue.getJob(id);
    const status = job ? mapJobState(await job.getState()) : "failed";
    if (status === "failed" || status === "done") {
      // The worker can finish and remove the queue entry between the two reads.
      const completed = await store.result(id);
      if (completed) return { status: "done", ...completed };
      const error = job?.failedReason === "Documents exceed model limits"
        ? "The documents exceed the model’s limits. Shorten them and submit again."
        : "The analysis did not finish. Try again.";
      return { status: "failed", error };
    }
    const preview = status === "active" ? await store.preview(id) : null;
    return preview ? { status, preview } : { status };
  });

  app.delete<{ Params: { jobId: string } }>("/analyze/:jobId", async (request, reply) => {
    const id = request.params.jobId;
    if (!validId(id) || !(await store.authorized(id, request.headers.authorization))) {
      return reply.code(404).send({ error: "Analysis unavailable or expired." });
    }
    await store.remove(id);
    // Active computation may finish, but save() cannot recreate deleted results.
    const job = await queue.getJob(id);
    if (job) {
      try { await job.remove(); await store.release(id); } catch { /* Active job releases its slot when processing ends. */ }
    } else await store.release(id);
    return reply.code(204).send();
  });
}
