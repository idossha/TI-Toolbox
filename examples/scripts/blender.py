#!/usr/bin/env simnibs_python
"""
Blender visual exports: montage scenes, vector fields, cortical regions.

By Ido Haber
March 2026
"""

from tit.blender import (
    MontageConfig,
    VectorConfig,
    RegionConfig,
    run_montage,
    run_vectors,
    run_regions,
)

SUBJECTS = ["ernie"]
SIMULATION = "L_Insula"

# -- 1. Montage Publication ---------------------------------------------------

for subject_id in SUBJECTS:
    config = MontageConfig(
        subject_id=subject_id,
        simulation_name=SIMULATION,
        electrode_diameter_mm=10.0,
        electrode_height_mm=6.0,
        show_full_net=True,
    )
    run_montage(config)

# -- 2. Vector Field Export ----------------------------------------------------

for subject_id in SUBJECTS:
    config = VectorConfig(
        subject_id=subject_id,
        simulation_name=SIMULATION,
        export_ti_normal=True,
        count=50_000,
    )
    run_vectors(config)

# -- 3. Cortical Region Export -------------------------------------------------

for subject_id in SUBJECTS:
    config = RegionConfig(
        subject_id=subject_id,
        simulation_name=SIMULATION,
        format=RegionConfig.Format.PLY,
        atlas="DK40",
        field_name="TI_max",
        regions=["V1", "PT", "PO", "SP", "SM"],
    )
    run_regions(config)
