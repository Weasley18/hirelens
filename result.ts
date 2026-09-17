import { AnalysisResultSchema, type AnalysisResult, type JobStatus } from "@hirelens/shared";

/** Thrown when the ML service returned something we can't show a recruiter. */
export class ModelOutputError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ModelOutputError";
  }
}

/**
 * The model is a 3B model quantized to 4 bits. It is mostly reliable and occasionally not,
 * so nothing downstream trusts its output until it has been through here.
 *
 * Two small coercions are deliberate: a score of "82" or 81.6 is an unambiguous formatting
 * slip, not a wrong answer, so it is repaired rather than rejected. Missing required content
 * is a wrong answer and is rejected.
 */
export function normalizeAnalysis(raw: unknown): AnalysisResult {
  if (raw === null || typeof raw !== "object") {
    throw new ModelOutputError("Model returned a non-object response");
  }

  const obj = raw as Record<string, unknown>;

  if (typeof obj.error === "string") {
    throw new ModelOutputError(obj.error);
  }

  const candidate = { ...obj };

  if (typeof candidate.fitScore === "string" && candidate.fitScore.trim() !== "") {
    const n = Number(candidate.fitScore);
    if (Number.isFinite(n)) candidate.fitScore = n;
  }
  if (typeof candidate.fitScore === "number" && Number.isFinite(candidate.fitScore)) {
    candidate.fitScore = Math.min(100, Math.max(0, Math.round(candidate.fitScore)));
  }
  if (candidate.gaps === undefined || candidate.gaps === null) {
    candidate.gaps = [];
  }

  const parsed = AnalysisResultSchema.safeParse(candidate);
  if (!parsed.success) {
    const where = parsed.error.issues
      .slice(0, 3)
      .map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`)
      .join("; ");
    throw new ModelOutputError(`Model output did not match the schema — ${where}`);
  }

  return parsed.data;
}

/** BullMQ's vocabulary is wider than the frontend needs. */
export function mapJobState(state: string | undefined): JobStatus {
  switch (state) {
    case "completed":
      return "done";
    case "failed":
      return "failed";
    case "active":
      return "active";
    default:
      return "queued";
  }
}
