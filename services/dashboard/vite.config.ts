/// <reference types="vitest" />
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Read-only import of the shared contract types. Never edit /contracts from here.
      "@contracts": fileURLToPath(new URL("../../contracts", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // Localhost only: the backend trusts the dev proxy as a loopback caller for its admin endpoints.
    host: "127.0.0.1",
    fs: { allow: ["..", "../../contracts"] },
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    // Tests must not depend on a developer's .env.local (live mode, a Sentry DSN): pin every variable.
    env: {
      VITE_USE_MOCKS: "true",
      VITE_API_BASE: "",
      VITE_SENTRY_ORG: "",
      VITE_SENTRY_DSN: "",
      VITE_SENTRY_REPLAY_RATE: "0.1",
    },
  },
});
