import { AnalysisResultSchema, type AnalysisResult } from "@hirelens/shared";
import { TransientInferenceError, InvalidDocumentsError } from "./processor.js";

export async function readInferenceResponse(response: Response, onPreview: (preview: Partial<AnalysisResult>) => Promise<unknown>) {
  if (!response.body) throw new TransientInferenceError();
  const reader = response.body.getReader();
  const streaming = response.headers.get("content-type")?.startsWith("application/x-ndjson");
  const decoder = new TextDecoder();
  let buffer = "";
  let size = 0;
  let preview: Partial<AnalysisResult> = {};
  let finalResult: unknown;
  while (true) {
    const { done, value } = await reader.read().catch(() => { throw new TransientInferenceError(); });
    if (done) break;
    size += value.length;
    if (size > 100_000) { await reader.cancel(); throw new Error("Oversized response"); }
    buffer += decoder.decode(value, { stream: true });
    if (!streaming) continue;
    const lines = buffer.split("\n");
    buffer = lines.pop()!;
    for (const line of lines) {
      const event = JSON.parse(line);
      if (event.error === 422) throw new InvalidDocumentsError();
      if (event.error) throw new Error("Inference failed");
      if (event.done) finalResult = event.done;
      else if (event.reset) { preview = {}; await onPreview(preview); }
      else {
        const parsed = AnalysisResultSchema.partial().safeParse({ [event.field]: event.value });
        if (parsed.success) {
          preview = { ...preview, ...parsed.data };
          await onPreview(preview);
        }
      }
    }
  }
  if (streaming) {
    if (!finalResult) throw new TransientInferenceError();
    return finalResult;
  }
  return JSON.parse(buffer + decoder.decode());
}
