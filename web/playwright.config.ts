import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI
    ? [
        ["list"],
        ["junit", { outputFile: "../artifacts/playwright-junit.xml" }]
      ]
    : "list",
  outputDir: "../review/UI-7/runs/playwright",
  use: {
    baseURL: "http://127.0.0.1:8765",
    trace: "on",
    screenshot: "only-on-failure",
    video: "retain-on-failure"
  },
  projects: [
    {
      name: "chromium-1280x800",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } }
    },
    {
      name: "chromium-1440x900",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }
    },
    {
      name: "chromium-768x1024",
      use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } }
    },
    {
      name: "chromium-390x844",
      use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 } }
    },
    {
      name: "firefox-1280x800",
      use: { ...devices["Desktop Firefox"], viewport: { width: 1280, height: 800 } }
    },
    {
      name: "webkit-1280x800",
      use: { ...devices["Desktop Safari"], viewport: { width: 1280, height: 800 } }
    },
  ],
  webServer: {
    command: "npm run build && python ../tests/run_ui7_playwright_server.py",
    url: "http://127.0.0.1:8765/api/v1/health",
    timeout: 120_000,
    reuseExistingServer: false
  }
});
