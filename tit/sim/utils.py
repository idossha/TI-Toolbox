#!/usr/bin/env simnibs_python
"""Shared utilities for TI/mTI simulations.

This module provides all non-class helpers consumed by the simulation
package:

* **Montage file I/O** -- CRUD operations on ``montage_list.json``.
* **Montage loading** -- build ``Montage`` objects from ``montage_list.json``.
* **Directory setup** -- create the BIDS output directory tree.
* **Montage visualisation** -- render 2-D montage diagrams.
* **Post-processing helpers** -- field extraction, NIfTI conversion,
  T1-to-MNI transform, file moves.
* **Simulation orchestration** -- sequential montage execution.

Public API
----------
run_simulation
    Execute simulations for every montage in a configuration.
load_montages
    Load named montages from ``montage_list.json``.
list_montage_names
    List montage names defined under an EEG net.
load_montage_data
    Load the full ``montage_list.json`` as a dict.
save_montage_data
    Write a montage dict to ``montage_list.json``.
ensure_montage_file
    Return (and optionally create) the ``montage_list.json`` path.
upsert_montage
    Insert or update a montage definition.

See Also
--------
tit.sim.config : Dataclasses consumed by the functions here.
tit.sim.base : Base class that calls directory-setup and viz helpers.
tit.sim.TI : 2-pair TI post-processing that uses extract/transform helpers.
tit.sim.mTI : N-pair mTI post-processing that uses extract/transform helpers.
"""

import glob
import json
import logging
import math
import os
import shutil
import subprocess
import time
import csv
from datetime import datetime
from typing import Callable

from tit.paths import PathManager, get_path_manager
from tit import constants as const
from tit.sim.config import (
    Montage,
    SimulationConfig,
    SimulationMode,
)

# ── Montage file I/O ────────────────────────────────────────────────────────────────


def _montage_list_path(pm: PathManager | None = None) -> str:
    """Return the absolute path to ``montage_list.json``."""
    pm = pm if pm is not None else get_path_manager()
    return os.path.join(pm.config_dir(), const.FILE_MONTAGE_LIST)


def ensure_montage_file(*, pm: PathManager | None = None) -> str:
    """Return the path to ``montage_list.json``, creating it if absent.

    If the file does not exist, creates it with the default schema
    ``{"nets": {}}``.

    Returns
    -------
    str
        Absolute path to the ``montage_list.json`` file.

    See Also
    --------
    load_montage_data : Read the file returned by this function.
    save_montage_data : Write data to the file returned by this function.
    """
    path = _montage_list_path(pm)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({"nets": {}}, f, indent=4)
    return path


def load_montage_data(*, pm: PathManager | None = None) -> dict:
    """Load the full ``montage_list.json`` as a dict.

    Returns
    -------
    dict
        Parsed JSON with top-level key ``"nets"`` mapping EEG net
        names to their uni/multi polar montage definitions.

    See Also
    --------
    save_montage_data : Write the dict back to disk.
    ensure_montage_file : Guarantees the file exists before reading.
    """
    with open(ensure_montage_file(pm=pm)) as f:
        return json.load(f)


def save_montage_data(data: dict, *, pm: PathManager | None = None) -> None:
    """Write *data* to ``montage_list.json``, overwriting the file.

    Parameters
    ----------
    data : dict
        Full montage dict (must contain a ``"nets"`` key).

    See Also
    --------
    load_montage_data : Read the data back after saving.
    """
    with open(ensure_montage_file(pm=pm), "w") as f:
        json.dump(data, f, indent=4)


