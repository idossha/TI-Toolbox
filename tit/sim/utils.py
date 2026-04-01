#!/usr/bin/env simnibs_python
"""
Shared utilities for TI/mTI simulations.

- Montage file I/O   (montage_list.json CRUD)
- Montage loading    (EEG-cap + flex/freehand)
- Directory setup    (BIDS output structure)
- Montage visualization
- Post-processing helpers (field extraction, NIfTI, T1→MNI, file moves)
- Simulation orchestration (sequential + parallel)
"""

import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from typing import Callable

from tit.paths import get_path_manager
from tit import constants as const
from tit.sim.config import (
    Montage,
    SimulationConfig,
    SimulationMode,
)

# ── Montage file I/O ────────────────────────────────────────────────────────────────


def _montage_list_path() -> str:
    pm = get_path_manager()
    return os.path.join(pm.config_dir(), const.FILE_MONTAGE_LIST)


def ensure_montage_file() -> str:
    """Return path to montage_list.json, creating it if absent.

    If the file does not exist, creates it with the default schema
    ``{"nets": {}}``.

    Returns:
        str: Absolute path to the montage_list.json file.
    """
    path = _montage_list_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({"nets": {}}, f, indent=4)
    return path


def load_montage_data() -> dict:
    """Load the full montage_list.json as a dict.

    Returns:
        dict: Parsed JSON with top-level key ``"nets"`` mapping EEG net
            names to their uni/multi polar montage definitions.
    """
    with open(ensure_montage_file()) as f:
        return json.load(f)


def save_montage_data(data: dict) -> None:
    """Write *data* to montage_list.json, overwriting the file.

    Args:
        data: Full montage dict (must contain a ``"nets"`` key).
    """
    with open(ensure_montage_file(), "w") as f:
        json.dump(data, f, indent=4)


def ensure_eeg_net_entry(eeg_net: str) -> None:
    """Ensure an entry for *eeg_net* exists in montage_list.json.

    If the net is not yet present, creates it with empty
    ``uni_polar_montages`` and ``multi_polar_montages`` dicts.

    Args:
        eeg_net: EEG net identifier (e.g. ``"GSN-HydroCel-185.csv"``).
    """
    data = load_montage_data()
    data["nets"].setdefault(
        eeg_net, {"uni_polar_montages": {}, "multi_polar_montages": {}}
    )
    save_montage_data(data)


def upsert_montage(
    *,
    eeg_net: str,
    montage_name: str,
    electrode_pairs: list[list[str]],
    mode: str,
) -> None:
    """Insert or update a montage definition in montage_list.json.

    Creates the EEG net entry if it does not already exist.

    Args:
        eeg_net: EEG net identifier (e.g. ``"GSN-HydroCel-185.csv"``).
        montage_name: Human-readable montage name.
        electrode_pairs: List of electrode pairs, each a two-element list
            of electrode labels (e.g. ``[["E1","E2"],["E3","E4"]]``).
        mode: ``"U"`` for uni-polar montages (2-pair TI) or ``"M"`` for
            multi-polar montages (4-pair mTI).
    """
    data = load_montage_data()
    net = data["nets"].setdefault(
        eeg_net, {"uni_polar_montages": {}, "multi_polar_montages": {}}
    )
    key = "uni_polar_montages" if mode.upper() == "U" else "multi_polar_montages"
    net[key][montage_name] = electrode_pairs
    save_montage_data(data)


def list_montage_names(eeg_net: str, *, mode: str) -> list[str]:
    """List all montage names defined under an EEG net.

    Args:
        eeg_net: EEG net identifier (e.g. ``"GSN-HydroCel-185.csv"``).
        mode: ``"U"`` for uni-polar montage names or ``"M"`` for
            multi-polar montage names.

    Returns:
        list[str]: Sorted montage names. Returns an empty list if the
        net or mode key does not exist.
    """
    data = load_montage_data()
    net = data.get("nets", {}).get(eeg_net, {})
    key = "uni_polar_montages" if mode.upper() == "U" else "multi_polar_montages"
    return sorted(net.get(key, {}).keys())


