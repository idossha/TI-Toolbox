#!/usr/bin/env simnibs_python
"""Haber et al. (2026) style tissue-volume extraction across all subjects.

Loops over every subject with a SimNIBS head model and runs the toolbox's own
``run_tissue_analysis`` (the exact code that produced the volumetrics in
Haber et al. 2026, Brain Stimulation 19:103016, Sec. 3.5). For each subject it
extracts CSF / bone / skin **volume** (brain-bounding-box + brainstem-referenced
Z-cutoff, ``volume = filtered_voxels x voxel_volume``) plus thickness summaries,
and aggregates everything into a single tidy CSV for downstream modeling.

Why reuse the toolbox code instead of re-implementing:
  - The CHARM labeling.nii.gz uses a *mixed* label scheme (FreeSurfer-aseg
    labels for CSF ventricles + charm labels 511/515/516/520 for skin/bone/CSF).
    TISSUE_CONFIGS in tit.pre.tissue_analyzer is the single source of truth.
  - Matching Haber's numbers exactly requires the same Z-cutoff / padding logic.

Output
------
One row per subject, columns:
    subject_id,
    {tissue}_volume_cm3, {tissue}_volume_mm3,
    {tissue}_thickness_mean_mm, {tissue}_thickness_std_mm,
    {tissue}_thickness_min_mm, {tissue}_thickness_max_mm,
    {tissue}_voxels_total, {tissue}_voxels_filtered
for tissue in (csf, bone, skin).

Per-subject text reports + methodology/thickness figures are also written by the
analyzer under derivatives/ti-toolbox/tissue_analysis/sub-XXX/.

Run inside the ti-toolbox Docker container (PROJECT_DIR is auto-detected):
    simnibs_python scripts/extract_tissue_volumes_haber.py
"""

from __future__ import annotations

import csv
import logging
import os
import sys

from tit.paths import get_path_manager
from tit.pre.tissue_analyzer import DEFAULT_TISSUES, run_tissue_analysis

# --------------------------------------------------------------------------
# Config -- edit SUBJECTS to a list of IDs (without "sub-") to restrict, or
# leave as None to process every subject with an m2m folder.
# --------------------------------------------------------------------------
SUBJECTS: list[str] | None = None
TISSUES = tuple(DEFAULT_TISSUES)  # ("bone", "csf", "skin")
OUTPUT_CSV: str | None = None  # default: <ti-toolbox>/tissue_analysis/tissue_volumes_haber.csv
RESUME = True  # skip subjects already present in the output CSV (set False to force re-run)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("extract_tissue_volumes")


def _row_for_subject(results: dict) -> dict:
    """Flatten run_tissue_analysis() output into one flat CSV row."""
    row: dict[str, object] = {}
    for tissue in TISSUES:
        res = results.get(tissue, {}) or {}
        thick = res.get("thickness", {}) or {}
        voxels = res.get("voxels", {}) or {}
        row[f"{tissue}_volume_cm3"] = res.get("volume_cm3", "")
        row[f"{tissue}_volume_mm3"] = res.get("volume_mm3", "")
        row[f"{tissue}_thickness_mean_mm"] = thick.get("mean", "")
        row[f"{tissue}_thickness_std_mm"] = thick.get("std", "")
        row[f"{tissue}_thickness_min_mm"] = thick.get("min", "")
        row[f"{tissue}_thickness_max_mm"] = thick.get("max", "")
        row[f"{tissue}_voxels_total"] = voxels.get("total", "")
        row[f"{tissue}_voxels_filtered"] = voxels.get("filtered", "")
    return row


def main() -> int:
    pm = get_path_manager()
    project_dir = pm.project_dir
    if not project_dir:
        logger.error(
            "PROJECT_DIR is not set / detectable. Run inside the ti-toolbox "
            "container or `export PROJECT_DIR=/mnt/<project>`."
        )
        return 1

    subjects = SUBJECTS if SUBJECTS is not None else pm.list_simnibs_subjects()
    if not subjects:
        logger.error("No subjects with an m2m folder found under %s", pm.simnibs())
        return 1
    logger.info("Project: %s", project_dir)
    logger.info("Subjects (%d): %s", len(subjects), ", ".join(subjects))

    fieldnames = ["subject_id"]
    for tissue in TISSUES:
        fieldnames += [
            f"{tissue}_volume_cm3",
            f"{tissue}_volume_mm3",
            f"{tissue}_thickness_mean_mm",
            f"{tissue}_thickness_std_mm",
            f"{tissue}_thickness_min_mm",
            f"{tissue}_thickness_max_mm",
            f"{tissue}_voxels_total",
            f"{tissue}_voxels_filtered",
        ]

    out_csv = OUTPUT_CSV or os.path.join(
        pm.ensure(os.path.join(pm.ti_toolbox(), "tissue_analysis")),
        "tissue_volumes_haber.csv",
    )

    # Resume: keep rows for subjects already in the output CSV; recompute the rest.
    existing: dict[str, dict] = {}
    if RESUME and os.path.exists(out_csv):
        with open(out_csv, newline="") as fh:
            for row in csv.DictReader(fh):
                existing[row["subject_id"]] = row
        if existing:
            logger.info("Resume: %d subjects already in %s", len(existing), out_csv)

    rows: list[dict] = []
    failed: list[str] = []
    skipped = 0
    for sid in subjects:
        if RESUME and f"sub-{sid}" in existing:
            rows.append(existing[f"sub-{sid}"])
            skipped += 1
            continue
        logger.info("=== sub-%s ===", sid)
        try:
            results = run_tissue_analysis(
                project_dir, sid, tissues=TISSUES, logger=logger
            )
        except Exception as exc:  # noqa: BLE001 -- keep the loop going
            logger.warning("sub-%s failed: %s", sid, exc)
            failed.append(sid)
            continue
        row = {"subject_id": f"sub-{sid}"}
        row.update(_row_for_subject(results))
        rows.append(row)

    if not rows:
        logger.error("No subjects produced results; nothing written.")
        return 1

    with open(out_csv, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Wrote %d subjects to %s (%d reused, %d newly computed)",
                len(rows), out_csv, skipped, len(rows) - skipped)
    if failed:
        logger.warning("Failed subjects (%d): %s", len(failed), ", ".join(failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
