import { InvokeCommand, LambdaClient } from "@aws-sdk/client-lambda";
import { Worker } from "bullmq";
import IORedis from "ioredis";
import { AnalysisEnvelopeSchema, AnalyzeRequestSchema } from "@hirelens/shared";
import { env } from "./env.js";
import { prisma } from "./db.js";
import { connection, ANALYSIS_QUEUE } from "./queue.js";
import { PrivateStore } from "./privacy.js";

const lambda = new LambdaClient({ maxAttempts: 1 });
const store = new PrivateStore(connection);
const workerConnection = new IORedis(env.REDIS_URL, { maxRetriesPerRequest: null });
workerConnection.on("error", () => console.error("Worker Redis unavailable"));
const worker = new Worker(ANALYSIS_QUEUE, async job => {
  const id = job.id!;
  try {
    const input = AnalyzeRequestSchema.parse(await store.input(id));
    let raw: string;
    if (env.ML_LAMBDA_FUNCTION) {
      // Private IAM invocation avoids both a public model endpoint and gateway timeouts.
      const event = { version: "2.0", routeKey: "POST /infer", rawPath: "/infer", rawQueryString: "",
        headers: { "content-type": "application/json", authorization: `Bearer ${env.ML_SERVICE_TOKEN}` },
        requestContext: { http: { method: "POST", path: "/infer", sourceIp: "127.0.0.1", protocol: "HTTP/1.1" } },
        body: JSON.stringify(input), isBase64Encoded: false };
      const response = await lambda.send(new InvokeCommand({ FunctionName: env.ML_LAMBDA_FUNCTION,
        InvocationType: "RequestResponse", Payload: Buffer.from(JSON.stringify(event)) }),
        { abortSignal: AbortSignal.timeout(90_000) });
      if (response.FunctionError || !response.Payload || response.Payload.length > 100_000) throw new Error("Inference failed");
      const payload = JSON.parse(Buffer.from(response.Payload).toString("utf8"));
      if (payload.statusCode !== 200 || payload.isBase64Encoded) throw new Error("Inference failed");
      raw = payload.body;
    } else {
      const response = await fetch(`${env.ML_SERVICE_URL}/infer`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.ML_SERVICE_TOKEN}` },
        body: JSON.stringify(input), signal: AbortSignal.timeout(90_000), redirect: "error",
      });
      if (!response.ok) throw new Error("Inference failed");
      const reader = response.body!.getReader();
      const chunks: Uint8Array[] = []; let size = 0;
      while (true) {
        const { done, value } = await reader.read(); if (done) break;
        size += value.length;
        if (size > 100_000) { await reader.cancel(); throw new Error("Oversized response"); }
        chunks.push(value);
      }
      raw = Buffer.concat(chunks).toString("utf8");
    }
    const result = AnalysisEnvelopeSchema.parse(JSON.parse(raw));
    if (env.NODE_ENV === "production" && result.metadata.backend !== "gguf") throw new Error("Unexpected backend");
    if (await store.save(id, result)) {
      // Only an anonymous completion count is persisted, never candidate content.
      await prisma.analysis.upsert({ where: { id }, create: { id }, update: {} });
    }
  } catch {
    // BullMQ persists failure messages. Never put upstream errors or inputs in them.
    throw new Error("Analysis failed");
  } finally { await store.clearInput(id); }
}, { connection: workerConnection, concurrency: 1 });
worker.on("error", () => console.error("Worker unavailable"));
worker.on("failed", () => console.error("Analysis failed"));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, async () => {
  await worker.close(); workerConnection.disconnect(); connection.disconnect(); await prisma.$disconnect();
});
