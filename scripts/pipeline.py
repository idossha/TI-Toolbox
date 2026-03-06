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
SUBJECT_ID = "101"
EEG_NET = "GSN-HydroCel-128.csv"

# ── 1. Preprocessing ─────────────────────────────────────────────────────────

# run_pipeline(
#     project_dir=PROJECT_DIR,
#     subject_ids=[SUBJECT_ID],
#     convert_dicom=True,
#     run_recon=True,
#     create_m2m=True,
# )

# ── 2. Leadfield ─────────────────────────────────────────────────────────────

# lfg = LeadfieldGenerator(SUBJECT_ID, electrode_cap="EEG10-20_Okamoto_2004")
# lf = lfg.generate()

# ── 3. Optimization ──────────────────────────────────────────────────────────

# flex_config = FlexConfig(
#     subject_id=SUBJECT_ID,
#     project_dir=PROJECT_DIR,
#     goal="mean",
#     postproc="max_TI",
#     current_mA=2.0,
#     electrode=FlexElectrodeConfig(),
#     roi=SphericalROI(x=0, y=0, z=0, radius=10.0),
# )
# run_flex_search(flex_config)

# ── 4. Simulation ────────────────────────────────────────────────────────────

# config = SimulationConfig(
#     subject_id=SUBJECT_ID,
#     project_dir=PROJECT_DIR,
#     conductivity_type=ConductivityType.SCALAR,
#     intensities=IntensityConfig(pair1=1.0, pair2=1.0),
#     electrode=ElectrodeConfig(
#         shape="ellipse",
#         dimensions=[8.0, 8.0],
#         thickness=4.0,
#         sponge_thickness=2.0,
#     ),
# )
# montages = load_montages(
#     montage_names=["L_Insula"],
#     project_dir=PROJECT_DIR,
#     eeg_net=EEG_NET,
# )
# run_simulation(config, montages)

# ── 5. Analysis ──────────────────────────────────────────────────────────────

# analyzer = Analyzer(
#     subject_id=SUBJECT_ID,
#     simulation="L_Insula",
#     space="voxel",
# )
# result = analyzer.analyze_sphere(
#     center=(0.0, 0.0, 0.0),
#     radius=10.0,
#     coordinate_space="MNI",
#     visualize=True,
# )
