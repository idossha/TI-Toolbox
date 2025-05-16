#!/bin/bash

###########################################
# Neuroimaging Field Analyzer CLI
# Based on the TI-CSC analyzer functionality
# This script provides a command-line interface for analyzing 
# mesh and voxel-based neuroimaging data.
###########################################

set -e  # Exit immediately if a command exits with a non-zero status

umask 0000  # Set umask to 0000 to ensure all created files and directories have permissions 777

# Base directories
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="/mnt/$PROJECT_DIR_NAME"

# Define color variables
BOLD='\033[1m'
UNDERLINE='\033[4m'
RESET='\033[0m'
RED='\033[0;31m' #Red for errors or important exit messages.
GREEN='\033[0;32m' #Green for successful completions.
CYAN='\033[0;36m' #Cyan for actions being performed.
BOLD_CYAN='\033[1;36m'
YELLOW='\033[0;33m' #Yellow for warnings or important notices
BOLD_YELLOW='\033[1;33m'

# Function to handle invalid input and reprompt
reprompt() {
    echo -e "${RED}Invalid input. Please try again.${RESET}"
}

# Function to display welcome message
show_welcome_message() {
    clear  # Clear the screen before starting
    echo -e "${BOLD_CYAN}╔════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD_CYAN}║    TI-CSC Neuroimaging Analyzer Tool   ║${RESET}"
    echo -e "${BOLD_CYAN}╚════════════════════════════════════════╝${RESET}"
    echo -e "${CYAN}Version 1.0 - $(date +%Y)${RESET}"
    echo -e "${CYAN}Analyze neuroimaging data with customizable ROI configurations${RESET}\n"
}

