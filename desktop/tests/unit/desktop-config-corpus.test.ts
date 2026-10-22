// @vitest-environment jsdom
/**
 * The desktop-config corpus: every config a run page or panel BUILDS, with the page's own verdict
 * on it, written to `tests/fixtures/desktop_configs/<page>/<case>.json` — one file per case.
 *
 * What it pins: the bytes each page's real builder emits for one user-visible state, and whether
 * that page's own gate lets the user run it. `tests/test_desktop_config_corpus.py` then feeds every
 * file through the server's real validators (`check_job_config`, `deserialize_config(strict=True)`,
 * `POST /api/validate`, `POST /api/plan`) and asserts the server's accept/refuse equals the page's;
 * `tests/test_runner_dispatch_replay.py` drives each accepted file through `JobManager` into its
 * runner's `main()` and checks the call it reaches against `expect`.
 *
 * Where the numbers come from:
 *   - `jobs[].config` — the REAL builders (`buildSimulationConfig`, `jobsForRow`,
 *     `buildConfig`/`rowTargets`, `toSubmitConfig`, the panels' `config.ts`), and for the panels the
 *     config the rendered panel itself sends to `plan*`/`create*Job`.
 *   - `desktop` — the page's own gate: `isRunnableRow`; `isRunnableOptimizerRow` + `rowFormReason` +
 *     `jobsForRow`; `groupMismatchReason` + `blockedReasonFor`; the pre page's blocked chain; and for
 *     a panel the rendered Run button's `title` (its `clientErrors[0]`).
 *   - `expect` — the user's selection itself (which goal, which mode, the currents the row SHOWS
 *     via `currentValues`), never the builder's output, so a builder that drops the selection
 *     disagrees with it downstream.
 *
 * Reproduce / regenerate:
 *   cd desktop && npx vitest run tests/unit/desktop-config-corpus.test.ts
 *   cd desktop && UPDATE_DESKTOP_CONFIGS=1 npx vitest run tests/unit/desktop-config-corpus.test.ts
 * Without the variable the committed files are compared byte for byte (a drift guard), and a file
 * no case produces any more is a failure.
 *
 * Paths are written under the placeholder project root `/corpus/project`; the Python tests map it
 * onto a synthetic tmp project. Deliberately elsewhere: boundary values (radius 0, NaN, negative
 * currents) belong to the owning fix packages, and disagreements found today are listed — one file
 * each — in `tests/fixtures/desktop_configs/known_gaps/`. Dated 2026-10-22.
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { existsSync, mkdirSync, readdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../src/renderer/api/client", () => ({ getSubjects: vi.fn(async () => []) }));
const planResult = { jobs: [], lock_conflicts: [], cost: { cpus: 1, mem_gb: 1 }, warnings: [] };
const okResult = { ok: true, errors: [] };
vi.mock("../../src/renderer/pages/panels/cluster-permutation/api", () => ({
  getSimulationsFor: vi.fn(async () => []),
  validateStats: vi.fn(async () => okResult),
  planStats: vi.fn(async () => planResult),
  createStatsJob: vi.fn(async () => ({ id: "job" })),
}));
vi.mock("../../src/renderer/pages/panels/nifti-group-average/api", () => ({
  getSimulationsFor: vi.fn(async () => []),
  validateNiftiAverage: vi.fn(async () => okResult),
  planNiftiAverage: vi.fn(async () => planResult),
  createNiftiAverageJob: vi.fn(async () => ({ id: "job" })),
}));
vi.mock("../../src/renderer/pages/panels/nilearn-visuals/api", () => ({
  getSimulationsFor: vi.fn(async () => []),
  validateNilearn: vi.fn(async () => okResult),
  planNilearn: vi.fn(async () => planResult),
  createNilearnJob: vi.fn(async () => ({ id: "job" })),
}));
vi.mock("../../src/renderer/pages/panels/visual-exporter/api", () => ({
  getSimulationsFor: vi.fn(async () => []),
  getAtlasRegions: vi.fn(async () => []),
  getNiftiLabels: vi.fn(async () => []),
  validateBlender: vi.fn(async () => okResult),
  planBlender: vi.fn(async () => planResult),
  createBlenderJob: vi.fn(async () => ({ id: "job" })),
}));
// The run pane (job console), the scene preview and scroll memory have their own tests; the corpus
// reads the form's gate and the config it sends.
vi.mock("../../src/renderer/pages/panels/ExtensionRunPanel", () => ({
  ExtensionRunPanel: () => null,
  useExtensionJobs: () => ({ startedJobIds: [], pinnedJobId: null, setPinnedJobId: () => {}, trackJob: () => {} }),
}));
vi.mock("../../src/renderer/pages/panels/visual-exporter/ExportPreview", () => ({ ExportPreview: () => null }));
vi.mock("../../src/renderer/pages/_shared/session/usePageScrollMemory", () => ({ usePageScrollMemory: () => {} }));

import { buildSimulationConfig, type GlobalParams } from "../../src/renderer/pages/simulator/buildConfig";
import { defaultJobSettings, isRunnableRow, type SelectedRow } from "../../src/renderer/pages/simulator/types";
import { currentValues, rowCurrentsCount } from "../../src/renderer/pages/simulator/MontageManager";
import { simStepRows } from "../../src/renderer/pages/simulator/planStep";
import { automaticRunName, flexOutputFolder, jobsForRow, rowFormReason } from "../../src/renderer/pages/optimizer/plan";
import { emptyOptimizerRow, isRunnableOptimizerRow, type OptimizerRow } from "../../src/renderer/pages/optimizer/rows";
import { defaultFlexFormState, type FlexFormState } from "../../src/renderer/pages/optimizer/flexConfig";
import { defaultExFormState, defaultMExFormState } from "../../src/renderer/pages/optimizer/exConfig";
import { buildConfig as buildAnalyzerConfig, rowTargets, type AnalysisType } from "../../src/renderer/pages/analyzer/buildConfig";
import { blockedReasonFor, groupMismatchReason } from "../../src/renderer/pages/analyzer/AnalyzerPage";
import { isPlannableAnalyzerRow, isRunnableAnalyzerRow, type AnalyzerRow } from "../../src/renderer/pages/analyzer/JobRows";
import { EMPTY_SPHERE } from "../../src/renderer/pages/analyzer/SphereRows";
import { isRoiComplete, type RoiValue } from "../../src/renderer/pages/_shared/roi";
import { subjectsBlockedReason } from "../../src/renderer/pages/_shared/subjects";
import { defaultConfig as defaultPreConfig, plannedSteps, toSubmitConfig } from "../../src/renderer/pages/preprocess/index";
import { buildCorrelationConfig, buildGroupComparisonConfig, type SharedStatsFields } from "../../src/renderer/pages/panels/cluster-permutation/config";
import { buildNiftiAverageConfig } from "../../src/renderer/pages/panels/nifti-group-average/config";
import { buildNilearnConfig } from "../../src/renderer/pages/panels/nilearn-visuals/config";
import { buildMontageConfig, buildRegionConfigs, buildSubcorticalConfig, buildVectorConfig } from "../../src/renderer/pages/panels/visual-exporter/config";
import { clearPageSession, sessionSlot, writeSession } from "../../src/renderer/app/pageSession";
import * as statsApi from "../../src/renderer/pages/panels/cluster-permutation/api";
import * as niftiApi from "../../src/renderer/pages/panels/nifti-group-average/api";
import * as nilearnApi from "../../src/renderer/pages/panels/nilearn-visuals/api";
import * as blenderApi from "../../src/renderer/pages/panels/visual-exporter/api";
import statsPage from "../../src/renderer/pages/panels/cluster-permutation/index";
import niftiPage from "../../src/renderer/pages/panels/nifti-group-average/index";
import nilearnPage from "../../src/renderer/pages/panels/nilearn-visuals/index";
import blenderPage from "../../src/renderer/pages/panels/visual-exporter/index";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const CORPUS = resolve(__dirname, "../../../tests/fixtures/desktop_configs");
const UPDATE = process.env.UPDATE_DESKTOP_CONFIGS === "1";
/** The placeholder project root every absolute path in the corpus sits under. */
const P = "/corpus/project";
const sub = (sid: string) => `${P}/derivatives/SimNIBS/sub-${sid}`;
const NET = "GSN-HydroCel-185.csv";

