#!/usr/bin/env simnibs_python

import tit
tit.init()

from tit.pre import run_pipeline

PROJECT_DIR = "/mnt/000/"
SUBJECTS = ["ernie"]

run_pipeline(
    project_dir=PROJECT_DIR,
    subject_ids=SUBJECTS,

    # Structural pipeline
    convert_dicom=False,        # DICOM → NIfTI (dcm2niix)
    run_recon=False,            # FreeSurfer recon-all
    parallel_recon=False,      # run recon-all in parallel across subjects
    create_m2m=False,           # SimNIBS charm (head mesh)
    run_tissue_analysis=False, # tissue volume / thickness analysis

    # DWI pipeline (requires Docker socket)
    run_qsiprep=False,
    run_qsirecon=False,
    extract_dti=False,
    run_subcortical_segmentations=True,
)
