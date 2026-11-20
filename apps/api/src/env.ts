import { config } from "dotenv";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import { isAllowedProductionMlUrl } from "./ml-url.js";

config({ path: fileURLToPath(new URL("../../../.env", import.meta.url)) });
const EnvSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  DATABASE_URL: z.string().min(1),
  REDIS_URL: z.string().url().default("redis://localhost:6379"),
  ML_SERVICE_URL: z.string().url().default("http://localhost:8000"),
  API_DOMAIN: z.string().regex(/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/i).optional(),
  ML_LAMBDA_FUNCTION: z.string().optional(),
  ML_SERVICE_TOKEN: z.string().regex(/^[a-f0-9]{64}$/, "must be a random 32-byte hex token"),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  CORS_ORIGIN: z.string().default("http://localhost:3001"),
  TRUST_PROXY: z.string().default(""),
  // Two queued jobs x two attempts x this timeout must fit the browser's ten-minute polling window.
  INFERENCE_TIMEOUT_SECONDS: z.coerce.number().int().min(10).max(140).default(90),
}).superRefine((env, ctx) => {
  if (env.CORS_ORIGIN.split(",").some(origin => !/^https?:\/\/[^/\s*]+$/.test(origin.trim()))) {
    ctx.addIssue({ code: "custom", path: ["CORS_ORIGIN"], message: "explicit origins required" });
  }
  if (env.NODE_ENV === "production" && !env.ML_LAMBDA_FUNCTION && !isAllowedProductionMlUrl(env.ML_SERVICE_URL)) {
    ctx.addIssue({ code: "custom", path: ["ML_SERVICE_URL"], message: "HTTPS or an internal service name required in production" });
  }
});
const parsed = EnvSchema.safeParse(process.env);
if (!parsed.success) throw new Error(`Invalid configuration: ${parsed.error.issues.map(i => i.path.join(".")).join(", ")}. See .env.example.`);
export const env = parsed.data;
