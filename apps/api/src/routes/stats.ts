import type { FastifyInstance } from "fastify";
import { prisma } from "../db.js";
import { summarize } from "../metrics.js";

export const STATS_WINDOW_DAYS = 30;
const MAX_ROWS = 20_000;

/** Anonymous metric rows for the last `days` days, newest first. */
export function recentMetrics(days: number) {
  return prisma.analysis.findMany({
    where: { createdAt: { gte: new Date(Date.now() - days * 86_400_000) } },
    orderBy: { createdAt: "desc" }, take: MAX_ROWS,
    select: { status: true, durationMs: true, queueWaitMs: true, costUsd: true, inputTokens: true, outputTokens: true,
      citationsChecked: true, citationsRemoved: true },
  });
}

export async function statsRoutes(app: FastifyInstance) {
  // Every completed analysis is a row, so this is the real usage number.
  app.get("/stats", async () => {
    const [analyses, lastRun, recent] = await Promise.all([
      prisma.analysis.count({ where: { status: "complete" } }),
      prisma.analysis.findFirst({ where: { status: "complete" }, orderBy: { createdAt: "desc" }, select: { createdAt: true } }),
      recentMetrics(STATS_WINDOW_DAYS),
    ]);
    return { analyses, lastRun: lastRun?.createdAt ?? null,
      last30Days: summarize(recent) };
  });
}
