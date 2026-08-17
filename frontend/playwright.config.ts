import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  retries: 0,
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  webServer: { command: 'set "RADAR_E2E=1" && npm run dev', url: "http://127.0.0.1:3000", reuseExistingServer: true, timeout: 120_000 },
  projects: [{ name: "edge", use: { ...devices["Desktop Chrome"], channel: "msedge" } }],
});
