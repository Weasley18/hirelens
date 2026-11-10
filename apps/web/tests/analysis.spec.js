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
    await expect(page.getByLabel("Resume", { exact: true })).toHaveValue("");
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
    await expect(page.getByRole("button", { name: "Check existing analysis" })).toBeEnabled();
});
test("reduced motion keeps processing feedback readable without rotation", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.route(/\/analyze(?:\/.*)?$/, route => route.fulfill({ status: route.request().method() === "POST" ? 202 : 200,
        json: route.request().method() === "POST" ? handle : { status: "active" } }));
    await page.goto("/");
    await page.getByRole("button", { name: "Use the sample resume" }).click();
    await expect(page.locator(".lens-sweep")).toBeVisible();
    expect(await page.locator(".lens-sweep").evaluate(element => getComputedStyle(element).animationName)).toBe("none");
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
