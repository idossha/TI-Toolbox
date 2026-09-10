import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/unit/**/*.test.{ts,tsx}", "tests/mock-server/**/*.test.ts"],
    environment: "node",
  },
});
