#!/bin/bash

###########################################
# Neuroimaging Group Field Analyzer CLI
# This script provides a command-line interface for analyzing 
# mesh and voxel-based neuroimaging data across multiple subjects.
###########################################

set -e  # Exit immediately if a command exits with a non-zero status

umask 0000  # Set umask to 0000 to ensure all created files and directories have permissions 777

# Base directories
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="/mnt/$PROJECT_DIR_NAME"

# Global variables for per-subject configurations
declare -A subject_simulations
declare -A subject_field_paths

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

# Configuration setup
ti_csc_dir="$project_dir/ti-csc"
config_dir="$ti_csc_dir/config"
config_file="$config_dir/group_analyzer_config.json"

# Function to read configuration
read_config() {
    local key=$1
    local subkey=$2
    if [ -f "$config_file" ]; then
        if [ -n "$subkey" ]; then
            # Use -r to get raw output and handle boolean values correctly
            jq -r "if .$key.$subkey == false then \"false\" elif .$key.$subkey == true then \"true\" else .$key.$subkey end" "$config_file" 2>/dev/null
        else
            jq -r "if .$key == false then \"false\" elif .$key == true then \"true\" else .$key end" "$config_file" 2>/dev/null
        fi
    fi
}

# Function to check if prompting is enabled for a given key
is_prompt_enabled() {
    local key=$1
    local prompt_enabled=$(read_config "$key" "prompt")
    if [ "$prompt_enabled" = "disable" ]; then
        return 1
    fi
    return 0
}

# Function to get default value for a given key
get_default_value() {
    local key=$1
    read_config "$key" "default"
}

