import { UnrecoverableError, type Job } from "bullmq";
import type { Span } from "@opentelemetry/api";
import { AnalysisEnvelopeSchema, AnalyzeRequestSchema, InferenceTelemetrySchema, PRODUCTION_BACKENDS, type AnalyzeRequest } from "@hirelens/shared";
import type { PrivateStore } from "./privacy.js";
import { completionMetrics, type AnalysisMetrics } from "./metrics.js";
import { inSpan, traceCarrier } from "./tracing.js";

export class TransientInferenceError extends Error {
  constructor() { super("Inference temporarily unavailable"); }
}
export class InvalidDocumentsError extends Error {
  constructor() { super("Documents exceed model limits"); }
}
export function createProcessor(deps: {
  store: PrivateStore;
  infer: (input: AnalyzeRequest, jobId: string) => Promise<unknown>;
  recordCompletion: (id: string, metrics?: AnalysisMetrics) => Promise<unknown>;
  /** Anonymous failure row for error rates. Best effort: it never changes the job's outcome. */
  recordFailure?: (id: string, metrics: AnalysisMetrics) => Promise<unknown>;
  production?: boolean;
}) {
  return async (job: Job) => {
    const started = Date.now();
    const queueWaitMs = Math.max(0, started - job.timestamp);
    return inSpan("analysis.process", { "hirelens.job.attempt": job.attemptsMade + 1, "hirelens.queue_wait_ms": queueWaitMs },
      span => run(job, started, queueWaitMs, span), traceCarrier(job.data?.trace));
  };

  async function run(job: Job, started: number, queueWaitMs: number, span: Span) {
    const id = job.id!;
    let retry = false;
    try {
      // A retry after a statistics write failed must not invoke the model a second time.
      const existing = await deps.store.result(id);
      if (existing) {
        await deps.recordCompletion(id).catch(() => { throw new TransientInferenceError(); });
        return;
      }
      const input = AnalyzeRequestSchema.parse(await deps.store.input(id));
      const { telemetry, ...envelope } = (await deps.infer(input, id) ?? {}) as Record<string, unknown>;
      // Usage is reported beside the envelope; it is recorded, never saved with the result.
      const result = AnalysisEnvelopeSchema.parse(envelope);
      const usage = InferenceTelemetrySchema.safeParse(telemetry).data;
      if (deps.production && !PRODUCTION_BACKENDS.includes(result.metadata.backend)) throw new Error("Invalid backend");
      const metrics = completionMetrics(result, usage, { durationMs: Date.now() - started, queueWaitMs });
      span.setAttributes({ "hirelens.backend": result.metadata.backend, "gen_ai.request.model": metrics.model ?? "",
        "gen_ai.usage.input_tokens": metrics.inputTokens ?? 0, "gen_ai.usage.output_tokens": metrics.outputTokens ?? 0,
        "hirelens.cost_usd": metrics.costUsd ?? 0, "hirelens.citations.removed": metrics.citationsRemoved ?? 0 });
      if (await deps.store.save(id, result)) {
        await deps.recordCompletion(id, metrics).catch(() => { throw new TransientInferenceError(); });
      }
      console.info(JSON.stringify({ event: "analysis_completed", durationMs: metrics.durationMs, queueWaitMs,
        grounded: result.metadata.grounded, model: metrics.model, attempts: metrics.attempts,
        inputTokens: metrics.inputTokens, outputTokens: metrics.outputTokens, costUsd: metrics.costUsd,
        citationsRemoved: metrics.citationsRemoved }));
    } catch (error) {
      retry = error instanceof TransientInferenceError && job.attemptsMade + 1 < (job.opts.attempts ?? 1);
      console.warn(JSON.stringify({ event: "analysis_failed", retry, durationMs: Date.now() - started }));
      if (retry) throw new Error("Inference temporarily unavailable");
      await deps.recordFailure?.(id, { status: error instanceof InvalidDocumentsError ? "rejected" : "failed",
        durationMs: Date.now() - started, queueWaitMs }).catch(() => console.error("Failure metrics unavailable"));
      // Persist only allowlisted failure text in BullMQ, never upstream exception content.
      throw new UnrecoverableError(error instanceof InvalidDocumentsError ? "Documents exceed model limits" : "Analysis failed");
    } finally {
      await deps.store.clearPreview(id).catch(() => console.error("Preview cleanup unavailable; TTL applies"));
      if (!retry) {
        // A Redis cleanup failure must not replace the classified job failure.
        await deps.store.clearInput(id).catch(() => console.error("Input cleanup unavailable; TTL applies"));
        await deps.store.release(id).catch(() => console.error("Capacity cleanup unavailable; TTL applies"));
      }
    }
  }
}
