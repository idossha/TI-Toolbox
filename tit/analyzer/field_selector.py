"""
Field selection utilities for automatic field file determination.

This module provides functions to automatically select appropriate field files
for analysis, eliminating the need for manual user selection.
"""

import os
from pathlib import Path
from typing import Optional, Tuple
from tit.core import get_path_manager


def _extract_subject_and_project_dirs(m2m_subject_path: str) -> Tuple[str, str]:
    """
    Extract subject ID and project directory from m2m subject path.

    Uses PathManager for standardized project directory handling.

    Returns:
        Tuple of (subject_id, project_dir)
    """
    # Extract subject ID from m2m_subject_path, preserving underscores (e.g., m2m_ernie_extended -> ernie_extended)
    base_name = os.path.basename(m2m_subject_path)
    subject_id = base_name[4:] if base_name.startswith('m2m_') else base_name

    # Navigate up to find the project directory
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(m2m_subject_path))))

    # Use PathManager to standardize the project directory path
    # This handles /mnt/ prefix logic and validation
    pm = get_path_manager()
    if pm.project_dir and os.path.abspath(project_dir) == os.path.abspath(pm.project_dir):
        # If it matches the global path manager's project dir, use that (handles /mnt/ logic)
        project_dir = pm.project_dir
    elif not project_dir.startswith('/mnt/'):
        # Apply /mnt/ prefix if not already present (fallback logic)
        project_dir = f"/mnt/{os.path.basename(project_dir)}"

    return subject_id, project_dir


def select_field_file(
    m2m_subject_path: str,
    montage_name: str,
    space: str,
    analysis_type: str = "spherical"
) -> Tuple[str, str]:
    """
    Automatically select the appropriate field file for analysis.

    Args:
        m2m_subject_path: Path to the m2m subject directory
        montage_name: Name of the simulation montage
        space: Analysis space ('mesh' or 'voxel')
        analysis_type: Type of analysis ('spherical' or 'cortical')

    Returns:
        Tuple of (field_path, field_name) where field_name is the SimNIBS field name

    Raises:
        FileNotFoundError: If no suitable field file is found
        ValueError: If space is not supported
    """
    if space == 'mesh':
        field_path = _select_mesh_field_file(m2m_subject_path, montage_name)
        # Determine field name based on simulation type
        field_name = "TI_Max" if 'mTI' in field_path else "TI_max"
    elif space == 'voxel':
        field_path = _select_voxel_field_file(m2m_subject_path, montage_name)
        field_name = "TI_max"  # Voxel analysis typically uses lowercase
    else:
        raise ValueError(f"Unsupported space: {space}")

    return field_path, field_name


