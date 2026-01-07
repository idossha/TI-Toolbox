#!/usr/bin/env simnibs_python
"""ROI helpers used across optimizers/analyzers.

Goal: keep this module small and fast. It intentionally focuses on:
- Mapping simple ROI definitions (sphere + tissue tags) to mesh elements
- Computing summary metrics for an ROI (and optional GM reference)
- Minimal coordinate helpers for ex-search (CSV + MNI→subject)
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np


def find_roi_element_indices(mesh, roi_coords: Sequence[float], radius: float = 3.0):
    """Return element indices/volumes for elements whose barycenters fall in a sphere."""
    centers = mesh.elements_baricenters()
    if hasattr(centers, 'value'):
        centers = centers.value
    centers = np.asarray(centers).reshape(-1, 3)  # Ensure 2D shape (N, 3)
    center = np.asarray(roi_coords, dtype=float)
    r2 = float(radius) ** 2
    d2 = np.sum((centers - center) ** 2, axis=1)
    mask = d2 <= r2
    volumes_areas = mesh.elements_volumes_and_areas()
    if hasattr(volumes_areas, 'value'):
        volumes_areas = volumes_areas.value
    volumes_areas = np.asarray(volumes_areas)
    if volumes_areas.ndim > 1:
        # If it returns volumes and areas as separate columns, take volumes (first column)
        volumes_areas = volumes_areas[:, 0]
    return np.flatnonzero(mask), volumes_areas[mask]


def find_grey_matter_indices(mesh, grey_matter_tags: Iterable[int] = (2,)):
    """Return element indices/volumes for elements with tags in `grey_matter_tags`."""
    tags = mesh.elm.tag1
    mask = np.isin(tags, list(grey_matter_tags))
    volumes_areas = mesh.elements_volumes_and_areas()
    if hasattr(volumes_areas, 'value'):
        volumes_areas = volumes_areas.value
    volumes_areas = np.asarray(volumes_areas)
    if volumes_areas.ndim > 1:
        # If it returns volumes and areas as separate columns, take volumes (first column)
        volumes_areas = volumes_areas[:, 0]
    return np.flatnonzero(mask), volumes_areas[mask]


def calculate_roi_metrics(
    ti_field_roi,
    element_volumes,
    ti_field_gm=None,
    gm_volumes=None,
):
    """Compute TImax/TImean in ROI and (optionally) focality vs GM."""
    if len(ti_field_roi) == 0:
        return {
            "TImax_ROI": 0.0,
            "TImean_ROI": 0.0,
            "n_elements": 0,
            # Preserve existing behavior used in tests
            "Focality": 0.0,
        }

    timax_roi = float(np.max(ti_field_roi))
    timean_roi = float(np.average(ti_field_roi, weights=element_volumes))

    result = {
        "TImax_ROI": timax_roi,
        "TImean_ROI": timean_roi,
        "n_elements": int(len(ti_field_roi)),
    }

    if ti_field_gm is not None and gm_volumes is not None and len(ti_field_gm) > 0:
        timean_gm = float(np.average(ti_field_gm, weights=gm_volumes))
        focality = float(timean_roi / timean_gm) if timean_gm > 0 else 0.0
        result["TImean_GM"] = timean_gm
        result["Focality"] = focality

    return result


class ROICoordinateHelper:
    @staticmethod
    def transform_mni_to_subject(mni_coords: Sequence[float], m2m_path: str):
        # Lazy import so this module stays importable without SimNIBS installed
        from simnibs.utils.transformations import mni2subject_coords

        return mni2subject_coords(list(mni_coords), m2m_path)

    @staticmethod
    def find_voxels_in_sphere(voxel_positions, center: Sequence[float], radius: float):
        center = np.asarray(center, dtype=float)
        r2 = float(radius) ** 2
        d2 = np.sum((voxel_positions - center) ** 2, axis=1)
        return np.flatnonzero(d2 <= r2)

    @staticmethod
    def load_roi_from_csv(csv_path: str):
        import csv

        try:
            with open(csv_path, "r") as f:
                for row in csv.reader(f):
                    if not row:
                        continue
                    try:
                        coords = [float(c.strip()) for c in row]
                    except ValueError:
                        continue
                    if len(coords) >= 3:
                        return np.asarray(coords[:3], dtype=float)
        except FileNotFoundError:
            return None
        except Exception:
            return None
        return None

    @staticmethod
    def save_roi_to_csv(coordinates: Sequence[float], csv_path: str):
        import csv

        with open(csv_path, "w", newline="") as f:
            csv.writer(f).writerow(list(coordinates))


def validate_ti_montage(electrodes: Sequence[int], num_electrodes: int) -> bool:
    if len(electrodes) != 4:
        return False
    if len(set(electrodes)) != 4:
        return False
    if any(e < 0 or e >= num_electrodes for e in electrodes):
        return False
    return True


__all__ = [
    "find_roi_element_indices",
    "find_grey_matter_indices",
    "calculate_roi_metrics",
    "ROICoordinateHelper",
    "validate_ti_montage",
]