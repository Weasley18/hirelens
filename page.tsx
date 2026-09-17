"use client";

import { useState } from "react";
import type { AnalysisResult } from "@hirelens/shared";
import Assessment from "@/components/Assessment";
import { AnalysisError, runAnalysis } from "@/lib/api";
import { SAMPLE_JD, SAMPLE_RESUME } from "@/lib/sample";

export default function Home() {
  const [resume, setResume] = useState("");
  const [jd, setJd] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState<string | null>(null);

  const busy = waiting !== null;

  async function analyze(resumeText: string, jdText: string) {
    setError(null);
    setResult(null);
    setWaiting("Reading both documents");

    // The model is on Lambda and may be cold. Saying so is better than a silent spinner.
    const slowNotice = setTimeout(
      () => setWaiting("Waking the model up — this takes about 15 seconds after a quiet period"),
      6000,
    );

    try {
      setResult(await runAnalysis(resumeText, jdText));
    } catch (err) {
      setError(
        err instanceof AnalysisError
          ? err.message
          : "Something went wrong running that analysis. Try again.",
      );
    } finally {
      clearTimeout(slowNotice);
      setWaiting(null);
    }
  }

  function loadSample() {
    setResume(SAMPLE_RESUME);
    setJd(SAMPLE_JD);
    void analyze(SAMPLE_RESUME, SAMPLE_JD);
  }

  return (
    <main className="mx-auto max-w-[1180px] px-6 py-12 lg:px-10">
      <header className="border-b border-rule pb-6">
        <h1 className="font-document text-2xl">HireLens</h1>
        <p className="measure mt-2 text-ink-soft">
          Put a resume next to a job description and get back what a good recruiter would
          write on the scorecard: where it fits, where it does not, and what to ask about it.
        </p>
      </header>

      <div className="mt-10 grid gap-12 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)] lg:gap-16">
        <div>
          <label className="block font-ui text-sm font-semibold" htmlFor="resume">
            Resume
          </label>
          <textarea
            id="resume"
            rows={12}
            value={resume}
            onChange={(event) => setResume(event.target.value)}
            placeholder="Paste the candidate's resume"
            className="mt-2"
          />

          <label className="mt-6 block font-ui text-sm font-semibold" htmlFor="jd">
            Job description
          </label>
          <textarea
            id="jd"
            rows={10}
            value={jd}
            onChange={(event) => setJd(event.target.value)}
            placeholder="Paste the job description"
            className="mt-2"
          />

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void analyze(resume, jd)}
              disabled={busy || resume.trim().length < 80 || jd.trim().length < 60}
              className="bg-ink px-5 py-2.5 font-ui text-sm text-paper disabled:opacity-40"
            >
              {busy ? "Working" : "Run analysis"}
            </button>
            <button
              type="button"
              onClick={loadSample}
              disabled={busy}
              className="border border-rule px-5 py-2.5 font-ui text-sm disabled:opacity-40"
            >
              Use the sample resume
            </button>
          </div>

          {waiting && (
            <p aria-live="polite" className="mt-4 font-ui text-sm text-ink-soft">
              {waiting}
            </p>
          )}
        </div>

        <div className="lg:border-l lg:border-rule lg:pl-16">
          {error && (
            <div role="alert" className="border-l-2 border-flag pl-4">
              <p className="font-ui text-sm font-semibold text-flag">The analysis stopped</p>
              <p className="measure mt-1 text-ink-soft">{error}</p>
            </div>
          )}

          {!error && !result && !busy && (
            <div className="measure text-ink-soft">
              <p>
                Nothing assessed yet. Paste two documents on the left, or load the sample to
                see a finished scorecard in one click.
              </p>
              <p className="mt-4 font-ui text-sm">
                The model runs on demand rather than on an always-on server, so the first
                analysis after a quiet period is slower than the ones after it.
              </p>
            </div>
          )}

          {result && <Assessment result={result} />}
        </div>
      </div>
    </main>
  );
}
