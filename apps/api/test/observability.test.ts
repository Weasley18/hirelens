import { test } from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { context, propagation, trace } from "@opentelemetry/api";
import { InMemorySpanExporter, SimpleSpanProcessor, TracerProvider } from "@opentelemetry/sdk-trace";
import { W3CTraceContextPropagator } from "@opentelemetry/core";
import { AsyncLocalStorageContextManager } from "@opentelemetry/context-async-hooks";
import { buildApp } from "../src/app.ts";
import { createProcessor, InvalidDocumentsError } from "../src/processor.ts";
import { percentile, summarize, type AnalysisMetrics } from "../src/metrics.ts";
import { traceCarrier } from "../src/tracing.ts";

// Tracing as production sets it up, but exporting to memory (node --test runs each file in its own process).
const exporter = new InMemorySpanExporter();
context.setGlobalContextManager(new AsyncLocalStorageContextManager().enable());
propagation.setGlobalPropagator(new W3CTraceContextPropagator());
trace.setGlobalTracerProvider(new TracerProvider({ spanProcessors: [new SimpleSpanProcessor({ exporter })] }));

const input = { resume: "Backend engineer building Python services with SQL and testing. ".repeat(3), jd: "Seeking a Python engineer for backend services and testing. ".repeat(3) };
const envelope = { result: { fitScore: 50, verdict: "Needs further assessment.", gaps: [], strengths: [{ text: "Python", evidence: "building Python services with SQL" }], interviewQuestions: [
  { question: "Describe a system you built.", targets: "Python", difficulty: "mid" as const },
  { question: "How do you test your systems?", targets: "Testing", difficulty: "mid" as const },
] }, metadata: { backend: "hosted" as const, grounded: true, citations: { checked: 5, removed: 1 } } };
const telemetry = { model: "gpt-6-luna", attempts: 2, inputTokens: 6000, outputTokens: 2400, reasoningTokens: 1400,
  cachedTokens: 0, costUsd: 0.0018, stages: { retrieve: 40, generate: 9000 }, totalMs: 9100 };

function memoryStore(id: string) {
  const saved = new Map<string, unknown>();
  return { saved, store: {
    admit: async () => true, reserve: async () => true, create: async () => undefined, remove: async () => undefined,
    result: async (key: string) => saved.get(key) ?? null, input: async () => input,
    save: async (key: string, value: unknown) => { saved.set(key, value); return key === id; },
    clearPreview: async () => undefined, clearInput: async () => undefined, release: async () => undefined,
  } as any };
}
const job = (id: string, data: Record<string, unknown> = {}) =>
  ({ id, data, attemptsMade: 0, opts: { attempts: 1 }, timestamp: Date.now() - 250 }) as any;

test("percentiles use the nearest rank; error rate ignores rejected documents", () => {
  assert.equal(percentile([], 50), null);
  assert.equal(percentile([1, 2, 3, 4], 50), 2);
  assert.equal(percentile([...Array(100).keys()].map(i => i + 1), 95), 95);
  const row = (status: AnalysisMetrics["status"], durationMs: number | null, costUsd: number | null = null) =>
    ({ status, durationMs, queueWaitMs: 1000, costUsd, inputTokens: 3000, outputTokens: 1000, citationsChecked: 5, citationsRemoved: 0 });
  const summary = summarize([row("complete", 9000, 0.002), row("complete", 19000, 0.004), row("complete", 4000),
    row("failed", 2000), row("rejected", 10)]);
  assert.deepEqual(summary.latencyMs, { p50: 10000, p95: 20000, p99: 20000 });
  assert.equal(summary.errorRate, 0.25);
  assert.equal(summary.costPerAnalysisUsd, 0.003);
  assert.deepEqual(summary.citations, { checked: 15, removed: 0, supportRate: 1 });
});

