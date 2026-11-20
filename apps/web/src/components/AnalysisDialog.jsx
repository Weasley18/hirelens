import { useEffect, useRef, useState } from "react";
import Assessment from "./Assessment";
import Lens from "./Lens";
import Icon from "./Icon";
import { downloadReport } from "@/lib/report";

export default function AnalysisDialog({ batch, roleName, onClose, onClear }) {
    const { rows, busy, deleting, deleteError } = batch;
    const [selected, setSelected] = useState(null);
    const [preparing, setPreparing] = useState(null);
    const dialog = useRef(null);
    const tabs = useRef([]);
    const processing = rows.findIndex(row => !["Complete", "Failed", "Deleted", "Pending"].includes(row.status));
    const pending = rows.findIndex(row => row.status === "Pending");
    const index = selected ?? (processing >= 0 ? processing : pending >= 0 ? pending : rows.length - 1);
    const row = rows[index];
    useEffect(() => {
        const element = dialog.current;
        element.showModal();
        return () => element.close();
    }, []);
    useEffect(() => { tabs.current[index]?.scrollIntoView({ block: "nearest", inline: "nearest" }); }, [index]);
    function changeTab(next) {
        setSelected(next);
        tabs.current[next]?.focus();
    }
    function tabKey(e) {
        const keys = { ArrowRight: (index + 1) % rows.length, ArrowLeft: (index + rows.length - 1) % rows.length, Home: 0, End: rows.length - 1 };
        if (Object.hasOwn(keys, e.key)) { e.preventDefault(); changeTab(keys[e.key]); }
    }
    const result = row?.result;
    const finished = rows.filter(item => item.result).length;
    async function download(which, reportRows) {
        setPreparing(which);
        try { await downloadReport(reportRows, roleName); } finally { setPreparing(null); }
    }
    const canRetry = row?.error && !busy && !deleting && (processing === -1 || processing === index);
    return <dialog ref={dialog} className="analysis-dialog" aria-labelledby="analysis-title" onCancel={onClose}>
        <div className="output-panel dialog-layout">
            <header className="dialog-header"><div><p className="eyebrow">ASSESSMENT RESULTS</p><h2 id="analysis-title">Analysis output</h2></div>
                <button className="icon-button" aria-label="Close results" onClick={onClose}><Icon name="close"/></button></header>
            <div className="tab-list" role="tablist" aria-label="Resume assessments">{rows.map((item, i) =>
                <button key={i} role="tab" id={`tab-${i}`} aria-controls="report-panel" aria-selected={index === i}
                    ref={el => { tabs.current[i] = el; }} tabIndex={index === i ? 0 : -1}
                    onKeyDown={tabKey} onClick={() => setSelected(i)} title={item.document.name}>
                    <span className="tab-state" data-state={item.status}/><span>{item.document.name}</span></button>)}</div>
            {row && <section key={index} className="dialog-body" id="report-panel" role="tabpanel" tabIndex={0} aria-labelledby={`tab-${index}`}>
                <p className="report-progress" role="status">{row.status} · {finished} of {rows.length} complete</p>
                {(row.error || deleteError) && <div role="alert" className="error-message"><div><strong>The analysis stopped</strong><p>{deleteError || row.error}</p></div></div>}
                {canRetry && <button className="dialog-action" onClick={() => { setSelected(null); batch.retry(index, row.status === "Failed"); }}>{row.status === "Paused" ? "Check existing analysis" : "Run analysis"}</button>}
                {canRetry && !rows.some(item => item.handle) && <button className="dialog-action edit-documents" onClick={() => onClear(true)}>Edit documents</button>}
                {!result && !row.preview && !row.error && row.status !== "Deleted" && <div className="empty-state"><Lens processing={index === processing && busy}/>
                    <p className="state-copy">{row.status === "Pending" ? "This resume is waiting its turn." : "Results will appear here as they arrive."}</p></div>}
                {(result || row.preview) && <div className="result-container">
                    {result?.metadata.backend === "stub" && <p className="result-notice">Demo mode: this is a simulated keyword-based assessment.</p>}
                    {result && !result.metadata.grounded && <p className="grounding-note">Reference material was unavailable. Review claims against the original documents.</p>}
                    {!result && <p className="grounding-note">Draft assessment · awaiting final validation</p>}
                    <Assessment result={result?.result ?? row.preview}/>
                </div>}
            </section>}
            <footer className="dialog-footer">
                <button className="dialog-action" disabled={deleting} onClick={() => onClear(false)}>{deleting ? "Deleting…" : "Delete analysis and clear documents"}</button>
                <div className="download-actions">
                {rows.length > 1 && !busy && pending < 0 && finished > 0 && <button className="dialog-action" disabled={!!preparing || deleting}
                    onClick={() => download("batch", rows)}>{preparing === "batch" ? "Preparing PDF…" : "Download batch report"}</button>}
                <button className="download-button" disabled={!result || deleting || !!preparing} aria-busy={preparing === "single"}
                    onClick={() => download("single", [row])}><Icon name="download"/>{preparing === "single" ? "Preparing PDF…" : "Download report"}</button>
                </div>
            </footer>
        </div>
    </dialog>;
}
