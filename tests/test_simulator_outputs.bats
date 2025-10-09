#!/usr/bin/env bats

@test "Simulator outputs exist for central_montage" {
    PROJECT_DIR="/mnt/test_projectdir"
    SUBJECT="ernie_extended"
    SIM_DIR="$PROJECT_DIR/derivatives/SimNIBS/sub-$SUBJECT/Simulations/central_montage"

    # Debug: show tree or ls of simulation directory
    if command -v tree >/dev/null 2>&1; then
        echo "--- TREE $SIM_DIR ---"
        tree -a "$SIM_DIR" || true
        echo "---------------------"
    else
        echo "--- LS -R $SIM_DIR ---"
        ls -laR "$SIM_DIR" || true
        echo "----------------------"
    fi

    # Base structure
    [ -d "$SIM_DIR" ]
    [ -d "$SIM_DIR/TI" ]
    [ -d "$SIM_DIR/high_Frequency" ]
    [ -d "$SIM_DIR/documentation" ]

    # TI mesh files
    [ -d "$SIM_DIR/TI/mesh" ]
    [ -f "$SIM_DIR/TI/mesh/central_montage_TI.msh" ]
    [ -f "$SIM_DIR/TI/mesh/central_montage_TI.msh.opt" ]
    [ -f "$SIM_DIR/TI/mesh/central_montage_normal.msh" ]
    [ -f "$SIM_DIR/TI/mesh/central_montage_normal.msh.opt" ]
    [ -f "$SIM_DIR/TI/mesh/grey_central_montage_TI.msh" ]
    [ -f "$SIM_DIR/TI/mesh/white_central_montage_TI.msh" ]

    # TI montage images dir exists
    [ -d "$SIM_DIR/TI/montage_imgs" ]

    # TI niftis
    [ -d "$SIM_DIR/TI/niftis" ]
    [ -f "$SIM_DIR/TI/niftis/central_montage_TI_MNI_MNI_TI_max.nii.gz" ]
    [ -f "$SIM_DIR/TI/niftis/central_montage_TI_subject_TI_max.nii.gz" ]
    [ -f "$SIM_DIR/TI/niftis/grey_central_montage_TI_MNI_MNI_TI_max.nii.gz" ]
    [ -f "$SIM_DIR/TI/niftis/grey_central_montage_TI_subject_TI_max.nii.gz" ]
    [ -f "$SIM_DIR/TI/niftis/white_central_montage_TI_MNI_MNI_TI_max.nii.gz" ]
    [ -f "$SIM_DIR/TI/niftis/white_central_montage_TI_subject_TI_max.nii.gz" ]

    # TI surface_overlays
    [ -d "$SIM_DIR/TI/surface_overlays" ]
    [ -f "$SIM_DIR/TI/surface_overlays/ernie_extended_TDCS_1_scalar_central.msh" ]
    [ -f "$SIM_DIR/TI/surface_overlays/ernie_extended_TDCS_1_scalar_central.msh.opt" ]
    [ -f "$SIM_DIR/TI/surface_overlays/ernie_extended_TDCS_2_scalar_central.msh" ]
    [ -f "$SIM_DIR/TI/surface_overlays/ernie_extended_TDCS_2_scalar_central.msh.opt" ]
    [ -f "$SIM_DIR/TI/surface_overlays/lh.central" ]
    [ -f "$SIM_DIR/TI/surface_overlays/lh.ernie_extended_TDCS_1_scalar.central.E.angle" ]
    [ -f "$SIM_DIR/TI/surface_overlays/lh.ernie_extended_TDCS_1_scalar.central.E.magn" ]
    [ -f "$SIM_DIR/TI/surface_overlays/lh.ernie_extended_TDCS_1_scalar.central.E.normal" ]
    [ -f "$SIM_DIR/TI/surface_overlays/lh.ernie_extended_TDCS_1_scalar.central.E.tangent" ]
    [ -f "$SIM_DIR/TI/surface_overlays/lh.ernie_extended_TDCS_2_scalar.central.E.angle" ]
    [ -f "$SIM_DIR/TI/surface_overlays/lh.ernie_extended_TDCS_2_scalar.central.E.magn" ]
    [ -f "$SIM_DIR/TI/surface_overlays/lh.ernie_extended_TDCS_2_scalar.central.E.normal" ]
    [ -f "$SIM_DIR/TI/surface_overlays/lh.ernie_extended_TDCS_2_scalar.central.E.tangent" ]
    [ -f "$SIM_DIR/TI/surface_overlays/rh.central" ]
    [ -f "$SIM_DIR/TI/surface_overlays/rh.ernie_extended_TDCS_1_scalar.central.E.angle" ]
    [ -f "$SIM_DIR/TI/surface_overlays/rh.ernie_extended_TDCS_1_scalar.central.E.magn" ]
    [ -f "$SIM_DIR/TI/surface_overlays/rh.ernie_extended_TDCS_1_scalar.central.E.normal" ]
    [ -f "$SIM_DIR/TI/surface_overlays/rh.ernie_extended_TDCS_1_scalar.central.E.tangent" ]
    [ -f "$SIM_DIR/TI/surface_overlays/rh.ernie_extended_TDCS_2_scalar.central.E.angle" ]
    [ -f "$SIM_DIR/TI/surface_overlays/rh.ernie_extended_TDCS_2_scalar.central.E.magn" ]
    [ -f "$SIM_DIR/TI/surface_overlays/rh.ernie_extended_TDCS_2_scalar.central.E.normal" ]
    [ -f "$SIM_DIR/TI/surface_overlays/rh.ernie_extended_TDCS_2_scalar.central.E.tangent" ]

    # Documentation: at least one log and one mat file (timestamped)
    [ -n "$(ls -1 "$SIM_DIR/documentation"/simnibs_simulation_*.log 2>/dev/null)" ]
    [ -n "$(ls -1 "$SIM_DIR/documentation"/simnibs_simulation_*.mat 2>/dev/null)" ]

    # High frequency analysis summary
    [ -f "$SIM_DIR/high_Frequency/analysis/fields_summary.txt" ]

    # High frequency mesh files
    [ -d "$SIM_DIR/high_Frequency/mesh" ]
    [ -f "$SIM_DIR/high_Frequency/mesh/ernie_extended_TDCS_1_el_currents.geo" ]
    [ -f "$SIM_DIR/high_Frequency/mesh/ernie_extended_TDCS_1_scalar.msh" ]
    [ -f "$SIM_DIR/high_Frequency/mesh/ernie_extended_TDCS_1_scalar.msh.opt" ]
    [ -f "$SIM_DIR/high_Frequency/mesh/ernie_extended_TDCS_2_el_currents.geo" ]
    [ -f "$SIM_DIR/high_Frequency/mesh/ernie_extended_TDCS_2_scalar.msh" ]
    [ -f "$SIM_DIR/high_Frequency/mesh/ernie_extended_TDCS_2_scalar.msh.opt" ]

    # High frequency niftis
    [ -d "$SIM_DIR/high_Frequency/niftis" ]
    [ -f "$SIM_DIR/high_Frequency/niftis/ernie_extended_TDCS_1_scalar_E.nii.gz" ]
    [ -f "$SIM_DIR/high_Frequency/niftis/ernie_extended_TDCS_1_scalar_magnE.nii.gz" ]
    [ -f "$SIM_DIR/high_Frequency/niftis/ernie_extended_TDCS_2_scalar_E.nii.gz" ]
    [ -f "$SIM_DIR/high_Frequency/niftis/ernie_extended_TDCS_2_scalar_magnE.nii.gz" ]
}


