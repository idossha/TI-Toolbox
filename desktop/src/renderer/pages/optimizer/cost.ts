/**
 * The search-cost read-out (wireframes §4: "the cost of widening a bucket must be visible *while*
 * you widen it"). Pure and unit-tested — the page renders it beside the decision that changes it
 * *and* in the action-bar digest, and the two cannot disagree because they read one function.
 */
import type { ExFormState, MExFormState } from "./exConfig";
import { EX_BUCKET_KEYS, MEX_BUCKET_KEYS } from "./exConfig";
import type { FlexFormState } from "./flexConfig";
import { sweepCombinationCount, jobKindFor } from "./flexConfig";

export interface SearchCost {
  /** Distinct electrodes in the search space. */
  electrodes: number;
  /** Current splits swept per montage (ex only; 1 for mEx, whose current is fixed per pair). */
  splits: number;
  /** Electrode montages enumerated. */
  montages: number;
  /** `montages × splits` — the number of candidate evaluations. */
  combinations: number;
  /** Human-readable montage and evaluation counts, shared by the editor and digest. */
  line: string;
}

function n(value: number): string {
  return value.toLocaleString("en-US");
}

/**
 * Counts the splits of tit.opt.ex.logic.generate_current_ratios: no channel limit is the single
 * balanced split, a limit the descending sweep.
 */
export function currentSplits(totalCurrent: number, currentStep: number, channelLimit: number | null): number {
  if (!Number.isFinite(totalCurrent) || !Number.isFinite(currentStep) || !(currentStep > 0) || !(totalCurrent > 0)) return 0;
  if (channelLimit === null) return 1;
  const limit = channelLimit;
  if (!Number.isFinite(limit) || limit <= 0) return 0;
  const epsilon = currentStep * 0.01;
  const maximum = Math.min(limit, totalCurrent - currentStep);
  const minimum = Math.max(totalCurrent - limit, currentStep);
  // The first split starts at the channel limit, not necessarily a multiple of the step.
  return Math.max(0, Math.floor((maximum - minimum + epsilon) / currentStep) + 1);
}

/**
 * Whether the sweep's split list is its own mirror — it holds (b, a) for every (a, b). The TI
 * envelope ignores which channel is which, so channel 1 on pair P at a with channel 2 on Q at b
 * is then already evaluated as the swapped order at (b, a). Mirrors
 * `tit.opt.ex.logic.ratios_mirror_symmetric` on the descending sweep: the last channel-1 value
 * equals the first channel-2 value.
 */
export function splitsMirrorSymmetric(totalCurrent: number, currentStep: number, channelLimit: number | null): boolean {
  const count = currentSplits(totalCurrent, currentStep, channelLimit);
  if (count === 0 || channelLimit === null) return true;
  const first = Math.min(channelLimit, totalCurrent - currentStep);
  const last = first - (count - 1) * currentStep;
  return Math.abs(last - (totalCurrent - first)) <= 1e-9;
}

function choose(n: number, k: number): number {
  if (n < k) return 0;
  let result = 1;
  for (let i = 0; i < k; i++) result = (result * (n - i)) / (i + 1);
  return Math.round(result);
}

/**
 * Physical montages of a pool, as `tit.opt.ex.logic._pool_montages` enumerates them: TI_max
 * ignores a channel's polarity, so each 4-electrode set is split into pairs 3 ways, in both
 * channel orders only when the split list is not its own mirror. A repeated label is one electrode.
 */
function poolMontages(pool: string[], bothOrders: boolean): number {
  return choose(new Set(pool).size, 4) * 3 * (bothOrders ? 2 : 1);
}

/**
 * Tuples with one electrode from each bucket, all different — the mEx runner's bucket enumeration
 * (`_distinct_product`): no channel starts and ends on one electrode and no electrode serves two
 * poles. Counted without enumerating (eight buckets of 70 would be 5.8e14 tuples): a DP over the
 * set of filled positions, adding one distinct electrode at a time to any bucket that lists it.
 */
