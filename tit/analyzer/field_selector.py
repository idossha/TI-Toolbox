"""Field selection utilities for automatic field file determination.

Resolves the correct field file path and SimNIBS field name for a given
subject, simulation, and analysis space (mesh or voxel).

Public API
----------
select_field_file
    Resolve the field path and SimNIBS field name for a subject/simulation.
simulation_nifti_path
    Locate a named NIfTI of a TI or mTI simulation (used by the group tools).

See Also
--------
tit.analyzer.analyzer : Analyzer class that consumes the resolved paths.
"""

import logging
import re
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

    Detects whether the simulation is TI (2 channels) or mTI (4+) by checking
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
        Default ``None`` resolves :func:`default_field`: ``TI_max`` (TI), ``mTI_max``
        (mTI), or ``hf_peak`` for a carrier-only control.
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
    if field is None and sim_dir.is_dir():
        # Only a carrier-only run changes the default; the envelope keeps None, whose voxel
        # lookup still accepts an older run's unsuffixed NIfTI.
        if default_field(subject_id, simulation) == const.FIELD_HF_PEAK:
            field = const.FIELD_HF_PEAK

    if space == "mesh":
        return _select_mesh(sim_dir, simulation, is_mti, field)
    if space == "voxel":
        return _select_voxel(sim_dir, simulation, is_mti, tissue_type, field)
    raise ValueError(f"Unsupported space: {space!r} (expected 'mesh' or 'voxel')")


