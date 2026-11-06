import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { AnalyzeRequestSchema, AnalysisResultSchema } from "@hirelens/shared";
import { normalizeAnalysis, mapJobState, ModelOutputError } from "../src/result.ts";

const fixture = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../../packages/shared/fixtures/sample-analysis.json", import.meta.url)),
    "utf8",
  ),
);

const validResume = "Backend engineer with six years building Node services. ".repeat(4);
const validJd = "We are hiring a senior backend engineer to own our payments platform. ".repeat(3);

describe("AnalyzeRequestSchema", () => {
  test("accepts a normal resume and job description", () => {
    const parsed = AnalyzeRequestSchema.safeParse({ resume: validResume, jd: validJd });
    assert.equal(parsed.success, true);
  });

  test("rejects a resume that is too short to analyse", () => {
    const parsed = AnalyzeRequestSchema.safeParse({ resume: "hire me", jd: validJd });
    assert.equal(parsed.success, false);
  });

  test("rejects a document pasted far over the input cap", () => {
    const parsed = AnalyzeRequestSchema.safeParse({ resume: "x".repeat(50_000), jd: validJd });
    assert.equal(parsed.success, false);
  });

  test("rejects a missing job description", () => {
    const parsed = AnalyzeRequestSchema.safeParse({ resume: validResume });
    assert.equal(parsed.success, false);
  });
});

describe("shared schema parity", () => {
  test("the shared fixture satisfies the zod schema", () => {
    const parsed = AnalysisResultSchema.safeParse(fixture);
    assert.equal(parsed.success, true, JSON.stringify(parsed.error?.issues));
  });
});

describe("normalizeAnalysis", () => {
  test("passes through a well-formed analysis", () => {
    const result = normalizeAnalysis(structuredClone(fixture));
    assert.equal(result.fitScore, 74);
    assert.equal(result.gaps.length, 3);
  });

  test("rejects malformed scores and missing evidence rather than repairing claims", () => {
    for (const fitScore of ["82", 104, -10, 81.6]) {
      assert.throws(() => normalizeAnalysis({ ...structuredClone(fixture), fitScore }), ModelOutputError);
    }
    const raw = structuredClone(fixture);
    delete raw.gaps;
    assert.throws(() => normalizeAnalysis(raw), ModelOutputError);
    assert.throws(() => normalizeAnalysis({ ...fixture, unexpected: true }), ModelOutputError);
  });

  test("rejects output missing required content instead of inventing it", () => {
    const raw = structuredClone(fixture);
    delete raw.strengths;
    assert.throws(() => normalizeAnalysis(raw), ModelOutputError);
  });

  test("rejects an unknown severity value", () => {
    const raw = structuredClone(fixture);
    raw.gaps[0].severity = "catastrophic";
    assert.throws(() => normalizeAnalysis(raw), ModelOutputError);
  });

  test("surfaces the inference service's own error payload", () => {
    assert.throws(
      () => normalizeAnalysis({ error: "model produced invalid JSON", raw: "{fitScore:" }),
      /did not match the schema/,
    );
  });

  test("rejects a non-object response", () => {
    assert.throws(() => normalizeAnalysis("not json"), ModelOutputError);
  });
});

describe("mapJobState", () => {
  test("maps BullMQ states to what the frontend polls for", () => {
    assert.equal(mapJobState("completed"), "done");
    assert.equal(mapJobState("failed"), "failed");
    assert.equal(mapJobState("active"), "active");
    assert.equal(mapJobState("waiting"), "queued");
    assert.equal(mapJobState(undefined), "queued");
  });
});