export function distinctTuples(buckets: Record<string, string[]>, keys: readonly string[]): number {
  const where = new Map<string, number[]>();
  keys.forEach((k, position) => {
    for (const e of new Set(buckets[k] ?? [])) where.set(e, [...(where.get(e) ?? []), position]);
  });
  let ways = new Map<number, number>([[0, 1]]);
  for (const positions of where.values()) {
    const next = new Map(ways);
    for (const [mask, count] of ways) {
      for (const position of positions) {
        const bit = 1 << position;
        if (mask & bit) continue;
        next.set(mask | bit, (next.get(mask | bit) ?? 0) + count);
      }
    }
    ways = next;
  }
  return ways.get((1 << keys.length) - 1) ?? 0;
}

/**
 * Physical montages of the Ex bucket product, as `tit.opt.ex.logic._bucket_montages` keeps them:
 * a channel is an unordered pair its two buckets hold either way round (TI ignores polarity), the
 * channels share no electrode, and two channels count once in either order when the split list
 * is its own mirror. Closed form over the channels' pairs (O(N²), not the product's N⁴).
 */
function bucketMontages(buckets: Record<string, string[]>, bothOrders: boolean): number {
  const pairs = (plus: string[] = [], minus: string[] = []) => {
    const out = new Set<string>();
    for (const p of plus) for (const m of minus) if (p !== m) out.add([p, m].sort().join("\0"));
    return out;
  };
  // Ordered disjoint (P, Q), P from a, Q from b: |a||b| − Σₑ degₐ(e)·deg_b(e) + |a ∩ b|.
  const disjoint = (a: Set<string>, b: Set<string>) => {
    const degB = new Map<string, number>();
    for (const q of b) for (const e of q.split("\0")) degB.set(e, (degB.get(e) ?? 0) + 1);
    let count = a.size * b.size;
    for (const p of a) {
      for (const e of p.split("\0")) count -= degB.get(e) ?? 0;
      if (b.has(p)) count += 1;
    }
    return count;
  };
  const r1 = pairs(buckets.e1_plus, buckets.e1_minus);
  const r2 = pairs(buckets.e2_plus, buckets.e2_minus);
  if (bothOrders) return disjoint(r1, r2);
  const both = new Set([...r1].filter((p) => r2.has(p)));
  return disjoint(r1, r2) - disjoint(both, both) / 2;
}

/** Distinct electrodes across the bucket set (an electrode used in two buckets is still one). */
function distinct(buckets: Record<string, string[]>, keys: readonly string[]): number {
  const seen = new Set<string>();
  for (const k of keys) for (const e of buckets[k] ?? []) seen.add(e);
  return seen.size;
}

export function exCost(form: ExFormState): SearchCost {
  const splits = currentSplits(form.totalCurrent, form.currentStep, form.channelLimit);
  const bothOrders = !splitsMirrorSymmetric(form.totalCurrent, form.currentStep, form.channelLimit);
  let electrodes: number;
  let montages: number;
  if (form.electrodeMode === "bucketed") {
    electrodes = distinct(form.buckets, EX_BUCKET_KEYS);
    montages = bucketMontages(form.buckets, bothOrders);
  } else {
    electrodes = new Set(form.pool).size;
    montages = poolMontages(form.pool, bothOrders);
  }
  const combinations = montages * splits;
  return {
    electrodes,
    splits,
    montages,
    combinations,
    line: `${n(electrodes)} electrodes · ${n(montages)} montage${montages === 1 ? "" : "s"} · ${n(splits)} current split${splits === 1 ? "" : "s"} · ${n(combinations)} iteration${combinations === 1 ? "" : "s"}`,
  };
}

