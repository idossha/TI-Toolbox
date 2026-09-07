/**
 * The analyzer preview's projection and its number formatting.
 *
 * `tests/fixtures/preview/analysis_results_{mesh,voxel}.csv` are verbatim copies of two real
 * analyses of Dataset 000's `sub-ernie/Simulations/Thalamus` — a DK40 cortical analysis in mesh
 * space and an aparc+aseg thalamic one in voxel space. Every expected value below is a number that
 * exists in one of those files, which is the point: this is the pane that used to print all 22 of
 * them at full float64 width.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  analysisView,
  extentUnit,
  focalityUnit,
  metricMap,
  type TableLike,
} from "../../src/renderer/pages/results/preview/analysis";
import {
  formatCount,
  formatMetric,
  formatNumber,
} from "../../src/renderer/pages/results/preview/metrics";
import { orderSections, SECTION_ORDER } from "../../src/renderer/pages/results/preview/ResultLayout";

/** A `results.csv` fixture as the `TableData` the summary endpoint returns (values are strings). */
function fixture(name: string): TableLike {
  const text = readFileSync(resolve(__dirname, "../fixtures/preview", name), "utf8");
  // `csv.writer` writes CRLF, so the real files do too — split on both.
  const [header, ...rows] = text.trim().split(/\r?\n/);
  return {
    columns: (header ?? "").split(","),
    rows: rows.map((line) => {
      const cut = line.indexOf(",");
      return [line.slice(0, cut), line.slice(cut + 1)];
    }),
  };
}

const MESH = fixture("analysis_results_mesh.csv");
const VOXEL = fixture("analysis_results_voxel.csv");

// ─── number formatting ───────────────────────────────────────────────────────

describe("formatNumber", () => {
  it("keeps four significant digits of a field value", () => {
    // The exact string the old pane rendered was "0.07018370126141073".
    expect(formatNumber(0.07018370126141073)).toBe("0.07018");
    expect(formatNumber(0.10841794671292951)).toBe("0.1084");
    expect(formatNumber(0.5191924168021956)).toBe("0.5192");
  });

  it("trims trailing zeros, and rounds to the digit budget rather than padding", () => {
    // Four significant digits of 15225 is 15230, not 15225 — the budget is digits, not decimals.
    expect(formatNumber(15225)).toBe("15230");
    expect(formatNumber(15230)).toBe("15230");
    expect(formatNumber(2.5)).toBe("2.5");
    expect(formatNumber(0)).toBe("0");
  });

  it("goes exponential only outside the range a fixed rendering reads well in", () => {
    expect(formatNumber(2.0603e-8)).toBe("2.06e-8");
    expect(formatNumber(1383362)).toBe("1.383e6");
    // 1787.34 is inside the range and stays fixed.
    expect(formatNumber(1787.34)).toBe("1787");
    expect(formatNumber(0.00123456)).toBe("0.001235");
  });

  it("keeps the sign", () => {
    expect(formatNumber(-0.07018370126141073)).toBe("-0.07018");
    expect(formatNumber(-1383362)).toBe("-1.383e6");
  });

  it("says so when a value is not a number", () => {
    expect(formatNumber(Number.NaN)).toBe("—");
    expect(formatNumber(Number.POSITIVE_INFINITY)).toBe("—");
  });

  it("takes a wider digit budget when asked", () => {
    expect(formatNumber(0.07018370126141073, 6)).toBe("0.0701837");
  });
});

describe("formatMetric / formatCount", () => {
  it("appends the unit", () => {
    expect(formatMetric(0.07018370126141073, "V/m")).toBe("0.07018 V/m");
    expect(formatMetric(119.28014487819011, "cm²")).toBe("119.3 cm²");
  });

  it("returns undefined for a metric the file does not have", () => {
    expect(formatMetric(undefined, "V/m")).toBeUndefined();
    expect(formatCount(undefined)).toBeUndefined();
  });

  it("renders a count as an integer, never as an exponent", () => {
    expect(formatCount(4957)).toBe("4,957");
    expect(formatCount(1383362)).toBe("1,383,362");
  });
});

// ─── units (SCI-03) ──────────────────────────────────────────────────────────

describe("focality units", () => {
  it("is cm² in mesh space and cm³ in voxel space", () => {
    // The field is called `focality_*_area` in both, which is the naming SCI-03 deliberately
    // kept when it fixed the voxel divisor — so the label is the only place a reader can learn
    // which of the two this run is.
    expect(focalityUnit("mesh")).toBe("cm²");
    expect(focalityUnit("voxel")).toBe("cm³");
    expect(focalityUnit(undefined)).toBe("cm²");
  });

  it("reports total_area_or_volume in mm² / mm³, which SCI-03 did not rescale", () => {
    expect(extentUnit("mesh")).toBe("mm²");
    expect(extentUnit("voxel")).toBe("mm³");
  });
});

// ─── the projection ──────────────────────────────────────────────────────────

describe("metricMap", () => {
  it("reads the two-column Metric/Value shape", () => {
    expect(metricMap(MESH).get("field_name")).toBe("TI_max");
    expect(metricMap(MESH).size).toBe(22);
  });

  it("is empty for a table with other columns", () => {
    expect(metricMap({ columns: ["a", "b"], rows: [["1", "2"]] }).size).toBe(0);
    expect(metricMap(undefined).size).toBe(0);
  });
});