interface CorpusJob {
  kind: string;
  subject_ids: string[];
  config: unknown;
}
interface CorpusCase {
  id: string;
  page: string;
  title: string;
  jobs: CorpusJob[];
  desktop: { accepts: boolean; reason: string | null };
  expect: Record<string, unknown>;
}

/** Stable key order, so a builder reordering keys is not drift but a value change is. */
function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value as Record<string, unknown>)
        .sort()
        .filter((k) => (value as Record<string, unknown>)[k] !== undefined)
        .map((k) => [k, canonical((value as Record<string, unknown>)[k])]),
    );
  }
  return value;
}

function serialise(c: CorpusCase): string {
  const { id, page, title, jobs, desktop, expect: exp } = c;
  return `${JSON.stringify({ id, page, title, jobs: canonical(jobs), desktop, expect: canonical(exp) }, null, 2)}\n`;
}

/** Compare (or, with UPDATE_DESKTOP_CONFIGS=1, write) one page's directory. */
function checkPage(page: string, cases: CorpusCase[]): void {
  expect(cases.length, `${page} has cases to check`).toBeGreaterThan(0);
  const dir = join(CORPUS, page);
  const want = new Map(cases.map((c) => [`${c.id.split("/")[1]}.json`, serialise(c)]));
  expect(want.size, `${page} case ids are unique`).toBe(cases.length);
  for (const c of cases) expect(c.id.startsWith(`${page}/`), c.id).toBe(true);
  if (UPDATE) {
    mkdirSync(dir, { recursive: true });
    for (const name of readdirSync(dir)) if (!want.has(name)) unlinkSync(join(dir, name));
    for (const [name, text] of want) writeFileSync(join(dir, name), text);
    return;
  }
  expect(existsSync(dir), `${dir} exists (regenerate with UPDATE_DESKTOP_CONFIGS=1)`).toBe(true);
  const onDisk = readdirSync(dir).filter((n) => n.endsWith(".json")).sort();
  expect(onDisk, `${page}: committed files equal the generated cases`).toEqual([...want.keys()].sort());
  for (const [name, text] of want) expect(readFileSync(join(dir, name), "utf8"), `${page}/${name}`).toBe(text);
}

// ---------------------------------------------------------------------------------------------
// Simulator: one row = one job; the gate is `isRunnableRow`.
// ---------------------------------------------------------------------------------------------
const SIM_DEFAULTS: GlobalParams = defaultJobSettings() as GlobalParams;
const xyz = (n: number): [[number, number, number], [number, number, number]][] =>
  Array.from({ length: n }, (_, i) => [
    [-40 - i, 20 + i, 60 - i],
    [40 + i, 20 + i, 60 - i],
  ]);
const labelPairs = (n: number): [string, string][] =>
  Array.from({ length: n }, (_, i) => [`E${String(10 + 2 * i).padStart(3, "0")}`, `E${String(11 + 2 * i).padStart(3, "0")}`]);

function simRow(seed: Partial<SelectedRow>): SelectedRow {
  return { id: "row", subjectId: "001", source: "montage", name: "M1", currents: "1.0,1.0", ...seed };
}

/** `uiMode` is what the user picked (Source cell + net), stated independently of the builder. */
function simCase(slug: string, title: string, row: SelectedRow, ui: { mode: string; carrierOnly?: boolean }): CorpusCase {
  const config = buildSimulationConfig(row, SIM_DEFAULTS) as Record<string, unknown>;
  const accepts = isRunnableRow(row);
  return {
    id: `simulator/${slug}`,
    page: "simulator",
    title,
    jobs: [{ kind: "sim", subject_ids: [row.subjectId], config }],
    desktop: { accepts, reason: accepts ? null : "isRunnableRow is false" },
    expect: {
      runner: "run_simulation",
      montage_mode: ui.mode,
      // The currents the row's channel inputs SHOW (MontageManager's display), not what is sent.
      intensities: currentValues(row.currents, rowCurrentsCount(row)),
      carrier_only: !!ui.carrierOnly,
      tissue_conductivities: row.settings?.customConductivities ?? {},
    },
  };
}

