import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["src/main/**/*.test.ts", "tests/unit/**/*.test.{ts,tsx}", "tests/mock-server/**/*.test.ts"],
    environment: "node",
  },
});
