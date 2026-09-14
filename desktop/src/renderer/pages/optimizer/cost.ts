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

/** Counts the descending sweep used by tit.opt.ex.logic.generate_current_ratios. */
export function currentSplits(totalCurrent: number, currentStep: number, channelLimit: number | null): number {
  if (!Number.isFinite(totalCurrent) || !Number.isFinite(currentStep) || !(currentStep > 0) || !(totalCurrent > 0)) return 0;
  const limit = channelLimit ?? totalCurrent - currentStep;
  if (!Number.isFinite(limit) || limit <= 0) return 0;
  const epsilon = currentStep * 0.01;
  const maximum = Math.min(limit, totalCurrent - currentStep);
  const minimum = Math.max(totalCurrent - limit, currentStep);
  // The first split starts at the channel limit, not necessarily a multiple of the step.
  return Math.max(0, Math.floor((maximum - minimum + epsilon) / currentStep) + 1);
}

/** Ordered, distinct-electrode tuples, including multiplicities in an imported pool. */
function poolMontages(pool: string[]): number {
  const occurrences = new Map<string, number>();
  for (const electrode of pool) occurrences.set(electrode, (occurrences.get(electrode) ?? 0) + 1);
  const selections = [1, 0, 0, 0, 0];
  for (const multiplicity of occurrences.values()) {
    for (let size = 4; size > 0; size--) selections[size] = selections[size]! + selections[size - 1]! * multiplicity;
  }
  return selections[4]! * 24; // All four pole assignments are evaluated by the engine.
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
    electrodes = new Set(form.pool).size;
    montages = poolMontages(form.pool);
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
