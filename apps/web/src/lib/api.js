import { AnalysisEnvelopeSchema } from "@hirelens/shared";
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:3000";
export class AnalysisError extends Error {
}
const headers = (handle) => ({ Authorization: `Bearer ${handle.accessToken}` });
const requestSignal = (signal) => signal ? AbortSignal.any([signal, AbortSignal.timeout(10_000)]) : AbortSignal.timeout(10_000);
const pause = (ms, signal) => new Promise((resolve, reject) => {
    if (signal?.aborted)
        return reject(new AnalysisError("Analysis cancelled."));
    const done = () => { signal?.removeEventListener("abort", cancel); resolve(); };
    const timer = setTimeout(done, ms);
    const cancel = () => { clearTimeout(timer); signal?.removeEventListener("abort", cancel); reject(new AnalysisError("Analysis cancelled.")); };
    signal?.addEventListener("abort", cancel, { once: true });
});
export async function deleteAnalysis(handle) {
    const response = await fetch(`${API_URL}/analyze/${handle.jobId}`, {
        method: "DELETE", headers: headers(handle), signal: requestSignal(), cache: "no-store",
    });
    if (!response.ok && response.status !== 404)
        throw new AnalysisError("Could not delete the analysis. Try again.");
}
export async function pollAnalysis(handle, onStatus, signal) {
    // Two admitted jobs, each with at most two 90s attempts and 5s backoff, fit this window.
    const deadline = Date.now() + 600_000;
    while (Date.now() < deadline) {
        await pause(1500, signal);
        let polled;
        try {
            polled = await fetch(`${API_URL}/analyze/${handle.jobId}`, { headers: headers(handle), signal: requestSignal(signal), cache: "no-store" });
        }
        catch {
            if (signal?.aborted)
                throw new AnalysisError("Analysis cancelled.");
            continue;
        }
        if (polled.status === 429 || polled.status >= 500) {
            const retrySeconds = Number(polled.headers.get("Retry-After"));
            await pause(Number.isFinite(retrySeconds) && retrySeconds > 0 ? Math.min(retrySeconds, 60) * 1000 : 5000, signal);
            continue;
        }
        if (!polled.ok)
            throw new AnalysisError("Analysis unavailable or expired. Submit a new analysis.");
        const data = await polled.json();
        if (data.status === "done")
            return AnalysisEnvelopeSchema.parse({ result: data.result, metadata: data.metadata });
        if (data.status === "failed")
            throw new AnalysisError(data.error === "The documents exceed the model’s limits. Shorten them and submit again."
                ? data.error : "The analysis could not be completed. Please try again.");
        if (data.status !== "queued" && data.status !== "active")
            throw new AnalysisError("Unexpected service response.");
        onStatus?.(data.status);
    }
    throw new AnalysisError("Still waiting. Choose Check existing analysis to continue without submitting again.");
}
export async function runAnalysis(resume, jd, onStatus, onSubmitted, signal) {
    const submitted = await fetch(`${API_URL}/analyze`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ resume, jd }),
        signal: requestSignal(signal), cache: "no-store",
    }).catch(() => { throw new AnalysisError("Could not reach the service. Please try again."); });
    if (!submitted.ok)
        throw new AnalysisError(submitted.status === 429 ? "The service is busy. Wait a minute and try again."
            : submitted.status >= 500 ? "The service is temporarily unavailable. Please try again shortly."
                : "Check both documents and their length, then try again.");
    const handle = await submitted.json();
    if (!/^[a-f0-9-]{36}$/.test(handle.jobId) || !/^[a-f0-9]{64}$/.test(handle.accessToken))
        throw new AnalysisError("Invalid service response.");
    // Keep the capability only in memory, never URLs, browser storage, or logs.
    onSubmitted?.(handle);
    if (signal?.aborted) {
        await deleteAnalysis(handle);
        throw new AnalysisError("Analysis cancelled.");
    }
    return pollAnalysis(handle, onStatus, signal);
}
