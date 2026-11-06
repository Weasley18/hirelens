import { config } from "dotenv";
import { fileURLToPath } from "node:url";
import { z } from "zod";

config({ path: fileURLToPath(new URL("../../../.env", import.meta.url)) });
const EnvSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  DATABASE_URL: z.string().min(1),
  REDIS_URL: z.string().url().default("redis://localhost:6379"),
  ML_SERVICE_URL: z.string().url().default("http://localhost:8000"),
  ML_LAMBDA_FUNCTION: z.string().optional(),
  ML_SERVICE_TOKEN: z.string().regex(/^[a-f0-9]{64}$/, "must be a random 32-byte hex token"),
  PORT: z.coerce.number().int().min(1).max(65535).default(3000),
  CORS_ORIGIN: z.string().default("http://localhost:3001"),
  TRUST_PROXY: z.string().default(""),
}).superRefine((env, ctx) => {
  if (env.CORS_ORIGIN.split(",").some(origin => !/^https?:\/\/[^/\s*]+$/.test(origin.trim()))) {
    ctx.addIssue({ code: "custom", path: ["CORS_ORIGIN"], message: "explicit origins required" });
  }
  if (env.NODE_ENV === "production" && !env.ML_LAMBDA_FUNCTION && !env.ML_SERVICE_URL.startsWith("https://")) {
    ctx.addIssue({ code: "custom", path: ["ML_SERVICE_URL"], message: "HTTPS required in production" });
  }
});
const parsed = EnvSchema.safeParse(process.env);
if (!parsed.success) throw new Error(`Invalid configuration: ${parsed.error.issues.map(i => i.path.join(".")).join(", ")}. See .env.example.`);
export const env = parsed.data;