function simulatorCases(): CorpusCase[] {
  const s = (patch: Partial<GlobalParams>) => ({ ...SIM_DEFAULTS, ...patch });
  const step = simStepRows({
    proposalId: "p",
    stepId: "s",
    number: 1,
    title: "Simulate",
    kind: "sim",
    config: { montages: [{ name: "M1", mode: "net", eeg_net: NET, electrode_pairs: labelPairs(2) }] },
    subjectIds: ["001"],
    overwrite: false,
  })[0] as SelectedRow;
  return [
    simCase("ti-net", "TI montage on an EEG net, 2 pairs", simRow({ kind: "uni_polar", eegNet: NET, pairs: labelPairs(2) }), { mode: "net" }),
    simCase("mti-net-4-pairs", "mTI montage, 4 pairs, 4 currents", simRow({ kind: "multi_polar", eegNet: NET, pairs: labelPairs(4), currents: "1.0,1.0,1.0,1.0" }), { mode: "net" }),
    simCase("mti-net-6-pairs", "mTI montage, 6 pairs, 6 currents", simRow({ kind: "multi_polar", eegNet: NET, pairs: labelPairs(6), currents: "1,1,1,1,1,1" }), { mode: "net" }),
    simCase("uni-polar-bucket-4-pairs", "A 4-pair montage stored under uni_polar_montages (2 currents)", simRow({ kind: "uni_polar", eegNet: NET, pairs: labelPairs(4), currents: "1.0,1.0" }), { mode: "net" }),
    simCase("one-pair-montage", "A hand-written 1-pair montage", simRow({ kind: "uni_polar", eegNet: NET, pairs: labelPairs(1) }), { mode: "net" }),
    simCase("three-pair-montage", "A hand-written 3-pair multi_polar montage", simRow({ kind: "multi_polar", eegNet: NET, pairs: labelPairs(3), currents: "1,1,1" }), { mode: "net" }),
    simCase("flex-mapped", "Flex result mapped onto an EEG net", simRow({ source: "flex", name: "flexrun", eegNet: NET, pairs: labelPairs(2) }), { mode: "flex_mapped" }),
    simCase("flex-free", "Flex result at the optimiser's own XYZ", simRow({ source: "flex", name: "flexrun", xyzPairs: xyz(2) }), { mode: "flex_free" }),
    simCase("freehand-2-pairs", "Free-hand, 4 positions", simRow({ source: "freehand", name: "fh", xyzPairs: xyz(2) }), { mode: "freehand" }),
    simCase("freehand-4-pairs", "Free-hand, 8 positions (mTI)", simRow({ source: "freehand", name: "fh8", xyzPairs: xyz(4), currents: "1,1,1,1" }), { mode: "freehand" }),
    simCase("carrier-only-ti", "Carrier-only control on a 2-pair row", simRow({ kind: "uni_polar", eegNet: NET, pairs: labelPairs(2), settings: s({ carrierOnly: true }) }), { mode: "net", carrierOnly: true }),
    simCase("carrier-only-on-mti", "Carrier-only ticked on an mTI row (flag dropped)", simRow({ kind: "multi_polar", eegNet: NET, pairs: labelPairs(4), currents: "1,1,1,1", settings: s({ carrierOnly: true }) }), { mode: "net" }),
    simCase("conductivity-vn", "Anisotropic volume-normalised conductivity", simRow({ kind: "uni_polar", eegNet: NET, pairs: labelPairs(2), settings: s({ conductivity: "vn" }) }), { mode: "net" }),
    simCase("conductivity-dir", "Anisotropic direct conductivity", simRow({ kind: "uni_polar", eegNet: NET, pairs: labelPairs(2), settings: s({ conductivity: "dir" }) }), { mode: "net" }),
    simCase("conductivity-mc", "Anisotropic mean conductivity", simRow({ kind: "uni_polar", eegNet: NET, pairs: labelPairs(2), settings: s({ conductivity: "mc" }) }), { mode: "net" }),
    simCase("tissue-overrides", "Two tissue conductivity overrides", simRow({ kind: "uni_polar", eegNet: NET, pairs: labelPairs(2), settings: s({ customConductivities: { "1": 0.14, "2": 0.33 } }) }), { mode: "net" }),
    simCase("all-output-fields", "Every selectable output field, MNI and fsaverage", simRow({ kind: "uni_polar", eegNet: NET, pairs: labelPairs(2), settings: s({ outputFields: ["TI_max", "TI_avg", "hf_peak", "hf_sar"], mapToMni: true, mapToFsavg: true }) }), { mode: "net" }),
    simCase("plan-step-no-intensities", "A plan step row whose step names no intensities (currents '')", step, { mode: "net" }),
    simCase("currents-zero-one", "Channel currents typed as 0 and 1 mA", simRow({ kind: "uni_polar", eegNet: NET, pairs: labelPairs(2), currents: "0,1" }), { mode: "net" }),
    simCase("no-montage-picked", "A row with a subject but no montage yet", simRow({ name: "", kind: "uni_polar", eegNet: NET, pairs: [] }), { mode: "net" }),
  ];
}

// ---------------------------------------------------------------------------------------------
// Optimizer: one row -> jobsForRow; the gate is isRunnableOptimizerRow + rowFormReason + "a job".
// ---------------------------------------------------------------------------------------------
const AUTO_DATE = new Date(2026, 9, 22, 12, 0, 0, 0);
const CORTICAL_ATLAS = `${P}/derivatives/freesurfer/sub-001/label/lh.aparc.DKTatlas.annot`;
const SUBJECT_LABELING = `${sub("001")}/m2m_001/segmentation/labeling.nii.gz`;
const SUBJECT_MASK = `${P}/derivatives/ti-toolbox/masks/sub-001/imported/target.nii.gz`;
const MNI_MASK = `${P}/derivatives/ti-toolbox/masks/MNI/imported/target_MNI.nii.gz`;
const LEADFIELD = `${sub("001")}/leadfields/GSN-HydroCel-185_leadfield.hdf5`;

const atlasFor = () => (atlas: string) =>
  atlas === "DKTatlas" ? { path: CORTICAL_ATLAS } : atlas === "labeling.nii.gz" ? { path: SUBJECT_LABELING } : undefined;

