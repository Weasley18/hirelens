import { z } from "zod";

/**
 * Mirror of analysis.schema.json. That file is canonical (Python reads it directly);
 * this is the TypeScript side. apps/ml-service/tests/test_schema_parity.py validates
 * the shared fixture against the JSON Schema, apps/api/test/analysis.test.ts validates
 * the same fixture against these zod schemas — so drift fails a test on one side or the other.
 */

export const Severity = z.enum(["minor", "moderate", "severe"]);
export const Difficulty = z.enum(["junior", "mid", "senior"]);

export const GapSchema = z.object({
  skill: z.string().min(1).max(60),
  severity: Severity,
  note: z.string().min(10).max(240),
}).strict();

export const InterviewQuestionSchema = z.object({
  question: z.string().min(15).max(400),
  targets: z.string().min(2).max(80),
  difficulty: Difficulty,
}).strict();

export const AnalysisResultSchema = z.object({
  fitScore: z.number().int().min(0).max(100),
  verdict: z.string().min(10).max(240),
  gaps: z.array(GapSchema).max(8),
  strengths: z.array(z.string().min(2).max(120)).min(1).max(8),
  interviewQuestions: z.array(InterviewQuestionSchema).min(2).max(8),
}).strict();

export type Gap = z.infer<typeof GapSchema>;
export type InterviewQuestion = z.infer<typeof InterviewQuestionSchema>;
export type AnalysisResult = z.infer<typeof AnalysisResultSchema>;

/** Input caps exist so a 50,000-word paste is rejected before it reaches the model (Phase 10.2). */
export const RESUME_MIN = 80;
export const RESUME_MAX = 20000;
export const JD_MIN = 60;
export const JD_MAX = 20000;

export const AnalyzeRequestSchema = z.object({
  resume: z.string().trim().min(RESUME_MIN).max(RESUME_MAX).refine(s => !s.includes("<|") && !s.includes("|>")),
  jd: z.string().trim().min(JD_MIN).max(JD_MAX).refine(s => !s.includes("<|") && !s.includes("|>")),
}).strict();

export type AnalyzeRequest = z.infer<typeof AnalyzeRequestSchema>;

/** Job status as the frontend sees it. */
export type JobStatus = "queued" | "active" | "done" | "failed";

export const AnalysisEnvelopeSchema = z.object({
  result: AnalysisResultSchema,
  metadata: z.object({ backend: z.enum(["stub", "gguf"]), grounded: z.boolean() }).strict(),
}).strict();
export type AnalysisEnvelope = z.infer<typeof AnalysisEnvelopeSchema>;
