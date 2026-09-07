"""Resolve non-``montage_list.json`` montage sources into ``Montage`` objects.

Extracted from the former PyQt ``SimulatorTab`` (as of the v3 audit): the pure logic that turns a flex-search run
selection, or a freehand ``stim_configs/*.json`` file, into a concrete
:class:`~tit.sim.config.Montage` -- the same shape a plain
``montage_list.json`` entry produces via :func:`tit.sim.utils.load_montages`.
Nothing here touches Qt; every function takes a :class:`~tit.paths.PathManager`
and plain values instead of reading widget state, so it is reusable from
:mod:`tit.server.routes.plan`, notebooks, and future non-Qt UIs alike.

Two sources, two resolvers
---------------------------
- **Flex-search** (:func:`resolve_flex_montage`): a run under
  ``flex-search/<subject>/<run_name>/`` has an ``electrode_positions.json``
  with the optimizer's raw XYZ output. ``electrode_type="optimized"`` uses
  those coordinates directly (``Montage.Mode.FLEX_FREE``);
  ``electrode_type="mapped"`` maps them onto the nearest electrodes of a
  named EEG net via the Hungarian algorithm
  (:func:`tit.tools.map_electrodes.map_electrodes_to_net`) and uses the
  resulting labels (``Montage.Mode.FLEX_MAPPED``), caching the mapping
  alongside the run.
- **Freehand** (:func:`resolve_freehand_montage`): a
  ``m2m_{subject}/stim_configs/<name>.json`` file holds an
  ``electrode_positions`` dict keyed by electrode role (``"E1+"``,
  ``"E1-"``, ``"E2+"``, ``"E2-"``, ...). Only the **first four** coordinates
  are used, in ``["E1+", "E1-", "E2+", "E2-"]`` order when those keys are
  present, else sorted-key order for whatever remains -- this is the
  original GUI's behavior verbatim, not a new convention. mTI (>4
  electrodes) freehand configs are not resolvable by this function today;
  see its docstring.

See Also
--------
tit.tools.map_electrodes : Hungarian-algorithm electrode-to-net mapping.
tit.sim.utils.load_montages : Resolves plain ``montage_list.json`` entries.
tit.sim.config.Montage : The dataclass every resolver here returns.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from tit.paths import PathManager
from tit.sim.config import Montage

__all__ = [
    "short_flex_run_id",
    "flex_montage_name",
    "list_flex_run_options",
    "resolve_flex_montage",
    "list_freehand_configs",
    "resolve_freehand_montage",
]


def short_flex_run_id(subject_id: str, run_name: str) -> str:
    """Build a stable short id from the subject and flex-search run folder.

    Mirrors ``SimulatorTab._short_flex_run_id`` -- used only as a display
    disambiguator (folder names are not unique across subjects), never as a
    lookup key on disk.
    """
    raw = f"{subject_id}/{run_name}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:8]


def flex_montage_name(run_name: str, run_id: str, electrode_type: str) -> str:
    """Build a filesystem-safe unique simulation name for a flex-search run.

    Mirrors ``SimulatorTab._build_flex_montage_name`` exactly (same
    sanitisation and length cap), so simulation output directories named
    from a flex-search source stay stable across the PyQt and v3 GUIs.
    """
    safe_run_name = re.sub(r"[^A-Za-z0-9_]+", "_", str(run_name)).strip("_")
    safe_run_name = safe_run_name[:32] or "run"
    safe_type = re.sub(r"[^A-Za-z0-9_]+", "_", str(electrode_type)).strip("_")
    safe_type = safe_type or "mapped"
    return f"flex_{safe_run_name}_{run_id}_{safe_type}"


def list_flex_run_options(pm: PathManager, subject_id: str) -> list[dict[str, Any]]:
    """List resolvable flex-search montage sources for a subject.

    Returns one entry per (run, electrode_type) combination that
    :func:`resolve_flex_montage` can turn into a ``Montage`` -- every run
    has a ``"mapped"`` option; a run also gets an ``"optimized"`` option
    when its ``electrode_positions.json`` carries ``optimized_positions``.

    Returns
    -------
    list of dict
        Each dict has ``run_name``, ``electrode_type``
        (``"mapped"``/``"optimized"``), and ``run_id`` (see
        :func:`short_flex_run_id`).
    """
    options: list[dict[str, Any]] = []
    for run_name in pm.list_flex_search_runs(subject_id):
        run_id = short_flex_run_id(subject_id, run_name)
        options.append(
            {"run_name": run_name, "electrode_type": "mapped", "run_id": run_id}
        )
        positions_file = pm.flex_electrode_positions(subject_id, run_name)
        if positions_file and os.path.isfile(positions_file):
            try:
                with open(positions_file, "r") as f:
                    pos_data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if pos_data.get("optimized_positions"):
                options.append(
                    {
                        "run_name": run_name,
                        "electrode_type": "optimized",
                        "run_id": run_id,
                    }
                )
    return options


def resolve_flex_montage(
    pm: PathManager,
    subject_id: str,
    run_name: str,
    electrode_type: str,
    *,
    eeg_net: str | None = None,
    run_id: str | None = None,
    display_name: str | None = None,
) -> Montage:
    """Resolve one flex-search run selection into a concrete ``Montage``.

    Parameters
    ----------
    pm : PathManager
        Project path resolver.
    subject_id : str
        Subject identifier (no ``sub-`` prefix).
    run_name : str
        Flex-search run folder name under ``flex-search/{subject_id}/``.
    electrode_type : str
        ``"mapped"`` (map optimized positions onto *eeg_net*'s nearest
        electrodes) or ``"optimized"`` (use the raw optimizer XYZ output
        directly, no net needed).
    eeg_net : str or None, optional
        EEG net CSV filename (e.g. ``"GSN-HydroCel-185.csv"``). Required
        when *electrode_type* is ``"mapped"``.
    run_id : str or None, optional
        Precomputed :func:`short_flex_run_id`; recomputed if omitted.
    display_name : str or None, optional
        User-facing label for the resulting ``Montage.display_name``.
        Defaults to ``"{run_name} | {run_id} | {electrode_type}"``.

    Returns
    -------
    Montage
        ``mode=FLEX_MAPPED`` (4 named electrodes) for ``"mapped"``, or
        ``mode=FLEX_FREE`` (4 XYZ coordinates) for ``"optimized"``.

    Raises
    ------
    ValueError
        If *electrode_type* is unknown, *eeg_net* is missing for
        ``"mapped"``, the run folder / ``electrode_positions.json`` /
        EEG-net CSV cannot be found, or fewer than 4 electrodes are
        available (TI requires exactly one pair per channel; only the
        first 4 are used for higher electrode counts, matching
        ``SimulatorTab``'s behavior).
    """
    run_id = run_id or short_flex_run_id(subject_id, run_name)
    display_name = display_name or f"{run_name} | {run_id} | {electrode_type}"
    montage_name = flex_montage_name(run_name, run_id, electrode_type)

    flex_search_dir = pm.flex_search_run(subject_id, run_name)
    if not flex_search_dir or not os.path.isdir(flex_search_dir):
        raise ValueError(f"Flex-search folder not found for {subject_id} | {run_name}")
    positions_file = os.path.join(flex_search_dir, "electrode_positions.json")
    if not os.path.isfile(positions_file):
        raise ValueError(f"electrode_positions.json not found: {positions_file}")

    if electrode_type == "optimized":
        with open(positions_file, "r") as f:
            pos_data = json.load(f)
        optimized_positions = pos_data.get("optimized_positions", [])
        if len(optimized_positions) < 4:
            raise ValueError(
                f"Not enough optimized electrodes in {run_name} "
                f"(need >=4, found {len(optimized_positions)})"
            )
        positions = optimized_positions[:4]
        return Montage(
            name=montage_name,
            mode=Montage.Mode.FLEX_FREE,
            electrode_pairs=[
                (positions[0], positions[1]),
                (positions[2], positions[3]),
            ],
            display_name=display_name,
        )

    if electrode_type != "mapped":
        raise ValueError(
            f"Unknown electrode_type {electrode_type!r}; expected 'mapped' or "
            "'optimized'"
        )
    if not eeg_net:
        raise ValueError("eeg_net is required when electrode_type='mapped'")

    eeg_positions_dir = pm.eeg_positions(subject_id)
    eeg_net_path = os.path.join(eeg_positions_dir or "", eeg_net)
    if not eeg_positions_dir or not os.path.isfile(eeg_net_path):
        raise ValueError(f"EEG net file not found: {eeg_net_path}")

    from tit.tools.map_electrodes import (
        load_electrode_positions_json,
        map_electrodes_to_net,
        read_csv_positions,
        save_mapping_result,
    )

    opt_pos, ch_arr_idx = load_electrode_positions_json(positions_file)
    net_pos, net_labels = read_csv_positions(eeg_net_path)
    result = map_electrodes_to_net(opt_pos, net_pos, net_labels, ch_arr_idx)

    mapping_file = os.path.join(
        flex_search_dir, f'electrode_mapping_{eeg_net.replace(".csv", "")}.json'
    )
    save_mapping_result(
        result, mapping_file, eeg_net_name=os.path.basename(eeg_net_path)
    )

    mapped_labels = result.get("mapped_labels", [])
    if len(mapped_labels) < 4:
        raise ValueError(
            f"Not enough electrodes for TI in {run_name} "
            f"(need >=4, found {len(mapped_labels)})"
        )
    electrodes = mapped_labels[:4]
    return Montage(
        name=montage_name,
        mode=Montage.Mode.FLEX_MAPPED,
        electrode_pairs=[
            (electrodes[0], electrodes[1]),
            (electrodes[2], electrodes[3]),
        ],
        eeg_net=eeg_net,
        display_name=display_name,
    )


def list_freehand_configs(pm: PathManager, subject_id: str) -> list[str]:
    """List freehand stim-config names available for a subject.

    Returns
    -------
    list of str
        Names from each ``stim_configs/*.json``'s ``"name"`` field (falling
        back to the filename stem), sorted by filename.
    """
    names: list[str] = []
    m2m_dir = pm.m2m(subject_id)
    if not m2m_dir or not os.path.isdir(m2m_dir):
        return names
    stim_configs_dir = os.path.join(m2m_dir, "stim_configs")
    if not os.path.isdir(stim_configs_dir):
        return names
    for config_file in sorted(os.listdir(stim_configs_dir)):
        if not config_file.endswith(".json"):
            continue
        config_path = os.path.join(stim_configs_dir, config_file)
        try:
            with open(config_path, "r") as f:
                config_data = json.load(f)
            names.append(config_data.get("name", config_file[: -len(".json")]))
        except (OSError, json.JSONDecodeError):
            names.append(config_file[: -len(".json")])
    return names


def resolve_freehand_montage(pm: PathManager, subject_id: str, name: str) -> Montage:
    """Resolve one freehand stim-config name into a concrete ``Montage``.

    Only the **first four** coordinates from ``electrode_positions`` are
    used -- ``["E1+", "E1-", "E2+", "E2-"]`` order when present, else the
    remaining keys in sorted order -- reproducing
    ``SimulatorTab._build_montage_configs_from_freehand`` exactly. A
    freehand config's ``"type"`` field (if any) is not consulted: this
    matches today's GUI behavior (2-pair TI only) rather than a documented
    contract, and an mTI (>4-electrode) freehand config cannot be resolved
    to a usable ``Montage`` by this function -- see the module docstring.

    Raises
    ------
    ValueError
        If the subject has no ``m2m``/``stim_configs`` directory, no config
        named *name* exists, or it has fewer than 4 electrode positions.
    """
    m2m_dir = pm.m2m(subject_id)
    if not m2m_dir:
        raise ValueError(f"No m2m directory for subject {subject_id}")
    stim_configs_dir = os.path.join(m2m_dir, "stim_configs")
    if not os.path.isdir(stim_configs_dir):
        raise ValueError(f"No stim_configs directory for subject {subject_id}")

    for config_file in sorted(os.listdir(stim_configs_dir)):
        if not config_file.endswith(".json"):
            continue
        config_path = os.path.join(stim_configs_dir, config_file)
        try:
            with open(config_path, "r") as f:
                config_data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if config_data.get("name", config_file[: -len(".json")]) != name:
            continue

        electrode_positions = config_data.get("electrode_positions", {})
        ordered_keys = ["E1+", "E1-", "E2+", "E2-"]
        coords = [
            electrode_positions[k] for k in ordered_keys if k in electrode_positions
        ]
        if len(coords) < 4:
            for k in sorted(electrode_positions.keys()):
                if k not in ordered_keys and len(coords) < 4:
                    coords.append(electrode_positions[k])
        if len(coords) < 4:
            raise ValueError(
                f"Freehand config {name!r} has fewer than 4 electrode "
                f"positions (found {len(coords)})"
            )
        return Montage(
            name=name,
            mode=Montage.Mode.FREEHAND,
            electrode_pairs=[(coords[0], coords[1]), (coords[2], coords[3])],
            eeg_net="freehand",
        )

    raise ValueError(f"Freehand config {name!r} not found for subject {subject_id}")
