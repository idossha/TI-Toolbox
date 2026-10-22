// @vitest-environment jsdom
/**
 * The Pre-processing page's submission, written to `contracts/fixtures/pre/<scenario>.json`.
 *
 * What it pins (2026-10-22, p27): the exact config `toSubmitConfig` sends to `POST /api/jobs/groups`
 * for four user-visible states — the page's defaults; QSIPrep + QSIRecon with saved processing
 * preferences (patch2self, mrdegibbs, MNI normalization, two atlases) and resource limits;
 * FreeSurfer subregions only (recon-all off in Settings); and "replace" for two subjects with saved
 * charm options. Each file also carries what produced it: the user's saved preferences (the
 * `PUT /api/surfer-settings` body), the CPU capacity, and the `GET /api/surfer-settings` body the
 * page received (`settings`, built here from the preferences the way `tit.surfer_settings.read_settings`
 * does; `tests/test_pre_desktop_runner_contract.py` asserts the server returns exactly it).
 *
 * The Python side then submits each `config`, reads every stage's `config.json` and feeds it to the
 * `tit.pre` runner, and checks that an agent sending only `{subject_ids, run_qsiprep, run_qsirecon,
 * run_freesurfer}` with the same saved preferences gets the same processing choices.
 *
 * Reproduce / regenerate:
 *   cd desktop && npx vitest run tests/unit/preprocess-submit-golden.test.ts
 *   cd desktop && UPDATE_PRE_FIXTURES=1 npx vitest run tests/unit/preprocess-submit-golden.test.ts
 * Without the variable the committed files are compared byte for byte, and a file no scenario
 * produces is a failure. The page's gate (blocked reasons) is the desktop-config corpus's job.
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { defaultConfig, toSubmitConfig, type ExistingOutputPolicy } from "../../src/renderer/pages/preprocess/index";
import { defaultQsiPrepConfig, defaultQsiReconConfig } from "../../src/renderer/pages/preprocess/qsi";
import type { SurferSettings } from "../../src/renderer/pages/settings/api";
import type { PreprocessConfig } from "../../src/renderer/pages/preprocess/api";

const DIR = resolve(__dirname, "../../../contracts/fixtures/pre");
const UPDATE = process.env.UPDATE_PRE_FIXTURES === "1";
const CAPACITY = 8;

const STEP_FLAGS = [
  "convert_dicom",
  "create_m2m",
  "run_fastsurfer",
  "run_freesurfer",
  "run_tissue_analysis",
  "run_qsiprep",
  "run_qsirecon",
  "extract_dti",
] as const;
type Flags = Partial<Record<(typeof STEP_FLAGS)[number], boolean>>;
const NONE: Flags = Object.fromEntries(STEP_FLAGS.map((f) => [f, false]));

type Preferences = Record<string, unknown>;

/** A QSI settings dict without its resource fields: the processing preferences Settings saves. */
function processing(settings: object): Record<string, unknown> {
  return Object.fromEntries(Object.entries(settings).filter(([k]) => !["cpus", "memory_gb", "omp_threads"].includes(k)));
}

/** What `GET /api/surfer-settings` returns for *prefs* at *capacity* (license status aside). */
function settingsFor(prefs: Preferences, capacity: number): Omit<SurferSettings, "freesurfer_license"> {
  const qsiprep = processing(defaultQsiPrepConfig());
  const qsirecon = processing(defaultQsiReconConfig());
  const tools = ["fastsurfer", "freesurfer", "charm", "qsiprep", "qsirecon"];
  const saved = {
    ...Object.fromEntries(tools.map((t) => [`${t}_threads`, null])),
    qsiprep_memory_gb: null,
    qsirecon_memory_gb: null,
    qsiprep_omp_threads: null,
    qsirecon_omp_threads: null,
    charm_options: null,
    freesurfer_recon_all: true,
    freesurfer_subregions: ["thalamus", "hippo-amygdala"],
    ...prefs,
    qsiprep_config: { ...qsiprep, ...((prefs.qsiprep_config as object) ?? {}) },
    qsi_recon_config: { ...qsirecon, ...((prefs.qsi_recon_config as object) ?? {}) },
  } as Record<string, unknown>;
  const effective = Object.fromEntries(
    tools.map((t) => [`effective_${t}_threads`, Math.min(capacity, (saved[`${t}_threads`] as number | null) ?? capacity)]),
  );
  return { ...saved, ...effective, available_threads: capacity, default_threads: capacity } as Omit<SurferSettings, "freesurfer_license">;
}

interface Scenario {
  id: string;
  title: string;
  preferences: Preferences;
  flags: Flags;
  subject_ids: string[];
  policy: ExistingOutputPolicy;
}

