very good now i need your help with another thing:

i want to add another functionality for the nifti-viewer tab.

i want to let the user decide if they want to also load high frequency fields. If they choose to do so you will need to load the following niftis:

example:

project_dir=BIDS_new
subjectID=101
Simulation=L_insula

high frequency niftis to load:
101_TDCS_1_scalar_magnE.nii.gz
101_TDCS_2_scalar_magnE.nii.gz


L_insula > pwd
BIDS_new/derivatives/SimNIBS/sub-101/Simulations/L_insula
(base) idohaber|L_insula > tree
.
├── TI
│   ├── mesh
│   │   ├── 101_L_insula_TI.msh
│   │   ├── 101_L_insula_TI.msh.opt
│   │   ├── 101_L_insula_TI_central.msh
│   │   ├── 101_L_insula_TI_central.msh.opt
│   │   ├── grey_101_L_insula_TI.msh
│   │   ├── grey_101_L_insula_TI_central.msh
│   │   ├── grey_101_L_insula_TI_central.msh.opt
│   │   ├── lh.101_L_insula_TI.central.TI_max
│   │   ├── lh.central
│   │   ├── lh.grey_101_L_insula_TI.central.TI_max
│   │   ├── rh.101_L_insula_TI.central.TI_max
│   │   ├── rh.central
│   │   ├── rh.grey_101_L_insula_TI.central.TI_max
│   │   └── white_101_L_insula_TI.msh
│   ├── montage_imgs
│   │   └── L_insula_highlighted_visualization.png
│   └── niftis
│       ├── 101_L_insula_TI_MNI_TI_max.nii.gz
│       ├── 101_L_insula_TI_TI_max.nii.gz
│       ├── grey_101_L_insula_TI_MNI_TI_max.nii.gz
│       ├── grey_101_L_insula_TI_TI_max.nii.gz
│       ├── white_101_L_insula_TI_MNI_TI_max.nii.gz
│       └── white_101_L_insula_TI_TI_max.nii.gz
├── documentation
│   ├── sim_pipeline.log
│   ├── simnibs_simulation_20250523-183103.log
│   └── simnibs_simulation_20250523-183103.mat
└── high_Frequency
    ├── analysis
    │   └── fields_summary.txt
    ├── mesh
    │   ├── 101_TDCS_1_el_currents.geo
    │   ├── 101_TDCS_1_scalar.msh
    │   ├── 101_TDCS_1_scalar.msh.opt
    │   ├── 101_TDCS_2_el_currents.geo
    │   ├── 101_TDCS_2_scalar.msh
    │   └── 101_TDCS_2_scalar.msh.opt
    └── niftis
        ├── 101_TDCS_1_scalar_E.nii.gz
        ├── 101_TDCS_1_scalar_magnE.nii.gz
        ├── 101_TDCS_2_scalar_E.nii.gz
        └── 101_TDCS_2_scalar_magnE.nii.gz

10 directories, 35 files


the tree structure should show you the path. it is always going to be the same names, just different project names, subjects, and simulation names.

I want the button to be in the simualtion configuration window.