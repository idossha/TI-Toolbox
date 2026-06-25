#!/usr/bin/env simnibs_python
"""Run both anatomy extractions for subjects 142 and onward only.

Convenience wrapper: filters the subject list to numeric IDs >= START_SUBJECT and
runs both extraction scripts on just that subset, merging into the same output
CSVs (tissue_volumes_haber.csv, label_metrics_full.csv) as the full sweep. RESUME
in those scripts still applies, so already-finished subjects in the subset are
skipped too.

Run inside the ti-toolbox Docker container (from /ti-toolbox):
    simnibs_python scripts/extract_from_142.py
"""

from __future__ import annotations

import logging
import sys

from tit.paths import get_path_manager

# scripts/ is sys.path[0] when invoked as `simnibs_python scripts/extract_from_142.py`,
# so the sibling extraction modules import directly.
import extract_tissue_volumes_haber as tissue_vol
import extract_label_metrics_full as label_metrics

START_SUBJECT = 142  # inclusive lower bound on numeric subject ID

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("extract_from_142")


def main() -> int:
    pm = get_path_manager()
    if not pm.project_dir:
        logger.error(
            "PROJECT_DIR is not set / detectable. `export PROJECT_DIR=/mnt/<project>`."
        )
        return 1

    all_subjects = pm.list_simnibs_subjects()
    subset = sorted(
        (s for s in all_subjects if s.isdigit() and int(s) >= START_SUBJECT),
        key=int,
    )
    if not subset:
        logger.error("No numeric subjects >= %d found among: %s",
                     START_SUBJECT, ", ".join(all_subjects))
        return 1
    logger.info("Subjects >= %d (%d): %s", START_SUBJECT, len(subset), ", ".join(subset))

    # Drive both extraction scripts on just this subset via their module globals.
    tissue_vol.SUBJECTS = subset
    label_metrics.SUBJECTS = subset

    logger.info("--- Haber-style tissue volumes ---")
    rc1 = tissue_vol.main()
    logger.info("--- Full-volume label metrics ---")
    rc2 = label_metrics.main()
    return rc1 or rc2


if __name__ == "__main__":
    sys.exit(main())
