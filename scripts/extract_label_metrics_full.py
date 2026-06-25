#!/usr/bin/env simnibs_python
"""Full-volume label inventory across all subjects (no spatial filtering).

Companion to ``extract_tissue_volumes_haber.py``. Where that script applies the
Haber brain-region / Z-cutoff filter and reports only CSF/bone/skin, THIS script
makes no spatial restriction: it counts *every* label present in each subject's
CHARM ``labeling.nii.gz`` over the whole volume and reports voxel counts and
volumes. Use it as a raw, assumption-free census -- e.g. to sanity-check the
filtered volumes, inspect tissues the Haber step ignores (GM/WM/eyes/muscle/...),
or build alternative whole-head tissue predictors.

Output (long / tidy CSV, one row per subject x label):
    subject_id, label, label_name, n_voxels, volume_mm3, volume_cm3,
    voxel_dx_mm, voxel_dy_mm, voxel_dz_mm

Run inside the ti-toolbox Docker container (PROJECT_DIR is auto-detected):
    simnibs_python scripts/extract_label_metrics_full.py
"""

from __future__ import annotations

import csv
import logging
import os
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

from tit.paths import get_path_manager

# --------------------------------------------------------------------------
# Config -- SUBJECTS=None processes every subject with an m2m folder.
# Set INCLUDE_ZERO=True to also emit the background (label 0) row per subject.
# --------------------------------------------------------------------------
SUBJECTS: list[str] | None = None
INCLUDE_ZERO = False
OUTPUT_CSV: str | None = None  # default: <ti-toolbox>/tissue_analysis/label_metrics_full.csv
RESUME = True  # skip subjects already present in the output CSV (set False to force re-run)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("extract_label_metrics_full")


def load_label_names(label_path: Path) -> dict[int, str]:
    """Parse ``labeling_LUT.txt`` (tab-separated: id<TAB>name) next to the volume."""
    lut = label_path.parent / "labeling_LUT.txt"
    names: dict[int, str] = {}
    if not lut.exists():
        logger.debug("No LUT next to %s", label_path)
        return names
    with open(lut, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                try:
                    names[int(parts[0].strip())] = parts[1].strip().rstrip(":")
                except ValueError:
                    continue
    return names


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

    fieldnames = [
        "subject_id",
        "label",
        "label_name",
        "n_voxels",
        "volume_mm3",
        "volume_cm3",
        "voxel_dx_mm",
        "voxel_dy_mm",
        "voxel_dz_mm",
    ]
    out_csv = OUTPUT_CSV or os.path.join(
        pm.ensure(os.path.join(pm.ti_toolbox(), "tissue_analysis")),
        "label_metrics_full.csv",
    )

    # Resume: keep rows for subjects already in the output CSV; recompute the rest.
    rows: list[dict] = []
    done: set[str] = set()
    if RESUME and os.path.exists(out_csv):
        with open(out_csv, newline="") as fh:
            for row in csv.DictReader(fh):
                rows.append(row)
                done.add(row["subject_id"])
        if done:
            logger.info("Resume: %d subjects already in %s", len(done), out_csv)

    failed: list[str] = []
    skipped = 0

    for sid in subjects:
        if RESUME and f"sub-{sid}" in done:
            skipped += 1
            continue
        label_path = Path(pm.tissue_labeling(sid))
        if not label_path.exists():
            logger.warning("sub-%s: labeling.nii.gz not found (%s)", sid, label_path)
            failed.append(sid)
            continue
        logger.info("=== sub-%s ===", sid)
        try:
            nii = nib.load(str(label_path))
            data = np.asanyarray(nii.dataobj)
            dx, dy, dz = (float(z) for z in nii.header.get_zooms()[:3])
            voxel_volume = dx * dy * dz  # mm^3
            names = load_label_names(label_path)

            labels, counts = np.unique(np.rint(data).astype(np.int64), return_counts=True)
            for label, count in zip(labels.tolist(), counts.tolist()):
                if label == 0 and not INCLUDE_ZERO:
                    continue
                vol_mm3 = count * voxel_volume
                rows.append(
                    {
                        "subject_id": f"sub-{sid}",
                        "label": label,
                        "label_name": names.get(label, ""),
                        "n_voxels": count,
                        "volume_mm3": vol_mm3,
                        "volume_cm3": vol_mm3 / 1000.0,
                        "voxel_dx_mm": dx,
                        "voxel_dy_mm": dy,
                        "voxel_dz_mm": dz,
                    }
                )
            logger.info("sub-%s: %d distinct labels", sid, len(labels))
        except Exception as exc:  # noqa: BLE001 -- keep the loop going
            logger.warning("sub-%s failed: %s", sid, exc)
            failed.append(sid)
            continue

    if not rows:
        logger.error("No label rows produced; nothing written.")
        return 1

    with open(out_csv, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Wrote %d rows (%d subjects) to %s (%d subjects reused)",
                len(rows), len({r["subject_id"] for r in rows}), out_csv, skipped)
    if failed:
        logger.warning("Failed subjects (%d): %s", len(failed), ", ".join(failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