def _select_mesh_field_file(m2m_subject_path: str, montage_name: str) -> str:
    """
    Select the appropriate mesh field file based on montage name.

    This implements the same logic as construct_mesh_field_path in main_analyzer.py
    """
    from tit.core.paths import PathManager

    subject_id, project_dir = _extract_subject_and_project_dirs(m2m_subject_path)

    # Create PathManager instance for this project directory
    pm = PathManager(project_dir=project_dir)

    # Get base simulation directory using PathManager
    base_sim_dir = pm.path_optional("simulation", subject_id=subject_id, simulation_name=montage_name)
    if not base_sim_dir:
        raise FileNotFoundError(f"No simulation directory found for {montage_name}")

    # Check if mTI directory exists - if yes, this is an mTI simulation
    mti_mesh_dir = os.path.join(base_sim_dir, 'mTI', 'mesh')
    ti_mesh_dir = os.path.join(base_sim_dir, 'TI', 'mesh')

    # Determine if this is an mTI or TI simulation
    is_mti = os.path.exists(mti_mesh_dir)

    if is_mti:
        # For mTI simulations, look in mTI/mesh directory for _mTI.msh files
        mesh_dir = mti_mesh_dir
        possible_filenames = []

        # Pattern 1: Use montage directory name + _mTI.msh
        possible_filenames.append(f'{montage_name}_mTI.msh')

        # Pattern 2: Check for variations with _mTI suffix
        if '_mTINormal' in montage_name:
            possible_filenames.append(f'{montage_name}_mTI.msh')

        # Pattern 3: Standard pattern where we remove any _mTI-related suffix from montage name
        if montage_name.endswith('_mTINormal'):
            base_name = montage_name.replace('_mTINormal', '')
            possible_filenames.append(f'{base_name}_mTI.msh')
        elif montage_name.endswith('Normal'):
            base_name = montage_name.replace('Normal', '')
            possible_filenames.append(f'{base_name}_mTI.msh')
    else:
        # For regular TI simulations, use the original logic
        mesh_dir = ti_mesh_dir
        possible_filenames = []

        # Pattern 1: Use montage directory name + _TI.msh
        possible_filenames.append(f'{montage_name}_TI.msh')

        # Pattern 2: If montage dir has _TINormal, the file might be montage_dir + _TI.msh
        # (This handles the case where directory is ernie_sphere_5mm_max_TINormal and file is ernie_sphere_5mm_max_TINormal_TI.msh)
        if '_TINormal' in montage_name:
            possible_filenames.append(f'{montage_name}_TI.msh')  # Already added above, but keep for clarity

        # Pattern 3: Standard pattern where we remove any _TI-related suffix from montage name
        if montage_name.endswith('_TINormal'):
            base_name = montage_name.replace('_TINormal', '')
            possible_filenames.append(f'{base_name}_TI.msh')
        elif montage_name.endswith('Normal'):
            base_name = montage_name.replace('Normal', '')
            possible_filenames.append(f'{base_name}_TI.msh')

        # Pattern 4: Some exports use *_normal.msh rather than *_TI.msh
        possible_filenames.append(f'{montage_name}_normal.msh')
        if montage_name.endswith('_Normal'):
            base_name = montage_name[:-7]
            possible_filenames.append(f'{base_name}_normal.msh')

    # Remove duplicates while preserving order
    seen = set()
    unique_filenames = []
    for filename in possible_filenames:
        if filename not in seen:
            seen.add(filename)
            unique_filenames.append(filename)

    # Check which file actually exists
    for filename in unique_filenames:
        field_path = os.path.join(mesh_dir, filename)
        if os.path.exists(field_path):
            return field_path

    # Fallback: pick the first .msh file in the directory if available
    try:
        for fname in sorted(os.listdir(mesh_dir)):
            if fname.lower().endswith('.msh'):
                return os.path.join(mesh_dir, fname)
    except (OSError, PermissionError):
        # Directory may not be accessible - will use default filename
        pass

    # If no file found, return the first pattern for error reporting
    suffix = '_mTI.msh' if is_mti else '_TI.msh'
    return os.path.join(mesh_dir, unique_filenames[0] if unique_filenames else f'{montage_name}{suffix}')


def _select_voxel_field_file(m2m_subject_path: str, montage_name: str) -> str:
    """
    Select the appropriate voxel field file based on montage name.

    This implements the same logic as the GUI analyzer_tab.py for voxel field selection.
    """
    from tit.core.paths import PathManager

    subject_id, project_dir = _extract_subject_and_project_dirs(m2m_subject_path)

    # Get base simulation directory using PathManager
    pm = PathManager(project_dir=project_dir)
    base_sim_dir = pm.path_optional("simulation", subject_id=subject_id, simulation_name=montage_name)
    if not base_sim_dir:
        raise FileNotFoundError(f"No simulation directory found for {montage_name}")

    # Check for mTI or TI directory structure
    nifti_dir = None
    if os.path.exists(os.path.join(base_sim_dir, 'mTI', 'niftis')):
        nifti_dir = os.path.join(base_sim_dir, 'mTI', 'niftis')
    elif os.path.exists(os.path.join(base_sim_dir, 'TI', 'niftis')):
        nifti_dir = os.path.join(base_sim_dir, 'TI', 'niftis')

    if not nifti_dir or not os.path.exists(nifti_dir):
        raise FileNotFoundError(f"No nifti directory found for simulation {montage_name}")

    # Prefer grey matter files
    grey_files = [f for f in os.listdir(nifti_dir) if f.startswith('grey_') and not f.endswith('_MNI.nii.gz')]
    if grey_files:
        return os.path.join(nifti_dir, grey_files[0])

    # Fallback to any NIfTI file
    nii_files = [f for f in os.listdir(nifti_dir) if f.endswith('.nii') or f.endswith('.nii.gz')]
    if nii_files:
        return os.path.join(nifti_dir, nii_files[0])

    raise FileNotFoundError(f"No suitable NIfTI field file found in {nifti_dir}")