#!/usr/bin/env simnibs_python
"""
Fix T2 filenames for FreeSurfer compatibility.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

from .common import PreprocessError


def _clean_name(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if re.search(r"[Tt]1", name):
        return "anat-T1w_acq-MPRAGE"
    if re.search(r"[Tt]2", name):
        return "anat-T2w_acq-CUBE"
    return name


def run_fix_t2_filenames(project_dir: str, *, logger) -> None:
    """Fix T2 filenames to be FreeSurfer-friendly.

    Parameters
    ----------
    project_dir : str
        BIDS project root.
    logger : logging.Logger
        Logger used for progress output.
    """
    project_path = Path(project_dir)
    if not project_path.is_dir():
        raise PreprocessError(f"Project directory does not exist: {project_dir}")

    processed = 0
    for subject_dir in sorted(project_path.glob("sub-*")):
        if not subject_dir.is_dir():
            continue
        anat_dir = subject_dir / "anat"
        if not anat_dir.is_dir():
            continue
        subject_id = subject_dir.name
        logger.info(f"Processing subject: {subject_id}")

        for file_path in anat_dir.iterdir():
            if not file_path.is_file():
                continue
            filename = file_path.name
            if " " not in filename and "T2" not in filename and "t2" not in filename:
                continue

            suffix = "".join(file_path.suffixes)
            base_name = filename[: -len(suffix)] if suffix else file_path.stem
            clean_name = _clean_name(base_name)
            new_filename = f"{clean_name}{suffix}"
            new_path = anat_dir / new_filename

            if new_path.exists():
                timestamp_suffix = time.strftime("_%H%M%S")
                new_filename = f"{clean_name}{timestamp_suffix}{suffix}"
                new_path = anat_dir / new_filename

            file_path.rename(new_path)
            logger.info(f"Renamed {filename} -> {new_filename}")
        processed += 1

    logger.info(f"Completed T2 filename fixing for {processed} subjects")
