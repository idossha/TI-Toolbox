#!/usr/bin/env simnibs_python

from tit import setup_logging, add_stream_handler

setup_logging()
add_stream_handler("tit")

from tit.sim import SimulationConfig, Montage, run_simulation, load_montages

PROJECT_DIR = "/mnt/000/"
SUBJECTS = ["101"]

# Construct montages explicitly
montages = [
    Montage(
        name="L_Insula",
        mode=Montage.Mode.NET,
        electrode_pairs=[("E001", "E002"), ("E003", "E004")],
        eeg_net="GSN-HydroCel-185.csv",
    ),
]


for subject_id in SUBJECTS:
    config = SimulationConfig(
        subject_id=subject_id,
        project_dir=PROJECT_DIR,
        montages=montages,
        conductivity="scalar",
        intensities=[1.0, 1.0],
        electrode_shape="ellipse",
        electrode_dimensions=[8.0, 8.0],
        gel_thickness=4.0,
        rubber_thickness=2.0,
    )
    run_simulation(config)
