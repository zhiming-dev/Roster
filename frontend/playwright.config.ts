import { defineConfig } from "@playwright/test";

// Smoke tests run against the Vite dev server (npm run dev) with the Python
// runtime live on :8765 (so /api and /ws proxy through). Not run in CI yet.
export default defineConfig({
  testDir: "./tests",
  use: { baseURL: "http://localhost:5173" },
  reporter: "list",
});
