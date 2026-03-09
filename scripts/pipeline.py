#!/usr/bin/env simnibs_python
"""Full TI-Toolbox pipeline: preprocess -> leadfield -> optimize -> simulate -> analyze."""

from tit.pre import run_pipeline
from tit.opt import FlexConfig, FlexElectrodeConfig, SphericalROI, run_flex_search
from tit.opt.leadfield import LeadfieldGenerator
from tit.sim import (
    SimulationConfig,
    ElectrodeConfig,
    IntensityConfig,
    ConductivityType,
    run_simulation,
    load_montages,
)
from tit.analyzer import Analyzer

PROJECT_DIR = "/mnt/000/"
SUBJECTS = ["101", "ernie"]
EEG_NET = "GSN-HydroCel-185.csv"

# ── 1. Preprocessing ─────────────────────────────────────────────────────────

# run_pipeline(
#     project_dir=PROJECT_DIR,
#     subject_ids=SUBJECTS,
#     convert_dicom=True,
#     run_recon=True,
#     create_m2m=True,
# )

# ── 2. Leadfield ─────────────────────────────────────────────────────────────

# for subject_id in SUBJECTS:
#     lfg = LeadfieldGenerator(subject_id, electrode_cap="EEG10-20_Okamoto_2004")
#     lf = lfg.generate()

# ── 3. Optimization ──────────────────────────────────────────────────────────

for subject_id in SUBJECTS:
    flex_config = FlexConfig(
        subject_id=subject_id,
        project_dir=PROJECT_DIR,
        goal="mean",
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexElectrodeConfig(),
        roi=SphericalROI(x=0, y=0, z=0, radius=10.0),
    )
    run_flex_search(flex_config)

# ── 4. Simulation ────────────────────────────────────────────────────────────

montages = load_montages(
    montage_names=["L_Insula"],
    project_dir=PROJECT_DIR,
    eeg_net=EEG_NET,
)

for subject_id in SUBJECTS:
    config = SimulationConfig(
        subject_id=subject_id,
        project_dir=PROJECT_DIR,
        conductivity_type=ConductivityType.SCALAR,
        intensities=IntensityConfig(values=[1.0, 1.0]),
        electrode=ElectrodeConfig(
            shape="ellipse",
            dimensions=[8.0, 8.0],
            gel_thickness=4.0,
            rubber_thickness=2.0,
        ),
    )
    run_simulation(config, montages)

# ── 5. Analysis ──────────────────────────────────────────────────────────────

for subject_id in SUBJECTS:
    analyzer = Analyzer(
        subject_id=subject_id,
        simulation="L_Insula",
        space="voxel",
    )
    result = analyzer.analyze_sphere(
        center=(0.0, 0.0, 0.0),
        radius=10.0,
        coordinate_space="MNI",
        visualize=True,
    )
