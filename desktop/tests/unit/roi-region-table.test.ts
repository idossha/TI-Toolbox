/**
 * The ROI picker's atlas selections build the same ROI the server builds for an agent (2026-10-08).
 *
 * The cases come from `tests/fixtures/region_rois.json` (groundTruth: authored), which
 * `tests/test_region_rois.py` reads for `tit.catalog.region_roi` (the agent's `find_regions`), so
 * the two constructions cannot drift. The picker keeps its own (synchronous) construction because
 * it builds the ROI on every chip click for the live plan; this table is the one rule both follow.
 * Reproduce: cd desktop && npx vitest run tests/unit/roi-region-table.test.ts
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { roiToConfig, type RoiRegion, type RoiValue, type TissueKind } from "../../src/renderer/pages/_shared/roi/types";

interface Case {
  why: string;
  atlas: { path: string; kind: "surface" | "volume" };
  regions: RoiRegion[];
  tissues?: TissueKind;
  space?: "subject" | "mni";
  roi: unknown;
}

const table = JSON.parse(readFileSync(resolve(__dirname, "../../../tests/fixtures/region_rois.json"), "utf-8")) as { cases: Case[] };

describe("shared atlas-region ROI table", () => {
  it("has cases to check", () => {
    expect(table.cases.length).toBeGreaterThanOrEqual(4);
  });

  it.each(table.cases)("$why", (c) => {
    const regions = c.regions.map(({ id, name, hemi }) => ({ id, name, ...(hemi ? { hemi } : {}) }));
    const value: RoiValue =
      c.atlas.kind === "surface"
        ? { mode: "cortical", space: "subject", atlas: "A", regions }
        : { mode: "subcortical", space: c.space ?? "subject", atlas: "A", regions, tissues: c.tissues ?? "GM" };
    expect(roiToConfig(value, (id) => (id === "A" ? { path: c.atlas.path } : undefined))).toStrictEqual(c.roi);
  });
});