# ── Montage loading ────────────────────────────────────────────────────────────────


def load_flex_montages(flex_file: str | None = None) -> list[dict]:
    """Load flex/freehand montage definitions from a JSON file.

    Args:
        flex_file: Path to the flex montages JSON file. Falls back to the
            ``FLEX_MONTAGES_FILE`` environment variable if not provided.

    Returns:
        list[dict]: List of raw flex montage dicts. Returns an empty list
        if no file is found.
    """
    if not flex_file:
        flex_file = os.environ.get("FLEX_MONTAGES_FILE")
    if not flex_file or not os.path.exists(flex_file):
        return []
    with open(flex_file) as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return [data.get("montage", data)]


def parse_flex_montage(flex: dict) -> Montage:
    """Convert a raw flex montage dict into a Montage dataclass.

    Args:
        flex: Dict with keys ``"name"``, ``"type"``, and either
            ``"pairs"`` (for ``flex_mapped``) or
            ``"electrode_positions"`` (for ``flex_optimized`` /
            ``freehand_xyz``).

    Returns:
        Montage: Populated Montage instance.

    Raises:
        ValueError: If ``flex["type"]`` is not a recognised montage type.
    """
    name, mtype = flex["name"], flex["type"]
    if mtype == "flex_mapped":
        p = flex["pairs"]
        return Montage(
            name=name,
            mode=Montage.Mode.FLEX_MAPPED,
            electrode_pairs=[(p[0][0], p[0][1]), (p[1][0], p[1][1])],
            eeg_net=flex.get("eeg_net") or "",
        )
    if mtype in ("flex_optimized", "freehand_xyz"):
        ep = flex["electrode_positions"]
        mode = (
            Montage.Mode.FLEX_FREE
            if mtype == "flex_optimized"
            else Montage.Mode.FREEHAND
        )
        return Montage(
            name=name,
            mode=mode,
            electrode_pairs=[(ep[0], ep[1]), (ep[2], ep[3])],
        )
    raise ValueError(f"Unknown flex montage type: {mtype!r}")


def load_montages(
    montage_names: list[str],
    eeg_net: str,
    include_flex: bool = True,
) -> list[Montage]:
    """Load named montages from the project's montage_list.json.

    Reads the montage_list.json file (managed by ``ensure_montage_file``),
    looks up each name under the given EEG net's uni- and multi-polar
    sections, and returns them as ``Montage`` instances. When
    *include_flex* is True, any flex/freehand montages found via
    ``load_flex_montages`` are appended.

    The ``eeg_net`` value determines the montage mode:
    - ``"freehand"`` sets ``Montage.Mode.FREEHAND``
    - ``"flex_mode"`` sets ``Montage.Mode.FLEX_FREE``
    - Any other value (e.g. ``"GSN-HydroCel-185.csv"``) sets
      ``Montage.Mode.NET``

    Args:
        montage_names: Names to look up in the montage file.
        eeg_net: EEG net identifier that selects the sub-dict inside
            ``montage_list.json["nets"]``.
        include_flex: If True, append flex/freehand montages loaded from
            the ``FLEX_MONTAGES_FILE`` environment variable.

    Returns:
        list[Montage]: Resolved montage objects ready for simulation.
    """
    data = load_montage_data()
    net = data.get("nets", {}).get(eeg_net, {})
    uni = net.get("uni_polar_montages", {})
    multi = net.get("multi_polar_montages", {})

    if eeg_net == "freehand":
        mode = Montage.Mode.FREEHAND
    elif eeg_net == "flex_mode":
        mode = Montage.Mode.FLEX_FREE
    else:
        mode = Montage.Mode.NET

    montages = [
        Montage(
            name=n,
            mode=mode,
            electrode_pairs=multi.get(n) or uni[n],
            eeg_net=eeg_net,
        )
        for n in montage_names
        if n in multi or n in uni
    ]

    if include_flex:
        for flex in load_flex_montages():
            montages.append(parse_flex_montage(flex))

    return montages


