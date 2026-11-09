import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";
import { loadEnv } from "vite";

// Opt-in integration tests against the live demo workspaces. Run after every seed.
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: {
    include: ["tests/live/**/*.test.ts"],
    env: loadEnv("", process.cwd(), ""),
    testTimeout: 60_000,
  },
});
