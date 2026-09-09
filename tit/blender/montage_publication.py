#!/usr/bin/env simnibs_python
"""
Montage publication asset builder.

This module owns the Blender/montage-publication business logic.
"""

import json
import logging
import os
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from dataclasses import asdict, dataclass

import numpy as np

from tit.paths import get_path_manager
from tit import constants as const
from tit.blender import utils as be_utils
from tit.blender.io import read_binary_stl, write_binary_stl

logger = logging.getLogger(__name__)


def configure_montage_loggers(parent_logger: logging.Logger) -> None:
    """
    Configure all montage publication related loggers to use the parent logger's handlers.

    This ensures consistent logging behavior between CLI and GUI interfaces.

    Args:
        parent_logger: The parent logger whose handlers should be used
    """
    names = [
        "tit.blender.montage_publication",
        "tit.blender.electrode_placement",
        "tit.blender.utils",
        "tit.blender.scene_setup",
        "simnibs",
    ]
    for name in names:
        child = logging.getLogger(name)
        child.handlers = list(parent_logger.handlers)
        child.setLevel(parent_logger.level or logging.INFO)
        child.propagate = False


def _find_tetrahedral_mesh(sim_dir: str) -> str:
    candidates: list[str] = []

    ti_mesh_dir = os.path.join(sim_dir, "TI", "mesh")
    if os.path.isdir(ti_mesh_dir):
        for f in os.listdir(ti_mesh_dir):
            if f.endswith("_TI_final.msh") or f.endswith("_T1.msh"):
                candidates.append(os.path.join(ti_mesh_dir, f))

    hf_mesh_dir = os.path.join(sim_dir, "high_Frequency", "mesh")
    if os.path.isdir(hf_mesh_dir):
        for f in os.listdir(hf_mesh_dir):
            if f.endswith(".msh"):
                candidates.append(os.path.join(hf_mesh_dir, f))

    if not candidates:
        raise FileNotFoundError(f"No tetrahedral mesh found under {sim_dir}")
    return sorted(candidates)[0]


def _find_central_surface_mesh(
    sim_dir: str, subject_id: str, simulation_name: str
) -> str:
    pm = get_path_manager()
    path = pm.ti_central_surface(subject_id, simulation_name)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Central surface not found at {path}. Run simulation first."
        )
    return path


def export_scalp_stl_from_sim(
    sim_dir: str, *, output_stl: str, skin_tag: int = 1005, mesh_path: str | None = None
) -> str:
    """Extract the scalp surface from a simulation mesh and write it as STL.

    Parameters
    ----------
    sim_dir : str
        Path to the simulation directory containing tetrahedral meshes.
    output_stl : str
        Destination path for the binary STL file.
    skin_tag : int, optional
        Element tag identifying scalp tissue in the mesh (default 1005).
    mesh_path : str or None
        Canonical PathManager mesh when available; otherwise use legacy discovery.

    Returns
    -------
    str
        The *output_stl* path that was written.
    """
    tetra_mesh = mesh_path or _find_tetrahedral_mesh(sim_dir)
    vertices, faces = be_utils.extract_scalp_from_msh(tetra_mesh, skin_tag=skin_tag)
    os.makedirs(os.path.dirname(output_stl), exist_ok=True)
    write_binary_stl(output_stl, vertices, faces, header_text="TI-Toolbox Scalp Mesh")
    return output_stl


def export_gm_stl_from_sim(
    sim_dir: str, *, subject_id: str, simulation_name: str, output_stl: str
) -> str:
    """Extract the grey-matter central surface from a simulation and write it as STL.

    Parameters
    ----------
    sim_dir : str
        Path to the simulation directory.
    subject_id : str
        Subject identifier (without the ``sub-`` prefix).
    simulation_name : str
        Name of the simulation whose central surface mesh is used.
    output_stl : str
        Destination path for the binary STL file.

    Returns
    -------
    str
        The *output_stl* path that was written.
    """
    import numpy as np
    import simnibs

    central_mesh_path = _find_central_surface_mesh(sim_dir, subject_id, simulation_name)
    mesh = simnibs.read_msh(central_mesh_path)

    triangular = mesh.elm.elm_type == 2
    triangle_nodes = mesh.elm.node_number_list[triangular][:, :3]
    if len(triangle_nodes) == 0:
        raise ValueError("No triangular surface elements found in central surface mesh")

    unique_nodes = np.unique(triangle_nodes.flatten())
    node_to_idx = {old_idx: new_idx for new_idx, old_idx in enumerate(unique_nodes)}

    vertices = mesh.nodes.node_coord[unique_nodes - 1]
    faces = np.array([[node_to_idx[n] for n in tri] for tri in triangle_nodes])

    os.makedirs(os.path.dirname(output_stl), exist_ok=True)
    write_binary_stl(
        output_stl, vertices, faces, header_text="TI-Toolbox GM Surface Mesh"
    )
    return output_stl


