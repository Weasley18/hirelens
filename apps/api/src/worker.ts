import { InvokeCommand, LambdaClient } from "@aws-sdk/client-lambda";
import { Worker } from "bullmq";
import IORedis from "ioredis";
import { type AnalyzeRequest } from "@hirelens/shared";
import { readInferenceResponse } from "./inference-response.js";
import { env } from "./env.js";
import { prisma } from "./db.js";
import { connection, analysisQueue, ANALYSIS_QUEUE } from "./queue.js";
import { PrivateStore } from "./privacy.js";
import { createProcessor, TransientInferenceError, InvalidDocumentsError } from "./processor.js";

const lambda = new LambdaClient({ maxAttempts: 1 });
const store = new PrivateStore(connection);
const workerConnection = new IORedis(env.REDIS_URL, { maxRetriesPerRequest: null });
workerConnection.on("error", () => console.error("Worker Redis unavailable"));
async function infer(input: AnalyzeRequest, id: string): Promise<unknown> {
    let raw: string;
    if (env.ML_LAMBDA_FUNCTION) {
      // Private IAM invocation avoids both a public model endpoint and gateway timeouts.
      const progress = env.API_DOMAIN ? {
        host: env.API_DOMAIN, jobId: id, token: await store.beginPreview(id),
      } : undefined;
      const event = { hirelensProgress: progress, version: "2.0", routeKey: "POST /infer", rawPath: "/infer", rawQueryString: "",
        headers: { "content-type": "application/json", authorization: `Bearer ${env.ML_SERVICE_TOKEN}` },
        requestContext: { http: { method: "POST", path: "/infer", sourceIp: "127.0.0.1", protocol: "HTTP/1.1" } },
        body: JSON.stringify(input), isBase64Encoded: false };
      const response = await lambda.send(new InvokeCommand({ FunctionName: env.ML_LAMBDA_FUNCTION,
        InvocationType: "RequestResponse", Payload: Buffer.from(JSON.stringify(event)) }),
        { abortSignal: AbortSignal.timeout(env.INFERENCE_TIMEOUT_SECONDS * 1000) }).catch(() => { throw new TransientInferenceError(); });
      if (response.FunctionError || !response.Payload || response.Payload.length > 100_000) throw new Error("Inference failed");
      const payload = JSON.parse(Buffer.from(response.Payload).toString("utf8"));
      if ([429, 500, 503, 504].includes(payload.statusCode)) throw new TransientInferenceError();
      if (payload.statusCode === 422) throw new InvalidDocumentsError();
      if (payload.statusCode !== 200 || payload.isBase64Encoded) throw new Error("Inference failed");
      raw = payload.body;
    } else {
      const response = await fetch(`${env.ML_SERVICE_URL}/infer`, {
        method: "POST", headers: { "Content-Type": "application/json", Accept: "application/x-ndjson", Authorization: `Bearer ${env.ML_SERVICE_TOKEN}` },
        body: JSON.stringify(input), signal: AbortSignal.timeout(env.INFERENCE_TIMEOUT_SECONDS * 1000), redirect: "error",
      }).catch(() => { throw new TransientInferenceError(); });
      if ([429, 500, 503, 504].includes(response.status)) throw new TransientInferenceError();
      if (response.status === 422) throw new InvalidDocumentsError();
      if (!response.ok) throw new Error("Inference failed");
      return readInferenceResponse(response, preview => store.savePreview(id, preview));
    }
    return JSON.parse(raw);
}
const worker = new Worker(ANALYSIS_QUEUE, createProcessor({ store, infer,
  recordCompletion: id => prisma.analysis.upsert({ where: { id }, create: { id }, update: {} }),
  production: env.NODE_ENV === "production",
}), { connection: workerConnection, concurrency: 1 });
const heartbeat = async () => {
  try {
    await connection.set("health:worker", "1", "EX", 30);
    const counts = await analysisQueue.getJobCounts("waiting", "active", "delayed", "failed");
    const [oldest] = await analysisQueue.getJobs(["waiting"], 0, 0, true);
    console.info(JSON.stringify({ event: "worker_health", ...counts,
      oldestWaitingMs: oldest ? Date.now() - oldest.timestamp : 0, rssBytes: process.memoryUsage().rss }));
  } catch { console.error("Worker heartbeat unavailable"); }
};
void heartbeat();
const heartbeatTimer = setInterval(() => void heartbeat(), 10_000);
heartbeatTimer.unref();
worker.on("error", () => console.error("Worker unavailable"));
worker.on("failed", () => console.error("Analysis failed"));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, async () => {
  clearInterval(heartbeatTimer); await worker.close(); workerConnection.disconnect(); await analysisQueue.close(); connection.disconnect(); await prisma.$disconnect();
});
