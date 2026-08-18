import { defineConfig, devices } from "@playwright/test";

const e2ePort = Number(process.env.RADAR_E2E_PORT ?? "3000");
const e2eBaseUrl = `http://127.0.0.1:${e2ePort}`;
const reuseExistingServer = process.env.RADAR_E2E_REUSE === "true" || e2ePort === 3000;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  retries: 0,
  use: { baseURL: e2eBaseUrl, trace: "retain-on-failure" },
  webServer: { command: `set "RADAR_E2E=1" && npm run dev -- -p ${e2ePort}`, url: e2eBaseUrl, reuseExistingServer, timeout: 120_000 },
  projects: [{ name: "edge", use: { ...devices["Desktop Chrome"], channel: "msedge" } }],
});