const sphere: RoiValue = { mode: "spherical", spheres: [{ x: -30, y: 10, z: 5, radius: 10 }], space: "subject", volumetric: false, tissues: "GM" };
const corticalUnion: RoiValue = { mode: "cortical", space: "subject", atlas: "DKTatlas", regions: [{ id: 35, name: "insula", hemi: "lh" }, { id: 35, name: "insula", hemi: "rh" }] };
const corticalOne: RoiValue = { mode: "cortical", space: "subject", atlas: "DKTatlas", regions: [{ id: 35, name: "insula", hemi: "lh" }] };
const subcortical: RoiValue = { mode: "subcortical", space: "subject", atlas: "labeling.nii.gz", regions: [{ id: 10, name: "Left-Thalamus" }], tissues: "GM" };
const subjectMask: RoiValue = { mode: "mask", path: SUBJECT_MASK, space: "subject", tissues: "GM" };

/** What the page submits: `jobsForRow`, then the flex run folder resolved the way index.tsx does. */
function optimizerJobs(row: OptimizerRow): CorpusJob[] {
  return jobsForRow(row, { atlas: atlasFor, leadfield: () => LEADFIELD }).map((job) => {
    const config = { ...(job.config as Record<string, unknown>) };
    if (job.stage === "flex") {
      // index.tsx: plan with output_folder null, then flexOutputFolder(<the server's folder>, ...).
      const folder = `${sub(job.subject)}/flex-search/20261022_120000`;
      config.output_folder = flexOutputFolder(folder, String(config.output_folder ?? ""), automaticRunName(row.id, AUTO_DATE));
    }
    return { kind: job.kind, subject_ids: [job.subject], config };
  });
}

function optimizerVerdict(row: OptimizerRow): CorpusCase["desktop"] {
  if (!isRunnableOptimizerRow(row, () => true)) return { accepts: false, reason: "isRunnableOptimizerRow is false" };
  const reason = rowFormReason(row);
  if (reason) return { accepts: false, reason };
  if (optimizerJobs(row).length === 0) return { accepts: false, reason: "No job resolves to a target yet." };
  return { accepts: true, reason: null };
}

function flexCase(slug: string, title: string, flex: Partial<FlexFormState>, roi: RoiValue, ui: { kind: string; nonRoi?: RoiValue }): CorpusCase {
  const row = emptyOptimizerRow({ subjectId: "001", method: "flex", roi, nonRoi: ui.nonRoi, flex: { ...defaultFlexFormState(), ...flex } });
  row.id = `opt-${slug}`;
  const jobs = optimizerJobs(row);
  const goal = flex.goal ?? defaultFlexFormState().goal;
  return {
    id: `optimizer-flex/${slug}`,
    page: "optimizer-flex",
    title,
    jobs,
    desktop: optimizerVerdict(row),
    expect: { flex_mode: ui.kind, goal, roi_type: roi.mode },
  };
}

function optimizerFlexCases(): CorpusCase[] {
  return [
    flexCase("mean-sphere", "Goal mean, subject-space sphere", { goal: "mean" }, sphere, { kind: "flex" }),
    flexCase("max-cortical-union", "Goal max, lh+rh insula (atlas union)", { goal: "max" }, corticalUnion, { kind: "flex" }),
    flexCase("mean-subcortical", "Goal mean, subject labeling.nii.gz thalamus", { goal: "mean" }, subcortical, { kind: "flex" }),
    flexCase("mean-mask", "Goal mean, an imported subject mask", { goal: "mean" }, subjectMask, { kind: "flex" }),
    flexCase("mean-ratio", "Goal mean with the current ratio optimised", { goal: "mean", optimizeCurrentRatio: true }, sphere, { kind: "flex" }),
    flexCase("focality-manual", "Focality, manual thresholds 0.1,0.3", { goal: "focality", focalityMode: "manual", manualThresholds: "0.1,0.3" }, sphere, { kind: "flex" }),
    flexCase("focality-manual-ratio", "Focality, manual thresholds, ratio optimised", { goal: "focality", focalityMode: "manual", manualThresholds: "0.1,0.3", optimizeCurrentRatio: true }, sphere, { kind: "flex" }),
    flexCase("focality-manual-blank", "Focality, manual mode with the thresholds box left blank", { goal: "focality", focalityMode: "manual", manualThresholds: "" }, sphere, { kind: "flex" }),
    flexCase("focality-adaptive", "Focality, adaptive thresholds", { goal: "focality", focalityMode: "adaptive" }, sphere, { kind: "flex_adaptive" }),
    flexCase("focality-adaptive-ratio", "Focality, adaptive thresholds, ratio optimised", { goal: "focality", focalityMode: "adaptive", optimizeCurrentRatio: true }, sphere, { kind: "flex_adaptive" }),
    flexCase("focality-pareto", "Focality, multi-threshold sweep", { goal: "focality", focalityMode: "pareto" }, sphere, { kind: "flex_pareto" }),
    flexCase("focality-pareto-ratio", "Focality, multi-threshold sweep, ratio optimised", { goal: "focality", focalityMode: "pareto", optimizeCurrentRatio: true }, sphere, { kind: "flex_pareto" }),
    flexCase("focality-tf-specific-nonroi", "focality_tf with a specific (atlas) non-ROI", { goal: "focality_tf", nonRoiMethod: "specific" }, sphere, { kind: "flex", nonRoi: corticalOne }),
    flexCase("rect-10x6", "Rectangular 10x6 electrodes", { goal: "mean", electrodeShape: "rect", dimensionWidth: 10, dimensionHeight: 6 }, sphere, { kind: "flex" }),
    flexCase("ellipse-8x10", "Ellipse with unequal dimensions 8x10", { goal: "mean", electrodeShape: "ellipse", dimensionWidth: 8, dimensionHeight: 10 }, sphere, { kind: "flex" }),
    flexCase("min-distance-0", "Minimum electrode distance 0 mm", { goal: "mean", minElectrodeDistance: 0 }, sphere, { kind: "flex" }),
    flexCase("mapped-net", "Mapped-electrode simulation on an EEG net", { goal: "mean", enableMapping: true, eegNet: NET }, sphere, { kind: "flex" }),
  ];
}

function exRow(slug: string, seed: Partial<OptimizerRow>): OptimizerRow {
  const row = emptyOptimizerRow({ subjectId: "001", method: "ex", net: "GSN-HydroCel-185", ...seed });
  row.id = `opt-${slug}`;
  return row;
}

function exCase(slug: string, title: string, row: OptimizerRow, ui: { runner: string; roiNames: string[] }): CorpusCase {
  return {
    id: `optimizer-ex/${slug}`,
    page: "optimizer-ex",
    title,
    jobs: optimizerJobs(row),
    desktop: optimizerVerdict(row),
    expect: { runner: ui.runner, roi_names: ui.roiNames },
  };
}

