/**
 * The Ex/mEx bucket ↔ electrode mapping (`pages/optimizer/buckets.ts`).
 *
 * The pane draws what these functions say and nothing else, so they are checked against the rules
 * themselves — a bucket's channel is its pair number, both poles share it, the pool is one hue, and
 * a click toggles within one bucket without touching another.
 */
import { describe, expect, it } from "vitest";
import {
  POOL_KEY,
  bucketChannel,
  bucketChannels,
  bucketLabel,
  bucketLegendRows,
  exBucketView,
  mexBucketView,
  resolveActiveBucket,
  toggleBucketElectrode,
} from "../../src/renderer/pages/optimizer/buckets";
import { defaultExFormState, defaultMExFormState } from "../../src/renderer/pages/optimizer/exConfig";
import { channelCss } from "../../src/renderer/pages/_shared/scene/model";

describe("bucket → channel", () => {
  it("gives both poles of a pair the same channel", () => {
    expect(bucketChannel("e1_plus")).toBe(0);
    expect(bucketChannel("e1_minus")).toBe(0);
    expect(bucketChannel("e2_plus")).toBe(1);
    expect(bucketChannel("e2_minus")).toBe(1);
    expect(bucketChannel("e4_minus")).toBe(3);
  });

  it("puts the pool on channel 1", () => {
    expect(bucketChannel(POOL_KEY)).toBe(0);
    expect(bucketLabel(POOL_KEY)).toBe("Pool");
  });

  it("paints E1± and E2± in the Simulator's own pair hues", () => {
    // The same function the montage legend's chips call: "pair 2 is orange" has to mean the same
    // thing in the Simulator's pane and in the Optimizer's.
    expect(channelCss(bucketChannel("e1_minus"))).toBe(channelCss(0));
    expect(channelCss(bucketChannel("e2_plus"))).toBe(channelCss(1));
    expect(channelCss(bucketChannel("e1_plus"))).not.toBe(channelCss(bucketChannel("e2_plus")));
  });
});

describe("electrode → channel", () => {
  const view = exBucketView({
    ...defaultExFormState(),
    buckets: { e1_plus: ["Fp1", "Fp2"], e1_minus: ["O1"], e2_plus: ["C3"], e2_minus: [] },
  });

  it("maps every bucketed electrode and leaves the rest absent", () => {
    expect(bucketChannels(view)).toEqual({ Fp1: 0, Fp2: 0, O1: 0, C3: 1 });
    expect(bucketChannels(view).Cz).toBeUndefined();
  });

  it("gives an electrode in two buckets the first bucket's channel", () => {
    const shared = exBucketView({ ...defaultExFormState(), buckets: { e1_plus: ["Cz"], e1_minus: [], e2_plus: ["Cz"], e2_minus: [] } });
    expect(bucketChannels(shared)).toEqual({ Cz: 0 });
  });

  it("gives the whole pool one hue", () => {
    const pooled = exBucketView({ ...defaultExFormState(), electrodeMode: "all", pool: ["Fp1", "C3", "O2"] });
    expect(pooled.keys).toEqual([POOL_KEY]);
    expect(bucketChannels(pooled)).toEqual({ Fp1: 0, C3: 0, O2: 0 });
  });

  it("spreads mEx's eight buckets over four channels", () => {
    const mex = mexBucketView({
      buckets: { ...defaultMExFormState().buckets, e1_plus: ["A"], e2_minus: ["B"], e3_plus: ["C"], e4_minus: ["D"] },
    });
    expect(bucketChannels(mex)).toEqual({ A: 0, B: 1, C: 2, D: 3 });
    expect(bucketLegendRows(mex).map((r) => r.channel)).toEqual([0, 0, 1, 1, 2, 2, 3, 3]);
  });

  it("counts each bucket in the legend", () => {
    expect(bucketLegendRows(view).map((r) => [r.label, r.count])).toEqual([
      ["E1+", 2],
      ["E1-", 1],
      ["E2+", 1],
      ["E2-", 0],
    ]);
  });
});

describe("toggling an electrode into a bucket", () => {
  const view = exBucketView({
    ...defaultExFormState(),
    buckets: { e1_plus: ["Fp1"], e1_minus: [], e2_plus: ["Fp1"], e2_minus: [] },
  });

  it("adds an electrode the bucket does not have", () => {
    expect(toggleBucketElectrode(view, "e1_plus", "C3").e1_plus).toEqual(["Fp1", "C3"]);
  });

  it("removes one it does", () => {
    expect(toggleBucketElectrode(view, "e1_plus", "Fp1").e1_plus).toEqual([]);
  });

  it("never touches another bucket — two buckets may legitimately share an electrode", () => {
    const next = toggleBucketElectrode(view, "e1_plus", "Fp1");
    expect(next.e2_plus).toEqual(["Fp1"]);
    expect(next.e1_minus).toEqual([]);
  });

  it("is a no-op, identically, for a bucket this view does not have", () => {
    expect(toggleBucketElectrode(view, "e3_plus", "C3")).toBe(view.values);
  });

  it("toggles the pool through the same call", () => {
    const pooled = exBucketView({ ...defaultExFormState(), electrodeMode: "all", pool: ["Fp1"] });
    expect(toggleBucketElectrode(pooled, POOL_KEY, "C3")[POOL_KEY]).toEqual(["Fp1", "C3"]);
    expect(toggleBucketElectrode(pooled, POOL_KEY, "Fp1")[POOL_KEY]).toEqual([]);
  });
});

describe("the active bucket", () => {
  const ex = exBucketView(defaultExFormState());
  const pooled = exBucketView({ ...defaultExFormState(), electrodeMode: "all" });

  it("defaults to E1+", () => {
    expect(resolveActiveBucket(ex, null)).toBe("e1_plus");
  });

  it("defaults to the pool when that is all there is", () => {
    expect(resolveActiveBucket(pooled, null)).toBe(POOL_KEY);
  });

  it("keeps a bucket this view has", () => {
    expect(resolveActiveBucket(ex, "e2_minus")).toBe("e2_minus");
  });

  it("falls back when the row switched away from the stored bucket", () => {
    // Bucketed → pooled, or Ex → mEx: a stale key would point the next click at a bucket that is
    // not on screen, and the click would go nowhere.
    expect(resolveActiveBucket(pooled, "e2_minus")).toBe(POOL_KEY);
    expect(resolveActiveBucket(ex, POOL_KEY)).toBe("e1_plus");
    expect(resolveActiveBucket(mexBucketView(defaultMExFormState()), "e4_plus")).toBe("e4_plus");
  });
});