# ── Directory setup ────────────────────────────────────────────────────────────────


def setup_montage_directories(montage_dir: str, mode: SimulationMode) -> dict[str, str]:
    """Create the BIDS-compliant output directory tree for one montage.

    Creates sub-directories for high-frequency fields, TI fields, meshes,
    NIfTIs, surface overlays, montage images, and documentation. For mTI
    mode, additional ``mTI/`` sub-directories are created.

    Args:
        montage_dir: Root output directory for this montage.
        mode: ``SimulationMode.TI`` or ``SimulationMode.MTI``.

    Returns:
        dict[str, str]: Mapping of logical names (e.g. ``"ti_mesh"``,
        ``"hf_niftis"``) to their absolute paths.
    """
    dirs = {
        "montage_dir": montage_dir,
        "hf_dir": os.path.join(montage_dir, "high_Frequency"),
        "hf_mesh": os.path.join(montage_dir, "high_Frequency", "mesh"),
        "hf_niftis": os.path.join(montage_dir, "high_Frequency", "niftis"),
        "hf_analysis": os.path.join(montage_dir, "high_Frequency", "analysis"),
        "ti_mesh": os.path.join(montage_dir, "TI", "mesh"),
        "ti_niftis": os.path.join(montage_dir, "TI", "niftis"),
        "ti_surfaces": os.path.join(montage_dir, "TI", "mesh", "surfaces"),
        "ti_surface_overlays": os.path.join(montage_dir, "TI", "surface_overlays"),
        "ti_montage_imgs": os.path.join(montage_dir, "TI", "montage_imgs"),
        "documentation": os.path.join(montage_dir, "documentation"),
    }
    if mode == SimulationMode.MTI:
        dirs["mti_mesh"] = os.path.join(montage_dir, "mTI", "mesh")
        dirs["mti_surfaces"] = os.path.join(montage_dir, "mTI", "mesh", "surfaces")
        dirs["mti_niftis"] = os.path.join(montage_dir, "mTI", "niftis")
        dirs["mti_montage_imgs"] = os.path.join(montage_dir, "mTI", "montage_imgs")

    for path in dirs.values():
        os.makedirs(path, exist_ok=True)
    return dirs


# ── Montage visualization ───────────────────────────────────────────────────────────────


def run_montage_visualization(
    montage_name: str,
    simulation_mode: SimulationMode,
    eeg_net: str,
    output_dir: str,
    logger,
    electrode_pairs: list | None = None,
) -> None:
    """Render a 2-D montage diagram for an EEG-cap montage.

    Skips rendering for freehand and flex_mode montages (no cap layout).

    Args:
        montage_name: Name of the montage to visualize.
        simulation_mode: ``SimulationMode.TI`` or ``SimulationMode.MTI``.
        eeg_net: EEG net identifier. Visualization is skipped when this
            is ``"freehand"`` or ``"flex_mode"``.
        output_dir: Directory where the image file is saved.
        logger: Logger instance for status messages.
        electrode_pairs: Electrode pair list to annotate on the diagram.
            Defaults to an empty list.
    """
    if eeg_net in ("freehand", "flex_mode"):
        logger.info(f"Skipping montage visualization for {eeg_net} mode")
        return

    from tit.tools.montage_visualizer import visualize_montage

    sim_mode_str = "U" if simulation_mode == SimulationMode.TI else "M"
    visualize_montage(
        montage_name=montage_name,
        electrode_pairs=electrode_pairs or [],
        eeg_net=eeg_net,
        output_dir=output_dir,
        sim_mode=sim_mode_str,
    )


# ── Simulation config file ────────────────────────────────────────────────────────────────


