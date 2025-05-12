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
BOLD='\033[1m'
UNDERLINE='\033[4m'
RESET='\033[0m'
RED='\033[0;31m' #Red for errors or important exit messages.
GREEN='\033[0;32m' #Green for successful completions.
CYAN='\033[0;36m' #Cyan for actions being performed.
BOLD_CYAN='\033[1;36m'
YELLOW='\033[0;33m' #Yellow for warnings or important notices

# Check if PROJECT_DIR_NAME is set
if [ -z "$PROJECT_DIR_NAME" ]; then
    echo -e "${RED}Error: PROJECT_DIR_NAME environment variable is not set${RESET}"
    exit 1
fi

# Define the new BIDS-compliant directory structure
project_dir="/mnt/$PROJECT_DIR_NAME"
derivatives_dir="$project_dir/derivatives"
simnibs_dir="$derivatives_dir/SimNIBS"

# Function to list available subjects
list_subjects() {
    subjects=()
    i=1
    # Look for subjects in the new BIDS structure
    for subject_path in "$simnibs_dir"/sub-*/m2m_*; do
        if [ -d "$subject_path" ]; then
            # Extract subject ID from the path (e.g., sub-101 -> 101)
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

# Get the current script directory and set paths
script_dir=$(pwd)
ex_search_dir="$script_dir/../ex-search"

# Loop through selected subjects and run the pipeline
for subject_index in "${selected_subjects[@]}"; do
    subject_name="${subjects[$((subject_index-1))]}"
    subject_bids_dir="$simnibs_dir/sub-$subject_name"
    m2m_dir="$subject_bids_dir/m2m_$subject_name"
    roi_dir="$m2m_dir/ROIs"
    ex_search_output_dir="$subject_bids_dir/ex-search"

    # Create ex-search output directory if it doesn't exist
    mkdir -p "$ex_search_output_dir"

    echo -e "\n${BOLD_CYAN}Processing subject: ${subject_name}${RESET}"

    # Call the ROI creator script to handle ROI creation or selection
    echo -e "${CYAN}Running roi-creator.py for subject $subject_name...${RESET}"
    python3 "$ex_search_dir/roi-creator.py" "$roi_dir"

    # Check if the ROI creation was successful
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}ROI creation completed successfully for subject $subject_name.${RESET}"
    else
        echo -e "${RED}ROI creation failed for subject $subject_name. Exiting.${RESET}"
        exit 1
    fi

    # Define leadfield directories
    leadfield_vol_dir="$subject_bids_dir/leadfield_vol_$subject_name"

    # Check if leadfield directory exists
    if [ ! -d "$leadfield_vol_dir" ] ; then
        echo -e "${YELLOW}Missing Leadfield matrices for subject $subject_name.${RESET}"
        while true; do
            echo -ne "${GREEN}Do you wish to create them? It will take some time (Y/N):${RESET} "
            read -r create_leadfield
            if [[ "$create_leadfield" =~ ^[Yy]$ ]]; then
                echo -e "${CYAN}Running leadfield.py for subject $subject_name...${RESET}"
                simnibs_python "$ex_search_dir/leadfield.py" "$m2m_dir" "EGI_template.csv"
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
    leadfield_hdf="$subject_bids_dir/leadfield_$subject_name/${subject_name}_leadfield_EGI_template.hdf5"
    export LEADFIELD_HDF=$leadfield_hdf
    export PROJECT_DIR=$project_dir
    export SUBJECT_NAME=$subject_name

    # Call the TI optimizer script
    echo -e "${CYAN}Running TImax_optimizer.py for subject $subject_name...${RESET}"
    #simnibs_python "$ex_search_dir/ti_sim.py"

    # Check if the TI optimization was successful
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}TI optimization completed successfully for subject $subject_name.${RESET}"
    else
        echo -e "${RED}TI optimization failed for subject $subject_name. Exiting.${RESET}"
        exit 1
    fi

    # Call the ROI analyzer script
    echo -e "${CYAN}Running roi-analyzer.py for subject $subject_name...${RESET}"
    #python3 "$ex_search_dir/roi-analyzer.py" "$roi_dir"

    # Check if the ROI analysis was successful
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}ROI analysis completed successfully for subject $subject_name.${RESET}"
    else
        echo -e "${RED}ROI analysis failed for subject $subject_name. Exiting.${RESET}"
        exit 1
    fi

    # Define and check roi_list_file
    roi_list_file="$roi_dir/roi_list.txt"
    if [ ! -f "$roi_list_file" ]; then
        echo -e "${RED}Error: roi_list.txt not found in $roi_dir${RESET}"
        exit 1
    fi

    # Get ROI coordinates from the first ROI file
    first_roi=$(head -n1 "$roi_list_file" || echo "")
    if [ -z "$first_roi" ]; then
        echo -e "${RED}Error: roi_list.txt is empty${RESET}"
        exit 1
    fi
    
    # Construct full path to ROI file
    roi_file="$roi_dir/$first_roi"
    if [ ! -f "$roi_file" ]; then
        echo -e "${RED}Error: ROI file not found: $roi_file${RESET}"
        exit 1
    fi

    # Read coordinates from the ROI file and handle Windows line endings
    coordinates=$(head -n1 "$roi_file" | tr -d '\r')
    IFS=',' read -r x y z <<< "$coordinates"
    
    # Remove any whitespace and validate coordinates
    x=$(echo "$x" | tr -d ' ')
    y=$(echo "$y" | tr -d ' ')
    z=$(echo "$z" | tr -d ' ')
    
    # Print coordinates for debugging
    echo -e "${CYAN}Processing coordinates from $roi_file: $x, $y, $z${RESET}"
    
    # Round coordinates to integers using awk for better decimal and negative number handling
    x_int=$(echo "$x" | awk '{printf "%.0f", $1}')
    y_int=$(echo "$y" | awk '{printf "%.0f", $1}')
    z_int=$(echo "$z" | awk '{printf "%.0f", $1}')
    
    # Validate that we got all coordinates
    if [ -z "$x_int" ] || [ -z "$y_int" ] || [ -z "$z_int" ]; then
        echo -e "${RED}Error: Failed to parse coordinates from $roi_file${RESET}"
        echo -e "${RED}Raw coordinates: $coordinates${RESET}"
        exit 1
    fi
    
    # Create directory name from coordinates
    coord_dir="xyz_${x_int}_${y_int}_${z_int}"
    echo -e "${CYAN}Creating directory: $coord_dir${RESET}"
    mesh_dir="$ex_search_output_dir/$coord_dir"

    # Create output directory if it doesn't exist
    mkdir -p "$mesh_dir"

    # Run the process_mesh_files_new.sh script
    echo -e "${CYAN}Running process_mesh_files_new.sh for subject $subject_name...${RESET}"
    "$ex_search_dir/field-analysis/run_process_mesh_files.sh" "$mesh_dir"

    # Check if the mesh processing was successful
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Mesh processing completed successfully for subject $subject_name.${RESET}"
    else
        echo -e "${RED}Mesh processing failed for subject $subject_name. Exiting.${RESET}"
        exit 1
    fi

    # Run the Python script to update the output.csv file
    echo -e "${CYAN}Running update_output_csv.py for subject $subject_name...${RESET}"
    python3 "$ex_search_dir/update_output_csv.py" "$project_dir" "$subject_name"

    # Check if the Python script was successful
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Updated output.csv successfully for subject $subject_name.${RESET}"
    else
        echo -e "${RED}Failed to update output.csv for subject $subject_name. Exiting.${RESET}"
        exit 1
    fi

    # Run the mesh selector script
    echo -e "${CYAN}Running mesh-selector.sh for subject $subject_name...${RESET}"
    #bash "$ex_search_dir/mesh-selector.sh"

done

echo -e "\n${BOLD_CYAN}All tasks completed successfully for all selected subjects.${RESET}\n" 