def upsert_montage(
    *,
    eeg_net: str,
    montage_name: str,
    electrode_pairs: list[list[str]],
    mode: str,
    pm: PathManager | None = None,
) -> None:
    """Insert or update a montage definition in ``montage_list.json``.

    Creates the EEG net entry if it does not already exist.

    Parameters
    ----------
    eeg_net : str
        EEG-net CSV filename exactly as it appears in the subject's
        ``eeg_positions`` folder, e.g. ``"GSN-HydroCel-185.csv"`` or
        ``"EEG10-10_UI_Jurak_2007.csv"``.  Created in the file if absent.
    montage_name : str
        Montage name; an existing montage of the same name under this net is
        replaced, whichever polarity it was saved under (one name, one
        ``Simulations/<name>/`` folder).
    electrode_pairs : list[list[str]]
        Electrode pairs, each a two-element list of labels from that net
        (e.g. ``[["E010", "E011"], ["E012", "E013"]]``).  Two pairs for
        ``mode="U"``, four (or more, even) for ``mode="M"``.
    mode : str
        ``"U"`` for uni-polar montages (2-pair TI) or ``"M"`` for
        multi-polar montages (4+-pair mTI).  Case-insensitive; anything
        other than ``"U"`` is treated as ``"M"``.
    pm : PathManager or None, optional
        Path manager to locate the project; ``None`` uses the global one.

    Returns
    -------
    None
        The file is rewritten in place.

    Examples
    --------
    >>> from tit.sim import upsert_montage, list_montage_names
    >>> upsert_montage(
    ...     eeg_net="GSN-HydroCel-185.csv",
    ...     montage_name="L_Insula",
    ...     electrode_pairs=[["E010", "E011"], ["E012", "E013"]],
    ...     mode="U",
    ... )  # doctest: +SKIP
    >>> list_montage_names("GSN-HydroCel-185.csv", mode="U")  # doctest: +SKIP
    ['L_Insula']

    See Also
    --------
    list_montage_names : List montage names after upserting.
    load_montages : Load upserted montages as ``Montage`` objects.
    """
    data = load_montage_data(pm=pm)
    net = data["nets"].setdefault(
        eeg_net, {"uni_polar_montages": {}, "multi_polar_montages": {}}
    )
    key = "uni_polar_montages" if mode.upper() == "U" else "multi_polar_montages"
    other = (
        "multi_polar_montages" if key == "uni_polar_montages" else "uni_polar_montages"
    )
    # One name is one Simulations/<name>/ folder, and load_montages refuses a name in both.
    net.get(other, {}).pop(montage_name, None)
    net[key][montage_name] = electrode_pairs
    save_montage_data(data, pm=pm)


def list_montage_names(eeg_net: str, *, mode: str) -> list[str]:
    """List all montage names defined under an EEG net.

    These are exactly the names :func:`load_montages` can resolve for
    that net; a name not in this list is silently skipped by
    :func:`load_montages`.

    Parameters
    ----------
    eeg_net : str
        EEG-net CSV filename (e.g. ``"GSN-HydroCel-185.csv"``,
        ``"EEG10-10_UI_Jurak_2007.csv"``), the key under
        ``montage_list.json["nets"]``.
    mode : str
        ``"U"`` for uni-polar (2-pair TI) montage names or ``"M"`` for
        multi-polar (4+-pair mTI) montage names.  Case-insensitive.

    Returns
    -------
    list[str]
        Sorted montage names.  Returns an empty list if the net or
        mode key does not exist (never raises for an unknown net).

    Examples
    --------
    >>> from tit.sim import list_montage_names
    >>> list_montage_names("GSN-HydroCel-185.csv", mode="U")  # doctest: +SKIP
    ['L_Insula', 'R_Insula']
    >>> list_montage_names("GSN-HydroCel-185.csv", mode="M")  # doctest: +SKIP
    []

    See Also
    --------
    upsert_montage : Add montage names to the list.
    load_montages : Load the named montages as ``Montage`` objects.
    """
    data = load_montage_data()
    net = data.get("nets", {}).get(eeg_net, {})
    key = "uni_polar_montages" if mode.upper() == "U" else "multi_polar_montages"
    return sorted(net.get(key, {}).keys())


# ── Montage loading ────────────────────────────────────────────────────────────────


