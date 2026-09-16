/**
 * The progress line a downloading part-row shows, derived from `GET /api/example-data` alone.
 *
 * This is what replaced `useExampleDataJobs`: a download is not a job, so its progress is not a
 * job stream but four fields on the part's own status, polled while anything is in flight.
 */
import { describe, expect, it } from "vitest";
import {
  formatBytes,
  isBusy,
  progressPercent,
  progressText,
  splitPartId,
} from "../../src/renderer/app/exampleData/api";
import type { ExampleStatus } from "../../src/renderer/app/exampleData/api";

const status = (over: Partial<ExampleStatus> = {}): ExampleStatus => ({
  id: "ernie/headmodel",
  dataset: "ernie",
  part: "headmodel",
  installed: false,
  bytes: 591621145,
  downloading: false,
  queued: false,
  received: 0,
  total: 0,
  ...over,
});

describe("progressText", () => {
  it("shows nothing for a part that is not downloading", () => {
    expect(progressText(undefined)).toBeUndefined();
    expect(progressText(status())).toBeUndefined();
    expect(progressText(status({ installed: true }))).toBeUndefined();
  });

  /** The server reports `downloading` before the first byte arrives; a bare `0%` reads as stuck. */
  it("says Starting… before any total is known", () => {
    expect(progressText(status({ downloading: true }))).toBe("Starting…");
  });

  /** A part POSTed while another is in flight waits on the server's worker queue. */
  it("says Queued for a part waiting its turn", () => {
    expect(progressText(status({ queued: true }))).toBe("Queued");
  });

  /**
   * Both numbers in one unit, named once: `433 / 455 MB`. The old line was
   * `95% · 433 MB / 455 MB` in a grey box, which said the same thing three times — the bar is
   * the percentage.
   */
  it("reports both sizes in one unit once bytes are flowing", () => {
    expect(progressText(status({ downloading: true, received: 454000000, total: 477129122 }))).toBe(
      "433 / 455 MB",
    );
  });

  it("never over-reports if the server's received exceeds its total", () => {
    expect(progressText(status({ downloading: true, received: 700, total: 600 }))).toBe("1 / 1 kB");
  });
});

describe("progressPercent", () => {
  it("is the bar's width, and undefined while the total is unknown", () => {
    expect(progressPercent(status())).toBeUndefined();
    expect(progressPercent(status({ downloading: true }))).toBeUndefined();
    expect(progressPercent(status({ downloading: true, received: 50, total: 200 }))).toBe(25);
    expect(progressPercent(status({ downloading: true, received: 999, total: 200 }))).toBe(100);
  });
});

describe("isBusy", () => {
  it("covers both the running part and the ones queued behind it", () => {
    expect(isBusy(status())).toBe(false);
    expect(isBusy(status({ downloading: true }))).toBe(true);
    expect(isBusy(status({ queued: true }))).toBe(true);
  });
});

describe("formatBytes and splitPartId", () => {
  it("uses the unit a part is actually measured in", () => {
    expect(formatBytes(591621145)).toBe("564 MB");
    expect(formatBytes(14915970)).toBe("14 MB");
    expect(formatBytes(2 * 1024 ** 3)).toBe("2.0 GB");
  });

  it("splits a catalogue id into the two path segments the route takes", () => {
    expect(splitPartId("ernie/headmodel")).toEqual(["ernie", "headmodel"]);
    expect(splitPartId("mni152/nifti")).toEqual(["mni152", "nifti"]);
  });
});
