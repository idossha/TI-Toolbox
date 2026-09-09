// @vitest-environment node
import { createServer } from "node:net";
import { describe, expect, it } from "vitest";
import { availableHostPort } from "../../scripts/devHost";

describe("host development port", () => {
  it("keeps an existing server running and chooses another port", async () => {
    const occupied = createServer();
    await new Promise<void>((resolve) => occupied.listen(0, "127.0.0.1", resolve));
    try {
      const address = occupied.address();
      if (!address || typeof address === "string") throw new Error("Expected TCP address");
      const selected = await availableHostPort(address.port);
      expect(selected).toBeGreaterThan(address.port);
      expect(occupied.listening).toBe(true);
    } finally {
      await new Promise<void>((resolve) => occupied.close(() => resolve()));
    }
  });
});
