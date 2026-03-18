#!/usr/bin/env simnibs_python
"""
Blender visual exports: montage scenes, vector fields, cortical regions.

By Ido Haber
March 2026
"""

import os

from tit.paths import get_path_manager
from tit.blender import (
    MontageConfig,
    VectorConfig,
    RegionConfig,
    run_montage,
    run_vectors,
    run_regions,
)

pm = get_path_manager()

SUBJECTS = ["ernie"]
SIMULATION = "L_Insula"

# ── 1. Montage Publication ───────────────────────────────────────────────────

for subject_id in SUBJECTS:
    config = MontageConfig(
        subject_id=subject_id,
        simulation_name=SIMULATION,
        export_glb=True,
        electrode_diameter_mm=10.0,
        electrode_height_mm=6.0,
        show_full_net=True,
    )
    run_montage(config)

# ── 2. Vector Field Export ───────────────────────────────────────────────────

for subject_id in SUBJECTS:
    sim_base = pm.simulation(subject_id, SIMULATION)
    config = VectorConfig(
        mesh1=os.path.join(sim_base, "high_Frequency", "mesh", f"{subject_id}_TDCS_1_scalar.msh"),
        mesh2=os.path.join(sim_base, "high_Frequency", "mesh", f"{subject_id}_TDCS_2_scalar.msh"),
        output_dir=os.path.join(pm.ti_toolbox(), "visual_exports", f"sub-{subject_id}", SIMULATION, "vectors"),
        central_surface=pm.ti_central_surface(subject_id, SIMULATION),
        export_ti_normal=True,
        count=50_000,
    )
    run_vectors(config)

# ── 3. Cortical Region Export ────────────────────────────────────────────────

for subject_id in SUBJECTS:
    config = RegionConfig(
        m2m_dir=pm.m2m(subject_id),
        output_dir=os.path.join(pm.ti_toolbox(), "visual_exports", f"sub-{subject_id}", SIMULATION, "ply"),
        mesh=pm.ti_central_surface(subject_id, SIMULATION),
        format=RegionConfig.Format.PLY,
        atlas="DK40",
        field_name="TI_max",
        regions=["V1", "PT", "PO", "SP", "SM"],
    )
    run_regions(config)
