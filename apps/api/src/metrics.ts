/**
 * Anonymous per-analysis metrics: latency, queue wait, tokens, cost and citation counts.
 * Rows hold no document content; they are what /stats and `npm run metrics` summarise.
 */
import type { AnalysisEnvelope, InferenceTelemetry } from "@hirelens/shared";

export type AnalysisStatus = "complete" | "failed" | "rejected";
export interface AnalysisMetrics {
  status: AnalysisStatus;
  durationMs: number;
  queueWaitMs: number;
  backend?: string | null;
  model?: string | null;
  attempts?: number | null;
  inputTokens?: number | null;
  outputTokens?: number | null;
  costUsd?: number | null;
  citationsChecked?: number | null;
  citationsRemoved?: number | null;
}

export function completionMetrics(envelope: AnalysisEnvelope, telemetry: InferenceTelemetry | undefined,
  timing: { durationMs: number; queueWaitMs: number }): AnalysisMetrics {
  return { status: "complete", ...timing, backend: envelope.metadata.backend, model: telemetry?.model ?? null,
    attempts: telemetry?.attempts ?? null, inputTokens: telemetry?.inputTokens ?? null, outputTokens: telemetry?.outputTokens ?? null,
    costUsd: telemetry?.costUsd ?? null, citationsChecked: envelope.metadata.citations.checked,
    citationsRemoved: envelope.metadata.citations.removed };
}

/** A stored row, as the database returns it. */
export interface MetricRow {
  status: string;
  durationMs: number | null;
  queueWaitMs: number | null;
  costUsd: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  citationsChecked: number | null;
  citationsRemoved: number | null;
}

/** Nearest-rank percentile of an ascending list. */
export function percentile(sorted: number[], p: number) {
  if (!sorted.length) return null;
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1))];
}

const mean = (values: number[]) => values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
const round = (value: number | null, digits = 0) => value === null ? null : Number(value.toFixed(digits));

export function summarize(rows: MetricRow[]) {
  const complete = rows.filter(r => r.status === "complete");
  const failed = rows.filter(r => r.status === "failed").length;
  // End to end, as a user waits: time in the queue plus processing.
  const latency = complete.filter(r => r.durationMs !== null)
    .map(r => r.durationMs! + (r.queueWaitMs ?? 0)).sort((a, b) => a - b);
  const processing = complete.flatMap(r => r.durationMs === null ? [] : [r.durationMs]).sort((a, b) => a - b);
  const costs = complete.flatMap(r => r.costUsd === null ? [] : [r.costUsd]);
  const checked = complete.reduce((n, r) => n + (r.citationsChecked ?? 0), 0);
  const removed = complete.reduce((n, r) => n + (r.citationsRemoved ?? 0), 0);
  return {
    analyses: complete.length,
    failed,
    // "rejected" (documents over the model's limits) is the caller's error, not the service's.
    errorRate: round(complete.length + failed ? failed / (complete.length + failed) : null, 4),
    latencyMs: { p50: percentile(latency, 50), p95: percentile(latency, 95), p99: percentile(latency, 99) },
    processingMs: { p50: percentile(processing, 50), p95: percentile(processing, 95) },
    costPerAnalysisUsd: round(mean(costs), 6),
    tokensPerAnalysis: {
      input: round(mean(complete.flatMap(r => r.inputTokens ? [r.inputTokens] : []))),
      output: round(mean(complete.flatMap(r => r.outputTokens ? [r.outputTokens] : []))),
    },
    citations: { checked, removed, supportRate: round(checked ? (checked - removed) / checked : null, 4) },
  };
}
export type MetricsSummary = ReturnType<typeof summarize>;