# Function to validate input against allowed options
validate_option() {
    local input=$1
    local key=$2
    local options=($(jq -r ".$key.options[] // empty" "$config_file"))
    
    if [ ${#options[@]} -eq 0 ]; then
        return 0  # No options defined, so any input is valid
    fi
    
    for option in "${options[@]}"; do
        if [ "$input" == "$option" ]; then
            return 0  # Input matches an allowed option
        fi
    done
    
    return 1  # Input doesn't match any allowed option
}

# Ensure ti-csc directory exists and set permissions
if [ ! -d "$ti_csc_dir" ]; then
    mkdir -p "$ti_csc_dir"
    chmod 777 "$ti_csc_dir"
    echo -e "${GREEN}Created ti-csc directory at $ti_csc_dir with permissions 777.${RESET}"
else
    chmod 777 "$ti_csc_dir"
fi

# Ensure config directory exists
if [ ! -d "$config_dir" ]; then
    mkdir -p "$config_dir"
    chmod 777 "$config_dir"
    echo -e "${GREEN}Created config directory at $config_dir with permissions 777.${RESET}"
else
    chmod 777 "$config_dir"
fi

# Create default config file if it doesn't exist
if [ ! -f "$config_file" ]; then
    cat > "$config_file" << EOL
{
    "subjects": {
        "prompt": "enable",
        "default": null
    },
    "simulation": {
        "prompt": "enable",
        "default": null
    },
    "space_type": {
        "prompt": "enable",
        "default": "mesh",
        "options": ["mesh", "voxel"]
    },
    "analysis_type": {
        "prompt": "enable",
        "default": "spherical",
        "options": ["spherical", "cortical"]
    },
    "field_name": {
        "prompt": "enable",
        "default": "normE"
    },
    "coordinates": {
        "prompt": "enable",
        "default": [0, 0, 0]
    },
    "radius": {
        "prompt": "enable",
        "default": 10
    },
    "atlas": {
        "prompt": "enable",
        "default": "DK40",
        "options": ["DK40", "HCP_MMP1", "a2009s"]
    },
    "whole_head": {
        "prompt": "enable",
        "default": false
    },
    "compare": {
        "prompt": "enable",
        "default": true
    },
    "output_dir": {
        "prompt": "enable",
        "default": null
    }
}
EOL
    chmod 777 "$config_file"
    echo -e "${GREEN}Created default group analyzer configuration file at $config_file${RESET}"
else
    echo -e "${CYAN}Using configuration file: $config_file${RESET}"
fi

# =========================================
# Configuration and Setup Functions
# =========================================

# Function to handle invalid input and reprompt
reprompt() {
    echo -e "${RED}Invalid input. Please try again.${RESET}"
}

# Function to display welcome message
show_welcome_message() {
    clear  # Clear the screen before starting
    echo -e "${BOLD_CYAN}╔════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD_CYAN}║      TI-CSC Group Analyzer Tool       ║${RESET}"
    echo -e "${BOLD_CYAN}╚════════════════════════════════════════╝${RESET}"
    echo -e "${CYAN}Version 1.0 - $(date +%Y)${RESET}\n"
    echo -e "${YELLOW}This tool runs analysis across multiple subjects${RESET}"
    echo -e "${YELLOW}and generates comparison results.${RESET}\n"
}

# =========================================
# Input Collection Functions
# =========================================

# Function to collect subject information
collect_subjects_info() {
    if ! is_prompt_enabled "subjects"; then
        local default_value=$(get_default_value "subjects")
        if [ -n "$default_value" ]; then
            # Parse JSON array into bash array
            selected_subjects=($(echo "$default_value" | jq -r '.[]'))
            echo -e "${CYAN}Using default subjects: ${selected_subjects[*]}${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Choose subjects for group analysis:${RESET}"
    list_subjects
    
    selected_subjects=()
    
    echo -e "${YELLOW}Enter subject numbers separated by spaces (e.g., 1 3 5):${RESET}"
    echo -e "${YELLOW}Or enter 'all' to select all subjects:${RESET}"
    
    valid_selection=false
    until $valid_selection; do
        read -p "Enter your selection: " subject_input
        
        if [ "$subject_input" == "all" ]; then
            selected_subjects=("${subjects[@]}")
            valid_selection=true
            echo -e "${CYAN}Selected all ${#selected_subjects[@]} subjects${RESET}"
        else
            # Parse space-separated numbers
            read -ra subject_nums <<< "$subject_input"
            selected_subjects=()
            
            for num in "${subject_nums[@]}"; do
                if [[ "$num" =~ ^[0-9]+$ ]] && [ "$num" -ge 1 ] && [ "$num" -le "${#subjects[@]}" ]; then
                    selected_subjects+=(${subjects[$((num-1))]})
                else
                    echo -e "${RED}Invalid subject number: $num${RESET}"
                    selected_subjects=()
                    break
                fi
            done
            
            if [ ${#selected_subjects[@]} -gt 0 ]; then
                valid_selection=true
                echo -e "${CYAN}Selected ${#selected_subjects[@]} subjects: ${selected_subjects[*]}${RESET}"
            else
                reprompt
            fi
        fi
    done
}

# Function to collect simulation information
collect_simulation_info() {
    # For group analysis, we need to collect simulation info for each subject
    
    echo -e "${GREEN}Collecting simulation and field information for each subject...${RESET}\n"
    
    for subject_id in "${selected_subjects[@]}"; do
        echo -e "${BOLD_CYAN}=== Subject: $subject_id ===${RESET}"
        
        # List simulations for this subject
        if ! list_simulations "$subject_id"; then
            echo -e "${RED}No simulations found for subject $subject_id. Skipping this subject.${RESET}"
            continue
        fi
        
        # Get simulation selection for this subject
        valid_simulation=false
        until $valid_simulation; do
            read -p "Enter the number of the simulation for subject $subject_id: " sim_num
            if [[ "$sim_num" =~ ^[0-9]+$ ]] && [ "$sim_num" -ge 1 ] && [ "$sim_num" -le "${#simulations[@]}" ]; then
                selected_simulation=${simulations[$((sim_num-1))]}
                valid_simulation=true
            else
                reprompt
            fi
        done
        
        subject_simulations["$subject_id"]="$selected_simulation"
        echo -e "${CYAN}Selected simulation for $subject_id: $selected_simulation${RESET}"
        
        # Get field file for this subject
        echo -e "${GREEN}Choose a field file for subject $subject_id:${RESET}"
        if ! list_field_files "$subject_id" "$selected_simulation" "$space_type"; then
            echo -e "${RED}No field files found for subject $subject_id simulation $selected_simulation. Skipping this subject.${RESET}"
            continue
        fi
        
        valid_field=false
        until $valid_field; do
            read -p "Enter the number of the field file for subject $subject_id: " field_num
            if [[ "$field_num" =~ ^[0-9]+$ ]] && [ "$field_num" -ge 1 ] && [ "$field_num" -le "${#field_files[@]}" ]; then
                field_basename=${field_files[$((field_num-1))]}
                
                # Construct the full path to the field file
                if [ "$space_type" == "mesh" ]; then
                    field_path="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/$selected_simulation/TI/mesh/$field_basename"
                else
                    field_path="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/$selected_simulation/TI/niftis/$field_basename"
                fi
                
                subject_field_paths["$subject_id"]="$field_path"
                valid_field=true
            else
                reprompt
            fi
        done
        
        echo -e "${CYAN}Selected field file for $subject_id: $field_basename${RESET}\n"
    done
    
    # Validate that we have at least one subject with valid simulation and field
    if [ ${#subject_simulations[@]} -eq 0 ]; then
        echo -e "${RED}No valid subjects with simulations and field files found. Exiting.${RESET}"
        exit 1
    fi
    
    # Update selected_subjects to only include those with valid configurations
    valid_subjects=()
    for subject_id in "${selected_subjects[@]}"; do
        if [[ -n "${subject_simulations[$subject_id]}" && -n "${subject_field_paths[$subject_id]}" ]]; then
            valid_subjects+=("$subject_id")
        fi
    done
    selected_subjects=("${valid_subjects[@]}")
    
    echo -e "${GREEN}✓ Collected simulation and field information for ${#selected_subjects[@]} subjects${RESET}"
}

# Function to collect analysis space information
collect_space_info() {
    if ! is_prompt_enabled "space_type"; then
        local default_value=$(get_default_value "space_type")
        if [ -n "$default_value" ]; then
            if validate_option "$default_value" "space_type"; then
                space_type="$default_value"
                echo -e "${CYAN}Using default space type: $space_type${RESET}"
                return
            else
                echo -e "${RED}Invalid default space type in configuration: $default_value${RESET}"
            fi
        fi
    fi

    echo -e "${GREEN}Choose analysis space:${RESET}"
    echo "1. Mesh (for .msh files)"
    echo "2. Voxel (for NIfTI/MGZ files)"
    valid_space=false
    until $valid_space; do
        read -p "Enter your choice (1 or 2): " space_choice
        if [ "$space_choice" == "1" ]; then
            space_type="mesh"
            if validate_option "$space_type" "space_type"; then
                valid_space=true
            else
                echo -e "${RED}Invalid space type: $space_type${RESET}"
            fi
        elif [ "$space_choice" == "2" ]; then
            space_type="voxel"
            if validate_option "$space_type" "space_type"; then
                valid_space=true
            else
                echo -e "${RED}Invalid space type: $space_type${RESET}"
            fi
        else
            reprompt
        fi
    done

    echo -e "${CYAN}Selected analysis space: $space_type${RESET}"
}

# Function to collect analysis type information
collect_analysis_type() {
    if ! is_prompt_enabled "analysis_type"; then
        local default_value=$(get_default_value "analysis_type")
        if [ -n "$default_value" ]; then
            if validate_option "$default_value" "analysis_type"; then
                analysis_type="$default_value"
                echo -e "${CYAN}Using default analysis type: $analysis_type${RESET}"
                return
            else
                echo -e "${RED}Invalid default analysis type in configuration: $default_value${RESET}"
            fi
        fi
    fi

    echo -e "${GREEN}Choose analysis type:${RESET}"
    echo "1. Spherical (ROI defined by coordinates and radius)"
    if [ "$space_type" == "voxel" ]; then
        echo "2. Sub/Cortical (ROI defined by brain atlas regions)"
    else
        echo "2. Cortical (ROI defined by brain atlas regions)"
    fi
    valid_analysis=false
    until $valid_analysis; do
        read -p "Enter your choice (1 or 2): " analysis_choice
        if [ "$analysis_choice" == "1" ]; then
            analysis_type="spherical"
            if validate_option "$analysis_type" "analysis_type"; then
                valid_analysis=true
            else
                echo -e "${RED}Invalid analysis type: $analysis_type${RESET}"
            fi
        elif [ "$analysis_choice" == "2" ]; then
            analysis_type="cortical"
            if validate_option "$analysis_type" "analysis_type"; then
                valid_analysis=true
            else
                echo -e "${RED}Invalid analysis type: $analysis_type${RESET}"
            fi
        else
            reprompt
        fi
    done

    echo -e "${CYAN}Selected analysis type: $analysis_type${RESET}"
}

# Function to collect field name for mesh analysis
collect_field_name() {
    if [ "$space_type" != "mesh" ]; then
        return
    fi

    if ! is_prompt_enabled "field_name"; then
        local default_value=$(get_default_value "field_name")
        if [ -n "$default_value" ]; then
            field_name="$default_value"
            echo -e "${CYAN}Using default field name: $field_name${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Enter the field name within the mesh files (e.g., normE, TI_max):${RESET}"
    read -p " " field_name
    
    while [[ -z "$field_name" ]]; do
        echo -e "${RED}Field name cannot be empty. Please enter a valid field name.${RESET}"
        read -p " " field_name
    done
    
    echo -e "${CYAN}Field name: $field_name${RESET}"
}

# Function to collect spherical analysis parameters
collect_spherical_params() {
    if ! is_prompt_enabled "coordinates"; then
        local default_coords=$(get_default_value "coordinates")
        if [ -n "$default_coords" ]; then
            # Parse the JSON array into bash array
            coordinates=($(echo "$default_coords" | jq -r '.[]'))
            echo -e "${CYAN}Using default coordinates: ${coordinates[*]}${RESET}"
        fi
    else
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
    fi
    
    echo -e "${CYAN}Coordinates (x, y, z): ${coordinates[*]}${RESET}"
    
    # Collect radius
    if ! is_prompt_enabled "radius"; then
        local default_radius=$(get_default_value "radius")
        if [ -n "$default_radius" ]; then
            radius="$default_radius"
            echo -e "${CYAN}Using default radius: $radius mm${RESET}"
        fi
    else
        valid_radius=false
        until $valid_radius; do
            read -p "Enter radius in mm: " radius
            if [[ "$radius" =~ ^[0-9]+\.?[0-9]*$ ]] && (( $(echo "$radius > 0" | bc -l) )); then
                valid_radius=true
            else
                echo -e "${RED}Invalid radius. Please enter a positive number.${RESET}"
            fi
        done
    fi
    
    echo -e "${CYAN}Radius: $radius mm${RESET}"
}

# Function to collect cortical analysis parameters
collect_cortical_params() {
    if [ "$space_type" == "mesh" ]; then
        # For mesh, collect atlas name
        if ! is_prompt_enabled "atlas"; then
            local default_atlas=$(get_default_value "atlas")
            if [ -n "$default_atlas" ]; then
                if validate_option "$default_atlas" "atlas"; then
                    atlas_name="$default_atlas"
                    echo -e "${CYAN}Using default atlas: $atlas_name${RESET}"
                else
                    echo -e "${RED}Invalid default atlas in configuration: $default_atlas${RESET}"
                fi
            fi
        else
            echo -e "${GREEN}Choose an atlas type:${RESET}"
            show_atlas_types
            
            valid_atlas=false
            until $valid_atlas; do
                read -p "Enter your choice (1-3): " atlas_choice
                case "$atlas_choice" in
                    "1") atlas_name="DK40" ;;
                    "2") atlas_name="HCP_MMP1" ;;
                    "3") atlas_name="a2009s" ;;
                    *) 
                        echo -e "${RED}Invalid choice. Please enter 1, 2, or 3.${RESET}"
                        continue
                        ;;
                esac
                
                if validate_option "$atlas_name" "atlas"; then
                    valid_atlas=true
                else
                    echo -e "${RED}Invalid atlas type: $atlas_name${RESET}"
                fi
            done
        fi
        
        echo -e "${CYAN}Selected atlas: $atlas_name${RESET}"
        
    else  # voxel
        echo -e "${CYAN}For voxel cortical analysis, each subject needs its own atlas file.${RESET}"
        echo -e "${YELLOW}The script will automatically find appropriate atlas files for each subject.${RESET}"
        
        # Validate that all subjects have atlas files
        echo -e "${CYAN}Validating atlas files for all subjects...${RESET}"
        missing_atlas_subjects=()
        for subject_id in "${selected_subjects[@]}"; do
            if ! find_subject_atlas_file "$subject_id"; then
                missing_atlas_subjects+=("$subject_id")
            fi
        done
        
        if [ ${#missing_atlas_subjects[@]} -gt 0 ]; then
            echo -e "${RED}Error: No atlas files found for the following subjects:${RESET}"
            for subject in "${missing_atlas_subjects[@]}"; do
                echo -e "${RED}  - $subject${RESET}"
            done
            echo -e "${RED}Please ensure FreeSurfer preprocessing has been completed for all subjects.${RESET}"
            exit 1
        fi
        echo -e "${GREEN}✓ Atlas files validated for all subjects${RESET}"
    fi
    
    # Handle whole head vs specific region selection
    if ! is_prompt_enabled "whole_head"; then
        # Use default value from config
        local default_whole_head=$(get_default_value "whole_head")
        if [ -n "$default_whole_head" ]; then
            # Convert JSON boolean to bash boolean
            if [ "$default_whole_head" = "true" ] || [ "$default_whole_head" = "false" ]; then
                whole_head="$default_whole_head"
                echo -e "${CYAN}Using default analysis scope: ${whole_head}${RESET}"
                
                # If default is false, proceed to region selection
                if [ "$whole_head" = "false" ]; then
                    echo -e "${GREEN}Please select a specific region to analyze:${RESET}"
                    collect_region_selection
                    
                    while [[ -z "$region_name" ]]; do
                        echo -e "${RED}Region name cannot be empty. Please enter a valid region name.${RESET}"
                        collect_region_selection
                    done
                    
                    echo -e "${CYAN}Target region: $region_name${RESET}"
                else
                    echo -e "${CYAN}Analysis scope: Whole Head${RESET}"
                fi
            else
                echo -e "${RED}Invalid whole_head value in configuration. Must be true or false.${RESET}"
                exit 1
            fi
        else
            echo -e "${RED}No default whole_head value specified in configuration.${RESET}"
            exit 1
        fi
    else
        # Prompt user for whole head or specific region
        echo -e "${GREEN}Do you want to analyze the whole head or a specific region?${RESET}"
        echo "1. Whole Head"
        echo "2. Specific Region"
        
        valid_scope=false
        until $valid_scope; do
            read -p "Enter your choice (1 or 2): " scope_choice
            if [ "$scope_choice" == "1" ]; then
                whole_head="true"
                valid_scope=true
                echo -e "${CYAN}Analysis scope: Whole Head${RESET}"
            elif [ "$scope_choice" == "2" ]; then
                whole_head="false"
                valid_scope=true
                echo -e "${GREEN}Please select a specific region to analyze:${RESET}"
                collect_region_selection
                
                while [[ -z "$region_name" ]]; do
                    echo -e "${RED}Region name cannot be empty. Please enter a valid region name.${RESET}"
                    collect_region_selection
                done
                
                echo -e "${CYAN}Target region: $region_name${RESET}"
            else
                reprompt
            fi
        done
    fi
}

# Function to collect region selection (simplified for group analysis)
collect_region_selection() {
    echo -e "${GREEN}Enter the region name/identifier:${RESET}"
    echo -e "${YELLOW}Examples:${RESET}"
    echo -e "  - For mesh: superiorfrontal, bankssts, etc.${RESET}"
    echo -e "  - For voxel: Left-Hippocampus, ctx-lh-superiorfrontal, etc.${RESET}"
    read -p " " region_name
}

# Function to collect comparison and output settings
collect_output_settings() {
    # Collect comparison preference
    if ! is_prompt_enabled "compare"; then
        local default_compare=$(get_default_value "compare")
        if [ -n "$default_compare" ]; then
            compare_analyses="$default_compare"
            echo -e "${CYAN}Using default comparison setting: $compare_analyses${RESET}"
        fi
    else
        echo -e "${GREEN}Do you want to run comparison analysis after processing all subjects? (y/n)${RESET}"
        read -p " " compare_choice
        if [[ "$compare_choice" == "y" || "$compare_choice" == "Y" ]]; then
            compare_analyses="true"
            echo -e "${CYAN}Comparison analysis will be performed.${RESET}"
        else
            compare_analyses="false"
            echo -e "${CYAN}No comparison analysis will be performed.${RESET}"
        fi
    fi
    
    # Collect output directory
    if ! is_prompt_enabled "output_dir"; then
        local default_output=$(get_default_value "output_dir")
        if [ -n "$default_output" ]; then
            output_dir="$default_output"
            echo -e "${CYAN}Using default output directory: $output_dir${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Enter output directory for group analysis results:${RESET}"
    echo -e "${YELLOW}This will store comparison results and group summaries.${RESET}"
    echo -e "${YELLOW}Leave empty to use default: $project_dir/ti-csc/group_analyses/${RESET}"
    read -p " " output_dir
    
    if [[ -z "$output_dir" ]]; then
        # Create default output directory with timestamp
        timestamp=$(date +"%Y%m%d_%H%M%S")
        output_dir="$project_dir/ti-csc/group_analyses/group_${analysis_type}_${space_type}_${timestamp}"
    fi
    
    echo -e "${CYAN}Output directory: $output_dir${RESET}"
}

# =========================================
# Helper Functions
# =========================================

# Function to find atlas file for a subject (voxel mode)
find_subject_atlas_file() {
    local subject_id=$1
    
    # Check FreeSurfer mri directory for common atlas files
    local freesurfer_dir="$project_dir/derivatives/freesurfer/sub-$subject_id/$subject_id/mri"
    local atlas_files=("aparc.DKTatlas+aseg.mgz" "aparc.a2009s+aseg.mgz")
    
    for atlas in "${atlas_files[@]}"; do
        if [ -f "$freesurfer_dir/$atlas" ]; then
            return 0  # Found at least one atlas
        fi
    done
    
    return 1  # No atlas found
}

# Function to get field path for a subject
get_subject_field_path() {
    local subject_id=$1
    echo "${subject_field_paths[$subject_id]}"
}

# Function to get atlas path for a subject (voxel mode)
get_subject_atlas_path() {
    local subject_id=$1
    
    # Check FreeSurfer mri directory for atlas files (prefer DKTatlas)
    local freesurfer_dir="$project_dir/derivatives/freesurfer/sub-$subject_id/$subject_id/mri"
    
    if [ -f "$freesurfer_dir/aparc.DKTatlas+aseg.mgz" ]; then
        echo "$freesurfer_dir/aparc.DKTatlas+aseg.mgz"
    elif [ -f "$freesurfer_dir/aparc.a2009s+aseg.mgz" ]; then
        echo "$freesurfer_dir/aparc.a2009s+aseg.mgz"
    else
        return 1
    fi
}

# Function to get simulation name for a subject
get_subject_simulation() {
    local subject_id=$1
    echo "${subject_simulations[$subject_id]}"
}

# =========================================
# List and Display Functions
# =========================================

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
    simulations=()
    
    # Check mesh simulations
    mesh_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/*/TI/mesh"
    for sim_path in $mesh_dir; do
        if [ -d "$sim_path" ]; then
            sim_name=$(basename "$(dirname "$(dirname "$sim_path")")")
            simulations+=("$sim_name")
        fi
    done
    
    # Check voxel simulations
    voxel_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/*/TI/niftis"
    for sim_path in $voxel_dir; do
        if [ -d "$sim_path" ]; then
            sim_name=$(basename "$(dirname "$(dirname "$sim_path")")")
            if [[ ! " ${simulations[@]} " =~ " ${sim_name} " ]]; then
                simulations+=("$sim_name")
            fi
        fi
    done
    
    if [ ${#simulations[@]} -eq 0 ]; then
        return 1
    fi
    
    echo -e "${BOLD_CYAN}Available Simulations:${RESET}"
    echo "-------------------"
    for i in "${!simulations[@]}"; do
        printf "%3d. %s\n" $((i+1)) "${simulations[i]}"
    done
    echo
    return 0
}

# Function to show available atlas types
show_atlas_types() {
    echo -e "${BOLD_CYAN}Available Atlas Types:${RESET}"
    echo "-------------------"
    echo "1. DK40 (Desikan-Killiany 40)"
    echo "2. HCP_MMP1 (Human Connectome Project Multi-Modal Parcellation)"
    echo "3. a2009s (Automated Anatomical Labeling)"
    echo
}

# Function to list available field files
list_field_files() {
    local subject_id=$1
    local simulation_name=$2
    local space_type=$3
    field_files=()
    
    if [ "$space_type" == "mesh" ]; then
        field_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/$simulation_name/TI/mesh"
        if [ -d "$field_dir" ]; then
            while IFS= read -r -d '' file; do
                if [[ "$file" == *.msh ]]; then
                    field_files+=("$(basename "$file")")
                fi
            done < <(find "$field_dir" -name "*.msh" -print0)
        fi
    else
        field_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/$simulation_name/TI/niftis"
        if [ -d "$field_dir" ]; then
            while IFS= read -r -d '' file; do
                if [[ "$file" == *.nii || "$file" == *.nii.gz ]]; then
                    field_files+=("$(basename "$file")")
                fi
            done < <(find "$field_dir" -name "*.nii" -o -name "*.nii.gz" -print0)
        fi
    fi
    
    if [ ${#field_files[@]} -eq 0 ]; then
        return 1
    fi
    
    echo -e "${BOLD_CYAN}Available Field Files:${RESET}"
    echo "-------------------"
    for i in "${!field_files[@]}"; do
        printf "%3d. %s\n" $((i+1)) "${field_files[i]}"
    done
    echo
    return 0
}

# Function to show confirmation dialog
show_confirmation_dialog() {
    echo -e "\n${BOLD_CYAN}Group Analysis Configuration Summary${RESET}"
    echo -e "----------------------------------------"
    echo -e "${BOLD}Selected Parameters:${RESET}"
    
    # Subject Information
    echo -e "\n${BOLD_CYAN}Subject Information:${RESET}"
    echo -e "Number of subjects: ${CYAN}${#selected_subjects[@]}${RESET}"
    
    # Show per-subject configurations
    echo -e "\n${BOLD_CYAN}Per-Subject Configurations:${RESET}"
    for subject_id in "${selected_subjects[@]}"; do
        local sim_name="${subject_simulations[$subject_id]}"
        local field_path="${subject_field_paths[$subject_id]}"
        local field_basename=$(basename "$field_path")
        echo -e "  ${CYAN}$subject_id${RESET}: $sim_name → $field_basename"
    done
    
    # Analysis Parameters
    echo -e "\n${BOLD_CYAN}Analysis Parameters:${RESET}"
    echo -e "Space Type: ${CYAN}$space_type${RESET}"
    echo -e "Analysis Type: ${CYAN}$analysis_type${RESET}"
    
    if [ "$space_type" == "mesh" ]; then
        echo -e "Field Name: ${CYAN}$field_name${RESET}"
    fi
    
    # Analysis-specific Parameters
    if [ "$analysis_type" == "spherical" ]; then
        echo -e "\n${BOLD_CYAN}Spherical Analysis Parameters:${RESET}"
        echo -e "Coordinates: ${CYAN}(${coordinates[0]}, ${coordinates[1]}, ${coordinates[2]})${RESET}"
        echo -e "Radius: ${CYAN}$radius mm${RESET}"
    else
        echo -e "\n${BOLD_CYAN}Cortical Analysis Parameters:${RESET}"
        if [ "$space_type" == "mesh" ]; then
            echo -e "Atlas: ${CYAN}$atlas_name${RESET}"
        else
            echo -e "Atlas: ${CYAN}Subject-specific atlas files${RESET}"
        fi
        echo -e "Analysis Scope: ${CYAN}$([ "$whole_head" == "true" ] && echo "Whole Head" || echo "Region: $region_name")${RESET}"
    fi
    
    # Output Settings
    echo -e "\n${BOLD_CYAN}Output Settings:${RESET}"
    echo -e "Output Directory: ${CYAN}$output_dir${RESET}"
    echo -e "Run Comparison: ${CYAN}$([ "$compare_analyses" == "true" ] && echo "Yes" || echo "No")${RESET}"
    echo -e "Generate Visualizations: ${CYAN}Yes (always enabled)${RESET}"
    
    echo -e "\n${BOLD_YELLOW}Please review the configuration above.${RESET}"
    echo -e "${YELLOW}Do you want to proceed with the group analysis? (y/n)${RESET}"
    read -p " " confirm
    
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo -e "${RED}Analysis cancelled by user.${RESET}"
        exit 0
    fi
}

# Function to run the group analysis
run_group_analysis() {
    # Build the command to run group_analyzer.py
    local cmd=(simnibs_python "$script_dir/../analyzer/group_analyzer.py")
    
    # Add common parameters
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
        fi
        
        if [ "$whole_head" == "true" ]; then
            cmd+=(--whole_head)
        else
            cmd+=(--region "$region_name")
        fi
    fi
    
    # Add comparison flag if enabled
    if [ "$compare_analyses" == "true" ]; then
        cmd+=(--compare)
    fi
    
    # Always enable visualizations
    cmd+=(--visualize)
    
    # Add subject specifications (now using per-subject field paths)
    for subject_id in "${selected_subjects[@]}"; do
        local m2m_path="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id"
        local field_path="${subject_field_paths[$subject_id]}"
        
        if [ -z "$field_path" ] || [ ! -f "$field_path" ]; then
            echo -e "${RED}Error: No field file found for subject $subject_id${RESET}"
            exit 1
        fi
        
        if [ "$space_type" == "voxel" ] && [ "$analysis_type" == "cortical" ]; then
            # For voxel cortical analysis, need to include atlas path
            local atlas_path=$(get_subject_atlas_path "$subject_id")
            if [ -z "$atlas_path" ] || [ ! -f "$atlas_path" ]; then
                echo -e "${RED}Error: No atlas file found for subject $subject_id${RESET}"
                exit 1
            fi
            cmd+=(--subject "$subject_id" "$m2m_path" "$field_path" "$atlas_path")
        else
            cmd+=(--subject "$subject_id" "$m2m_path" "$field_path")
        fi
    done
    
    # Set environment variables
    export PROJECT_DIR="$project_dir"
    
    # Print the command being executed
    echo -e "${CYAN}Executing command:${RESET}"
    echo -e "${BOLD_CYAN}${cmd[*]}${RESET}"
    echo
    
    # Run the group analysis
    echo -e "${CYAN}Running group analysis...${RESET}"
    if "${cmd[@]}"; then
        echo -e "${GREEN}Group analysis completed successfully.${RESET}"
        if [ "$compare_analyses" == "true" ]; then
            echo -e "${GREEN}Comparison results saved to: $output_dir${RESET}"
        fi
    else
        echo -e "${RED}Group analysis failed.${RESET}"
        exit 1
    fi
}

# =========================================
# Main Execution Flow
# =========================================

# Main script execution
show_welcome_message

# Collect all necessary inputs
collect_subjects_info
collect_space_info
collect_analysis_type
collect_simulation_info  # This now collects both simulation and field info per subject

# Collect space-specific parameters
if [ "$space_type" == "mesh" ]; then
    collect_field_name
fi

# Collect analysis-specific parameters
if [ "$analysis_type" == "spherical" ]; then
    collect_spherical_params
else
    collect_cortical_params
fi

# Collect output settings
collect_output_settings

# Show confirmation dialog
show_confirmation_dialog

# Run the group analysis
run_group_analysis

echo -e "\n${BOLD_GREEN}Group analysis completed successfully!${RESET}"
if [ "$compare_analyses" == "true" ]; then
    echo -e "${GREEN}Results and comparisons are available in: $output_dir${RESET}"
fi 
