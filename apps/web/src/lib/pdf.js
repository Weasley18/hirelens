import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

GlobalWorkerOptions.workerSrc = workerUrl;

export async function readPdf(file, min, max) {
    if (file.size > 10 * 1024 * 1024) throw new Error("Choose a PDF smaller than 10 MB.");
    const task = getDocument({ data: await file.arrayBuffer(), useWasm: false, stopAtErrors: true });
    try {
        const doc = await task.promise;
        const pages = [];
        let length = 0;
        for (let number = 1; number <= doc.numPages; number++) {
            const page = await doc.getPage(number);
            const { items } = await page.getTextContent();
            const text = items.map(item => item.str || "").join(" ").replace(/\s+/gu, " ").trim();
            page.cleanup();
            if (!text) continue;
            length += text.length + Number(pages.length > 0);
            if (length > max) throw new RangeError(`Shorten this document to ${max.toLocaleString()} characters and try again.`);
            pages.push(text);
        }
        const text = pages.join("\n");
        if (text.length < min) throw new RangeError(`Use a PDF with selectable text or paste at least ${min} characters. Scans need OCR first.`);
        return text;
    } catch (error) {
        if (error instanceof RangeError) throw error;
        if (error.name === "PasswordException") throw new Error("Unlock this PDF and try again.");
        throw new Error("This PDF could not be read. Choose another PDF or paste its text.");
    } finally {
        await task.destroy();
    }
}
