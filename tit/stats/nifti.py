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


# ==============================================================================
# GRID CONSISTENCY
# ==============================================================================

#: Tolerances for declaring two NIfTI grids "the same space".  Voxelwise group
#: statistics compare voxel *i* across subjects, which is only meaningful if
#: voxel *i* is the same point of the world in every image.  Equal ``shape``
#: alone does not guarantee that: two images can share a shape and disagree on
#: origin, orientation, voxel size or handedness.
AFFINE_ROTATION_ATOL = 1e-4  # unitless (direction-cosine * zoom entries, mm)
AFFINE_TRANSLATION_ATOL = 1e-3  # mm


def _check_same_grid(
    subject_id,
    filepath,
    shape,
    affine,
    ref_shape,
    ref_affine,
    ref_path,
):
    """Raise ``ValueError`` unless *affine*/*shape* match the reference grid.

    v2.x stacked any images that happened to share a shape and silently kept
    only the first affine, so a subject in a differently-oriented (or
    differently-handed) space was analysed as if it were aligned.  Errors here
    name the offending subject and file so the mismatch can be fixed at the
    source (re-run the MNI normalisation, or resample to a common reference).
    """
    if tuple(shape) != tuple(ref_shape):
        raise ValueError(
            f"Subject {subject_id} has shape {tuple(shape)}, but the group "
            f"reference has shape {tuple(ref_shape)}.\n"
            f"  subject:   {filepath}\n"
            f"  reference: {ref_path}\n"
            "All subjects must be on a common voxel grid; resample them to a "
            "shared reference before running group statistics."
        )

    affine = np.asarray(affine, dtype=np.float64)
    ref_affine = np.asarray(ref_affine, dtype=np.float64)
    rot_ok = np.allclose(affine[:3, :3], ref_affine[:3, :3], atol=AFFINE_ROTATION_ATOL)
    trans_ok = np.allclose(
        affine[:3, 3], ref_affine[:3, 3], atol=AFFINE_TRANSLATION_ATOL
    )
    if rot_ok and trans_ok:
        return

    detail = []
    if not rot_ok:
        detail.append("orientation/voxel size")
        if np.sign(np.linalg.det(affine[:3, :3])) != np.sign(
            np.linalg.det(ref_affine[:3, :3])
        ):
            detail.append("handedness (left/right flip!)")
    if not trans_ok:
        offset = affine[:3, 3] - ref_affine[:3, 3]
        detail.append(
            f"origin (offset {offset[0]:+.3f}, {offset[1]:+.3f}, {offset[2]:+.3f} mm)"
        )
    raise ValueError(
        f"Subject {subject_id} is on a different voxel grid from the group "
        f"reference: {', '.join(detail)}.\n"
        f"  subject affine:\n{affine}\n"
        f"  reference affine:\n{ref_affine}\n"
        f"  subject:   {filepath}\n"
        f"  reference: {ref_path}\n"
        "Equal array shapes are not enough -- voxelwise statistics compare "
        "voxel i across subjects, so voxel i must be the same anatomical "
        "location in every image. Resample the subjects to a common reference."
    )


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
    if len(subject_configs) == 0:
        raise ValueError("No subjects could be loaded successfully")

    data_4d = None
    subject_ids: list[str] = []
    template_affine = None
    template_header = None
    reference_path = None

    for index, config in enumerate(subject_configs):
        subject_id = config["subject_id"]
        simulation_name = config["simulation_name"]

        data, img, filepath = load_subject_nifti_ti_toolbox(
            subject_id, simulation_name, nifti_file_pattern, dtype=dtype
        )

        if data_4d is None:
            template_affine = img.affine.copy()
            template_header = img.header.copy()
            reference_path = filepath
            # Preallocate: np.stack + astype on a list of N volumes peaks at
            # ~3x the final array; writing each subject straight into the
            # output keeps it at 1x + one volume.
            data_4d = np.empty(data.shape + (len(subject_configs),), dtype=dtype)
        else:
            _check_same_grid(
                subject_id,
                filepath,
                data.shape,
                img.affine,
                data_4d.shape[:-1],
                template_affine,
                reference_path,
            )

        data_4d[..., index] = data
        subject_ids.append(subject_id)

        # Clear the image object to free memory
        del img, data

    # Recreate minimal template image
    template_img = nib.Nifti1Image(data_4d[..., 0], template_affine, template_header)

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
