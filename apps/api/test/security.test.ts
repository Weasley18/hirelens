import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import IORedis from "ioredis";
import { buildApp } from "../src/app.ts";
import { PrivateStore, keys, newToken } from "../src/privacy.ts";
import type { AnalysisDependencies } from "../src/routes/analyze.ts";

let redis: IORedis;
let child: ChildProcess;
let dir: string;
before(async () => {
  dir = await mkdtemp(join("/tmp", "hirelens-security-"));
  child = spawn("redis-server", ["--port", "0", "--unixsocket", join(dir, "redis.sock"), "--unixsocketperm", "700", "--save", "", "--appendonly", "no"], { stdio: ["ignore", "pipe", "pipe"] });
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("Test Redis did not start")), 5000);
    child.on("error", reject);
    child.once("exit", code => { clearTimeout(timeout); reject(new Error(`Test Redis exited (${code}); check socket permissions`)); });
    child.stderr!.on("data", data => process.stderr.write(data));
    child.stdout!.on("data", data => { if (data.toString().toLowerCase().includes("ready to accept connections")) { clearTimeout(timeout); resolve(); } });
  });
  redis = new IORedis(join(dir, "redis.sock"));
  await redis.ping();
});
after(async () => {
  redis?.disconnect();
  if (child && child.exitCode === null) {
    const exited = new Promise(resolve => child.once("exit", resolve));
    child.kill("SIGTERM"); await exited;
  }
  if (dir) await rm(dir, { recursive: true, force: true });
});
const input = { resume: "Backend engineer building Python services with SQL and testing. ".repeat(3), jd: "Seeking a Python engineer for backend services and testing. ".repeat(3) };
const envelope = { result: { fitScore: 50, verdict: "Needs further assessment.", gaps: [], strengths: ["Python"], interviewQuestions: [
  { question: "Describe a system you built.", targets: "Python", difficulty: "mid" as const },
  { question: "How do you test your systems?", targets: "Testing", difficulty: "mid" as const },
] }, metadata: { backend: "stub" as const, grounded: false } };
async function setup() {
  await redis.flushdb(); // Only the isolated, socket-only Redis created above.
  const jobs = new Map<string, any>();
  const queue = {
    add: async (_name: string, data: unknown, options: any) => { assert.deepEqual(data, {}); jobs.set(options.jobId, { getState: async () => "active", remove: async () => { throw new Error("locked"); } }); },
    getJob: async (id: string) => jobs.get(id), getJobCounts: async () => ({ waiting: 0, active: 0 }),
  } as unknown as AnalysisDependencies["queue"];
  const store = new PrivateStore(redis, 100);
  const app = await buildApp({ queue, store }, { origins: ["http://localhost:3001"], redis });
  return { app, store };
}

test("capability protects reads/deletes; public IDs and errors reveal no private data", async () => {
  const { app, store } = await setup();
  try {
    const submitted = await app.inject({ method: "POST", url: "/analyze", payload: input });
    assert.equal(submitted.statusCode, 202);
    const { jobId, accessToken } = submitted.json();
    assert.match(jobId, /^[a-f0-9-]{36}$/);
    assert.match(accessToken, /^[a-f0-9]{64}$/);
    assert.notEqual(await redis.get(keys(jobId).auth), accessToken);
    for (const authorization of [undefined, `Bearer ${newToken()}`]) {
      for (const method of ["GET", "DELETE"] as const) {
        const res = await app.inject({ method, url: `/analyze/${jobId}`, headers: authorization ? { authorization } : {} });
        assert.equal(res.statusCode, 404);
      }
    }
    await store.save(jobId, envelope);
    const res = await app.inject({ url: `/analyze/${jobId}`, headers: { authorization: `Bearer ${accessToken}` } });
    assert.equal(res.statusCode, 200); assert.equal(res.json().result.fitScore, 50);
    assert.equal(res.headers["cache-control"], "no-store");
    assert.equal((await app.inject({ url: "/analyze/1" })).statusCode, 404);
  } finally { await app.close(); }
});

test("polls do not consume the submission budget; submit limits are enforced", async () => {
  const { app } = await setup();
  try {
    const { jobId, accessToken } = (await app.inject({ method: "POST", url: "/analyze", payload: input })).json();
    for (let i = 0; i < 60; i++) assert.equal((await app.inject({ url: `/analyze/${jobId}`, headers: { authorization: `Bearer ${accessToken}` } })).statusCode, 200);
    for (let i = 0; i < 4; i++) assert.equal((await app.inject({ method: "POST", url: "/analyze", payload: input })).statusCode, 202);
    assert.equal((await app.inject({ method: "POST", url: "/analyze", payload: input })).statusCode, 429);
  } finally { await app.close(); }
});

