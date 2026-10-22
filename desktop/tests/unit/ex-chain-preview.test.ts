/**
 * The Results pane's summary of an Ex and an mEx run agrees with the config the Optimizer page
 * built and with the files the runner wrote from it (2026-10-22).
 *
 * `tests/fixtures/ex_chain/{ex,mex}/` holds the `run_config.json` and `final_output.csv` that
 * `tests/test_ex_desktop_runner_chain.py` gets by running the desktop-config corpus cases
 * `optimizer-ex/bucketed-saved` and `optimizer-ex/mex-saved` (written by the real
 * `buildExConfig`/`buildMExConfig`) through `/api/validate`, `/api/plan` and `python -m tit.opt.ex`
 * / `tit.opt.mex` on a synthetic leadfield; that test fails when these copies drift from what the
 * chain writes. Expected values here come from the corpus config itself (buckets, currents, ROI)
 * and from counting: the montage count is the product of the bucket sizes (the buckets are
 * disjoint) times the current splits of the sweep, and it is the number of rows in the CSV.
 *
 * Reproduce: `cd desktop && npx vitest run tests/unit/ex-chain-preview.test.ts`.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseExRunConfig } from "../../src/renderer/pages/results/preview/ex";

const read = (...parts: string[]): string => readFileSync(resolve(__dirname, ...parts), "utf8");
const chain = (kind: string, name: string): string => read("../fixtures/ex_chain", kind, name);
const corpus = (name: string): Record<string, unknown> =>
  (JSON.parse(read("../../../tests/fixtures/desktop_configs/optimizer-ex", `${name}.json`)) as { jobs: { config: Record<string, unknown> }[] }).jobs[0]!.config;

/** Data rows of a CSV file (header excluded). */
const csvRows = (text: string): number => text.split("\n").filter((line) => line.trim() !== "").length - 1;

/** Splits of `total` on the `step` grid with both channels in [step, limit]. */
function splitCount(total: number, step: number, limit: number): number {
  const n = Math.round(total / step);
  let count = 0;
  for (let k = 1; k < n; k++) {
    if (k * step <= limit + 1e-9 && (n - k) * step <= limit + 1e-9) count++;
  }
  return count;
}

function rowMap(text: string): { rows: Record<string, string>; buckets: { label: string; electrodes: string[] }[] } {
  const summary = parseExRunConfig(text);
  expect(summary).toBeDefined();
  return { rows: Object.fromEntries(summary!.rows.map((r) => [r.label, r.value])), buckets: summary!.buckets };
}

const CHANNEL_POLES: [string, string][] = [
  ["Channel 1 +", "e1_plus"],
  ["Channel 1 −", "e1_minus"],
  ["Channel 2 +", "e2_plus"],
  ["Channel 2 −", "e2_minus"],
];

describe("Ex run of the corpus case optimizer-ex/bucketed-saved", () => {
  const config = corpus("bucketed-saved");
  const buckets = config.electrodes as Record<string, string[]>;
  const { rows, buckets: shown } = rowMap(chain("ex", "run_config.json"));

  it("has as many montages as the buckets and the current sweep make, and as the CSV has rows", () => {
    const montages =
      ["e1_plus", "e1_minus", "e2_plus", "e2_minus"].reduce((n, key) => n * buckets[key]!.length, 1) *
      splitCount(config.total_current as number, config.current_step as number, config.channel_limit as number);
    expect(montages).toBe(2 ** 4 * 7);
    expect(rows.Montages).toBe(String(montages));
    expect(csvRows(chain("ex", "final_output.csv"))).toBe(montages);
  });

  it("states the target, the cap, the sweep and the limit the page asked for", () => {
    // ExConfig appends ".csv" to a saved ROI's name.
    expect(rows.ROI).toBe(`${config.roi_name as string}.csv · r ${config.roi_radius as number} mm`);
    expect(rows["EEG net"]).toBe("GSN-HydroCel-185"); // the corpus leadfield GSN-HydroCel-185_leadfield.hdf5
    expect(rows.Electrodes).toBe("bucket");
    expect(rows.Current).toBe(`${config.total_current as number} mA · step ${config.current_step as number} mA`);
    expect(rows["Channel limit"]).toBe(`${config.channel_limit as number} mA`);
  });

  it("lists each channel pole's bucket as the page built it", () => {
    expect(shown.map((b) => b.label)).toEqual(CHANNEL_POLES.map(([label]) => label));
    for (const [label, key] of CHANNEL_POLES) {
      expect(shown.find((b) => b.label === label)!.electrodes).toEqual(buckets[key]);
    }
  });
});

describe("mEx run of the corpus case optimizer-ex/mex-saved", () => {
  const config = corpus("mex-saved");
  const buckets = config.electrodes as Record<string, string[]>;
  const { rows, buckets: shown } = rowMap(chain("mex", "run_config.json"));

  it("has as many montages as the eight buckets make, and as the CSV has rows", () => {
    const keys = [1, 2, 3, 4].flatMap((k) => [`e${k}_plus`, `e${k}_minus`]);
    const montages = keys.reduce((n, key) => n * buckets[key]!.length, 1);
    expect(montages).toBe(16);
    expect(rows.Montages).toBe(String(montages));
    expect(csvRows(chain("mex", "final_output.csv"))).toBe(montages);
  });

  it("states the target and the cap", () => {
    expect(rows.ROI).toBe(`${config.roi_name as string}.csv · r ${config.roi_radius as number} mm`);
    expect(rows["EEG net"]).toBe("GSN-HydroCel-185");
    expect(rows.Electrodes).toBe("bucket");
  });

  it("shows the first two channels' buckets as the page built them", () => {
    for (const [label, key] of CHANNEL_POLES) {
      expect(shown.find((b) => b.label === label)!.electrodes).toEqual(buckets[key]);
    }
  });
});
