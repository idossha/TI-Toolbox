#!/usr/bin/env simnibs_python

from tit.sim import (
    SimulationConfig,
    ElectrodeConfig,
    IntensityConfig,
    ConductivityType,
    run_simulation,
    load_montages,
)

PROJECT_DIR = "/mnt/000/"
SUBJECTS = ["101", "ernie"]

montages = load_montages(
    montage_names=["L_Insula"], project_dir=PROJECT_DIR, eeg_net="GSN-HydroCel-185.csv"
)

for subject_id in SUBJECTS:
    config = SimulationConfig(
        subject_id=subject_id,
        project_dir=PROJECT_DIR,
        conductivity_type=ConductivityType.SCALAR,
        intensities=IntensityConfig(values=[1.0, 1.0]),
        electrode=ElectrodeConfig(
            shape="ellipse", dimensions=[8.0, 8.0], thickness=4.0, sponge_thickness=2.0
        ),
    )
    run_simulation(config, montages)
