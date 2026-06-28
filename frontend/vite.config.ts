import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// The app is served by the Python runtime under /app/ in production
// (build.outDir → runtime/static/app). In dev, Vite proxies the API and the
// WebSocket to the running FastAPI server on :8765 so relative /api and /ws
// URLs work identically in both modes.
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  build: {
    outDir: "../runtime/static/app",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": { target: "http://localhost:8765", changeOrigin: true },
      "/ws": { target: "http://localhost:8765", ws: true },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Vitest owns unit tests under src/; Playwright owns tests/ (see playwright.config.ts).
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
