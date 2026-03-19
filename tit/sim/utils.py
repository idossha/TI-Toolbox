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

from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

from tit.paths import get_path_manager
from tit import constants as const
from tit.sim.config import (
    ConductivityType,
    ElectrodeConfig,
    IntensityConfig,
    LabelMontage,
    XYZMontage,
    MontageConfig,
    SimulationConfig,
    SimulationMode,
)

# ── Montage file I/O ────────────────────────────────────────────────────────────────


def _montage_list_path(project_dir: str) -> str:
    pm = get_path_manager(project_dir)
    return os.path.join(pm.config_dir(), const.FILE_MONTAGE_LIST)


def ensure_montage_file(project_dir: str) -> str:
    """Return path to montage_list.json, creating it with default schema if absent."""
    path = _montage_list_path(project_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump({"nets": {}}, f, indent=4)
    return path


def load_montage_data(project_dir: str) -> dict:
    with open(ensure_montage_file(project_dir)) as f:
        return json.load(f)


def save_montage_data(project_dir: str, data: dict) -> None:
    with open(ensure_montage_file(project_dir), "w") as f:
        json.dump(data, f, indent=4)


def ensure_eeg_net_entry(project_dir: str, eeg_net: str) -> None:
    data = load_montage_data(project_dir)
    data["nets"].setdefault(
        eeg_net, {"uni_polar_montages": {}, "multi_polar_montages": {}}
    )
    save_montage_data(project_dir, data)


def upsert_montage(
    *,
    project_dir: str,
    eeg_net: str,
    montage_name: str,
    electrode_pairs: List[List[str]],
    mode: str,
) -> None:
    """mode: 'U' → uni_polar_montages, 'M' → multi_polar_montages"""
    data = load_montage_data(project_dir)
    net = data["nets"].setdefault(
        eeg_net, {"uni_polar_montages": {}, "multi_polar_montages": {}}
    )
    key = "uni_polar_montages" if mode.upper() == "U" else "multi_polar_montages"
    net[key][montage_name] = electrode_pairs
    save_montage_data(project_dir, data)


def list_montage_names(project_dir: str, eeg_net: str, *, mode: str) -> List[str]:
    """mode: 'U' or 'M'. Returns [] for missing nets."""
    data = load_montage_data(project_dir)
    net = data.get("nets", {}).get(eeg_net, {})
    key = "uni_polar_montages" if mode.upper() == "U" else "multi_polar_montages"
    return sorted(net.get(key, {}).keys())


# ── Montage loading ────────────────────────────────────────────────────────────────


def load_flex_montages(flex_file: Optional[str] = None) -> List[dict]:
    if not flex_file:
        flex_file = os.environ.get("FLEX_MONTAGES_FILE")
    if not flex_file or not os.path.exists(flex_file):
        return []
    with open(flex_file) as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return [data.get("montage", data)]


def parse_flex_montage(flex: dict) -> MontageConfig:
    name, mtype = flex["name"], flex["type"]
    if mtype == "flex_mapped":
        p = flex["pairs"]
        return LabelMontage(
            name=name,
            electrode_pairs=[(p[0][0], p[0][1]), (p[1][0], p[1][1])],
            eeg_net=flex.get("eeg_net") or "",
        )
    if mtype in ("flex_optimized", "freehand_xyz"):
        ep = flex["electrode_positions"]
        return XYZMontage(name=name, electrode_pairs=[(ep[0], ep[1]), (ep[2], ep[3])])
    raise ValueError(f"Unknown flex montage type: {mtype!r}")


def load_montages(
    montage_names: List[str],
    project_dir: str,
    eeg_net: str,
    include_flex: bool = True,
) -> List[MontageConfig]:
    data = load_montage_data(project_dir)
    net = data.get("nets", {}).get(eeg_net, {})
    uni = net.get("uni_polar_montages", {})
    multi = net.get("multi_polar_montages", {})
    is_xyz = eeg_net in ("freehand", "flex_mode")

    montages = [
        (
            XYZMontage(name=n, electrode_pairs=multi.get(n) or uni[n], eeg_net=eeg_net)
            if is_xyz
            else LabelMontage(
                name=n, electrode_pairs=multi.get(n) or uni[n], eeg_net=eeg_net
            )
        )
        for n in montage_names
        if n in multi or n in uni
    ]

    if include_flex:
        for flex in load_flex_montages():
            montages.append(parse_flex_montage(flex))

    return montages


# ── Directory setup ────────────────────────────────────────────────────────────────


def setup_montage_directories(montage_dir: str, mode: SimulationMode) -> Dict[str, str]:
    dirs = {
        "montage_dir": montage_dir,
        "hf_dir": os.path.join(montage_dir, "high_Frequency"),
        "hf_mesh": os.path.join(montage_dir, "high_Frequency", "mesh"),
        "hf_niftis": os.path.join(montage_dir, "high_Frequency", "niftis"),
        "hf_analysis": os.path.join(montage_dir, "high_Frequency", "analysis"),
        "ti_mesh": os.path.join(montage_dir, "TI", "mesh"),
        "ti_niftis": os.path.join(montage_dir, "TI", "niftis"),
        "ti_surface_overlays": os.path.join(montage_dir, "TI", "surface_overlays"),
        "ti_montage_imgs": os.path.join(montage_dir, "TI", "montage_imgs"),
        "documentation": os.path.join(montage_dir, "documentation"),
    }
    if mode == SimulationMode.MTI:
        dirs["mti_montage_imgs"] = os.path.join(montage_dir, "mTI", "montage_imgs")
        dirs["shared_fields_mesh"] = os.path.join(montage_dir, "shared_fields", "mesh")
        dirs["shared_fields_niftis"] = os.path.join(
            montage_dir, "shared_fields", "niftis"
        )

    for path in dirs.values():
        os.makedirs(path, exist_ok=True)
    return dirs


# ── Montage visualization ───────────────────────────────────────────────────────────────


def run_montage_visualization(
    montage_name: str,
    simulation_mode: SimulationMode,
    eeg_net: str,
    output_dir: str,
    project_dir: str,
    logger,
    electrode_pairs: Optional[List] = None,
) -> None:
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
    montage: MontageConfig,
    documentation_dir: str,
    logger,
) -> None:
    path = os.path.join(documentation_dir, "config.json")
    data = {
        "subject_id": config.subject_id,
        "simulation_name": montage.name,
        "simulation_mode": montage.simulation_mode.value,
        "eeg_net": montage.eeg_net,
        "conductivity_type": config.conductivity_type.value,
        "electrode_pairs": montage.electrode_pairs,
        "is_xyz_montage": montage.is_xyz,
        "intensities": {"values": config.intensities.values},
        "electrode_geometry": {
            "shape": config.electrode.shape,
            "dimensions": config.electrode.dimensions,
            "gel_thickness": config.electrode.gel_thickness,
            "rubber_thickness": config.electrode.rubber_thickness,
        },
        "mapping_options": {
            "map_to_surf": config.map_to_surf,
            "map_to_vol": config.map_to_vol,
            "map_to_mni": config.map_to_mni,
            "map_to_fsavg": config.map_to_fsavg,
        },
        "mti_field_methods": [m.value for m in config.mti_field_methods],
        "direct_field_assumptions": {
            "pair_polarity": config.direct_field_pair_polarity,
            "phase_deg": config.direct_field_phase_deg,
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
    """Extract GM (tag 2) and WM (tag 1) meshes from a full-head mesh."""
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
    fields: Optional[List[str]] = None,
    skip_patterns: Optional[List[str]] = None,
) -> None:
    """Convert mesh files to NIfTI (subject + MNI space)."""
    from tit.tools.mesh2nii import convert_mesh_dir

    convert_mesh_dir(
        mesh_dir=mesh_dir,
        output_dir=output_dir,
        m2m_dir=m2m_dir,
        fields=fields,
        skip_patterns=skip_patterns,
    )


def convert_t1_to_mni(m2m_dir: str, subject_id: str, logger) -> None:
    """Convert T1 to MNI space (no-op if already done)."""
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
    shutil.move(src, dest)




# ── Simulation Orchestration ────────────────────────────────────────────────────────────────


def run_simulation(
    config: SimulationConfig,
    montages: List[MontageConfig],
    logger=None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> List[dict]:
    """
    Run TI/mTI simulations sequentially. Mode is auto-detected per montage.
    Returns list of result dicts: montage_name, montage_type, status, output_mesh.
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
    return logging.getLogger(name)
