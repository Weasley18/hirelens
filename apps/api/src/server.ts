import { env } from "./env.js";
import { buildApp } from "./app.js";
import { connection, analysisQueue } from "./queue.js";
import { PrivateStore } from "./privacy.js";
import { statsRoutes } from "./routes/stats.js";
import { prisma } from "./db.js";
import { createPdfRenderer } from "./report/pdf.js";
import { startTracing, stopTracing } from "./tracing.js";

await startTracing("hirelens-api");

const renderPdf = env.CHROMIUM_PATH ? createPdfRenderer({ executablePath: env.CHROMIUM_PATH }) : undefined;
const app = await buildApp({ queue: analysisQueue, store: new PrivateStore(connection), renderPdf }, {
  origins: env.CORS_ORIGIN.split(",").map(s => s.trim()), redis: connection,
  trustProxy: env.TRUST_PROXY.split(",").map(s => s.trim()).filter(Boolean), production: env.NODE_ENV === "production",
  readiness: async () => {
    const [heartbeat] = await Promise.all([connection.get("health:worker"),
      prisma.$queryRaw`SELECT 1`.then(() => undefined)]);
    if (!heartbeat) throw new Error("Worker unavailable");
  },
});
await app.register(statsRoutes);
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, async () => {
  await app.close(); await renderPdf?.close(); await analysisQueue.close(); connection.disconnect(); await prisma.$disconnect(); await stopTracing();
});
try { await app.listen({ port: env.PORT, host: "0.0.0.0" }); }
catch { console.error("API startup failed"); process.exit(1); }
