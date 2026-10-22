/**
 * What a row's target becomes when the row moves to another subject (a subject change, or a
 * duplicate re-pointed at another subject).
 *
 * The rule is the coordinate frame. Subject-space millimetres and a subject-space mask name points
 * in ONE subject's scanner frame — `analyzer.py::_analyze_mask_file` samples a mask by world
 * coordinates, and a flex/ex sphere is placed at those millimetres — so carried to another head
 * they measure or optimise the wrong anatomy without any error. A saved ROI is a CSV of the old
 * subject (`rois/sub-<id>/`), which the new subject may not have or may mean differently. MNI
 * spheres and MNI masks are one frame for every subject (each run warps them to its own head),
 * and an atlas target is an atlas *id* resolved against each subject's own files when the job is
 * built (U16), so those three are kept.
 */
import { emptyRoi, type RoiValue } from "./types";

/** The target to keep after moving a row from subject `from` to `to`, and the sentence saying
 *  what was cleared (`null` when nothing was). */
export interface SubjectChangeResult {
  roi: RoiValue;
  note: string | null;
}

export function roiForSubject(roi: RoiValue, from: string, to: string): SubjectChangeResult {
  if (from === to || !from) return { roi, note: null };
  const head = `sub-${from}`;
  if (roi.mode === "spherical" && roi.space === "subject") {
    if (roi.spheres.every((s) => s.x === undefined && s.y === undefined && s.z === undefined)) return { roi, note: null };
    return {
      roi: { ...roi, spheres: (emptyRoi("spherical", "subject") as typeof roi).spheres },
      note: `The subject-space sphere was cleared: its coordinates are millimetres in ${head}'s head, not sub-${to}'s. Enter coordinates for sub-${to}, or use MNI space.`,
    };
  }
  if (roi.mode === "mask" && roi.space === "subject") {
    if (!roi.path.trim()) return { roi, note: null };
    return {
      roi: { ...roi, path: "" },
      note: `The subject-space mask was cleared: it is drawn in ${head}'s head, not sub-${to}'s. Choose a mask for sub-${to}, or an MNI-space mask.`,
    };
  }
  if (roi.mode === "saved") {
    if (roi.selected.length === 0) return { roi, note: null };
    return {
      roi: { ...roi, selected: [] },
      note: `The saved ROI selection was cleared: ${roi.selected.join(", ")} belong${roi.selected.length === 1 ? "s" : ""} to ${head}. Choose sub-${to}'s own ROIs.`,
    };
  }
  return { roi, note: null };
}
