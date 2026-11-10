/** Run with all old API/worker instances stopped, before deploying the private queue. */
import { Queue } from "bullmq";
import IORedis from "ioredis";
import { config } from "dotenv";
import { fileURLToPath } from "node:url";
config({ path: fileURLToPath(new URL("../../../.env", import.meta.url)) });
const redis = new IORedis(process.env.REDIS_URL ?? "redis://localhost:6379", { maxRetriesPerRequest: 1 });
redis.on("error", () => console.error("Redis unavailable"));
const legacy = new Queue("analysis", { connection: redis });
try {
  // Deliberately scoped to the legacy queue; never FLUSHDB/FLUSHALL.
  await legacy.obliterate({ force: false });
  console.log("Legacy analysis queue and its private payloads removed.");
} catch {
  console.error("Cleanup failed. Stop all legacy workers, resolve active jobs, and retry.");
  process.exitCode = 1;
} finally { await legacy.close(); redis.disconnect(); }
