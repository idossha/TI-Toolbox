import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import Ajv2020 from "ajv/dist/2020";
import type { ErrorObject } from "ajv";
import type { JSONSchema } from "../../src/renderer/forms/schema";
import {
  atlasTarget,
  buildExConfig,
  buildMExConfig,
  defaultExFormState,
  defaultMExFormState,
  savedTargets,
} from "../../src/renderer/pages/optimizer/exConfig";
import type { ExConfigBody, LeadfieldConfigBody, MExConfigBody } from "../../src/renderer/pages/optimizer/api";

// contracts/generated/config.schema.json is repo-root; desktop/tests/unit -> ../../.. reaches the repo root.
const schemaPath = join(__dirname, "..", "..", "..", "contracts", "generated", "config.schema.json");
const schemaDoc = JSON.parse(readFileSync(schemaPath, "utf8")) as JSONSchema;

/**
 * `desktop/src/renderer/forms/ajvResolver.ts` (`createAjvResolver`) and `forms/schema.ts`
 * (`resolveDef` + `loadConfigSchema`) compile ONE isolated `$defs/<Name>` object with Ajv,
 * stripped of the sibling `$defs` its own `$ref`s point to. Every config with a `oneOf`/`$ref`
 * to another `$defs` entry — `ExConfig.electrodes` -> `$defs/ExConfigBucketElectrodes`,
 * `PreprocessConfig` -> `$defs/QSIPrepConfig`, etc. — then fails to compile at all
 * ("can't resolve reference #/$defs/X from id #"), not just fails validation. Reproduced here
 * AND independently in `tests/unit/preprocess-defaults.test.ts` (a different lane's page, same
 * `createAjvResolver` call shape), so this is a `forms/` infra bug, not a page-level misuse —
 * reported to the orchestrator/F2 rather than fixed here (`forms/**` is not this lane's file).
 *
 * This test instead adds the FULL schema document to Ajv once (giving it an id) and resolves one
 * named `$def` from it via `getSchema`, which keeps sibling `$ref`s resolvable — the correct
 * story `createAjvResolver` should tell once that bug is fixed.
 */
const ajv = new Ajv2020({ allErrors: true, strict: false, useDefaults: true });
ajv.addSchema(schemaDoc, "schema.json");

function validate(defName: string, values: Record<string, unknown>): ErrorObject[] {
  const fn = ajv.getSchema(`schema.json#/$defs/${defName}`);
  if (!fn) throw new Error(`No $defs/${defName} in contracts/generated/config.schema.json`);
  fn(values);
  return (fn.errors ?? []) as ErrorObject[];
}