export function mexCost(form: MExFormState): SearchCost {
  const electrodes = distinct(form.buckets, MEX_BUCKET_KEYS);
  const montages = distinctTuples(form.buckets, MEX_BUCKET_KEYS);
  // One fixed current per pair — mEx sweeps no amplitudes, so a "split" count would be a fiction.
  const splits = 1;
  return {
    electrodes,
    splits,
    montages,
    combinations: montages,
    // Symmetry search prunes this set by a factor the client cannot compute (it depends on the
    // net's mirror map), so the number is stated as the unpruned ceiling and said to be one.
    line: `${n(electrodes)} electrodes · 4 channels · ${n(montages)} combinations${form.symmetricBucket ? " before symmetry" : ""}`,
  };
}

/** A number field's accepted range, inclusive. One table feeds the input's min/max, its
 *  invalid flag and the row gate, so the three cannot disagree. */
export interface Bound {
  label: string;
  min: number;
  max: number;
}

/** Ex current fields: > 0 by physics and `ExConfig`; the upper ends are the inputs' own. */
export const EX_BOUNDS = {
  totalCurrent: { label: "Total current", min: 0.1, max: 10 },
  currentStep: { label: "Step", min: 0.01, max: 2 },
  channelLimit: { label: "Channel limit", min: 0.1, max: 10 },
} as const satisfies Record<string, Bound>;

export const MEX_BOUNDS = {
  currentMa: { label: "Channel current", min: 0.1, max: 10 },
} as const satisfies Record<string, Bound>;

/** True when *value* is set and outside *bound* (a cleared optional field is in bounds). */
export function outOfBounds(value: number | null | undefined, bound: Bound): boolean {
  return value !== null && value !== undefined && !(value >= bound.min && value <= bound.max);
}

function boundsReason(fields: Record<string, number | null | undefined>, bounds: Record<string, Bound>): string | null {
  for (const [key, bound] of Object.entries(bounds)) {
    if (outOfBounds(fields[key], bound)) return `${bound.label} must be between ${bound.min} and ${bound.max} mA.`;
  }
  return null;
}

/**
 * Why a filled-in Ex form still has nothing to run, or null. Called after the empty-bucket check,
 * so a zero here means every combination was filtered out — exactly when the runner would refuse.
 */
export function exFormReason(form: ExFormState): string | null {
  const bounds = boundsReason(
    { totalCurrent: form.totalCurrent, currentStep: form.currentStep, channelLimit: form.channelLimit },
    EX_BOUNDS,
  );
  if (bounds) return bounds;
  const cost = exCost(form);
  if (cost.splits === 0) {
    return "No current split fits: each channel needs at least one step and at most the channel limit, and the two channels must add up to the total.";
  }
  if (cost.montages === 0) {
    return form.electrodeMode === "bucketed"
      ? "No montage has four different electrodes: a channel cannot start and end on one electrode, and the two channels cannot share one."
      : "Add at least four different electrodes to the pool.";
  }
  return null;
}

/** The mEx counterpart of `exFormReason`: the pair current, then eight different electrodes. */
export function mexFormReason(form: MExFormState): string | null {
  const bounds = boundsReason({ currentMa: form.currentMa }, MEX_BOUNDS);
  if (bounds) return bounds;
  if (mexCost(form).montages === 0) {
    return "No montage has eight different electrodes: each of the four channels needs its own two electrodes (Ek+ and Ek-).";
  }
  return null;
}

export interface FlexCost {
  solves: number;
  line: string;
}

/**
 * Differential evolution costs one FEM solve per candidate: `population × iterations`, once per
 * multistart run, and once per Pareto threshold pair when the sweep is on.
 */
export function flexCost(form: FlexFormState): FlexCost {
  const runs = Math.max(1, form.nMultistart);
  const sweeps = jobKindFor(form) === "flex_pareto" ? Math.max(1, sweepCombinationCount(form)) : 1;
  const solves = form.populationSize * form.maxIterations * runs * sweeps;
  const runsPart = runs > 1 ? ` × ${n(runs)} runs` : "";
  const sweepPart = sweeps > 1 ? ` × ${n(sweeps)} sweeps` : "";
  return {
    solves,
    line: `population ${n(form.populationSize)} × ${n(form.maxIterations)} generations${runsPart}${sweepPart} ≈ ${n(solves)} solves`,
  };
}
