#!/usr/bin/env simnibs_python
"""TI-Toolbox NIfTI loading helpers for statistical analysis.

Convenience wrappers around ``nibabel`` that resolve paths through
:func:`tit.paths.get_path_manager` and return arrays ready for
voxelwise group comparison or correlation pipelines.

Public API
----------
load_subject_nifti_ti_toolbox
    Load a single subject's NIfTI from the BIDS simulation tree.
load_group_data_ti_toolbox
    Stack multiple subjects into a 4-D array.
load_grouped_subjects_ti_toolbox
    Load multiple subjects organized by named groups.

See Also
--------
tit.stats.comparison : Voxelwise group comparison pipeline.
tit.stats.correlation : Voxelwise correlation pipeline.
"""

import os
import gc
import numpy as np
import nibabel as nib

# Import TI-Toolbox core modules
from tit.paths import get_path_manager

# ==============================================================================
# TI-TOOLBOX INTEGRATED LOADING
# ==============================================================================


def load_subject_nifti_ti_toolbox(
    subject_id: str,
    simulation_name: str,
    nifti_file_pattern: str = "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",
    dtype=np.float32,
) -> tuple[np.ndarray, nib.Nifti1Image, str]:
    """Load a single subject's NIfTI file from TI-Toolbox BIDS structure.

    Parameters
    ----------
    subject_id : str
        Subject identifier (e.g. ``'070'``).
    simulation_name : str
        Simulation folder name (e.g. ``'ICP_RHIPPO'``).
    nifti_file_pattern : str, optional
        Filename pattern with ``{subject_id}`` / ``{simulation_name}``
        placeholders.
    dtype : numpy dtype, optional
        Data type for the returned array.  Default is ``np.float32``.

    Returns
    -------
    data : numpy.ndarray
        3-D array of voxel values.
    img : nibabel.Nifti1Image
        The loaded NIfTI image (useful for affine / header).
    filepath : str
        Absolute path of the loaded file.

    Raises
    ------
    FileNotFoundError
        If the resolved NIfTI path does not exist.
    """
    pm = get_path_manager()

    nifti_dir = os.path.join(
        pm.simulation(subject_id, simulation_name),
        "TI",
        "niftis",
    )

    # Format the filename pattern
    filename = nifti_file_pattern.format(
        subject_id=subject_id, simulation_name=simulation_name
    )
    filepath = os.path.join(nifti_dir, filename)

    # Load the file (inline basic loading)
    if not os.path.exists(filepath):
        # Provide extra context to make debugging path/layout issues easier
        if os.path.isdir(nifti_dir):
            try:
                existing = sorted(os.listdir(nifti_dir))
            except OSError:
                existing = []
            preview = existing[:20]
            suffix = ""
            if len(existing) > len(preview):
                suffix = f" (showing first {len(preview)} of {len(existing)})"
            raise FileNotFoundError(
                f"NIfTI file not found: {filepath}. "
                f"Directory exists: {nifti_dir}. "
                f"Files in directory: {preview}{suffix}"
            )
        raise FileNotFoundError(f"NIfTI file not found: {filepath}")

    img = nib.load(filepath)
    data = img.get_fdata(dtype=dtype)

    # Ensure 3D data (squeeze out extra dimensions if present)
    while data.ndim > 3:
        data = np.squeeze(data, axis=-1)

    return data, img, filepath


def load_group_data_ti_toolbox(
    subject_configs: list[dict],
    nifti_file_pattern: str = "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",
    dtype=np.float32,
) -> tuple[np.ndarray, nib.Nifti1Image, list[str]]:
    """Load and stack multiple subjects into a 4-D array.

    Parameters
    ----------
    subject_configs : list of dict
        Each dict must contain ``'subject_id'`` and ``'simulation_name'``
        keys (e.g. ``{'subject_id': '070', 'simulation_name': 'ICP_RHIPPO'}``).
    nifti_file_pattern : str, optional
        Filename pattern forwarded to :func:`load_subject_nifti_ti_toolbox`.
    dtype : numpy dtype, optional
        Data type for the returned arrays.  Default is ``np.float32``.

    Returns
    -------
    data_4d : numpy.ndarray
        Shape ``(X, Y, Z, n_subjects)``.
    template_img : nibabel.Nifti1Image
        Image from the first subject (affine / header reference).
    subject_ids : list of str
        Subject identifiers in the same order as the last axis of
        *data_4d*.

    Raises
    ------
    ValueError
        If no subjects could be loaded.
    """
    data_list = []
    subject_ids = []
    template_img = None
    template_affine = None
    template_header = None

    for config in subject_configs:
        subject_id = config["subject_id"]
        simulation_name = config["simulation_name"]

        data, img, filepath = load_subject_nifti_ti_toolbox(
            subject_id, simulation_name, nifti_file_pattern, dtype=dtype
        )

        # Store template image from first subject
        if template_img is None:
            template_img = img
            template_affine = img.affine.copy()
            template_header = img.header.copy()

        data_list.append(data)
        subject_ids.append(subject_id)

        # Clear the image object to free memory
        del img

    if len(data_list) == 0:
        raise ValueError("No subjects could be loaded successfully")

    # Stack into 4D array
    data_4d = np.stack(data_list, axis=-1).astype(dtype)

    # Recreate minimal template image
    template_img = nib.Nifti1Image(data_4d[..., 0], template_affine, template_header)

    # Clean up
    del data_list
    gc.collect()

    return data_4d, template_img, subject_ids


def load_grouped_subjects_ti_toolbox(
    subject_configs: list[dict],
    nifti_file_pattern: str = "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",
    dtype=np.float32,
) -> tuple[dict[str, np.ndarray], nib.Nifti1Image, dict[str, list[str]]]:
    """Load subjects organized by named groups.

    Each config dict must include a ``'group'`` key in addition to the
    fields required by :func:`load_group_data_ti_toolbox`.  Configs
    without a ``'group'`` key are assigned to the ``'default'`` group.

    Parameters
    ----------
    subject_configs : list of dict
        Each dict must contain ``'subject_id'``, ``'simulation_name'``,
        and ``'group'`` (e.g. ``'Responders'``).
    nifti_file_pattern : str, optional
        Filename pattern forwarded to :func:`load_subject_nifti_ti_toolbox`.
    dtype : numpy dtype, optional
        Data type for the returned arrays.  Default is ``np.float32``.

    Returns
    -------
    groups_data : dict of str to numpy.ndarray
        Mapping from group name to a 4-D array ``(X, Y, Z, n_subjects)``.
    template_img : nibabel.Nifti1Image
        Image from the first loaded subject.
    groups_ids : dict of str to list of str
        Mapping from group name to ordered list of subject identifiers.
    """
    # Organize configs by group
    groups = {}
    for config in subject_configs:
        group_name = config.get("group", "default")
        if group_name not in groups:
            groups[group_name] = []
        groups[group_name].append(config)

    # Load each group
    groups_data = {}
    groups_ids = {}
    template_img = None

    for group_name, group_configs in groups.items():
        data_4d, img, subject_ids = load_group_data_ti_toolbox(
            group_configs, nifti_file_pattern, dtype=dtype
        )

        groups_data[group_name] = data_4d
        groups_ids[group_name] = subject_ids

        # Use first group's image as template
        if template_img is None:
            template_img = img

    return groups_data, template_img, groups_ids
