"""A synthetic project tree shaped like Dataset 000, for tests that call the real server.

``build_contract_project(root)`` writes, under ``root``, the files the catalog, viewer and
overview routes read, with the names and folder layout the runners produce (checked
against Dataset 000 on 2026-10-22: ``sub-101/Simulations/L_Insula/TI/niftis/*``,
``high_Frequency/niftis/101_TDCS_<i>_<cond>_<space>_magnE.nii.gz``, ``Analyses/Mesh|Voxel``,
``flex-search/<stamp>/flex_meta.json``, ``ex-search/<stamp>/run_config.json`` +
``final_output.csv``, ``derivatives/ti-toolbox/{reports,stats,nifti_average,
nilearn_visuals}``). Image payloads are placeholders (the host suite mocks nibabel); what
matters to the routes is which files exist and what the JSON/CSV sidecars say.

It covers: a TI simulation with MNI outputs and ``hf_peak``/``hf_sar``; an mTI
simulation; an anisotropic (``vn``) simulation; Mesh and Voxel analyses; a flex run with
an ``electrode_mapping_<net>.json``; an ex run; a report; group-comparison and
correlation stats runs; a NIfTI average and a nilearn visual; subject and MNI ROIs; a
free-hand config; two EEG caps.

Importable by any test (``from tests.contract_project import build_contract_project``);
it writes only under ``root``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from tit.paths import get_path_manager

SUBJECT = "101"
NET = "GSN-HydroCel-185.csv"
NET_1010 = "EEG10-10_UI_Jurak_2007.csv"
TI_SIM = "L_Insula"
MTI_SIM = "mTI_Thalamus"
VN_SIM = "AF3_vn"
MESH_ANALYSIS = "cortical_lh.insula_DK40"
VOXEL_ANALYSIS = "sphere_x-30.00_y10.00_z5.00_r10.0_MNI"
FLEX_RUN = "20260919_131736_879_1"
EX_RUN = "20260914_112857"
ROI = "L_Insula"
MNI_ROI = "R_Hippo_MNI"
FREEHAND = "four_points"
STATS_COMPARISON = "responders_vs_non"
STATS_CORRELATION = "efield_vs_improvement"
NIFTI_AVERAGE = "cohort_mean"
NILEARN_VISUAL = "L_Insula_glass_brain"


@dataclass(frozen=True)
class ContractProject:
    """Where the tree is and the identifiers a request needs to reach each part of it."""

    root: Path
    subject: str = SUBJECT
    net: str = NET
    ti_sim: str = TI_SIM
    mti_sim: str = MTI_SIM
    vn_sim: str = VN_SIM
    mesh_analysis: str = MESH_ANALYSIS
    voxel_analysis: str = VOXEL_ANALYSIS
    flex_run: str = FLEX_RUN
    ex_run: str = EX_RUN
    roi: str = ROI
    freehand: str = FREEHAND
    stats: tuple[tuple[str, str], ...] = field(
        default=(
            ("group_comparison", STATS_COMPARISON),
            ("correlation", STATS_CORRELATION),
        )
    )


def _write(path: str | Path, content: str | bytes = b"\0") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    with open(path, mode) as handle:
        handle.write(content)


def _json(path: str | Path, data: object) -> None:
    _write(path, json.dumps(data, indent=2))


def _sim_config(sim: str, *, mode: str, conductivity: str, pairs: list) -> dict:
    """The shape of ``documentation/config.json`` the simulator writes."""
    return {
        "subject_id": SUBJECT,
        "simulation_name": sim,
        "simulation_display_name": None,
        "simulation_mode": mode,
        "montage_mode": "net",
        "eeg_net": NET,
        "conductivity": conductivity,
        "electrode_pairs": pairs,
        "is_xyz_montage": False,
        "electrode_coordinates": [[-37.6, 66.4, 5.3]] * (2 * len(pairs)),
        "electrode_coordinate_source": f"eeg_positions/{NET}",
        "intensities": [1.0] * len(pairs),
        "electrode_geometry": {
            "shape": "ellipse",
            "dimensions": [8, 8],
            "gel_thickness": 4,
            "rubber_thickness": 2.0,
        },
        "mapping_options": {
            "map_to_surf": True,
            "map_to_vol": True,
            "map_to_mni": True,
            "map_to_fsavg": False,
        },
        "tissues_in_niftis": "all",
        "created_at": "2026-09-23T13:13:20.899598",
    }


def _analysis(sim_dir: str, space: str, name: str, analysis: dict) -> None:
    folder = os.path.join(sim_dir, "Analyses", space, name)
    _json(os.path.join(folder, "analysis.json"), analysis)
    _write(
        os.path.join(folder, "results.csv"),
        "Metric,Value\n"
        "roi_mean,0.112\nroi_max,0.231\nroi_min,0.011\n"
        "gm_mean,0.081\ngm_max,0.402\n"
        "percentile_95,0.198\npercentile_99,0.221\npercentile_99_9,0.229\n"
        "focality_50_area,812.5\nfocality_75_area,301.2\n"
        "focality_90_area,95.4\nfocality_95_area,40.1\n",
    )
    _write(os.path.join(folder, "roi.png"), b"\x89PNG\r\n\x1a\n")


def build_contract_project(root: Path) -> ContractProject:
    """Write the synthetic project under ``root`` and return its identifiers."""
    os.makedirs(root, exist_ok=True)
    pm = get_path_manager(str(root))
    sid = SUBJECT

    # -- head model, caps, montages, ROIs, free-hand configs, leadfield ----------
    m2m = pm.m2m(sid)
    _write(os.path.join(m2m, "T1.nii.gz"))
    _write(os.path.join(m2m, f"{sid}.msh"))
    caps = pm.eeg_positions(sid)
    _write(
        os.path.join(caps, NET),
        "".join(
            f"Electrode,{x:.1f},{y:.1f},{z:.1f},E{i:03d}\n"
            for i, (x, y, z) in enumerate(
                [
                    (-37.6, 66.4, 5.3),
                    (10.3, 73.0, 9.9),
                    (-80.7, -48.3, -59.5),
                    (-87.9, -14.1, -24.0),
                ],
                start=1,
            )
        ),
    )
    _write(
        os.path.join(caps, NET_1010),
        "Electrode,-26.1,113.7,19.1,Fp1\nElectrode,26.1,113.7,19.1,Fp2\n"
        "Electrode,-60.2,30.1,70.4,C3\nElectrode,60.2,30.1,70.4,C4\n",
    )
    _write(os.path.join(caps, "Fiducials.csv"), "Fiducial,0.0,90.0,0.0,Nz\n")
    _json(
        pm.montage_config(),
        {
            "nets": {
                NET: {
                    "uni_polar_montages": {
                        TI_SIM: [["E001", "E002"], ["E003", "E004"]]
                    },
                    "multi_polar_montages": {
                        MTI_SIM: [
                            ["E001", "E002"],
                            ["E003", "E004"],
                            ["E002", "E003"],
                            ["E004", "E001"],
                        ]
                    },
                }
            }
        },
    )
    rois = pm.rois(sid)
    _write(os.path.join(rois, f"{ROI}.csv"), "-30.0,10.0,5.0\n")
    _write(os.path.join(rois, f"{MNI_ROI}.csv"), "28.0,-22.0,-14.0\n")
    _write(os.path.join(rois, "roi_list.txt"), f"{ROI}.csv\n{MNI_ROI}.csv\n")
    _json(
        os.path.join(m2m, "stim_configs", f"{FREEHAND}.json"),
        {
            "name": FREEHAND,
            "type": "U",
            "electrode_positions": {
                "A": [-37.6, 66.4, 5.3],
                "B": [10.3, 73.0, 9.9],
                "C": [-80.7, -48.3, -59.5],
                "D": [-87.9, -14.1, -24.0],
            },
        },
    )
    _write(
        os.path.join(pm.leadfields(sid), f"{sid}_leadfield_{NET[:-4]}.hdf5"),
        b"0" * 1024,
    )

    # -- TI simulation: subject + MNI volumes, hf_peak/hf_sar, HF fields ----------
    ti_dir = pm.simulation(sid, TI_SIM)
    _json(
        os.path.join(ti_dir, "documentation", "config.json"),
        _sim_config(
            TI_SIM,
            mode="TI",
            conductivity="scalar",
            pairs=[["E001", "E002"], ["E003", "E004"]],
        ),
    )
    for prefix in ("", "grey_", "white_"):
        for space in ("subject", "MNI_MNI"):
            for fld in ("TI_max", "hf_peak", "hf_sar"):
                _write(
                    os.path.join(
                        ti_dir,
                        "TI",
                        "niftis",
                        f"{prefix}{TI_SIM}_TI_{space}_{fld}.nii.gz",
                    )
                )
    for name in (f"{TI_SIM}_TI.msh", f"{TI_SIM}_normal.msh", f"grey_{TI_SIM}_TI.msh"):
        _write(os.path.join(ti_dir, "TI", "mesh", name))
    _write(
        os.path.join(
            ti_dir, "TI", "montage_imgs", f"{TI_SIM}_highlighted_visualization.png"
        ),
        b"\x89PNG\r\n\x1a\n",
    )
    for i in (1, 2):
        for space in ("subject", "MNI_MNI"):
            _write(
                os.path.join(
                    ti_dir,
                    "high_Frequency",
                    "niftis",
                    f"{sid}_TDCS_{i}_scalar_{space}_magnE.nii.gz",
                )
            )
        _write(
            os.path.join(ti_dir, "high_Frequency", "mesh", f"{sid}_TDCS_{i}_scalar.msh")
        )
    _analysis(
        ti_dir,
        "Mesh",
        MESH_ANALYSIS,
        {
            "analysis_type": "cortical",
            "space": "mesh",
            "field_name": "TI_max",
            "atlas": "DK40",
            "region": "lh.insula",
            "coordinate_space": "subject",
        },
    )
    _analysis(
        ti_dir,
        "Voxel",
        VOXEL_ANALYSIS,
        {
            "analysis_type": "spherical",
            "space": "voxel",
            "field_name": "TI_max",
            "center": [-30.0, 10.0, 5.0],
            "radius": 10.0,
            "coordinate_space": "MNI",
        },
    )

    # -- mTI simulation -----------------------------------------------------------
    mti_dir = pm.simulation(sid, MTI_SIM)
    _json(
        os.path.join(mti_dir, "documentation", "config.json"),
        _sim_config(
            MTI_SIM,
            mode="mTI",
            conductivity="scalar",
            pairs=[
                ["E001", "E002"],
                ["E003", "E004"],
                ["E002", "E003"],
                ["E004", "E001"],
            ],
        ),
    )
    for space in ("subject", "MNI_MNI"):
        _write(
            os.path.join(
                mti_dir, "mTI", "niftis", f"{MTI_SIM}_mTI_{space}_mTI_max.nii.gz"
            )
        )
    _write(os.path.join(mti_dir, "mTI", "mesh", f"{MTI_SIM}_mTI.msh"))
    for pair in ("A", "B"):
        _write(
            os.path.join(
                mti_dir, "TI", "niftis", f"{MTI_SIM}_TI_{pair}_subject_TI_max.nii.gz"
            )
        )

    # -- anisotropic (vn) simulation ---------------------------------------------
    vn_dir = pm.simulation(sid, VN_SIM)
    _json(
        os.path.join(vn_dir, "documentation", "config.json"),
        _sim_config(
            VN_SIM,
            mode="TI",
            conductivity="vn",
            pairs=[["E001", "E003"], ["E002", "E004"]],
        ),
    )
    _write(os.path.join(vn_dir, "TI", "niftis", f"{VN_SIM}_TI_subject_TI_max.nii.gz"))
    _write(os.path.join(vn_dir, "TI", "mesh", f"{VN_SIM}_TI.msh"))
    for i in (1, 2):
        _write(
            os.path.join(
                vn_dir,
                "high_Frequency",
                "niftis",
                f"{sid}_TDCS_{i}_vn_subject_magnE.nii.gz",
            )
        )

    # -- flex and ex runs ----------------------------------------------------------
    flex_dir = pm.flex_search_run(sid, FLEX_RUN)
    _json(
        os.path.join(flex_dir, "flex_meta.json"),
        {
            "version": 1,
            "created": "2026-09-19T14:03:00",
            "subject_id": sid,
            "goal": "mean",
            "postproc": "max_TI",
            "current_mA": 1.0,
            "electrode": {"shape": "ellipse", "dimensions": [8, 8], "gel_thickness": 4},
            "roi": {
                "type": "spherical",
                "x": -30.0,
                "y": 10.0,
                "z": 5.0,
                "radius": 10.0,
            },
            "label": "L_Insula sphere",
            "n_multistart": 1,
            "best_value": -0.142,
        },
    )
    _json(
        os.path.join(flex_dir, "electrode_positions.json"),
        {
            "optimized_positions": [
                [-37.6, 66.4, 5.3],
                [10.3, 73.0, 9.9],
                [-80.7, -48.3, -59.5],
                [-87.9, -14.1, -24.0],
            ],
            "channel_array_indices": [[0, 0], [0, 1], [1, 0], [1, 1]],
            "current_mA": [1.0, -1.0, 1.0, -1.0],
        },
    )
    _json(
        os.path.join(flex_dir, f"electrode_mapping_{NET[:-4]}.json"),
        {
            "optimized_positions": [
                [-37.6, 66.4, 5.3],
                [10.3, 73.0, 9.9],
                [-80.7, -48.3, -59.5],
                [-87.9, -14.1, -24.0],
            ],
            "channel_array_indices": [[0, 0], [0, 1], [1, 0], [1, 1]],
            "mapped_labels": ["E001", "E002", "E003", "E004"],
            "mapped_positions": [
                [-37.6, 66.4, 5.3],
                [10.3, 73.0, 9.9],
                [-80.7, -48.3, -59.5],
                [-87.9, -14.1, -24.0],
            ],
            "distances": [0.0, 0.0, 0.0, 0.0],
            "eeg_net": NET[:-4],
        },
    )
    ex_dir = pm.ex_search_run(sid, EX_RUN)
    _json(
        os.path.join(ex_dir, "run_config.json"),
        {
            "subject_id": sid,
            "leadfield_hdf": f"/x/{sid}_leadfield_{NET[:-4]}.hdf5",
            "roi_name": f"{ROI}.csv",
            "total_current": 2.0,
            "current_step": 0.5,
        },
    )
    _write(
        os.path.join(ex_dir, "final_output.csv"),
        "Montage,Current_Ch1_mA,Current_Ch2_mA,TImax_ROI,TImean_ROI,TImean_GM,Focality,Composite_Index\n"
        "E001_E002 <> E003_E004,1.0,1.0,0.30,0.20,0.10,1.5,0.30\n"
        "E001_E003 <> E002_E004,1.5,0.5,0.40,0.25,0.12,1.6,0.40\n",
    )

    # -- project-level outputs: reports, stats, averages, nilearn, notes ----------
    _write(
        os.path.join(
            pm.reports(),
            f"sub-{sid}",
            f"simulation_report_{TI_SIM}_20260923_131320.html",
        ),
        "<!doctype html><title>Simulation report</title><h1>L_Insula</h1>",
    )
    for kind, name in (
        ("group_comparison", STATS_COMPARISON),
        ("correlation", STATS_CORRELATION),
    ):
        run = os.path.join(pm.ti_toolbox(), "stats", kind, name)
        _write(os.path.join(run, "analysis_summary.txt"), "Significant clusters: 1\n")
        _write(
            os.path.join(run, "significant_clusters.csv"),
            "cluster,size,mass,peak_x,peak_y,peak_z\n1,42,61.3,-30,10,5\n",
        )
        _write(os.path.join(run, "pvalues_map.nii.gz"))
    _write(
        os.path.join(pm.ti_toolbox(), "nifti_average", NIFTI_AVERAGE, "average.nii.gz")
    )
    _write(
        os.path.join(
            pm.ti_toolbox(), "nilearn_visuals", NILEARN_VISUAL, "glass_brain.png"
        ),
        b"\x89PNG\r\n\x1a\n",
    )
    _write(os.path.join(pm.ti_toolbox(), "notes.txt"), "Pilot cohort.\n")

    return ContractProject(root=Path(root))
