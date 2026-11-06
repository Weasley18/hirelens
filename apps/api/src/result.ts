import { AnalysisResultSchema, type AnalysisResult, type JobStatus } from "@hirelens/shared";

/** Thrown when the ML service returned something we can't show a recruiter. */
export class ModelOutputError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ModelOutputError";
  }
}

/** Reject malformed model claims instead of inventing scores or missing evidence. */
export function normalizeAnalysis(raw: unknown): AnalysisResult {
  const parsed = AnalysisResultSchema.safeParse(raw);
  if (!parsed.success) throw new ModelOutputError("Model output did not match the schema");
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
