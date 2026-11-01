import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import Ajv2020 from "ajv/dist/2020";
import type { ErrorObject } from "ajv";
import type { JSONSchema } from "../../src/renderer/forms/schema";
import {
  buildExConfig,
  buildMExConfig,
  defaultExFormState,
  defaultMExFormState,
  exTargets,
  type ExTarget,
} from "../../src/renderer/pages/optimizer/exConfig";
import type { ExConfigBody, LeadfieldConfigBody, MExConfigBody } from "../../src/renderer/pages/optimizer/api";
import { leadfieldJobConfig } from "../../src/renderer/pages/optimizer/api";

/** `exTargets` for a saved-ROI selection, the page's own expansion with the names given directly. */
function savedTargets(names: string[], combine: boolean, radius = 3.0, space: "subject" | "mni" = "subject"): ExTarget[] {
  return exTargets({ mode: "saved", selected: names, combine, radius, space }, () => undefined, true);
}

/** `exTargets` for one subcortical atlas selection, given the atlas's resolved path. */
function atlasTarget(atlasId: string, atlasPath: string, labels: number[], space: "subject" | "mni" = "subject"): ExTarget {
  const regions = labels.map((id) => ({ id, name: String(id) }));
  const value = { mode: "subcortical" as const, space, atlas: atlasId, regions, tissues: "GM" as const };
  return exTargets(value, () => ({ path: atlasPath }), true)[0] as ExTarget;
}

// contracts/generated/config.schema.json is repo-root; desktop/tests/unit -> ../../.. reaches the repo root.
const schemaPath = join(__dirname, "..", "..", "..", "contracts", "generated", "config.schema.json");
const schemaDoc = JSON.parse(readFileSync(schemaPath, "utf8")) as JSONSchema;

/**
 * Validates against the same whole-document Ajv scheme `createAjvResolver` uses
 * (`desktop/src/renderer/forms/ajvResolver.ts`): the FULL schema document is added to Ajv once and
 * one named `$def` is resolved from it via `getSchema`, so the sibling `$ref`s a config carries
 * (`ExConfig.electrodes` -> `$defs/ExConfigBucketElectrodes`, ...) stay resolvable.
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

  it("a LeadfieldConfig built for the 'Generate leadfield' step validates and carries the chosen electrode", () => {
    const electrode = { electrode_shape: "rect" as const, electrode_dimensions: [12, 6], gel_thickness: 2.5, rubber_thickness: 2 };
    const config: LeadfieldConfigBody = leadfieldJobConfig("ernie", "GSN-HydroCel-185", electrode);
    expect(validate("LeadfieldConfig", config as unknown as Record<string, unknown>)).toEqual([]);
    // `overwrite` is "compute this electrode"; replacing a file on disk still takes the 409 answer.
    expect(config).toMatchObject({ subject_id: "ernie", eeg_net: "GSN-HydroCel-185", overwrite: true, ...electrode });
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