def load_montages(
    montage_names: list[str],
    eeg_net: str,
    include_flex: bool = False,
) -> list[Montage]:
    """Load the named montages from the project's ``montage_list.json``.

    **Only the montages named in** *montage_names* **are returned, in that
    order** -- this is not a listing of every montage under the net.
    ``load_montages(["L_Insula"], ...)`` returns a one-element list, so
    indexing ``[1]`` raises ``IndexError``.  Use
    :func:`list_montage_names` to see which names exist.  A name that is
    not defined under *eeg_net* is silently skipped (no error), so the
    result can be shorter than *montage_names*; check ``len()`` or the
    returned ``.name`` values before relying on positions.  A name saved
    under both the uni- and the multi-polar section raises ``ValueError``.

    Reads the ``montage_list.json`` file (managed by
    :func:`ensure_montage_file`), looks up each name under the given
    EEG net's uni- and multi-polar sections, and returns them as
    :class:`Montage` instances.

    The *eeg_net* value determines the montage mode:

    * ``"freehand"`` sets ``Montage.Mode.FREEHAND``
    * ``"flex_mode"`` sets ``Montage.Mode.FLEX_FREE``
    * Any other value (e.g. ``"GSN-HydroCel-185.csv"``) sets
      ``Montage.Mode.NET``

    Parameters
    ----------
    montage_names : list[str]
        Names to look up in the montage file, e.g. ``["L_Insula"]``.
        Order is preserved in the result.
    eeg_net : str
        EEG-net CSV filename (e.g. ``"GSN-HydroCel-185.csv"``,
        ``"EEG10-10_UI_Jurak_2007.csv"``) that selects the sub-dict
        inside ``montage_list.json["nets"]``; it is also stored on each
        returned :class:`Montage` as ``eeg_net``.
    include_flex : bool, optional
        Ignored. It once appended flex montages named by an environment
        variable that nothing sets any more; it is still accepted so
        scripts and notebooks that pass it keep running.

    Returns
    -------
    list[Montage]
        One :class:`Montage` per *found* name, in *montage_names* order,
        ready to pass as ``SimulationConfig(montages=...)``.

    Examples
    --------
    >>> from tit.sim import list_montage_names, load_montages
    >>> list_montage_names("GSN-HydroCel-185.csv", mode="U")  # doctest: +SKIP
    ['L_Insula', 'R_Insula']
    >>> montages = load_montages(["L_Insula"], eeg_net="GSN-HydroCel-185.csv")  # doctest: +SKIP
    >>> len(montages), montages[0].name  # doctest: +SKIP
    (1, 'L_Insula')
    >>> both = load_montages(["L_Insula", "R_Insula"], eeg_net="GSN-HydroCel-185.csv")  # doctest: +SKIP
    >>> [m.name for m in both]  # doctest: +SKIP
    ['L_Insula', 'R_Insula']

    See Also
    --------
    list_montage_names : Discover available names before loading.
    upsert_montage : Add montages that can then be loaded.
    Montage : The returned dataclass type.
    """
    data = load_montage_data()
    net = data.get("nets", {}).get(eeg_net, {})
    uni = net.get("uni_polar_montages", {})
    multi = net.get("multi_polar_montages", {})

    ambiguous = [n for n in montage_names if n in uni and n in multi]
    if ambiguous:
        # It used to return the multi-polar pairs without a word, whichever was meant.
        raise ValueError(
            f"Montage(s) {', '.join(map(repr, ambiguous))} are saved under both "
            f"uni_polar and multi_polar for {eeg_net!r}; delete one before loading."
        )

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
            electrode_pairs=multi[n] if n in multi else uni[n],
            eeg_net=eeg_net,
        )
        for n in montage_names
        if n in multi or n in uni
    ]

    return montages


# ── Directory setup ────────────────────────────────────────────────────────────────


def setup_montage_directories(
    montage_dir: str, mode: SimulationMode, *, niftis: bool = False
) -> dict[str, str]:
    """Create the BIDS-compliant output directory tree for one montage.

    Creates sub-directories for the high-frequency (channel) fields, the
    run's field mesh and its central surface, montage images and
    documentation: under ``TI/`` for a TI run and ``mTI/`` for an mTI run.

    Parameters
    ----------
    montage_dir : str
        Root output directory for this montage.
    mode : SimulationMode
        ``SimulationMode.TI`` or ``SimulationMode.MTI``.
    niftis : bool
        Also create the ``niftis/`` folders (the run writes NIfTIs, ``map_to_vol``). Their
        paths are always in the mapping; a step that writes one later creates the folder.

    Returns
    -------
    dict[str, str]
        Mapping of logical names (e.g. ``"ti_mesh"``, ``"hf_niftis"``)
        to their absolute paths.

    See Also
    --------
    SimulationMode : Enum controlling which directories are created.
    BaseSimulation.run : Calls this at the start of each montage pipeline.
    """
    dirs = {
        "montage_dir": montage_dir,
        "hf_dir": os.path.join(montage_dir, "high_Frequency"),
        "hf_mesh": os.path.join(montage_dir, "high_Frequency", "mesh"),
        "hf_niftis": os.path.join(montage_dir, "high_Frequency", "niftis"),
        "hf_analysis": os.path.join(montage_dir, "high_Frequency", "analysis"),
        "documentation": os.path.join(montage_dir, "documentation"),
    }
    key, folder = ("mti", "mTI") if mode == SimulationMode.MTI else ("ti", "TI")
    dirs[f"{key}_mesh"] = os.path.join(montage_dir, folder, "mesh")
    dirs[f"{key}_surfaces"] = os.path.join(montage_dir, folder, "mesh", "surfaces")
    dirs[f"{key}_niftis"] = os.path.join(montage_dir, folder, "niftis")
    dirs[f"{key}_montage_imgs"] = os.path.join(montage_dir, folder, "montage_imgs")

    for key, path in dirs.items():
        if niftis or not key.endswith("_niftis"):
            os.makedirs(path, exist_ok=True)
    return dirs


