"use client";

import { useState, useRef, useEffect } from "react";
import { RESUME_MIN, RESUME_MAX, JD_MIN, JD_MAX, type AnalysisEnvelope } from "@hirelens/shared";
import Assessment from "@/components/Assessment";
import { AnalysisError, runAnalysis, deleteAnalysis, type AnalysisHandle } from "@/lib/api";
import { SAMPLE_JD, SAMPLE_RESUME } from "@/lib/sample";

export default function Home() {
  const [resume, setResume] = useState("");
  const [jd, setJd] = useState("");
  const [result, setResult] = useState<AnalysisEnvelope | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState<string | null>(null);

  const [handle, setHandle] = useState<AnalysisHandle | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const busy = waiting !== null;

  async function erase() {
    controller.current?.abort();
    try {
      if (handle) await deleteAnalysis(handle);
      setHandle(null); setResult(null); setResume(""); setJd(""); setWaiting(null); setError(null);
    } catch { setError("Deletion failed. Please try again; automatic expiry still applies."); }
  }

  async function analyze(resumeText: string, jdText: string) {
    setError(null);
    setResult(null);
    setWaiting("Reading both documents");

    controller.current = new AbortController();
    try {
      if (handle) { await deleteAnalysis(handle); setHandle(null); }
      setResult(await runAnalysis(resumeText, jdText,
        status => setWaiting(status === "queued" ? "Waiting for an available worker" : "Assessing the documents"),
        setHandle, controller.current.signal));
    } catch (err) {
      setError(
        err instanceof AnalysisError
          ? err.message
          : "Something went wrong running that analysis. Try again.",
      );
    } finally {
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
            disabled={busy}
            maxLength={RESUME_MAX}
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
            disabled={busy}
            maxLength={JD_MAX}
            rows={10}
            value={jd}
            onChange={(event) => setJd(event.target.value)}
            placeholder="Paste the job description"
            className="mt-2"
          />

          <p className="mt-3 font-ui text-xs text-ink-soft">
            Documents are held temporarily for processing (up to 15 minutes). Results expire within one hour.
            Nothing is saved to your account. You can delete this analysis below.
            Assessments need human review and should not determine hiring decisions on their own.
          </p>
          {handle && <button type="button" onClick={() => void erase()} className="mt-3 border border-rule px-4 py-2">Delete analysis and clear documents</button>}
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void analyze(resume, jd)}
              disabled={busy || resume.trim().length < RESUME_MIN || jd.trim().length < JD_MIN}
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

          {result && <div aria-live="polite">
            {result.metadata.backend === "stub" && <p role="status" className="mb-6 border-l-2 border-flag pl-4">Demo mode: this is a simulated keyword-based assessment, not an AI model analysis.</p>}
            {!result.metadata.grounded && <p className="mb-4 text-ink-soft">Reference material was unavailable. Review these claims against the original documents.</p>}
            <Assessment result={result.result} />
          </div>}
        </div>
      </div>
    </main>
  );
}
