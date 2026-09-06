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
  /** "185 electrodes · 7 splits · 119 140 combinations", ready for a tile and for the digest. */
  line: string;
}

function n(value: number): string {
  return value.toLocaleString("en-US");
}

/**
 * How many two-channel current splits the sweep visits: `c1 = k·step` for `k = 1 …`, with both
 * `c1` and `total − c1` at or under the per-channel limit. Mirrors `tit.opt.ex`'s amplitude sweep,
 * which never assigns zero to a channel.
 */
export function currentSplits(totalCurrent: number, currentStep: number, channelLimit: number | null): number {
  if (!(currentStep > 0) || !(totalCurrent > 0)) return 0;
  const steps = Math.round(totalCurrent / currentStep);
  const limit = channelLimit ?? totalCurrent;
  let count = 0;
  for (let k = 1; k < steps; k++) {
    const c1 = k * currentStep;
    // Floating-point steps (0.2 mA) do not land exactly on the limit; a 1e-9 slack keeps a
    // deliberate "limit == total/2" from silently dropping the balanced split.
    if (c1 <= limit + 1e-9 && totalCurrent - c1 <= limit + 1e-9) count++;
  }
  return count;
}

/** Distinct electrodes across the bucket set (an electrode used in two buckets is still one). */
function distinct(buckets: Record<string, string[]>, keys: readonly string[]): number {
  const seen = new Set<string>();
  for (const k of keys) for (const e of buckets[k] ?? []) seen.add(e);
  return seen.size;
}

function product(buckets: Record<string, string[]>, keys: readonly string[]): number {
  return keys.reduce((acc, k) => acc * (buckets[k] ?? []).length, 1);
}

export function exCost(form: ExFormState): SearchCost {
  const splits = currentSplits(form.totalCurrent, form.currentStep, form.channelLimit);
  let electrodes: number;
  let montages: number;
  if (form.electrodeMode === "bucketed") {
    electrodes = distinct(form.buckets, EX_BUCKET_KEYS);
    montages = product(form.buckets, EX_BUCKET_KEYS);
  } else {
    // Four distinct electrodes from the pool, unordered within each pair and between the two
    // pairs: n(n−1)(n−2)(n−3) orderings / (2 · 2 · 2).
    const p = form.pool.length;
    electrodes = p;
    montages = p < 4 ? 0 : (p * (p - 1) * (p - 2) * (p - 3)) / 8;
  }
  const combinations = montages * splits;
  return {
    electrodes,
    splits,
    montages,
    combinations,
    line: `${n(electrodes)} electrodes · ${n(splits)} splits · ${n(combinations)} combinations`,
  };
}

export function mexCost(form: MExFormState): SearchCost {
  const electrodes = distinct(form.buckets, MEX_BUCKET_KEYS);
  const montages = product(form.buckets, MEX_BUCKET_KEYS);
  // One fixed current per pair — mEx sweeps no amplitudes, so a "split" count would be a fiction.
  const splits = 1;
  return {
    electrodes,
    splits,
    montages,
    combinations: montages,
    // Symmetry search prunes this set by a factor the client cannot compute (it depends on the
    // net's mirror map), so the number is stated as the unpruned ceiling and said to be one.
    line: `${n(electrodes)} electrodes · 4 pairs · ${n(montages)} combinations${form.symmetricBucket ? " before symmetry" : ""}`,
  };
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