function optimizerExCases(): CorpusCase[] {
  const buckets = { e1_plus: ["E010", "E012"], e1_minus: ["E011", "E013"], e2_plus: ["E020", "E022"], e2_minus: ["E021", "E023"] };
  const mexBuckets = { ...buckets, e3_plus: ["E030"], e3_minus: ["E031"], e4_plus: ["E040"], e4_minus: ["E041"] };
  const ex = (patch: Partial<OptimizerRow["ex"]>) => ({ ...defaultExFormState(), buckets, ...patch });
  const saved = (names: string[], combine: boolean): RoiValue => ({ mode: "saved", selected: names, combine, radius: 3, space: "subject" });
  return [
    exCase("bucketed-saved", "Ex, bucketed electrodes, one saved ROI", exRow("bucketed-saved", { ex: ex({}), roi: saved(["L_Insula"], false) }), { runner: "run_ex_search", roiNames: ["L_Insula"] }),
    exCase("pool-saved-combined", "Ex, electrode pool, two saved ROIs combined", exRow("pool-saved-combined", { ex: ex({ electrodeMode: "all", pool: ["E010", "E011", "E012", "E013", "E014"] }), roi: saved(["L_Insula", "R_Insula"], true) }), { runner: "run_ex_search", roiNames: ["L_Insula+R_Insula"] }),
    exCase("bucketed-saved-separate", "Ex, two saved ROIs run separately (two jobs)", exRow("bucketed-saved-separate", { ex: ex({}), roi: saved(["L_Insula", "R_Insula"], false) }), { runner: "run_ex_search", roiNames: ["L_Insula", "R_Insula"] }),
    exCase("bucketed-subcortical", "Ex, subject labeling.nii.gz thalamus", exRow("bucketed-subcortical", { ex: ex({}), roi: subcortical }), { runner: "run_ex_search", roiNames: ["labeling.nii.gz_1region"] }),
    exCase("bucketed-mask", "Ex, imported subject mask", exRow("bucketed-mask", { ex: ex({}), roi: subjectMask }), { runner: "run_ex_search", roiNames: ["target"] }),
    exCase("pool-too-small", "Ex, electrode pool of three", exRow("pool-too-small", { ex: ex({ electrodeMode: "all", pool: ["E010", "E011", "E012"] }), roi: saved(["L_Insula"], false) }), { runner: "run_ex_search", roiNames: ["L_Insula"] }),
    exCase("mex-saved", "mEx, eight buckets, one saved ROI", exRow("mex-saved", { exPairs: 4, mex: { ...defaultMExFormState(), buckets: mexBuckets }, roi: saved(["L_Insula"], false) }), { runner: "run_m_ex_search", roiNames: ["L_Insula"] }),
    exCase("mex-subcortical", "mEx, subject labeling.nii.gz thalamus", exRow("mex-subcortical", { exPairs: 4, mex: { ...defaultMExFormState(), buckets: mexBuckets }, roi: subcortical }), { runner: "run_m_ex_search", roiNames: ["labeling.nii.gz_1region"] }),
  ];
}

// ---------------------------------------------------------------------------------------------
// Analyzer: rows -> AnalyzerPage's config composition (buildConfig x rowTargets); the gate is
// blockedReasonFor(groupMismatchReason, targetReady).
// ---------------------------------------------------------------------------------------------
function analyzerRow(seed: Partial<AnalyzerRow>): AnalyzerRow {
  return { id: "a", subjectId: "001", simulation: "M1", space: "mesh", field: "TI_max", tissue: "GM", roi: sphere, combine: true, ...seed };
}

/** AnalyzerPage.tsx's `configs` derivation, line for line over the page's exported pieces. */
function analyzerJobs(rows: AnalyzerRow[], group: boolean): { jobs: CorpusJob[]; desktop: CorpusCase["desktop"] } {
  const runnable = rows.filter(isRunnableAnalyzerRow);
  const cohort = [...new Set(runnable.map((r) => r.subjectId))];
  const targetReady = runnable.length > 0 && runnable.every((r) => isRoiComplete(r.roi));
  const groupMismatch = group ? groupMismatchReason(rows) : null;
  const effectiveSubjectIds = group ? cohort : runnable.map((r) => r.subjectId);
  const reason = blockedReasonFor({ subjectsBlocked: subjectsBlockedReason(effectiveSubjectIds, []), rowCount: runnable.length, groupMismatch, targetReady });
  const plannable = rows.filter(isPlannableAnalyzerRow);
  const make = (row: AnalyzerRow, roi: RoiValue) =>
    buildAnalyzerConfig({
      mode: group ? "group" : "single",
      subjectId: group ? null : row.subjectId,
      subjectIds: group ? cohort : [],
      simulation: row.simulation,
      space: row.space,
      tissueType: row.tissue,
      field: row.field,
      analysisType: roi.mode as AnalysisType,
      coordinateSpace: roi.space,
      roiValue: roi,
      sphere: roi.mode === "spherical" ? (roi.spheres[0] ?? EMPTY_SPHERE) : EMPTY_SPHERE,
    });
  const lead = plannable[0];
  const configs = group ? (lead ? rowTargets(lead).map((roi) => make(lead, roi)) : []) : plannable.flatMap((row) => rowTargets(row).map((roi) => make(row, roi)));
  return {
    jobs: configs.map((config) => ({ kind: "analyzer", subject_ids: group ? cohort : [config.subject_id as string], config })),
    desktop: { accepts: reason === null, reason },
  };
}

function analyzerCase(slug: string, title: string, rows: AnalyzerRow[], group: boolean, ui: Record<string, unknown>): CorpusCase {
  const { jobs, desktop } = analyzerJobs(rows, group);
  return { id: `analyzer/${slug}`, page: "analyzer", title, jobs, desktop, expect: ui };
}

