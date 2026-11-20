import { useEffect, useRef, useState } from "react";
import { JD_MIN, JD_MAX, RESUME_MIN, RESUME_MAX } from "@hirelens/shared";
import { AnalysisError, TerminalAnalysisError, deleteAnalysis, pollAnalysis, runAnalysis } from "./api";

const statusText = {
    queued: "Waiting for a worker",
    active: "Assessing the documents",
    "rate-limited": "Service busy. Waiting to retry",
};

async function documentText(document, min, max) {
    if (!document.file) return document.text.trim();
    const { readPdf } = await import("./pdf");
    try {
        return await readPdf(document.file, min, max);
    } catch (error) {
        throw new AnalysisError(`${document.name} — ${error.message}`);
    }
}

export default function useAnalysisBatch() {
    const [rows, setRows] = useState([]);
    const state = useRef([]);
    const [busy, setBusy] = useState(false);
    const [deleting, setDeleting] = useState(false);
    const [deleteError, setDeleteError] = useState("");
    const operation = useRef(null);
    const deletion = useRef(false);
    const role = useRef(null);
    useEffect(() => () => operation.current?.controller.abort(), []);

    function replace(next) {
        state.current = next;
        setRows(next);
    }
    function update(index, patch) {
        replace(state.current.map((row, i) => i === index ? { ...row, ...patch } : row));
    }
    async function process(start, signal, resubmit) {
        let jd;
        try {
            jd = await documentText(role.current, JD_MIN, JD_MAX);
        } catch (error) {
            if (!signal.aborted) replace(state.current.map(row => ({ ...row, status: "Failed", error: error.message })));
            return;
        }
        for (let i = start; i < state.current.length && !signal.aborted; i++) {
            const row = state.current[i];
            if (row.status === "Complete" || row.status === "Deleted" || (i !== start && row.status === "Failed")) continue;
            update(i, { status: "Reading documents", error: "", preview: null });
            const progress = (status, preview) => {
                if (!signal.aborted) update(i, { status: statusText[status], preview });
            };
            try {
                let result;
                if (row.handle && resubmit && i === start) {
                    await deleteAnalysis(row.handle);
                    update(i, { handle: null });
                }
                if (state.current[i].handle) {
                    result = await pollAnalysis(row.handle, progress, signal);
                } else {
                    const resume = await documentText(row.document, RESUME_MIN, RESUME_MAX);
                    if (signal.aborted) return;
                    update(i, { status: "Submitting documents" });
                    result = await runAnalysis(resume, jd, progress, handle => update(i, { handle }), signal, state.current.length > 1);
                }
                if (!signal.aborted) update(i, { result, preview: null, status: "Complete" });
            } catch (error) {
                if (signal.aborted) return;
                // A lost poll may still have an active job. Resume that job before starting another.
                const paused = state.current[i].handle && !(error instanceof TerminalAnalysisError);
                update(i, { status: paused ? "Paused" : "Failed", preview: null,
                    error: error instanceof AnalysisError ? error.message : "Could not read the assessment. Try again." });
                if (paused) return;
            }
        }
    }
    function run(start, resubmit = false) {
        if (operation.current || deletion.current) return;
        setDeleteError("");
        setBusy(true);
        const controller = new AbortController();
        const task = { controller };
        operation.current = task;
        task.promise = process(start, controller.signal, resubmit).finally(() => {
            operation.current = null;
            setBusy(false);
        });
    }
    function start(documents, jd) {
        if (state.current.length || deletion.current) return;
        role.current = jd;
        replace(documents.map(document => ({ document, status: "Pending" })));
        run(0);
    }
    async function clear() {
        if (deletion.current) return false;
        deletion.current = true;
        setDeleting(true);
        setDeleteError("");
        const task = operation.current;
        task?.controller.abort();
        await task?.promise;
        try {
            for (const [i, row] of state.current.entries()) {
                if (row.handle) {
                    await deleteAnalysis(row.handle);
                    update(i, { handle: null, result: null, preview: null, error: "", status: "Deleted" });
                }
            }
            role.current = null;
            replace([]);
            return true;
        } catch {
            setDeleteError("Deletion failed. Please try again. Automatic expiry still applies.");
            return false;
        } finally {
            deletion.current = false;
            setDeleting(false);
        }
    }
    return { rows, busy, deleting, deleteError, start, retry: run, clear };
}
