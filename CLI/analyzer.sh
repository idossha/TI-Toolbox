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

# Configuration setup
ti_csc_dir="$project_dir/ti-csc"
config_dir="$ti_csc_dir/config"
config_file="$config_dir/analyzer_config.json"

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
    "subject": {
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
    "visualize": {
        "prompt": "enable",
        "default": true
    }
}
EOL
    chmod 777 "$config_file"
    echo -e "${GREEN}Created default analyzer configuration file at $config_file${RESET}"
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
    echo -e "${BOLD_CYAN}║         TI-CSC Analyzer Tool          ║${RESET}"
    echo -e "${BOLD_CYAN}╚════════════════════════════════════════╝${RESET}"
    echo -e "${CYAN}Version 1.0 - $(date +%Y)${RESET}\n"
}

# =========================================
# Input Collection Functions
# =========================================

# Function to collect subject information
collect_subject_info() {
    if ! is_prompt_enabled "subject"; then
        local default_value=$(get_default_value "subject")
        if [ -n "$default_value" ]; then
            subject_id="$default_value"
            echo -e "${CYAN}Using default subject: $subject_id${RESET}"
            m2m_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id"
            return
        fi
    fi

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
    m2m_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id"
}

# Function to collect simulation information
collect_simulation_info() {
    if ! is_prompt_enabled "simulation"; then
        local default_value=$(get_default_value "simulation")
        if [ -n "$default_value" ]; then
            simulation_name="$default_value"
            echo -e "${CYAN}Using default simulation: $simulation_name${RESET}"
            return
        fi
    fi

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
    echo "2. Cortical (ROI defined by brain atlas regions)"
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

# Function to collect field file information
collect_field_info() {
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
        if ! is_prompt_enabled "field_name"; then
            local default_value=$(get_default_value "field_name")
            if [ -n "$default_value" ]; then
                field_name="$default_value"
                echo -e "${CYAN}Using default field name: $field_name${RESET}"
                return
            fi
        fi

        echo -e "${GREEN}Enter the field name within the mesh file (e.g., normE, TI_max):${RESET}"
        read -p " " field_name
        
        while [[ -z "$field_name" ]]; do
            echo -e "${RED}Field name cannot be empty. Please enter a valid field name.${RESET}"
            read -p " " field_name
        done
        
        echo -e "${CYAN}Field name: $field_name${RESET}"
    fi
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
                atlas_path=${atlas_paths[$((atlas_num-1))]}  # Use the stored full path
                valid_atlas=true
            else
                reprompt
            fi
        done
        
        echo -e "${CYAN}Selected atlas file: $atlas_basename${RESET}"
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
                    prompt_region_selection "$subject_id" "$space_type" "$atlas_name" "$atlas_path"
                    
                    while [[ -z "$region_name" ]]; do
                        echo -e "${RED}Region name cannot be empty. Please enter a valid region name.${RESET}"
                        prompt_region_selection "$subject_id" "$space_type" "$atlas_name" "$atlas_path"
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
                prompt_region_selection "$subject_id" "$space_type" "$atlas_name" "$atlas_path"
                
                while [[ -z "$region_name" ]]; do
                    echo -e "${RED}Region name cannot be empty. Please enter a valid region name.${RESET}"
                    prompt_region_selection "$subject_id" "$space_type" "$atlas_name" "$atlas_path"
                done
                
                echo -e "${CYAN}Target region: $region_name${RESET}"
            else
                reprompt
            fi
        done
    fi
}

# Function to collect visualization preference
collect_visualization_pref() {
    if ! is_prompt_enabled "visualize"; then
        local default_vis=$(get_default_value "visualize")
        if [ -n "$default_vis" ]; then
            visualize="$default_vis"
            echo -e "${CYAN}Using default visualization setting: $visualize${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Do you want to generate visualizations? (y/n)${RESET}"
    read -p " " vis_choice
    if [[ "$vis_choice" == "y" || "$vis_choice" == "Y" ]]; then
        visualize="true"
        echo -e "${CYAN}Visualizations will be generated.${RESET}"
    else
        visualize="false"
        echo -e "${CYAN}No visualizations will be generated.${RESET}"
    fi
}

# =========================================
# Output Directory Setup Functions
# =========================================

# Function to setup output directory
setup_output_directory() {
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

    # Create output directory
    mkdir -p "$output_dir"
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

# Function to list atlas files for a subject (voxel mode)
list_atlas_files() {
    local subject_id=$1
    atlas_files=()
    atlas_paths=()  # Array to store full paths
    
    # Check SimNIBS segmentation directory
    atlas_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id/segmentation"
    if [ -d "$atlas_dir" ]; then
        while IFS= read -r -d '' file; do
            if [[ "$file" == *.nii.gz || "$file" == *.mgz ]]; then
                atlas_files+=("$(basename "$file")")
                atlas_paths+=("$file")  # Store full path
            fi
        done < <(find "$atlas_dir" -name "*.nii.gz" -o -name "*.mgz" -print0)
    fi
    
    # Check FreeSurfer mri directory
    freesurfer_dir="$project_dir/derivatives/freesurfer/sub-$subject_id/mri"
    echo -e "${BOLD_CYAN}FreeSurfer Directory: $freesurfer_dir${RESET}"
    if [ -d "$freesurfer_dir" ]; then
        while IFS= read -r -d '' file; do
            if [[ "$file" == *.mgz ]]; then
                atlas_files+=("$(basename "$file")")
                atlas_paths+=("$file")  # Store full path
            fi
        done < <(find "$freesurfer_dir" -name "*.mgz" -print0)
    fi
    
    if [ ${#atlas_files[@]} -eq 0 ]; then
        return 1
    fi
    
    echo -e "${BOLD_CYAN}Available Atlas Files:${RESET}"
    echo "-------------------"
    for i in "${!atlas_files[@]}"; do
        printf "%3d. %s\n" $((i+1)) "${atlas_files[i]}"
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

# Function to get region information from atlas file
get_region_info() {
    local atlas_path=$1
    local subject_id=$2
    local space_type=$3
    local atlas_name=$4
    local display_regions=${5:-false}  # Optional parameter to control display
    
    if [ "$space_type" == "mesh" ]; then
        # For mesh analysis, use simnibs_python to get regions
        echo -e "${CYAN}Loading $atlas_name atlas...${RESET}"
        regions=$(simnibs_python -c "
import simnibs
import sys

try:
    atlas = simnibs.subject_atlas('$atlas_name', '$m2m_dir')
    regions = sorted(atlas.keys())
    
    # Create a mapping of region names to IDs
    region_map = {}
    for i, region in enumerate(regions, 1):
        region_map[region] = i
    
    # Print regions with their IDs
    for region in regions:
        print(f'{region_map[region]}\t{region}')
except Exception as e:
    print(f'Error: {str(e)}', file=sys.stderr)
    sys.exit(1)
")
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error loading atlas regions.${RESET}"
            return 1
        fi
        
        if [ "$display_regions" = true ]; then
            echo -e "${BOLD_CYAN}Available Regions:${RESET}"
            echo -e "${YELLOW}You can use either the Region ID or the Region Name in your selection${RESET}"
            echo "-------------------"
            # Display regions in two columns with IDs in brackets
            echo "$regions" | awk -F'\t' '{printf "%-6s  %s\n", "[" $1 "]", $2}' | pr -2 -t -w 120
            echo
        fi
        return 0
    else
        # For voxel analysis, use FreeSurfer's mri_segstats
        local m2m_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id/segmentation"
        local freesurfer_dir="$project_dir/derivatives/freesurfer/sub-$subject_id/mri"
        local atlas_basename=$(basename "$atlas_path")
        local atlas_name="${atlas_basename%.*}"
        if [[ "$atlas_name" == *.nii ]]; then  # Handle .nii.gz case
            atlas_name="${atlas_name%.*}"
        fi
        
        # First check if the atlas file exists in either directory
        local atlas_found=false
        if [ -f "$m2m_dir/$atlas_basename" ]; then
            atlas_path="$m2m_dir/$atlas_basename"
            atlas_found=true
        elif [ -f "$freesurfer_dir/$atlas_basename" ]; then
            atlas_path="$freesurfer_dir/$atlas_basename"
            atlas_found=true
        fi
        
        if [ "$atlas_found" = false ]; then
            echo -e "${RED}Error: Atlas file not found in either m2m or FreeSurfer directories${RESET}"
            return 1
        fi
        
        # Define the labels file paths
        local m2m_labels_file="$m2m_dir/${atlas_name}_labels.txt"
        local freesurfer_labels_file="$freesurfer_dir/${atlas_name}_labels.txt"
        
        # Check if labels file exists in m2m directory first
        if [ -f "$m2m_labels_file" ]; then
            if [ "$display_regions" = true ]; then
                echo -e "${BOLD_CYAN}Available Regions:${RESET}"
                echo -e "${YELLOW}You can use either the Region ID or the Region Name in your selection${RESET}"
                echo "-------------------"
                # Display regions in two columns with IDs in brackets
                awk '
                    !/^#/ && NF >= 5 {
                        id = $2
                        name = $5
                        for(i=6; i<=NF; i++) name = name " " $i
                        gsub(/^[ \t]+|[ \t]+$/, "", name)
                        if (length(name) > 0) {
                            printf "%-6s  %s\n", "[" id "]", name
                        }
                    }
                ' "$m2m_labels_file" | sort -k2 | pr -2 -t -w 120
                echo
            fi
            return 0
        fi
        
        # If not in m2m, check FreeSurfer directory
        if [ -f "$freesurfer_labels_file" ]; then
            echo -e "${CYAN}Using existing labels file from FreeSurfer directory${RESET}"
            # Copy the file to m2m directory for future use
            mkdir -p "$m2m_dir"
            cp "$freesurfer_labels_file" "$m2m_labels_file"
            chmod 666 "$m2m_labels_file"
            if [ "$display_regions" = true ]; then
                echo -e "${BOLD_CYAN}Available Regions:${RESET}"
                echo -e "${YELLOW}You can use either the Region ID or the Region Name in your selection${RESET}"
                echo "-------------------"
                # Display regions in two columns with IDs in brackets
                awk '
                    !/^#/ && NF >= 5 {
                        id = $2
                        name = $5
                        for(i=6; i<=NF; i++) name = name " " $i
                        gsub(/^[ \t]+|[ \t]+$/, "", name)
                        if (length(name) > 0) {
                            printf "%-6s  %s\n", "[" id "]", name
                        }
                    }
                ' "$m2m_labels_file" | sort -k2 | pr -2 -t -w 120
                echo
            fi
            return 0
        fi
        
        # If no pre-generated file exists, create one using mri_segstats
        echo -e "${CYAN}Generating region information using mri_segstats...${RESET}"
        local temp_output=$(mktemp)
        mri_segstats --in "$atlas_path" --sum "$temp_output" 2>/dev/null
        
        if [ -f "$temp_output" ]; then
            # Create labels file in m2m directory with FreeSurfer format
            mkdir -p "$m2m_dir"
            {
                echo "# Title Segmentation Statistics"
                echo "#"
                echo "# generating_program mri_segstats"
                echo "# cmdline mri_segstats --in $atlas_path --sum $m2m_labels_file"
                echo "#"
                echo "# TableCol  1 ColHeader Index"
                echo "# TableCol  1 FieldName Index"
                echo "# TableCol  1 Units     NA"
                echo "# TableCol  2 ColHeader SegId"
                echo "# TableCol  2 FieldName Segmentation Id"
                echo "# TableCol  2 Units     NA"
                echo "# TableCol  3 ColHeader NVoxels"
                echo "# TableCol  3 FieldName Number of Voxels"
                echo "# TableCol  3 Units     unitless"
                echo "# TableCol  4 ColHeader Volume_mm3"
                echo "# TableCol  4 FieldName Volume"
                echo "# TableCol  4 Units     mm^3"
                echo "# TableCol  5 ColHeader StructName"
                echo "# TableCol  5 FieldName Structure Name"
                echo "# TableCol  5 Units     NA"
                echo "# ColHeaders  Index SegId NVoxels Volume_mm3 StructName"
                echo ""
                # Process the mri_segstats output
                while IFS= read -r line; do
                    if [[ $line =~ ^[0-9]+ ]]; then
                        # Parse the line into components
                        index=$(echo "$line" | awk '{print $1}')
                        segid=$(echo "$line" | awk '{print $2}')
                        nvoxels=$(echo "$line" | awk '{print $3}')
                        volume=$(echo "$line" | awk '{print $4}')
                        name=$(echo "$line" | awk '{$1=$2=$3=$4=""; print $0}' | sed 's/^[[:space:]]*//')
                        # Format the line to match FreeSurfer format
                        printf "%3d %4d %8d %10.1f  %s\n" "$index" "$segid" "$nvoxels" "$volume" "$name"
                    fi
                done < "$temp_output"
            } > "$m2m_labels_file"
            
            # Set permissions to ensure it's readable/writable
            chmod 666 "$m2m_labels_file"
            
            if [ "$display_regions" = true ]; then
                echo -e "${BOLD_CYAN}Available Regions:${RESET}"
                echo -e "${YELLOW}You can use either the Region ID or the Region Name in your selection${RESET}"
                echo "-------------------"
                # Display regions in two columns with IDs in brackets
                awk '
                    !/^#/ && NF >= 5 {
                        id = $2
                        name = $5
                        for(i=6; i<=NF; i++) name = name " " $i
                        gsub(/^[ \t]+|[ \t]+$/, "", name)
                        if (length(name) > 0) {
                            printf "%-6s  %s\n", "[" id "]", name
                        }
                    }
                ' "$m2m_labels_file" | sort -k2 | pr -2 -t -w 120
                echo
            fi
            rm "$temp_output"
            return 0
        else
            echo -e "${YELLOW}Could not extract region information from atlas file.${RESET}"
            rm "$temp_output"
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
    
    while true; do
        echo -e "${GREEN}Do you want to:${RESET}"
        echo "1. View available regions"
        echo "2. Enter region identifier (ID or name)"
        echo "3. Cancel"
        read -p "Enter your choice (1-3): " choice

        case $choice in
            1)
                get_region_info "$atlas_path" "$subject_id" "$space_type" "$atlas_name" true
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
    regions = sorted(atlas.keys())
    region = '$region_input'
    
    # Check if input is numeric
    try:
        region_id = int(region)
        # Convert ID to name if possible
        if 1 <= region_id <= len(regions):
            print(regions[region_id - 1])
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
    echo -e "Space Type: ${CYAN}$space_type${RESET}"
    echo -e "Analysis Type: ${CYAN}$analysis_type${RESET}"
    echo -e "Field File: ${CYAN}$field_basename${RESET}"
    
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
            echo -e "Atlas File: ${CYAN}$atlas_basename${RESET}"
        fi
        echo -e "Analysis Scope: ${CYAN}$([ "$whole_head" == "true" ] && echo "Whole Head" || echo "Region: $region_name")${RESET}"
    fi
    
    # Output Settings
    echo -e "\n${BOLD_CYAN}Output Settings:${RESET}"
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

# Function to run the analysis
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
    
    # Set environment variables
    export PROJECT_DIR="$project_dir"
    export SUBJECT_ID="$subject_id"
    
    # Print the command being executed
    echo -e "${CYAN}Executing command:${RESET}"
    echo -e "${BOLD_CYAN}${cmd[*]}${RESET}"
    echo
    
    # Run the analysis
    echo -e "${CYAN}Running analysis...${RESET}"
    if "${cmd[@]}"; then
        echo -e "${GREEN}Analysis completed successfully.${RESET}"
    else
        echo -e "${RED}Analysis failed.${RESET}"
        exit 1
    fi
}

# =========================================
# Main Execution Flow
# =========================================

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
        setup_output_directory
    fi
    
    # Set visualization flag
    visualize="${VISUALIZE:-true}"
    
    # Run the analysis without prompting
    run_analysis
    exit 0
fi

# Main script execution
show_welcome_message

# Collect all necessary inputs
collect_subject_info
collect_simulation_info
collect_space_info
collect_analysis_type
collect_field_info

# Collect analysis-specific parameters
if [ "$analysis_type" == "spherical" ]; then
    collect_spherical_params
else
    collect_cortical_params
fi

# Collect visualization preference
collect_visualization_pref

# Setup output directory
setup_output_directory

# Show confirmation dialog
show_confirmation_dialog

# Run the analysis
run_analysis
