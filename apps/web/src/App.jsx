import { useState, useRef, useEffect } from "react";
import { RESUME_MIN, RESUME_MAX, JD_MIN, JD_MAX } from "@hirelens/shared";
import Assessment from "@/components/Assessment";
import Icon from "@/components/Icon";
import Lens from "@/components/Lens";
import { AnalysisError, runAnalysis, pollAnalysis, deleteAnalysis } from "@/lib/api";
import { SAMPLE_JD, SAMPLE_RESUME } from "@/lib/sample";
export default function App() {
    const [resume, setResume] = useState("");
    const [jd, setJd] = useState("");
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [waiting, setWaiting] = useState(null);
    const [handle, setHandle] = useState(null);
    const controller = useRef(null);
    useEffect(() => () => controller.current?.abort(), []);
    const [deleting, setDeleting] = useState(false);
    const busy = waiting !== null || deleting;
    async function erase() {
        controller.current?.abort();
        setDeleting(true);
        try {
            if (handle)
                await deleteAnalysis(handle);
            setHandle(null);
            setResult(null);
            setResume("");
            setJd("");
            setWaiting(null);
            setError(null);
        }
        catch {
            setError("Deletion failed. Please try again; automatic expiry still applies.");
        }
        finally {
            setDeleting(false);
        }
    }
    async function analyze(resumeText, jdText) {
        setError(null);
        setResult(null);
        setWaiting("Reading both documents");
        const active = new AbortController();
        controller.current = active;
        try {
            if (handle) {
                await deleteAnalysis(handle);
                setHandle(null);
            }
            const assessment = await runAnalysis(resumeText, jdText, status => setWaiting(status === "queued" ? "Waiting for an available worker" : "Assessing the documents"), setHandle, active.signal);
            if (!active.signal.aborted)
                setResult(assessment);
        }
        catch (err) {
            if (active.signal.aborted)
                return;
            setError(err instanceof AnalysisError
                ? err.message
                : "Something went wrong running that analysis. Try again.");
        }
        finally {
            if (controller.current === active)
                setWaiting(null);
        }
    }
    async function resumePolling() {
        if (!handle || busy)
            return;
        const active = new AbortController();
        controller.current = active;
        setError(null);
        setWaiting("Checking the existing analysis");
        try {
            const assessment = await pollAnalysis(handle, status => setWaiting(status === "queued" ? "Waiting for an available worker" : "Assessing the documents"), active.signal);
            if (!active.signal.aborted)
                setResult(assessment);
        }
        catch (err) {
            if (!active.signal.aborted)
                setError(err instanceof AnalysisError ? err.message : "Could not check the analysis. Try again.");
        }
        finally {
            if (controller.current === active)
                setWaiting(null);
        }
    }
    function loadSample() {
        setResume(SAMPLE_RESUME);
        setJd(SAMPLE_JD);
        void analyze(SAMPLE_RESUME, SAMPLE_JD);
    }
    const resumeReady = resume.trim().length >= RESUME_MIN;
    const jdReady = jd.trim().length >= JD_MIN;
    const inputLocked = busy || handle !== null;
    return (<div className="site-shell">
      <a className="skip-link" href="#workspace">Skip to assessment</a>
      <header className="site-header">
        <a href="#" className="wordmark" aria-label="HireLens home">
          <span className="brand-icon" aria-hidden="true"><span /><span /></span>
          hirelens<span className="brand-period">.</span>
        </a>
        <nav aria-label="Main navigation"><a href="#workspace">Workspace</a><a href="#how-it-works">How it works <span aria-hidden="true">↗</span></a></nav>
        <span className="header-note"><span className="status-dot"/> A clearer perspective</span>
      </header>

      <main>
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy enter">
            <p className="eyebrow"><span className="tiny-cross" aria-hidden="true">+</span> THE HUMAN SIDE OF HIRING</p>
            <h1 id="hero-title">See the fit. <span>Find the signal.</span></h1>
            <p className="hero-description">Two documents. A clearer perspective. Your next great conversation starts here.</p>
          </div>
          <div className="hero-aside">
            <div className="hero-glyph" aria-hidden="true"><span /><span /><span /><span /><span /></div>
            <span className="mono">HUMAN JUDGMENT.<br />A SHARPER LENS.</span>
          </div>
        </section>

        <section className="workspace enter" id="workspace" aria-label="Assessment workspace" style={{ animationDelay: "120ms" }}>
          <div className="input-panel">
            <div className="panel-heading"><div><p className="eyebrow">01 — THE CONTEXT</p><h2>Bring both sides.</h2></div><span className="step-count">{Number(resumeReady) + Number(jdReady)} / 2</span></div>
            <div className="document-field">
              <div className="field-heading"><label htmlFor="resume"><Icon name="file"/> Resume</label><span className={resumeReady ? "field-status ready" : "field-status"}>{resumeReady ? <><Icon name="check"/> Added</> : "CANDIDATE"}</span></div>
              <textarea id="resume" aria-describedby="resume-help" disabled={inputLocked} maxLength={RESUME_MAX} rows={4} value={resume} onChange={event => { setResume(event.target.value); setResult(null); }} placeholder="The experience. The skills. The story.
Paste the candidate’s resume here."/>
              <p id="resume-help" className="field-help"><span>At least {RESUME_MIN} characters</span><span>{resume.trim().length.toLocaleString()} / {RESUME_MAX.toLocaleString()}</span></p>
            </div>
            <div className="document-field">
              <div className="field-heading"><label htmlFor="jd"><Icon name="briefcase"/> Job description</label><span className={jdReady ? "field-status ready" : "field-status"}>{jdReady ? <><Icon name="check"/> Added</> : "OPPORTUNITY"}</span></div>
              <textarea id="jd" aria-describedby="jd-help" disabled={inputLocked} maxLength={JD_MAX} rows={4} value={jd} onChange={event => { setJd(event.target.value); setResult(null); }} placeholder="What does success look like?
Paste the role’s requirements here."/>
              <p id="jd-help" className="field-help"><span>At least {JD_MIN} characters</span><span>{jd.trim().length.toLocaleString()} / {JD_MAX.toLocaleString()}</span></p>
            </div>
            <p className="input-note">Keep it focused. Long documents may exceed the model’s limits.</p>
            <button className="button button-primary" type="button" onClick={() => void analyze(resume, jd)} disabled={busy || !resumeReady || !jdReady}>
              <span>{busy ? "Finding the signal" : "Run analysis"}</span>{busy ? <span className="button-spinner" aria-hidden="true"/> : <Icon name="arrow"/>}
            </button>
            <button className="button button-sample" type="button" onClick={loadSample} disabled={busy}><Icon name="spark"/> Use the sample resume <span aria-hidden="true">↗</span></button>
            {handle && <div className="recovery-actions">
              {!result && !busy && <button className="text-button" type="button" onClick={() => void resumePolling()}><Icon name="refresh"/> Check existing analysis</button>}
              <button className="text-button delete-button" type="button" disabled={deleting} onClick={() => void erase()}><Icon name="close"/> Delete analysis and clear documents</button>
              <p>Delete this analysis to edit the documents. Refreshing this tab loses access.</p>
            </div>}
            <div className="privacy-note"><Icon name="lock"/><p>Private by design. Documents expire within 15 minutes.<br />Results expire within an hour. <a href="#privacy">Your data, explained</a></p></div>
          </div>

          <div className="output-panel" aria-busy={waiting !== null}>
            <div className="output-heading"><p className="eyebrow">02 — THE PERSPECTIVE</p><span className="output-status"><span className={busy ? "status-dot busy-dot" : "status-dot"}/>{result ? "Assessment ready" : busy ? "In progress" : "Ready when you are"}</span></div>
            {error && <div role="alert" className="error-message"><span className="error-symbol" aria-hidden="true">!</span><div><strong>The analysis stopped</strong><p>{error}</p></div></div>}
            {!result && <div className="empty-state">
              <Lens processing={waiting !== null}/>
              {waiting ? <div className="state-copy" role="status" aria-live="polite"><span className="eyebrow">CONNECTING THE DOTS</span><h2>{waiting}</h2><p>Looking for the experience that matters.<br />The first assessment may take a little longer.</p><div className="processing-track" aria-hidden="true"><span /></div></div>
                : <div className="state-copy"><span className="eyebrow">LESS GUESSWORK. MORE CLARITY.</span><h2>There’s a story<br />between the lines.</h2><p>Add a resume and a job description.<br />We’ll help you see how they come together.</p></div>}
              <div className="output-preview">
                <div><Icon name="check"/><strong>Strengths</strong><span>Find the alignment</span></div>
                <div><Icon name="arrow"/><strong>Skill gaps</strong><span>Explore what’s missing</span></div>
                <div><Icon name="spark"/><strong>Questions</strong><span>Go a little deeper</span></div>
              </div>
            </div>}
            {result && <div className="result-container" aria-live="polite">
              {result.metadata.backend === "stub" && <p role="status" className="result-notice"><Icon name="spark"/><span>Demo mode: this is a simulated keyword-based assessment, not an AI model analysis.</span></p>}
              {!result.metadata.grounded && <p className="grounding-note">Reference material was unavailable. Review these claims against the original documents.</p>}
              <Assessment result={result.result}/>
            </div>}
            <div className="output-footer"><span className="mini-brand" aria-hidden="true">h.</span><p>A perspective to inform your judgment.<br />Never a replacement for it.</p><span className="mono">HUMAN FIRST ↗</span></div>
          </div>
        </section>

        <section className="how-section" id="how-it-works" aria-labelledby="how-title">
          <div className="how-heading"><p className="eyebrow">A LITTLE CONTEXT. A LOT OF CLARITY.</p><h2 id="how-title">From documents to dialogue.</h2></div>
          <div className="how-grid">
            <article><span className="how-number">01</span><div><h3>Set the context</h3><p>Bring the candidate’s experience and the role’s requirements into one place.</p></div></article>
            <article><span className="how-number">02</span><div><h3>See the alignment</h3><p>Explore supported strengths and the areas that need a closer look.</p></div></article>
            <article><span className="how-number">03</span><div><h3>Start a better conversation</h3><p>Take thoughtful, role-specific questions into your next interview.</p></div></article>
          </div>
        </section>
        <details className="privacy-details" id="privacy"><summary><Icon name="lock"/> A note on privacy & responsible use <span aria-hidden="true">+</span></summary><div><p>Documents are held temporarily for processing, for up to 15 minutes. Results expire within one hour of submission. You can delete an analysis at any time; processing already in progress may finish, but deleted results cannot be restored.</p><p>Access stays in this tab’s memory. Refreshing or closing it loses access. Assessments need human review and should not determine hiring decisions on their own.</p></div></details>
      </main>
      <footer className="site-footer"><span className="wordmark">hirelens<span className="brand-period">.</span></span><p>See people beyond the paper.</p><span className="mono">CONTEXT OVER KEYWORDS</span></footer>
    </div>);
}
