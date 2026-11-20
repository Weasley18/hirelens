import { defineConfig, devices } from "@playwright/test";
const port = Number(process.env.PLAYWRIGHT_PORT || 3001);
const baseURL = `http://127.0.0.1:${port}`;
export default defineConfig({
    testDir: "./tests",
    fullyParallel: true,
    retries: process.env.CI ? 1 : 0,
    use: { baseURL, trace: "off", screenshot: "off" },
    projects: [
        { name: "desktop", use: { ...devices["Desktop Chrome"] } },
        { name: "mobile", use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" } },
    ],
    webServer: { command: `npm run start -- --host 127.0.0.1 --port ${port}`, url: baseURL, reuseExistingServer: false },
});
