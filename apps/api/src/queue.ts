import { Queue } from "bullmq";
import IORedis from "ioredis";
import { env } from "./env.js";

// Producers fail quickly; only the blocking worker uses unlimited Redis retries.
export const connection = new IORedis(env.REDIS_URL, {
  maxRetriesPerRequest: 1, enableOfflineQueue: false, connectTimeout: 5000, commandTimeout: 5000,
});
connection.on("error", () => console.error("Redis unavailable"));
export const ANALYSIS_QUEUE = "analysis-private-v2";
export const analysisQueue = new Queue(ANALYSIS_QUEUE, { connection });
