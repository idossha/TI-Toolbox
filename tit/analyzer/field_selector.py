"""
Field selection utilities for automatic field file determination.

Resolves the correct field file path and SimNIBS field name for a given
subject, simulation, and analysis space (mesh or voxel).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from tit.paths import get_path_manager
from tit import constants as const

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FieldTarget:
    measure: str
    field_path: Path
    field_name: str


def select_field_file(
    subject_id: str,
    simulation: str,
    space: str,
    tissue_type: str = "GM",
    measure: str | None = None,
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
    targets = list_field_targets(subject_id, simulation, space, tissue_type)
    if not targets:
        sim_dir = Path(pm.simulation(subject_id, simulation))
        raise FileNotFoundError(f"No analyzable field targets found in {sim_dir}")
    if measure is not None:
        for target in targets:
            if target.measure == measure:
                return target.field_path, target.field_name
        raise FileNotFoundError(
            f"No field target found for measure {measure!r} in simulation {simulation!r}"
        )
    first = targets[0]
    return first.field_path, first.field_name


def list_field_targets(
    subject_id: str,
    simulation: str,
    space: str,
    tissue_type: str = "GM",
) -> list[FieldTarget]:
    pm = get_path_manager()
    sim_dir = Path(pm.simulation(subject_id, simulation))
    if space not in {"mesh", "voxel"}:
        raise ValueError(f"Unsupported space: {space!r} (expected 'mesh' or 'voxel')")

    targets: list[FieldTarget] = []
    mti_method_dirs = sorted(
        p for p in sim_dir.iterdir() if p.is_dir() and p.name.startswith("mTI_")
    ) if sim_dir.is_dir() else []

    if mti_method_dirs:
        for method_dir in mti_method_dirs:
            measure = method_dir.name.removeprefix("mTI_")
            field_names = [const.FIELD_MTI_MAX]
            if measure == "grossman_ext_directional_am":
                field_names.append(const.FIELD_MTI_AVG)
            for field_name in field_names:
                target = _select_measure_dir(
                    method_dir=method_dir,
                    simulation=simulation,
                    space=space,
                    tissue_type=tissue_type,
                    field_name=field_name,
                    measure=_target_measure_name(measure, field_name),
                )
                if target is not None:
                    targets.append(target)
        return targets

    # Legacy single-folder layout.
    is_mti = (sim_dir / "mTI" / "mesh").is_dir()
    if space == "mesh":
        path, field_name = _select_mesh(sim_dir, simulation, is_mti)
    else:
        path, field_name = _select_voxel(sim_dir, is_mti, tissue_type)
    targets.append(
        FieldTarget(
            measure="mTI" if is_mti else "TI",
            field_path=path,
            field_name=field_name,
        )
    )
    return targets


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _select_measure_dir(
    *,
    method_dir: Path,
    simulation: str,
    space: str,
    tissue_type: str,
    field_name: str,
    measure: str,
) -> FieldTarget | None:
    subdir = "mesh" if space == "mesh" else "niftis"
    target_dir = method_dir / subdir
    if not target_dir.is_dir():
        return None
    if space == "mesh":
        mesh_candidates = sorted(target_dir.glob(f"{simulation}_mTI_{measure}.msh"))
        if not mesh_candidates:
            mesh_candidates = sorted(target_dir.glob(f"{simulation}_mTI*.msh"))
        if not mesh_candidates:
            return None
        return FieldTarget(
            measure=measure,
            field_path=mesh_candidates[0],
            field_name=field_name,
        )
    voxel_path = _select_voxel_from_dir(target_dir, field_name, tissue_type)
    return FieldTarget(measure=measure, field_path=voxel_path, field_name=field_name)


def _target_measure_name(measure: str, field_name: str) -> str:
    if field_name == const.FIELD_MTI_MAX:
        return measure
    return f"{measure}_{field_name}"


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

    return _select_voxel_from_dir(nifti_dir, field_name, tissue_type), field_name


def _select_voxel_from_dir(
    nifti_dir: Path,
    field_name: str,
    tissue_type: str,
) -> Path:
    """Resolve a voxel (.nii.gz) field file from an explicit NIfTI directory."""

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
        # Prefer subject-space TI/TI_Max files (no tissue prefix, no MNI tag).
        for nii in niftis:
            name = nii.name
            if (
                not name.startswith(("grey_", "white_"))
                and "_MNI" not in name
                and field_name in name
            ):
                logger.debug(
                    "Selected voxel field file: %s (field=%s, tissue=%s)",
                    nii,
                    field_name,
                    tissue,
                )
                return nii
    else:
        for nii in niftis:
            name = nii.name
            if (
                name.startswith(preferred_prefix)
                and "_MNI" not in name
                and field_name in name
            ):
                logger.debug(
                    "Selected voxel field file: %s (field=%s, tissue=%s)",
                    nii,
                    field_name,
                    tissue,
                )
                return nii

    # Fall back to tissue/space-compatible files before giving up completely.
    if preferred_prefix is None:
        for nii in niftis:
            name = nii.name
            if not name.startswith(("grey_", "white_")) and "_MNI" not in name:
                logger.debug(
                    "Selected voxel field file (non-field fallback): %s (field=%s, tissue=%s)",
                    nii,
                    field_name,
                    tissue,
                )
                return nii
    else:
        for nii in niftis:
            name = nii.name
            if name.startswith(preferred_prefix) and "_MNI" not in name:
                logger.debug(
                    "Selected voxel field file (non-field fallback): %s (field=%s, tissue=%s)",
                    nii,
                    field_name,
                    tissue,
                )
                return nii

    # Fall back to the first available NIfTI.
    logger.debug(
        "Selected voxel field file (fallback): %s (field=%s, tissue=%s)",
        niftis[0],
        field_name,
        tissue,
    )
    return niftis[0]