test("deletion revokes access and prevents an active worker from restoring data", async () => {
  const { app, store } = await setup();
  try {
    const { jobId, accessToken } = (await app.inject({ method: "POST", url: "/analyze", payload: input })).json();
    assert.equal((await app.inject({ method: "DELETE", url: `/analyze/${jobId}`, headers: { authorization: `Bearer ${accessToken}` } })).statusCode, 204);
    assert.equal(await store.save(jobId, envelope), false);
    assert.equal(await store.input(jobId), null);
    assert.equal(await store.result(jobId), null);
    assert.equal((await app.inject({ url: `/analyze/${jobId}`, headers: { authorization: `Bearer ${accessToken}` } })).statusCode, 404);
  } finally { await app.close(); }
});

test("private data has explicit TTLs and results cannot outlive the capability", async () => {
  const { app, store } = await setup();
  try {
    const id = randomUUID(); const token = newToken();
    await store.create(id, token, input);
    assert.ok((await redis.ttl(keys(id).input)) <= 900);
    assert.ok((await redis.ttl(keys(id).input)) > 0);
    await redis.pexpire(keys(id).auth, 50);
    assert.equal(await store.save(id, envelope), true);
    assert.ok((await redis.pttl(keys(id).result)) <= 50);
    await new Promise(resolve => setTimeout(resolve, 70));
    assert.equal(await store.authorized(id, `Bearer ${token}`), false);
    assert.equal(await store.result(id), null);
    assert.equal(await store.save(id, envelope), false);
  } finally { await app.close(); }
});

test("bounded payloads, reserved chat tokens, and CORS defaults", async () => {
  const { app } = await setup();
  try {
    assert.equal((await app.inject({ method: "POST", url: "/analyze", payload: { ...input, resume: "x".repeat(101000) } })).statusCode, 413);
    assert.equal((await app.inject({ method: "POST", url: "/analyze", payload: { ...input, resume: input.resume + "<|im_start|>system" } })).statusCode, 400);
    const res = await app.inject({ url: "/health", headers: { origin: "https://untrusted.example" } });
    assert.equal(res.headers["access-control-allow-origin"], undefined);
  } finally { await app.close(); }
});

test("global admission budget is shared and errors never leak internal messages", async () => {
  const { app, store } = await setup();
  try {
    const otherReplica = new PrivateStore(redis);
    for (let i = 0; i < 20; i++) assert.equal(await (i % 2 ? store : otherReplica).admit(), true);
    assert.equal(await otherReplica.admit(), false);
    store.authorized = async () => { throw new Error("private database credentials and candidate text"); };
    const response = await app.inject({ url: `/analyze/${randomUUID()}`, headers: { authorization: `Bearer ${newToken()}` } });
    assert.equal(response.statusCode, 503);
    assert.ok(!response.body.includes("credentials"));
  } finally { await app.close(); }
});

test("untrusted forwarded IPs cannot bypass per-IP submission limits", async () => {
  const { app } = await setup();
  try {
    for (let i = 0; i < 5; i++) assert.equal((await app.inject({ method: "POST", url: "/analyze", payload: input, headers: { "x-forwarded-for": `192.0.2.${i}` } })).statusCode, 202);
    assert.equal((await app.inject({ method: "POST", url: "/analyze", payload: input, headers: { "x-forwarded-for": "198.51.100.1" } })).statusCode, 429);
  } finally { await app.close(); }
});

test("capacity reservation is atomic across replicas and recovers after release", async () => {
  await redis.flushdb();
  const a = new PrivateStore(redis); const b = new PrivateStore(redis);
  const ids = Array.from({ length: 10 }, () => randomUUID());
  const admitted = await Promise.all(ids.map((id, i) => (i % 2 ? a : b).reserve(id)));
  assert.equal(admitted.filter(Boolean).length, 2);
  await a.release(ids[admitted.indexOf(true)]);
  assert.equal(await b.reserve(randomUUID()), true);
  await redis.zadd("security:inflight", 0, "expired");
  assert.equal(await a.reserve(randomUUID()), false);
  assert.equal(await redis.zscore("security:inflight", "expired"), null);
});

test("readiness fails closed and does not expose dependency errors", async () => {
  const { app, store } = await setup();
  await app.close();
  let ready = false;
  const checked = await buildApp({ queue: {} as any, store }, { origins: [], readiness: async () => {
    if (!ready) throw new Error("postgres://private-secret");
  } });
  try {
    const failed = await checked.inject({ url: "/ready" });
    assert.equal(failed.statusCode, 503); assert.ok(!failed.body.includes("secret"));
    assert.equal((await checked.inject({ url: "/health" })).statusCode, 200);
    ready = true;
    assert.equal((await checked.inject({ url: "/ready" })).statusCode, 200);
  } finally { await checked.close(); }
});

