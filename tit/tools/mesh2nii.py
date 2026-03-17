#!/usr/bin/env simnibs_python
"""
Mesh-to-NIfTI conversion using the SimNIBS Python API.

Provides callable functions that wrap ``simnibs.transformations`` so the
simulator pipeline can convert meshes without shelling out to bash scripts.

Public API
----------
msh_to_nifti   – single mesh → subject-space NIfTI
msh_to_mni     – single mesh → MNI-space NIfTI
convert_mesh_dir – batch-convert every mesh in a directory
"""


import logging
import os
import tempfile
from copy import deepcopy

from simnibs import mesh_io, transformations

logger = logging.getLogger(__name__)


def _write_temp_mesh(mesh) -> str:
    """Write *mesh* to a temporary file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".msh")
    os.close(fd)
    mesh_io.write_msh(mesh, path)
    return path


def _filter_mesh_fields(mesh, fields: list[str]):
    """Return a shallow copy of *mesh* containing only the named fields.

    Filters both ``elmdata`` (element data) and ``nodedata`` (node data).
    If a requested field is not present it is silently skipped.
    """
    out = deepcopy(mesh)
    out.elmdata = [d for d in out.elmdata if d.field_name in fields]
    out.nodedata = [d for d in out.nodedata if d.field_name in fields]
    return out


def msh_to_nifti(
    mesh_path: str,
    m2m_dir: str,
    output_path: str,
    fields: list[str] | None = None,
) -> None:
    """Convert a mesh file to subject-space NIfTI.

    Parameters
    ----------
    mesh_path : str
        Path to the ``.msh`` file.
    m2m_dir : str
        Path to the ``m2m_{subject}`` directory (used as reference grid).
    output_path : str
        Output file prefix.  SimNIBS appends the field name
        (e.g. ``prefix_magnE.nii.gz``).
    fields : list[str] | None
        If given, only these fields are written.  Otherwise all fields in the
        mesh are converted.
    """
    mesh = mesh_io.read_msh(mesh_path)
    if fields:
        mesh = _filter_mesh_fields(mesh, fields)
    transformations.interpolate_to_volume(mesh, m2m_dir, output_path)


def msh_to_mni(
    mesh_path: str,
    m2m_dir: str,
    output_path: str,
    fields: list[str] | None = None,
) -> None:
    """Convert a mesh file to MNI-space NIfTI.

    Parameters
    ----------
    mesh_path : str
        Path to the ``.msh`` file.
    m2m_dir : str
        Path to the ``m2m_{subject}`` directory.
    output_path : str
        Output file prefix.  SimNIBS appends the field name
        (e.g. ``prefix_magnE.nii.gz``).
    fields : list[str] | None
        If given, only these fields are written.
    """
    if fields:
        mesh = mesh_io.read_msh(mesh_path)
        mesh = _filter_mesh_fields(mesh, fields)
        mesh_path = _write_temp_mesh(mesh)
    transformations.warp_volume(mesh_path, m2m_dir, output_path)


def convert_mesh_dir(
    mesh_dir: str,
    output_dir: str,
    m2m_dir: str,
    fields: list[str] | None = None,
    skip_patterns: list[str] | None = None,
) -> None:
    """Batch-convert every ``.msh`` file in *mesh_dir* to NIfTI.

    For each mesh two NIfTI sets are produced:

    * ``{basename}_subject_{field}.nii.gz``  – subject space
    * ``{basename}_MNI_{field}.nii.gz``      – MNI space

    Parameters
    ----------
    mesh_dir : str
        Directory containing ``.msh`` files.
    output_dir : str
        Where the NIfTI files are written.
    m2m_dir : str
        Path to the ``m2m_{subject}`` directory.
    fields : list[str] | None
        If given, only these fields are converted.
    skip_patterns : list[str] | None
        Basenames containing any of these substrings are skipped.
        Defaults to ``["normal"]`` (surface-only meshes have no volume
        elements).
    """
    if skip_patterns is None:
        skip_patterns = ["normal"]

    os.makedirs(output_dir, exist_ok=True)

    msh_files = sorted(f for f in os.listdir(mesh_dir) if f.endswith(".msh"))
    if not msh_files:
        logger.warning("No .msh files found in %s", mesh_dir)
        return

    for fname in msh_files:
        base = os.path.splitext(fname)[0]
        if any(p in base for p in skip_patterns):
            logger.debug("Skipping surface mesh: %s", fname)
            continue

        mesh_path = os.path.join(mesh_dir, fname)
        mesh = mesh_io.read_msh(mesh_path)

        # When filtering fields, write a temp mesh for warp_volume
        # (it only accepts file paths, not in-memory mesh objects).
        warp_path = mesh_path
        if fields:
            mesh = _filter_mesh_fields(mesh, fields)
            warp_path = _write_temp_mesh(mesh)

        subject_prefix = os.path.join(output_dir, f"{base}_subject")
        mni_prefix = os.path.join(output_dir, f"{base}_MNI")

        logger.debug("Converting %s → subject space", fname)
        transformations.interpolate_to_volume(mesh, m2m_dir, subject_prefix)

        logger.debug("Converting %s → MNI space", fname)
        transformations.warp_volume(warp_path, m2m_dir, mni_prefix)

        if warp_path != mesh_path:
            os.unlink(warp_path)

    logger.info("NIfTI conversion complete: %s", output_dir)
