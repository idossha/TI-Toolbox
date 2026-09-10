/**
 * Ex / mEx form state → `ExConfig` / `MExConfig` wire shapes, plus the bucket vocabulary and the
 * ROI→target expansion. Merged from `optimizer-ex/{ExForm,MExForm,lib}.tsx` — see
 * `pages/optimizer/PARITY.md` for the control-by-control map of where each field went.
 *
 * The one behavioural change from the predecessors: the target's ROI now comes from the ONE
 * shared `RoiValue` (`pages/_shared/roi`), so an atlas target carries the atlas's real
 * `atlas_path` (resolved through the catalog) instead of the atlas *id* the old local picker put
 * in that field.
 */
import type { RoiValue, AtlasLookup } from "../_shared/roi";
import type { ExConfigBody, MExConfigBody } from "./api";

export const EX_BUCKET_KEYS = ["e1_plus", "e1_minus", "e2_plus", "e2_minus"] as const;
export const MEX_BUCKET_KEYS = [
  "e1_plus",
  "e1_minus",
  "e2_plus",
  "e2_minus",
  "e3_plus",
  "e3_minus",
  "e4_plus",
  "e4_minus",
] as const;

export const BUCKET_LABELS: Record<string, string> = {
  e1_plus: "E1+",
  e1_minus: "E1-",
  e2_plus: "E2+",
  e2_minus: "E2-",
  e3_plus: "E3+",
  e3_minus: "E3-",
  e4_plus: "E4+",
  e4_minus: "E4-",
};

export const BUCKET_TOOLTIPS: Record<string, string> = {
  e1_plus: "Electrodes for channel 1 positive pole (anodes)",
  e1_minus: "Electrodes for channel 1 negative pole (cathodes)",
  e2_plus: "Electrodes for channel 2 positive pole (anodes)",
  e2_minus: "Electrodes for channel 2 negative pole (cathodes)",
  e3_plus: "Electrodes for pair 3 positive pole (anodes)",
  e3_minus: "Electrodes for pair 3 negative pole (cathodes)",
  e4_plus: "Electrodes for pair 4 positive pole (anodes)",
  e4_minus: "Electrodes for pair 4 negative pole (cathodes)",
};

export const MTI_SYMMETRY_HELP =
  "When checked, only left/right mirrored electrode-pair candidates are evaluated (mirroring " +
  "derived from the selected leadfield's EEG net), instead of the full combination of all eight " +
  "buckets.\n\n" +
  "Within each pair: each pair's own +/- electrodes mirror across the midline.\n" +
  "Cross pairs: additionally requires pair 1<->3 and pair 2<->4 to mirror each other.";

export interface ExFormState {
  electrodeMode: "bucketed" | "all";
  buckets: Record<string, string[]>;
  pool: string[];
  totalCurrent: number;
  currentStep: number;
  channelLimit: number | null;
}

export interface MExFormState {
  buckets: Record<string, string[]>;
  currentMa: number;
  symmetricBucket: boolean;
  symmetryPairing: "within_pairs" | "cross_pairs";
}

export function defaultExFormState(): ExFormState {
  return {
    electrodeMode: "bucketed",
    buckets: { e1_plus: [], e1_minus: [], e2_plus: [], e2_minus: [] },
    pool: [],
    totalCurrent: 2.0,
    currentStep: 0.2,
    channelLimit: 1.6,
  };
}

export function defaultMExFormState(): MExFormState {
  return {
    buckets: Object.fromEntries(MEX_BUCKET_KEYS.map((k) => [k, []])),
    currentMa: 2.0,
    symmetricBucket: false,
    symmetryPairing: "within_pairs",
  };
}

/** One resolved ex/mEx run target: what `roi_name` / `roi_names` / `roi_atlas` will carry. */
export interface ExTarget {
  /** `ExConfig.roi_name` — also the run's output label. */
  roiName: string;
  /** `ExConfig.roi_names` — the saved CSV names unioned into this target, or `[]` for atlas-only. */
  roiNames: string[] | null;
  /** `ExConfig.roi_atlas` — volumetric regions unioned into the target, or `null`. */
  roiAtlas: { atlas_path: string; label: number | null; atlas_space?: "subject" | "mni" }[] | null;
  radius: number;
  space: "subject" | "mni";
}

/**
 * Expand the shared ROI value into the ex/mEx target list.
 *
 * - `saved` + combine → one target named by joining the ROI names with "+".
 * - `saved` without combine → one target per selected ROI (one run each).
 * - `subcortical` → a single atlas-only target (`roi_names: []`, the schema's "no spherical
 *   centres" signal), named for the atlas and its region count.
 * - anything else, or nothing selected → no targets, which is what disables Run.
 *
 * `allowCombine === false` (mEx) forces the per-ROI expansion regardless of the flag, matching the
 * mTI run path, which has no combined mode.
 */
