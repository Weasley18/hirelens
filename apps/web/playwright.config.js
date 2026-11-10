import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
    testDir: "./tests",
    fullyParallel: true,
    retries: process.env.CI ? 1 : 0,
    use: { baseURL: "http://127.0.0.1:3001", trace: "off", screenshot: "off" },
    projects: [
        { name: "desktop", use: { ...devices["Desktop Chrome"] } },
        { name: "mobile", use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" } },
    ],
    webServer: { command: "npm run start -- --host 127.0.0.1", url: "http://127.0.0.1:3001", reuseExistingServer: false },
});
