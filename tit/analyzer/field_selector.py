"""Field selection utilities for automatic field file determination.

Resolves the correct field file path and SimNIBS field name for a given
subject, simulation, and analysis space (mesh or voxel).

Public API
----------
select_field_file
    Resolve the field path and SimNIBS field name for a subject/simulation.

See Also
--------
tit.analyzer.analyzer : Analyzer class that consumes the resolved paths.
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
    field: str | None = None,
) -> tuple[Path, str]:
    """Return the field file path and SimNIBS field name.

    Detects whether the simulation is TI (2-pair) or mTI (4-pair) by checking
    for the existence of the mTI mesh directory.

    Parameters
    ----------
    subject_id : str
        Subject identifier (without ``sub-`` prefix).
    simulation : str
        Simulation (montage) folder name.
    space : str
        ``"mesh"`` or ``"voxel"``.
    tissue_type : str, optional
        ``"GM"``, ``"WM"``, or ``"both"`` (voxel only). Default ``"GM"``.
    field : str or None, optional
        Field name from ``constants.FIELD_REGISTRY`` (e.g. ``"hf_peak"``).
        Default ``None`` resolves ``TI_max`` (TI) or ``mTI_max`` (mTI).
        ``"TI_max"``/``"mTI_max"`` are treated as aliases for the same
        quantity; the on-disk spelling is always chosen by the detected
        simulation type, regardless of which alias is passed.

    Returns
    -------
    field_path : pathlib.Path
        Resolved absolute path to the field file.
    field_name : str
        SimNIBS field name (e.g. ``"TI_max"``, ``"mTI_max"``).

    Raises
    ------
    FileNotFoundError
        If the expected field file does not exist.
    ValueError
        If *space* is not ``"mesh"``/``"voxel"``, *field* is unknown, or
        ``TI_normal`` is requested in voxel space (it has no NIfTI export).

    See Also
    --------
    Analyzer : Consumes the resolved path to load and analyze fields.
    """
    if field is not None:
        try:
            const.get_field_spec(field)
        except KeyError as exc:
            valid = ", ".join(const.get_field_names())
            raise ValueError(
                f"Unknown field: {field!r}. Valid fields: {valid}."
            ) from exc

    pm = get_path_manager()
    sim_dir = Path(pm.simulation(subject_id, simulation))
    is_mti = is_mti_simulation(subject_id, simulation)

    if space == "mesh":
        return _select_mesh(sim_dir, simulation, is_mti, field)
    if space == "voxel":
        return _select_voxel(sim_dir, is_mti, tissue_type, field)
    raise ValueError(f"Unsupported space: {space!r} (expected 'mesh' or 'voxel')")


def is_mti_simulation(subject_id: str, simulation: str) -> bool:
    """Whether *simulation* is an mTI (multipolar) run.

    The only signal is whether the simulation wrote an ``mTI/mesh/``
    directory; there is no flag stored anywhere else.

    Parameters
    ----------
    subject_id : str
        Subject identifier (without ``sub-`` prefix).
    simulation : str
        Simulation (montage) folder name.

    Returns
    -------
    bool
        ``True`` for an mTI simulation, ``False`` for 2-pair TI.
    """
    sim_dir = Path(get_path_manager().simulation(subject_id, simulation))
    return (sim_dir / "mTI" / "mesh").is_dir()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _canonical_field_name(field_name: str, is_mti: bool) -> str:
    """Resolve the TI_max/mTI_max alias pair to the on-disk spelling.

    ``TI_max`` and ``mTI_max`` are the same quantity (modulation depth) — the
    2-pair TI mesh and the 4-pair/mTI mesh just name it differently. Callers
    (e.g. the GUI) should not need to know which spelling a given simulation
    used; only *is_mti* decides it.
    """
    if field_name in (const.FIELD_TI_MAX, const.FIELD_MTI_MAX):
        return const.FIELD_MTI_MAX if is_mti else const.FIELD_TI_MAX
    return field_name


def _select_mesh(
    sim_dir: Path, simulation: str, is_mti: bool, field: str | None
) -> tuple[Path, str]:
    """Resolve a mesh (.msh) field file."""
    field_name = (
        field
        if field is not None
        else (const.FIELD_MTI_MAX if is_mti else const.FIELD_TI_MAX)
    )
    field_name = _canonical_field_name(field_name, is_mti)

    # TI_normal lives in a separate mesh (written by _calculate_ti_normal),
    # not the main TI/mTI output mesh.
    if field_name == const.FIELD_TI_NORMAL:
        normal_path = sim_dir / "TI" / "mesh" / f"{simulation}_normal.msh"
        if not normal_path.exists():
            raise FileNotFoundError(
                f"TI_normal mesh not found: {normal_path}. TI_normal is only "
                "computed for standard 2-pair TI simulations."
            )
        logger.debug("Selected mesh field file: %s (field=%s)", normal_path, field_name)
        return normal_path, field_name

    if is_mti:
        mesh_path = sim_dir / "mTI" / "mesh" / f"{simulation}_mTI.msh"
    else:
        mesh_path = sim_dir / "TI" / "mesh" / f"{simulation}_TI.msh"

    if not mesh_path.exists():
        high_freq = sim_dir / "high_Frequency"
        hint = ""
        if high_freq.is_dir():
            hint = (
                " The high_Frequency folder exists, but TI/mTI post-processing "
                "outputs are missing. Check the simulation log for post-processing "
                "or NIfTI/mesh conversion errors."
            )
        raise FileNotFoundError(
            f"Mesh field file not found: {mesh_path}.{hint} Expected TI output at "
            f"{sim_dir / 'TI' / 'mesh'} or mTI output at {sim_dir / 'mTI' / 'mesh'}."
        )

    logger.debug("Selected mesh field file: %s (field=%s)", mesh_path, field_name)
    return mesh_path, field_name


def _select_voxel(
    sim_dir: Path, is_mti: bool, tissue_type: str, field: str | None
) -> tuple[Path, str]:
    """Resolve a voxel (.nii.gz) field file."""
    subdir = "mTI" if is_mti else "TI"
    nifti_dir = sim_dir / subdir / "niftis"
    field_name = (
        field
        if field is not None
        else (const.FIELD_MTI_MAX if is_mti else const.FIELD_TI_MAX)
    )
    field_name = _canonical_field_name(field_name, is_mti)

    if field_name == const.FIELD_TI_NORMAL:
        raise ValueError(
            "TI_normal is a surface (mesh) field and is not exported to NIfTI; "
            "select space='mesh' to analyze it."
        )

    if not nifti_dir.is_dir():
        high_freq = sim_dir / "high_Frequency"
        hint = ""
        if high_freq.is_dir():
            hint = (
                " The high_Frequency folder exists, but TI/mTI NIfTI outputs are "
                "missing. Check the simulation log for post-processing or mesh-to-NIfTI "
                "conversion errors."
            )
        raise FileNotFoundError(f"NIfTI directory not found: {nifti_dir}.{hint}")

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

    # The field name must appear as the filename suffix (mesh2nii writes
    # "{base}_{field}.nii.gz"), so distinct fields sharing a mesh (TI_max,
    # TI_avg, hf_peak, ...) aren't conflated. This applies to the implicit
    # default too: without it, a sorted listing would pick "_TI_avg" ahead of
    # "_TI_max" and silently analyze the wrong field under the TI_max label.
    field_suffixes = (f"_{field_name}.nii.gz", f"_{field_name}.nii")

    def _field_matches(name: str) -> bool:
        return name.endswith(field_suffixes)

    preferred_prefix = prefix_map[tissue]
    if preferred_prefix is None:
        # Prefer subject-space, full-field files (no tissue prefix, no MNI tag).
        candidates = (
            nii
            for nii in niftis
            if not nii.name.startswith(("grey_", "white_")) and "_MNI" not in nii.name
        )
    else:
        candidates = (
            nii
            for nii in niftis
            if nii.name.startswith(preferred_prefix) and "_MNI" not in nii.name
        )

    candidates = list(candidates)
    for nii in candidates:
        if _field_matches(nii.name):
            logger.debug(
                "Selected voxel field file: %s (field=%s, tissue=%s)",
                nii,
                field_name,
                tissue,
            )
            return nii, field_name

    if field is not None:
        raise FileNotFoundError(
            f"No {tissue_type} NIfTI file found for field {field_name!r} in {nifti_dir}"
        )
    # Legacy fallback for the implicit default only: older simulations wrote
    # a single NIfTI without a field suffix, so take the first candidate.
    if candidates:
        logger.debug(
            "No %s-suffixed NIfTI in %s; falling back to %s",
            field_name,
            nifti_dir,
            candidates[0],
        )
        return candidates[0], field_name
    raise FileNotFoundError(f"No {tissue_type} NIfTI file found in {nifti_dir}")
