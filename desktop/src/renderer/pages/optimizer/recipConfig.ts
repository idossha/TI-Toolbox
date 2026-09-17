/**
 * Reciprocity search form state <-> the `recip` job's wire config, mirroring `exConfig.ts`.
 *
 * Reciprocity is the third method of this page: it reads the SAME leadfield an ex-search reads,
 * but it does not search. Electrode i's leadfield column at the target *is* the scalp potential a
 * unit dipole at the target would produce at electrode i, so the best pair is read off that map
 * (argmax minus argmin along the target direction) and only the top-k pairs are then combined into
 * channels and evaluated. There is therefore no electrode bucket and no current sweep here — the
 * whole form is the target, the direction, the objective and how many channels to build.
 *
 * Wire shape (frozen contract, `scratchpad/recip/BRIEF.md` §"Config contract"):
 *
 * ```json
 * { "subject_id": "ernie", "leadfield_hdf": "…hdf5",
 *   "target": {"_type": "PointTarget", "xyz": [2.2, 10.4, 17.3], "space": "subject", "radius_mm": 5.0},
 *   "direction": null, "objective": "intensity", "focality_weight": 0.0,
 *   "n_channels": 2, "current_mA": 1.0, "top_k": null, "gm_subsample": 100000, "run_name": null }
 * ```
 *
 * Two readings of that contract this module had to make, both reported with the lane:
 *
 *  1. **`project_dir` is not sent.** The brief's example spec is the file the runner is given
 *     directly; no desktop config carries `project_dir` (the server injects the project it has
 *     open — `ExConfig`, `MExConfig` and every flex config are the same), so sending one from here
 *     would be the renderer inventing a container path.
 *  2. **An ROI target travels as the existing `_type`-discriminated ROI config**
 *     (`SphericalROI` / `SubcorticalROI` / `AtlasROI`, i.e. exactly what `roiToConfig()` already
 *     builds for flex), which is what "the existing ROI specs reused unchanged" inside a `_type`
 *     union resolves to. The saved-CSV ex target is therefore not offered here: it is not one of
 *     those shapes, and it is the one ex form with no `_type` of its own.
 */
import type { components } from "../../api/schema";
import type { RoiConfig } from "../_shared/roi";

/** The generated contract (`contracts/openapi.yaml` -> `npm run gen`), not a local restatement. */
export type RecipConfigBody = components["schemas"]["RecipConfig"];
/** A point target: a coordinate, its space, and the radius of the element set around it. */
export type RecipPointTarget = components["schemas"]["PointTarget"];
/** Point, or one of the `_type`-discriminated ROI configs every optimizer already speaks. */
export type RecipTarget = RecipConfigBody["target"];

export type RecipObjective = RecipConfigBody["objective"];
export type RecipTargetMode = "point" | "roi";
/**
 * 2 or 4 — **not** 3. `RecipConfig.__post_init__` rejects an odd count
 * (`tit/opt/config.py::VALID_RECIP_CHANNELS`) because the verified envelope,
 * `tit.calc.get_TI_vectors`, is defined for an even number of channels only. The wire type is a
 * plain integer, so this is the one place the renderer holds that rule.
 */
export type RecipChannels = 2 | 4;

/**
 * Default `top_k` per channel count — a mirror of `tit/opt/config.py::DEFAULT_TOP_K`, measured on
 * ernie's EEG10-10 net: 40 pairs give 780 two-channel combinations (580 electrode-disjoint), and
 * 20 pairs give 150 disjoint four-channel montages, where 12 left only 4 because the top of the
 * map crowds onto the same few electrodes.
 *
 * The form sends `null` for "use the runner's table"; the cost line still has to state the number
 * the user will actually get, which is the only reason the table is mirrored here.
 */
export const RECIP_DEFAULT_TOP_K: Record<RecipChannels, number> = { 2: 40, 4: 20 };

/**
 * Hard ceiling on evaluated candidates (`tit/opt/config.py::MAX_RECIP_CANDIDATES`), whatever
 * `top_k` allows. Candidates are generated in reciprocity-rank order, so the ones past the cap are
 * the ones the map already ranked worst.
 */
export const MAX_RECIP_CANDIDATES = 1000;

export interface RecipFormState {
  targetMode: RecipTargetMode;
  /** Point target, kept independently editable while a coordinate is half-typed. */
  point: { x: number | undefined; y: number | undefined; z: number | undefined; radius: number | undefined };
  pointSpace: "subject" | "mni";
  /** "any" maximises the envelope amplitude; "vector" projects it on a direction. */
  directionMode: "any" | "vector";
  direction: { x: number | undefined; y: number | undefined; z: number | undefined };
  objective: RecipObjective;
  /** `focality_weight`, used only by the focality objective. */
  focalityWeight: number;
  nChannels: RecipChannels;
  currentMa: number;
  /** `null` = the default table above. */
  topK: number | null;
  gmSubsample: number;
}

export function defaultRecipFormState(): RecipFormState {
  return {
    targetMode: "point",
    point: { x: undefined, y: undefined, z: undefined, radius: 5 },
    pointSpace: "subject",
    directionMode: "any",
    direction: { x: undefined, y: undefined, z: undefined },
    objective: "intensity",
    focalityWeight: 0,
    nChannels: 2,
    currentMa: 1,
    topK: null,
    gmSubsample: 100000,
  };
}

