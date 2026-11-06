import { env } from "./env.js";
import { buildApp } from "./app.js";
import { connection, analysisQueue } from "./queue.js";
import { PrivateStore } from "./privacy.js";
import { statsRoutes } from "./routes/stats.js";
import { prisma } from "./db.js";

const app = await buildApp({ queue: analysisQueue, store: new PrivateStore(connection) }, {
  origins: env.CORS_ORIGIN.split(",").map(s => s.trim()), redis: connection,
  trustProxy: env.TRUST_PROXY.split(",").map(s => s.trim()).filter(Boolean), production: env.NODE_ENV === "production",
});
await app.register(statsRoutes);
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, async () => {
  await app.close(); await analysisQueue.close(); connection.disconnect(); await prisma.$disconnect();
});
try { await app.listen({ port: env.PORT, host: "0.0.0.0" }); }
catch { console.error("API startup failed"); process.exit(1); }
