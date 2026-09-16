/**
 * The progress line a downloading row shows, derived from `GET /api/example-data` alone.
 *
 * This is what replaced `useExampleDataJobs`: a download is not a job, so its progress is not a
 * job stream but three fields on the sample's own status, polled while anything is in flight.
 */
import { describe, expect, it } from "vitest";
import { formatBytes, layoutTag, progressText } from "../../src/renderer/app/exampleData/api";
import type { ExampleStatus } from "../../src/renderer/app/exampleData/api";

const status = (over: Partial<ExampleStatus> = {}): ExampleStatus => ({
  id: "ernie-headmodel",
  installed: false,
  bytes: 627045804,
  downloading: false,
  received: 0,
  total: 0,
  ...over,
});

describe("progressText", () => {
  it("shows nothing for a sample that is not downloading", () => {
    expect(progressText(undefined)).toBeUndefined();
    expect(progressText(status())).toBeUndefined();
    expect(progressText(status({ installed: true }))).toBeUndefined();
  });

  /** The server reports `downloading` before the first byte arrives; a bare `0%` reads as stuck. */
  it("says Starting… before any total is known", () => {
    expect(progressText(status({ downloading: true }))).toBe("Starting…");
  });

  it("reports a percentage and both sizes once bytes are flowing", () => {
    expect(progressText(status({ downloading: true, received: 313522902, total: 627045804 }))).toBe(
      "50% · 299 MB / 598 MB",
    );
  });

  it("never exceeds 100% if the server over-reports", () => {
    expect(progressText(status({ downloading: true, received: 700, total: 600 }))).toBe(
      "100% · 1 kB / 1 kB",
    );
  });
});

describe("formatBytes and layoutTag", () => {
  it("uses the unit a sample is actually measured in", () => {
    expect(formatBytes(627045804)).toBe("598 MB");
    expect(formatBytes(14915970)).toBe("14 MB");
    expect(formatBytes(2 * 1024 ** 3)).toBe("2.0 GB");
  });

  it("says what the sample lets you do the moment it lands", () => {
    expect(layoutTag("headmodel")).toBe("ready to simulate");
    expect(layoutTag("raw")).toBe("needs pre-processing");
  });
});
