#!/usr/bin/env simnibs_python

from tit.opt import *
from tit.opt.config import PoolElectrodes
from tit.opt.leadfield import LeadfieldGenerator

PROJECT_DIR = "/mnt/000/"
SUBJECT_ID = "101"
EEG_NET = "GSN-HydroCel-128.csv"
lf = "101_leadfield_EEG10-20_Okamoto_2004.hdf5"

# ── Leadfield ─────────────────────────────────────────────────────────────────

# lfg = LeadfieldGenerator(SUBJECT_ID, electrode_cap="EEG10-20_Okamoto_2004")
# lf = lfg.generate()
#
# ── Flex-search ───────────────────────────────────────────────────────────────

flex_config = FlexConfig(
     subject_id=SUBJECT_ID,
     project_dir=PROJECT_DIR,
     goal="mean",
     postproc="max_TI",
     current_mA=2.0,
     electrode=FlexElectrodeConfig(),
     roi=SphericalROI(x=0, y=0, z=0, radius=10.0),
)

run_flex_search(flex_config)

# ── Exhaustive search ─────────────────────────────────────────────────────────

# ex_config = ExConfig(
#     subject_id=SUBJECT_ID,
#     project_dir=PROJECT_DIR,
#     leadfield_hdf=lf,
#     roi_name="my_roi.csv",
#     electrodes=PoolElectrodes(["C3", "C4", "Cz", "Pz"]),
#     currents=ExCurrentConfig(total=1.0, step=0.1),
# )

# run_ex_search(ex_config)
