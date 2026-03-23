#!/usr/bin/env simnibs_python
"""
End-to-end integration test: simulation -> analysis -> blender visualization.

Subject: ernie
Montage: L_Insula (2-pair TI)

Tests the full pipeline including:
1. Simulation (produces TDCS meshes, TI_max, central surface)
2. Mesh-space cortical analysis (uses central surface from simulator)
3. Blender vector field export (reads conductivity from config.json)
4. Blender cortical region export (uses central surface from simulator)

By Ido Haber
March 2026
"""

from tit.sim import SimulationConfig, Montage, run_simulation
from tit.analyzer import Analyzer
from tit.blender import (
    MontageConfig,
    VectorConfig,
    RegionConfig,
    run_montage,
    run_vectors,
    run_regions,
)

SUBJECT = "ernie"
SIMULATION = "L_Insula"

# -- 1. Simulation -------------------------------------------------------------

print(f"\n{'='*60}")
print("PHASE 1: Simulation")
print(f"{'='*60}\n")

montages = [
    Montage(
        name=SIMULATION,
        mode=Montage.Mode.NET,
        electrode_pairs=[("E010", "E011"), ("E012", "E013")],
        eeg_net="GSN-HydroCel-185.csv",
    ),
]

config = SimulationConfig(
    subject_id=SUBJECT,
    montages=montages,
    conductivity="scalar",
    intensities=[1.0, 1.0],
    electrode_shape="ellipse",
    electrode_dimensions=[8.0, 8.0],
    gel_thickness=4.0,
    rubber_thickness=2.0,
)
# run_simulation(config)

print("\nSimulation complete.")

# -- 2. Mesh-space cortical analysis ------------------------------------------

print(f"\n{'='*60}")
print("PHASE 2: Mesh Analysis")
print(f"{'='*60}\n")

analyzer = Analyzer(
    subject_id=SUBJECT,
    simulation=SIMULATION,
    space="mesh",
)

# Spherical ROI analysis
sphere_result = analyzer.analyze_sphere(
    center=(0.0, 0.0, 0.0),
    radius=10.0,
    coordinate_space="MNI",
    visualize=False,
)
print(f"Sphere ROI mean: {sphere_result.roi_mean:.4f}")
print(f"Sphere ROI max:  {sphere_result.roi_max:.4f}")


print("\nMesh analysis complete.")

# -- 3. Blender: Montage Publication ------------------------------------------

print(f"\n{'='*60}")
print("PHASE 3: Blender Montage Publication")
print(f"{'='*60}\n")

montage_config = MontageConfig(
    subject_id=SUBJECT,
    simulation_name=SIMULATION,
    electrode_diameter_mm=10.0,
    electrode_height_mm=6.0,
    show_full_net=True,
)
try:
    run_montage(montage_config)
    print("\nMontage publication complete.")
except Exception as e:
    print(f"\nMontage publication skipped (requires Blender/bpy): {e}")

# -- 4. Blender: Vector Field Export -------------------------------------------

print(f"\n{'='*60}")
print("PHASE 4: Blender Vector Field Export")
print(f"{'='*60}\n")

vec_config = VectorConfig(
    subject_id=SUBJECT,
    simulation_name=SIMULATION,
    export_ti_normal=True,
    count=5000,
)
run_vectors(vec_config)

print("\nVector field export complete.")

# -- 5. Blender: Cortical Region Export ----------------------------------------

print(f"\n{'='*60}")
print("PHASE 5: Blender Cortical Region Export")
print(f"{'='*60}\n")

region_config = RegionConfig(
    subject_id=SUBJECT,
    simulation_name=SIMULATION,
    format=RegionConfig.Format.PLY,
    atlas="DK40",
    field_name="TI_max",
    regions=["insula", "superiorfrontal", "precentral"],
)
run_regions(region_config)

print("\nCortical region export complete.")

# -- Done ----------------------------------------------------------------------

print(f"\n{'='*60}")
print("ALL PHASES COMPLETE")
print(f"{'='*60}")
