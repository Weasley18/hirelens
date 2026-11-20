import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderReportHtml, esc } from "../src/report/template.ts";
import { createPdfRenderer } from "../src/report/pdf.ts";

const fixture = JSON.parse(readFileSync(fileURLToPath(new URL("../../../packages/shared/fixtures/sample-analysis.json", import.meta.url)), "utf8"));
const item = (overrides: object = {}, label = "Candidate.pdf") => ({ label, envelope: { result: { ...fixture, ...overrides }, metadata: { backend: "hosted" as const, grounded: true } } });

test("template escapes every untrusted value and contains no script or external resource", () => {
  assert.equal(esc(`<a href="x">'&'</a>`), "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;");
  const html = renderReportHtml({ title: "<b>Role</b>", generatedAt: new Date(0), items: [
    item({ verdict: "<script>alert(1)</script>", strengths: ["<img src=x onerror=alert(1)>"] }, "<i>name</i>.pdf")] });
  assert.ok(!/<script/i.test(html), "no script elements");
  assert.ok(!/<img/i.test(html), "no image elements");
  assert.ok(!/(src|href)=["']?https?:/i.test(html), "no external resources");
  assert.ok(html.includes("&lt;script&gt;alert(1)&lt;/script&gt;") && html.includes("&lt;i&gt;name&lt;/i&gt;.pdf"));
  assert.match(html, /Content-Security-Policy" content="default-src 'none'/);
});

test("single report has no overview; batch report adds one and a page per candidate", () => {
  const single = renderReportHtml({ generatedAt: new Date(0), items: [item()] });
  const batch = renderReportHtml({ generatedAt: new Date(0), items: [item(), item({ fitScore: 30 }, "Second.pdf")] });
  assert.ok(!single.includes("Overview") && !single.includes('class="candidate new-page"'));
  assert.ok(batch.includes("Overview"));
  assert.equal(batch.match(/class="candidate new-page"/g)?.length, 2);
  assert.ok(batch.includes("Limited alignment"));
});

const chromium = [process.env.CHROMIUM_PATH, "/usr/bin/chromium", "/usr/bin/google-chrome", "/usr/bin/chromium-browser"]
  .find(path => path && existsSync(path));

test("renders a real PDF with the system Chromium", { skip: !chromium && "no Chromium on this machine" }, async () => {
  const render = createPdfRenderer({ executablePath: chromium!, idleMs: 1000 });
  try {
    const pdf = await render(renderReportHtml({ title: "Backend Engineer", generatedAt: new Date(0), items: [item(), item({}, "Second.pdf")] }));
    assert.equal(Buffer.from(pdf.subarray(0, 5)).toString(), "%PDF-");
    assert.ok(pdf.length > 10_000);
  } finally { await render.close(); }
});
