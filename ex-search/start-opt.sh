#!/bin/bash

#########################################
# Ido Haber - ihaber@wisc.edu
# October 31, 2024
#
# This is the main script for the optimizer tool, which collects input from 
# the user and orchestrates the execution of all necessary scripts and executables 
# in the pipeline. It handles ROI creation, leadfield matrix generation, 
# TI optimization, mesh processing, and output file updates.
#########################################

set -e  # Exit immediately if a command exits with a non-zero status

# Define color variables
# Define color variables
BOLD='\033[1m'
UNDERLINE='\033[4m'
RESET='\033[0m'
RED='\033[0;31m' #Red for errors or important exit messages.
GREEN='\033[0;32m' #Green for successful completions.
CYAN='\033[0;36m' #Cyan for actions being performed.
BOLD_CYAN='\033[1;36m'
YELLOW='\033[0;33m' #Yellow for warnings or important notices

project_dir="/mnt/$PROJECT_DIR_NAME"
subject_dir="$project_dir/Subjects"

# Function to list available subjects
list_subjects() {
    subjects=()
    i=1
    for subject_path in "$subject_dir"/m2m_*; do
        if [ -d "$subject_path" ]; then
            subject_id=$(basename "$subject_path" | sed 's/m2m_//')
            subjects+=("$subject_id")
            printf "%3d. %s\n" "$i" "$subject_id"
            ((i++))
        fi
    done
}

echo -e "${BOLD_CYAN}Choose subjects:${RESET}"
list_subjects

# Prompt user to select subjects
while true; do
    echo -ne "${GREEN}Enter the numbers of the subjects to analyze (comma-separated):${RESET} "
    read -r subject_choices
    if [[ "$subject_choices" =~ ^[0-9]+(,[0-9]+)*$ ]]; then
        IFS=',' read -r -a selected_subjects <<< "$subject_choices"
        valid_input=true
        for num in "${selected_subjects[@]}"; do
            if (( num < 1 || num >= i )); then
                echo -e "${RED}Invalid subject number: $num. Please try again.${RESET}"
                valid_input=false
                break
            fi
        done
        if $valid_input; then
            break
        fi
    else
        echo -e "${RED}Invalid input format. Please enter numbers separated by commas.${RESET}"
    fi
done

# Get the current script directory
script_dir=$(pwd)

# Loop through selected subjects and run the pipeline
for subject_index in "${selected_subjects[@]}"; do
    subject_name="${subjects[$((subject_index-1))]}"
    roi_dir="$subject_dir/m2m_$subject_name/ROIs"

    echo -e "\n${BOLD_CYAN}Processing subject: ${subject_name}${RESET}"

    # Call the ROI creator script to handle ROI creation or selection
    echo -e "${CYAN}Running roi-creator.py for subject $subject_name...${RESET}"
    python3 roi-creator.py "$roi_dir"

    # Check if the ROI creation was successful
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}ROI creation completed successfully for subject $subject_name.${RESET}"
    else
        echo -e "${RED}ROI creation failed for subject $subject_name. Exiting.${RESET}"
        exit 1
    fi

    # Define leadfield directories
    leadfield_vol_dir="$subject_dir/leadfield_vol_$subject_name"

    # Check if both leadfield directories exist
    if [ ! -d "$leadfield_vol_dir" ] ; then
        echo -e "${YELLOW}Missing Leadfield matrices for subject $subject_name.${RESET}"
        while true; do
            echo -ne "${GREEN}Do you wish to create them? It will take some time (Y/N):${RESET} "
            read -r create_leadfield
            if [[ "$create_leadfield" =~ ^[Yy]$ ]]; then
                echo -e "${CYAN}Running leadfield.py for subject $subject_name...${RESET}"
                simnibs_python leadfield.py "$subject_dir/m2m_$subject_name" "EGI_template.csv"
                break
            elif [[ "$create_leadfield" =~ ^[Nn]$ ]]; then
                echo -e "${RED}Skipping leadfield creation. Exiting.${RESET}"
                exit 1
            else
                echo -e "${RED}Invalid input. Please enter Y or N.${RESET}"
            fi
        done
    else
        echo -e "${GREEN}Leadfield directories already exist for subject $subject_name. Skipping leadfield.py.${RESET}"
    fi

    # Set the leadfield_hdf path
    leadfield_hdf="$project_dir/Subjects/leadfield_$subject_name/${subject_name}_leadfield_EGI_template.hdf5"
    export LEADFIELD_HDF=$leadfield_hdf
    export PROJECT_DIR=$project_dir
    export SUBJECT_NAME=$subject_name

    # Call the TI optimizer script
    echo -e "${CYAN}Running TImax_optimizer.py for subject $subject_name...${RESET}"
    simnibs_python ti_sim.py

    # Check if the TI optimization was successful
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}TI optimization completed successfully for subject $subject_name.${RESET}"
    else
        echo -e "${RED}TI optimization failed for subject $subject_name. Exiting.${RESET}"
        exit 1
    fi

    # Call the ROI analyzer script
    echo -e "${CYAN}Running roi-analyzer.py for subject $subject_name...${RESET}"
    python3 roi-analyzer.py "$roi_dir"

    # Check if the ROI analysis was successful
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}ROI analysis completed successfully for subject $subject_name.${RESET}"
    else
        echo -e "${RED}ROI analysis failed for subject $subject_name. Exiting.${RESET}"
        exit 1
    fi

    # Define the mesh directory
    mesh_dir="$project_dir/Simulations/opt_$subject_name"

    # Run the process_mesh_files_new.sh script
    echo -e "${CYAN}Running process_mesh_files_new.sh for subject $subject_name...${RESET}"
    ./field-analysis/run_process_mesh_files.sh "$mesh_dir"

    # Check if the mesh processing was successful
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Mesh processing completed successfully for subject $subject_name.${RESET}"
    else
        echo -e "${RED}Mesh processing failed for subject $subject_name. Exiting.${RESET}"
        exit 1
    fi

    # Run the Python script to update the output.csv file
    echo -e "${CYAN}Running update_output_csv.py for subject $subject_name...${RESET}"
    python3 update_output_csv.py "$project_dir" "$subject_name"

    # Check if the Python script was successful
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Updated output.csv successfully for subject $subject_name.${RESET}"
    else
        echo -e "${RED}Failed to update output.csv for subject $subject_name. Exiting.${RESET}"
        exit 1
    fi

    # Run the mesh selector script
    echo -e "${CYAN}Running mesh-selector.sh for subject $subject_name...${RESET}"
    #bash mesh-selector.sh

done

echo -e "\n${BOLD_CYAN}All tasks completed successfully for all selected subjects.${RESET}\n"