# Function to list available subjects
list_subjects() {
    subjects=()
    for subject_path in "$project_dir"/derivatives/SimNIBS/sub-*/m2m_*; do
        if [ -d "$subject_path" ]; then
            subject_id=$(basename "$(dirname "$subject_path")" | sed 's/sub-//')
            subjects+=("$subject_id")
        fi
    done

    total_subjects=${#subjects[@]}
    max_rows=10
    num_columns=$(( (total_subjects + max_rows - 1) / max_rows ))

    echo -e "${BOLD_CYAN}Available Subjects:${RESET}"
    echo "-------------------"
    for (( row=0; row<max_rows; row++ )); do
        for (( col=0; col<num_columns; col++ )); do
            index=$(( col * max_rows + row ))
            if [ $index -lt $total_subjects ]; then
                printf "%3d. %-25s" $(( index + 1 )) "${subjects[$index]}"
            fi
        done
        echo
    done
    echo
}

# Function to list available simulations for a subject
list_simulations() {
    local subject_id=$1
    local simulation_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations"
    
    if [ ! -d "$simulation_dir" ]; then
        echo -e "${RED}No simulations found for subject $subject_id${RESET}"
        return 1
    fi
    
    simulations=()
    for sim_path in "$simulation_dir"/*; do
        if [ -d "$sim_path" ]; then
            sim_name=$(basename "$sim_path")
            simulations+=("$sim_name")
        fi
    done
    
    if [ ${#simulations[@]} -eq 0 ]; then
        echo -e "${RED}No simulations found for subject $subject_id${RESET}"
        return 1
    fi
    
    total_sims=${#simulations[@]}
    
    echo -e "${BOLD_CYAN}Available Simulations for subject $subject_id:${RESET}"
    echo "-------------------"
    for (( i=0; i<total_sims; i++ )); do
        printf "%3d. %s\n" $(( i + 1 )) "${simulations[$i]}"
    done
    echo
    
    return 0
}

# Function to list available field files for a simulation
list_field_files() {
    local subject_id=$1
    local simulation_name=$2
    local space_type=$3  # mesh or voxel
    
    # Set the appropriate directory based on space type
    if [ "$space_type" == "mesh" ]; then
        local field_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/$simulation_name/TI/mesh"
        local file_pattern="*.msh"
    else
        local field_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/$simulation_name/TI/niftis"
        local file_pattern="*.{nii,nii.gz,mgz}"
    fi
    
    if [ ! -d "$field_dir" ]; then
        echo -e "${RED}No field files found for simulation $simulation_name${RESET}"
        return 1
    fi
    
    # Use find to get all matching files
    field_files=()
    
    if [ "$space_type" == "mesh" ]; then
        # For mesh files, exclude .msh.opt files
        while IFS= read -r -d $'\0' file; do
            # Skip .msh.opt files
            if [[ "$file" != *".msh.opt" ]]; then
                field_files+=("$(basename "$file")")
            fi
        done < <(find "$field_dir" -type f -name "$file_pattern" -print0 | sort -z)
    else
        # For voxel files
        shopt -s extglob  # Enable extended pattern matching
        while IFS= read -r -d $'\0' file; do
            field_files+=("$(basename "$file")")
        done < <(find "$field_dir" -type f \( -name "*.nii" -o -name "*.nii.gz" -o -name "*.mgz" \) -print0 | sort -z)
        shopt -u extglob  # Disable extended pattern matching
    fi
    
    if [ ${#field_files[@]} -eq 0 ]; then
        echo -e "${RED}No field files found for simulation $simulation_name${RESET}"
        return 1
    fi
    
    # Separate grey_ prefixed files and others
    grey_files=()
    other_files=()
    
    for file in "${field_files[@]}"; do
        if [[ "$file" == grey_* ]]; then
            grey_files+=("$file")
        else
            other_files+=("$file")
        fi
    done
    
    # Combine arrays with grey files first
    field_files=("${grey_files[@]}" "${other_files[@]}")
    
    total_files=${#field_files[@]}
    
    echo -e "${BOLD_CYAN}Available Field Files for $space_type analysis:${RESET}"
    echo "-------------------"
    for (( i=0; i<total_files; i++ )); do
        printf "%3d. %s\n" $(( i + 1 )) "${field_files[$i]}"
    done
    echo
    
    return 0
}

# Function to list atlas files for a subject (voxel mode)
list_atlas_files() {
    local subject_id=$1
    local m2m_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id"
    local segmentation_dir="$m2m_dir/segmentation"
    
    if [ ! -d "$segmentation_dir" ]; then
        echo -e "${RED}No segmentation directory found for subject $subject_id${RESET}"
        return 1
    fi
    
    atlas_files=()
    while IFS= read -r -d $'\0' file; do
        atlas_files+=("$(basename "$file")")
    done < <(find "$segmentation_dir" -type f \( -name "*.nii" -o -name "*.nii.gz" -o -name "*.mgz" \) -print0 | sort -z)
    
    if [ ${#atlas_files[@]} -eq 0 ]; then
        echo -e "${RED}No atlas files found for subject $subject_id${RESET}"
        return 1
    fi
    
    total_files=${#atlas_files[@]}
    
    echo -e "${BOLD_CYAN}Available Atlas Files:${RESET}"
    echo "-------------------"
    for (( i=0; i<total_files; i++ )); do
        printf "%3d. %s\n" $(( i + 1 )) "${atlas_files[$i]}"
    done
    echo
    
    return 0
}

# Function to display available atlas types for mesh analysis
show_atlas_types() {
    echo -e "${BOLD_CYAN}Available Atlas Types for Mesh Analysis:${RESET}"
    echo "-------------------"
    echo "1. DK40       - Desikan-Killiany Atlas (40 regions)"
    echo "2. HCP_MMP1   - Human Connectome Project Multi-Modal Parcellation"
    echo "3. a2009s     - Destrieux Atlas"
    echo
}

# Function to list available regions for an atlas
list_available_regions() {
    local subject_id=$1
    local space_type=$2
    local atlas_name=$3
    local atlas_path=$4
    local m2m_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id"

    echo -e "${BOLD_CYAN}Available Regions:${RESET}"
    echo -e "${YELLOW}You can use either the Region ID or the Region Name in your selection${RESET}"
    echo "-------------------"

    if [ "$space_type" == "mesh" ]; then
        # For mesh analysis, use simnibs_python to get regions
        echo -e "${CYAN}Loading $atlas_name atlas...${RESET}"
        regions=$(simnibs_python -c "
import simnibs
import sys

try:
    atlas = simnibs.subject_atlas('$atlas_name', '$m2m_dir')
    regions = sorted(atlas.keys())
    print('\n'.join(regions))
except Exception as e:
    print(f'Error: {str(e)}', file=sys.stderr)
    sys.exit(1)
")
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error loading atlas regions.${RESET}"
            return 1
        fi
    else
        # For voxel analysis, use FreeSurfer's mri_segstats
        local segmentation_dir="$m2m_dir/segmentation"
        local atlas_basename=$(basename "$atlas_path")
        local atlas_name_base="${atlas_basename%.*}"  # Remove extension
        if [[ "$atlas_basename" == *.nii.gz ]]; then
            atlas_name_base="${atlas_name_base%.*}"  # Remove .nii from .nii.gz
        fi
        local labels_file="$segmentation_dir/${atlas_name_base}_labels.txt"

        # Generate labels file if it doesn't exist
        if [ ! -f "$labels_file" ]; then
            echo -e "${CYAN}Generating labels file...${RESET}"
            mri_segstats --seg "$atlas_path" --excludeid 0 --ctab-default --sum "$labels_file" > /dev/null 2>&1
            if [ $? -ne 0 ]; then
                echo -e "${RED}Error generating labels file.${RESET}"
                return 1
            fi
        fi

        # Extract and format region information - showing both ID and name
        echo -e "${CYAN}Reading atlas regions...${RESET}"
        # Process the labels file to extract region IDs and structure names
        regions=$(awk '
            # Skip header lines (starting with #) and empty lines
            !/^#/ && NF >= 5 {
                # Get the region ID (2nd column) and structure name (5th column to end of line)
                id = $2
                name = $5
                for(i=6; i<=NF; i++) name = name " " $i
                # Remove any leading/trailing whitespace
                gsub(/^[ \t]+|[ \t]+$/, "", name)
                if (length(name) > 0) printf "%-6s  %s\n", "[" id "]", name
            }
        ' "$labels_file" | sort -k2)
    fi

    # Display regions in columns (2 columns, with proper spacing for ID and name)
    echo "$regions" | pr -2 -t -w 120

    echo
}

# Function to validate region identifier against atlas
validate_region() {
    local labels_file=$1
    local region_input=$2
    
    # Check if input is numeric (Region ID) or text (Region Name)
    if [[ "$region_input" =~ ^[0-9]+$ ]]; then
        # Search by Region ID
        if grep -q "^[[:space:]]*[0-9]\+[[:space:]]\+${region_input}[[:space:]]" "$labels_file"; then
            # Get the region name for display
            region_name=$(awk -v id="$region_input" '
                $2 == id {
                    for(i=5; i<=NF; i++) printf "%s%s", (i>5?" ":""), $i
                    exit
                }
            ' "$labels_file")
            echo "$region_name"
            return 0
        else
            echo -e "${RED}Error: Region ID '$region_input' not found in atlas${RESET}"
            return 1
        fi
    else
        # Search by exact Region Name
        if grep -q "[[:space:]]${region_input}[[:space:]]*$" "$labels_file"; then
            echo "$region_input"
            return 0
        else
            echo -e "${RED}Error: Region name '$region_input' not found in atlas${RESET}"
            return 1
        fi
    fi
}

# Function to prompt for region selection
prompt_region_selection() {
    local subject_id=$1
    local space_type=$2
    local atlas_name=$3
    local atlas_path=$4
    local m2m_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id"
    local segmentation_dir="$m2m_dir/segmentation"
    local atlas_basename=$(basename "$atlas_path")
    local atlas_name_base="${atlas_basename%.*}"
    if [[ "$atlas_basename" == *.nii.gz ]]; then
        atlas_name_base="${atlas_name_base%.*}"
    fi
    local labels_file="$segmentation_dir/${atlas_name_base}_labels.txt"

    while true; do
        echo -e "${GREEN}Do you want to:${RESET}"
        echo "1. View available regions"
        echo "2. Enter region identifier (ID or name)"
        echo "3. Cancel"
        read -p "Enter your choice (1-3): " choice

        case $choice in
            1)
                list_available_regions "$subject_id" "$space_type" "$atlas_name" "$atlas_path"
                ;;
            2)
                echo -e "${GREEN}Enter the region identifier:${RESET}"
                echo -e "${YELLOW}You can enter either:${RESET}"
                echo -e "  - Region Name (e.g., Left-Hippocampus, ctx-lh-superiorfrontal)"
                echo -e "  - Region ID (e.g., 17, 1028)${RESET}"
                read -p " " region_input
                
                if [ -z "$region_input" ]; then
                    echo -e "${RED}Region identifier cannot be empty.${RESET}"
                    continue
                fi

                # Validate the region input
                if [[ "$space_type" == "mesh" ]]; then
                    # For mesh analysis, use simnibs_python to validate
                    valid_region=$(simnibs_python -c "
import simnibs
import sys

try:
    atlas = simnibs.subject_atlas('$atlas_name', '$m2m_dir')
    region = '$region_input'
    
    # Check if input is numeric
    try:
        region_id = int(region)
        # Convert ID to name if possible
        region_name = next((name for name, id in atlas.items() if id == region_id), None)
        if region_name:
            print(region_name)
            sys.exit(0)
    except ValueError:
        # Input is a name, check if it exists
        if region in atlas:
            print(region)
            sys.exit(0)
    
    sys.exit(1)
except Exception as e:
    print(f'Error: {str(e)}', file=sys.stderr)
    sys.exit(1)
")
                    if [ $? -eq 0 ]; then
                        region_name="$valid_region"
                        echo -e "${CYAN}Selected region: $region_name${RESET}"
                        return 0
                    else
                        echo -e "${RED}Error: Invalid region identifier '$region_input' for atlas $atlas_name${RESET}"
                    fi
                else
                    # For voxel analysis, use the labels file to validate
                    result=$(validate_region "$labels_file" "$region_input")
                    if [ $? -eq 0 ]; then
                        region_name="$result"
                        echo -e "${CYAN}Selected region: $region_name${RESET}"
                        return 0
                    fi
                fi
                ;;
            3)
                echo -e "${RED}Region selection cancelled.${RESET}"
                exit 0
                ;;
            *)
                reprompt
                ;;
        esac
    done
}

# Function to run analysis
run_analysis() {
    # Build the command to run main_analyzer.py
    local cmd=(simnibs_python "$script_dir/../analyzer/main_analyzer.py")
    
    # Add common parameters
    cmd+=(--m2m_subject_path "$m2m_dir")
    cmd+=(--field_path "$field_path")
    cmd+=(--space "$space_type")
    cmd+=(--analysis_type "$analysis_type")
    cmd+=(--output_dir "$output_dir")
    
    # Add space-specific parameters
    if [ "$space_type" == "mesh" ]; then
        cmd+=(--field_name "$field_name")
    fi
    
    # Add analysis-specific parameters
    if [ "$analysis_type" == "spherical" ]; then
        cmd+=(--coordinates "${coordinates[@]}")
        cmd+=(--radius "$radius")
    else  # cortical
        if [ "$space_type" == "mesh" ]; then
            cmd+=(--atlas_name "$atlas_name")
        else
            cmd+=(--atlas_path "$atlas_path")
        fi
        
        if [ "$whole_head" == "true" ]; then
            cmd+=(--whole_head)
        else
            cmd+=(--region "$region_name")
        fi
    fi
    
    # Add visualization flag if enabled
    if [ "$visualize" == "true" ]; then
        cmd+=(--visualize)
    fi
    
    # Display command
    echo -e "${CYAN}Running analysis with command:${RESET}"
    echo -e "${GREEN}${cmd[*]}${RESET}"
    echo
    
    # Run the command
    "${cmd[@]}"
    
    # Check execution status
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Analysis completed successfully.${RESET}"
        echo -e "${GREEN}Results saved to: $output_dir${RESET}"
    else
        echo -e "${RED}Analysis failed. Check the output for errors.${RESET}"
    fi
}

# Function to show confirmation dialog
show_confirmation_dialog() {
    echo -e "\n${BOLD_CYAN}Analysis Configuration Summary${RESET}"
    echo -e "----------------------------------------"
    echo -e "${BOLD}Selected Parameters:${RESET}"
    
    # Subject and Simulation Information
    echo -e "\n${BOLD_CYAN}Subject Information:${RESET}"
    echo -e "Subject ID: ${CYAN}$subject_id${RESET}"
    echo -e "Simulation: ${CYAN}$simulation_name${RESET}"
    
    # Analysis Parameters
    echo -e "\n${BOLD_CYAN}Analysis Parameters:${RESET}"
    echo -e "Analysis Space: ${CYAN}$space_type${RESET}"
    echo -e "Analysis Type: ${CYAN}$analysis_type${RESET}"
    echo -e "Field File: ${CYAN}$field_basename${RESET}"
    
    if [ "$space_type" == "mesh" ]; then
        echo -e "Field Name: ${CYAN}$field_name${RESET}"
    fi
    
    # Specific Analysis Parameters
    if [ "$analysis_type" == "spherical" ]; then
        echo -e "\n${BOLD_CYAN}Spherical Analysis Parameters:${RESET}"
        echo -e "Coordinates (x, y, z): ${CYAN}${coordinates[*]}${RESET}"
        echo -e "Radius: ${CYAN}${radius} mm${RESET}"
    else  # cortical
        echo -e "\n${BOLD_CYAN}Cortical Analysis Parameters:${RESET}"
        if [ "$space_type" == "mesh" ]; then
            echo -e "Atlas Type: ${CYAN}$atlas_name${RESET}"
        else
            echo -e "Atlas File: ${CYAN}$atlas_basename${RESET}"
        fi
        
        if [ "$whole_head" == "true" ]; then
            echo -e "Analysis Scope: ${CYAN}Whole Head${RESET}"
        else
            echo -e "Target Region: ${CYAN}$region_name${RESET}"
        fi
    fi
    
    # Output Directory
    echo -e "\n${BOLD_CYAN}Output Configuration:${RESET}"
    echo -e "Output Directory: ${CYAN}$output_dir${RESET}"
    echo -e "Generate Visualizations: ${CYAN}$([ "$visualize" == "true" ] && echo "Yes" || echo "No")${RESET}"
    
    echo -e "\n${BOLD_YELLOW}Please review the configuration above.${RESET}"
    echo -e "${YELLOW}Do you want to proceed with the analysis? (y/n)${RESET}"
    read -p " " confirm
    
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo -e "${RED}Analysis cancelled by user.${RESET}"
        exit 0
    fi
}

# Check if direct execution is requested
if [[ "$1" == "--run-direct" ]]; then
    echo "Running in direct execution mode"
    
    # Set direct mode flag
    export DIRECT_MODE=true
    
    # Check for required environment variables
    if [[ -z "$SUBJECT" || -z "$SIMULATION_NAME" || -z "$SPACE_TYPE" || -z "$ANALYSIS_TYPE" || -z "$FIELD_PATH" ]]; then
        echo -e "${RED}Error: Missing required environment variables for direct execution.${RESET}"
        echo "Required: SUBJECT, SIMULATION_NAME, SPACE_TYPE, ANALYSIS_TYPE, FIELD_PATH"
        exit 1
    fi
    
    # Set variables from environment without prompting
    subject_id="$SUBJECT"
    simulation_name="$SIMULATION_NAME"
    space_type="$SPACE_TYPE"
    analysis_type="$ANALYSIS_TYPE"
    field_path="$FIELD_PATH"
    field_basename=$(basename "$field_path")
    
    # Set space-specific variables
    if [ "$space_type" == "mesh" ]; then
        if [[ -z "$FIELD_NAME" ]]; then
            echo -e "${RED}Error: Missing required FIELD_NAME for mesh analysis.${RESET}"
            exit 1
        fi
        field_name="$FIELD_NAME"
    fi
    
    # Set analysis-specific variables
    if [ "$analysis_type" == "spherical" ]; then
        if [[ -z "$COORDINATES" || -z "$RADIUS" ]]; then
            echo -e "${RED}Error: Missing required variables for spherical analysis.${RESET}"
            echo "Required: COORDINATES, RADIUS"
            exit 1
        fi
        # Parse coordinates as array
        IFS=' ' read -ra coordinates <<< "$COORDINATES"
        radius="$RADIUS"
    else  # cortical
        if [ "$space_type" == "mesh" ]; then
            if [[ -z "$ATLAS_NAME" ]]; then
                echo -e "${RED}Error: Missing ATLAS_NAME for mesh cortical analysis.${RESET}"
                exit 1
            fi
            atlas_name="$ATLAS_NAME"
        else
            if [[ -z "$ATLAS_PATH" ]]; then
                echo -e "${RED}Error: Missing ATLAS_PATH for voxel cortical analysis.${RESET}"
                exit 1
            fi
            atlas_path="$ATLAS_PATH"
            atlas_basename=$(basename "$atlas_path")
        fi
        
        # Check if whole head or region
        if [[ "$WHOLE_HEAD" == "true" ]]; then
            whole_head="true"
        else
            if [[ -z "$REGION" ]]; then
                echo -e "${RED}Error: Missing REGION for cortical analysis.${RESET}"
                exit 1
            fi
            whole_head="false"
            region_name="$REGION"
        fi
    fi
    
    # Output directory
    if [[ -n "$OUTPUT_DIR" ]]; then
        output_dir="$OUTPUT_DIR"
    else
        # Generate organized output directory structure
        subject_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id"
        m2m_dir="$subject_dir/m2m_$subject_id"
        analyses_dir="$subject_dir/Analyses"
        
        # Directory structure: Analyses > Simulation > (Mesh or Voxel) > analysis_output
        analysis_type_dir="$analyses_dir/$simulation_name/${space_type^}"
        
        # Create target_info based on analysis type
        if [ "$analysis_type" == "spherical" ]; then
            target_info="sphere_x${coordinates[0]}_y${coordinates[1]}_z${coordinates[2]}_r${radius}"
        else  # cortical
            if [ "$whole_head" == "true" ]; then
                if [ "$space_type" == "mesh" ]; then
                    target_info="whole_head_${atlas_name}"
                else
                    atlas_name_base=$(basename "$atlas_path" | cut -d. -f1)
                    target_info="whole_head_${atlas_name_base}"
                fi
            else
                target_info="region_${region_name}"
            fi
        fi
        
        # Set output directory (without field name)
        output_dir="${analysis_type_dir}/${target_info}"
    fi
    
    # Set visualization flag
    visualize="${VISUALIZE:-true}"
    
    # Run the analysis without prompting
    run_analysis
    exit 0
fi

# Main script execution
show_welcome_message

# Collect subject ID
echo -e "${GREEN}Choose a subject by entering the corresponding number:${RESET}"
list_subjects
valid_subject=false
until $valid_subject; do
    read -p "Enter the number of the subject to analyze: " subject_num
    if [[ "$subject_num" =~ ^[0-9]+$ ]] && [ "$subject_num" -ge 1 ] && [ "$subject_num" -le "${#subjects[@]}" ]; then
        subject_id=${subjects[$((subject_num-1))]}
        valid_subject=true
    else
        reprompt
    fi
done

echo -e "${CYAN}Selected subject: $subject_id${RESET}"

# Set the m2m directory path
m2m_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id"

# Collect simulation name
echo -e "${GREEN}Choose a simulation:${RESET}"
if ! list_simulations "$subject_id"; then
    echo -e "${RED}No simulations found for subject $subject_id. Exiting.${RESET}"
    exit 1
fi

valid_simulation=false
until $valid_simulation; do
    read -p "Enter the number of the simulation to analyze: " sim_num
    if [[ "$sim_num" =~ ^[0-9]+$ ]] && [ "$sim_num" -ge 1 ] && [ "$sim_num" -le "${#simulations[@]}" ]; then
        simulation_name=${simulations[$((sim_num-1))]}
        valid_simulation=true
    else
        reprompt
    fi
done

echo -e "${CYAN}Selected simulation: $simulation_name${RESET}"

# Collect analysis space (mesh or voxel)
echo -e "${GREEN}Choose analysis space:${RESET}"
echo "1. Mesh (for .msh files)"
echo "2. Voxel (for NIfTI/MGZ files)"
valid_space=false
until $valid_space; do
    read -p "Enter your choice (1 or 2): " space_choice
    if [ "$space_choice" == "1" ]; then
        space_type="mesh"
        valid_space=true
    elif [ "$space_choice" == "2" ]; then
        space_type="voxel"
        valid_space=true
    else
        reprompt
    fi
done

echo -e "${CYAN}Selected analysis space: $space_type${RESET}"

# Collect analysis type (spherical or cortical)
echo -e "${GREEN}Choose analysis type:${RESET}"
echo "1. Spherical (ROI defined by coordinates and radius)"
echo "2. Cortical (ROI defined by brain atlas regions)"
valid_analysis=false
until $valid_analysis; do
    read -p "Enter your choice (1 or 2): " analysis_choice
    if [ "$analysis_choice" == "1" ]; then
        analysis_type="spherical"
        valid_analysis=true
    elif [ "$analysis_choice" == "2" ]; then
        analysis_type="cortical"
        valid_analysis=true
    else
        reprompt
    fi
done

echo -e "${CYAN}Selected analysis type: $analysis_type${RESET}"

# Collect field file
echo -e "${GREEN}Choose a field file:${RESET}"
if ! list_field_files "$subject_id" "$simulation_name" "$space_type"; then
    echo -e "${RED}No field files found for simulation $simulation_name. Exiting.${RESET}"
    exit 1
fi

valid_field=false
until $valid_field; do
    read -p "Enter the number of the field file to analyze: " field_num
    if [[ "$field_num" =~ ^[0-9]+$ ]] && [ "$field_num" -ge 1 ] && [ "$field_num" -le "${#field_files[@]}" ]; then
        field_basename=${field_files[$((field_num-1))]}
        
        # Construct the full path to the field file
        if [ "$space_type" == "mesh" ]; then
            field_path="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/$simulation_name/TI/mesh/$field_basename"
        else
            field_path="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/$simulation_name/TI/niftis/$field_basename"
        fi
        
        valid_field=true
    else
        reprompt
    fi
done

echo -e "${CYAN}Selected field file: $field_basename${RESET}"

# For mesh analysis, collect field name
if [ "$space_type" == "mesh" ]; then
    echo -e "${GREEN}Enter the field name within the mesh file (e.g., normE, TI_max):${RESET}"
    read -p " " field_name
    
    while [[ -z "$field_name" ]]; do
        echo -e "${RED}Field name cannot be empty. Please enter a valid field name.${RESET}"
        read -p " " field_name
    done
    
    echo -e "${CYAN}Field name: $field_name${RESET}"
fi

# Collect analysis-specific parameters
if [ "$analysis_type" == "spherical" ]; then
    # Collect coordinates
    echo -e "${GREEN}Enter coordinates for spherical ROI:${RESET}"
    coordinates=()
    
    # X coordinate
    valid_coord=false
    until $valid_coord; do
        read -p "Enter X coordinate: " coord_x
        if [[ "$coord_x" =~ ^-?[0-9]+\.?[0-9]*$ ]]; then
            coordinates+=("$coord_x")
            valid_coord=true
        else
            echo -e "${RED}Invalid coordinate. Please enter a valid number.${RESET}"
        fi
    done
    
    # Y coordinate
    valid_coord=false
    until $valid_coord; do
        read -p "Enter Y coordinate: " coord_y
        if [[ "$coord_y" =~ ^-?[0-9]+\.?[0-9]*$ ]]; then
            coordinates+=("$coord_y")
            valid_coord=true
        else
            echo -e "${RED}Invalid coordinate. Please enter a valid number.${RESET}"
        fi
    done
    
    # Z coordinate
    valid_coord=false
    until $valid_coord; do
        read -p "Enter Z coordinate: " coord_z
        if [[ "$coord_z" =~ ^-?[0-9]+\.?[0-9]*$ ]]; then
            coordinates+=("$coord_z")
            valid_coord=true
        else
            echo -e "${RED}Invalid coordinate. Please enter a valid number.${RESET}"
        fi
    done
    
    echo -e "${CYAN}Coordinates (x, y, z): ${coordinates[*]}${RESET}"
    
    # Collect radius
    valid_radius=false
    until $valid_radius; do
        read -p "Enter radius in mm: " radius
        if [[ "$radius" =~ ^[0-9]+\.?[0-9]*$ ]] && (( $(echo "$radius > 0" | bc -l) )); then
            valid_radius=true
        else
            echo -e "${RED}Invalid radius. Please enter a positive number.${RESET}"
        fi
    done
    
    echo -e "${CYAN}Radius: $radius mm${RESET}"
    
else  # cortical analysis
    if [ "$space_type" == "mesh" ]; then
        # For mesh, collect atlas name
        echo -e "${GREEN}Choose an atlas type:${RESET}"
        show_atlas_types
        
        valid_atlas=false
        until $valid_atlas; do
            read -p "Enter your choice (1-3): " atlas_choice
            if [ "$atlas_choice" == "1" ]; then
                atlas_name="DK40"
                valid_atlas=true
            elif [ "$atlas_choice" == "2" ]; then
                atlas_name="HCP_MMP1"
                valid_atlas=true
            elif [ "$atlas_choice" == "3" ]; then
                atlas_name="a2009s"
                valid_atlas=true
            else
                reprompt
            fi
        done
        
        echo -e "${CYAN}Selected atlas: $atlas_name${RESET}"
        
    else  # voxel
        # For voxel, collect atlas file path
        echo -e "${GREEN}Choose an atlas file:${RESET}"
        if ! list_atlas_files "$subject_id"; then
            echo -e "${RED}No atlas files found for subject $subject_id. Exiting.${RESET}"
            exit 1
        fi
        
        valid_atlas=false
        until $valid_atlas; do
            read -p "Enter the number of the atlas file to use: " atlas_num
            if [[ "$atlas_num" =~ ^[0-9]+$ ]] && [ "$atlas_num" -ge 1 ] && [ "$atlas_num" -le "${#atlas_files[@]}" ]; then
                atlas_basename=${atlas_files[$((atlas_num-1))]}
                atlas_path="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id/segmentation/$atlas_basename"
                valid_atlas=true
            else
                reprompt
            fi
        done
        
        echo -e "${CYAN}Selected atlas file: $atlas_basename${RESET}"
    fi
    
    # Ask if analyzing whole head or specific region
    echo -e "${GREEN}Do you want to analyze the whole head or a specific region?${RESET}"
    echo "1. Whole Head"
    echo "2. Specific Region"
    
    valid_scope=false
    until $valid_scope; do
        read -p "Enter your choice (1 or 2): " scope_choice
        if [ "$scope_choice" == "1" ]; then
            whole_head="true"
            valid_scope=true
        elif [ "$scope_choice" == "2" ]; then
            whole_head="false"
            valid_scope=true
        else
            reprompt
        fi
    done
    
    if [ "$whole_head" == "false" ]; then
        # Prompt for region selection
        prompt_region_selection "$subject_id" "$space_type" "$atlas_name" "$atlas_path"
        
        while [[ -z "$region_name" ]]; do
            echo -e "${RED}Region name cannot be empty. Please enter a valid region name.${RESET}"
            prompt_region_selection "$subject_id" "$space_type" "$atlas_name" "$atlas_path"
        done
        
        echo -e "${CYAN}Target region: $region_name${RESET}"
    else
        echo -e "${CYAN}Analysis scope: Whole Head${RESET}"
    fi
fi

# Ask for visualization
echo -e "${GREEN}Do you want to generate visualizations? (y/n)${RESET}"
read -p " " vis_choice
if [[ "$vis_choice" == "y" || "$vis_choice" == "Y" ]]; then
    visualize="true"
    echo -e "${CYAN}Visualizations will be generated.${RESET}"
else
    visualize="false"
    echo -e "${CYAN}No visualizations will be generated.${RESET}"
fi

# Set up output directory
# Generate organized output directory structure
subject_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id"
analyses_dir="$subject_dir/Analyses"

# Directory structure: Analyses > Simulation > (Mesh or Voxel) > analysis_output
analysis_type_dir="$analyses_dir/$simulation_name/${space_type^}"

# Create target_info based on analysis type
if [ "$analysis_type" == "spherical" ]; then
    target_info="sphere_x${coordinates[0]}_y${coordinates[1]}_z${coordinates[2]}_r${radius}"
else  # cortical
    if [ "$whole_head" == "true" ]; then
        if [ "$space_type" == "mesh" ]; then
            target_info="whole_head_${atlas_name}"
        else
            atlas_name_base=$(basename "$atlas_path" | cut -d. -f1)
            target_info="whole_head_${atlas_name_base}"
        fi
    else
        target_info="region_${region_name}"
    fi
fi

# Set output directory (without field name)
output_dir="${analysis_type_dir}/${target_info}"

# Check if output directory exists
if [ -d "$output_dir" ]; then
    echo -e "${YELLOW}Warning: Output directory already exists: $output_dir${RESET}"
    echo -e "${YELLOW}Do you want to overwrite it? (y/n)${RESET}"
    read -p " " overwrite
    
    if [[ "$overwrite" != "y" && "$overwrite" != "Y" ]]; then
        echo -e "${RED}Analysis cancelled. Please specify a different output directory.${RESET}"
        exit 0
    fi
fi

# Show confirmation dialog
show_confirmation_dialog

# Create output directory
mkdir -p "$output_dir"

# Run the analysis
run_analysis

echo -e "${GREEN}Analysis completed.${RESET}"
