#!/usr/bin/env simnibs_python

from tit import setup_logging, add_stream_handler

setup_logging()
add_stream_handler("tit")

from tit.opt import (
    FlexConfig,
    FlexElectrodeConfig,
    SphericalROI,
    run_flex_search,
    ExConfig,
    ExCurrentConfig,
    PoolElectrodes,
    run_ex_search,
)
from tit.opt.leadfield import LeadfieldGenerator

PROJECT_DIR = "/mnt/000/"
SUBJECTS = ["101", "ernie"]
EEG_NET = "GSN-HydroCel-128.csv"

# ── Leadfield ─────────────────────────────────────────────────────────────────

# for subject_id in SUBJECTS:
#     lfg = LeadfieldGenerator(subject_id, electrode_cap="EEG10-20_Okamoto_2004")
#     lf = lfg.generate()

# ── Flex-search ───────────────────────────────────────────────────────────────

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

# ── Exhaustive search ─────────────────────────────────────────────────────────

# for subject_id in SUBJECTS:
#     lf = f"{subject_id}_leadfield_EEG10-20_Okamoto_2004.hdf5"
#     ex_config = ExConfig(
#         subject_id=subject_id,
#         project_dir=PROJECT_DIR,
#         leadfield_hdf=lf,
#         roi_name="my_roi.csv",
#         electrodes=PoolElectrodes(["C3", "C4", "Cz", "Pz"]),
#         currents=ExCurrentConfig(total_current=1.0, current_step=0.1),
#     )
#     run_ex_search(ex_config)