export function exTargets(
  roi: RoiValue,
  atlasLookup: (atlas: string) => AtlasLookup | undefined,
  allowCombine = true,
): ExTarget[] {
  if (roi.mode === "mask") {
    const path = roi.path.trim();
    if (!/\.nii(\.gz)?$/i.test(path)) return [];
    return [{ roiName: path.split("/").pop()!.replace(/\.nii(\.gz)?$/i, ""), roiNames: [],
      roiAtlas: [{ atlas_path: path, label: null, atlas_space: roi.space }], radius: 3, space: roi.space }];
  }
  if (roi.mode === "saved") {
    if (roi.selected.length === 0) return [];
    if (roi.combine && allowCombine) {
      return [{ roiName: roi.selected.join("+"), roiNames: [...roi.selected], roiAtlas: null, radius: roi.radius, space: roi.space }];
    }
    return roi.selected.map((name) => ({ roiName: name, roiNames: null, roiAtlas: null, radius: roi.radius, space: roi.space }));
  }
  if (roi.mode === "subcortical") {
    const atlas = roi.atlas ? atlasLookup(roi.atlas) : undefined;
    if (!atlas || roi.regions.length === 0) return [];
    const n = roi.regions.length;
    return [
      {
        roiName: `${roi.atlas}_${n}region${n === 1 ? "" : "s"}`,
        roiNames: [],
        roiAtlas: roi.regions.map((r) => ({ atlas_path: atlas.path, label: r.id })),
        radius: 3.0,
        space: roi.atlasSpace,
      },
    ];
  }
  return [];
}

export function buildExConfig(
  subjectId: string,
  leadfieldHdf: string,
  form: ExFormState,
  target: ExTarget,
  runName: string,
): ExConfigBody {
  const electrodes: ExConfigBody["electrodes"] =
    form.electrodeMode === "bucketed"
      ? {
          e1_plus: form.buckets.e1_plus ?? [],
          e1_minus: form.buckets.e1_minus ?? [],
          e2_plus: form.buckets.e2_plus ?? [],
          e2_minus: form.buckets.e2_minus ?? [],
          _type: "BucketElectrodes",
        }
      : { electrodes: form.pool, _type: "PoolElectrodes" };
  return {
    subject_id: subjectId,
    leadfield_hdf: leadfieldHdf,
    roi_name: target.roiName,
    electrodes,
    total_current: form.totalCurrent,
    current_step: form.currentStep,
    channel_limit: form.channelLimit,
    roi_radius: target.radius,
    roi_names: target.roiNames,
    roi_atlas: target.roiAtlas?.map((roi) => ({ ...roi, atlas_space: roi.atlas_space ?? "subject" })) ?? null,
    roi_coordinate_space: target.space,
    run_name: runName.trim() || null,
    n_jobs: -1,
    // Ex-search symmetric buckets (added on main in v2.5.0) have no control on
    // the Optimizer page yet; these are the server-side defaults. See
    // docs/dev/RELEASE.md §B.
    symmetric_bucket: false,
    symmetry_eeg_csv: null,
    symmetry_pairing: "within_pairs",
  };
}

export function buildMExConfig(
  subjectId: string,
  leadfieldHdf: string,
  form: MExFormState,
  target: ExTarget,
  runName: string,
): MExConfigBody {
  return {
    subject_id: subjectId,
    leadfield_hdf: leadfieldHdf,
    roi_name: target.roiName,
    electrodes: {
      e1_plus: form.buckets.e1_plus ?? [],
      e1_minus: form.buckets.e1_minus ?? [],
      e2_plus: form.buckets.e2_plus ?? [],
      e2_minus: form.buckets.e2_minus ?? [],
      e3_plus: form.buckets.e3_plus ?? [],
      e3_minus: form.buckets.e3_minus ?? [],
      e4_plus: form.buckets.e4_plus ?? [],
      e4_minus: form.buckets.e4_minus ?? [],
      _type: "BucketElectrodes",
    },
    current_mA: form.currentMa,
    roi_radius: target.radius,
    roi_names: target.roiNames,
    roi_atlas: target.roiAtlas?.map((roi) => ({ ...roi, atlas_space: roi.atlas_space ?? "subject" })) ?? null,
    roi_coordinate_space: target.space,
    run_name: runName.trim() || null,
    symmetric_bucket: form.symmetricBucket,
    symmetry_eeg_csv: null,
    symmetry_pairing: form.symmetryPairing,
    n_jobs: -1,
  };
}

export function formatBytes(n: number): string {
  if (n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log2(n) / 10));
  return `${(n / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/** `exTargets` for a saved-ROI selection, without constructing a `RoiValue` — the shape unit
 *  tests and callers that already have names want. */
export function savedTargets(names: string[], combine: boolean, radius = 3.0, space: "subject" | "mni" = "subject"): ExTarget[] {
  return exTargets({ mode: "saved", selected: names, combine, radius, space }, () => undefined, true);
}

/** `exTargets` for one subcortical atlas selection, given the atlas's resolved path. */
export function atlasTarget(atlasId: string, atlasPath: string, labels: number[], space: "subject" | "mni" = "subject"): ExTarget {
  const value: RoiValue = {
    mode: "subcortical",
    atlasSpace: space,
    atlas: atlasId,
    regions: labels.map((id) => ({ id, name: String(id) })),
    tissues: "GM",
  };
  return exTargets(value, () => ({ path: atlasPath }), true)[0] as ExTarget;
}
