/**
 * The Results parsers on every real Dataset 000 output give logical, complete rows (2026-10-22, p12).
 *
 * Gated: `export TIT_DATASET_000=/Users/idohaber/datasets/000` (read-only; nothing is written: a
 * listing of every file's mtime under derivatives/SimNIBS is taken before the suite and compared
 * after it). Skips with the reason when unset. Bounds come from definitions, never from current
 * output:
 * - simulation `documentation/config.json`: one intensity per electrode pair; TI for 2 pairs, mTI
 *   for 3 or more (`tit/sim/config.py`); the "Mapped to" row (the file's
 *   `mapping_options.map_to_mni`) names MNI iff the run has `*_MNI_*` volumes under
 *   TI|mTI|high_Frequency/niftis (`tit/sim/utils.py` writes them only when map_to_mni is set);
 * - flex `flex_meta.json` + `electrode_positions.json`: the ROI row names every atlas file and every
 *   label the manifest lists; 2 electrodes per pair, finite, |xyz| < 200 mm, no two closer than
 *   `min_electrode_distance`;
 * - ex `run_config.json` + `final_output.csv`: Montages == CSV data rows; Ch1 + Ch2 == the total;
 *   no channel above its limit; TImean_ROI <= TImax_ROI; a pool run lists its pool; the ranked
 *   table starts with the maximum Composite_Index;
 * - analysis `results.csv`: roi_min <= roi_mean <= roi_max; p95 <= p99 <= p99.9 <= gm_max;
 *   gm_mean <= gm_max; focality_95 <= 90 <= 75 <= 50; `space` is the parent folder (Mesh/Voxel)
 *   and decides the unit (cm² / cm³); whole-GM metrics depend only on (simulation, field, space).
 *
 * Known failure (p15): sub-101/L_Insula, sub-101/Thalamus_example and sub-LA/L_Insula hold
 * `*_MNI_MNI_*` volumes from an earlier run while their config.json says map_to_mni false; a re-run
 * did not clear the old outputs. They are listed in STALE_MNI and asserted to still mismatch, so a
 * dataset re-run that clears them fails here until the entry is removed.
 *
 * Deliberately not here: the analysis figures-vs-catalog check, which needs the Python catalog
 * (tests/test_catalog_analysis_figures.py).
 *
 * `rankExRows` and `shortMontage` are read here (the ranked-table check); no page calls them, so
 * the package that deletes them must drop that check with them.
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { analysisView, focalityUnit, metricMap, type TableLike } from "../../src/renderer/pages/results/preview/analysis";
import { parseExRunConfig, rankExRows, shortMontage, type ExTable } from "../../src/renderer/pages/results/preview/ex";
import { flexManifestSummary, parseFlexPositions } from "../../src/renderer/pages/results/preview/flex";
import { parseSimulationConfig } from "../../src/renderer/pages/results/preview/simulation";

const ROOT = process.env.TIT_DATASET_000 ?? "";
const SIMNIBS = join(ROOT, "derivatives", "SimNIBS");
const HAVE = ROOT !== "" && existsSync(SIMNIBS);
if (!HAVE) console.info("skipping realdata-results-parsers: TIT_DATASET_000 is unset or has no derivatives/SimNIBS");

const dirs = (p: string): string[] =>
  existsSync(p) ? readdirSync(p).filter((n) => !n.startsWith(".") && statSync(join(p, n)).isDirectory()) : [];

/** `<sub>/<kind>/<run>` folders holding `file`. */
function runs(kind: string, file: string): string[] {
  return dirs(SIMNIBS).flatMap((sub) =>
    dirs(join(SIMNIBS, sub, kind))
      .map((run) => join(SIMNIBS, sub, kind, run))
      .filter((run) => existsSync(join(run, file))),
  );
}

function csvTable(path: string): ExTable {
  const [head, ...body] = readFileSync(path, "utf8").replace(/\r\n/g, "\n").trim().split("\n");
  const cell = (s: string): string | number => (s !== "" && !Number.isNaN(Number(s)) ? Number(s) : s);
  return { columns: head!.split(","), rows: body.map((line) => line.split(",").map(cell)) };
}

const rowsOf = (summary: { rows: { label: string; value: string }[] }): Record<string, string> =>
  Object.fromEntries(summary.rows.map((r) => [r.label, r.value]));

/** Every file under `root` with its mtime: the suite must leave this listing unchanged. */
function mtimes(root: string): Map<string, number> {
  const out = new Map<string, number>();
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const path = join(root, entry.name);
    if (entry.isDirectory()) for (const [p, t] of mtimes(path)) out.set(p, t);
    else out.set(path, statSync(path).mtimeMs);
  }
  return out;
}

/**
 * Simulations whose `*_MNI_*` volumes are left over from an earlier run of the same name: their
 * config.json says map_to_mni false. Known failure owned by p15: stale MNI files, rerun clears them.
 */
