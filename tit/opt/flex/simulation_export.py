"""Export flex-search results as regular Simulator outputs.

    Flex-search writes optimization-centric folders under ``flex-search/``.  When
    users request a mapped-electrode simulation, this module bridges the mapped
    flex result back into the standard
``Simulations/<montage>/`` layout so downstream viewer/analyzer workflows see
the same files they would get from running the Simulator tab manually.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict
from pathlib import Path

from tit.opt.config import FlexConfig
from tit.paths import get_path_manager
from tit.sim.config import Montage, SimulationConfig


def export_flex_run_to_simulations(
    config: FlexConfig, flex_run_dir: str, logger
) -> list[dict]:
    """Create Simulator-style folders for enabled flex final simulations.

    The mapped export intentionally uses the normal simulation pipeline rather
    than trying to reshape the optimizer summary mesh.  That is slower, but it
    guarantees the output folder has the same structure and post-processing
    products as a manual Simulator-tab run of the mapped flex montage.
    """
    montages = _build_export_montages(config, flex_run_dir, logger)
    if not montages:
        return []

    sim_config = _build_simulation_config(config, montages)
    logger.info(
        "Exporting %d flex result(s) to standard Simulations folders",
        len(montages),
    )

    from tit.sim.utils import run_simulation

    results = run_simulation(sim_config, logger=logger)
    for montage in montages:
        _copy_flex_documentation(config.subject_id, flex_run_dir, montage.name, logger)
        _export_roi_mask(config, flex_run_dir, montage.name, logger)
    return results


def _build_export_montages(
    config: FlexConfig, flex_run_dir: str, logger
) -> list[Montage]:
    montages: list[Montage] = []
    run_name = os.path.basename(os.path.normpath(flex_run_dir))
    run_id = _short_flex_run_id(config.subject_id, run_name)

    if config.enable_mapping and not config.disable_mapping_simulation:
        mapped = _mapped_montage(config, flex_run_dir, run_name, run_id, logger)
        if mapped is not None:
            montages.append(mapped)

    return montages


def _mapped_montage(
    config: FlexConfig, flex_run_dir: str, run_name: str, run_id: str, logger
) -> Montage | None:
    mapping_path = os.path.join(flex_run_dir, "electrode_mapping.json")
    if not os.path.isfile(mapping_path):
        logger.warning("Mapped flex export skipped; missing %s", mapping_path)
        return None

    with open(mapping_path) as f:
        data = json.load(f)

    labels = data.get("mapped_labels") or []
    if len(labels) < 4:
        logger.warning("Mapped flex export skipped; fewer than 4 mapped labels")
        return None

    eeg_net = data.get("eeg_net") or _eeg_net_filename(config.eeg_net)
    name = _build_flex_montage_name(run_name, run_id, "mapped")
    return Montage(
        name=name,
        mode=Montage.Mode.FLEX_MAPPED,
        electrode_pairs=[(labels[0], labels[1]), (labels[2], labels[3])],
        eeg_net=eeg_net,
        display_name=f"{run_name} | {run_id} | mapped",
    )


def _build_simulation_config(
    config: FlexConfig, montages: list[Montage]
) -> SimulationConfig:
    return SimulationConfig(
        subject_id=config.subject_id,
        montages=montages,
        conductivity=config.anisotropy_type,
        intensities=[config.current_mA, config.current_mA],
        electrode_shape=config.electrode.shape,
        electrode_dimensions=config.electrode.dimensions,
        gel_thickness=config.electrode.gel_thickness,
        aniso_maxratio=config.aniso_maxratio,
        aniso_maxcond=config.aniso_maxcond,
    )


def _copy_flex_documentation(
    subject_id: str, flex_run_dir: str, montage_name: str, logger
) -> None:
    pm = get_path_manager()
    doc_dir = (
        Path(pm.simulation(subject_id, montage_name)) / "documentation" / "flex-search"
    )
    doc_dir.mkdir(parents=True, exist_ok=True)

    for fname in (
        "flex_meta.json",
        "electrode_positions.json",
        "electrode_mapping.json",
        "summary.txt",
    ):
        src = Path(flex_run_dir) / fname
        if src.is_file():
            shutil.copy2(src, doc_dir / fname)

    try:
        with open(doc_dir / "export_source.json", "w") as f:
            json.dump({"flex_run_dir": flex_run_dir}, f, indent=2)
    except OSError as exc:
        logger.warning("Could not write flex export provenance: %s", exc)


def _export_roi_mask(
    config: FlexConfig, flex_run_dir: str, montage_name: str, logger
) -> None:
    """Save the flex ROI field beside the exported Simulator output."""
    opt_mesh = Path(flex_run_dir) / f"{config.subject_id}_tes_flex_opt_head_mesh.msh"
    if not opt_mesh.is_file():
        logger.warning("ROI export skipped; missing optimization mesh %s", opt_mesh)
        return

    pm = get_path_manager()
    sim_dir = Path(pm.simulation(config.subject_id, montage_name))
    roi_mesh_dir = sim_dir / "ROI" / "mesh"
    roi_nifti_dir = sim_dir / "ROI" / "niftis"
    roi_mesh_dir.mkdir(parents=True, exist_ok=True)
    roi_nifti_dir.mkdir(parents=True, exist_ok=True)

    roi_mesh = roi_mesh_dir / f"{montage_name}_ROI.msh"
    roi_prefix = roi_nifti_dir / f"{montage_name}_subject"

    try:
        _write_roi_only_mesh(str(opt_mesh), str(roi_mesh))
        from tit.tools.mesh2nii import msh_to_nifti

        msh_to_nifti(str(roi_mesh), pm.m2m(config.subject_id), str(roi_prefix), ["ROI"])
        _write_roi_metadata(config, roi_nifti_dir / f"{montage_name}_ROI.json")
    except Exception as exc:  # pragma: no cover - best-effort export
        logger.warning("Could not export flex ROI mask for %s: %s", montage_name, exc)


def _write_roi_only_mesh(input_mesh: str, output_mesh: str) -> None:
    import numpy as np
    from simnibs import mesh_io

    mesh = mesh_io.read_msh(input_mesh)
    roi = next((ed for ed in mesh.elmdata if ed.field_name == "ROI"), None)
    if roi is None:
        raise ValueError("optimization mesh does not contain an ROI field")

    keep = mesh.elm.elm_number[np.asarray(roi.value).reshape(-1) > 0]
    if len(keep) == 0:
        raise ValueError("ROI field contains no selected elements")

    cropped = mesh.crop_mesh(elements=keep)
    cropped.elmdata = [ed for ed in cropped.elmdata if ed.field_name == "ROI"]
    mesh_io.write_msh(cropped, output_mesh)


def _write_roi_metadata(config: FlexConfig, path: Path) -> None:
    roi = config.roi
    data = {
        "type": type(roi).__name__,
        "roi": asdict(roi),
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _eeg_net_filename(eeg_net: str | None) -> str:
    if not eeg_net:
        return ""
    return eeg_net if eeg_net.endswith(".csv") else f"{eeg_net}.csv"


def _short_flex_run_id(subject_id: str, run_name: str) -> str:
    raw = f"{subject_id}/{run_name}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:8]


def _build_flex_montage_name(run_name: str, run_id: str, electrode_type: str) -> str:
    safe_run_name = re.sub(r"[^A-Za-z0-9_]+", "_", str(run_name)).strip("_")
    safe_run_name = safe_run_name[:32] or "run"
    safe_type = re.sub(r"[^A-Za-z0-9_]+", "_", str(electrode_type)).strip("_")
    safe_type = safe_type or "mapped"
    return f"flex_{safe_run_name}_{run_id}_{safe_type}"
