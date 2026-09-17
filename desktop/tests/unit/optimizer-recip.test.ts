/**
 * The reciprocity form <-> wire mapping (`pages/optimizer/recipConfig.ts`).
 *
 * Every built config is validated against `contracts/generated/config.schema.json`'s `RecipConfig`
 * — the same Ajv setup, and for the same reason, as `optimizer-ex.test.ts` (see its header for why
 * the whole schema document is added once and one `$def` resolved from it, rather than compiling
 * the isolated `$def` through `forms/ajvResolver.ts`). A renamed or mistyped field is then a red
 * test rather than a run that quietly does something else.
 *
 * The rules the schema cannot state are asserted directly: `n_channels` is a plain integer on the
 * wire, but `RecipConfig.__post_init__` accepts 2 or 4 only, and `top_k`/`focality_weight` have
 * bounds the runner enforces.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import Ajv2020 from "ajv/dist/2020";
import type { ErrorObject } from "ajv";
import type { JSONSchema } from "../../src/renderer/forms/schema";
import {
  buildRecipConfig,
  defaultRecipFormState,
  recipFormErrors,
  recipFormFromConfig,
  recipTopK,
  MAX_RECIP_CANDIDATES,
  RECIP_DEFAULT_TOP_K,
  type RecipFormState,
} from "../../src/renderer/pages/optimizer/recipConfig";
import { recipCost } from "../../src/renderer/pages/optimizer/cost";
import type { RoiConfig } from "../../src/renderer/pages/_shared/roi";

const schemaPath = join(__dirname, "..", "..", "..", "contracts", "generated", "config.schema.json");
const schemaDoc = JSON.parse(readFileSync(schemaPath, "utf8")) as JSONSchema;
const ajv = new Ajv2020({ allErrors: true, strict: false, useDefaults: true });
ajv.addSchema(schemaDoc, "schema.json");

function validate(defName: string, values: Record<string, unknown>): ErrorObject[] {
  const fn = ajv.getSchema(`schema.json#/$defs/${defName}`);
  if (!fn) throw new Error(`No $defs/${defName} in contracts/generated/config.schema.json`);
  fn(values);
  return (fn.errors ?? []) as ErrorObject[];
}

const HDF = "/mnt/000/derivatives/SimNIBS/sub-ernie/leadfields/ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5";

function pointForm(patch: Partial<RecipFormState> = {}): RecipFormState {
  return { ...defaultRecipFormState(), point: { x: 2.2, y: 10.4, z: 17.3, radius: 5 }, ...patch };
}

const thalamus: RoiConfig = {
  _type: "SubcorticalROI",
  atlas_path: ["/mnt/000/derivatives/SimNIBS/sub-ernie/m2m_ernie/labeling.nii.gz"],
  label: [10, 49],
  tissues: "GM",
  atlas_space: "subject",
};

describe("the recip wire config", () => {
  it("builds the contract's example spec from the point form, and it validates", () => {
    const config = buildRecipConfig("ernie", HDF, pointForm(), undefined, "");
    expect(config).toEqual({
      subject_id: "ernie",
      leadfield_hdf: HDF,
      target: { _type: "PointTarget", xyz: [2.2, 10.4, 17.3], space: "subject", radius_mm: 5 },
      direction: null,
      objective: "intensity",
      focality_weight: 0,
      n_channels: 2,
      current_mA: 1,
      top_k: null,
      gm_subsample: 100000,
      run_name: null,
    });
    expect(validate("RecipConfig", config as unknown as Record<string, unknown>)).toEqual([]);
  });

  it("sends an ROI target as the ROI config itself, unchanged, and it validates", () => {
    const config = buildRecipConfig("ernie", HDF, pointForm({ targetMode: "roi" }), thalamus, "thal");
    expect(config?.target).toBe(thalamus);
    expect(config?.run_name).toBe("thal");
    expect(validate("RecipConfig", config as unknown as Record<string, unknown>)).toEqual([]);
  });

  it("validates the four-channel, directional, focality shape too", () => {
    const config = buildRecipConfig(
      "ernie",
      HDF,
      pointForm({ nChannels: 4, directionMode: "vector", direction: { x: 0, y: 0, z: 1 }, objective: "focality", focalityWeight: 0.4, topK: 24 }),
      undefined,
      "run",
    );
    expect(validate("RecipConfig", config as unknown as Record<string, unknown>)).toEqual([]);
  });

  it("refuses to build a target it cannot resolve", () => {
    expect(buildRecipConfig("ernie", HDF, pointForm({ targetMode: "roi" }), undefined, "")).toBeNull();
    expect(buildRecipConfig("ernie", HDF, { ...pointForm(), point: { x: 1, y: 2, z: undefined, radius: 5 } }, undefined, "")).toBeNull();
  });

  it("sends a direction only when one was entered, and the weight only for focality", () => {
    const any = buildRecipConfig("ernie", HDF, pointForm({ directionMode: "any", direction: { x: 1, y: 0, z: 0 } }), undefined, "");
    expect(any?.direction).toBeNull();
    const directed = buildRecipConfig("ernie", HDF, pointForm({ directionMode: "vector", direction: { x: 0, y: 0, z: 1 } }), undefined, "");
    expect(directed?.direction).toEqual([0, 0, 1]);
    // A weight typed under Focality and then switched back to Intensity must not travel.
    const intensity = buildRecipConfig("ernie", HDF, pointForm({ objective: "intensity", focalityWeight: 0.6 }), undefined, "");
    expect(intensity?.focality_weight).toBe(0);
    const focality = buildRecipConfig("ernie", HDF, pointForm({ objective: "focality", focalityWeight: 0.6 }), undefined, "");
    expect(focality?.focality_weight).toBe(0.6);
  });

  it("round-trips every field the form owns", () => {
    const form = pointForm({
      pointSpace: "mni",
      directionMode: "vector",
      direction: { x: 0, y: 1, z: -1 },
      objective: "focality",
      focalityWeight: 0.35,
      nChannels: 4,
      currentMa: 1.5,
      topK: 20,
      gmSubsample: 50000,
    });
    const config = buildRecipConfig("ernie", HDF, form, undefined, "run")!;
    expect(recipFormFromConfig(config)).toEqual(form);
  });

  it("round-trips an ROI target back to the ROI mode", () => {
    const form = pointForm({ targetMode: "roi" });
    const config = buildRecipConfig("ernie", HDF, form, thalamus, "")!;
    expect(recipFormFromConfig(config).targetMode).toBe("roi");
  });

  it("reads an out-of-vocabulary channel count back as two", () => {
    // `n_channels` is a plain integer on the wire; the runner rejects 3, and the form cannot hold
    // it, so a hand-written spec carrying one restores as the default rather than a dead segment.
    const config = { ...buildRecipConfig("ernie", HDF, pointForm(), undefined, "")!, n_channels: 3 };
    expect(recipFormFromConfig(config).nChannels).toBe(2);
  });
});

describe("recip form validation", () => {
  it("accepts the default point form once the coordinate is filled in", () => {
    expect(recipFormErrors(pointForm())).toEqual([]);
  });

  it("names each rule the runner enforces", () => {
    expect(recipFormErrors(pointForm({ point: { x: undefined, y: 1, z: 1, radius: 5 } }))).toEqual([
      "Enter the target's X, Y, Z and radius.",
    ]);
    expect(recipFormErrors(pointForm({ directionMode: "vector", direction: { x: 0, y: 0, z: 0 } }))).toEqual([
      "The direction vector cannot be zero.",
    ]);
    expect(recipFormErrors(pointForm({ directionMode: "vector", direction: { x: 1, y: 1, z: undefined } }))).toEqual([
      "Enter all three direction components, or choose Any direction.",
    ]);
    expect(recipFormErrors(pointForm({ objective: "focality", focalityWeight: 1.5 }))).toEqual([
      "The focality weight must be between 0 and 1.",
    ]);
    expect(recipFormErrors(pointForm({ currentMa: 0 }))).toEqual(["The per-channel current must be greater than 0 mA."]);
    // top_k must leave at least one pair per channel.
    expect(recipFormErrors(pointForm({ nChannels: 4, topK: 3 }))).toEqual([
      "Top-k must be a whole number of at least 4 (one pair per channel).",
    ]);
    expect(recipFormErrors(pointForm({ nChannels: 4, topK: 4 }))).toEqual([]);
    expect(recipFormErrors(pointForm({ gmSubsample: 0 }))).toEqual(["The grey-matter subsample must be a positive whole number."]);
  });

  it("rejects an odd channel count, which has no verified envelope", () => {
    // Cast: the form type cannot express 3, which is the point — this guards a config arriving
    // from outside the form (a restored session, a future import).
    expect(recipFormErrors({ ...pointForm(), nChannels: 3 as unknown as 2 })).toEqual(["Choose 2 or 4 channels."]);
  });

  it("ignores the focality weight while the objective is intensity", () => {
    expect(recipFormErrors(pointForm({ objective: "intensity", focalityWeight: 5 }))).toEqual([]);
  });
});

describe("the recip cost line", () => {
  it("mirrors tit/opt/config.py's default top-k table", () => {
    expect(RECIP_DEFAULT_TOP_K).toEqual({ 2: 40, 4: 20 });
    expect(recipTopK(pointForm())).toBe(40);
    expect(recipTopK(pointForm({ nChannels: 4 }))).toBe(20);
    expect(recipTopK(pointForm({ nChannels: 4, topK: 30 }))).toBe(30);
  });

  it("states the candidate ceiling, C(top_k, channels), capped at the runner's limit", () => {
    // C(40,2) = 780 — computed here, not read off the implementation.
    expect(recipCost(pointForm()).combinations).toBe(780);
    expect(recipCost(pointForm()).line).toBe("top 40 pairs · 2 channels · at most 780 candidates");
    // C(20,4) = 4 845, above MAX_RECIP_CANDIDATES, so the line states the cap the runner applies.
    expect(recipCost(pointForm({ nChannels: 4 })).combinations).toBe(MAX_RECIP_CANDIDATES);
    expect(recipCost(pointForm({ nChannels: 4 })).line).toBe("top 20 pairs · 4 channels · at most 1,000 candidates");
    // C(8,4) = 70 stays under the cap.
    expect(recipCost(pointForm({ nChannels: 4, topK: 8 })).combinations).toBe(70);
  });
});