const STALE_MNI = new Set(["sub-101/L_Insula", "sub-101/Thalamus_example", "sub-LA/L_Insula"]);
const MNI_VOLUME = /_MNI_.*\.nii(\.gz)?$/;

describe.skipIf(!HAVE)("Dataset 000 through the Results parsers", () => {
  let before = new Map<string, number>();
  beforeAll(() => {
    before = mtimes(SIMNIBS);
  });
  afterAll(() => {
    expect(mtimes(SIMNIBS), "the suite changed no file under derivatives/SimNIBS").toEqual(before);
  });

  it("simulations: one intensity per pair, TI for two pairs and mTI for more", () => {
    const sims = dirs(SIMNIBS).flatMap((sub) =>
      dirs(join(SIMNIBS, sub, "Simulations"))
        .map((s) => join(SIMNIBS, sub, "Simulations", s, "documentation", "config.json"))
        .filter(existsSync),
    );
    expect(sims.length, "has simulations to check").toBeGreaterThan(0);
    for (const path of sims) {
      const raw = JSON.parse(readFileSync(path, "utf8")) as { electrode_pairs: unknown[]; intensities: number[] };
      const summary = parseSimulationConfig(readFileSync(path, "utf8"))!;
      const pairs = raw.electrode_pairs.length;
      expect(raw.intensities.length, path).toBe(pairs);
      expect(rowsOf(summary).Mode, path).toBe(pairs === 2 ? "TI" : "MTI");
      expect(rowsOf(summary).Intensity, path).toBe(`${raw.intensities.map((v) => Number(v.toFixed(4))).join(" / ")} mA`);
    }
  });

  it("simulations: the Mapped to row names MNI iff the run has MNI volumes (stale ones listed, p15)", () => {
    const sims = dirs(SIMNIBS).flatMap((sub) =>
      dirs(join(SIMNIBS, sub, "Simulations"))
        .map((name) => ({ key: `${sub}/${name}`, dir: join(SIMNIBS, sub, "Simulations", name) }))
        .filter(({ dir }) => existsSync(join(dir, "documentation", "config.json"))),
    );
    expect(sims.length, "has simulations to check").toBeGreaterThan(0);
    for (const { key, dir } of sims) {
      const summary = parseSimulationConfig(readFileSync(join(dir, "documentation", "config.json"), "utf8"))!;
      const mappedTo = rowsOf(summary)["Mapped to"];
      expect(mappedTo, `${key}: config.json has mapping_options`).toBeDefined();
      const mapsMni = mappedTo!.split(", ").includes("MNI");
      const volumes = ["TI", "mTI", "high_Frequency"].flatMap((kind) => {
        const niftis = join(dir, kind, "niftis");
        return existsSync(niftis) ? readdirSync(niftis).filter((n) => MNI_VOLUME.test(n)) : [];
      });
      if (STALE_MNI.has(key)) {
        // Known failure (p15): stale MNI files, rerun clears them. Still a mismatch today; when a
        // re-run clears them this fails, and the entry comes out of STALE_MNI.
        expect({ key, mapsMni, hasVolumes: volumes.length > 0 }).toEqual({ key, mapsMni: false, hasVolumes: true });
      } else {
        expect(volumes.length > 0, `${key}: MNI volumes ${volumes.join(", ") || "none"}, Mapped to ${mappedTo}`).toBe(mapsMni);
      }
    }
  });

  it("flex runs: the ROI row names every atlas file and label; electrodes are 4, finite and apart", () => {
    const found = runs("flex-search", "flex_meta.json");
    expect(found.length, "has flex runs to check").toBeGreaterThan(0);
    for (const run of found) {
      const meta = JSON.parse(readFileSync(join(run, "flex_meta.json"), "utf8")) as {
        roi: { atlas_path?: string | string[]; label?: number | number[] };
        n_pairs?: number;
        min_electrode_distance: number;
      };
      const roiRow = rowsOf(flexManifestSummary(meta)).ROI ?? "";
      for (const path of ([] as string[]).concat(meta.roi.atlas_path ?? [])) expect(roiRow, run).toContain(basename(path));
      for (const label of ([] as number[]).concat(meta.roi.label ?? [])) expect(roiRow, run).toMatch(new RegExp(`\\b${label}\\b`));

      const electrodes = parseFlexPositions(readFileSync(join(run, "electrode_positions.json"), "utf8"));
      expect(electrodes, run).toHaveLength(2 * (meta.n_pairs ?? 2));
      for (const e of electrodes) for (const v of [e.x, e.y, e.z]) expect(Math.abs(v), run).toBeLessThan(200);
      const gaps = electrodes.flatMap((a, i) => electrodes.slice(i + 1).map((b) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z)));
      expect(Math.min(...gaps), run).toBeGreaterThanOrEqual(meta.min_electrode_distance);
      expect(electrodes.map((e) => [e.channel, e.array])).toEqual([
        [0, 0],
        [0, 1],
        [1, 0],
        [1, 1],
      ]);
    }
  });

  it("ex runs: Montages is the CSV's row count, currents add up within limits, a pool is listed", () => {
    const found = runs("ex-search", "run_config.json").filter((run) => existsSync(join(run, "final_output.csv")));
    expect(found.length, "has ex runs to check").toBeGreaterThan(0);
    for (const run of found) {
      const text = readFileSync(join(run, "run_config.json"), "utf8");
      const config = JSON.parse(text) as {
        electrode_mode: string;
        electrodes: Record<string, string[]>;
        total_current_mA?: number;
        current_mA?: number;
        channel_limit_mA?: number | null;
      };
      const summary = parseExRunConfig(text)!;
      const table = csvTable(join(run, "final_output.csv"));
      expect(rowsOf(summary).Montages, run).toBe(table.rows.length.toLocaleString());
      if (config.electrode_mode === "pool") {
        expect(summary.buckets, run).toEqual([{ label: "Pool", electrodes: config.electrodes.electrodes }]);
      }
      const col = (name: string) => table.columns.indexOf(name);
      const total = config.total_current_mA ?? config.current_mA!;
      for (const row of table.rows) {
        const [c1, c2] = [row[col("Current_Ch1_mA")] as number, row[col("Current_Ch2_mA")] as number];
        expect(c1 + c2, run).toBeCloseTo(total, 6);
        if (config.channel_limit_mA) expect(Math.max(c1, c2), run).toBeLessThanOrEqual(config.channel_limit_mA + 1e-9);
        expect(row[col("TImean_ROI")] as number, run).toBeLessThanOrEqual(row[col("TImax_ROI")] as number);
      }
      const rank = col("Composite_Index");
      const best = table.rows.reduce((a, b) => ((b[rank] as number) > (a[rank] as number) ? b : a));
      expect(rankExRows(table).rows[0]![0], run).toBe(shortMontage(String(best[0])));
    }
  });

  it("analyses: ordered metrics, the space of their folder, and one whole-GM value per simulation", () => {
    const analyses = dirs(SIMNIBS).flatMap((sub) =>
      dirs(join(SIMNIBS, sub, "Simulations")).flatMap((sim) =>
        ["Mesh", "Voxel"].flatMap((space) =>
          dirs(join(SIMNIBS, sub, "Simulations", sim, "Analyses", space))
            .map((a) => join(SIMNIBS, sub, "Simulations", sim, "Analyses", space, a, "results.csv"))
            .filter(existsSync),
        ),
      ),
    );
    expect(analyses.length, "has analyses to check").toBeGreaterThan(0);
    const wholeGm = new Map<string, number[]>();
    for (const path of analyses) {
      const table: TableLike = csvTable(path);
      const m = metricMap(table);
      const n = (k: string): number => Number(m.get(k));
      const space = m.get("space")!;
      expect(space, path).toBe(basename(dirname(dirname(path))).toLowerCase());
      expect(n("roi_min"), path).toBeLessThanOrEqual(n("roi_mean"));
      expect(n("roi_mean"), path).toBeLessThanOrEqual(n("roi_max"));
      expect(n("percentile_95"), path).toBeLessThanOrEqual(n("percentile_99"));
      expect(n("percentile_99"), path).toBeLessThanOrEqual(n("percentile_99_9"));
      expect(n("percentile_99_9"), path).toBeLessThanOrEqual(n("gm_max"));
      expect(n("gm_mean"), path).toBeLessThanOrEqual(n("gm_max"));
      expect(n("focality_95_area"), path).toBeLessThanOrEqual(n("focality_90_area"));
      expect(n("focality_90_area"), path).toBeLessThanOrEqual(n("focality_75_area"));
      expect(n("focality_75_area"), path).toBeLessThanOrEqual(n("focality_50_area"));
      const view = analysisView(table);
      const unit = space === "voxel" ? "cm³" : "cm²";
      expect(focalityUnit(view.space), path).toBe(unit);
      expect(view.groups.some((g) => g.title === `Focality extent · ${unit}`), path).toBe(true);
      // Whole-GM numbers do not depend on the ROI: one value per (simulation, field, space). The
      // 1e-9 relative tolerance absorbs summation order only (measured: 1e-13 between runs).
      const sim = dirname(dirname(dirname(dirname(path))));
      const key = `${sim}|${m.get("field_name")}|${space}`;
      const gm = ["gm_mean", "gm_max", "percentile_95", "percentile_99", "percentile_99_9"].map(n);
      const first = wholeGm.get(key);
      if (!first) wholeGm.set(key, gm);
      else gm.forEach((v, i) => expect(Math.abs(v - first[i]!), path).toBeLessThanOrEqual(1e-9 * Math.abs(first[i]!)));
    }
  });
});
