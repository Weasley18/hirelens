import { useRef, useState } from "react";
import { RESUME_MIN, RESUME_MAX, JD_MIN, JD_MAX } from "@hirelens/shared";
import AnalysisDialog from "@/components/AnalysisDialog";
import DocumentField from "@/components/DocumentField";
import Icon from "@/components/Icon";
import Lens from "@/components/Lens";
import useAnalysisBatch from "@/lib/useAnalysisBatch";
import { SAMPLE_JD, SAMPLE_RESUME } from "@/lib/sample";

const provider = import.meta.env.VITE_INFERENCE_PROVIDER;
const emptyInput = () => ({ mode: "pdf", text: "", files: [] });
function documents(input, name) {
    return input.mode === "text" ? [{ name, text: input.text }] : input.files.map(file => ({ name: file.name, file }));
}

export default function App() {
    const [resume, setResume] = useState(emptyInput);
    const [jd, setJd] = useState(emptyInput);
    const [open, setOpen] = useState(false);
    const [generation, setGeneration] = useState(0);
    const info = useRef(null);
    const batch = useAnalysisBatch();
    const locked = batch.rows.length > 0;
    const candidates = documents(resume, "Pasted resume");
    const role = documents(jd, "Pasted job description")[0];
    const ready = (resume.mode === "text" ? resume.text.trim().length >= RESUME_MIN : candidates.length > 0)
        && (jd.mode === "text" ? jd.text.trim().length >= JD_MIN : Boolean(role));
    function start() {
        batch.start(candidates, role);
        setOpen(true);
    }
    function sample() {
        setResume({ ...emptyInput(), mode: "text", text: SAMPLE_RESUME });
        setJd({ ...emptyInput(), mode: "text", text: SAMPLE_JD });
        batch.start([{ name: "Sample resume", text: SAMPLE_RESUME }], { name: "Sample job description", text: SAMPLE_JD });
        setOpen(true);
    }
    async function clear(keepDocuments = false) {
        if (await batch.clear()) {
            setOpen(false);
            if (!keepDocuments) {
                setResume(emptyInput());
                setJd(emptyInput());
            }
            setGeneration(n => n + 1);
        }
    }
    return <div className="site-shell">
        <a className="skip-link" href="#workspace">Skip to assessment</a>
        <header className="site-header">
            <a className="wordmark" href="#workspace" aria-label="HireLens home"><span className="brand-icon" aria-hidden="true"><span/><span/></span>hirelens<span className="brand-period">.</span></a>
            <button className="text-button" onClick={() => info.current.showModal()}><Icon name="lock"/> Privacy &amp; use</button>
        </header>
        <main className="workspace-page" id="workspace">
            <section className="hero enter"><div className="hero-copy">
                <h1>See the fit. <span>Find the signal.</span></h1>
                <p className="hero-description">Compare one or more resumes with a single job description.</p>
            </div><Lens compact/></section>
            <div className="document-grid enter" key={generation}>
                <DocumentField kind="resume" label="Resumes" multiple min={RESUME_MIN} max={RESUME_MAX} value={resume} onChange={setResume} locked={locked}/>
                <DocumentField kind="jd" label="Job description" min={JD_MIN} max={JD_MAX} value={jd} onChange={setJd} locked={locked}/>
            </div>
            <section className="analysis-bar" aria-label="Analysis controls">
                <div><p className="eyebrow">ANALYSIS QUEUE</p><p>{ready ? `${candidates.length} resume${candidates.length === 1 ? "" : "s"} · 1 job description` : "Add resumes and a job description"}</p></div>
                <button className="button button-primary" disabled={!ready && !locked} onClick={locked ? () => setOpen(true) : start}>
                    <span>{locked ? "View analysis" : "Run analysis"}</span><Icon name="arrow"/>
                </button>
            </section>
            <div className="workspace-foot"><span>Resumes are assessed in selection order.{provider && ` Document text is sent to ${provider}.`}</span>
                <button className="text-button" disabled={locked} onClick={sample}><Icon name="spark"/> Use the sample resume</button></div>
        </main>
        <dialog ref={info} className="info-dialog" aria-labelledby="privacy-title"><div className="dialog-header"><h2 id="privacy-title">Privacy &amp; responsible use</h2>
            <button className="icon-button" aria-label="Close privacy information" onClick={() => info.current.close()}><Icon name="close"/></button></div>
            <p>PDF text is extracted in this browser. The server holds submitted text for up to 15 minutes. Results expire within an hour of submission.</p>
            {provider && <p data-testid="provider-disclosure">The resume and job description text are sent to {provider}’s API for assessment. You can remove contact details before submission.</p>}
            <p>Use the results window to delete the analysis and clear your documents. Access stays in this tab’s memory. Refreshing or closing it loses access.</p>
            <p>Review each assessment against the original documents and use human judgment in hiring decisions.</p>
        </dialog>
        {open && locked && <AnalysisDialog batch={batch} roleName={role?.name} onClose={() => setOpen(false)} onClear={clear}/>}
    </div>;
}
