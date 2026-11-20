import type { AnalysisEnvelope } from "@hirelens/shared";

/**
 * The PDF report as a self-contained HTML document: inline CSS and SVG only, no scripts, no
 * external resources. Every value that came from a model or a browser goes through esc().
 */
export interface ReportItem { label: string; envelope: AnalysisEnvelope }
export interface ReportInput { title?: string; generatedAt: Date; items: ReportItem[] }

const ESCAPES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" };
export const esc = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, char => ESCAPES[char]);
const score = (value: number) => Math.max(0, Math.min(100, Math.round(Number(value) || 0)));

const BAND = (fit: number) => fit >= 80 ? { name: "Strong alignment", color: "#3f7d1f" }
  : fit >= 60 ? { name: "Good alignment", color: "#6b8e23" }
  : fit >= 40 ? { name: "Partial alignment", color: "#b7791f" }
  : { name: "Limited alignment", color: "#b4442e" };
const SEVERITY: Record<string, { label: string; color: string; bg: string }> = {
  severe: { label: "Severe", color: "#9a2f1f", bg: "#f8e1dc" },
  moderate: { label: "Moderate", color: "#8a5a10", bg: "#f6ead2" },
  minor: { label: "Minor", color: "#45524d", bg: "#e7ebe6" },
};

const LENS_MARK = `<svg width="26" height="18" viewBox="0 0 26 18" aria-hidden="true">
  <circle cx="9" cy="9" r="7.5" fill="none" stroke="#172421" stroke-width="1.6"/>
  <circle cx="17" cy="9" r="7.5" fill="none" stroke="#172421" stroke-width="1.6"/>
  <path d="M13 3.2a7.5 7.5 0 0 1 0 11.6a7.5 7.5 0 0 1 0-11.6z" fill="#d2f474"/></svg>`;

