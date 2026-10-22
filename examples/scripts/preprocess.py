#!/usr/bin/env simnibs_python

from tit.pre import run_pipeline

SUBJECTS = ["ernie"]

run_pipeline(
    subject_ids=SUBJECTS,

    # Structural pipeline
    convert_dicom=False,        # DICOM → NIfTI (dcm2niix)
    run_fastsurfer=False,       # FastSurfer deep segmentation (--seg_only)
    create_m2m=False,           # SimNIBS charm (head mesh)
    run_tissue_analysis=False, # tissue volume / thickness analysis

    # DWI pipeline (requires Docker socket)
    run_qsiprep=False,
    run_qsirecon=False,
    extract_dti=False,
)