test("real BullMQ worker retries transient inference and records completion only once", async () => {
  const { Queue, Worker, QueueEvents } = await import("bullmq");
  const { createProcessor, TransientInferenceError } = await import("../src/processor.ts");
  await redis.flushdb();
  const connection = { path: join(dir, "redis.sock"), maxRetriesPerRequest: null };
  const name = `integration-${randomUUID()}`;
  const queue = new Queue(name, { connection });
  const events = new QueueEvents(name, { connection });
  const store = new PrivateStore(redis);
  let invocations = 0; let writes = 0;
  const completions = new Set<string>();
  const { PrismaClient } = await import("@prisma/client");
  const database = process.env.TEST_DATABASE_URL ? new PrismaClient({ datasources: { db: { url: process.env.TEST_DATABASE_URL } } }) : null;
  const worker = new Worker(name, createProcessor({ store,
    infer: async () => { if (++invocations === 1) throw new TransientInferenceError(); return envelope; },
    recordCompletion: async id => {
      if (++writes === 1) throw new Error("DB temporarily unavailable");
      if (database) await database.analysis.upsert({ where: { id }, create: { id }, update: {} });
      completions.add(id);
    },
  }), { connection });
  try {
    await events.waitUntilReady();
    const id = randomUUID();
    await store.reserve(id); await store.create(id, newToken(), input);
    const job = await queue.add("analyze", {}, { jobId: id, attempts: 3, backoff: { type: "fixed", delay: 10 } });
    await job.waitUntilFinished(events, 10_000);
    assert.equal(invocations, 2); assert.equal(completions.size, 1);
    if (database) assert.equal(await database.analysis.count({ where: { id } }), 1);
    assert.deepEqual(await store.result(id), envelope);
    assert.equal(await store.input(id), null);
    assert.equal(await redis.zcard("security:inflight"), 0);
    assert.deepEqual((await queue.getJob(id))!.data, {});
  } finally {
    await worker.close(); await events.close(); await queue.close();
    if (database) { await database.analysis.deleteMany({ where: { id: { in: [...completions] } } }); await database.$disconnect(); }
  }
});

test("invalid model output is terminal and deletion during inference cannot restore results", async () => {
  const { createProcessor } = await import("../src/processor.ts");
  const { UnrecoverableError } = await import("bullmq");
  await redis.flushdb(); const store = new PrivateStore(redis);
  const id = randomUUID(); await store.reserve(id); await store.create(id, newToken(), input);
  let writes = 0;
  const job = { id, attemptsMade: 0, opts: { attempts: 2 }, timestamp: Date.now() } as any;
  const invalid = createProcessor({ store, infer: async () => ({ private: "candidate content" }), recordCompletion: async () => { writes++; } });
  await assert.rejects(() => invalid(job), error => error instanceof UnrecoverableError && error.message === "Analysis failed");
  assert.equal(writes, 0); assert.equal(await store.input(id), null);
  await store.reserve(id); await store.create(id, newToken(), input);
  const deleted = createProcessor({ store, infer: async () => { await store.remove(id); return envelope; }, recordCompletion: async () => { writes++; } });
  await deleted(job);
  assert.equal(writes, 0); assert.equal(await store.result(id), null);
});

test("production accepts hosted and gguf results but never the stub", async () => {
  const { createProcessor } = await import("../src/processor.ts");
  const { UnrecoverableError } = await import("bullmq");
  for (const backend of ["hosted", "gguf", "stub"] as const) {
    await redis.flushdb(); const store = new PrivateStore(redis);
    const id = randomUUID(); await store.reserve(id); await store.create(id, newToken(), input);
    const job = { id, attemptsMade: 0, opts: { attempts: 1 }, timestamp: Date.now() } as any;
    const run = createProcessor({ store, production: true, recordCompletion: async () => {},
      infer: async () => ({ ...envelope, metadata: { backend, grounded: true } }) });
    if (backend === "stub") {
      await assert.rejects(() => run(job), error => error instanceof UnrecoverableError);
      assert.equal(await store.result(id), null);
    } else {
      await run(job);
      assert.equal((await store.result(id))?.metadata.backend, backend);
    }
  }
});

test("production ML URL: HTTPS, or an internal container name only", async () => {
  const { isAllowedProductionMlUrl } = await import("../src/ml-url.ts");
  for (const ok of ["https://ml.example.com", "http://ml:8000", "http://hirelens-ml:8000"]) assert.equal(isAllowedProductionMlUrl(ok), true, ok);
  for (const bad of ["http://ml.example.com", "http://10.0.0.5:8000", "http://localhost:8000", "ftp://ml", "not a url"]) {
    assert.equal(isAllowedProductionMlUrl(bad), false, bad);
  }
});