def _resolve_eeg_net_csv(*, subject_id: str, eeg_net_name: str) -> str:
    pm = get_path_manager()
    eeg_dir = pm.eeg_positions(subject_id)
    if not eeg_dir:
        raise FileNotFoundError(
            f"EEG positions directory not found for subject {subject_id}"
        )
    path = os.path.join(eeg_dir, eeg_net_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"EEG net CSV not found: {path}")
    return path


@dataclass(frozen=True)
class MontageResult:
    """Paths produced by a montage publication build.

    Attributes
    ----------
    scalp_stl : str
        Path to the exported scalp STL mesh.
    gm_stl : str
        Path to the exported grey-matter STL mesh.
    electrodes_blend : str
        Path to the intermediate Blender file with placed electrodes.
    final_blend : str
        Path to the final publication-ready Blender scene.
    """

    scalp_stl: str
    gm_stl: str
    electrodes_blend: str
    final_blend: str


def run_montage(
    cfg: "MontageConfig",
    *,
    logger_override: logging.Logger | None = None,
) -> MontageResult:
    """Create a publication-ready montage Blender scene (.blend).

    This is the shared entrypoint for CLI and GUI callers.
    """
    from tit.blender.config import MontageConfig  # noqa: F811 (deferred)
    from tit.telemetry import track_operation
    from tit import constants as _const

    with track_operation(_const.TELEMETRY_OP_BLENDER_MONTAGE):
        subject_id = cfg.subject_id.strip()
        simulation_name = cfg.simulation_name.strip()

        if logger_override is not None:
            configure_montage_loggers(logger_override)

        return build_montage_publication_blend(
            subject_id=subject_id,
            simulation_name=simulation_name,
            output_dir=cfg.output_dir,
            show_full_net=bool(cfg.show_full_net),
            electrode_diameter_mm=float(cfg.electrode_diameter_mm),
            electrode_height_mm=float(cfg.electrode_height_mm),
        )


