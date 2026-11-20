import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import fixture from "../../../packages/shared/fixtures/sample-analysis.json" with { type: "json" };
const handle = { jobId: "12345678-1234-4234-8234-123456789abc", accessToken: "a".repeat(64) };
const result = { status: "done", result: fixture, metadata: { backend: "stub", grounded: false } };
test("sample assessment, privacy disclosure, keyboard access, and deletion", async ({ page }, testInfo) => {
    let deleted = false;
    await page.route(/\/analyze(?:\/.*)?$/, async (route) => {
        const method = route.request().method();
        if (method === "POST")
            return route.fulfill({ status: 202, json: handle });
        expect(route.request().headers().authorization).toBe(`Bearer ${handle.accessToken}`);
        if (method === "DELETE") {
            deleted = true;
            return route.fulfill({ status: 204 });
        }
        return route.fulfill({ json: result });
    });
    await page.goto("/");
    if (process.env.CAPTURE_UI) {
        await page.waitForTimeout(400);
        await page.screenshot({ path: `/tmp/hirelens-${testInfo.project.name}.png`, fullPage: true, animations: "disabled" });
    }
    await expect(page.getByRole("button", { name: "Run analysis", exact: true })).toBeDisabled();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Skip to assessment" })).toBeFocused();
    await page.getByRole("button", { name: "Use the sample resume" }).click();
    await expect(page.getByRole("tab")).toHaveCount(1);
    await expect(page.getByText(/Demo mode:/)).toBeVisible();
    await expect(page.getByText(fixture.verdict)).toBeVisible();
    if (process.env.CAPTURE_UI) {
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: `/tmp/hirelens-${testInfo.project.name}-result.png`, fullPage: true, animations: "disabled" });
    }
    await expect(page.getByLabel("Resume", { exact: true })).toBeDisabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
    await page.getByRole("button", { name: "Delete analysis and clear documents" }).click();
    await expect(page.getByLabel("Upload resume PDFs")).toHaveValue("");
    expect(deleted).toBe(true);
});
test("poll recovery reuses the existing job instead of submitting again", async ({ page }) => {
    let submissions = 0;
    let polls = 0;
    await page.route(/\/analyze(?:\/.*)?$/, async (route) => {
        if (route.request().method() === "POST") {
            submissions++;
            return route.fulfill({ status: 202, json: handle });
        }
        if (++polls === 1)
            return route.fulfill({ json: { status: "unexpected" } });
        return route.fulfill({ json: result });
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Use the sample resume" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "The analysis stopped" })).toBeVisible();
    await page.getByRole("button", { name: "Check existing analysis" }).click();
    await expect(page.getByText(fixture.verdict)).toBeVisible();
    expect(submissions).toBe(1);
});
test("overload and failed deletion keep recovery available", async ({ page }) => {
    let overloaded = true;
    await page.route(/\/analyze(?:\/.*)?$/, async (route) => {
        if (overloaded)
            return route.fulfill({ status: 429, json: {} });
        if (route.request().method() === "POST")
            return route.fulfill({ status: 202, json: handle });
        if (route.request().method() === "DELETE")
            return route.fulfill({ status: 503, json: {} });
        return route.fulfill({ json: { status: "failed" } });
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Use the sample resume" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "The analysis stopped" })).toContainText("busy");
    overloaded = false;
    await page.getByRole("button", { name: "Run analysis", exact: true }).click();
    await expect(page.getByRole("alert").filter({ hasText: "The analysis stopped" })).toContainText("could not be completed");
    await page.getByRole("button", { name: "Delete analysis and clear documents" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "The analysis stopped" })).toContainText("Deletion failed");
    await expect(page.getByRole("button", { name: "Delete analysis and clear documents" })).toBeEnabled();
});
test("reduced motion keeps processing feedback readable without rotation", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.route(/\/analyze(?:\/.*)?$/, route => route.fulfill({ status: route.request().method() === "POST" ? 202 : 200,
        json: route.request().method() === "POST" ? handle : { status: "active" } }));
    await page.goto("/");
    const homeSweep = page.locator(".hero .lens-sweep");
    await expect(homeSweep).toBeInViewport();
    await expect(homeSweep).toHaveCSS("animation-name", "revolve");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect(homeSweep).toHaveCSS("animation-name", "none");
    await page.getByRole("button", { name: "Use the sample resume" }).click();
    const processingSweep = page.getByRole("dialog").locator(".lens-sweep");
    await expect(processingSweep).toBeVisible();
    await expect(processingSweep).toHaveCSS("animation-name", "none");
    await expect(page.getByLabel("Resume", { exact: true })).toBeDisabled();
});

test("React entry retains metadata and production security headers", async ({ page }) => {
    const response = await page.goto("/");
    await expect(page).toHaveTitle("HireLens — resume and job description assessment");
    await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", /Paste a resume/);
    await expect(page.locator("#root h1")).toContainText("See the fit.");
    expect(response.headers()["content-security-policy"]).toContain("frame-ancestors 'none'");
    expect(response.headers()["x-frame-options"]).toBe("DENY");
    expect(response.headers()["x-content-type-options"]).toBe("nosniff");
    expect(await page.locator('script[src*="/_next/"]').count()).toBe(0);
    await expect(page.locator('script[type="module"][src^="/assets/"]')).toHaveCount(1);
});

function pdf(name, text) {
    const content = `BT /F1 10 Tf 40 730 Td (${text}) Tj ET`;
    const objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        `<< /Length ${content.length} >>\nstream\n${content}\nendstream`,
    ];
    let body = "%PDF-1.4\n";
    const offsets = ["0000000000 65535 f "];
    objects.forEach((object, i) => {
        offsets.push(body.length.toString().padStart(10, "0") + " 00000 n ");
        body += `${i + 1} 0 obj\n${object}\nendobj\n`;
    });
    const start = body.length;
    body += `xref\n0 6\n${offsets.join("\n")}\ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${start}\n%%EOF\n`;
    return { name, mimeType: "application/pdf", buffer: Buffer.from(body) };
}

test("PDF batch writes partial results, submits in order and exports both reports", async ({ page }) => {
    const jd = "Role requires Python expertise and experience in building reliable payment services.";
    const resumes = ["First", "Second"].map(name => name + " engineer with extensive Python experience designing, testing, and operating payment services.");
    const submissions = [];
    const secondHandle = { jobId: "abcd5678-1234-4234-8234-123456789abc", accessToken: "b".repeat(64) };
    const secondVerdict = "Second candidate demonstrates relevant experience.";
    let allowFinish = false;
    await page.route(/\/analyze(?:\/.*)?$/, async route => {
        if (route.request().method() === "POST") {
            submissions.push(route.request().postDataJSON());
            return route.fulfill({ status: 202, json: submissions.length === 1 ? handle : secondHandle });
        }
        const second = route.request().url().endsWith(secondHandle.jobId);
        expect(route.request().headers().authorization).toBe(`Bearer ${(second ? secondHandle : handle).accessToken}`);
        if (!allowFinish) return route.fulfill({ json: { status: "active", preview: { verdict: "Streaming the initial alignment." } } });
        return route.fulfill({ json: second ? { ...result, result: { ...fixture, verdict: secondVerdict } } : result });
    });
    await page.goto("/");
    await page.getByLabel("Upload resume PDFs").setInputFiles(resumes.map((text, i) => pdf(`Candidate-${i + 1}.pdf`, text)));
    await page.getByLabel("Upload job description PDF").setInputFiles(pdf("Role.pdf", jd));
    await page.getByRole("button", { name: "Run analysis" }).click();
    await expect(page.getByRole("tab")).toHaveCount(2);
    await expect(page.getByText("Streaming the initial alignment.")).toBeVisible();
    expect(submissions).toEqual([{ resume: resumes[0], jd }]);
    await page.getByRole("tab", { name: "Candidate-2.pdf" }).click();
    await expect(page.getByText("This resume is waiting its turn.")).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "View analysis" }).click();
    allowFinish = true;
    await expect(page.getByText("Complete · 2 of 2 complete")).toBeVisible({ timeout: 12000 });
    expect(submissions).toEqual(resumes.map(resume => ({ resume, jd })));
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight && document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole("tab", { name: "Candidate-1.pdf" }).click();
    for (const [label, filename] of [["Download report", "HireLens-Candidate-1.txt"], ["Download batch report", "HireLens-batch-report.txt"]]) {
        const waiting = page.waitForEvent("download");
        await page.getByRole("button", { name: label, exact: true }).click();
        const file = await waiting;
        expect(file.suggestedFilename()).toBe(filename);
        const text = await readFile(await file.path(), "utf8");
        expect(text).toContain(fixture.verdict);
        expect(text).toContain("Role.pdf");
        expect(text.includes("Candidate-2.pdf")).toBe(label === "Download batch report");
        expect(text.includes(secondVerdict)).toBe(label === "Download batch report");
        expect(text).not.toContain(handle.accessToken);
    }
});

