/**
 * The pure core of the run pages' scene pane (lane SCC): every mapping between what the *form*
 * holds and what the *scene* draws. It is the half of decision S6 ("both directions stay in sync")
 * that can be checked without a GPU, a DOM or a server.
 *
 * Every expected value below is arithmetic on a hand-written fixture — a legend typed from the
 * shape `GET /api/scene/regions` really returns, and coordinates whose centroids are computable in
 * closed form. Nothing here is read back from the implementation.
 */
import { describe, expect, it } from "vitest";
import {
  advanceSlot,
  applyElectrodePick,
  channelByElectrode,
  firstEmptySlot,
  markerIndicesFor,
  markersFromElectrodes,
  placedElectrodes,
  DEFAULT_OPACITY,
  regionCentroids,
  regionKey,
  regionsFromWireLabels,
  roundCoord,
  slotAt,
  slotLabel,
  slotOf,
  sphereMarkers,
  wireLabelsFor,
  withSlot,
  type Pair,
} from "../../src/renderer/pages/_shared/scene/model";
import { hasActiveJob, resolveTab } from "../../src/renderer/pages/_shared/run/RunPaneTabs";
import type { SceneLegendRow } from "../../src/renderer/pages/_shared/scene/api";

/**
 * Four rows in the shape the live server answered with on 2026-09-04
 * (`/api/scene/regions?subject=ernie&atlas=DK40`): `label` is the uint16 wire value, `id` is the
 * `.annot` row, and lh row 1 and rh row 1 are DIFFERENT regions with different wire labels — which
 * is the whole reason `hemi` is part of the key.
 */
const LEGEND: SceneLegendRow[] = [
  { label: 1, id: 1, hemi: "lh", name: "bankssts", color: "#196428" },
  { label: 2, id: 2, hemi: "lh", name: "caudalanteriorcingulate", color: "#7d64a0" },
  { label: 36, id: 1, hemi: "rh", name: "bankssts", color: "#196428" },
  { label: 37, id: 2, hemi: "rh", name: "caudalanteriorcingulate", color: "#7d64a0" },
];

describe("region mapping: the form's regions <-> the payload's uint16 labels", () => {
  it("keys on (hemi, id), so the two hemispheres' row 1 are two different labels", () => {
    expect(regionKey({ id: 1, hemi: "lh" })).toBe("lh:1");
    expect(regionKey({ id: 1, hemi: "rh" })).toBe("rh:1");
    expect(wireLabelsFor(LEGEND, [{ id: 1, hemi: "lh" }])).toEqual([1]);
    expect(wireLabelsFor(LEGEND, [{ id: 1, hemi: "rh" }])).toEqual([36]);
  });

  it("round-trips a mixed selection in the order it was given", () => {
    const regions = [
      { id: 2, name: "caudalanteriorcingulate", hemi: "rh" as const },
      { id: 1, name: "bankssts", hemi: "lh" as const },
    ];
    const labels = wireLabelsFor(LEGEND, regions);
    expect(labels).toEqual([37, 1]);
    expect(regionsFromWireLabels(LEGEND, labels)).toEqual(regions);
  });

  it("drops a region the atlas does not contain instead of mapping it onto label 0", () => {
    // 0 means "no region" in the payload (lane SCA), so mapping an unknown region onto it would
    // highlight every unlabelled vertex — the cerebellum and brainstem included.
    expect(wireLabelsFor(LEGEND, [{ id: 999, hemi: "lh" }])).toEqual([]);
    expect(regionsFromWireLabels(LEGEND, [0, 4242])).toEqual([]);
  });

  it("collapses a duplicate rather than highlighting the same region twice", () => {
    expect(wireLabelsFor(LEGEND, [{ id: 1, hemi: "lh" }, { id: 1, hemi: "lh" }])).toEqual([1]);
  });
});