function analyzerCases(): CorpusCase[] {
  const mniSphere: RoiValue = { ...sphere, space: "mni", spheres: [{ x: -38, y: 4, z: 2, radius: 8 }] } as RoiValue;
  const twoRegions: RoiValue = { mode: "cortical", space: "subject", atlas: "DK40", regions: [{ id: 35, name: "insula", hemi: "lh" }, { id: 30, name: "precuneus", hemi: "lh" }] };
  const mniMask: RoiValue = { mode: "mask", path: MNI_MASK, space: "mni", tissues: "GM" };
  const thal: RoiValue = { mode: "subcortical", space: "subject", atlas: "labeling.nii.gz", regions: [{ id: 10, name: "Left-Thalamus" }], tissues: "GM" };
  return [
    analyzerCase("mesh-sphere-single", "Mesh, subject-space sphere, one subject", [analyzerRow({})], false, { method: "analyze_sphere", calls: 1 }),
    analyzerCase("voxel-sphere-mni-both", "Voxel, MNI sphere, GM+WM", [analyzerRow({ space: "voxel", tissue: "both", roi: mniSphere })], false, { method: "analyze_sphere", calls: 1, tissue_type: "both" }),
    analyzerCase("mesh-cortical-one", "Mesh, cortical lh.insula", [analyzerRow({ roi: { ...twoRegions, regions: [twoRegions.regions[0]!] } as RoiValue })], false, { method: "analyze_cortex", calls: 1, regions: [["lh.insula"]] }),
    analyzerCase("mesh-cortical-combined", "Mesh, two cortical regions combined", [analyzerRow({ roi: twoRegions, combine: true })], false, { method: "analyze_cortex", calls: 1, regions: [["lh.insula", "lh.precuneus"]] }),
    analyzerCase("mesh-cortical-separate", "Mesh, two cortical regions run separately", [analyzerRow({ roi: twoRegions, combine: false })], false, { method: "analyze_cortex", calls: 2, regions: [["lh.insula"], ["lh.precuneus"]] }),
    analyzerCase("voxel-subcortical-subject", "Voxel, subject labeling.nii.gz Left-Thalamus", [analyzerRow({ space: "voxel", roi: thal })], false, { method: "analyze_subcortical", calls: 1, regions: [["Left-Thalamus"]] }),
    analyzerCase("mesh-subcortical-subject", "Mesh, subject labeling.nii.gz Left-Thalamus", [analyzerRow({ roi: thal })], false, { method: "analyze_subcortical", calls: 1, regions: [["Left-Thalamus"]] }),
    analyzerCase("voxel-mask-subject", "Voxel, imported subject mask", [analyzerRow({ space: "voxel", roi: subjectMask })], false, { method: "analyze_mask", calls: 1 }),
    analyzerCase("mesh-field-hf-peak", "Mesh sphere measuring hf_peak", [analyzerRow({ field: "hf_peak" })], false, { method: "analyze_sphere", calls: 1, field: "hf_peak" }),
    analyzerCase("group-sphere-mni", "Group of two, MNI sphere", [analyzerRow({ roi: mniSphere }), analyzerRow({ subjectId: "002", roi: mniSphere })], true, { method: "run_group_analysis", calls: 1, subjects: ["001", "002"] }),
    analyzerCase("group-mask-mni", "Group of two, MNI mask", [analyzerRow({ space: "voxel", roi: mniMask }), analyzerRow({ subjectId: "002", space: "voxel", roi: mniMask })], true, { method: "run_group_analysis", calls: 1, subjects: ["001", "002"] }),
    analyzerCase("group-mask-subject", "Group of two, subject-space mask", [analyzerRow({ space: "voxel", roi: subjectMask }), analyzerRow({ subjectId: "002", space: "voxel", roi: subjectMask })], true, { method: "run_group_analysis", calls: 1, subjects: ["001", "002"] }),
  ];
}

// ---------------------------------------------------------------------------------------------
// Pre-processing: toSubmitConfig; the gate is the page's blocked chain (subjects, steps, FreeSurfer).
// ---------------------------------------------------------------------------------------------
function preCase(slug: string, title: string, flags: Record<string, boolean>, subjects: string[], policy: "skip" | "replace"): CorpusCase {
  const values = { ...defaultPreConfig(), ...flags };
  const config = toSubmitConfig(values, subjects, policy, undefined);
  const reason = subjectsBlockedReason(subjects, []) ?? (plannedSteps(values).length === 0 ? "Select at least one processing step." : null);
  const stages = Object.entries({ convert_dicom: "G1", create_m2m: "G2a", run_fastsurfer: "G2b", run_freesurfer: "G2c", run_tissue_analysis: "G3", run_qsiprep: "G4", run_qsirecon: "G5", extract_dti: "G6" })
    .filter(([flag]) => (values as unknown as Record<string, boolean>)[flag])
    .map(([, tag]) => tag);
  return {
    id: `preprocess/${slug}`,
    page: "preprocess",
    title,
    jobs: [{ kind: "pre", subject_ids: subjects, config }],
    desktop: { accepts: reason === null, reason },
    expect: { stages_per_subject: stages, skip_existing_outputs: policy === "skip" },
  };
}

function preprocessCases(): CorpusCase[] {
  const none = { convert_dicom: false, create_m2m: false, run_fastsurfer: false, run_freesurfer: false, run_tissue_analysis: false, run_qsiprep: false, run_qsirecon: false, extract_dti: false };
  return [
    preCase("defaults", "The page's default steps for one subject", {}, ["001"], "skip"),
    preCase("charm-only-replace", "Head model only, replacing existing outputs", { ...none, create_m2m: true }, ["001", "002"], "replace"),
    preCase("dwi-chain", "QSIPrep, QSIRecon and DTI extraction", { ...none, run_qsiprep: true, run_qsirecon: true, extract_dti: true }, ["001"], "skip"),
    preCase("no-steps", "No step ticked", none, ["001"], "skip"),
  ];
}

// ---------------------------------------------------------------------------------------------
// Panels: render the real panel with its session seeded, read the Run button (title =
// clientErrors[0]) and capture the config it hands the server.
// ---------------------------------------------------------------------------------------------
type PanelPage = { Component: () => React.ReactElement | null };

async function renderPanel(page: PanelPage, session: Record<string, unknown>): Promise<{ title: string | null; disabled: boolean; click: () => Promise<void>; unmount: () => void }> {
  clearPageSession();
  for (const [key, value] of Object.entries(session)) writeSession(sessionSlot("", key), value);
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = page.Component;
  act(() => root.render(React.createElement(QueryClientProvider, { client }, React.createElement(Panel))));
  // The panels debounce their validate/plan key (350-400 ms) before asking the server.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1500);
  });
  const button = container.querySelector<HTMLButtonElement>('[data-testid="run-button"]');
  expect(button, "the panel renders its Run button").not.toBeNull();
  return {
    title: button!.getAttribute("title"),
    disabled: button!.disabled,
    click: async () => {
      await act(async () => {
        button!.click();
        await vi.advanceTimersByTimeAsync(100);
      });
    },
    unmount: () => {
      act(() => root.unmount());
      client.clear();
      container.remove();
    },
  };
}