describe("analysisView (mesh)", () => {
  const view = analysisView(MESH, { subject: "ernie", simulation: "Thalamus" });

  it("puts the four descriptive rows in the header block, not in a number grid", () => {
    expect(view.header).toEqual([
      { label: "Subject", value: "ernie" },
      { label: "Simulation", value: "Thalamus" },
      { label: "Field", value: "TI_max", mono: true },
      { label: "Space", value: "Mesh (surface)" },
      { label: "Analysis", value: "Cortical region" },
      { label: "Region", value: "lh.bankssts + rh.bankssts" },
    ]);
  });

  it("leads with the ROI mean and max, at four significant digits with their unit", () => {
    const roi = view.groups.find((g) => g.title === "ROI");
    expect(roi?.metrics).toEqual([
      { label: "Mean", value: "0.07018 V/m", lead: true },
      { label: "Max", value: "0.1084 V/m", lead: true },
      { label: "Min", value: "0.04837 V/m" },
      { label: "Focality ratio", value: "0.8302" },
    ]);
  });

  it("labels the focality extent group with cm² for a mesh analysis", () => {
    const focality = view.groups.find((g) => g.title.startsWith("Focality extent"));
    expect(focality?.title).toBe("Focality extent · cm²");
    expect(focality?.metrics[0]).toEqual({ label: "≥ 50 % of max", value: "119.3 cm²" });
  });

  it("counts mesh elements and reports the ROI area in mm²", () => {
    const extent = view.groups.find((g) => g.title === "ROI extent");
    expect(extent?.metrics).toEqual([
      { label: "Elements", value: "4,957" },
      { label: "Area", value: "2366 mm²" },
    ]);
  });

  it("names every metric the file carries, so nothing falls through to extras", () => {
    expect(view.extras).toEqual([]);
  });

  it("keeps the normal-component group, which only a mesh analysis writes", () => {
    expect(view.groups.map((g) => g.title)).toContain("Normal component");
  });
});

describe("analysisView (voxel)", () => {
  const view = analysisView(VOXEL, { subject: "ernie", simulation: "Thalamus" });

  it("labels the focality extent group with cm³ and the extent as a volume", () => {
    expect(view.groups.find((g) => g.title.startsWith("Focality extent"))?.title).toBe(
      "Focality extent · cm³",
    );
    expect(view.groups.find((g) => g.title === "ROI extent")?.metrics).toEqual([
      { label: "Voxels", value: "15,225" },
      { label: "Volume", value: "15230 mm³" },
    ]);
  });

  it("drops the normal-component group a voxel analysis does not write", () => {
    expect(view.groups.map((g) => g.title)).not.toContain("Normal component");
  });
});

describe("analysisView (degenerate input)", () => {
  it("returns empty sections rather than throwing on a missing table", () => {
    const view = analysisView(undefined);
    expect(view.header).toEqual([]);
    expect(view.groups).toEqual([]);
  });

  it("shows a metric a newer analyzer adds, rather than dropping it", () => {
    const view = analysisView({
      columns: ["Metric", "Value"],
      rows: [
        ["space", "mesh"],
        ["roi_mean", "0.5"],
        ["some_new_metric", "0.123456789"],
      ],
    });
    expect(view.extras).toEqual([{ label: "some new metric", value: "0.1235" }]);
  });
});

// ─── section ordering ────────────────────────────────────────────────────────

describe("orderSections", () => {
  it("renders the Ex-search order whatever order the caller passes", () => {
    const ordered = orderSections([
      { kind: "files", content: null },
      { kind: "figures", figures: [{ path: "/a.png", kind: "png" }] },
      { kind: "metrics", groups: [{ title: "ROI", metrics: [{ label: "Mean", value: "1" }] }] },
      { kind: "header", rows: [{ label: "Subject", value: "ernie" }] },
      { kind: "table", title: "Top 10", content: null },
    ]);
    expect(ordered.map((s) => s.kind)).toEqual(["header", "metrics", "table", "figures", "files"]);
  });

  it("keeps a trailing section below the files, and a custom one above the figures", () => {
    const ordered = orderSections([
      { kind: "trailing", content: null },
      { kind: "files", content: null },
      { kind: "figures", figures: [{ path: "/a.png", kind: "png" }] },
      { kind: "custom", content: null },
      { kind: "header", rows: [{ label: "Subject", value: "ernie" }] },
    ]);
    expect(ordered.map((s) => s.kind)).toEqual(["header", "custom", "figures", "files", "trailing"]);
  });

  it("drops sections with nothing in them", () => {
    const ordered = orderSections([
      { kind: "header", rows: [] },
      { kind: "metrics", groups: [{ title: "ROI", metrics: [] }] },
      { kind: "figures", figures: [] },
      false,
      undefined,
      { kind: "files", content: null },
    ]);
    expect(ordered.map((s) => s.kind)).toEqual(["files"]);
  });

  it("is stable within one kind", () => {
    const ordered = orderSections([
      { kind: "metrics", groups: [{ title: "B", metrics: [{ label: "x", value: "1" }] }] },
      { kind: "metrics", groups: [{ title: "A", metrics: [{ label: "y", value: "2" }] }] },
    ]);
    expect(ordered.map((s) => (s.kind === "metrics" ? s.groups[0]?.title : ""))).toEqual(["B", "A"]);
  });

  it("puts the artifacts under the pictures, and the pictures under the numbers", () => {
    expect(SECTION_ORDER.indexOf("files")).toBeGreaterThan(SECTION_ORDER.indexOf("figures"));
    expect(SECTION_ORDER.indexOf("figures")).toBeGreaterThan(SECTION_ORDER.indexOf("custom"));
    expect(SECTION_ORDER.indexOf("trailing")).toBeGreaterThan(SECTION_ORDER.indexOf("files"));
    expect(SECTION_ORDER.indexOf("figures")).toBeGreaterThan(SECTION_ORDER.indexOf("metrics"));
    expect(SECTION_ORDER.indexOf("metrics")).toBeGreaterThan(SECTION_ORDER.indexOf("header"));
  });
});
