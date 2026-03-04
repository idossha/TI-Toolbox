"""Utility helpers for the tit.pre package."""
from __future__ import annotations

import os
import glob
from typing import List


def discover_subjects(project_dir: str) -> List[str]:
    """Return sorted, deduplicated subject IDs found in a BIDS project tree.

    Discovery order:
    1. sourcedata/sub-*/T1w/ or T2w/ — any subdir, NIfTI (.nii/.nii.gz), or .tgz
    2. sourcedata/sub-*/*.tgz (compressed bundles at top level)
    3. sub-*/anat/*T1w*.nii[.gz] or *T2w*.nii[.gz] at project root
    """
    found: List[str] = []

    # First check sourcedata directory for new subjects
    sourcedata_dir = os.path.join(project_dir, "sourcedata")

    if os.path.exists(sourcedata_dir):
        for subj_dir in glob.glob(os.path.join(sourcedata_dir, "sub-*")):
            if os.path.isdir(subj_dir):
                t1w_dir = os.path.join(subj_dir, "T1w")
                t2w_dir = os.path.join(subj_dir, "T2w")

                has_valid_structure = (
                    (
                        os.path.exists(t1w_dir)
                        and (
                            any(
                                os.path.isdir(os.path.join(t1w_dir, d))
                                for d in os.listdir(t1w_dir)
                            )
                            or any(
                                f.endswith((".tgz", ".json", ".nii", ".nii.gz"))
                                for f in os.listdir(t1w_dir)
                            )
                        )
                    )
                    or (
                        os.path.exists(t2w_dir)
                        and (
                            any(
                                os.path.isdir(os.path.join(t2w_dir, d))
                                for d in os.listdir(t2w_dir)
                            )
                            or any(
                                f.endswith((".tgz", ".json", ".nii", ".nii.gz"))
                                for f in os.listdir(t2w_dir)
                            )
                        )
                    )
                    or any(f.endswith(".tgz") for f in os.listdir(subj_dir))
                )

                if has_valid_structure:
                    subject_id = os.path.basename(subj_dir).replace("sub-", "")
                    found.append(subject_id)

    # Also check root directory for BIDS-compliant subjects (like example data)
    for subj_dir in glob.glob(os.path.join(project_dir, "sub-*")):
        if os.path.isdir(subj_dir):
            subject_id = os.path.basename(subj_dir).replace("sub-", "")

            # Skip if already added from sourcedata
            if subject_id in found:
                continue

            # Check if this subject has BIDS-compliant anatomical data
            anat_dir = os.path.join(subj_dir, "anat")
            if os.path.exists(anat_dir):
                has_nifti = any(
                    f.endswith((".nii", ".nii.gz")) and ("T1w" in f or "T2w" in f)
                    for f in os.listdir(anat_dir)
                )
                if has_nifti:
                    found.append(subject_id)

    return sorted(found)


def check_m2m_exists(project_dir: str, subject_id: str) -> bool:
    """Return True if the SimNIBS m2m directory for subject_id already exists.

    Path: <project_dir>/derivatives/SimNIBS/sub-<subject_id>/m2m_<subject_id>
    """
    m2m_dir = os.path.join(
        project_dir,
        "derivatives",
        "SimNIBS",
        f"sub-{subject_id}",
        f"m2m_{subject_id}",
    )
    return os.path.exists(m2m_dir)
