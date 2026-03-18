#!/usr/bin/env simnibs_python

from tit.opt import ExConfig, run_ex_search


SUBJECTS = ["ernie"]


for subject_id in SUBJECTS:
    lf = f"{subject_id}_leadfield_EEG10-20_Okamoto_2004.hdf5"
    ex_config = ExConfig(
        subject_id=subject_id,
        leadfield_hdf=lf,
        roi_name="L-Insula.csv",
        electrodes=ExConfig.PoolElectrodes(["Fp1", "C3", "C4", "Cz", "Pz"]),
        total_current=2.0,
        current_step=0.2,
        channel_limit=1.2
    )
    run_ex_search(ex_config)