def default_field(subject_id: str, simulation: str) -> str:
    """The field an analysis with no field (the app's **Auto**) analyses.

    The envelope -- ``TI_max``, or ``mTI_max`` for an mTI run -- except for a carrier-only
    control (its run record's ``carrier_only``), which has no envelope: there it is
    ``hf_peak``. A run without a record is not carrier-only.

    Raises:
        ValueError: the run record is not JSON.
    """
    import json

    record = Path(get_path_manager().simulation(subject_id, simulation))
    record = record / "documentation" / "config.json"
    if record.is_file() and json.loads(record.read_text()).get("carrier_only") is True:
        return const.FIELD_HF_PEAK
    return (
        const.FIELD_MTI_MAX
        if is_mti_simulation(subject_id, simulation)
        else (const.FIELD_TI_MAX)
    )


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
        ``True`` for an mTI simulation, ``False`` for two-channel TI.
    """
    sim_dir = Path(get_path_manager().simulation(subject_id, simulation))
    return (sim_dir / "mTI" / "mesh").is_dir()


def simulation_nifti_path(
    subject_id: str, simulation: str, nifti_file_pattern: str
) -> Path:
    """The NIfTI *nifti_file_pattern* names in *simulation*, for TI and mTI alike.

    Patterns use the TI spelling (``grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz``,
    read from ``TI/niftis/``). An mTI run writes the same files from its ``<sim>_mTI.msh``
    into ``mTI/niftis/``, and of its fields only the envelope is spelled differently
    (``mTI_max``; ``TI_avg``, ``hf_peak`` and ``hf_rms`` keep their names). So for mTI the
    mesh token before the space (``_TI_subject_`` / ``_TI_MNI_``) becomes ``_mTI_`` and a
    trailing ``_TI_max`` becomes ``_mTI_max``: ``grey_<sim>_mTI_MNI_MNI_mTI_max.nii.gz``,
    ``grey_<sim>_mTI_MNI_MNI_TI_avg.nii.gz``. A pattern already spelled for mTI is unchanged.

    Parameters
    ----------
    subject_id : str
        Subject identifier (without ``sub-`` prefix).
    simulation : str
        Simulation (montage) folder name.
    nifti_file_pattern : str
        File name with ``{subject_id}``/``{simulation_name}`` placeholders.

    Returns
    -------
    pathlib.Path
        Where the file is (or would be); existence is not checked.
    """
    is_mti = is_mti_simulation(subject_id, simulation)
    if is_mti:
        nifti_file_pattern = _MTI_MESH_TOKEN.sub("_mTI_", nifti_file_pattern)
        nifti_file_pattern = _TI_MAX_SUFFIX.sub("_mTI_max", nifti_file_pattern)
    filename = nifti_file_pattern.format(
        subject_id=subject_id, simulation_name=simulation
    )
    sim_dir = Path(get_path_manager().simulation(subject_id, simulation))
    return sim_dir / ("mTI" if is_mti else "TI") / "niftis" / filename


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

#: The ``_TI_`` of the mesh stem, right before mesh2nii's space token.
_MTI_MESH_TOKEN = re.compile(r"_TI_(?=subject_|MNI_)")
#: The envelope field at the end of a TI name; mTI meshes call it ``mTI_max``.
_TI_MAX_SUFFIX = re.compile(r"_TI_max(?=\.nii(?:\.gz)?$)")


def _canonical_field_name(field_name: str, is_mti: bool) -> str:
    """Resolve the TI_max/mTI_max alias pair to the on-disk spelling.

    ``TI_max`` and ``mTI_max`` are the same quantity (modulation depth) — the
    two-channel TI mesh and the mTI mesh just name it differently. Callers
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

    # TI_normal lives in a separate mesh (written by
    # BaseSimulation._write_ti_normal), not the main TI/mTI output mesh.
    if field_name == const.FIELD_TI_NORMAL:
        if is_mti:
            normal_path = sim_dir / "mTI" / "mesh" / f"{simulation}_mTI_normal.msh"
        else:
            normal_path = sim_dir / "TI" / "mesh" / f"{simulation}_normal.msh"
        if not normal_path.exists():
            raise FileNotFoundError(
                f"TI_normal mesh not found: {normal_path}. This simulation "
                "predates TI_normal support for its mode; re-run it to get "
                "the normal-component mesh."
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
    sim_dir: Path, simulation: str, is_mti: bool, tissue_type: str, field: str | None
) -> tuple[Path, str]:
    """Resolve a voxel (.nii.gz) field file.

    The simulator's own name for it comes first: mesh2nii converts
    ``<tissue_><simulation>_<TI|mTI>.msh`` into
    ``<tissue_><simulation>_<TI|mTI>_subject_<field>.nii.gz``, so the file is
    known exactly and no part of a simulation name (``MNI_target``,
    ``grey_matter``) can be mistaken for a space or tissue tag. Folders whose
    files do not carry that name (renamed, or written by an older release)
    fall back to a scan.
    """
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

    preferred_prefix = prefix_map[tissue]
    mode = "mTI" if is_mti else "TI"
    stem = f"{preferred_prefix or ''}{simulation}_{mode}_subject_{field_name}"
    for exact in (nifti_dir / f"{stem}.nii.gz", nifti_dir / f"{stem}.nii"):
        if exact.is_file():
            logger.debug(
                "Selected voxel field file: %s (field=%s, tissue=%s)",
                exact,
                field_name,
                tissue,
            )
            return exact, field_name

    # Every other file named by that same rule is known exactly too -- another
    # tissue, field or space of this simulation -- so it is never a stand-in
    # (``grey_matter_TI_subject_TI_avg`` is the whole-head file of a simulation
    # called ``grey_matter``, not its grey-matter copy). The scan below is for
    # the files that rule does not name.
    known_fields = "|".join(
        re.escape(name) for name in (*const.get_field_names(), "magnE")
    )
    writer_name = re.compile(
        rf"(?:grey_|white_)?{re.escape(simulation)}_{mode}_(?:subject|MNI_MNI)_"
        rf"(?:{known_fields})\.nii(?:\.gz)?"
    )
    niftis = [nii for nii in niftis if not writer_name.fullmatch(nii.name)]

    # The field name must appear as the filename suffix (mesh2nii writes
    # "{base}_{field}.nii.gz"), so distinct fields sharing a mesh (TI_max,
    # TI_avg, hf_peak, ...) aren't conflated. This applies to the implicit
    # default too: without it, a sorted listing would pick "_TI_avg" ahead of
    # "_TI_max" and silently analyze the wrong field under the TI_max label.
    field_suffixes = (f"_{field_name}.nii.gz", f"_{field_name}.nii")

    def _field_matches(name: str) -> bool:
        return name.endswith(field_suffixes)

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
    # a single NIfTI without a field suffix, so take the first such candidate.
    # A file that ends in another field's name (``_TI_avg``, ``_hf_peak``) is
    # that field, never the envelope, so it is not a fallback.
    other_fields = tuple(
        f"_{name}{ext}"
        for name in (*const.get_field_names(), "magnE")
        for ext in (".nii.gz", ".nii")
    )
    unsuffixed = [nii for nii in candidates if not nii.name.endswith(other_fields)]
    if unsuffixed:
        logger.debug(
            "No %s-suffixed NIfTI in %s; falling back to %s",
            field_name,
            nifti_dir,
            unsuffixed[0],
        )
        return unsuffixed[0], field_name
    raise FileNotFoundError(f"No {tissue_type} NIfTI file found in {nifti_dir}")
