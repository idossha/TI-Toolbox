#!/usr/bin/env simnibs_python
"""
Blender visual exports: montage scenes, vector fields, cortical regions.

By Ido Haber
March 2026
"""

import tit

tit.init()

from tit.blender import (
    MontageConfig,
    VectorConfig,
    RegionConfig,
    run_montage,
    run_vectors,
    run_regions,
)

PROJECT_DIR = "/mnt/000"
SUBJECTS = ["ernie"]
SIMULATION = "L_Insula"

# ── 1. Montage Publication ───────────────────────────────────────────────────

for subject_id in SUBJECTS:
    config = MontageConfig(
        subject_id=subject_id,
        simulation_name=SIMULATION,
        project_dir=PROJECT_DIR,
        export_glb=True,
        electrode_diameter_mm=10.0,
        electrode_height_mm=6.0,
        show_full_net=True,
    )
    run_montage(config)

# ── 2. Vector Field Export ───────────────────────────────────────────────────

for subject_id in SUBJECTS:
    sim_base = f"{PROJECT_DIR}/derivatives/SimNIBS/sub-{subject_id}/Simulations/{SIMULATION}"
    config = VectorConfig(
        mesh1=f"{sim_base}/high_Frequency/mesh/{subject_id}_TDCS_1_scalar.msh",
        mesh2=f"{sim_base}/high_Frequency/mesh/{subject_id}_TDCS_2_scalar.msh",
        output_dir=f"{PROJECT_DIR}/derivatives/ti-toolbox/visual_exports/sub-{subject_id}/{SIMULATION}/vectors",
        central_surface=f"{sim_base}/TI/mesh/surfaces/{SIMULATION}_TI_central.msh",
        export_ti_normal=True,
        count=50_000,
    )
    run_vectors(config)

# ── 3. Cortical Region Export ────────────────────────────────────────────────

for subject_id in SUBJECTS:
    sim_base = f"{PROJECT_DIR}/derivatives/SimNIBS/sub-{subject_id}/Simulations/{SIMULATION}"
    config = RegionConfig(
        m2m_dir=f"{PROJECT_DIR}/derivatives/SimNIBS/sub-{subject_id}/m2m_{subject_id}",
        output_dir=f"{PROJECT_DIR}/derivatives/ti-toolbox/visual_exports/sub-{subject_id}/{SIMULATION}/ply",
        mesh=f"{sim_base}/TI/mesh/surfaces/{SIMULATION}_TI_central.msh",
        format=RegionConfig.Format.PLY,
        atlas="DK40",
        field_name="TI_max",
    )
    run_regions(config)
