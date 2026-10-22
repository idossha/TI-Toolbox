/**
 * An analysis's pictures reach the Results pane, and "Open in viewer" opens its own scene (2026-10-22, p11).
 *
 * Before: `analysisArtifacts` offered only `Analysis.pdf`, so the analyses the current analyzer
 * writes (`histogram.png`, plus the desktop's `scene.png`) showed an empty Figures section -- 5 of
 * 10 on Dataset 000. And the pane's "Open in viewer" asked the server for `kind: "analysis"`
 * without naming the analysis, which the server answers 404. The catalog now lists `figures`
 * (every PNG as `image`, every PDF as `pdf`) and `scene` (`tests/test_catalog_analysis_figures.py`).
 *
 * The rows below are shaped like the server's `Analysis` for sub-101's
 * `cortical_lh.parstriangularis_DK40` on Dataset 000 (paths shortened): histogram.png and
 * scene.png on disk, scene.tetravox.json beside them, no PDF. Expected values are those rows'
 * own paths and the server's kinds; the figure kinds the pane renders as thumbnails are read
 * from the page source, not retyped.
 *
 * Run: cd desktop && npx vitest run tests/unit/results-analysis-figures.test.ts
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { components } from "../../src/renderer/api/schema";
import {
  analysisArtifacts,
  outputsTreeFor,
  viewerLinkFor,
  type OutputNode,
} from "../../src/renderer/pages/results/outputsTree";

type Ana = components["schemas"]["Analysis"];

const DIR = "/mnt/000/derivatives/SimNIBS/sub-101/Simulations/L_Insula/Analyses/Mesh/cortical_lh.parstriangularis_DK40";

function pngOnly(overrides: Partial<Ana> = {}): Ana {
  return {
    name: "cortical_lh.parstriangularis_DK40",
    space: "subject",
    analysis_space: "mesh",
    field: "TI_max",
    roi: "lh.parstriangularis",
    csv: `${DIR}/results.csv`,
    json: `${DIR}/analysis.json`,
    msh: `${DIR}/roi_overlay.msh`,
    nifti: null,
    pdf: null,
    figures: [
      { path: `${DIR}/histogram.png`, kind: "image", label: "histogram" },
      { path: `${DIR}/scene.png`, kind: "image", label: "scene" },
    ],
    scene: `${DIR}/scene.tetravox.json`,
    ...overrides,
  };
}

/** The pane's thumbnail kinds, read from `results/index.tsx` (`FIGURE_KINDS`). */
function figureKinds(): Set<string> {
  const page = readFileSync(join(__dirname, "../../src/renderer/pages/results/index.tsx"), "utf8");
  const match = page.match(/const FIGURE_KINDS = new Set\(\[([^\]]*)\]\)/);
  expect(match, "FIGURE_KINDS is declared in index.tsx").toBeTruthy();
  return new Set([...match![1]!.matchAll(/"([^"]+)"/g)].map((m) => m[1]!));
}

function nodeFor(a: Ana): OutputNode {
  const tree = outputsTreeFor("101", {
    simulations: [],
    flexRuns: [],
    exRuns: [],
    mexRuns: [],
    reports: [],
    analyses: { L_Insula: [a] },
  });
  return tree.groups[0]!.nodes[0]!;
}

describe("analysisArtifacts", () => {
  it("offers every picture the catalog listed as a figure the pane renders", () => {
    const a = pngOnly();
    const kinds = figureKinds();
    const figures = analysisArtifacts(a).filter((x) => kinds.has(x.kind));
    expect(figures.map((f) => f.path)).toEqual(a.figures!.map((f) => f.path));
  });

  it("lists a PDF once, whether the catalog names it as pdf, as a figure, or both", () => {
    const pdf = `${DIR}/histogram_histogram.pdf`;
    const both = pngOnly({ pdf, figures: [{ path: pdf, kind: "pdf", label: "histogram histogram" }] });
    expect(analysisArtifacts(both).filter((x) => x.path === pdf)).toHaveLength(1);
    // An older server that sends no `figures` still shows its PDF.
    const legacy = pngOnly({ pdf, figures: undefined, scene: undefined });
    expect(analysisArtifacts(legacy).filter((x) => x.path === pdf).map((x) => x.kind)).toEqual(["pdf"]);
  });

  it("lists the scene file among the analysis's files, never as a figure", () => {
    const a = pngOnly();
    const kinds = figureKinds();
    const scene = analysisArtifacts(a).filter((x) => x.path === a.scene);
    expect(scene).toHaveLength(1);
    expect(kinds.has(scene[0]!.kind)).toBe(false);
  });

  it("every artifact path is distinct (they are React keys)", () => {
    const paths = analysisArtifacts(pngOnly()).map((x) => x.path);
    expect(new Set(paths).size).toBe(paths.length);
  });
});

describe("viewerLinkFor (an analysis)", () => {
  it("opens the analysis's own scene", () => {
    const a = pngOnly();
    expect(viewerLinkFor("101", nodeFor(a))).toEqual({ subject: "101", kind: "custom", path: a.scene, open: true });
  });

  it("falls back to the masked field when the analysis has no scene", () => {
    const a = pngOnly({ scene: null });
    expect(viewerLinkFor("101", nodeFor(a))).toEqual({ subject: "101", kind: "custom", path: a.msh, open: true });
    const voxel = pngOnly({ scene: null, msh: null, nifti: `${DIR}/roi_overlay.nii.gz` });
    expect(viewerLinkFor("101", nodeFor(voxel))?.path).toBe(voxel.nifti);
  });

  it("offers no button it cannot honour: no scene and no overlay means no link", () => {
    expect(viewerLinkFor("101", nodeFor(pngOnly({ scene: null, msh: null, nifti: null })))).toBeUndefined();
  });

  it("never asks for an analysis scene without naming the analysis", () => {
    for (const a of [pngOnly(), pngOnly({ scene: null })]) {
      const link = viewerLinkFor("101", nodeFor(a));
      expect(link?.kind).not.toBe("analysis");
    }
  });
});
