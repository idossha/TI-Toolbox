/**
 * What the pane says about an atlas' labels (user report, 2026-11-07: grey cortex, then colours, with
 * nothing saying they were coming), and the version every cached guide URL carries (the same day: a
 * year-old cortex answered from the HTTP cache left a new atlas' labels unpainted, silently).
 *
 * The sentences are authored here from the requirement; the pane's use of them, on a real load, is
 * in tests/e2e/scene-pane-status.spec.ts.
 *
 * Run: npx vitest run tests/unit/scene-labels-status.test.ts
 */
import { describe, expect, it } from "vitest";
import { atlasLabelsStatus } from "../../src/renderer/pages/_shared/scene/model";
import { guideLabelsUrl, guideSurfaceUrl } from "../../src/renderer/pages/_shared/scene/api";

const arrived = {
  atlas: "a2009s",
  legendPending: false,
  legendFailed: false,
  legendRows: 150,
  surfaceExpected: true,
  surfaceReady: true,
  labelsPending: false,
  labelsError: null,
  misaligned: null,
};
const loading = { kind: "loading", text: "Loading a2009s labels…" };

describe("atlasLabelsStatus", () => {
  it("says nothing once the labels are on the surface", () => {
    expect(atlasLabelsStatus(arrived)).toBeNull();
  });

  it.each([
    ["the legend is on its way", { legendPending: true, legendRows: 0, labelsPending: true }],
    ["the labels are on their way", { labelsPending: true }],
    ["the surface they colour is on its way", { surfaceReady: false }],
  ])("says loading while %s", (_, change) => {
    expect(atlasLabelsStatus({ ...arrived, ...change })).toEqual(loading);
  });

  it("states a failed fetch and a payload for another surface, rather than staying grey", () => {
    expect(atlasLabelsStatus({ ...arrived, labelsError: "HTTP 500" })).toEqual({
      kind: "failed",
      text: "The a2009s labels could not be loaded: HTTP 500",
    });
    expect(atlasLabelsStatus({ ...arrived, misaligned: "labels are for 3 vertices, the surface has 2" })).toEqual({
      kind: "failed",
      text: "The a2009s labels were not applied: labels are for 3 vertices, the surface has 2.",
    });
  });

  it("never waits for what will not come", () => {
    // No atlas; an atlas with no regions, whose labels query never runs; a surface the head lacks.
    expect(atlasLabelsStatus({ ...arrived, atlas: null })).toBeNull();
    expect(atlasLabelsStatus({ ...arrived, legendRows: 0, labelsPending: true })).toBeNull();
    expect(atlasLabelsStatus({ ...arrived, surfaceExpected: false, surfaceReady: false })).toBeNull();
    // A failed legend is the hint's sentence, not a second one here.
    expect(atlasLabelsStatus({ ...arrived, legendFailed: true, legendPending: true })).toBeNull();
  });
});

describe("a guide payload URL names the guide's version", () => {
  it("is a different URL for different content", () => {
    expect(guideSurfaceUrl("gm", "mni", "aaa")).toBe("/api/guide/surface?part=gm&format=tvsc&guide=mni&v=aaa");
    expect(guideSurfaceUrl("gm", "mni", "bbb")).not.toBe(guideSurfaceUrl("gm", "mni", "aaa"));
    expect(guideLabelsUrl("DK40", undefined, "aaa")).toBe("/api/guide/labels?atlas=DK40&format=tvsc&v=aaa");
  });
});
