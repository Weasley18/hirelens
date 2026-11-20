import puppeteer, { type Browser } from "puppeteer-core";
import { FOOTER_TEMPLATE } from "./template.js";

export type RenderPdf = (html: string) => Promise<Uint8Array>;

/**
 * Renders report HTML to PDF with a system Chromium (Debian's `chromium` package in the API
 * image; Puppeteer's own Chrome download has no Linux ARM build).
 *
 * The page content includes model output, so the page is locked down: JavaScript disabled, every
 * network request aborted (the HTML is self-contained), and a strict CSP in the document itself.
 * One browser is reused, one page renders at a time, and the browser closes after a minute idle
 * so its memory is returned between downloads.
 */
export function createPdfRenderer({ executablePath, timeoutMs = 20_000, idleMs = 60_000 }:
  { executablePath: string; timeoutMs?: number; idleMs?: number }): RenderPdf & { close(): Promise<void> } {
  let browser: Promise<Browser> | null = null;
  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  let queue: Promise<unknown> = Promise.resolve();

  const launch = () => puppeteer.launch({
    executablePath,
    headless: true,
    // --no-sandbox: Chromium's sandbox needs privileges a hardened container does not grant. The
    // page runs no JavaScript and loads nothing, which is what the sandbox would otherwise contain.
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-first-run",
      "--disable-extensions", "--disable-background-networking", "--disable-sync", "--mute-audio"],
  }).then(instance => {
    instance.on("disconnected", () => { browser = null; });
    return instance;
  });

  async function close() {
    clearTimeout(idleTimer);
    const current = browser;
    browser = null;
    if (current) await (await current.catch(() => null))?.close().catch(() => undefined);
  }

  async function renderOnce(html: string): Promise<Uint8Array> {
    clearTimeout(idleTimer);
    browser ??= launch();
    let instance: Browser;
    try { instance = await browser; } catch (error) { browser = null; throw error; }
    const page = await instance.newPage();
    let deadline: ReturnType<typeof setTimeout> | undefined;
    try {
      await page.setJavaScriptEnabled(false);
      await page.setRequestInterception(true);
      page.on("request", request => {
        // setContent itself is not a network request; anything else (fonts, images, links) is refused.
        request.abort("blockedbyclient").catch(() => undefined);
      });
      const work = (async () => {
        await page.setContent(html, { waitUntil: "load", timeout: timeoutMs });
        return page.pdf({
          format: "A4", printBackground: true, preferCSSPageSize: true,
          displayHeaderFooter: true, headerTemplate: "<span></span>", footerTemplate: FOOTER_TEMPLATE,
          margin: { top: "18mm", bottom: "20mm", left: "16mm", right: "16mm" },
          timeout: timeoutMs,
        });
      })();
      return await Promise.race([work, new Promise<never>((_resolve, reject) => {
        deadline = setTimeout(() => reject(new Error("PDF rendering timed out")), timeoutMs);
      })]);
    } catch (error) {
      await close(); // a stuck renderer is not worth reusing
      throw error;
    } finally {
      clearTimeout(deadline);
      await page.close().catch(() => undefined);
      idleTimer = setTimeout(() => { void close(); }, idleMs);
      idleTimer.unref?.();
    }
  }

  const render = ((html: string) => {
    const next = queue.then(() => renderOnce(html), () => renderOnce(html));
    queue = next.catch(() => undefined);
    return next;
  }) as RenderPdf & { close(): Promise<void> };
  render.close = close;
  return render;
}
