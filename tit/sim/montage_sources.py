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
  ``electrode_positions`` dict of label -> XYZ. Every position is used,
  paired consecutively in file order (``(1, 2), (3, 4), ...``) -- the same
  pairing the desktop Simulator applies to a saved placement -- so 4
  positions are TI and 8, 12, 16, ... are mTI.

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

from tit import constants as const
from tit.paths import PathManager, resolve_within
from tit.sim.config import Montage

__all__ = [
    "short_flex_run_id",
    "flex_montage_name",
    "resolve_flex_montage",
    "flex_currents",
    "resolve_flex_simulation",
    "resolve_freehand_montage",
]


def _source_name(name: str, field: str) -> str:
    """Keep legacy spaces/dots, but require one filename component."""
    if (
        not isinstance(name, str)
        or not name
        or name in (".", "..")
        or any(character in name for character in ("/", "\\", "\0"))
    ):
        raise ValueError(f"{field} must be a name, not a path")
    return name


def _source_path(pm: PathManager, path: str) -> str:
    """Resolve project-owned montage inputs and mapping outputs before file I/O."""
    if pm.project_dir:
        try:
            return resolve_within(pm.project_dir, path)
        except ValueError:
            pass
    raise ValueError("Montage source paths must remain inside the project")


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
    run_id = _source_name(run_id, "run_id")
    safe_run_name = re.sub(r"[^A-Za-z0-9_]+", "_", str(run_name)).strip("_")
    safe_run_name = safe_run_name[:32] or "run"
    safe_type = re.sub(r"[^A-Za-z0-9_]+", "_", str(electrode_type)).strip("_")
    safe_type = safe_type or "mapped"
    return f"flex_{safe_run_name}_{run_id}_{safe_type}"


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
        ``mode=FLEX_MAPPED`` (net labels) for ``"mapped"``, or ``mode=FLEX_FREE`` (XYZ
        coordinates) for ``"optimized"``; one pair per stimulation channel, paired by
        :func:`tit.catalog.pair_by_channel` (the optimiser's ``channel_array_indices``), so
        a 4-channel (mTI) run keeps all four pairs, as the Simulator's flex rows do.

    Raises
    ------
    ValueError
        If *electrode_type* is unknown, *eeg_net* is missing for
        ``"mapped"``, the run folder / ``electrode_positions.json`` /
        EEG-net CSV cannot be found, or fewer than 4 electrodes are
        available.

    A net the run is already mapped to (its ``electrode_mapping_<net>.json``) is read, not
    re-mapped: the Hungarian mapping runs, and the cache is written, only the first time.
    """
    from tit import catalog

    run_name = _source_name(run_name, "run_name")
    run_id = run_id or short_flex_run_id(subject_id, run_name)
    display_name = display_name or f"{run_name} | {run_id} | {electrode_type}"
    montage_name = flex_montage_name(run_name, run_id, electrode_type)

    flex_search_dir = _source_path(pm, pm.flex_search_run(subject_id, run_name))
    if not flex_search_dir or not os.path.isdir(flex_search_dir):
        raise ValueError(f"Flex-search folder not found for {subject_id} | {run_name}")
    positions_file = _source_path(
        pm, os.path.join(flex_search_dir, "electrode_positions.json")
    )

    def require_positions() -> None:
        if not os.path.isfile(positions_file):
            raise ValueError(f"electrode_positions.json not found: {positions_file}")

    if electrode_type == "optimized":
        require_positions()
        pairs = catalog.flex_optimized_pairs(
            flex_search_dir, project_root=pm.project_dir
        )
        if not pairs:
            raise ValueError(
                f"Not enough optimized electrodes in {run_name} (need >=4 XYZ positions)"
            )
        return Montage(
            name=montage_name,
            mode=Montage.Mode.FLEX_FREE,
            electrode_pairs=[tuple(pair) for pair in pairs],
            display_name=display_name,
        )

    if electrode_type != "mapped":
        raise ValueError(
            f"Unknown electrode_type {electrode_type!r}; expected 'mapped' or "
            "'optimized'"
        )
    if not eeg_net:
        raise ValueError("eeg_net is required when electrode_type='mapped'")

    eeg_net = _source_name(eeg_net, "eeg_net")
    mapping_file = _source_path(
        pm,
        os.path.join(
            flex_search_dir, f'electrode_mapping_{eeg_net.replace(".csv", "")}.json'
        ),
    )
    mapping = catalog.read_flex_mapping(mapping_file)
    if mapping is None:
        # A run from before 2026-10-21 kept its search-time mapping under SimNIBS's name.
        legacy = catalog.read_flex_mapping(
            _source_path(pm, os.path.join(flex_search_dir, catalog.LEGACY_FLEX_MAPPING))
        )
        if legacy is not None and _net_stem(legacy["eeg_net"]) == _net_stem(eeg_net):
            mapping = legacy
    if mapping is None:
        require_positions()
        eeg_positions_dir = _source_path(pm, pm.eeg_positions(subject_id))
        eeg_net_path = _source_path(pm, os.path.join(eeg_positions_dir, eeg_net))
        if not eeg_positions_dir or not os.path.isfile(eeg_net_path):
            raise ValueError(f"EEG net file not found: {eeg_net_path}")

        from tit.tools.map_electrodes import (
            check_net_for_mapping,
            load_electrode_positions_json,
            map_electrodes_to_net,
            read_csv_positions,
            save_mapping_result,
        )

        opt_pos, ch_arr_idx = load_electrode_positions_json(positions_file)
        net_pos, net_labels = read_csv_positions(eeg_net_path)
        # Before anything is written: a refused net leaves no mapping file behind.
        check_net_for_mapping(net_pos, net_labels, len(opt_pos), eeg_net)
        result = map_electrodes_to_net(opt_pos, net_pos, net_labels, ch_arr_idx)
        save_mapping_result(result, mapping_file, eeg_net_name=eeg_net)
        # Read back through the catalog's reader: the pairs come from one rule either way.
        mapping = catalog.read_flex_mapping(mapping_file)
    if mapping is None:
        raise ValueError(
            f"Not enough electrodes for TI in {run_name} (need >=4 mapped labels)"
        )
    return Montage(
        name=montage_name,
        mode=Montage.Mode.FLEX_MAPPED,
        electrode_pairs=[tuple(pair) for pair in mapping["pairs"]],
        eeg_net=eeg_net,
        display_name=display_name,
    )


def _net_stem(name: str) -> str:
    return name[:-4] if name.lower().endswith(".csv") else name


def flex_currents(manifest: dict[str, Any], num_pairs: int) -> tuple[list[float], str]:
    """A flex run's own simulation currents (mA) and where they came from.

    The run's optimised ``current_split``, else its ``current_mA`` per channel, else 1 mA per
    channel. The Simulator page applies the same order to the catalog's manifest in
    ``desktop/src/renderer/pages/simulator/FlexTab.tsx`` (``flexCurrents``); both are pinned by
    ``tests/fixtures/flex_currents.json``.
    """
    if manifest.get("current_split"):
        return [
            float(c) for c in manifest["current_split"]
        ], "the run's optimised split"
    if manifest.get("current_mA"):
        return (
            [float(manifest["current_mA"])] * max(2, num_pairs),
            "the run's current_mA per channel",
        )
    return [1.0] * max(2, num_pairs), "app default"


def resolve_flex_simulation(
    pm: PathManager,
    subject_id: str,
    flex_run: str | None = None,
    *,
    eeg_net: str | None = None,
    intensities: list[float] | None = None,
) -> dict[str, Any]:
    """What the Simulator does for a flex row: the run's electrodes and currents as one montage.

    The single source for turning a finished flex-search run into a ``SimulationConfig``
    montage -- ``POST /api/sim-from-flex`` (the agent plugin's ``simulate_flex_result``) and a
    proposal's deferred ``sim_from_flex`` step (:mod:`tit.server.proposals`) both call it.

    The run is *flex_run* (a folder name or path; its basename is used), else the newest run.
    Placement is *eeg_net*'s labels (mapped on demand, cached beside the run), else the first
    net the run is already mapped to, else the optimised XYZ (``flex_free``). Currents are
    *intensities*, else the run's optimised split, else its ``current_mA`` per channel, else
    1 mA per channel.

    Returns ``{flex_run, eeg_net, placement, intensities, intensities_from, montage}`` where
    ``montage`` is a serialised ``Montage`` named after the run. Raises :class:`ValueError` for
    an unknown subject, no run, an unknown run or a run without usable positions.
    """
    from tit import catalog

    runs = catalog.flex_runs(pm, subject_id)
    if runs is None:
        raise ValueError(f"unknown subject: {subject_id}")
    if not runs:
        raise ValueError(f"sub-{subject_id} has no finished flex-search run")
    if flex_run:
        wanted = os.path.basename(str(flex_run).rstrip("/"))
        run = next((r for r in runs if r["name"] == wanted), None)
        if run is None:
            names = ", ".join(r["name"] for r in runs)
            raise ValueError(
                f"no finished flex run {wanted!r} for sub-{subject_id}; runs: {names}"
            )
    else:
        run = max(runs, key=lambda r: str(r.get("created") or ""))
    # The Simulator's placement: the given net (mapped now if the run has no mapping for it,
    # cached beside the run), else the first net the run is mapped to, else the optimised XYZ.
    mappings = run.get("mappings") or []
    if eeg_net:
        net = f"{_net_stem(eeg_net)}.csv"
    elif mappings:
        net = mappings[0]["eeg_net"]
    else:
        net = None
    montage = resolve_flex_montage(
        pm, subject_id, run["name"], "mapped" if net else "optimized", eeg_net=net
    )
    pairs = [list(pair) for pair in montage.electrode_pairs]
    if intensities:
        currents, source = [float(i) for i in intensities], "given"
    else:
        currents, source = flex_currents(run.get("manifest") or {}, len(pairs))
    return {
        "flex_run": run["name"],
        "eeg_net": net,
        "placement": f"mapped to {net}" if net else "optimised XYZ (flex_free)",
        "intensities": currents,
        "intensities_from": source,
        "montage": {
            "_type": "Montage",
            "name": run["name"],
            "mode": "flex_mapped" if net else "flex_free",
            "electrode_pairs": pairs,
            "eeg_net": net,
        },
    }


def resolve_freehand_montage(pm: PathManager, subject_id: str, name: str) -> Montage:
    """Resolve one freehand stim-config name into a concrete ``Montage``.

    Every coordinate in ``electrode_positions`` is used, paired consecutively
    in file order -- positions 1+2 are pair 1, 3+4 pair 2, and so on -- which
    is how the desktop Simulator turns a saved placement into a job
    (``MontageManager.setRowFreehand``). Four positions give TI; 8, 12, 16 ...
    give mTI.

    Raises
    ------
    ValueError
        If the subject has no ``m2m``/``stim_configs`` directory, no config
        named *name* exists, or its position count is not an allowed pair
        count (:func:`tit.constants.is_valid_pair_count` of half of it).
    """
    m2m_dir = pm.m2m(subject_id)
    if not m2m_dir:
        raise ValueError(f"No m2m directory for subject {subject_id}")
    stim_configs_dir = _source_path(pm, os.path.join(m2m_dir, "stim_configs"))
    if not os.path.isdir(stim_configs_dir):
        raise ValueError(f"No stim_configs directory for subject {subject_id}")

    for config_file in sorted(os.listdir(stim_configs_dir)):
        if not config_file.endswith(".json"):
            continue
        try:
            config_path = _source_path(pm, os.path.join(stim_configs_dir, config_file))
        except ValueError:
            continue
        try:
            with open(config_path, "r") as f:
                config_data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if config_data.get("name", config_file[: -len(".json")]) != name:
            continue

        coords = list(config_data.get("electrode_positions", {}).values())
        if len(coords) % 2 or not const.is_valid_pair_count(len(coords) // 2):
            raise ValueError(
                f"Freehand config {name!r} has {len(coords)} electrode positions; "
                "expected 4 (TI) or a multiple of 4 from 8 up (mTI)"
            )
        return Montage(
            name=name,
            mode=Montage.Mode.FREEHAND,
            electrode_pairs=list(zip(coords[0::2], coords[1::2])),
            eeg_net="freehand",
        )

    raise ValueError(f"Freehand config {name!r} not found for subject {subject_id}")