const SCENARIOS: Scenario[] = [
  {
    id: "defaults",
    title: "The page's default steps, nothing saved in Settings",
    preferences: {},
    flags: {},
    subject_ids: ["001"],
    policy: "skip",
  },
  {
    id: "qsi-preferences",
    title: "QSIPrep and QSIRecon with saved processing preferences and resource limits",
    preferences: {
      qsiprep_config: { denoise_method: "patch2self", unringing_method: "mrdegibbs", mni_normalization: true, output_resolution: 1.5 },
      qsi_recon_config: { atlases: ["AAL116", "4S156Parcels"], recon_specs: ["dsi_studio_gqi", "dipy_dki"] },
      qsiprep_threads: 6,
      qsiprep_memory_gb: 24,
      qsiprep_omp_threads: 3,
      qsirecon_threads: 4,
    },
    flags: { ...NONE, run_qsiprep: true, run_qsirecon: true },
    subject_ids: ["001"],
    policy: "skip",
  },
  {
    id: "freesurfer-subregions",
    title: "FreeSurfer thalamic nuclei only (recon-all off in Settings)",
    preferences: { freesurfer_recon_all: false, freesurfer_subregions: ["thalamus"], freesurfer_threads: 3 },
    flags: { ...NONE, run_freesurfer: true },
    subject_ids: ["001"],
    policy: "skip",
  },
  {
    id: "replace",
    title: "Head model and tissue analysis for two subjects, replacing existing outputs, with saved charm options",
    preferences: { charm_options: { denoise: false, skin_facet_size: 2.5 }, charm_threads: 2 },
    flags: { ...NONE, create_m2m: true, run_tissue_analysis: true },
    subject_ids: ["001", "002"],
    policy: "replace",
  },
];

function scenario(id: string): Scenario {
  const found = SCENARIOS.find((s) => s.id === id);
  if (!found) throw new Error(`no scenario ${id}`);
  return found;
}

/** Stable key order, so a reordered object is not drift but a changed value is. */
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

function build(s: Scenario): { values: PreprocessConfig; config: PreprocessConfig; text: string } {
  const settings = settingsFor(s.preferences, CAPACITY);
  const values = { ...defaultConfig(), ...s.flags };
  const page = { ...settings, freesurfer_license: { configured: true, source: "bundled", email: null } } as SurferSettings;
  const config = toSubmitConfig(values, s.subject_ids, s.policy, page);
  const file = {
    id: s.id,
    title: s.title,
    preferences: s.preferences,
    available_threads: CAPACITY,
    settings,
    flags: Object.fromEntries(STEP_FLAGS.map((f) => [f, Boolean(values[f])])),
    subject_ids: s.subject_ids,
    policy: s.policy,
    config,
  };
  return { values, config, text: `${JSON.stringify(canonical(file), null, 2)}\n` };
}

describe("preprocess submit golden fixtures", () => {
  it("has scenarios to check, one file each", () => {
    expect(SCENARIOS.length).toBe(4);
    expect(new Set(SCENARIOS.map((s) => s.id)).size).toBe(SCENARIOS.length);
  });

  it("the committed files equal what toSubmitConfig sends (UPDATE_PRE_FIXTURES=1 rewrites them)", () => {
    const want = new Map(SCENARIOS.map((s) => [`${s.id}.json`, build(s).text]));
    if (UPDATE) {
      mkdirSync(DIR, { recursive: true });
      for (const name of readdirSync(DIR)) if (name.endsWith(".json") && !want.has(name)) unlinkSync(join(DIR, name));
      for (const [name, text] of want) writeFileSync(join(DIR, name), text);
    }
    expect(existsSync(DIR), `${DIR} exists (regenerate with UPDATE_PRE_FIXTURES=1)`).toBe(true);
    expect(readdirSync(DIR).filter((n) => n.endsWith(".json")).sort()).toEqual([...want.keys()].sort());
    for (const [name, text] of want) expect(readFileSync(join(DIR, name), "utf8"), name).toBe(text);
  });

  // The user's choices, typed out from each scenario (not read back from the builder).
  it("the page sends the saved QSI processing preferences, not the form's defaults", () => {
    const { config } = build(scenario("qsi-preferences"));
    expect(config.qsiprep_config).toMatchObject({ denoise_method: "patch2self", unringing_method: "mrdegibbs", mni_normalization: true, output_resolution: 1.5 });
    expect(config.qsiprep_config).toMatchObject({ cpus: 6, memory_gb: 24, omp_threads: 3 });
    expect(config.qsi_recon_config).toMatchObject({ atlases: ["AAL116", "4S156Parcels"], recon_specs: ["dsi_studio_gqi", "dipy_dki"], cpus: 4 });
    // No saved omp limit for QSIRecon: the page uses the effective thread count.
    expect(config.qsi_recon_config?.omp_threads).toBe(4);
  });

  it("the page sends the FreeSurfer operations chosen in Settings", () => {
    const { config } = build(scenario("freesurfer-subregions"));
    expect(config.run_freesurfer).toBe(true);
    expect(config.freesurfer_recon_all).toBe(false);
    expect(config.freesurfer_subregions).toEqual(["thalamus"]);
    expect(config.qsiprep_config).toBeNull();
  });

  it("the policy and the saved charm options reach the config", () => {
    const { config } = build(scenario("replace"));
    expect([config.skip_existing_outputs, config.replace_existing_outputs]).toEqual([false, true]);
    expect(config.charm_options).toEqual({ denoise: false, skin_facet_size: 2.5 });
    expect(config.subject_ids).toEqual(["001", "002"]);
    const skip = build(scenario("defaults")).config;
    expect([skip.skip_existing_outputs, skip.replace_existing_outputs]).toEqual([true, false]);
  });
});