/** The `top_k` this run will actually use — the override, or the default for its channel count. */
export function recipTopK(form: RecipFormState): number {
  return form.topK ?? RECIP_DEFAULT_TOP_K[form.nChannels];
}

/** True once the point target has all three coordinates and a radius. */
export function isRecipPointComplete(form: RecipFormState): boolean {
  const { x, y, z, radius } = form.point;
  return x !== undefined && y !== undefined && z !== undefined && radius !== undefined;
}

/**
 * Why this form cannot be sent yet — the same role `rowFormReason` plays for ex/mEx, stated as a
 * list so a test can name each rule. Empty means valid.
 *
 * The target's own completeness is NOT checked here: for an ROI target that is `isRoiComplete`,
 * which the row already asks, and for a point target it is `isRecipPointComplete`.
 */
export function recipFormErrors(form: RecipFormState): string[] {
  const errors: string[] = [];
  if (form.targetMode === "point") {
    if (!isRecipPointComplete(form)) errors.push("Enter the target's X, Y, Z and radius.");
    else if ((form.point.radius ?? 0) < 0) errors.push("The target radius cannot be negative.");
  }
  if (form.directionMode === "vector") {
    const { x, y, z } = form.direction;
    if (x === undefined || y === undefined || z === undefined) errors.push("Enter all three direction components, or choose Any direction.");
    else if (Math.hypot(x, y, z) === 0) errors.push("The direction vector cannot be zero.");
  }
  if (form.objective === "focality" && !(form.focalityWeight >= 0 && form.focalityWeight <= 1)) {
    errors.push("The focality weight must be between 0 and 1.");
  }
  // Odd channel counts are rejected by the runner, not merely out of range.
  if (form.nChannels !== 2 && form.nChannels !== 4) errors.push("Choose 2 or 4 channels.");
  if (!(form.currentMa > 0)) errors.push("The per-channel current must be greater than 0 mA.");
  if (form.topK !== null && !(Number.isInteger(form.topK) && form.topK >= form.nChannels)) {
    errors.push(`Top-k must be a whole number of at least ${form.nChannels} (one pair per channel).`);
  }
  if (!(Number.isInteger(form.gmSubsample) && form.gmSubsample > 0)) errors.push("The grey-matter subsample must be a positive whole number.");
  return errors;
}

/**
 * The wire config. `roiTarget` is the ROI mode's resolved `roiToConfig()` output; the point mode
 * ignores it. Returns `null` when the target cannot be resolved, which is what keeps a half-filled
 * row out of the plan instead of sending a target the runner would reject.
 */
export function buildRecipConfig(
  subjectId: string,
  leadfieldHdf: string,
  form: RecipFormState,
  roiTarget: RoiConfig | undefined,
  runName: string,
): RecipConfigBody | null {
  const target = recipTarget(form, roiTarget);
  if (!target) return null;
  return {
    subject_id: subjectId,
    leadfield_hdf: leadfieldHdf,
    target,
    direction:
      form.directionMode === "vector" && form.direction.x !== undefined && form.direction.y !== undefined && form.direction.z !== undefined
        ? [form.direction.x, form.direction.y, form.direction.z]
        : null,
    objective: form.objective,
    // The weight belongs to the focality objective alone; an intensity run states 0 rather than
    // carrying a number that would silently apply if the objective were switched server-side.
    focality_weight: form.objective === "focality" ? form.focalityWeight : 0,
    n_channels: form.nChannels,
    current_mA: form.currentMa,
    top_k: form.topK,
    gm_subsample: form.gmSubsample,
    run_name: runName.trim() || null,
  };
}

export function recipTarget(form: RecipFormState, roiTarget: RoiConfig | undefined): RecipTarget | null {
  if (form.targetMode === "roi") return roiTarget ?? null;
  if (!isRecipPointComplete(form)) return null;
  return {
    _type: "PointTarget",
    xyz: [form.point.x!, form.point.y!, form.point.z!],
    space: form.pointSpace,
    radius_mm: form.point.radius!,
  };
}

/**
 * The inverse of `buildRecipConfig` for the fields the form owns — the round trip a unit test
 * walks, and what a future "load this run's settings" gesture would need. An ROI target restores
 * the mode only: the ROI itself lives in the row's shared `RoiValue`, not here.
 */
export function recipFormFromConfig(config: RecipConfigBody): RecipFormState {
  const base = defaultRecipFormState();
  const target = config.target;
  const point =
    target._type === "PointTarget"
      ? { x: target.xyz[0], y: target.xyz[1], z: target.xyz[2], radius: target.radius_mm }
      : base.point;
  return {
    targetMode: target._type === "PointTarget" ? "point" : "roi",
    point,
    pointSpace: target._type === "PointTarget" ? target.space : base.pointSpace,
    directionMode: config.direction ? "vector" : "any",
    direction: config.direction
      ? { x: config.direction[0], y: config.direction[1], z: config.direction[2] }
      : base.direction,
    objective: config.objective,
    focalityWeight: config.focality_weight,
    nChannels: config.n_channels === 4 ? 4 : 2,
    currentMa: config.current_mA,
    topK: config.top_k,
    gmSubsample: config.gm_subsample,
  };
}
