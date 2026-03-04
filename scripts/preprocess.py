#!/usr/bin/env simnibs_python

from tit.pre.structural import run_pipeline

PROJECT_DIR = "/mnt/000/"
SUBJECTS = ["101"]

run_pipeline(
    project_dir=PROJECT_DIR,
    subject_ids=SUBJECTS,

    # Structural pipeline
    convert_dicom=True,        # DICOM → NIfTI (dcm2niix)
    run_recon=True,            # FreeSurfer recon-all
    parallel_recon=False,      # run recon-all in parallel across subjects
    create_m2m=True,           # SimNIBS charm (head mesh)
    run_tissue_analysis=False, # tissue volume / thickness analysis

    # DWI pipeline (requires Docker socket)
    run_qsiprep=False,
    run_qsirecon=False,
    extract_dti=False,
)
