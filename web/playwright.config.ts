import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  outputDir: "../review/UI-7/runs/playwright",
  use: {
    baseURL: "http://127.0.0.1:8765",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure"
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ],
  webServer: {
    command: "npm run build && ../.venv/bin/python ../tests/run_ui7_playwright_server.py",
    url: "http://127.0.0.1:8765/api/v1/health",
    timeout: 120_000,
    reuseExistingServer: false
  }
});
