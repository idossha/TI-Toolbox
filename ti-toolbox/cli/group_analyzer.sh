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
ti_csc_dir="$project_dir/code/ti-toolbox"
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

# Ensure ti-toolbox directory exists and set permissions
if [ ! -d "$ti_csc_dir" ]; then
    mkdir -p "$ti_csc_dir"
    chmod 777 "$ti_csc_dir"
    echo -e "${GREEN}Created ti-toolbox directory at $ti_csc_dir with permissions 777.${RESET}"
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
    "coordinates": {
        "prompt": "enable",
        "default": [0, 0, 0]
    },
    "radius": {
        "prompt": "enable",
        "default": 10
    },
    "coordinate_space": {
        "prompt": "enable",
        "default": "MNI",
        "options": ["MNI", "subject"]
    },
    "atlas": {
        "prompt": "enable",
        "default": "DK40",
        "options": ["DK40", "HCP_MMP1", "a2009s"]
    },
    "output_dir": {
        "prompt": "disable",
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
    echo -e "${BOLD_CYAN}║      TI-Toolbox Group Analyzer Tool    ║${RESET}"
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
            selected_subjects=($(echo "$default_value" | jq -r '.[]'))
            echo -e "${CYAN}Using default subjects: ${selected_subjects[*]}${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Choose subjects for group analysis:${RESET}"
    list_subjects

    selected_subjects=()
    valid_selection=false
    until $valid_selection; do
        echo -e "${YELLOW}Enter subject numbers separated by spaces (e.g., 1 3 5):${RESET}"
        echo -e "${YELLOW}Or enter 'all' to select all subjects:${RESET}"
        read -p "Enter your selection: " subject_input

        if [ "$subject_input" == "all" ]; then
            selected_subjects=("${subjects[@]}")
        else
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
        fi
        if [ ${#selected_subjects[@]} -le 1 ]; then
            echo -e "${RED}You must select more than one subject for group analysis.${RESET}"
            selected_subjects=()
            continue
        fi
        valid_selection=true
        echo -e "${CYAN}Selected ${#selected_subjects[@]} subjects: ${selected_subjects[*]}${RESET}"
    done
}

# Function to collect simulation (montage) information and ensure all subjects have it
collect_simulation_info() {
    echo -e "${GREEN}Checking for common simulations (montages) across selected subjects...${RESET}\n"
    declare -A subject_sim_lists
    common_simulations=()

    # Gather simulation lists for each subject
    for subject_id in "${selected_subjects[@]}"; do
        simulations=()
        mesh_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/*/TI/mesh"
        for sim_path in $mesh_dir; do
            if [ -d "$sim_path" ]; then
                sim_name=$(basename "$(dirname "$(dirname "$sim_path")")")
                simulations+=("$sim_name")
            fi
        done
        voxel_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/*/TI/niftis"
        for sim_path in $voxel_dir; do
            if [ -d "$sim_path" ]; then
                sim_name=$(basename "$(dirname "$(dirname "$sim_path")")")
                if [[ ! " ${simulations[@]} " =~ " ${sim_name} " ]]; then
                    simulations+=("$sim_name")
                fi
            fi
        done
        subject_sim_lists[$subject_id]="${simulations[*]}"
    done

    # Find intersection of all simulation lists
    for sim in ${subject_sim_lists[${selected_subjects[0]}]}; do
        is_common=true
        for subject_id in "${selected_subjects[@]}"; do
            if [[ ! " ${subject_sim_lists[$subject_id]} " =~ " $sim " ]]; then
                is_common=false
                break
            fi
        done
        if $is_common; then
            common_simulations+=("$sim")
        fi
    done

    if [ ${#common_simulations[@]} -eq 0 ]; then
        echo -e "${RED}No common simulations (montages) found across all selected subjects. Please select a different set of subjects.${RESET}"
        exit 1
    fi

    echo -e "${BOLD_CYAN}Common Simulations (Montages) Across All Subjects:${RESET}"
    for i in "${!common_simulations[@]}"; do
        printf "%3d. %s\n" $((i+1)) "${common_simulations[i]}"
    done
    echo

    valid_simulation=false
    until $valid_simulation; do
        read -p "Enter the number of the simulation to use for all subjects: " sim_num
        if [[ "$sim_num" =~ ^[0-9]+$ ]] && [ "$sim_num" -ge 1 ] && [ "$sim_num" -le "${#common_simulations[@]}" ]; then
            selected_simulation="${common_simulations[$((sim_num-1))]}"
            valid_simulation=true
        else
            reprompt
        fi
    done
    echo -e "${CYAN}Selected simulation for all subjects: $selected_simulation${RESET}"

    # Assign the selected simulation to all subjects
    for subject_id in "${selected_subjects[@]}"; do
        subject_simulations["$subject_id"]="$selected_simulation"
    done

    # Auto-select field files for each subject
    for subject_id in "${selected_subjects[@]}"; do
        if [ "$space_type" == "mesh" ]; then
            field_path="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/$selected_simulation/TI/mesh/${selected_simulation}_TI.msh"
        else
            field_path="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/$selected_simulation/TI/niftis/grey_${selected_simulation}_TI_subject_TI_max.nii.gz"
        fi
        if [ ! -f "$field_path" ]; then
            echo -e "${RED}Field file not found for subject $subject_id: $field_path${RESET}"
            exit 1
        fi
        subject_field_paths["$subject_id"]="$field_path"
        echo -e "${CYAN}Auto-selected field file for $subject_id: $(basename "$field_path")${RESET}"
    done
    echo -e "${GREEN}✓ All field files auto-selected for ${#selected_subjects[@]} subjects${RESET}"
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
    # Field name is now hardcoded to 'TI_max'
    field_name="TI_max"
    echo -e "${CYAN}Field name is hardcoded to: $field_name${RESET}"
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

    # Collect coordinate space
    if ! is_prompt_enabled "coordinate_space"; then
        local default_coord_space=$(get_default_value "coordinate_space")
        if [ -n "$default_coord_space" ]; then
            coordinate_space="$default_coord_space"
            echo -e "${CYAN}Using default coordinate space: $coordinate_space${RESET}"
        else
            coordinate_space="MNI"
            echo -e "${CYAN}Using default coordinate space: MNI${RESET}"
        fi
    else
        echo -e "${GREEN}Select coordinate space for the entered coordinates:${RESET}"
        echo "1. MNI space"
        echo "2. Subject space"
        valid_choice=false
        until $valid_choice; do
            read -p "Enter choice (1-2): " coord_space_choice
            case $coord_space_choice in
                1)
                    coordinate_space="MNI"
                    valid_choice=true
                    ;;
                2)
                    coordinate_space="subject"
                    valid_choice=true
                    ;;
                *)
                    echo -e "${RED}Invalid choice. Please enter 1 or 2.${RESET}"
                    ;;
            esac
        done
    fi

    echo -e "${CYAN}Coordinate space: $coordinate_space${RESET}"

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

        # Function to get all available atlases for a subject
        get_all_subject_atlases() {
            local subject_id=$1
            local freesurfer_dir="$project_dir/derivatives/freesurfer/sub-$subject_id/$subject_id/mri"
            local found_atlases=()
            for atlas in "aparc.DKTatlas+aseg.mgz" "aparc.a2009s+aseg.mgz"; do
                if [ -f "$freesurfer_dir/$atlas" ]; then
                    found_atlases+=("$atlas")
                fi
            done
            echo "${found_atlases[@]}"
        }

        # Gather available atlases for each subject
        declare -A subject_atlas_lists
        for subject_id in "${selected_subjects[@]}"; do
            subject_atlas_lists[$subject_id]="$(get_all_subject_atlases "$subject_id")"
        done

        # Find intersection of atlas lists
        common_atlases=()
        for atlas in ${subject_atlas_lists[${selected_subjects[0]}]}; do
            is_common=true
            for subject_id in "${selected_subjects[@]}"; do
                if [[ ! " ${subject_atlas_lists[$subject_id]} " =~ " $atlas " ]]; then
                    is_common=false
                    break
                fi
            done
            if $is_common; then
                common_atlases+=("$atlas")
            fi
        done

        if [ ${#common_atlases[@]} -eq 0 ]; then
            echo -e "${RED}Error: No common atlas files found for all selected subjects.${RESET}"
            echo -e "${RED}Please ensure FreeSurfer preprocessing has been completed for all subjects.${RESET}"
            exit 1
        fi

        # Prompt user to select atlas if more than one is available
        if [ ${#common_atlases[@]} -gt 1 ]; then
            echo -e "${BOLD_CYAN}Common Atlases Available for All Subjects:${RESET}"
            for i in "${!common_atlases[@]}"; do
                printf "%3d. %s\n" $((i+1)) "${common_atlases[i]}"
            done
            valid_atlas=false
            until $valid_atlas; do
                read -p "Enter the number of the atlas to use for all subjects: " atlas_num
                if [[ "$atlas_num" =~ ^[0-9]+$ ]] && [ "$atlas_num" -ge 1 ] && [ "$atlas_num" -le "${#common_atlases[@]}" ]; then
                    selected_atlas="${common_atlases[$((atlas_num-1))]}"
                    valid_atlas=true
                else
                    reprompt
                fi
            done
        else
            selected_atlas="${common_atlases[0]}"
            echo -e "${CYAN}Using common atlas: $selected_atlas${RESET}"
        fi

        # Overwrite get_subject_atlas_path to use selected_atlas
        get_subject_atlas_path() {
            local subject_id=$1
            local freesurfer_dir="$project_dir/derivatives/freesurfer/sub-$subject_id/$subject_id/mri"
            if [ -f "$freesurfer_dir/$selected_atlas" ]; then
                echo "$freesurfer_dir/$selected_atlas"
            else
                return 1
            fi
        }
        # --- END NEW LOGIC FOR COMMON ATLAS SELECTION ---
        # Validate that all subjects have the selected atlas
        echo -e "${CYAN}Validating atlas files for all subjects...${RESET}"
        missing_atlas_subjects=()
        for subject_id in "${selected_subjects[@]}"; do
            if ! get_subject_atlas_path "$subject_id" >/dev/null; then
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
    # Always require a specific region (no prompt for whole head)
    while true; do
        echo -e "${GREEN}Region selection:${RESET}"
        echo "1. View available regions in the atlas"
        echo "2. Enter region name/identifier"
        echo "3. Cancel"
        read -p "Enter your choice (1-3): " region_choice
        case $region_choice in
            1)
                # Preview regions for the first subject (mesh or voxel)
                if [ "$space_type" == "mesh" ]; then
                    subject_id="${selected_subjects[0]}"
                    m2m_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id"
                    echo -e "${CYAN}Loading $atlas_name atlas for subject $subject_id...${RESET}"
                    regions=$(simnibs_python -c "import simnibs; atlas = simnibs.subject_atlas('$atlas_name', '$m2m_dir'); regions = sorted(atlas.keys()); [print(f'{i+1}. {r}') for i, r in enumerate(regions)]")
                    echo -e "${BOLD_CYAN}Available Regions:${RESET}"
                    echo "$regions"
                else
                    subject_id="${selected_subjects[0]}"
                    atlas_path=$(get_subject_atlas_path "$subject_id")
                    if [ -z "$atlas_path" ]; then
                        echo -e "${RED}No atlas file found for subject $subject_id${RESET}"
                        continue
                    fi
                    # Try to print region names from the labels file if available
                    labels_file="$(dirname "$atlas_path")/$(basename "$atlas_path" .mgz)_labels.txt"
                    if [ -f "$labels_file" ]; then
                        echo -e "${BOLD_CYAN}Available Regions:${RESET}"
                        awk '!/^#/ && NF >= 5 {id = $2; name = $5; for(i=6;i<=NF;i++) name = name " " $i; gsub(/^[ \t]+|[ \t]+$/, "", name); if(length(name)>0){printf "%-6s  %s\n", "[" id "]", name}}' "$labels_file" | sort -k2 | pr -2 -t -w 120
                    else
                        echo -e "${YELLOW}No region label file found for $atlas_path${RESET}"
                    fi
                fi
                ;;
            2)
                echo -e "${GREEN}Enter the region name or ID:${RESET}"
                read -p " " region_input
                if [[ -z "$region_input" ]]; then
                    echo -e "${RED}Region name cannot be empty. Please enter a valid region name.${RESET}"
                    continue
                fi
                # If input is a number, look up the region name
                if [[ "$region_input" =~ ^[0-9]+$ ]]; then
                    if [ "$space_type" == "mesh" ]; then
                        subject_id="${selected_subjects[0]}"
                        m2m_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id"
                        region_name=$(simnibs_python -c "import simnibs; atlas = simnibs.subject_atlas('$atlas_name', '$m2m_dir'); regions = sorted(atlas.keys()); idx = int('$region_input')-1; print(regions[idx]) if 0 <= idx < len(regions) else exit(1)")
                        if [ $? -ne 0 ] || [ -z "$region_name" ]; then
                            echo -e "${RED}Invalid region ID for $atlas_name. Please try again.${RESET}"
                            continue
                        fi
                    else
                        subject_id="${selected_subjects[0]}"
                        atlas_path=$(get_subject_atlas_path "$subject_id")
                        labels_file="$(dirname "$atlas_path")/$(basename "$atlas_path" .mgz)_labels.txt"
                        region_name=$(awk -v id="$region_input" '!/^#/ && NF >= 5 && $2 == id {name = $5; for(i=6;i<=NF;i++) name = name " " $i; gsub(/^[ \t]+|[ \t]+$/, "", name); print name; exit}' "$labels_file")
                        if [ -z "$region_name" ]; then
                            echo -e "${RED}Invalid region ID for atlas. Please try again.${RESET}"
                            continue
                        fi
                    fi
                else
                    # Validate region name exists
                    if [ "$space_type" == "mesh" ]; then
                        subject_id="${selected_subjects[0]}"
                        m2m_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id"
                        valid=$(simnibs_python -c "import simnibs; atlas = simnibs.subject_atlas('$atlas_name', '$m2m_dir'); print('1' if '$region_input' in atlas else '0')")
                        if [ "$valid" != "1" ]; then
                            echo -e "${RED}Invalid region name for $atlas_name. Please try again.${RESET}"
                            continue
                        fi
                        region_name="$region_input"
                    else
                        subject_id="${selected_subjects[0]}"
                        atlas_path=$(get_subject_atlas_path "$subject_id")
                        labels_file="$(dirname "$atlas_path")/$(basename "$atlas_path" .mgz)_labels.txt"
                        found=$(awk -v name="$region_input" 'BEGIN{IGNORECASE=1} !/^#/ && NF >= 5 {region = $5; for(i=6;i<=NF;i++) region = region " " $i; gsub(/^[ \t]+|[ \t]+$/, "", region); if (region == name) {print 1; exit}}' "$labels_file")
                        if [ "$found" != "1" ]; then
                            echo -e "${RED}Invalid region name for atlas. Please try again.${RESET}"
                            continue
                        fi
                        region_name="$region_input"
                    fi
                fi
                echo -e "${CYAN}Target region: $region_name${RESET}"
                break
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
    # Always run comparison analysis (no prompt, no --compare flag needed)
    compare_analyses="true"
    # Always use default output directory with timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    output_dir="$project_dir/code/ti-toolbox/group_analyses/group_${analysis_type}_${space_type}_${timestamp}"
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
        echo -e "Analysis Scope: ${CYAN}Region: $region_name${RESET}"
    fi
    
    # Output Settings
    echo -e "\n${BOLD_CYAN}Output Settings:${RESET}"
    echo -e "Output Directory: ${CYAN}$output_dir${RESET}"
    echo -e "Run Comparison: ${CYAN}Yes${RESET}"
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
    
    # Add analysis-specific parameters
    if [ "$analysis_type" == "spherical" ]; then
        cmd+=(--coordinates "${coordinates[@]}")
        cmd+=(--coordinate-space "$coordinate_space")
        cmd+=(--radius "$radius")
    else  # cortical
        if [ "$space_type" == "mesh" ]; then
            cmd+=(--atlas_name "$atlas_name")
        fi
        
        cmd+=(--region "$region_name")
    fi
    
    # Always enable visualizations
    cmd+=(--visualize)
    
    # Add quiet flag for summary mode (shows individual subject task steps)
    cmd+=(--quiet)
    
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
        echo -e "${GREEN}Comparison results saved to: $output_dir${RESET}"
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
