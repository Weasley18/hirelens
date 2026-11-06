import { AnalysisEnvelopeSchema, type AnalysisEnvelope, type JobStatus } from "@hirelens/shared";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:3000";
export class AnalysisError extends Error {}
export interface AnalysisHandle { jobId: string; accessToken: string }
const headers = (handle: AnalysisHandle) => ({ Authorization: `Bearer ${handle.accessToken}` });

export async function deleteAnalysis(handle: AnalysisHandle): Promise<void> {
  const response = await fetch(`${API_URL}/analyze/${handle.jobId}`, {
    method: "DELETE", headers: headers(handle), signal: AbortSignal.timeout(10_000), cache: "no-store",
  });
  if (!response.ok && response.status !== 404) throw new AnalysisError("Could not delete the analysis. Try again.");
}

export async function runAnalysis(resume: string, jd: string, onStatus?: (status: JobStatus) => void,
  onSubmitted?: (handle: AnalysisHandle) => void, signal?: AbortSignal): Promise<AnalysisEnvelope> {
  const requestSignal = () => signal ? AbortSignal.any([signal, AbortSignal.timeout(10_000)]) : AbortSignal.timeout(10_000);
  const submitted = await fetch(`${API_URL}/analyze`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ resume, jd }),
    signal: requestSignal(), cache: "no-store",
  }).catch(() => { throw new AnalysisError("Could not reach the service. Please try again."); });
  if (!submitted.ok) throw new AnalysisError(submitted.status === 429 ? "The service is busy. Wait a minute and try again." : "Check both documents and try again.");
  const handle = await submitted.json() as AnalysisHandle;
  if (!/^[a-f0-9-]{36}$/.test(handle.jobId) || !/^[a-f0-9]{64}$/.test(handle.accessToken)) throw new AnalysisError("Invalid service response.");
  // Keep the capability only in memory, never URLs, browser storage, or logs.
  onSubmitted?.(handle);
  const deadline = Date.now() + 180_000;
  while (Date.now() < deadline) {
    await new Promise(resolve => setTimeout(resolve, 1500));
    if (signal?.aborted) throw new AnalysisError("Analysis cancelled.");
    let polled: Response;
    try {
      polled = await fetch(`${API_URL}/analyze/${handle.jobId}`, { headers: headers(handle), signal: requestSignal(), cache: "no-store" });
    } catch { if (signal?.aborted) throw new AnalysisError("Analysis cancelled."); continue; }
    if (polled.status === 429 || polled.status >= 500) {
      await new Promise(resolve => setTimeout(resolve, 5000)); continue;
    }
    if (!polled.ok) throw new AnalysisError("Analysis unavailable or expired.");
    const data = await polled.json();
    if (data.status === "done") return AnalysisEnvelopeSchema.parse({ result: data.result, metadata: data.metadata });
    if (data.status === "failed") throw new AnalysisError("The analysis could not be completed. Shorten the documents and try again.");
    onStatus?.(data.status);
  }
  throw new AnalysisError("The analysis timed out. You can delete it below before retrying.");
}
