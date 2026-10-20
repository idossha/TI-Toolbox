/**
 * The EEG caps panel's pure core (`pages/panels/caps/model.ts`): which status a cap row shows,
 * which caps Apply would overwrite (the question the existing-outputs dialog asks), and how an
 * inspection becomes scene markers — collapsed electrodes in red, the compare net after the net so
 * marker index i is table row i. Expected values are hand-written fixtures, 2026-10-16.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HelpBody } from "../../src/renderer/ui/HelpPopover";
import {
  CAPS_HELP,
  INSPECT_HELP,
  appliedDate,
  capLabel,
  capStatus,
  defaultCapsSubject,
  electrodeColumns,
  existingAmong,
  inspectionMarkers,
  inspectionWarnings,
  reapplicable,
  sourceLabel,
} from "../../src/renderer/pages/panels/caps/model";
import type { CapInspection, CapStatus } from "../../src/renderer/pages/panels/caps/api";
import { SCENE_CATEGORICAL } from "../../src/renderer/scene/palette";

const cap = (over: Partial<CapStatus>): CapStatus => ({
  name: "A.csv",
  source: "simnibs",
  on_subject: false,
  subject_mtime: null,
  ...over,
});

const inspection = (over: Partial<CapInspection> = {}): CapInspection => ({
  subject: "ernie",
  net: "A.csv",
  collapse_mm: 2,
  electrodes: [
    { name: "Fz", world: [0, 0, 1], nn_mm: 0.5, nn_name: "Cz", scalp_mm: 0 },
    { name: "Cz", world: [0.5, 0, 1], nn_mm: 0.5, nn_name: "Fz", scalp_mm: 0 },
    { name: "Pz", world: [0, -50, 1], nn_mm: 50, nn_name: "Fz", scalp_mm: 0 },
  ],
  collapsed: [{ a: "Fz", b: "Cz", distance_mm: 0.5 }],
  duplicate_names: [],
  summary: { count: 3, nn_min_mm: 0.5, nn_median_mm: 0.5, nn_max_mm: 50, scalp_median_mm: 0, scalp_max_mm: 0 },
  compare: null,
  ...over,
});

describe("caps panel model", () => {
  it("names each status", () => {
    expect(capStatus(cap({})).label).toBe("not on subject");
    expect(capStatus(cap({ on_subject: true })).label).toBe("on subject");
    // A source newer than the subject's copy is not a status: after an image update every cap is.
    expect(capStatus(cap({ on_subject: true, subject_mtime: 1 }))).toMatchObject({ label: "on subject", kind: "success" });
    expect(capStatus(cap({ on_subject: true, source: null })).title).toMatch(/cannot be re-applied/);
  });

  it("names a cap as the rest of the app names a net, and dates only what is on the subject", () => {
    expect(capLabel("GSN-HydroCel-185.csv")).toBe("GSN-HydroCel-185");
    expect(capLabel("GSN-HydroCel-185")).toBe("GSN-HydroCel-185");
    expect(appliedDate(cap({}))).toBe("—");
    expect(appliedDate(cap({ on_subject: true, subject_mtime: 1_760_000_000 }))).toBe(new Date(1_760_000_000_000).toLocaleDateString());
  });

  it("asks before overwriting only the caps already on the subject", () => {
    const caps = [cap({ name: "A.csv", on_subject: true }), cap({ name: "B.csv" }), cap({ name: "Old.csv", on_subject: true, source: null })];
    expect(existingAmong(caps, ["A.csv", "B.csv"])).toEqual(["A.csv"]);
    expect(reapplicable(caps)).toEqual(["A.csv"]);
  });

  it("turns collapsed pairs and duplicate labels into sentences", () => {
    expect(inspectionWarnings(inspection())).toEqual(["1 electrode pair closer than 2 mm: Fz–Cz 0.5 mm"]);
    expect(inspectionWarnings(inspection({ collapsed: [], duplicate_names: ["E1"] }))).toEqual(["Duplicate labels: E1"]);
    expect(inspectionWarnings(inspection({ collapsed: [] }))).toEqual([]);
  });

  it("colours collapsed electrodes red and appends the compare net", () => {
    const markers = inspectionMarkers(
      inspection({ compare: { net: "B.csv", electrodes: [{ name: "X", world: [1, 2, 3] }], median_mm: 1, max_mm: 1 } }),
    );
    expect(markers.map((m) => m.label)).toEqual(["Fz", "Cz", "Pz", "X (B)"]);
    expect(markers.map((m) => m.color)).toEqual([SCENE_CATEGORICAL[7], SCENE_CATEGORICAL[7], SCENE_CATEGORICAL[0], SCENE_CATEGORICAL[1]]);
  });

  it("names each source in plain words", () => {
    expect(["ti-toolbox", "simnibs", "project", null].map((source) => sourceLabel(cap({ source: source as CapStatus["source"] })))).toEqual([
      "TI-Toolbox",
      "SimNIBS",
      "uploaded",
      "subject only",
    ]);
  });

  it("orders the electrode columns label, neighbour, then the two distances, compare last", () => {
    const headers = (net: string | null) => electrodeColumns(net).map((c) => c.header);
    expect(headers(null)).toEqual(["Label", "Nearest electrode", "Spacing to nearest (mm)", "Distance to scalp (mm)"]);
    expect(headers("B.csv").slice(4)).toEqual(["Nearest in B", "Distance to it (mm)"]);
    expect(electrodeColumns(null).map((c) => !!c.numeric)).toEqual([false, false, true, true]);
  });

  it("renders the help as prose and a list covering every control of the panel", () => {
    const html = renderToStaticMarkup(createElement(HelpBody, { text: `${CAPS_HELP}\n\n${INSPECT_HELP}` }));
    expect(html).toContain("<code class=\"help-code\">m2m_&lt;subject&gt;/eeg_positions/</code>");
    expect(html).not.toMatch(/\*\*|`/);
    for (const term of ["Source", "on subject", "Applied", "Add MNI cap…", "Electrode,x,y,z,name", "electrodes", "spacing", "warning", "Electrodes table", "Compare with", "3-D view"]) {
      expect(html).toContain(term);
    }
  });
});

describe("defaultCapsSubject", () => {
  // The project as the maintainer saw it: "102 · no head model" listed before the modelled ones.
  const subjects = [
    { id: "100", has_m2m: false },
    { id: "101", has_m2m: true },
    { id: "102", has_m2m: false },
    { id: "ernie", has_m2m: true },
  ];

  it("opens on the first subject that has a head model, skipping those without", () => {
    expect(defaultCapsSubject(subjects, null)).toBe("101");
  });

  it("keeps the app's current subject when it has a head model, and not when it has none", () => {
    expect(defaultCapsSubject(subjects, "ernie")).toBe("ernie");
    expect(defaultCapsSubject(subjects, "102")).toBe("101");
  });

  it("has no default when no subject has a head model, so the page says so", () => {
    expect(defaultCapsSubject([{ id: "102", has_m2m: false }], "102")).toBeNull();
    expect(defaultCapsSubject([], null)).toBeNull();
  });
});
