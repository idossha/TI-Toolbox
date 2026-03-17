from tit.opt.leadfield import LeadfieldGenerator
import tit
tit.init()


PROJECT_DIR = "/mnt/000/"
SUBJECTS = ["ernie"]


for subject_id in SUBJECTS:
    lf = f"{subject_id}_leadfield_EEG10-20_Okamoto_2004.hdf5"
    ex_config = ExConfig(
        subject_id=subject_id,
        project_dir=PROJECT_DIR,
        leadfield_hdf=lf,
        roi_name="L-Insula.csv",
        electrodes=ExConfig.PoolElectrodes(["Fp1", "C3", "C4", "Cz", "Pz"]),
        total_current=2.0,
        current_step=0.2,
        channel_limit=1.2
    )
    run_ex_search(ex_config)
