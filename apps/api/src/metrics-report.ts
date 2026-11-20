/**
 * Latency, cost and quality over recent analyses, from the anonymous Analysis rows.
 *
 *   npm run metrics --workspace apps/api              # last 7 days
 *   npm run metrics --workspace apps/api -- --days 30 --json
 */
import { prisma } from "./db.js";
import { summarize } from "./metrics.js";
import { recentMetrics } from "./routes/stats.js";

const args = process.argv.slice(2);
const days = Number(args[args.indexOf("--days") + 1]) || 7;
try {
  const summary = summarize(await recentMetrics(days));
  if (args.includes("--json")) {
    console.log(JSON.stringify({ days, ...summary }, null, 2));
  } else {
    const ms = (value: number | null) => value === null ? "—" : `${(value / 1000).toFixed(1)}s`;
    const pct = (value: number | null) => value === null ? "—" : `${(value * 100).toFixed(1)}%`;
    console.log(`Last ${days} days: ${summary.analyses} analyses, ${summary.failed} failed (error rate ${pct(summary.errorRate)})`);
    console.log(`Latency (queue + processing): p50 ${ms(summary.latencyMs.p50)}  p95 ${ms(summary.latencyMs.p95)}  p99 ${ms(summary.latencyMs.p99)}`);
    console.log(`Processing only:              p50 ${ms(summary.processingMs.p50)}  p95 ${ms(summary.processingMs.p95)}`);
    console.log(`Cost per analysis: ${summary.costPerAnalysisUsd === null ? "—" : `$${summary.costPerAnalysisUsd.toFixed(5)}`}` +
      `  (${summary.tokensPerAnalysis.input ?? "—"} input / ${summary.tokensPerAnalysis.output ?? "—"} output tokens on average)`);
    console.log(`Claims backed by a quote: ${pct(summary.citations.supportRate)} (${summary.citations.removed} of ${summary.citations.checked} removed)`);
  }
} finally {
  await prisma.$disconnect();
}
