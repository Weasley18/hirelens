import Fastify from "fastify";
import cors from "@fastify/cors";
import rateLimit from "@fastify/rate-limit";
import type IORedis from "ioredis";
import { analyzeRoutes, type AnalysisDependencies } from "./routes/analyze.js";

export async function buildApp(deps: AnalysisDependencies, options: { origins: string[]; redis?: IORedis; trustProxy?: string[]; production?: boolean }) {
  const app = Fastify({
    logger: { redact: ["req.headers.authorization", "req.headers.cookie", "res.headers.set-cookie"] },
    logController: { disableRequestLogging: true }, bodyLimit: 100_000,
    trustProxy: options.trustProxy?.length ? options.trustProxy : false,
  });
  await app.register(cors, { origin: options.origins, methods: ["GET", "POST", "DELETE"], allowedHeaders: ["Content-Type", "Authorization"] });
  await app.register(rateLimit, {
    max: 120, timeWindow: "1 minute", redis: options.redis, skipOnError: false,
    errorResponseBuilder: () => ({ statusCode: 429, error: "Too many requests. Wait a minute and try again." }),
  });
  app.addHook("onSend", async (_request, reply) => {
    reply.header("Cache-Control", "no-store");
    reply.header("X-Content-Type-Options", "nosniff");
    reply.header("Referrer-Policy", "no-referrer");
    if (options.production) reply.header("Strict-Transport-Security", "max-age=31536000");
  });
  app.setErrorHandler((error, _request, reply) => {
    // Validation/model/database exceptions may embed document text or connection secrets.
    const code = (error as { statusCode?: number }).statusCode;
    const status = code && code >= 400 && code < 500 ? code : 503;
    reply.code(status).send({ error: status === 413 ? "Documents are too large." : "Request could not be completed." });
  });
  app.get("/health", async () => ({ status: "ok" }));
  await app.register(analyzeRoutes, deps);
  return app;
}
