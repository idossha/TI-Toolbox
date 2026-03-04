#!/usr/bin/env simnibs_python

from tit.opt import *

PROJECT_DIR = "/mnt/000/"
SUBJECT_ID = "101"

# ── Flex-search ──────────────────────────────────────────────────────────────

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

# ── Exhaustive search ────────────────────────────────────────────────────────

ex_config = ExConfig(
    subject_id=SUBJECT_ID,
    project_dir=PROJECT_DIR,
    leadfield_hdf=f"/mnt/000/derivatives/SimNIBS/sub-{SUBJECT_ID}/leadfields/"
    f"{SUBJECT_ID}_leadfield_GSN-HydroCel-128.hdf5",
    roi_name="my_roi.csv",
    electrodes=BucketElectrodes(
        e1_plus=["C3"],
        e1_minus=["C4"],
        e2_plus=["Cz"],
        e2_minus=["Pz"],
    ),
    currents=ExCurrentConfig(total=1.0, step=0.1),
)

# run_ex_search(ex_config)
