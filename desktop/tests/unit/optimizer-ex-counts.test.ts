/**
 * The Optimizer's Ex/mEx cost line is the number of rows the runner writes, and a row the runner
 * would refuse cannot be run (package p05, 2026-10-22).
 *
 * The counts come from `tests/fixtures/ex_search_counts.json`, written by `dev/gen_ex_counts.py`: a
 * brute force over `itertools.product` that imports nothing from `tit` (Ex cases reduced to
 * physical stimulations — TI ignores channel polarity and order). `tests/test_ex_search_counts.py`
 * holds the runner's `count_combinations` and `POST /api/plan/{ex,mex}` to the same table, so the
 * three layers agree through it.
 *
 * The bounds are the inputs' own min/max (`ExSections.tsx`), > 0 by physics and `ExConfig`.
 * Reproduce: `python3 dev/gen_ex_counts.py && npx vitest run tests/unit/optimizer-ex-counts.test.ts`.
 */
import { describe, expect, it } from "vitest";
import table from "../../../tests/fixtures/ex_search_counts.json";
import { EX_BOUNDS, MEX_BOUNDS, exCost, mexCost } from "../../src/renderer/pages/optimizer/cost";
import { defaultExFormState, defaultMExFormState, type ExFormState, type MExFormState } from "../../src/renderer/pages/optimizer/exConfig";
import { rowFormReason } from "../../src/renderer/pages/optimizer/plan";
import { emptyOptimizerRow, type OptimizerRow } from "../../src/renderer/pages/optimizer/rows";

interface Case {
  id: string;
  kind: "ex" | "mex";
  mode?: "bucketed" | "all";
  buckets?: Record<string, string[]>;
  pool?: string[];
  total_current?: number;
  current_step?: number;
  channel_limit?: number | null;
  splits?: number[][];
  current_mA?: number;
  expected_montages: number;
  expected_combinations: number;
}

const cases = (table as { cases: Case[] }).cases;
const exCases = cases.filter((c) => c.kind === "ex");
const mexCases = cases.filter((c) => c.kind === "mex");

function exForm(c: Case): ExFormState {
  return {
    ...defaultExFormState(),
    electrodeMode: c.mode!,
    buckets: c.mode === "bucketed" ? c.buckets! : { e1_plus: [], e1_minus: [], e2_plus: [], e2_minus: [] },
    pool: c.mode === "all" ? c.pool! : [],
    totalCurrent: c.total_current!,
    currentStep: c.current_step!,
    channelLimit: c.channel_limit ?? null,
  };
}

function mexForm(c: Case): MExFormState {
  return { ...defaultMExFormState(), buckets: c.buckets!, currentMa: c.current_mA! };
}

describe("the shared count table", () => {
  it("has bucket, pool and mEx cases, including ones with nothing to run", () => {
    expect(exCases.some((c) => c.mode === "all")).toBe(true);
    expect(exCases.some((c) => c.mode === "bucketed")).toBe(true);
    expect(mexCases.length).toBeGreaterThanOrEqual(3);
    expect(cases.filter((c) => c.expected_combinations === 0).length).toBeGreaterThanOrEqual(3);
  });
});

describe("exCost equals the runner's row count", () => {
  it.each(exCases.map((c) => [c.id, c] as const))("%s", (_id, c) => {
    const cost = exCost(exForm(c));
    expect(cost.splits).toBe(c.splits!.length);
    expect(cost.montages).toBe(c.expected_montages);
    expect(cost.combinations).toBe(c.expected_combinations);
  });
});

describe("mexCost equals the runner's row count", () => {
  it.each(mexCases.map((c) => [c.id, c] as const))("%s", (_id, c) => {
    const cost = mexCost(mexForm(c));
    expect(cost.montages).toBe(c.expected_montages);
    expect(cost.combinations).toBe(c.expected_combinations);
  });

  it("states 8! for eight buckets of the same eight electrodes, not 8^8", () => {
    const same = mexCases.find((c) => c.id === "mex_same_eight")!;
    // 8 * 7 * ... * 1, by hand.
    expect(mexCost(mexForm(same)).line).toContain("40,320 combinations");
  });
});

function exRow(form: Partial<ExFormState>): OptimizerRow {
  const row = emptyOptimizerRow({ subjectId: "ernie", method: "ex", exPairs: 2 });
  return { ...row, ex: { ...row.ex, ...form } };
}

function mexRow(form: Partial<MExFormState>): OptimizerRow {
  const row = emptyOptimizerRow({ subjectId: "ernie", method: "ex", exPairs: 4 });
  return { ...row, mex: { ...row.mex, ...form } };
}