test("a scanned resume reports a file-specific error and the next PDF still completes", async ({ page }) => {
    let submissions = 0;
    await page.route(/\/analyze(?:\/.*)?$/, route => {
        if (route.request().method() === "POST") { submissions++; return route.fulfill({ status: 202, json: handle }); }
        return route.fulfill({ json: result });
    });
    await page.goto("/");
    await page.getByLabel("Upload resume PDFs").setInputFiles([
        pdf("Scan.pdf", ""), pdf("Resume.pdf", "Backend engineer with a decade of experience building payment services and managing infrastructure.")]);
    await page.getByLabel("Upload job description PDF").setInputFiles(pdf("Role.pdf", "We need a backend engineer with experience designing and operating APIs."));
    await page.getByRole("button", { name: "Run analysis" }).click();
    await expect(page.getByText(fixture.verdict)).toBeVisible();
    await page.getByRole("tab", { name: "Scan.pdf" }).click();
    await expect(page.getByRole("alert")).toContainText("Scans need OCR");
    expect(submissions).toBe(1);
});

test("one uploaded PDF opens one tab and can use a pasted job description", async ({ page }) => {
    const resume = "Engineer with experience building reliable data pipelines in Python and maintaining production services.";
    const jd = "We are hiring a data engineer to build Python services and maintain data pipelines.";
    await page.route(/\/analyze(?:\/.*)?$/, async route => {
        if (route.request().method() === "POST") {
            expect(route.request().postDataJSON()).toEqual({ resume, jd });
            return route.fulfill({ status: 202, json: handle });
        }
        return route.fulfill({ json: result });
    });
    await page.goto("/");
    await page.getByLabel("Upload resume PDFs").setInputFiles(pdf("Engineer.pdf", resume));
    await page.getByRole("region", { name: "Job description", exact: true }).getByRole("button", { name: "Text", exact: true }).click();
    await page.getByRole("textbox", { name: "Job description" }).fill(jd);
    await page.getByRole("button", { name: "Run analysis" }).click();
    await expect(page.getByRole("tab")).toHaveCount(1);
    await expect(page.getByRole("tab", { name: "Engineer.pdf" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText(fixture.verdict)).toBeVisible();
});

test("clearing during submission deletes the job when its capability arrives", async ({ page }) => {
    let accept;
    const accepted = new Promise(resolve => { accept = resolve; });
    let submitted;
    const started = new Promise(resolve => { submitted = resolve; });
    let deletions = 0;
    await page.route(/\/analyze(?:\/.*)?$/, async route => {
        if (route.request().method() === "POST") {
            submitted();
            await accepted;
            return route.fulfill({ status: 202, json: handle });
        }
        expect(route.request().method()).toBe("DELETE");
        expect(route.request().headers().authorization).toBe(`Bearer ${handle.accessToken}`);
        deletions++;
        return route.fulfill({ status: 204 });
    });
    await page.goto("/");
    await page.getByRole("button", { name: "Use the sample resume" }).click();
    await started;
    await page.getByRole("button", { name: "Delete analysis and clear documents" }).click();
    accept();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(deletions).toBe(1);
});
