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
SUBJECT_ID  = "101"    

config = SimulationConfig(
    subject_id=SUBJECT_ID,
    project_dir=PROJECT_DIR,

    conductivity_type=ConductivityType.SCALAR,

    intensities=IntensityConfig(pair1=1.0, pair2=1.0),

    electrode=ElectrodeConfig(
        shape="ellipse",
        dimensions=[8.0, 8.0],   
        thickness=4.0,            
        sponge_thickness=2.0)
)

montages = load_montages(
    montage_names=["L_Insula"],
    project_dir=PROJECT_DIR,
    eeg_net="GSN-HydroCel-185.csv")

run_simulation(config, montages)
