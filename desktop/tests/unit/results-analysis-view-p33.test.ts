/**
 * The analysis pane's units and whole-tissue labels (2026-10-22).
 *
 * What this pins
 *   1. Field values carry the unit `tit.constants.FIELD_REGISTRY` gives the analysed field — read
 *      here from `tit/constants.py` itself, so the desktop's copy of the table cannot drift
 *      unnoticed: `hf_sar` is (V/m)², not V/m.
 *   2. `gm_*` and `percentile_*` are whole-tissue numbers (analyzer AnalysisResult docstring): no
 *      metric in the ROI group comes from them, and they share one group titled by the tissue
 *      (grey matter for a mesh analysis; a voxel analysis may be WM or GM+WM, which `results.csv`
 *      does not record, so it is never titled grey matter).
 *   3. The focality extent is relative to the whole-tissue 99.9th percentile, not "max".
 *
 * Where the numbers come from
 *   `tests/fixtures/preview/analysis_results_voxel_mask_both.csv` is a verbatim copy of Dataset 000's
 *   `sub-ernie/Simulations/AF3_PO10_and_AF4_Oz/Analyses/Voxel/cortical_mask_roi_mask_subject_
 *   a41fbce2d5_unknown_atlas/results.csv` (its analysis.json says tissue_types GM+WM): the case
 *   where the old pane showed "Percentiles 99.9th 0.5169 V/m" beside "ROI Max 0.4131 V/m".
 *   Every rendered value is mapped back to the CSV key that produced it by formatting each key's
 *   own value, so nothing below is retyped from the code under test.
 *
 * Run: cd desktop && npx vitest run tests/unit/results-analysis-view-p33.test.ts
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { analysisView, metricMap, type TableLike } from "../../src/renderer/pages/results/preview/analysis";
import { formatCount, formatMetric } from "../../src/renderer/pages/results/preview/metrics";

function fixture(name: string): TableLike {
  const text = readFileSync(resolve(__dirname, "../fixtures/preview", name), "utf8");
  const [header, ...rows] = text.trim().split(/\r?\n/);
  return {
    columns: (header ?? "").split(","),
    rows: rows.map((line) => {
      const cut = line.indexOf(",");
      return [line.slice(0, cut), line.slice(cut + 1)];
    }),
  };
}

/** `FIELD_REGISTRY` read from the Python source: field name -> units, as the toolbox defines them. */
function registryUnits(): Map<string, string> {
  const source = readFileSync(resolve(__dirname, "../../../tit/constants.py"), "utf8");
  const names = new Map<string, string>();
  for (const m of source.matchAll(/^(FIELD_[A-Z_]+) = "([^"]+)"/gm)) names.set(m[1]!, m[2]!);
  const out = new Map<string, string>();
  for (const m of source.matchAll(/FieldSpec\(\s*name=(FIELD_[A-Z_]+),[\s\S]*?units="([^"]+)"/g)) {
    out.set(names.get(m[1]!)!, m[2]!.replace("^2", "²"));
  }
  return out;
}

function table(rows: [string, string][]): TableLike {
  return { columns: ["Metric", "Value"], rows };
}

/** The CSV keys whose own value renders as `rendered` (with `unit`), for every numeric key. */
function keysRendering(csv: TableLike, rendered: string, units: string[]): string[] {
  const hits: string[] = [];
  for (const [key, raw] of csv.rows as [string, string][]) {
    const value = Number(raw);
    if (raw === "" || !Number.isFinite(value)) continue;
    const candidates = [formatMetric(value), formatCount(value), ...units.map((u) => formatMetric(value, u))];
    if (candidates.includes(rendered)) hits.push(key);
  }
  return hits;
}

const MESH = fixture("analysis_results_mesh.csv");
const VOXEL = fixture("analysis_results_voxel.csv");
const ERNIE_BOTH = fixture("analysis_results_voxel_mask_both.csv");

