#!/bin/bash

##############################################
# Ido Haber - ihaber@wisc.edu
# September 2, 2024
# Optimized for optimizer pipeline
#
# This script helps visualize the T1-weighted MRI in subject space 
# for accurate ROI targeting. Freeview is launched in the background 
# to allow continuous user input while viewing the T1 image.
##############################################


set -e  # Exit immediately if a command exits with a non-zero status

# Set up the project and subject directories
project_dir=$1
subject_name=$2

# Construct the full path to the T1.nii.gz file
t1_file="$project_dir/m2m_$subject_name/T1.nii.gz"

# Check if the T1.nii.gz file exists
if [ -f "$t1_file" ]; then
    echo "Loading $t1_file in Freeview..."
    freeview "$t1_file" &
else
    echo "Error: $t1_file not found!"
    exit 1
fi
