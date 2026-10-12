import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "workflow.spec.ts",
  workers: 1,
  outputDir: "/tmp/roster_workflow_browser",
  use: { baseURL: "http://127.0.0.1:8876", viewport: { width: 1360, height: 950 } },
  reporter: "list",
  webServer: {
    command: "cd ../runtime && .venv/bin/python -m tests.workflow_server",
    url: "http://127.0.0.1:8876",
    reuseExistingServer: false,
  },
});