#: The folders under a montage directory that hold nothing but one run's derived outputs.
_DERIVED_OUTPUT_DIRS = ("TI", "mTI", "fsaverage")
#: SimNIBS's session records (``simnibs_simulation_<stamp>.mat``/``.log``): run history.
_SESSION_RECORD_PREFIX = "simnibs_simulation_"


def existing_result_meshes(montage_dir: str) -> list[str]:
    """Result meshes an earlier run left in *montage_dir* (``TI/mesh`` or ``mTI/mesh``).

    Parameters
    ----------
    montage_dir : str
        Root output directory of one montage.

    Returns
    -------
    list[str]
        Sorted paths of the ``.msh`` files found; empty when there is no result.
    """
    return sorted(
        path
        for mode in ("TI", "mTI")
        for path in glob.glob(os.path.join(montage_dir, mode, "mesh", "*.msh"))
    )


def refuse_existing_result(montage_dir: str, montage_name: str) -> None:
    """Refuse to run a montage whose folder already holds an earlier result.

    SimNIBS's own guard looks for its session record in ``high_Frequency/``,
    which ``_organize_files`` moves into ``documentation/``, so after a
    completed run it never fires: the result mesh is the toolbox's marker.

    Parameters
    ----------
    montage_dir : str
        Root output directory of one montage.
    montage_name : str
        The montage's name, for the message.

    Raises
    ------
    FileExistsError
        If :func:`existing_result_meshes` finds a mesh in *montage_dir*.
    """
    existing = existing_result_meshes(montage_dir)
    if existing:
        raise FileExistsError(
            f"Simulation {montage_name!r} already has results in {montage_dir} "
            f"({os.path.basename(existing[0])}); run with overwrite=True to replace "
            "them."
        )


