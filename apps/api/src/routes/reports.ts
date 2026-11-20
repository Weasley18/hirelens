import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { AnalysisEnvelopeSchema } from "@hirelens/shared";
import type { PrivateStore } from "../privacy.js";
import type { RenderPdf } from "../report/pdf.js";
import { renderReportHtml, type ReportItem } from "../report/template.js";

const Label = z.string().trim().min(1).max(120);
const ReportRequestSchema = z.object({
  title: Label.optional(),
  items: z.array(z.object({
    jobId: z.string().uuid(),
    accessToken: z.string().regex(/^[a-f0-9]{64}$/),
    label: Label,
  }).strict()).min(1).max(10),
}).strict();

export interface ReportDependencies { store: PrivateStore; renderPdf?: RenderPdf }

/**
 * POST /reports renders a PDF of finished analyses. Each item must carry that analysis's own
 * access token, and the content comes from the stored result, never from the request: the
 * endpoint cannot be used to print arbitrary text. Labels (file and role names) are display-only
 * and escaped. The PDF is streamed back and not stored.
 */
export async function reportRoutes(app: FastifyInstance, { store, renderPdf }: ReportDependencies) {
  app.post("/reports", { config: { rateLimit: { max: 10, timeWindow: "1 minute" } } }, async (request, reply) => {
    const parsed = ReportRequestSchema.safeParse(request.body);
    if (!parsed.success) return reply.code(400).send({ error: "Invalid report request." });
    const items: ReportItem[] = [];
    for (const item of parsed.data.items) {
      const stored = await store.authorized(item.jobId, `Bearer ${item.accessToken}`)
        ? await store.result(item.jobId) : null;
      // Re-validated even though the worker validated it: this content goes into a browser.
      const envelope = AnalysisEnvelopeSchema.safeParse(stored);
      if (!stored || !envelope.success) return reply.code(404).send({ error: "An analysis is unavailable or expired." });
      items.push({ label: item.label, envelope: envelope.data });
    }
    if (!renderPdf) return reply.code(503).send({ error: "PDF reports are unavailable." });
    let pdf: Uint8Array;
    try {
      pdf = await renderPdf(renderReportHtml({ title: parsed.data.title, generatedAt: new Date(), items }));
    } catch {
      request.log.warn("PDF rendering failed");
      return reply.code(503).send({ error: "PDF reports are temporarily unavailable." });
    }
    const filename = items.length === 1 ? "HireLens-report.pdf" : "HireLens-batch-report.pdf";
    return reply.header("Content-Type", "application/pdf")
      .header("Content-Disposition", `attachment; filename="${filename}"`)
      .send(Buffer.from(pdf));
  });
}