afterEach(() => {
  vi.useRealTimers();
});

const SHARED: SharedStatsFields = {
  analysisName: "corpus_stats",
  clusterThreshold: 0.05,
  clusterStat: "mass",
  nPermutations: 1000,
  alpha: 0.05,
  nJobs: -1,
  tissueType: "grey",
  niftiPattern: "",
  space: "mni",
  fsaverageField: "TI_max",
  fsaverageSpacing: 5,
  atlasFiles: [],
};
/** The panel's session-backed defaults (cluster-permutation/index.tsx `usePageSession` seeds). */
const CLASSIFICATION_EXTRA = { testType: "unpaired" as const, alternative: "two-sided" as const, group1Name: "Responders", group2Name: "Non-Responders", valueMetric: "Current intensity" };
const CORRELATION_EXTRA = { correlationType: "pearson" as const, useWeights: true, effectMetric: "Effect size", fieldMetric: "Electric field magnitude" };

interface StatsRow { subjectId: string; simulationName: string; response: 0 | 1; effectSize?: number; weight?: number }

async function statsCase(slug: string, title: string, mode: "classification" | "correlation", rows: StatsRow[], session: Record<string, unknown>): Promise<CorpusCase> {
  vi.useFakeTimers();
  vi.mocked(statsApi.planStats).mockClear();
  const panel = await renderPanel(statsPage as unknown as PanelPage, {
    mode,
    analysisName: SHARED.analysisName,
    rows: rows.map((r, i) => ({ id: `r${i}`, effectSize: undefined, weight: undefined, ...r })),
    ...session,
  });
  const extra = { ...CLASSIFICATION_EXTRA, ...(session["classification.testType"] ? { testType: session["classification.testType"] as "paired" } : {}) };
  const built =
    mode === "classification"
      ? buildGroupComparisonConfig(SHARED, rows, extra)
      : buildCorrelationConfig(SHARED, rows.map((r) => ({ subjectId: r.subjectId, simulationName: r.simulationName, effectSize: r.effectSize ?? 0, weight: r.weight ?? 1 })), CORRELATION_EXTRA);
  const subjects = [...new Set(rows.map((r) => r.subjectId))];
  const sent = vi.mocked(statsApi.planStats).mock.calls.at(-1);
  panel.unmount();
  const accepts = panel.title === null;
  // A panel that lets the user run must send exactly what its builder builds for these inputs.
  if (accepts) expect(sent, `${slug}: the panel planned the config it would submit`).toEqual([built, subjects]);
  else expect(panel.disabled, `${slug}: a blocked panel disables Run`).toBe(true);
  return {
    id: `panels-stats/${slug}`,
    page: "panels-stats",
    title,
    jobs: [{ kind: "stats", subject_ids: subjects, config: built }],
    desktop: { accepts, reason: panel.title },
    expect: { runner_call: mode === "classification" ? "run_group_comparison" : "run_correlation" },
  };
}

async function niftiCase(slug: string, title: string, rows: { subjectId: string; simulationName: string; group: string }[], space: "subject" | "mni", ui: { groups: string[] }): Promise<CorpusCase> {
  vi.useFakeTimers();
  vi.mocked(niftiApi.planNiftiAverage).mockClear();
  const panel = await renderPanel(niftiPage as unknown as PanelPage, { rows: rows.map((r, i) => ({ id: `n${i}`, ...r })), outputName: "corpus_average", space, pattern: "", diffPairs: "" });
  const built = buildNiftiAverageConfig({ outputName: "corpus_average", rows, space, niftiFilePattern: "", diffPairs: [] });
  const subjects = [...new Set(rows.map((r) => r.subjectId))];
  const sent = vi.mocked(niftiApi.planNiftiAverage).mock.calls.at(-1);
  panel.unmount();
  const accepts = panel.title === null;
  if (accepts) expect(sent, `${slug}: the panel planned the config it would submit`).toEqual([built, subjects]);
  return {
    id: `panels-nifti/${slug}`,
    page: "panels-nifti",
    title,
    jobs: [{ kind: "nifti_average", subject_ids: subjects, config: built }],
    desktop: { accepts, reason: panel.title },
    expect: { nifti_pattern_space: space, groups: ui.groups },
  };
}

async function nilearnCase(slug: string, title: string, pairs: { subjectId: string; simulationName: string }[]): Promise<CorpusCase> {
  vi.useFakeTimers();
  vi.mocked(nilearnApi.planNilearn).mockClear();
  const panel = await renderPanel(nilearnPage as unknown as PanelPage, { pairs: pairs.map((p, i) => ({ id: `p${i}`, ...p })), subdir: "corpus_figs" });
  const sent = vi.mocked(nilearnApi.planNilearn).mock.calls.at(-1);
  panel.unmount();
  const accepts = panel.title === null;
  const subjects = [...new Set(pairs.map((p) => p.subjectId))];
  const built = (sent?.[0] as unknown) ?? buildNilearnConfig({ pairs, subdirName: "corpus_figs", usePercentiles: false, atlasName: "harvard_oxford_sub", selectedRegion: "__all__" });
  return {
    id: `panels-nilearn/${slug}`,
    page: "panels-nilearn",
    title,
    jobs: [{ kind: "nilearn", subject_ids: subjects, config: built }],
    desktop: { accepts, reason: panel.title },
    expect: { pairs: pairs.map((p) => [p.subjectId, p.simulationName]) },
  };
}

async function blenderCase(slug: string, title: string, session: Record<string, unknown>, built: unknown[], ui: { types: string[] }): Promise<CorpusCase> {
  vi.useFakeTimers();
  vi.mocked(blenderApi.createBlenderJob).mockClear();
  const panel = await renderPanel(blenderPage as unknown as PanelPage, session);
  const accepts = panel.title === null;
  if (accepts) {
    await panel.click();
    // One Run click submits every config the mode builds (regions: an STL and a PLY job).
    expect(vi.mocked(blenderApi.createBlenderJob).mock.calls, `${slug}: the panel submits its builder's configs`).toEqual(built.map((c) => [c, [session.subjectId]]));
  }
  panel.unmount();
  return {
    id: `visual-exporter/${slug}`,
    page: "visual-exporter",
    title,
    jobs: built.map((config) => ({ kind: "blender", subject_ids: [session.subjectId as string], config })),
    desktop: { accepts, reason: panel.title },
    expect: { blender_types: ui.types },
  };
}

