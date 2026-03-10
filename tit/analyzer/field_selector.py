"""
Field selection utilities for automatic field file determination.

Resolves the correct field file path and SimNIBS field name for a given
subject, simulation, and analysis space (mesh or voxel).
"""

import logging
from pathlib import Path

from tit.paths import get_path_manager
from tit import constants as const

logger = logging.getLogger(__name__)


def select_field_file(
    subject_id: str,
    simulation: str,
    space: str,
    tissue_type: str = "GM",
) -> tuple[Path, str]:
    """Return (field_path, field_name) for a given subject/simulation/space.

    Detects whether the simulation is TI (2-pair) or mTI (4-pair) by checking
    for the existence of the mTI mesh directory.

    Args:
        subject_id: Subject identifier (without ``sub-`` prefix).
        simulation: Simulation (montage) folder name.
        space: ``"mesh"`` or ``"voxel"``.

    Returns:
        Tuple of (resolved field path, SimNIBS field name).

    Raises:
        FileNotFoundError: If the expected field file does not exist.
        ValueError: If *space* is not ``"mesh"`` or ``"voxel"``.
    """
    pm = get_path_manager()
    sim_dir = Path(pm.simulation(subject_id, simulation))
    is_mti = (sim_dir / "mTI" / "mesh").is_dir()

    if space == "mesh":
        return _select_mesh(sim_dir, simulation, is_mti)
    if space == "voxel":
        return _select_voxel(sim_dir, is_mti, tissue_type)
    raise ValueError(f"Unsupported space: {space!r} (expected 'mesh' or 'voxel')")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _select_mesh(sim_dir: Path, simulation: str, is_mti: bool) -> tuple[Path, str]:
    """Resolve a mesh (.msh) field file."""
    if is_mti:
        mesh_path = sim_dir / "mTI" / "mesh" / f"{simulation}_mTI.msh"
        field_name = const.FIELD_MTI_MAX
    else:
        mesh_path = sim_dir / "TI" / "mesh" / f"{simulation}_TI.msh"
        field_name = const.FIELD_TI_MAX

    if not mesh_path.exists():
        raise FileNotFoundError(f"Mesh field file not found: {mesh_path}")

    logger.debug("Selected mesh field file: %s (field=%s)", mesh_path, field_name)
    return mesh_path, field_name


def _select_voxel(sim_dir: Path, is_mti: bool, tissue_type: str) -> tuple[Path, str]:
    """Resolve a voxel (.nii.gz) field file."""
    subdir = "mTI" if is_mti else "TI"
    nifti_dir = sim_dir / subdir / "niftis"
    field_name = const.FIELD_MTI_MAX if is_mti else const.FIELD_TI_MAX

    if not nifti_dir.is_dir():
        raise FileNotFoundError(f"NIfTI directory not found: {nifti_dir}")

    niftis = sorted(
        p
        for p in nifti_dir.iterdir()
        if p.name.endswith(".nii.gz") or p.name.endswith(".nii")
    )

    if not niftis:
        raise FileNotFoundError(f"No NIfTI files found in {nifti_dir}")

    tissue = str(tissue_type or "GM").strip().lower()
    prefix_map = {"gm": "grey_", "wm": "white_", "both": None}
    if tissue not in prefix_map:
        raise ValueError(
            f"Unsupported tissue_type: {tissue_type!r} (expected 'GM', 'WM', or 'both')"
        )

    preferred_prefix = prefix_map[tissue]
    if preferred_prefix is None:
        # Prefer subject-space, full-field files (no tissue prefix, no MNI tag).
        for nii in niftis:
            name = nii.name
            if not name.startswith(("grey_", "white_")) and "_MNI" not in name:
                logger.debug(
                    "Selected voxel field file: %s (field=%s, tissue=%s)",
                    nii,
                    field_name,
                    tissue,
                )
                return nii, field_name
    else:
        for nii in niftis:
            name = nii.name
            if name.startswith(preferred_prefix) and "_MNI" not in name:
                logger.debug(
                    "Selected voxel field file: %s (field=%s, tissue=%s)",
                    nii,
                    field_name,
                    tissue,
                )
                return nii, field_name

    # Fall back to the first available NIfTI.
    logger.debug(
        "Selected voxel field file (fallback): %s (field=%s, tissue=%s)",
        niftis[0],
        field_name,
        tissue,
    )
    return niftis[0], field_name