describe("montage mode: a click toggles the electrode into the current pair slot", () => {
  const empty = (): Pair[] => [
    ["", ""],
    ["", ""],
  ];

  it("addresses slots as pair-major, A then B", () => {
    const pairs: Pair[] = [
      ["F3", "F4"],
      ["P3", "P4"],
    ];
    expect([0, 1, 2, 3].map((i) => slotAt(pairs, i))).toEqual(["F3", "F4", "P3", "P4"]);
    expect(slotOf(pairs, "P3")).toBe(2);
    expect(slotOf(pairs, "Cz")).toBe(-1);
    expect(slotLabel(pairs, 2)).toBe("Pair 2 · A");
    expect(slotLabel(pairs, 3)).toBe("Pair 2 · B");
  });

  it("fills the slots in order and advances the cursor", () => {
    let state = { pairs: empty(), cursor: 0 };
    for (const name of ["F3", "F4", "P3", "P4"]) state = applyElectrodePick(state.pairs, state.cursor, name);
    expect(state.pairs).toEqual([
      ["F3", "F4"],
      ["P3", "P4"],
    ]);
    // Every slot is full, so the cursor is simply the next one, wrapped.
    expect(state.cursor).toBe(0);
  });

  it("clicking a placed electrode removes it and parks the cursor on the slot it vacated", () => {
    const pairs: Pair[] = [
      ["F3", "F4"],
      ["P3", "P4"],
    ];
    const removed = applyElectrodePick(pairs, 0, "P3");
    expect(removed.pairs).toEqual([
      ["F3", "F4"],
      ["", "P4"],
    ]);
    expect(removed.cursor).toBe(2);
    // ...so the very next click refills exactly that slot: the "I mis-clicked" repair.
    const refilled = applyElectrodePick(removed.pairs, removed.cursor, "C3");
    expect(refilled.pairs).toEqual([
      ["F3", "F4"],
      ["C3", "P4"],
    ]);
  });

  it("replaces at the cursor when the montage is already full, so a full montage is still editable", () => {
    const pairs: Pair[] = [
      ["F3", "F4"],
      ["P3", "P4"],
    ];
    const replaced = applyElectrodePick(pairs, 1, "Cz");
    expect(replaced.pairs).toEqual([
      ["F3", "Cz"],
      ["P3", "P4"],
    ]);
    expect(replaced.cursor).toBe(2);
  });

  it("advances cyclically to the next EMPTY slot, so a 4-pair mTI montage wraps to pair 1", () => {
    const pairs: Pair[] = [
      ["", "F4"],
      ["P3", "P4"],
      ["C3", "C4"],
      ["O1", "O2"],
    ];
    expect(advanceSlot(pairs, 7)).toBe(0);
    expect(firstEmptySlot(pairs)).toBe(0);
    // Nothing empty: plain next, wrapped.
    expect(advanceSlot(withSlot(pairs, 0, "F3"), 7)).toBe(0);
  });

  it("colours a marker by the pair it belongs to and selects exactly the placed electrodes", () => {
    const pairs: Pair[] = [
      ["F3", "F4"],
      ["P3", ""],
    ];
    expect(channelByElectrode(pairs)).toEqual({ F3: 0, F4: 0, P3: 1 });
    const markers = markersFromElectrodes(
      [
        { name: "F3", world: [-40, 30, 50] },
        { name: "Cz", world: [0, 0, 90] },
        { name: "P3", world: [-40, -60, 50] },
      ],
      channelByElectrode(pairs),
    );
    expect(markers.map((m) => m.channel)).toEqual([0, undefined, 1]);
    expect(placedElectrodes(pairs)).toEqual(["F3", "F4", "P3"]);
    // F4 is not on this net, so it contributes no marker index rather than an out-of-range one.
    expect(markerIndicesFor(markers, placedElectrodes(pairs))).toEqual([0, 2]);
  });

  it("does nothing at all when there are no pairs to fill", () => {
    expect(applyElectrodePick([], 0, "F3")).toEqual({ pairs: [], cursor: 0 });
    expect(slotLabel([], 0)).toBe("no pairs");
  });
});

