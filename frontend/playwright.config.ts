import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

process.env.PLAYWRIGHT_BROWSERS_PATH ??= path.resolve(__dirname, "../.cache/ms-playwright");
const python = process.platform === "win32" ? '"../.venv/Scripts/python.exe"' : '"../.venv/bin/python"';

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "../.cache/playwright-results",
  timeout: 60000,
  expect: { timeout: 15000 },
  workers: 1,
  maxFailures: 1,
  use: { baseURL: "http://127.0.0.1:3001", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "android-layout", use: { ...devices["Pixel 7"] } },
    { name: "iphone-webkit", use: { ...devices["iPhone 13"] } },
  ],
  webServer: [
    { command: `${python} ../backend/tests/e2e_server.py`, url: "http://127.0.0.1:8001/api/v1/health", reuseExistingServer: false, timeout: 60000 },
    { command: "npm run dev -- --port 3001", url: "http://127.0.0.1:3001", env: { BACKEND_URL: "http://127.0.0.1:8001", NEXT_TELEMETRY_DISABLED: "1" }, reuseExistingServer: false, timeout: 60000 },
  ],
});
