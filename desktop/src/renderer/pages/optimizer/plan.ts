/**
 * From a jobs-table row to the wire — the pure half of the Optimizer's Run button (lane OJ).
 *
 * Kept out of `index.tsx` so it can be unit-tested without a React tree, and out of `rows.ts` so
 * the row model stays free of the config builders. The invariant this module exists to hold is the
 * U16 one, now made per row: **every per-subject path in an optimizer config points into that
 * subject's own derivatives** — `leadfield_hdf` at `sub-<id>/leadfields/`, an atlas target's
 * `atlas_path` at `derivatives/freesurfer/sub-<id>/`. Resolving either once and reusing it across
 * a table produces jobs that silently optimise every subject against another subject's anatomy,
 * which is why both facts arrive through `resolve` rather than being closed over.
 */
import { roiToConfig, type AtlasLookup, type RoiValue } from "../_shared/roi";
import type { GroupKind } from "../_shared/run";
import type { FlexConfigWire } from "./api";
import { buildFlexConfig } from "./flexConfig";
import { buildExConfig, buildMExConfig, exTargets, EX_BUCKET_KEYS, MEX_BUCKET_KEYS, type ExTarget } from "./exConfig";
import { OPT_METHOD_LABEL, rowJobKind, rowStage, type OptimizerRow } from "./rows";

/** One planned/submitted job: which row it came from, its kind, its subject and its wire config. */
export interface OptimizerJobSpec {
  rowId: string;
  kind: GroupKind;
  /** The plan grid's column — the family, not the individual run. */
  stage: "flex" | "ex" | "mex";
  subject: string;
  label: string;
  config: unknown;
}

/**
 * Expand one row into the jobs it will queue: one for a Flex row, one per resolved target for an
 * Ex/mEx row (an uncombined two-ROI selection is two runs, which is what 2.5.0 did too).
 */
export function jobsForRow(
  row: OptimizerRow,
  resolve: {
    atlas: (subject: string, roi: RoiValue) => (atlas: string) => AtlasLookup | undefined,
    leadfield: (subject: string, net: string | null) => string | null,
  },
): OptimizerJobSpec[] {
  if (!row.subjectId) return [];
  if (row.method === "flex") {
    const form = row.flex;
    const roi = roiToConfig(row.roi, resolve.atlas(row.subjectId, row.roi));
    if (!roi) return [];
    const focality = form.goal === "focality" || form.goal === "focality_tf";
    const nonRoi =
      focality && form.nonRoiMethod === "specific"
        ? roiToConfig(row.nonRoi, resolve.atlas(row.subjectId, row.nonRoi))
        : undefined;
    if (focality && form.nonRoiMethod === "specific" && !nonRoi) return [];
    const config = buildFlexConfig(row.subjectId, form, roi, nonRoi) as FlexConfigWire;
    // The run name is the flex output folder; the wire field is `output_folder`.
    if (row.runName.trim()) config.output_folder = row.runName.trim();
    // The KIND is derived from the form's focality mode (`jobKindFor`), never chosen.
    return [{ rowId: row.id, kind: rowJobKind(row) as GroupKind, stage: "flex", subject: row.subjectId, label: OPT_METHOD_LABEL[row.method], config }];
  }
  const hdf = resolve.leadfield(row.subjectId, row.net);
  if (!hdf) return [];
  // Two pairs is the two-channel TI search, four is the multipolar mTI one — the same inference the
  // Simulator makes from a montage's pairs, and the only thing that decides `ex` from `mex`.
  const kind = rowJobKind(row);
  const targets: ExTarget[] = exTargets(row.roi, resolve.atlas(row.subjectId, row.roi), kind === "ex");
  return targets.map((t) => ({
    rowId: row.id,
    kind: kind as GroupKind,
    stage: rowStage(row),
    subject: row.subjectId,
    label: t.roiName,
    config:
      kind === "ex"
        ? buildExConfig(row.subjectId, hdf, row.ex, t, row.runName)
        : buildMExConfig(row.subjectId, hdf, row.mex, t, row.runName),
  }));
}

/**
 * Why a row that *looks* filled in still cannot run — the form-level checks the page used to make
 * globally, now made per row so the sentence can name which row.
 */
export function rowFormReason(row: OptimizerRow): string | null {
  if (row.method === "flex") {
    const form = row.flex;
    if (form.goal === "focality" && form.focalityMode === "manual" && !form.manualThresholds.trim()) {
      return "Enter at least one E-field threshold.";
    }
    if (form.enableMapping && !form.eegNet) return "Select an EEG net for the mapped-electrode simulation.";
    if (form.visualizeSkinElectrodes && !form.skinVisualizationNet) return "Select a visualization EEG net.";
    return null;
  }
  if (row.exPairs === 2) {
    if (row.ex.electrodeMode === "bucketed" && EX_BUCKET_KEYS.some((k) => (row.ex.buckets[k] ?? []).length === 0)) {
      return "Fill in every electrode bucket.";
    }
    if (row.ex.electrodeMode === "all" && row.ex.pool.length < 4) return "Add at least four electrodes to the pool.";
    return null;
  }
  if (MEX_BUCKET_KEYS.some((k) => (row.mex.buckets[k] ?? []).length === 0)) return "Fill in all eight electrode buckets.";
  return null;
}