function ring(fit: number, size = 92) {
  const r = size / 2 - 7, c = 2 * Math.PI * r, band = BAND(fit);
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" class="ring" aria-label="Fit score ${fit} of 100">
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="#e4e8df" stroke-width="7"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${band.color}" stroke-width="7"
      stroke-linecap="round" stroke-dasharray="${(c * fit / 100).toFixed(2)} ${c.toFixed(2)}"
      transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <text x="50%" y="50%" text-anchor="middle" dominant-baseline="central" class="ring-number">${fit}</text>
  </svg>`;
}

function candidate(item: ReportItem, index: number, total: number) {
  const { result, metadata } = item.envelope;
  const fit = score(result.fitScore), band = BAND(fit);
  const notices = [
    metadata.backend === "stub" && "Demo mode: simulated keyword-based assessment, not a model's judgement.",
    !metadata.grounded && "Reference material was unavailable for this assessment. Check claims against the original documents.",
  ].filter(Boolean).map(text => `<p class="notice">${esc(text)}</p>`).join("");
  const strengths = result.strengths.length
    ? result.strengths.map(s => `<li><span class="tick">✓</span><span>${esc(s)}</span></li>`).join("")
    : `<li class="empty">No strengths reported.</li>`;
  const gaps = result.gaps.length
    ? result.gaps.map(g => {
      const sev = SEVERITY[g.severity] ?? SEVERITY.minor;
      return `<li class="gap"><div class="gap-head"><strong>${esc(g.skill)}</strong>
        <span class="pill" style="color:${sev.color};background:${sev.bg}">${sev.label}</span></div>
        <p>${esc(g.note)}</p></li>`;
    }).join("")
    : `<li class="empty">No gaps reported.</li>`;
  const questions = result.interviewQuestions.map((q, i) => `<li class="question">
      <span class="q-number">${String(i + 1).padStart(2, "0")}</span>
      <div><p class="q-text">${esc(q.question)}</p>
      <p class="q-meta"><span>Tests: ${esc(q.targets)}</span><span class="chip">${esc(q.difficulty)}</span></p></div></li>`).join("");
  return `<section class="candidate${index > 0 || total > 1 ? " new-page" : ""}">
    <div class="candidate-head">
      <div class="candidate-id">
        ${total > 1 ? `<p class="eyebrow">Candidate ${index + 1} of ${total}</p>` : `<p class="eyebrow">Candidate</p>`}
        <h2>${esc(item.label)}</h2>
        <p class="band" style="color:${band.color}">${band.name}</p>
        <p class="verdict">${esc(result.verdict)}</p>
      </div>
      <div class="score">${ring(fit)}<p>Role alignment</p></div>
    </div>
    ${notices}
    <div class="columns">
      <div class="panel"><h3>Strengths</h3><ul class="strengths">${strengths}</ul></div>
      <div class="panel"><h3>Areas to explore</h3><ul class="gaps">${gaps}</ul></div>
    </div>
    <div class="panel questions-panel"><h3>Interview questions</h3><ol class="questions">${questions}</ol></div>
  </section>`;
}

function summary(items: ReportItem[]) {
  const rows = items.map((item, i) => {
    const fit = score(item.envelope.result.fitScore), band = BAND(fit);
    return `<tr><td class="num">${i + 1}</td><td><strong>${esc(item.label)}</strong><span class="sub">${esc(item.envelope.result.verdict)}</span></td>
      <td class="bar-cell"><div class="bar"><span style="width:${fit}%;background:${band.color}"></span></div></td>
      <td class="fit" style="color:${band.color}">${fit}</td></tr>`;
  }).join("");
  return `<section class="summary"><h3>Overview</h3>
    <table><thead><tr><th></th><th>Candidate</th><th>Alignment</th><th class="fit">Score</th></tr></thead><tbody>${rows}</tbody></table>
  </section>`;
}

export function renderReportHtml({ title, generatedAt, items }: ReportInput): string {
  const date = generatedAt.toLocaleString("en-GB", { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "UTC" });
  const heading = items.length > 1 ? "Batch assessment" : "Candidate assessment";
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<title>HireLens ${esc(heading)}</title>
<style>
  @page { size: A4; margin: 18mm 16mm 20mm; }
  * { box-sizing: border-box; }
  body { margin: 0; color: #172421; font: 10pt/1.5 "Helvetica Neue", Helvetica, Arial, "Liberation Sans", "DejaVu Sans", sans-serif;
    -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  h1, h2, h3, p { margin: 0; }
  .masthead { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: 10px; border-bottom: 1.5px solid #172421; }
  .brand { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 13pt; letter-spacing: -0.02em; }
  .meta { text-align: right; font-size: 8.5pt; color: #5b6863; }
  .hero { margin: 12px 0 14px; padding: 14px 18px; border-radius: 12px; background: #152722; color: #f1f3eb; }
  .hero h1 { font-size: 18pt; letter-spacing: -0.03em; line-height: 1.15; }
  .hero h1 em { font-style: normal; color: #d2f474; }
  .hero .role { margin-top: 6px; font-size: 11pt; color: #c9d3c6; }
  .hero .review { margin-top: 6px; font-size: 8.5pt; color: #9fb09c; letter-spacing: 0.02em; }
  .eyebrow { font: 600 7.5pt/1 ui-monospace, "DejaVu Sans Mono", monospace; letter-spacing: 0.12em; text-transform: uppercase; color: #6b7a74; margin-bottom: 6px; }
  .summary h3, .panel h3 { font-size: 8pt; letter-spacing: 0.12em; text-transform: uppercase; color: #5b6863; margin-bottom: 10px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-size: 7.5pt; color: #6b7a74; font-weight: 600; padding: 0 6px 6px; border-bottom: 1px solid #d9dfd5; }
  td { padding: 9px 6px; border-bottom: 1px solid #edf0ea; vertical-align: top; }
  td .sub { display: block; color: #5b6863; font-size: 8.5pt; margin-top: 2px; }
  td.num { width: 22px; color: #9aa59f; } th.fit { width: 42px; text-align: right; } td.fit { width: 42px; text-align: right; font-weight: 700; font-size: 12pt; }
  td.bar-cell { width: 120px; padding-top: 14px; }
  .bar { height: 7px; border-radius: 4px; background: #e4e8df; overflow: hidden; } .bar span { display: block; height: 100%; border-radius: 4px; }
  .new-page { break-before: page; }
  .candidate-head { display: flex; gap: 22px; justify-content: space-between; align-items: center; padding: 4px 0 12px; border-bottom: 1px solid #d9dfd5; }
  .candidate-id h2 { font-size: 17pt; letter-spacing: -0.02em; line-height: 1.2; word-break: break-word; }
  .band { margin-top: 4px; font-weight: 700; font-size: 9.5pt; }
  .verdict { margin-top: 6px; font-size: 11pt; line-height: 1.45; max-width: 120mm; }
  .score { text-align: center; flex: none; } .score p { font-size: 7.5pt; color: #6b7a74; letter-spacing: 0.08em; text-transform: uppercase; margin-top: 2px; }
  .ring-number { font-size: 22pt; font-weight: 700; fill: #172421; }
  .notice { margin-top: 12px; padding: 8px 12px; border-radius: 8px; background: #fbf3d9; color: #6b5310; font-size: 8.5pt; }
  .columns { display: flex; gap: 12px; margin-top: 12px; }
  .columns .panel { flex: 1; }
  .panel { padding: 12px 14px; border: 1px solid #e1e6dd; border-radius: 12px; background: #fafbf7; break-inside: avoid; }
  ul, ol { list-style: none; margin: 0; padding: 0; }
  .strengths li { display: flex; gap: 8px; padding: 3px 0; }
  .tick { color: #3f7d1f; font-weight: 700; }
  .gap { padding: 5px 0 6px; border-bottom: 1px solid #edf0ea; } .gap:last-child { border-bottom: 0; }
  .gap-head { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
  .gap p { margin-top: 2px; color: #45524d; font-size: 9pt; }
  .pill { font-size: 7pt; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; padding: 2px 7px; border-radius: 99px; white-space: nowrap; }
  .empty { color: #8a958f; font-style: italic; }
  .questions-panel { margin-top: 12px; break-inside: auto; }
  .question { display: flex; gap: 12px; padding: 7px 0; border-bottom: 1px solid #edf0ea; break-inside: avoid; }
  .question:last-child { border-bottom: 0; }
  .q-number { font: 700 9pt/1.6 ui-monospace, "DejaVu Sans Mono", monospace; color: #8aa53a; }
  .q-text { font-size: 10pt; }
  .q-meta { display: flex; gap: 10px; align-items: center; margin-top: 4px; font-size: 8pt; color: #6b7a74; }
  .chip { padding: 1px 8px; border-radius: 99px; background: #eef4d6; color: #4d5f15; text-transform: capitalize; font-weight: 600; }
</style></head><body>
  <header class="masthead">
    <div class="brand">${LENS_MARK}<span>hirelens</span></div>
    <div class="meta">Generated ${esc(date)} UTC<br>${items.length} ${items.length === 1 ? "candidate" : "candidates"}</div>
  </header>
  <div class="hero">
    <h1>${esc(heading)}. <em>Find the signal.</em></h1>
    ${title ? `<p class="role">${esc(title)}</p>` : ""}
    <p class="review">AI-assisted analysis for human review. Not a hiring decision.</p>
  </div>
  ${items.length > 1 ? summary(items) : ""}
  ${items.map((item, i) => candidate(item, i, items.length)).join("")}
</body></html>`;
}

/** Footer printed on every page by Chrome (its own small document; inline styles only). */
export const FOOTER_TEMPLATE = `<div style="width:100%;padding:0 16mm;font:7pt Helvetica,Arial,sans-serif;color:#8a958f;display:flex;justify-content:space-between">
  <span>HireLens · AI-assisted analysis for human review</span>
  <span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`;
