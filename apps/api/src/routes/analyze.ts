import { randomUUID } from "node:crypto";
import type { FastifyInstance } from "fastify";
import type { Queue } from "bullmq";
import { AnalyzeRequestSchema } from "@hirelens/shared";
import { newToken, RETENTION_SECONDS, type PrivateStore } from "../privacy.js";
import { mapJobState } from "../result.js";

export interface AnalysisDependencies {
  queue: Pick<Queue, "add" | "getJob" | "getJobCounts">;
  store: PrivateStore;
}
const validId = (id: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(id);

export async function analyzeRoutes(app: FastifyInstance, { queue, store }: AnalysisDependencies) {
  app.post("/analyze", { config: { rateLimit: { max: 5, timeWindow: "1 minute" } } }, async (request, reply) => {
    const parsed = AnalyzeRequestSchema.safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: "Check the resume and job description" });
    const counts = await queue.getJobCounts("waiting", "active", "delayed");
    if (Object.values(counts).reduce((a, b) => a + b, 0) >= 100 || !(await store.admit())) {
      return reply.header("Retry-After", "60").code(429).send({ error: "The service is busy. Try again in a minute." });
    }
    const jobId = randomUUID();
    const accessToken = newToken();
    await store.create(jobId, accessToken, parsed.data);
    try {
      // Queue data, return values, and failed reasons never contain candidate documents.
      await queue.add("analyze", {}, { jobId, removeOnComplete: true, removeOnFail: { age: 3600, count: 200 } });
    } catch {
      await store.remove(jobId);
      return reply.code(503).send({ error: "The service is temporarily unavailable." });
    }
    return reply.code(202).send({ jobId, accessToken, expiresIn: RETENTION_SECONDS });
  });

  app.get<{ Params: { jobId: string } }>("/analyze/:jobId", async (request, reply) => {
    const id = request.params.jobId;
    if (!validId(id) || !(await store.authorized(id, request.headers.authorization))) {
      return reply.code(404).send({ error: "Analysis unavailable or expired." });
    }
    const result = await store.result(id);
    if (result) return { status: "done", ...result };
    const job = await queue.getJob(id);
    if (!job) return { status: "failed", error: "The analysis did not finish. Try again." };
    const status = mapJobState(await job.getState());
    if (status === "failed" || status === "done") return { status: "failed", error: "The analysis did not finish. Try again." };
    return { status };
  });

  app.delete<{ Params: { jobId: string } }>("/analyze/:jobId", async (request, reply) => {
    const id = request.params.jobId;
    if (!validId(id) || !(await store.authorized(id, request.headers.authorization))) {
      return reply.code(404).send({ error: "Analysis unavailable or expired." });
    }
    await store.remove(id);
    // Active computation may finish, but save() cannot recreate deleted results.
    const job = await queue.getJob(id);
    if (job) await job.remove().catch(() => undefined);
    return reply.code(204).send();
  });
}
