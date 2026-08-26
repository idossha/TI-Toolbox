#!/usr/bin/env simnibs_python
"""ROI resolution shared by the 2-pair and 4-pair exhaustive searches.

Both searches accept the same ROI inputs -- spherical centres from CSV, in
subject or MNI space, and volumetric atlas regions -- so the translation from
config fields to engine inputs lives here rather than in each search module.

See Also
--------
tit.opt.ex.engine.ExSearchEngine : Consumes the entries built here.
"""

import csv
import os
from pathlib import Path

import numpy as np


def read_roi_center(path: str) -> list[float]:
    """Return the first ``[x, y, z]`` triple in an ROI CSV.

    Rows that are empty or not fully numeric (a header such as ``x,y,z``)
    are skipped, so a CSV with a header row resolves the same as one
    without.

    Raises
    ------
    ValueError
        No row holds at least three numeric values.
    """
    with open(path) as f:
        for row in csv.reader(f):
            values = [v.strip() for v in row if v.strip()]
            try:
                coords = [float(v) for v in values]
            except ValueError:
                continue
            if len(coords) >= 3:
                return coords[:3]
    raise ValueError(f"No valid coordinates in {path}")


def mni_roi_files_to_subject_space(
    roi_names: list[str], roi_dir: str, m2m_path: str, output_dir: str, logger
) -> list[str]:
    """Reproject MNI-space ROI CSV centres to subject space.

    Reads each ROI CSV's ``x, y, z`` row, transforms it with
    ``simnibs.mni2subject_coords``, and writes a subject-space copy under
    *output_dir*. The search engine only ever receives subject-space centres.

    Parameters
    ----------
    roi_names : list of str
        ROI CSV filenames, relative to *roi_dir*.
    roi_dir : str
        Directory holding the ROI CSVs.
    m2m_path : str
        Subject ``m2m_<id>`` directory, used for the transform.
    output_dir : str
        Where the subject-space copies are written.
    logger : logging.Logger
        Logger for progress output.

    Returns
    -------
    list of str
        Paths to the subject-space CSVs, in the order given.
    """
    from simnibs import mni2subject_coords

    subject_files = []
    for name in roi_names:
        coords = read_roi_center(os.path.join(roi_dir, name))
        arr = np.atleast_2d(mni2subject_coords(np.array([coords]), str(m2m_path)))
        dst = os.path.join(output_dir, f"{Path(name).stem}_subject_space.csv")
        with open(dst, "w", newline="") as f:
            csv.writer(f).writerow(list(arr[0]))
        subject_files.append(dst)
    logger.info("Transformed %d MNI ROI center(s) to subject space", len(subject_files))
    return subject_files


def atlas_roi_entries(config) -> list:
    """Build engine ``roi_file`` entries from a config's ``roi_atlas`` targets.

    Parameters
    ----------
    config : ExConfig or MExConfig
        Any config exposing a ``roi_atlas`` sequence of targets with
        ``atlas_path`` and ``label`` attributes.

    Returns
    -------
    list
        A bare path per whole-file mask target, or a ``(path, label)`` pair
        per atlas-region target. Empty when no atlas targets are set.
    """
    if not getattr(config, "roi_atlas", None):
        return []
    return [
        target.atlas_path if target.label is None else (target.atlas_path, target.label)
        for target in config.roi_atlas
    ]
