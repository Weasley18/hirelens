import type { FastifyInstance } from "fastify";
import { prisma } from "../db.js";

export async function statsRoutes(app: FastifyInstance) {
  // Every completed analysis is a row, so this is the real usage number.
  app.get("/stats", async () => {
    const [analyses, lastRun] = await Promise.all([
      prisma.analysis.count(),
      prisma.analysis.findFirst({ orderBy: { createdAt: "desc" }, select: { createdAt: true } }),
    ]);

    return { analyses, lastRun: lastRun?.createdAt ?? null };
  });
}