def clear_previous_outputs(montage_dir: str) -> None:
    """Remove the derived outputs of earlier runs before a confirmed re-run.

    Removes ``TI/``, ``mTI/`` and ``fsaverage/`` and everything in
    ``high_Frequency/`` except SimNIBS session records, so the folder ends up
    holding exactly what the new ``config.json`` asks for.  The run history
    (``documentation/``, session records) and the user's ``Analyses/`` are
    kept, and so is anything else the simulator does not write.  A folder that
    is a symbolic link is left as it is, link and target: what it points at is
    not this montage's to delete.

    Parameters
    ----------
    montage_dir : str
        Root output directory of one montage.
    """
    for name in _DERIVED_OUTPUT_DIRS:
        path = os.path.join(montage_dir, name)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
    hf_dir = os.path.join(montage_dir, "high_Frequency")
    if not os.path.isdir(hf_dir) or os.path.islink(hf_dir):
        return
    for entry in os.listdir(hf_dir):
        path = os.path.join(hf_dir, entry)
        if entry.startswith(_SESSION_RECORD_PREFIX) and os.path.isfile(path):
            continue
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


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

    Skips rendering for ``"freehand"`` and ``"flex_mode"`` montages
    (no cap layout available).

    Parameters
    ----------
    montage_name : str
        Name of the montage to visualize.
    simulation_mode : SimulationMode
        ``SimulationMode.TI`` or ``SimulationMode.MTI``.
    eeg_net : str
        EEG net identifier.  Visualization is skipped when this is
        ``"freehand"`` or ``"flex_mode"``.
    output_dir : str
        Directory where the image file is saved.
    logger : logging.Logger
        Logger instance for status messages.
    electrode_pairs : list or None, optional
        Electrode pair list to annotate on the diagram.  Defaults to
        an empty list.

    See Also
    --------
    tit.tools.montage_visualizer.visualize_montage :
        Underlying rendering function.
    """
    from tit.tools.montage_visualizer import (
        get_expected_output_filename,
        is_skipped_net,
        is_supported_net,
        visualize_montage,
    )

    sim_mode_str = "U" if simulation_mode == SimulationMode.TI else "M"
    expected = get_expected_output_filename(montage_name, sim_mode_str)

    if is_skipped_net(eeg_net):
        logger.warning(
            "Montage visualization unavailable for EEG net '%s'; skipping render. "
            "This net does not currently have a supported 2-D montage template. "
            "Expected output would be %s in %s.",
            eeg_net,
            expected,
            output_dir,
        )
        return

    if not is_supported_net(eeg_net):
        logger.warning(
            "Montage visualization unavailable for unsupported EEG net '%s'. "
            "Expected output would be %s in %s.",
            eeg_net,
            expected,
            output_dir,
        )
        return

    try:
        visualize_montage(
            montage_name=montage_name,
            electrode_pairs=electrode_pairs or [],
            eeg_net=eeg_net,
            output_dir=output_dir,
            sim_mode=sim_mode_str,
            logger=logger,
        )
    except (OSError, subprocess.CalledProcessError, ValueError, TypeError) as exc:
        logger.warning(
            "Montage visualization unavailable for montage '%s' using EEG net '%s': %s. "
            "Continuing simulation without %s in %s.",
            montage_name,
            eeg_net,
            exc,
            expected,
            output_dir,
        )


# ── Simulation config file ────────────────────────────────────────────────────────────────


def _as_xyz(value) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"Expected XYZ coordinate, got {value!r}")
    xyz = [float(value[0]), float(value[1]), float(value[2])]
    if not all(math.isfinite(v) for v in xyz):
        raise ValueError(f"Expected a finite XYZ coordinate, got {value!r}")
    return xyz


def _load_eeg_position_csv(path: str) -> dict[str, list[float]]:
    positions: dict[str, list[float]] = {}
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if len(row) < 5 or row[0].strip().lower() != "electrode":
                continue
            positions[row[4].strip()] = [float(row[1]), float(row[2]), float(row[3])]
    return positions


def resolve_montage_electrode_coordinates(
    config: SimulationConfig, montage: Montage, logger=None
) -> tuple[list[list[float]] | None, str | None]:
    """Resolve every electrode in *montage* to XYZ coordinates when possible."""
    if montage.is_xyz:
        return (
            [_as_xyz(pos) for pair in montage.electrode_pairs for pos in pair],
            "config_xyz",
        )

    if not montage.eeg_net:
        if logger:
            logger.warning("No EEG net set; electrode coordinates not written")
        return None, None

    try:
        pm = get_path_manager()
        eeg_path = os.path.join(pm.eeg_positions(config.subject_id), montage.eeg_net)
        eeg_positions = _load_eeg_position_csv(eeg_path)
        coordinates = [
            eeg_positions[pos] for pair in montage.electrode_pairs for pos in pair
        ]
    except (OSError, RuntimeError, KeyError, ValueError) as exc:
        if logger:
            logger.warning("Could not resolve electrode coordinates: %s", exc)
        return None, None

    return coordinates, os.path.join("eeg_positions", montage.eeg_net)


def create_simulation_config_file(
    config: SimulationConfig,
    montage: Montage,
    documentation_dir: str,
    logger,
) -> None:
    """Write a JSON snapshot of the simulation configuration to disk.

    Serialises subject ID, montage details, electrode geometry, mapping
    options, and a timestamp into ``config.json`` inside
    *documentation_dir*. It records what this montage runs with:
    ``intensities`` holds one current per pair (SimNIBS reads the first two
    for TI and one per pair for mTI, though a config may list more), and
    ``tissue_conductivities`` the per-tissue overrides (S/m, keyed by tissue
    number) that ``BaseSimulation._apply_tissue_conductivities`` applies --
    the ``TISSUE_COND_<n>`` environment variables, which ``tit.sim.__main__``
    sets from ``SimulationConfig.tissue_conductivities``.

    Parameters
    ----------
    config : SimulationConfig
        The full simulation configuration.
    montage : Montage
        The specific montage being simulated.
    documentation_dir : str
        Directory to write ``config.json`` into.
    logger : logging.Logger
        Logger instance for status messages.

    See Also
    --------
    SimulationConfig : The serialised configuration type.
    """
    path = os.path.join(documentation_dir, "config.json")
    electrode_coordinates, electrode_coordinate_source = (
        resolve_montage_electrode_coordinates(config, montage, logger)
    )
    prefix = "TISSUE_COND_"
    tissue_overrides = {
        key[len(prefix) :]: float(value)
        for key, value in os.environ.items()
        if key.startswith(prefix) and key[len(prefix) :].isdigit()
    }
    data = {
        "subject_id": config.subject_id,
        "simulation_name": montage.name,
        "simulation_display_name": montage.display_name,
        "simulation_mode": montage.simulation_mode.value,
        "montage_mode": montage.mode.value,
        "eeg_net": montage.eeg_net,
        "conductivity": config.conductivity,
        "electrode_pairs": montage.electrode_pairs,
        "is_xyz_montage": montage.is_xyz,
        "electrode_coordinates": electrode_coordinates,
        "electrode_coordinate_source": electrode_coordinate_source,
        "intensities": config.intensities[: montage.num_pairs],
        "tissue_conductivities": tissue_overrides,
        "output_fields": config.output_fields,
        "carrier_only": config.carrier_only,
        "electrode_geometry": {
            "shape": config.electrode_shape,
            "dimensions": config.electrode_dimensions,
            "gel_thickness": config.gel_thickness,
            "rubber_thickness": config.rubber_thickness,
        },
        "mapping_options": {
            "map_to_vol": config.map_to_vol,
            "map_to_mni": config.map_to_mni,
            "map_to_fsavg": config.map_to_fsavg,
        },
        "aniso_maxratio": config.aniso_maxratio,
        "aniso_maxcond": config.aniso_maxcond,
        "created_at": datetime.now().isoformat(),
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Config written: {path}")


# ── Shared post-processing helpers ───────────────────────────────────────────────────────────


def transform_dirs_to_nifti(
    specs: list[dict], m2m_dir: str, logger, *, map_to_mni: bool = False
) -> None:
    """Convert several mesh directories to NIfTI in a single process pool.

    Thin wrapper over ``tit.tools.mesh2nii.convert_mesh_dirs``.  Overlaps
    directories that would otherwise be converted one after another (e.g.
    the TI-mesh and HF-mesh directories) by submitting every conversion
    task to one shared pool.

    Parameters
    ----------
    specs : list[dict]
        One dict per directory with keys ``mesh_dir`` and ``output_dir``
        (required) and optional ``fields`` / ``skip_patterns`` / ``tissues``.
    m2m_dir : str
        Path to the subject's m2m directory, used for coordinate transforms.
    logger : logging.Logger
        Logger instance for status messages.
    """
    from tit.tools.mesh2nii import convert_mesh_dirs

    convert_mesh_dirs(specs=specs, m2m_dir=m2m_dir, map_to_mni=map_to_mni)


def start_t1_to_mni(m2m_dir: str, subject_id: str) -> subprocess.Popen:
    """Launch the subject T1-to-MNI warp and return the running process.

    The ``subject2mni`` transform is independent of the simulation field
    meshes, so it can run concurrently with the mesh-to-NIfTI conversions.
    Pair this with :func:`finish_t1_to_mni` to wait for completion.

    Parameters
    ----------
    m2m_dir : str
        Path to the subject's m2m directory containing ``T1.nii.gz``.
    subject_id : str
        Subject identifier, used for the output filename.

    Returns
    -------
    subprocess.Popen
        The running ``subject2mni`` process.
    """
    t1 = os.path.join(m2m_dir, "T1.nii.gz")
    out = os.path.join(m2m_dir, f"T1_{subject_id}")
    return subprocess.Popen(
        ["subject2mni", "-i", t1, "-m", m2m_dir, "-o", out],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def finish_t1_to_mni(proc: subprocess.Popen, logger, timeout: int = 300) -> None:
    """Wait for a :func:`start_t1_to_mni` process and log any failure.

    Logs a warning (but does not raise) if the conversion fails or times
    out, matching the previous best-effort behaviour.

    Parameters
    ----------
    proc : subprocess.Popen
        Process returned by :func:`start_t1_to_mni`.
    logger : logging.Logger
        Logger instance for warning messages.
    timeout : int
        Seconds to wait before killing the process.
    """
    try:
        _, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        logger.warning("T1 MNI conversion timed out")
        return
    if proc.returncode != 0:
        logger.warning(f"T1 MNI conversion warning: {stderr}")


def safe_move(src: str, dest: str) -> None:
    """Move a file or directory from *src* to *dest*.

    Ignore a missing AppleDouble sidecar only after its data file has moved.

    Parameters
    ----------
    src : str
        Source path.
    dest : str
        Destination path.

    See Also
    --------
    shutil.move : Underlying implementation.
    """
    name = os.path.basename(src)
    target = os.path.join(dest, name) if os.path.isdir(dest) else dest
    target_name = os.path.basename(target)
    # macOS may move ._ metadata with its data file, leaving a stale listdir entry.
    if (
        name.startswith("._")
        and target_name.startswith("._")
        and not os.path.lexists(src)
        and not os.path.lexists(os.path.join(os.path.dirname(src), name[2:]))
        and os.path.isfile(os.path.join(os.path.dirname(target), target_name[2:]))
    ):
        return
    shutil.move(src, dest)


# ── Simulation Orchestration ────────────────────────────────────────────────────────────────


def run_simulation(
    config: SimulationConfig,
    logger: logging.Logger | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    *,
    overwrite: bool = False,
) -> list[dict]:
    """Run TI or mTI simulations for every montage in *config*.

    For each montage in ``config.montages``, this function:

    1. Auto-detects TI (2 pairs) vs mTI (4+ pairs) from the montage.
    2. Builds a SimNIBS SESSION with electrode geometry and conductivity
       settings from *config*.
    3. Runs the FEM solver to compute electric-field distributions.
    4. Computes temporal-interference envelope fields: ``TI_max``/``TI_avg``
       plus ``TI_normal`` (2-pair TI only), or the multi-channel
       superposition for mTI.
    5. Writes the field mesh, its central surface and (opt-in) NIfTIs to the
       BIDS-compliant simulation directory.

    Montages are processed sequentially.  If no *logger* is provided,
    a file logger is created under the subject's log directory.

    Parameters
    ----------
    config : SimulationConfig
        Full simulation configuration including subject ID, montage
        list, electrode geometry, and conductivity model.
    logger : logging.Logger or None, optional
        Logger instance.  If ``None``, a file logger is created
        automatically in the subject's BIDS logs directory.
    progress_callback : callable or None, optional
        Optional callback invoked before each montage as
        ``callback(current_index, total, montage_name)`` and once more
        with ``(total, total, "Complete")`` when finished.

    overwrite : bool, optional
        Replace an earlier result of a montage. Defaults to False; existing-result
        protection stays enabled unless confirmed. When set, the earlier run's
        derived outputs (``TI/``, ``mTI/``, ``fsaverage/``, ``high_Frequency/``) are
        removed before solving, keeping ``documentation/`` and ``Analyses/``, so the
        folder holds exactly what the new ``config.json`` says.

    Returns
    -------
    list[dict]
        One result dict per montage with keys ``montage_name``,
        ``montage_type``, ``status``, and ``output_mesh``.

    Raises
    ------
    ValueError
        If ``config.montages`` is empty, the subject's ``m2m_<id>``
        directory does not exist, a montage has an invalid pair count
        (must be an even number >= 2), too few *intensities* are given
        for a montage, a label-based montage has no *eeg_net* or its
        EEG-net CSV is missing from the subject's ``eeg_positions``
        folder, or an XYZ montage holds a malformed coordinate.
    OSError
        ``FileExistsError`` when a montage folder already holds a result mesh
        (``TI/mesh`` or ``mTI/mesh``) and *overwrite* is ``False``; every
        montage is checked before the first is solved, so nothing is
        written.  SimNIBS raises its own ``OSError`` when an interrupted run
        left a session record in ``high_Frequency/``.

    Examples
    --------
    >>> from tit.sim import SimulationConfig, load_montages, run_simulation
    >>> montages = load_montages(["L_Insula"], eeg_net="GSN-HydroCel-185.csv")  # doctest: +SKIP
    >>> cfg = SimulationConfig(subject_id="ernie", montages=montages,
    ...                        intensities=[1.0, 1.0], output_fields=["TI_max"])  # doctest: +SKIP
    >>> results = run_simulation(cfg)  # doctest: +SKIP
    >>> results[0]["status"], results[0]["output_mesh"]  # doctest: +SKIP
    ('completed', '.../Simulations/L_Insula/TI/mesh/ernie_L_Insula_TI.msh')

    See Also
    --------
    SimulationConfig : The configuration consumed by this function.
    BaseSimulation.run : Per-montage pipeline called internally.
    TISimulation : Concrete class for 2-pair simulations.
    mTISimulation : Concrete class for N-pair simulations.
    """
    # Determine dominant simulation type for telemetry
    from tit.telemetry import track_operation

    _validate_simulation_inputs(config)
    if not overwrite:
        # Every montage before the first solve, not each one as its turn comes.
        pm = get_path_manager()
        for montage in config.montages:
            refuse_existing_result(
                pm.simulation(config.subject_id, montage.name), montage.name
            )
    has_mti = any(m.simulation_mode == SimulationMode.MTI for m in config.montages)
    _tel_op = const.TELEMETRY_OP_SIM_MTI if has_mti else const.TELEMETRY_OP_SIM_TI

    with track_operation(_tel_op):
        return _run_simulation_inner(
            config, logger, progress_callback, overwrite=overwrite
        )


def _validate_simulation_inputs(config: SimulationConfig) -> None:
    """Validate user-controlled simulation inputs before telemetry starts."""
    if not config.montages:
        raise ValueError("At least one montage is required for simulation.")

    pm = get_path_manager()
    m2m_dir = pm.m2m(config.subject_id)
    if not os.path.isdir(m2m_dir):
        raise ValueError(
            f"SimNIBS m2m directory not found for subject {config.subject_id}: {m2m_dir}. "
            "Run preprocessing/CHARM before simulation."
        )

    for montage in config.montages:
        digest = (montage.provenance or {}).get("head_mesh_sha256")
        if digest is not None:
            from tit.mesh_identity import verify_subject_mesh

            verify_subject_mesh(pm, config.subject_id, digest)
        for pair in montage.electrode_pairs:
            if len(pair) != 2:
                raise ValueError(
                    f"Montage {montage.name!r} has an invalid electrode pair {pair!r}; "
                    "each pair must contain exactly two electrodes."
                )

        mode = montage.simulation_mode
        required_currents = 2 if mode == SimulationMode.TI else montage.num_pairs
        if len(config.intensities) < required_currents:
            raise ValueError(
                f"Montage {montage.name!r} requires {required_currents} current "
                f"intensities; got {len(config.intensities)}."
            )

        if montage.is_xyz:
            for pair in montage.electrode_pairs:
                for pos in pair:
                    _as_xyz(pos)
        else:
            if not montage.eeg_net:
                raise ValueError(f"Montage {montage.name!r} requires an EEG net file.")
            eeg_path = os.path.join(
                pm.eeg_positions(config.subject_id), montage.eeg_net
            )
            if not os.path.isfile(eeg_path):
                raise ValueError(
                    f"EEG net file not found for montage {montage.name!r}: {eeg_path}"
                )


def _run_simulation_inner(
    config: SimulationConfig,
    logger,
    progress_callback: Callable[[int, int, str], None] | None,
    *,
    overwrite: bool = False,
) -> list[dict]:
    """Inner implementation of :func:`run_simulation` (unwrapped)."""
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
        simulation = cls(config, montage, logger)
        results.append(
            simulation.run(simulation_dir, overwrite=True)
            if overwrite
            else simulation.run(simulation_dir)
        )
        if config.map_to_fsavg:
            _project_montage_to_fsaverage(config, montage, logger)
    if progress_callback:
        progress_callback(total, total, "Complete")
    return results


def _project_montage_to_fsaverage(config: SimulationConfig, montage, logger) -> None:
    """Project a finished TI montage's surface fields onto fsaverage5.

    Auxiliary step driven by ``config.map_to_fsavg``; runs in the same
    ``simnibs_python`` process right after the montage completes, so the central
    surface it reads is already on disk.

    Best-effort -- a projection failure logs a warning and never aborts
    the simulation. Covers both TI and mTI montages.
    """
    from tit.source.config import FsavgMapConfig
    from tit.source.fsaverage import project_subject

    try:
        # overwrite=True: this montage's surface was just (re)written, so any
        # cached projection from a prior run of the same montage name is stale.
        # A carrier-only run has no envelope on its surface; its coherent carrier
        # sum is read back from the run's config.json by the projection.
        cfg = (
            FsavgMapConfig(overwrite=True, fields=("hf_peak", "hf_rms"))
            if config.carrier_only
            else FsavgMapConfig(overwrite=True)
        )
        _, status, msg = project_subject(config.subject_id, montage.name, cfg)
        logger.info("fsaverage projection [%s] %s: %s", status, montage.name, msg)
    except Exception as exc:  # noqa: BLE001 - auxiliary step, never fatal
        logger.warning("fsaverage projection failed for %s: %r", montage.name, exc)


def _make_file_logger(
    name: str, log_file: str, level: int = logging.INFO
) -> logging.Logger:
    """Create a file-backed logger for simulation output."""
    from tit.logger import add_file_handler

    add_file_handler(log_file, level=logging.getLevelName(level), logger_name=name)
    # Also capture simnibs output in the same log file
    add_file_handler(log_file, logger_name="simnibs")
    return logging.getLogger(name)