test("usage is recorded with the anonymous row and never saved with the result", async () => {
  const id = randomUUID();
  const { saved, store } = memoryStore(id);
  const records: [string, AnalysisMetrics | undefined][] = [];
  await createProcessor({ store, infer: async () => ({ ...envelope, telemetry }),
    recordCompletion: async (key, metrics) => { records.push([key, metrics]); } })(job(id));
  assert.deepEqual(saved.get(id), envelope);
  const [[key, metrics]] = records;
  assert.equal(key, id);
  assert.equal(metrics!.status, "complete");
  assert.ok(metrics!.queueWaitMs >= 250 && metrics!.durationMs >= 0);
  assert.deepEqual({ ...metrics, durationMs: 0, queueWaitMs: 0 }, { status: "complete", durationMs: 0, queueWaitMs: 0,
    backend: "hosted", model: "gpt-6-luna", attempts: 2, inputTokens: 6000, outputTokens: 2400, costUsd: 0.0018,
    citationsChecked: 5, citationsRemoved: 1 });
});

test("malformed usage is ignored; failures are recorded as failed or rejected", async () => {
  const id = randomUUID();
  const { saved, store } = memoryStore(id);
  let recorded: AnalysisMetrics | undefined;
  await createProcessor({ store, infer: async () => ({ ...envelope, telemetry: { inputTokens: "lots", note: "resume text" } }),
    recordCompletion: async (_key, metrics) => { recorded = metrics; } })(job(id));
  assert.deepEqual(saved.get(id), envelope);
  assert.equal(recorded!.model, null);
  assert.equal(recorded!.citationsChecked, 5);

  const failures: string[] = [];
  const recordFailure = async (_key: string, metrics: AnalysisMetrics) => { failures.push(metrics.status); };
  for (const infer of [async () => { throw new InvalidDocumentsError(); }, async () => ({ result: "candidate text" })]) {
    await assert.rejects(createProcessor({ store: memoryStore(id).store, infer, recordCompletion: async () => {}, recordFailure })(job(id)));
  }
  assert.deepEqual(failures, ["rejected", "failed"]);
});

test("one trace runs from submission through the queue to the ML request", async () => {
  exporter.reset();
  const added: Record<string, unknown>[] = [];
  const queue = { add: async (_name: string, data: Record<string, unknown>) => { added.push(data); },
    getJob: async () => null, getJobCounts: async () => ({}) } as any;
  const app = await buildApp({ queue, store: memoryStore("x").store }, { origins: [] });
  try {
    const submitted = await app.inject({ method: "POST", url: "/analyze", payload: input });
    assert.equal(submitted.statusCode, 202);
  } finally { await app.close(); }
  const carrier = traceCarrier(added[0].trace);
  assert.ok(carrier?.traceparent);
  assert.deepEqual(Object.keys(added[0]), ["trace"]); // nothing else, and never the documents

  let mlHeaders: Record<string, string> = {};
  const { traceHeaders, inSpan } = await import("../src/tracing.ts");
  const id = randomUUID();
  await createProcessor({ store: memoryStore(id).store, recordCompletion: async () => {},
    infer: () => inSpan("ml.request", {}, async () => { mlHeaders = traceHeaders(); return { ...envelope, telemetry }; }),
  })(job(id, { trace: carrier }));

  const spans = Object.fromEntries(exporter.getFinishedSpans().map(s => [s.name, s]));
  const traceId = spans["analysis.submit"].spanContext().traceId;
  for (const name of ["analysis.process", "ml.request"]) assert.equal(spans[name].spanContext().traceId, traceId);
  assert.equal(spans["analysis.process"].parentSpanContext?.spanId, spans["analysis.submit"].spanContext().spanId);
  assert.equal(spans["ml.request"].parentSpanContext?.spanId, spans["analysis.process"].spanContext().spanId);
  assert.ok(mlHeaders.traceparent.includes(spans["ml.request"].spanContext().spanId));
  assert.equal(spans["analysis.process"].attributes["gen_ai.usage.input_tokens"], 6000);
  assert.equal(spans["analysis.process"].attributes["hirelens.cost_usd"], 0.0018);
  assert.ok(!JSON.stringify(exporter.getFinishedSpans().map(s => s.attributes)).includes("Python services"));
});

test("queue data only yields well-formed trace headers", () => {
  assert.equal(traceCarrier({ traceparent: "not a trace" }), undefined);
  assert.equal(traceCarrier("00-abc"), undefined);
  assert.deepEqual(traceCarrier({ traceparent: "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01", extra: "x" }),
    { traceparent: "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" });
});
