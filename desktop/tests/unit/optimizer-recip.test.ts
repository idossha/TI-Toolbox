/**
 * The reciprocity form <-> wire mapping (`pages/optimizer/recipConfig.ts`).
 *
 * The contract this checks is the frozen one in the lane brief, field for field — the runner reads
 * `target._type`, `direction`, `objective`, `focality_weight`, `n_channels`, `current_mA`, `top_k`
 * and `gm_subsample`, and a renamed field here is a run that silently does something else. It is
 * NOT validated against `contracts/generated/config.schema.json` the way `optimizer-ex.test.ts`
 * validates `ExConfig`: `RecipConfig` is lane A's and is not in that schema yet. Swap the shape
 * assertions below for a schema validation once `npm run gen` has run.
 */
import { describe, expect, it } from "vitest";
import {
  buildRecipConfig,
  defaultRecipFormState,
  recipFormErrors,
  recipFormFromConfig,
  recipTopK,
  RECIP_DEFAULT_TOP_K,
  type RecipFormState,
} from "../../src/renderer/pages/optimizer/recipConfig";
import { recipCost } from "../../src/renderer/pages/optimizer/cost";
import type { RoiConfig } from "../../src/renderer/pages/_shared/roi";

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
  it("builds the brief's example spec from the point form", () => {
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
  });

  it("sends an ROI target as the ROI config itself, unchanged", () => {
    const config = buildRecipConfig("ernie", HDF, pointForm({ targetMode: "roi" }), thalamus, "thal");
    expect(config?.target).toBe(thalamus);
    expect(config?.run_name).toBe("thal");
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
      nChannels: 3,
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
});

describe("recip form validation", () => {
  it("accepts the default point form once the coordinate is filled in", () => {
    expect(recipFormErrors(pointForm())).toEqual([]);
  });

  it("names each rule the contract states", () => {
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
    expect(recipFormErrors(pointForm({ nChannels: 3, topK: 2 }))).toEqual([
      "Top-k must be a whole number of at least 3 (one pair per channel).",
    ]);
    expect(recipFormErrors(pointForm({ nChannels: 3, topK: 3 }))).toEqual([]);
    expect(recipFormErrors(pointForm({ gmSubsample: 0 }))).toEqual(["The grey-matter subsample must be a positive whole number."]);
  });

  it("ignores the focality weight while the objective is intensity", () => {
    expect(recipFormErrors(pointForm({ objective: "intensity", focalityWeight: 5 }))).toEqual([]);
  });
});

describe("the recip cost line", () => {
  it("follows the runner's default top-k table per channel count", () => {
    expect(RECIP_DEFAULT_TOP_K).toEqual({ 2: 40, 3: 16, 4: 12 });
    expect(recipTopK(pointForm())).toBe(40);
    expect(recipTopK(pointForm({ nChannels: 4 }))).toBe(12);
    expect(recipTopK(pointForm({ nChannels: 4, topK: 20 }))).toBe(20);
  });

  it("states the candidate ceiling, C(top_k, channels)", () => {
    // C(40,2) = 780, C(16,3) = 560, C(12,4) = 495 — computed here, not read off the implementation.
    expect(recipCost(pointForm()).combinations).toBe(780);
    expect(recipCost(pointForm({ nChannels: 3 })).combinations).toBe(560);
    expect(recipCost(pointForm({ nChannels: 4 })).combinations).toBe(495);
    expect(recipCost(pointForm()).line).toBe("top 40 pairs · 2 channels · at most 780 candidates");
  });
});
