import { UnrecoverableError, type Job } from "bullmq";
import { AnalysisEnvelopeSchema, AnalyzeRequestSchema, type AnalyzeRequest } from "@hirelens/shared";
import type { PrivateStore } from "./privacy.js";

export class TransientInferenceError extends Error {
  constructor() { super("Inference temporarily unavailable"); }
}
export class InvalidDocumentsError extends Error {
  constructor() { super("Documents exceed model limits"); }
}
export function createProcessor(deps: {
  store: PrivateStore;
  infer: (input: AnalyzeRequest) => Promise<unknown>;
  recordCompletion: (id: string) => Promise<unknown>;
  production?: boolean;
}) {
  return async (job: Job) => {
    const id = job.id!;
    let retry = false;
    const started = Date.now();
    try {
      // A retry after a statistics write failed must not invoke the model a second time.
      const existing = await deps.store.result(id);
      if (existing) {
        await deps.recordCompletion(id).catch(() => { throw new TransientInferenceError(); });
        return;
      }
      const input = AnalyzeRequestSchema.parse(await deps.store.input(id));
      const result = AnalysisEnvelopeSchema.parse(await deps.infer(input));
      if (deps.production && result.metadata.backend !== "gguf") throw new Error("Invalid backend");
      if (await deps.store.save(id, result)) {
        await deps.recordCompletion(id).catch(() => { throw new TransientInferenceError(); });
      }
      console.info(JSON.stringify({ event: "analysis_completed", durationMs: Date.now() - started,
        queueWaitMs: started - job.timestamp, grounded: result.metadata.grounded }));
    } catch (error) {
      retry = error instanceof TransientInferenceError && job.attemptsMade + 1 < (job.opts.attempts ?? 1);
      console.warn(JSON.stringify({ event: "analysis_failed", retry, durationMs: Date.now() - started }));
      if (retry) throw new Error("Inference temporarily unavailable");
      // Persist only allowlisted failure text in BullMQ, never upstream exception content.
      throw new UnrecoverableError(error instanceof InvalidDocumentsError ? "Documents exceed model limits" : "Analysis failed");
    } finally {
      if (!retry) {
        // A Redis cleanup failure must not replace the classified job failure.
        await deps.store.clearInput(id).catch(() => console.error("Input cleanup unavailable; TTL applies"));
        await deps.store.release(id).catch(() => console.error("Capacity cleanup unavailable; TTL applies"));
      }
    }
  };
}
