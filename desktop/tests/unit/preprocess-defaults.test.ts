import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import type { ResolverOptions } from "react-hook-form";
import { createAjvResolver } from "../../src/renderer/forms/ajvResolver";
import {
  defaultsFromSchema,
  resolveDef,
  resetSchemaCache,
  type JSONSchema,
} from "../../src/renderer/forms/schema";
import {
  defaultConfig,
  describePreStageDir,
  plannedSteps,
  plannedStageIds,
  runLabelFor,
  stageLabelFor,
  toSubmitConfig,
} from "../../src/renderer/pages/preprocess/index";
import {
  defaultQsiPrepConfig,
  defaultQsiReconConfig,
} from "../../src/renderer/pages/preprocess/qsi";

// contracts/generated/config.schema.json is repo-root; desktop/tests/unit -> ../../.. reaches the repo root.
const schemaPath = join(
  __dirname,
  "..",
  "..",
  "..",
  "contracts",
  "generated", "config.schema.json",
);
const schemaDoc = JSON.parse(readFileSync(schemaPath, "utf8")) as JSONSchema;

const noopOptions = {
  shouldUseNativeValidation: false,
} as unknown as ResolverOptions<Record<string, unknown>>;

// `createAjvResolver(name)` fetches `/api/schema` via `loadSchema()` (forms/schema.ts); stub
// `fetch` to serve the same document read from disk above, and reset the module cache so each
// test run picks it up.
beforeSchemaFetchStub();
function beforeSchemaFetchStub() {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(schemaDoc), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    ),
  );
}
resetSchemaCache();

async function validate(defName: string, values: Record<string, unknown>) {
  const def = resolveDef(schemaDoc, defName);
  const resolver = createAjvResolver<Record<string, unknown>>(def);
  return resolver(values, undefined, noopOptions);
}

async function validatePreprocessConfig(values: Record<string, unknown>) {
  const resolver = createAjvResolver<Record<string, unknown>>("PreprocessConfig");
  return resolver(values, undefined, noopOptions);
}