describe("Optimizer Ex/mEx defaults validate against contracts/generated/config.schema.json", () => {
  it("ExForm's default (bucketed, single ROI) validates as an ExConfig", () => {
    const target = savedTargets(["Thalamus_target"], false)[0]!;
    const form = { ...defaultExFormState(), buckets: { e1_plus: ["F7"], e1_minus: ["P7"], e2_plus: ["F3"], e2_minus: ["P3"] } };
    const config = buildExConfig("ernie", "/mnt/example/leadfields/GSN-HydroCel-185/leadfield.hdf5", form, target, "");
    expect(validate("ExConfig", config as unknown as Record<string, unknown>)).toEqual([]);
  });

  it("ExForm's default (all-combinations pool) validates as an ExConfig", () => {
    const target = savedTargets(["Thalamus_target"], false)[0]!;
    const form = { ...defaultExFormState(), electrodeMode: "all" as const, pool: ["F7", "P7", "F3", "P3"] };
    const config = buildExConfig("ernie", "/mnt/example/leadfields/GSN-HydroCel-185/leadfield.hdf5", form, target, "");
    expect(validate("ExConfig", config as unknown as Record<string, unknown>)).toEqual([]);
  });

  it("combined ROIs produce one target whose roi_names unions the selected ROIs", () => {
    expect(savedTargets(["A", "B"], true)).toEqual([
      { roiName: "A+B", roiNames: ["A", "B"], roiAtlas: null, radius: 3.0, space: "subject" },
    ]);
  });

  it("uncombined ROIs produce one target per ROI — one run each", () => {
    expect(savedTargets(["A", "B"], false).map((t) => t.roiName)).toEqual(["A", "B"]);
  });

  it("an atlas-only target has roi_names: [] and validates with a roi_atlas entry", () => {
    // The merged picker resolves the atlas's real path, where the old local picker sent its id.
    const target = atlasTarget("CIT168", "/mnt/example/atlases/CIT168.nii.gz", [10]);
    const form = {
      ...defaultExFormState(),
      buckets: { e1_plus: ["F7"], e1_minus: ["P7"], e2_plus: ["F3"], e2_minus: ["P3"] },
    };
    const config: ExConfigBody = buildExConfig("ernie", "/mnt/example/leadfields/GSN-HydroCel-185/leadfield.hdf5", form, target, "");
    expect(config.roi_names).toEqual([]);
    expect(config.roi_atlas).toEqual([{ atlas_path: "/mnt/example/atlases/CIT168.nii.gz", label: 10, atlas_space: "subject" }]);
    expect(validate("ExConfig", config as unknown as Record<string, unknown>)).toEqual([]);
  });

  it("MExForm's default (eight buckets) validates as an MExConfig", () => {
    const target = savedTargets(["Thalamus_target"], false)[0]!;
    const form = {
      ...defaultMExFormState(),
      buckets: { e1_plus: ["E24"], e1_minus: ["E124"], e2_plus: ["E67"], e2_minus: ["E77"], e3_plus: ["E1"], e3_minus: ["E2"], e4_plus: ["E3"], e4_minus: ["E4"] },
    };
    const config = buildMExConfig("ernie", "/mnt/example/leadfields/GSN-HydroCel-185/leadfield.hdf5", form, target, "");
    expect(validate("MExConfig", config as unknown as Record<string, unknown>)).toEqual([]);
  });

  it("MExForm with shared-carrier wiring still validates", () => {
    const target = savedTargets(["Thalamus_target"], false)[0]!;
    const form = {
      ...defaultMExFormState(),
      symmetricBucket: true,
      symmetryPairing: "cross_pairs" as const,
      buckets: { e1_plus: ["E24"], e1_minus: ["E124"], e2_plus: ["E67"], e2_minus: ["E77"], e3_plus: ["E1"], e3_minus: ["E2"], e4_plus: ["E3"], e4_minus: ["E4"] },
    };
    const config: MExConfigBody = buildMExConfig("ernie", "/mnt/example/leadfields/GSN-HydroCel-185/leadfield.hdf5", form, target, "");
    expect(config.symmetry_pairing).toBe("cross_pairs");
    expect(validate("MExConfig", config as unknown as Record<string, unknown>)).toEqual([]);
  });

  it("a LeadfieldConfig built for the 'Generate leadfield' action validates", () => {
    const config: LeadfieldConfigBody = { subject_id: "ernie", eeg_net: "GSN-HydroCel-185", tissues: [1, 2], interpolation: null, overwrite: false };
    expect(validate("LeadfieldConfig", config as unknown as Record<string, unknown>)).toEqual([]);
  });
});


describe("subcortical target coordinate space", () => {
  it.each(["subject", "mni"] as const)("retains %s space on every Ex/mEx atlas entry", (space) => {
    const target = atlasTarget("CIT168", "/atlases/CIT168.nii.gz", [10, 11], space);
    const expected = [10, 11].map((label) => ({ atlas_path: "/atlases/CIT168.nii.gz", label, atlas_space: space }));
    const ex = buildExConfig("ernie", "/leadfield.hdf5", defaultExFormState(), target, "");
    const mex = buildMExConfig("ernie", "/leadfield.hdf5", defaultMExFormState(), target, "");
    expect(ex.roi_atlas).toEqual(expected);
    expect(mex.roi_atlas).toEqual(expected);
    expect(ex.roi_coordinate_space).toBe(space);
    expect(mex.roi_coordinate_space).toBe(space);
  });
});
