import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    fs: {
      // Allow importing ../../shared and ../../integrations (siblings in the repo root).
      allow: [path.resolve(__dirname, ".."), path.resolve(__dirname)],
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