describe("preprocess page defaults validate against contracts/generated/config.schema.json", () => {
  it("defaultConfig() (the form's Qt-parity default values) validates as a PreprocessConfig", async () => {
    const values = { ...defaultConfig(), subject_ids: ["ernie"] };
    const result = await validatePreprocessConfig(
      values as unknown as Record<string, unknown>,
    );
    expect(result.errors).toEqual({});
  });

  it("every property the schema defaults (bare dataclass defaults) also validates", async () => {
    const def = resolveDef(schemaDoc, "PreprocessConfig");
    const values = defaultsFromSchema(def);
    const result = await validatePreprocessConfig(values);
    expect(result.errors).toEqual({});
  });

  it("defaultQsiPrepConfig() validates as a QSIPrepSettings", async () => {
    const result = await validate(
      "QSIPrepSettings",
      defaultQsiPrepConfig() as unknown as Record<string, unknown>,
    );
    expect(result.errors).toEqual({});
  });

  it("defaultQsiReconConfig() validates as a QSIReconSettings", async () => {
    const result = await validate(
      "QSIReconSettings",
      defaultQsiReconConfig() as unknown as Record<string, unknown>,
    );
    expect(result.errors).toEqual({});
  });

  it("toSubmitConfig() builds a config that still validates, with QSI sub-configs nulled when their step is off", async () => {
    const submitted = toSubmitConfig(
      defaultConfig(),
      ["ernie", "101"],
      "replace",
    );
    expect(submitted.subject_ids).toEqual(["ernie", "101"]);
    expect(submitted.replace_existing_outputs).toBe(true);
    expect(submitted.skip_existing_outputs).toBe(false);
    expect(submitted.qsiprep_config).toBeNull();
    expect(submitted.qsi_recon_config).toBeNull();
    const result = await validatePreprocessConfig(
      submitted as unknown as Record<string, unknown>,
    );
    expect(result.errors).toEqual({});
  });

  it("toSubmitConfig() carries a QSIPrepSettings through when run_qsiprep is on", async () => {
    const withQsiprep = { ...defaultConfig(), run_qsiprep: true };
    const submitted = toSubmitConfig(withQsiprep, ["ernie"], "skip");
    expect(submitted.qsiprep_config).not.toBeNull();
    const result = await validatePreprocessConfig(
      submitted as unknown as Record<string, unknown>,
    );
    expect(result.errors).toEqual({});
  });

  it("stageLabelFor() prefers the server's stage/label over the directory-name guess, falling back gracefully (ra_13 finding 12)", () => {
    // Contract has no PlanJob.stage/label yet — a today's-shape job falls back to the guess.
    expect(stageLabelFor({ output_dir: "/mnt/proj/derivatives/fastsurfer/sub-ernie" })).toBe(
      describePreStageDir("/mnt/proj/derivatives/fastsurfer/sub-ernie"),
    );
    // Once a backend sends `stage`, it wins outright, even over an output_dir the guess would
    // otherwise classify differently.
    expect(stageLabelFor({ stage: "FreeSurfer recon-all", output_dir: "/mnt/proj/m2m_ernie" })).toBe(
      "FreeSurfer recon-all",
    );
    // `label` (e.g. the server's internal "sub-ernie:G2a") is the second choice, above the guess.
    expect(stageLabelFor({ label: "sub-ernie:G2a", output_dir: "/mnt/proj/m2m_ernie" })).toBe("sub-ernie:G2a");
  });

  it("runLabelFor() names the primary from the plan, not from the page", () => {
    expect(runLabelFor(0, 0)).toBe("Run preprocessing");
    expect(runLabelFor(1, 5)).toBe("Run preprocessing");
    expect(runLabelFor(2, 9)).toBe("Queue 9 jobs");
    // No plan resolved yet: fall back to the subject count rather than printing "Queue 0 jobs".
    expect(runLabelFor(3, 0)).toBe("Queue 3 jobs");
  });

  it("plannedSteps() follows run_pipeline's execution order", () => {
    const steps = plannedSteps({
      ...defaultConfig(),
      run_qsiprep: true,
      run_qsirecon: true,
      extract_dti: true,
      run_tissue_analysis: true,
    });
    expect(steps).toEqual([
      "Convert DICOM to NIfTI",
      "SimNIBS charm + subject atlas",
      "FastSurfer segmentation",
      "Tissue analysis",
      "QSIPrep",
      "QSIRecon",
      "Extract DTI tensor for SimNIBS",
    ]);
  });
});


describe("optional FreeSurfer", () => {
  it("keeps FastSurfer enabled and FreeSurfer disabled by default", () => {
    const config = defaultConfig();
    expect(config.run_fastsurfer).toBe(true);
    expect(config.run_freesurfer).toBe(false);
    expect(plannedStageIds(config)).not.toContain("G2c");
  });
  it("serializes subregion-only work and includes its plan stage", async () => {
    const config = toSubmitConfig({
      ...defaultConfig(), convert_dicom: false, create_m2m: false, run_fastsurfer: false,
      run_freesurfer: true, freesurfer_recon_all: false,
      freesurfer_subregions: ["thalamus", "hippo-amygdala"], freesurfer_threads: 2,
    }, ["ernie"], "skip");
    expect(plannedStageIds(config)).toEqual(["G2c"]);
    expect(plannedSteps(config)).toEqual(["FreeSurfer reconstruction / subregions"]);
    expect(config.freesurfer_subregions).toEqual(["thalamus", "hippo-amygdala"]);
    expect(config.freesurfer_recon_all).toBe(false);
    expect(config.freesurfer_threads).toBe(2);
    expect((await validatePreprocessConfig(config as unknown as Record<string, unknown>)).errors).toEqual({});
  });
});
