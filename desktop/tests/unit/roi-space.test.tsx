// @vitest-environment jsdom
/**
 * One space, two controls (`docs/dev/DECISIONS.md § 2026-09-17`).
 *
 * The Subject | MNI switch exists twice on a targeting page — above the scene pane and inside the
 * ROI picker's panel — and both are `<RoiSpaceControl>` writing the row's single `RoiValue.space`.
 * The failure these tests prevent is the one two fields would allow: the pane says MNI, the picker
 * says Subject, and the job runs on whichever the config builder read.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { RoiSpaceControl } from "../../src/renderer/pages/_shared/roi/RoiPicker";
import { emptyRoi, roiSpace, spaceChangeNote, withRoiSpace, type RoiValue } from "../../src/renderer/pages/_shared/roi/types";

describe("every ROI mode carries one space", () => {
  it("emptyRoi seeds it on all five modes", () => {
    for (const mode of ["spherical", "cortical", "subcortical", "saved", "mask"] as const) {
      expect(roiSpace(emptyRoi(mode, "mni"))).toBe("mni");
      expect(roiSpace(emptyRoi(mode, "subject"))).toBe("subject");
    }
  });

  it("a fresh subcortical row targets the subject's own labeling in subject space, nothing in MNI", () => {
    expect((emptyRoi("subcortical", "subject") as Extract<RoiValue, { mode: "subcortical" }>).atlas).toBe("labeling.nii.gz");
    // `labeling.nii.gz` is a per-subject file; naming it in MNI would be a target that does not exist.
    expect((emptyRoi("subcortical", "mni") as Extract<RoiValue, { mode: "subcortical" }>).atlas).toBeUndefined();
  });
});

describe("withRoiSpace", () => {
  it("clears an atlas selection that has no equivalent, and says so", () => {
    const roi: RoiValue = { mode: "subcortical", space: "subject", atlas: "labeling.nii.gz", regions: [{ id: 12, name: "Left-Putamen" }], tissues: "GM" };
    const moved = withRoiSpace(roi, "mni") as Extract<RoiValue, { mode: "subcortical" }>;
    expect(moved.space).toBe("mni");
    expect(moved.atlas).toBeUndefined();
    expect(moved.regions).toEqual([]);
    expect(spaceChangeNote(roi, "mni")).toContain("labeling.nii.gz");
  });

  it("keeps coordinates, radii and mask paths — they are reinterpreted, not lost", () => {
    const sphere: RoiValue = { mode: "spherical", space: "subject", spheres: [{ x: 1, y: 2, z: 3, radius: 5 }], volumetric: false, tissues: "GM" };
    expect(withRoiSpace(sphere, "mni")).toEqual({ ...sphere, space: "mni" });
    expect(spaceChangeNote(sphere, "mni")).toBeNull();
    const mask: RoiValue = { mode: "mask", space: "subject", path: "/p/roi.nii.gz", tissues: "GM" };
    expect(withRoiSpace(mask, "mni")).toEqual({ ...mask, space: "mni" });
  });

  it("is the identity when the space is already the one asked for", () => {
    const roi = emptyRoi("cortical", "mni");
    expect(withRoiSpace(roi, "mni")).toBe(roi);
    expect(spaceChangeNote(roi, "mni")).toBeNull();
  });
});

it("two RoiSpaceControls over one value stay in sync", async () => {
  const client = new QueryClient();
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  const seen: RoiValue[] = [];
  function Both({ value }: { value: RoiValue }) {
    const [roi, setRoi] = React.useState(value);
    const write = (next: RoiValue) => { seen.push(next); setRoi(next); };
    return (
      <>
        <RoiSpaceControl value={roi} onChange={write} label="Target space" id="above-pane" />
        <RoiSpaceControl value={roi} onChange={write} label="Atlas space" id="in-picker" />
      </>
    );
  }
  try {
    await act(async () => root.render(<QueryClientProvider client={client}><Both value={emptyRoi("subcortical", "subject")} /></QueryClientProvider>));
    const pressed = () => [...container.querySelectorAll('[data-state="on"]')].map((n) => (n as HTMLElement).textContent);
    expect(pressed()).toEqual(["Subject", "Subject"]);
    // Drive the one above the pane; the one in the picker must follow, because there is one value.
    const above = container.querySelector('[data-testid="above-pane"]') as HTMLElement;
    const mni = [...above.querySelectorAll("button")].find((b) => b.textContent === "MNI") as HTMLButtonElement;
    await act(async () => { mni.click(); });
    expect(roiSpace(seen[seen.length - 1]!)).toBe("mni");
    expect(pressed()).toEqual(["MNI", "MNI"]);
  } finally {
    act(() => root.unmount());
    container.remove();
    client.clear();
    vi.unstubAllGlobals();
  }
});