describe("field units come from FIELD_REGISTRY", () => {
  const units = registryUnits();

  it("reads the six registry fields from tit/constants.py", () => {
    expect([...units.keys()].sort()).toEqual(["TI_avg", "TI_max", "TI_normal", "hf_peak", "hf_sar", "mTI_max"]);
  });

  it.each([...registryUnits()])("labels %s values in %s", (field, unit) => {
    const view = analysisView(table([["field_name", field], ["space", "mesh"], ["roi_mean", "0.5"], ["gm_max", "2"]]));
    const roi = view.groups.find((g) => g.title === "ROI");
    expect(roi?.metrics[0]?.value).toBe(`0.5 ${unit}`);
    expect(view.groups.flatMap((g) => g.metrics).find((m) => m.value.startsWith("2 "))?.value).toBe(`2 ${unit}`);
  });

  it("does not call carrier power V/m", () => {
    const view = analysisView(table([["field_name", "hf_sar"], ["space", "voxel"], ["roi_max", "3.25"]]));
    const values = view.groups.flatMap((g) => g.metrics.map((m) => m.value));
    expect(values).toEqual(["3.25 (V/m)²"]);
  });
});

describe("whole-tissue numbers are not ROI numbers", () => {
  for (const [name, csv] of [
    ["mesh", MESH],
    ["voxel", VOXEL],
    ["ernie voxel GM+WM", ERNIE_BOTH],
  ] as const) {
    it(`${name}: every ROI metric comes from a roi_* key, every whole-tissue one from gm_*/percentile_*`, () => {
      const view = analysisView(csv);
      const unit = ["V/m"];
      const roi = view.groups.find((g) => g.title === "ROI")!;
      const roiKeys = roi.metrics.flatMap((m) => keysRendering(csv, m.value, unit));
      expect(roiKeys.length).toBeGreaterThanOrEqual(roi.metrics.length);
      expect(roiKeys.filter((k) => !k.startsWith("roi_"))).toEqual([]);

      const whole = view.groups.find((g) => g.metrics.some((m) => keysRendering(csv, m.value, unit).includes("percentile_99_9")));
      expect(whole, "a group shows percentile_99_9").toBeDefined();
      const wholeKeys = whole!.metrics.flatMap((m) => keysRendering(csv, m.value, unit));
      expect(new Set(wholeKeys)).toEqual(
        new Set(["gm_mean", "gm_max", "percentile_95", "percentile_99", "percentile_99_9"]),
      );
    });
  }

  it("titles the whole-tissue group grey matter for a mesh analysis", () => {
    const view = analysisView(MESH);
    const whole = view.groups.find((g) => g.metrics.some((m) => m.label.includes("99.9th")));
    expect(whole?.title.toLowerCase()).toContain("grey matter");
  });

  it("never titles a voxel analysis's whole-tissue group grey matter (it may be WM or GM+WM)", () => {
    for (const csv of [VOXEL, ERNIE_BOTH]) {
      const titles = analysisView(csv).groups.map((g) => g.title.toLowerCase());
      expect(titles.filter((t) => t.includes("grey") || t.includes("gray"))).toEqual([]);
    }
  });

  it("shows ernie's tissue 99.9th percentile outside the ROI group, where it can exceed the ROI max", () => {
    const view = analysisView(ERNIE_BOTH);
    const roi = view.groups.find((g) => g.title === "ROI")!;
    const csv = metricMap(ERNIE_BOTH);
    // The case the pane must make readable: the tissue's 99.9th percentile is above the ROI max.
    expect(Number(csv.get("percentile_99_9"))).toBeGreaterThan(Number(csv.get("roi_max")));
    const p999 = formatMetric(Number(csv.get("percentile_99_9")), "V/m");
    expect(roi.metrics.map((m) => m.value)).not.toContain(p999);
    expect(view.groups.flatMap((g) => g.metrics.map((m) => m.value))).toContain(p999);
  });
});

describe("focality extent reference", () => {
  it("is the 99.9th percentile of the whole tissue, not the maximum", () => {
    for (const [csv, tissue] of [
      [MESH, "GM"],
      [ERNIE_BOTH, "tissue"],
    ] as const) {
      const focality = analysisView(csv).groups.find((g) => g.title.startsWith("Focality extent"))!;
      const labels = focality.metrics.map((m) => m.label);
      expect(labels[0]).toBe(`≥ 50 % of ${tissue} 99.9th percentile`);
      expect(labels.join(" ")).not.toMatch(/\bmax\b/i);
    }
  });
});
