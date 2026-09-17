#!/usr/bin/env simnibs_python
"""
Full TI-Toolbox pipeline:

    preprocess -> optimize -> simulate -> analyze.

By Ido Haber
March 2026
"""

from tit.analyzer import Analyzer
from tit.opt import FlexConfig, run_flex_search
from tit.pre import run_pipeline
from tit.sim import SimulationConfig, load_montages, run_simulation

SUBJECTS = ["ernie"]
EEG_NET = "GSN-HydroCel-185.csv"

# ── 1. Preprocessing ─────────────────────────────────────────────────────────

run_pipeline(
    subject_ids=SUBJECTS,
    convert_dicom=False,
    run_recon=False,
    create_m2m=False,
    run_tissue_analysis=False,
)

# ── 2. Flex Optimization ──────────────────────────────────────────────────────────

for subject_id in SUBJECTS:
    flex_config = FlexConfig(
        subject_id=subject_id,
        goal="mean",
        postproc="max_TI",
        current_mA=2.0,
        n_multistart=3,
        electrode=FlexConfig.ElectrodeConfig(),
        roi=FlexConfig.SphericalROI(x=0, y=0, z=0, radius=10.0),
    )
    run_flex_search(flex_config)


# ── 3. Simulation ────────────────────────────────────────────────────────────

montages = load_montages(
    montage_names=["L_Insula"],
    eeg_net=EEG_NET,
)

for subject_id in SUBJECTS:
    config = SimulationConfig(
        subject_id=subject_id,
        montages=montages,
        conductivity="scalar",
        intensities=[1.0, 1.0],
        electrode_shape="ellipse",
        electrode_dimensions=[8.0, 8.0],
        gel_thickness=4.0,
        rubber_thickness=2.0,
    )
    run_simulation(config)

# ── 4. Analysis ──────────────────────────────────────────────────────────────

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
