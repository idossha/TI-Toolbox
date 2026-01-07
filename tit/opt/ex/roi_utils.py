#!/usr/bin/env simnibs_python
"""
ROI management utilities for ex-search optimization.

This module provides shared functionality for ROI management that can be used
by both CLI and GUI implementations of ex-search.
"""

import csv
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tit.core import get_path_manager
from tit.core.roi import ROICoordinateHelper


def load_roi_presets() -> Dict[str, Dict]:
    """Load ROI presets from the roi_presets.json file."""
    # Try multiple possible locations for the presets file
    possible_paths = [
        Path(__file__).parent.parent / "roi_presets.json",  # tit/opt/roi_presets.json
        Path(__file__).parent.parent.parent / "resources" / "roi_presets.json",  # resources/roi_presets.json
    ]

    for preset_path in possible_paths:
        if preset_path.exists():
            try:
                with open(preset_path, 'r') as f:
                    data = json.load(f)
                    return data.get('regions', {})
            except (json.JSONDecodeError, KeyError):
                continue

    # Return empty dict if no presets found
    return {}


def get_available_rois(subject_id: str) -> List[str]:
    """Get list of available ROIs for a subject."""
    pm = get_path_manager()
    m2m_dir = pm.get_m2m_dir(subject_id)
    roi_dir = os.path.join(m2m_dir, "ROIs")

    roi_files = []
    for p in Path(roi_dir).glob("*.csv"):
        roi_files.append(p.name)

    return sorted(roi_files)


def create_roi_from_preset(
    subject_id: str,
    roi_name: str,
    preset_key: str,
    presets: Optional[Dict[str, Dict]] = None
) -> Tuple[bool, str]:
    """
    Create an ROI from a preset.

    Args:
        subject_id: Subject identifier
        roi_name: Name for the ROI file (without .csv extension)
        preset_key: Key of the preset to use
        presets: Optional preset dictionary (will load if not provided)

    Returns:
        Tuple of (success: bool, message: str)
    """
    if presets is None:
        presets = load_roi_presets()

    if preset_key not in presets:
        return False, f"Preset '{preset_key}' not found"

    try:
        pm = get_path_manager()
        m2m_dir = pm.get_m2m_dir(subject_id)
        roi_dir = os.path.join(m2m_dir, "ROIs")
        os.makedirs(roi_dir, exist_ok=True)

        # Ensure .csv extension
        if not roi_name.endswith('.csv'):
            roi_name += '.csv'

        roi_file = Path(roi_dir) / roi_name

        # Get MNI coordinates from preset
        mni_coords = presets[preset_key]['mni']

        # Transform to subject space
        subject_coords = ROICoordinateHelper.transform_mni_to_subject(mni_coords, m2m_dir)
        x, y, z = subject_coords[0], subject_coords[1], subject_coords[2]

        # Save ROI file
        ROICoordinateHelper.save_roi_to_csv([x, y, z], str(roi_file))

        # Update roi_list.txt
        _update_roi_list_file(roi_dir, roi_name)

        return True, f"ROI '{roi_name}' created successfully at ({x:.2f}, {y:.2f}, {z:.2f})"

    except Exception as e:
        return False, f"Failed to create ROI: {str(e)}"


def create_roi_from_coordinates(
    subject_id: str,
    roi_name: str,
    x: float,
    y: float,
    z: float
) -> Tuple[bool, str]:
    """
    Create an ROI from custom coordinates.

    Args:
        subject_id: Subject identifier
        roi_name: Name for the ROI file (without .csv extension)
        x, y, z: Coordinates in subject space (RAS)

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        pm = get_path_manager()
        m2m_dir = pm.get_m2m_dir(subject_id)
        roi_dir = os.path.join(m2m_dir, "ROIs")
        os.makedirs(roi_dir, exist_ok=True)

        # Ensure .csv extension
        if not roi_name.endswith('.csv'):
            roi_name += '.csv'

        roi_file = Path(roi_dir) / roi_name

        # Save ROI file
        ROICoordinateHelper.save_roi_to_csv([x, y, z], str(roi_file))

        # Update roi_list.txt
        _update_roi_list_file(roi_dir, roi_name)

        return True, f"ROI '{roi_name}' created successfully at ({x:.2f}, {y:.2f}, {z:.2f})"

    except Exception as e:
        return False, f"Failed to create ROI: {str(e)}"


def delete_roi(subject_id: str, roi_name: str) -> Tuple[bool, str]:
    """
    Delete an ROI file.

    Args:
        subject_id: Subject identifier
        roi_name: Name of the ROI file to delete

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        pm = get_path_manager()
        m2m_dir = pm.get_m2m_dir(subject_id)
        roi_dir = os.path.join(m2m_dir, "ROIs")

        # Ensure .csv extension
        if not roi_name.endswith('.csv'):
            roi_name += '.csv'

        roi_file = Path(roi_dir) / roi_name
        roi_list_file = Path(roi_dir) / "roi_list.txt"

        # Remove the ROI file
        if roi_file.exists():
            roi_file.unlink()

        # Update roi_list.txt
        if roi_list_file.exists():
            with open(roi_list_file, 'r') as f:
                existing_rois = [line.strip() for line in f.readlines()]

            if roi_name in existing_rois:
                existing_rois.remove(roi_name)

                with open(roi_list_file, 'w') as f:
                    for roi in existing_rois:
                        f.write(f"{roi}\n")

        return True, f"ROI '{roi_name}' deleted successfully"

    except Exception as e:
        return False, f"Failed to delete ROI: {str(e)}"


def get_roi_coordinates(subject_id: str, roi_name: str) -> Optional[Tuple[float, float, float]]:
    """
    Get coordinates for an ROI.

    Args:
        subject_id: Subject identifier
        roi_name: Name of the ROI file

    Returns:
        Tuple of (x, y, z) coordinates or None if not found
    """
    try:
        pm = get_path_manager()
        m2m_dir = pm.get_m2m_dir(subject_id)
        roi_dir = os.path.join(m2m_dir, "ROIs")

        # Ensure .csv extension
        if not roi_name.endswith('.csv'):
            roi_name += '.csv'

        roi_file = Path(roi_dir) / roi_name

        coords = ROICoordinateHelper.load_roi_from_csv(str(roi_file))
        if coords is not None:
            return (float(coords[0]), float(coords[1]), float(coords[2]))

        return None

    except Exception:
        return None


def _update_roi_list_file(roi_dir: str, roi_name: str):
    """Update the roi_list.txt file to include a new ROI."""
    roi_list_file = Path(roi_dir) / "roi_list.txt"

    # Read existing ROIs
    existing_rois = []
    if roi_list_file.exists():
        with open(roi_list_file, 'r') as f:
            existing_rois = [line.strip() for line in f.readlines()]

    # Add new ROI if not already present
    if roi_name not in existing_rois:
        with open(roi_list_file, 'a') as f:
            f.write(f"{roi_name}\n")


__all__ = [
    "load_roi_presets",
    "get_available_rois",
    "create_roi_from_preset",
    "create_roi_from_coordinates",
    "delete_roi",
    "get_roi_coordinates",
]
