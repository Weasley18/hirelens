import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import type IORedis from "ioredis";
import type { AnalyzeRequest, AnalysisEnvelope } from "@hirelens/shared";

export const RETENTION_SECONDS = 3600;
export const INPUT_RETENTION_SECONDS = 900;
export const tokenHash = (token: string) => createHash("sha256").update(token).digest("hex");
export const newToken = () => randomBytes(32).toString("hex");
export const keys = (id: string) => ({ auth: `private:${id}:auth`, input: `private:${id}:input`, result: `private:${id}:result` });

export class PrivateStore {
  constructor(private redis: IORedis) {}
  async create(id: string, token: string, input: AnalyzeRequest) {
    const k = keys(id);
    // All private data has an actual Redis TTL, independent of BullMQ's lazy cleanup.
    await this.redis.eval(`
      redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
      redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[4])
      return 1`, 2, k.auth, k.input, tokenHash(token), JSON.stringify(input), RETENTION_SECONDS, INPUT_RETENTION_SECONDS);
  }
  async authorized(id: string, authorization?: string) {
    if (!authorization || !/^Bearer [a-f0-9]{64}$/.test(authorization)) return false;
    const expected = await this.redis.get(keys(id).auth);
    if (!expected || !/^[a-f0-9]{64}$/.test(expected)) return false;
    return timingSafeEqual(Buffer.from(expected, "hex"), Buffer.from(tokenHash(authorization.slice(7)), "hex"));
  }
  async input(id: string): Promise<AnalyzeRequest | null> {
    const raw = await this.redis.get(keys(id).input);
    return raw ? JSON.parse(raw) : null;
  }
  async clearInput(id: string) { await this.redis.del(keys(id).input); }
  async save(id: string, result: AnalysisEnvelope) {
    const k = keys(id);
    // An expired or deleted capability must never be resurrected by an in-flight worker.
    return Number(await this.redis.eval(`
      local ttl = redis.call('PTTL', KEYS[1])
      if ttl <= 0 then return 0 end
      redis.call('SET', KEYS[2], ARGV[1], 'PX', ttl)
      return 1`, 2, k.auth, k.result, JSON.stringify(result))) === 1;
  }
  async result(id: string): Promise<AnalysisEnvelope | null> {
    const raw = await this.redis.get(keys(id).result);
    return raw ? JSON.parse(raw) : null;
  }
  async remove(id: string) { await this.redis.del(...Object.values(keys(id))); }
  async admit() {
    // Shared across API replicas; limits aggregate spend, not just one IP.
    return Number(await this.redis.eval(`
      local n = redis.call('INCR', KEYS[1])
      if n == 1 then redis.call('EXPIRE', KEYS[1], 60) end
      return n`, 1, "security:submission-budget")) <= 20;
  }
}
