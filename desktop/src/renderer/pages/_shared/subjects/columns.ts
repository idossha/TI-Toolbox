/**
 * The general-case readiness columns (J3), built from the same booleans and the same words as
 * `app/subjectContext.ts`'s `presenceChips` — the vocabulary the Subjects page, the Subject-info
 * panel and Pre-processing already share. A page picks the subset its own data supports; nobody
 * invents a new dot.
 */
import type { SubjectColumn } from "./types";

/** The fields `GET /api/catalog/subjects` returns, plus the two only the per-subject detail has. */
export interface PresenceLike {
  id: string;
  has_raw: boolean;
  has_fastsurfer: boolean;
  has_freesurfer: boolean;
  has_m2m: boolean;
  has_dwi?: boolean;
  has_ct?: boolean;
  has_sourcedata?: boolean;
}

/**
 * RAW / FS / FSR / M2M (+ DWI / CT where the page has the detail read that carries them).
 * FastSurfer before FreeSurfer, matching `tit/catalog.py`'s own column order.
 */
export function presenceColumns<T extends PresenceLike>(opts: { dwi?: boolean; ct?: boolean } = {}): SubjectColumn<T>[] {
  const columns: SubjectColumn<T>[] = [
    { id: "raw", label: "raw", present: (s) => s.has_raw },
    { id: "fastsurfer", label: "fastsurfer", present: (s) => s.has_fastsurfer },
    { id: "freesurfer", label: "freesurfer", present: (s) => s.has_freesurfer },
    { id: "m2m", label: "m2m", present: (s) => s.has_m2m },
  ];
  if (opts.dwi) columns.push({ id: "dwi", label: "dwi", present: (s) => s.has_dwi === true });
  if (opts.ct) columns.push({ id: "ct", label: "ct", present: (s) => s.has_ct === true });
  return columns;
}

/**
 * "DICOMs are staged under `sourcedata/` but nothing is converted yet" — a state, not a presence,
 * so it renders as a warning flag and only when true. Without it such a subject's row is four
 * muted chips, indistinguishable from a directory with nothing in it at all (lane FX5).
 */
export function notConvertedColumn<T extends PresenceLike>(): SubjectColumn<T> {
  return {
    id: "not-converted",
    label: "not converted",
    kind: "flag",
    title: "DICOM staged under sourcedata/, not yet converted",
    present: (s) => !s.has_raw && s.has_sourcedata === true,
  };
}