// ---------------------------------------------------------------------------------------------
describe("desktop config corpus", () => {
  it("simulator", () => checkPage("simulator", simulatorCases()));
  it("optimizer-flex", () => checkPage("optimizer-flex", optimizerFlexCases()));
  it("optimizer-ex", () => checkPage("optimizer-ex", optimizerExCases()));
  it("analyzer", () => checkPage("analyzer", analyzerCases()));
  it("preprocess", () => checkPage("preprocess", preprocessCases()));

  it("panels-stats", async () => {
    const r = (subjectId: string, response: 0 | 1, effectSize?: number): StatsRow => ({ subjectId, simulationName: "M1", response, effectSize, weight: effectSize === undefined ? undefined : 1 });
    checkPage("panels-stats", [
      await statsCase("classification-2-groups", "Classification, one subject per response group", "classification", [r("001", 1), r("002", 0)], {}),
      await statsCase("classification-paired-2v1", "Paired classification, 2 responders vs 1", "classification", [r("001", 1), r("002", 1), r("003", 0)], { "classification.testType": "paired" }),
      await statsCase("classification-one-group", "Classification with every subject a responder", "classification", [r("001", 1), r("002", 1)], {}),
      await statsCase("correlation-3-rows", "Correlation over three subjects", "correlation", [r("001", 0, 0.4), r("002", 0, 1.2), r("003", 0, -0.3)], {}),
      await statsCase("correlation-2-rows", "Correlation over two subjects", "correlation", [r("001", 0, 0.4), r("002", 0, 1.2)], {}),
    ]);
  });

  it("panels-nifti", async () => {
    const row = (subjectId: string, group: string) => ({ subjectId, simulationName: "M1", group });
    checkPage("panels-nifti", [
      await niftiCase("subject-space", "Two groups averaged in subject space", [row("001", "Group1"), row("002", "Group2")], "subject", { groups: ["Group1", "Group2"] }),
      await niftiCase("mni-space", "Two groups averaged in MNI space", [row("001", "Group1"), row("002", "Group2")], "mni", { groups: ["Group1", "Group2"] }),
      await niftiCase("hyphen-space-labels", "Group labels with a hyphen and a space", [row("001", "pre-op"), row("002", "post op")], "mni", { groups: ["pre-op", "post op"] }),
      await niftiCase("untrimmed-label", "One row typed 'Group1 ' with a trailing space", [row("001", "Group1"), row("002", "Group1 ")], "mni", { groups: ["Group1"] }),
    ]);
  });

  it("panels-nilearn", async () => {
    checkPage("panels-nilearn", [
      await nilearnCase("one-pair", "One subject/simulation pair", [{ subjectId: "001", simulationName: "M1" }]),
      await nilearnCase("two-pairs", "Two pairs averaged", [{ subjectId: "001", simulationName: "M1" }, { subjectId: "002", simulationName: "M1" }]),
    ]);
  });

  it("visual-exporter", async () => {
    const base = { subjectId: "001", simulationName: "M1" };
    checkPage("visual-exporter", [
      await blenderCase("regions", "Cortical regions lh.insula (STL + PLY)", { ...base, mode: "regions", regions: ["lh.insula"] },
        buildRegionConfigs({ ...base, atlas: "DK40", fieldName: "TI_max", regions: ["lh.insula"] }), { types: ["RegionConfig", "RegionConfig"] }),
      await blenderCase("vectors", "Vector field export", { ...base, mode: "vectors" },
        [buildVectorConfig({ ...base, exportCh1Ch2: false, exportSum: false, exportTiNormal: false, count: 10000, allNodes: false, seed: 42, lengthScale: 1, vectorWidth: 1, anchor: "tail", color: "rgb", bluePercentile: 50, greenPercentile: 80, redPercentile: 95 })], { types: ["VectorConfig"] }),
      await blenderCase("montage", "Montage publication scene (net montage)", { ...base, mode: "montage" },
        [buildMontageConfig({ ...base, montageOnly: false, electrodeDiameterMm: 10, electrodeHeightMm: 6 })], { types: ["MontageConfig"] }),
      await blenderCase("montage-xyz", "Montage publication scene for an XYZ (free-hand) simulation", { subjectId: "001", simulationName: "FH1", mode: "montage" },
        [buildMontageConfig({ subjectId: "001", simulationName: "FH1", montageOnly: false, electrodeDiameterMm: 10, electrodeHeightMm: 6 })], { types: ["MontageConfig"] }),
      await blenderCase("subcortical", "Subcortical labels 10,49 from labeling.nii.gz", { ...base, mode: "subcortical", niftiPath: SUBJECT_LABELING, labelsText: "10,49" },
        [buildSubcorticalConfig({ ...base, niftiPath: SUBJECT_LABELING, labels: [10, 49], cleanComponents: false, fieldName: "TI_max" })], { types: ["SubcorticalConfig"] }),
    ]);
  });

  it("every known gap names cases that exist, an owner and a reason", () => {
    const dir = join(CORPUS, "known_gaps");
    const files = readdirSync(dir).filter((n) => n.endsWith(".json"));
    expect(files.length, "known gaps to check").toBeGreaterThan(0);
    for (const name of files) {
      const gap = JSON.parse(readFileSync(join(dir, name), "utf8")) as { case_ids: string[]; owner: string; reason: string; checks: string[] };
      expect(gap.case_ids.length, name).toBeGreaterThan(0);
      expect(gap.owner, name).toMatch(/^(p\d\d|triage)$/);
      expect(gap.reason.length, name).toBeGreaterThan(20);
      expect(gap.checks.every((c) => ["verdict", "dispatch"].includes(c)) && gap.checks.length > 0, name).toBe(true);
      expect(name.startsWith(`${gap.case_ids[0]!.split("/")[0]}-`), `${name} is named for its page`).toBe(true);
      for (const id of gap.case_ids) expect(existsSync(join(CORPUS, `${id}.json`)), `${name}: ${id}`).toBe(true);
    }
  });
});