describe("sphere mode: one clickable point per atlas region, snapped to a real vertex", () => {
  // Two regions, both with closed-form centroids:
  //   label 1 — a 2x2 square in z = 0: centroid (1, 1, 0), every corner sqrt(2) away (first wins);
  //   label 2 — a three-point arc: centroid (0, 10/3, 0), which lies 3.33 mm from NO vertex and
  //             is nearest (0, 10, 0) at 6.67 mm — the case that proves the snap is doing work.
  const positions = new Float32Array([
    0, 0, 0, 2, 0, 0, 0, 2, 0, 2, 2, 0, // label 1
    10, 0, 0, 0, 10, 0, -10, 0, 0, // label 2
    5, 5, 5, // label 0 = no region
  ]);
  const labels = new Uint16Array([1, 1, 1, 1, 2, 2, 2, 0]);
  const legend: SceneLegendRow[] = [
    { label: 1, id: 11, hemi: "lh", name: "square", color: "#000000" },
    { label: 2, id: 12, hemi: "rh", name: "arc", color: "#ffffff" },
  ];

  it("returns the served vertex nearest each region's centroid, never the centroid itself", () => {
    const centroids = regionCentroids(positions, labels, legend);
    expect(centroids.map((c) => c.name)).toEqual(["square", "arc"]);
    expect(centroids[0]?.world).toEqual([0, 0, 0]);
    expect(centroids[0]?.vertices).toBe(4);
    // The arc's arithmetic centroid is (0, 3.333, 0) — not a vertex, and 3.3 mm inside the arc.
    expect(centroids[1]?.world).toEqual([0, 10, 0]);
    expect(centroids[1]?.vertices).toBe(3);
  });

  it("ignores label 0 (no region) and regions below the vertex floor", () => {
    expect(regionCentroids(positions, labels, legend).every((c) => c.label !== 0)).toBe(true);
    expect(regionCentroids(positions, labels, legend, 4).map((c) => c.name)).toEqual(["square"]);
  });

  it("draws the current centre and nothing else — the centroid snap is gone", () => {
    // Before `onPickAt`, this returned one clickable marker per region centroid and a click
    // snapped the centre to the nearest of them (lane SCC's C11). A pick reports its world point
    // now, so the only marker left is the centre the form already holds.
    expect(sphereMarkers(null)).toEqual([]);
    expect(sphereMarkers([1, 2, 3])).toEqual([
      { id: "sphere-centre", label: "Sphere centre", world: [1, 2, 3], channel: 0 },
    ]);
  });

  it("rounds a picked coordinate to 0.1 mm before it reaches a form field", () => {
    expect(roundCoord([-26.080394138417162, 113.65480801883132, 19.072867841317812])).toEqual({
      x: -26.1,
      y: 113.7,
      z: 19.1,
    });
  });
});

describe("the Terminal · Scene tab rule (S7)", () => {
  const jobs = (kind: string, state: string) => [{ kind, state }];

  it("shows the Scene while configuring and the Terminal once a job of this kind is active", () => {
    expect(resolveTab(null, false)).toBe("scene");
    expect(resolveTab(null, true)).toBe("terminal");
  });

  it("never takes a tab away from a user who chose one", () => {
    // The failure this prevents: watching the scene while a batch runs would be impossible if
    // every new job of the kind yanked the pane back to the log.
    expect(resolveTab("scene", true)).toBe("scene");
    expect(resolveTab("terminal", false)).toBe("terminal");
  });

  it("counts only queued/running jobs of this page's own kinds", () => {
    expect(hasActiveJob(jobs("sim", "running"), ["sim"])).toBe(true);
    expect(hasActiveJob(jobs("sim", "queued"), ["sim"])).toBe(true);
    expect(hasActiveJob(jobs("sim", "succeeded"), ["sim"])).toBe(false);
    expect(hasActiveJob(jobs("flex", "running"), ["sim"])).toBe(false);
    expect(hasActiveJob(jobs("flex", "running"), ["flex", "ex", "mex"])).toBe(true);
  });
});

describe("surface opacity defaults", () => {
  it("offers a default for the skin only — the grey matter is always opaque", () => {
    // The slider is driven off this map, and a `gm` entry here would both bring the control back
    // and give a page-session a translucent value to remember (maintainer, 2026-09-06).
    expect(DEFAULT_OPACITY.skin).toBeGreaterThan(0);
    expect(DEFAULT_OPACITY.skin).toBeLessThan(1);
    expect(Object.keys(DEFAULT_OPACITY)).toEqual(["skin"]);
  });
});
