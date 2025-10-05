#!/usr/bin/env bats

@test "Analyzer outputs exist under Analyses after analyzer_runner" {
    PROJECT_DIR="/mnt/test_projectdir"
    SUBJECT="ernie_extended"
    SIMULATION_NAME="test_montage"

    analyses_root="$PROJECT_DIR/derivatives/SimNIBS/sub-$SUBJECT/Simulations/$SIMULATION_NAME/Analyses"
    analyses_mesh="$analyses_root/Mesh"

    # Debug: show tree or ls of Analyses
    if command -v tree >/dev/null 2>&1; then
        echo "--- TREE $analyses_root ---"
        tree -a "$analyses_root" || true
        echo "--------------------------"
    else
        echo "--- LS -R $analyses_root ---"
        ls -laR "$analyses_root" || true
        echo "----------------------------"
    fi

    # Base directories
    [ -d "$analyses_root" ]
    [ -d "$analyses_mesh" ]

    # Spherical outputs
    spherical_dir="$analyses_mesh/sphere_x-50_y0_z0_r5"
    [ -d "$spherical_dir" ]
    [ -f "$spherical_dir/node_distribution_sphere_x-50.0_y0.0_z0.0_r5.0.png" ]
    [ -f "$spherical_dir/spherical_sphere_x-50.0_y0.0_z0.0_r5.0.csv" ]
    [ -f "$spherical_dir/spherical_sphere_x-50.0_y0.0_z0.0_r5.0_extra_info.csv" ]

    # Cortical region outputs
    region_dir="$analyses_mesh/region_lh.superiortemporal"
    [ -d "$region_dir" ]
    [ -f "$region_dir/cortical_lh.superiortemporal.csv" ]
    [ -f "$region_dir/cortical_lh.superiortemporal_extra_info.csv" ]
    [ -f "$region_dir/lh.superiortemporal_ROI.msh" ]
    [ -f "$region_dir/lh.superiortemporal_ROI.msh.opt" ]
    [ -f "$region_dir/lh.superiortemporal_whole_head_roi_histogram.png" ]
}