const FOUR = { e1_plus: ["F3"], e1_minus: ["P3"], e2_plus: ["F4"], e2_minus: ["P4"] };
const EIGHT = Object.fromEntries(
  ["e1_plus", "e1_minus", "e2_plus", "e2_minus", "e3_plus", "e3_minus", "e4_plus", "e4_minus"].map((k, i) => [k, [`E${i}`]]),
);

describe("rowFormReason refuses what the runner would refuse", () => {
  it("blocks every fixture case with no candidate and passes every other one", () => {
    for (const c of exCases) {
      const reason = rowFormReason(exRow(exForm(c)));
      if (c.expected_combinations === 0) expect(reason, c.id).not.toBeNull();
      else expect(reason, c.id).toBeNull();
    }
    for (const c of mexCases) {
      const reason = rowFormReason(mexRow(mexForm(c)));
      if (c.expected_combinations === 0) expect(reason, c.id).not.toBeNull();
      else expect(reason, c.id).toBeNull();
    }
  });

  it("names a channel that starts and ends on one electrode", () => {
    const reason = rowFormReason(exRow({ buckets: { e1_plus: ["A"], e1_minus: ["A"], e2_plus: ["B"], e2_minus: ["C"] } }));
    expect(reason).toContain("four different electrodes");
  });

  it("names a pool that repeats a label to reach four", () => {
    expect(rowFormReason(exRow({ electrodeMode: "all", pool: ["A", "B", "A", "C"] }))).toContain("four different electrodes");
  });

  it("names a sweep with no split", () => {
    expect(rowFormReason(exRow({ buckets: FOUR, totalCurrent: 2, currentStep: 0.2, channelLimit: 0.8 }))).toContain("No current split fits");
  });

  it("names eight buckets that cannot make eight different electrodes", () => {
    const same = Object.fromEntries(Object.keys(EIGHT).map((k) => [k, ["A", "B", "C", "D"]]));
    expect(rowFormReason(mexRow({ buckets: same }))).toContain("eight different electrodes");
  });
});

describe("Ex current bounds are row rules, not input hints", () => {
  // value → accepted (null) or the field's label in the reason; the other two fields are chosen
  // so the sweep has a split, which isolates the bound being tested.
  const cases: [string, Partial<ExFormState>, string | null][] = [
    ["total current at its minimum", { totalCurrent: 0.1, currentStep: 0.05, channelLimit: null }, null],
    ["total current at its maximum", { totalCurrent: 10, currentStep: 2, channelLimit: null }, null],
    ["total current 0", { totalCurrent: 0, currentStep: 0.05, channelLimit: null }, EX_BOUNDS.totalCurrent.label],
    ["negative total current", { totalCurrent: -2, currentStep: 0.05, channelLimit: null }, EX_BOUNDS.totalCurrent.label],
    ["total current 11 mA", { totalCurrent: 11, currentStep: 2, channelLimit: null }, EX_BOUNDS.totalCurrent.label],
    ["step at its minimum", { totalCurrent: 2, currentStep: 0.01, channelLimit: null }, null],
    ["step 0", { totalCurrent: 2, currentStep: 0, channelLimit: null }, EX_BOUNDS.currentStep.label],
    ["step below 0.01", { totalCurrent: 2, currentStep: 0.005, channelLimit: null }, EX_BOUNDS.currentStep.label],
    ["step above 2", { totalCurrent: 10, currentStep: 2.5, channelLimit: null }, EX_BOUNDS.currentStep.label],
    ["channel limit cleared", { totalCurrent: 2, currentStep: 0.5, channelLimit: null }, null],
    ["channel limit at its minimum", { totalCurrent: 0.2, currentStep: 0.1, channelLimit: 0.1 }, null],
    ["channel limit 0", { totalCurrent: 2, currentStep: 0.5, channelLimit: 0 }, EX_BOUNDS.channelLimit.label],
    ["negative channel limit", { totalCurrent: 2, currentStep: 0.5, channelLimit: -1 }, EX_BOUNDS.channelLimit.label],
    ["channel limit above 10", { totalCurrent: 10, currentStep: 2, channelLimit: 10.5 }, EX_BOUNDS.channelLimit.label],
  ];

  it.each(cases)("%s", (_name, form, label) => {
    const reason = rowFormReason(exRow({ buckets: FOUR, ...form }));
    if (label === null) expect(reason).toBeNull();
    else expect(reason).toContain(label);
  });

  it.each([
    [0.1, null],
    [10, null],
    [0, MEX_BOUNDS.currentMa.label],
    [-1, MEX_BOUNDS.currentMa.label],
    [10.5, MEX_BOUNDS.currentMa.label],
  ] as const)("mEx pair current %s", (currentMa, label) => {
    const reason = rowFormReason(mexRow({ buckets: EIGHT, currentMa }));
    if (label === null) expect(reason).toBeNull();
    else expect(reason).toContain(label);
  });
});