def build_montage_publication_blend(
    *,
    subject_id: str,
    simulation_name: str,
    output_dir: str | None = None,
    show_full_net: bool = True,
    electrode_diameter_mm: float = 10.0,
    electrode_height_mm: float = 6.0,
) -> MontageResult:
    """Build a complete publication-ready montage Blender scene from scratch.

    Parameters
    ----------
    subject_id : str
        Subject identifier (without the ``sub-`` prefix).
    simulation_name : str
        Name of the simulation to visualise.
    output_dir : str or None, optional
        Directory for all output files.  When *None*, a default BIDS-derivative
        path is constructed via :class:`PathManager`.
    show_full_net : bool, optional
        If *True*, render the entire EEG net; otherwise only active electrodes.
    electrode_diameter_mm : float, optional
        Diameter of each electrode cylinder in mm (default 10.0).
    electrode_height_mm : float, optional
        Height of each electrode cylinder in mm (default 6.0).

    Returns
    -------
    MontageResult
        Dataclass with paths to all generated assets.
    """
    pm = get_path_manager()
    sim_dir = pm.simulation(subject_id, simulation_name)
    if not sim_dir:
        raise FileNotFoundError(
            f"Simulation directory not found for {subject_id}/{simulation_name}"
        )

    cfg = be_utils.load_simulation_config(subject_id, simulation_name)
    if not cfg:
        raise FileNotFoundError(
            f"Simulation config.json not found for {subject_id}/{simulation_name} (expected under documentation/config.json)."
        )

    if output_dir is None:
        if not pm.project_dir:
            raise RuntimeError(
                "Project directory is not set (PathManager.project_dir is None)."
            )
        output_dir = os.path.join(
            pm.project_dir,
            const.DIR_DERIVATIVES,
            const.DIR_TI_TOOLBOX,
            "visual_exports",
            f"{const.PREFIX_SUBJECT}{subject_id}",
            "montage_publication",
        )
    os.makedirs(output_dir, exist_ok=True)

    scalp_stl = os.path.join(output_dir, "scalp.stl")
    gm_stl = os.path.join(output_dir, "gm.stl")

    canonical_mesh = pm.ti_mesh(subject_id, simulation_name)
    export_scalp_stl_from_sim(
        sim_dir,
        output_stl=scalp_stl,
        mesh_path=canonical_mesh if os.path.isfile(canonical_mesh) else None,
    )
    export_gm_stl_from_sim(
        sim_dir,
        subject_id=subject_id,
        simulation_name=simulation_name,
        output_stl=gm_stl,
    )

    eeg_net = cfg.get("eeg_net")
    if not eeg_net:
        raise KeyError("config.json missing required field: 'eeg_net'")
    electrode_pairs = cfg.get("electrode_pairs") or []

    eeg_csv = _resolve_eeg_net_csv(subject_id=subject_id, eeg_net_name=str(eeg_net))
    # Packaged with tit.blender so source and installed API calls share the same template.
    electrode_template = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "Electrode.blend"
    )

    subject_m2m = pm.m2m(subject_id)
    if not subject_m2m or not os.path.isdir(subject_m2m):
        raise FileNotFoundError(f"m2m directory not found for subject {subject_id}")
    subject_msh = os.path.join(subject_m2m, f"{subject_id}.msh")

    from tit.blender.electrode_placement import (
        ElectrodePlacementConfig,
    )

    ele_cfg = ElectrodePlacementConfig(
        subject_id=subject_id,
        electrode_csv_path=eeg_csv,
        electrode_blend_path=electrode_template,
        output_dir=output_dir,
        subject_msh_path=subject_msh if os.path.exists(subject_msh) else None,
        scalp_stl_path=scalp_stl,
        electrode_diameter_mm=electrode_diameter_mm,
        electrode_height_mm=electrode_height_mm,
        electrode_size=None,
        montage_pairs=[
            tuple(p)
            for p in electrode_pairs
            if isinstance(p, (list, tuple)) and len(p) >= 2
        ],
        show_full_net=show_full_net,
    )

    # Preserve the old subject-MSH precedence and float64 coordinates. STL is an output,
    # not the transport: an STL roundtrip would quantize vertices before placement.
    if ele_cfg.subject_msh_path:
        vertices, faces = be_utils.extract_scalp_from_msh(
            ele_cfg.subject_msh_path, ele_cfg.skin_tag
        )
    else:
        vertices, faces = read_binary_stl(scalp_stl)
    electrodes = list(read_electrodes(eeg_csv))
    final_blend = os.path.join(
        output_dir, f"{subject_id}_{simulation_name}_montage_publication.blend"
    )
    with tempfile.TemporaryDirectory(prefix="tit-montage-") as temporary:
        geometry = os.path.join(temporary, "scalp.npz")
        np.savez(geometry, vertices=vertices, faces=faces)
        placement = asdict(ele_cfg)
        placement["subject_msh_path"] = None
        manifest = {
            "subject_id": subject_id,
            "simulation_name": simulation_name,
            "output_dir": output_dir,
            "gm_stl": gm_stl,
            "geometry": geometry,
            "placement": placement,
            "electrodes": electrodes,
        }
        manifest_path = os.path.join(temporary, "montage.json")
        with open(manifest_path, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, allow_nan=False)
        renderer = Path(__file__).with_name("montage_scene.py")
        executable = os.environ.get("TIT_BLENDER_BIN", "/opt/blender/blender")
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH"}
        }
        # Inherit the parent's process group: cancelling a job must also stop Blender.
        subprocess.run(
            [
                executable,
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python",
                str(renderer),
                "--",
                manifest_path,
            ],
            check=True,
            env=env,
        )
    for output in (ele_cfg.output_blend_path, final_blend):
        if not Path(output).is_file() or Path(output).stat().st_size == 0:
            raise RuntimeError(f"Blender did not create its expected output: {output}")
    return MontageResult(scalp_stl, gm_stl, ele_cfg.output_blend_path, final_blend)


def read_electrodes(csv_path: str) -> Iterator[list[str | float]]:
    """Prepare exactly the electrode rows the prior Blender-side reader selected."""
    from simnibs.utils.csv_reader import read_csv_positions

    types, coordinates, _extra, names, _columns, _header = read_csv_positions(csv_path)
    for kind, coordinate, name in zip(types, coordinates, names):
        if kind in ("Electrode", "ReferenceElectrode"):
            yield [
                name if name else "Electrode",
                *(float(value) for value in coordinate),
            ]