def create_simulation_config_file(
    config: SimulationConfig,
    montage: Montage,
    documentation_dir: str,
    logger,
) -> None:
    """Write a JSON snapshot of the simulation configuration to disk.

    Serialises subject ID, montage details, electrode geometry, mapping
    options, and a timestamp into ``config.json`` inside *documentation_dir*.

    Args:
        config: The full simulation configuration.
        montage: The specific montage being simulated.
        documentation_dir: Directory to write ``config.json`` into.
        logger: Logger instance for status messages.
    """
    path = os.path.join(documentation_dir, "config.json")
    data = {
        "subject_id": config.subject_id,
        "simulation_name": montage.name,
        "simulation_mode": montage.simulation_mode.value,
        "montage_mode": montage.mode.value,
        "eeg_net": montage.eeg_net,
        "conductivity": config.conductivity,
        "electrode_pairs": montage.electrode_pairs,
        "is_xyz_montage": montage.is_xyz,
        "intensities": config.intensities,
        "electrode_geometry": {
            "shape": config.electrode_shape,
            "dimensions": config.electrode_dimensions,
            "gel_thickness": config.gel_thickness,
            "rubber_thickness": config.rubber_thickness,
        },
        "mapping_options": {
            "map_to_surf": config.map_to_surf,
            "map_to_vol": config.map_to_vol,
            "map_to_mni": config.map_to_mni,
            "map_to_fsavg": config.map_to_fsavg,
        },
        "created_at": datetime.now().isoformat(),
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Config written: {path}")


# ── Shared post-processing helpers ───────────────────────────────────────────────────────────


def extract_fields(
    input_mesh: str,
    output_dir: str,
    base_name: str,
    m2m_dir: str,
    subject_id: str,
    logger,
) -> None:
    """Extract grey-matter and white-matter meshes from a full-head mesh.

    Crops the input mesh by SimNIBS tissue tags (tag 2 = GM, tag 1 = WM)
    and writes the results as separate ``.msh`` files.

    Args:
        input_mesh: Path to the full-head ``.msh`` file.
        output_dir: Directory to write the cropped meshes into.
        base_name: Stem used for output filenames (e.g.
            ``"grey_{base_name}.msh"``).
        m2m_dir: Path to the subject's m2m directory (unused here but
            kept for interface consistency).
        subject_id: Subject identifier (unused here but kept for
            interface consistency).
        logger: Logger instance for status messages.
    """
    from simnibs import mesh_io

    full_mesh = mesh_io.read_msh(input_mesh)
    gm_out = os.path.join(output_dir, f"grey_{base_name}.msh")
    wm_out = os.path.join(output_dir, f"white_{base_name}.msh")
    mesh_io.write_msh(full_mesh.crop_mesh(tags=[2]), gm_out)
    mesh_io.write_msh(full_mesh.crop_mesh(tags=[1]), wm_out)


def transform_to_nifti(
    mesh_dir: str,
    output_dir: str,
    subject_id: str,
    m2m_dir: str,
    logger,
    fields: list[str] | None = None,
    skip_patterns: list[str] | None = None,
) -> None:
    """Convert mesh files in a directory to NIfTI volumes.

    Delegates to ``tit.tools.mesh2nii.convert_mesh_dir`` which transforms
    each ``.msh`` file into subject-space (and optionally MNI-space)
    NIfTI images.

    Args:
        mesh_dir: Directory containing ``.msh`` files to convert.
        output_dir: Directory to write the resulting NIfTI files.
        subject_id: Subject identifier (unused here but kept for
            interface consistency).
        m2m_dir: Path to the subject's m2m directory, used for
            coordinate transforms.
        logger: Logger instance for status messages.
        fields: Mesh field names to convert. Converts all fields if None.
        skip_patterns: Filename patterns to skip during conversion.
    """
    from tit.tools.mesh2nii import convert_mesh_dir

    convert_mesh_dir(
        mesh_dir=mesh_dir,
        output_dir=output_dir,
        m2m_dir=m2m_dir,
        fields=fields,
        skip_patterns=skip_patterns,
    )


def convert_t1_to_mni(m2m_dir: str, subject_id: str, logger) -> None:
    """Convert the subject's T1 image to MNI space via ``subject2mni``.

    Calls the SimNIBS ``subject2mni`` CLI tool. Logs a warning (but does
    not raise) if the conversion fails.

    Args:
        m2m_dir: Path to the subject's m2m directory containing
            ``T1.nii.gz``.
        subject_id: Subject identifier, used for the output filename.
        logger: Logger instance for status/warning messages.
    """
    t1 = os.path.join(m2m_dir, "T1.nii.gz")
    out = os.path.join(m2m_dir, f"T1_{subject_id}")
    result = subprocess.run(
        ["subject2mni", "-i", t1, "-m", m2m_dir, "-o", out],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        logger.warning(f"T1 MNI conversion warning: {result.stderr}")


def safe_move(src: str, dest: str) -> None:
    """Move a file or directory from *src* to *dest*.

    Args:
        src: Source path.
        dest: Destination path.
    """
    shutil.move(src, dest)


# ── Simulation Orchestration ────────────────────────────────────────────────────────────────


def run_simulation(
    config: SimulationConfig,
    logger=None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[dict]:
    """Run TI or mTI simulations for every montage in *config*.

    For each montage in ``config.montages``, this function:

    1. Auto-detects TI (2 pairs) vs mTI (4+ pairs) from the montage.
    2. Builds a SimNIBS SESSION with electrode geometry and conductivity
       settings from *config*.
    3. Runs the FEM solver to compute electric-field distributions.
    4. Computes temporal-interference envelope fields (TI_max, TI_normal)
       and, for mTI, the multi-channel superposition.
    5. Writes output meshes, surface overlays, and NIfTIs to the
       BIDS-compliant simulation directory.

    Montages are processed sequentially. If no *logger* is provided, a
    file logger is created under the subject's log directory.

    Args:
        config: Full simulation configuration including subject ID,
            montage list, electrode geometry, and conductivity model.
        logger: Logger instance. If None, a file logger is created
            automatically in the subject's BIDS logs directory.
        progress_callback: Optional callback invoked before each montage
            as ``callback(current_index, total, montage_name)`` and once
            more with ``(total, total, "Complete")`` when finished.

    Returns:
        list[dict]: One result dict per montage with keys
        ``montage_name``, ``montage_type``, ``status``, and
        ``output_mesh``.
    """
    if logger is None:
        pm = get_path_manager()
        log_dir = pm.logs(config.subject_id)
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(
            log_dir, f'Simulator_{time.strftime("%Y%m%d_%H%M%S")}.log'
        )
        logger = _make_file_logger("tit.sim", log_file)

    pm = get_path_manager()
    simulation_dir = pm.simulations(config.subject_id)

    from tit.sim.TI import TISimulation
    from tit.sim.mTI import mTISimulation

    montages = config.montages
    results = []
    total = len(montages)
    for idx, montage in enumerate(montages):
        logger.info(
            f"[{idx+1}/{total}] {montage.simulation_mode.value}: {montage.name}"
        )
        if progress_callback:
            progress_callback(idx, total, montage.name)
        cls = (
            TISimulation
            if montage.simulation_mode == SimulationMode.TI
            else mTISimulation
        )
        results.append(cls(config, montage, logger).run(simulation_dir))
    if progress_callback:
        progress_callback(total, total, "Complete")
    return results


def _make_file_logger(
    name: str, log_file: str, level: int = logging.INFO
) -> logging.Logger:
    from tit.logger import add_file_handler

    add_file_handler(log_file, level=logging.getLevelName(level), logger_name=name)
    # Also capture simnibs output in the same log file
    add_file_handler(log_file, logger_name="simnibs")
    return logging.getLogger(name)
