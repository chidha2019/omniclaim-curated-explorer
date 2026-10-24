import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [
    ["list"],
    ["junit", { outputFile: "test-results/e2e.xml" }],
    ["html", { open: "never" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "node ../tools/dev.mjs",
    url: "http://127.0.0.1:5173/api/v1/config",
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
