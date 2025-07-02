#!/bin/bash

###########################################
# Ido Haber / ihaber@wisc.edu
# March 19, 2024
# Optimized for TI-CSC analyzer
# This script orchestrates the flex-search pipeline for optimizing electrode positions
###########################################

set -e  # Exit immediately if a command exits with a non-zero status

umask 0000  # Set umask to 0000 to ensure all created files and directories have permissions 777

# Base directories
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
flex_search_dir="$script_dir/../flex-search"
project_dir="/mnt/$PROJECT_DIR_NAME"
utils_dir="$script_dir/../utils"
config_file="$project_dir/ti-csc/config/flex-search_config/flex_config.json"

# Export project directory for Python script
export PROJECT_DIR="$project_dir"

# Define color variables
BOLD='\033[1m'
UNDERLINE='\033[4m'
RESET='\033[0m'
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD_CYAN='\033[1;36m'
YELLOW='\033[0;33m'
BOLD_RED='\033[1;31m'
BOLD_GREEN='\033[1;32m'
BOLD_YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
BOLD_BLUE='\033[1;34m'
BG_BLUE='\033[44m'

# Function to read configuration
read_config() {
    local key=$1
    local subkey=$2
    if [ -f "$config_file" ]; then
        if [ -n "$subkey" ]; then
            jq -r ".$key.$subkey // empty" "$config_file" 2>/dev/null
        else
            jq -r ".$key // empty" "$config_file" 2>/dev/null
        fi
    fi
}

# Function to read nested configuration
read_nested_config() {
    local key=$1
    local subkey=$2
    local subsubkey=$3
    if [ -f "$config_file" ]; then
        if [ -n "$subsubkey" ]; then
            jq -r ".$key.$subkey.$subsubkey // empty" "$config_file" 2>/dev/null
        else
            jq -r ".$key.$subkey // empty" "$config_file" 2>/dev/null
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

# Function to list available subjects
list_subjects() {
    subjects=()
    for subject_path in "$project_dir"/derivatives/SimNIBS/sub-*/m2m_*; do
        if [ -d "$subject_path" ]; then
            subject_id=$(basename "$subject_path" | sed 's/m2m_//')
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

# Choose subjects function with configuration support
choose_subjects() {
    if ! is_prompt_enabled "subjects"; then
        local default_value=$(get_default_value "subjects")
        if [ -n "$default_value" ]; then
            subject_choices="$default_value"
            echo -e "${CYAN}Using default subject(s): $subject_choices${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Choose subjects by entering the corresponding numbers (comma-separated, e.g., 1,2):${RESET}"
    list_subjects
    while true; do
        read -p "Enter the numbers of the subjects to analyze: " subject_choices
        if [[ "$subject_choices" =~ ^[0-9,]+$ ]]; then
            IFS=',' read -r -a selected_indices <<< "$subject_choices"
            valid_input=true
            selected_subjects=()  # Array to store actual subject IDs
            for num in "${selected_indices[@]}"; do
                if [[ $num -le 0 || $num -gt ${#subjects[@]} ]]; then
                    echo -e "${RED}Invalid subject number: $num. Please try again.${RESET}"
                    valid_input=false
                    break
                fi
                # Store the actual subject ID
                selected_subjects+=("${subjects[$((num-1))]}")
            done
            if $valid_input; then
                break
            fi
        else
            echo -e "${RED}Invalid input. Please enter numbers separated by commas.${RESET}"
        fi
    done
}

# Function to get threshold values for focality optimization
get_thresholds() {
    if ! is_prompt_enabled "thresholds"; then
        local default_value=$(get_default_value "thresholds")
        if [ -n "$default_value" ]; then
            THRESHOLD_VALUES="$default_value"
            echo -e "${CYAN}Using default threshold values: $THRESHOLD_VALUES${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Enter threshold value(s) for the electric field (V/m):${RESET}"
    echo "You can enter:"
    echo "1. A single value: E-field should be lower than this in non-ROI and higher in ROI"
    echo "2. Two values (comma-separated): First for non-ROI max, second for ROI min"
    echo "Example: 0.2 or 0.2,0.5"
    
    while true; do
        read -p "Enter threshold value(s): " threshold_input
        
        # Check if input contains a comma (two thresholds)
        if [[ $threshold_input == *","* ]]; then
            IFS=',' read -r non_roi_threshold roi_threshold <<< "$threshold_input"
            # Validate both numbers
            if [[ "$non_roi_threshold" =~ ^[0-9]+\.?[0-9]*$ ]] && [[ "$roi_threshold" =~ ^[0-9]+\.?[0-9]*$ ]]; then
                export THRESHOLD_VALUES="$non_roi_threshold,$roi_threshold"
                echo -e "${GREEN}Set thresholds: non-ROI max = ${non_roi_threshold}V/m, ROI min = ${roi_threshold}V/m${RESET}"
                break
            fi
        else
            # Single threshold value
            if [[ "$threshold_input" =~ ^[0-9]+\.?[0-9]*$ ]]; then
                export THRESHOLD_VALUES="$threshold_input"
                echo -e "${GREEN}Set threshold: ${threshold_input}V/m for both ROI and non-ROI${RESET}"
                break
            fi
        fi
        echo -e "${RED}Invalid input. Please enter numeric values only (e.g., 0.2 or 0.2,0.5).${RESET}"
    done
}

# Choose optimization goal
choose_goal() {
    if ! is_prompt_enabled "goal"; then
        local default_value=$(get_default_value "goal")
        if [ -n "$default_value" ]; then
            goal="$default_value"
            echo -e "${CYAN}Using default goal: $goal${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Choose optimization goal:${RESET}"
    echo "1. mean (maximize field in target ROI)"
    echo "2. focality (maximize field in target ROI while minimizing field elsewhere)"
    echo "3. max (maximize peak field in target ROI)"
    while true; do
        read -p "Enter your choice (1, 2, or 3): " goal_choice
        case "$goal_choice" in
            1) goal="mean"; break ;;
            2) 
                goal="focality"
                get_thresholds  # Get threshold values for focality optimization
                break 
                ;;
            3) goal="max"; break ;;
            *) echo -e "${RED}Invalid choice. Please enter 1, 2, or 3.${RESET}" ;;
        esac
    done
}

# Choose post-processing method
choose_postproc() {
    if ! is_prompt_enabled "postproc"; then
        local default_value=$(get_default_value "postproc")
        if [ -n "$default_value" ]; then
            postproc="$default_value"
            echo -e "${CYAN}Using default post-processing method: $postproc${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Choose post-processing method:${RESET}"
    echo "1. max_TI (maximum TI field)"
    echo "2. dir_TI_normal (TI field normal to surface)"
    echo "3. dir_TI_tangential (TI field tangential to surface)"
    while true; do
        read -p "Enter your choice (1, 2, or 3): " postproc_choice
        case "$postproc_choice" in
            1) postproc="max_TI"; break ;;
            2) postproc="dir_TI_normal"; break ;;
            3) postproc="dir_TI_tangential"; break ;;
            *) echo -e "${RED}Invalid choice. Please enter 1, 2, or 3.${RESET}" ;;
        esac
    done
}

# Function to list available EEG nets for a subject
list_eeg_nets() {
    local subject_id=$1
    local eeg_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id/eeg_positions"
    
    if [ ! -d "$eeg_dir" ]; then
        echo -e "${RED}Error: EEG positions directory not found for subject $subject_id${RESET}"
        return 1
    fi

    echo -e "${BOLD_CYAN}Available EEG nets:${RESET}"
    echo "-------------------"
    
    # Initialize array for EEG nets
    eeg_nets=()
    index=1
    
    # List all CSV files and extract base names
    for net_file in "$eeg_dir"/*.csv; do
        if [ -f "$net_file" ]; then
            net_name=$(basename "$net_file" .csv)
            eeg_nets+=("$net_name")
            printf "%3d. %s\n" "$index" "$net_name"
            ((index++))
        fi
    done
    
    if [ ${#eeg_nets[@]} -eq 0 ]; then
        echo -e "${YELLOW}No EEG net templates found in $eeg_dir${RESET}"
        return 1
    fi
    
    echo
    return 0
}

# Choose EEG net template
choose_eeg_net() {
    if ! is_prompt_enabled "eeg_net"; then
        local default_value=$(get_default_value "eeg_net")
        if [ -n "$default_value" ]; then
            eeg_net="$default_value"
            echo -e "${CYAN}Using default EEG net template: $eeg_net${RESET}"
            return
        fi
    fi

    # Get the first subject to list available EEG nets
    first_subject="${selected_subjects[0]}"
    
    if ! list_eeg_nets "$first_subject"; then
        echo -e "${RED}Failed to list EEG nets. Using default EGI_256.${RESET}"
        eeg_net="EGI_256"
        return
    fi

    while true; do
        read -p "Enter the number of the EEG net to use: " net_choice
        if [[ "$net_choice" =~ ^[0-9]+$ ]] && [ "$net_choice" -ge 1 ] && [ "$net_choice" -le "${#eeg_nets[@]}" ]; then
            eeg_net="${eeg_nets[$((net_choice-1))]}"
            # If the selected net is EGI_template, convert it to EGI_256
            if [ "$eeg_net" = "EGI_template" ]; then
                eeg_net="EGI_256"
                echo -e "${YELLOW}Converting EGI_template to EGI_256${RESET}"
            fi
            break
        else
            echo -e "${RED}Invalid choice. Please enter a number between 1 and ${#eeg_nets[@]}.${RESET}"
        fi
    done
}

# Choose electrode parameters
choose_electrode_params() {
    if ! is_prompt_enabled "electrode_params"; then
        local default_radius=$(get_default_value "electrode_radius")
        local default_current=$(get_default_value "electrode_current")
        if [ -n "$default_radius" ] && [ -n "$default_current" ]; then
            radius="$default_radius"
            current="$default_current"
            echo -e "${CYAN}Using default electrode parameters: radius=${radius}mm, current=${current}mA${RESET}"
            return
        fi
    fi

    while true; do
        read -p "Enter electrode radius in mm: " radius
        if [[ "$radius" =~ ^[0-9]+\.?[0-9]*$ ]]; then
            break
        else
            echo -e "${RED}Invalid radius. Please enter a positive number.${RESET}"
        fi
    done

    while true; do
        read -p "Enter electrode current in mA: " current
        if [[ "$current" =~ ^[0-9]+\.?[0-9]*$ ]]; then
            break
        else
            echo -e "${RED}Invalid current. Please enter a positive number.${RESET}"
        fi
    done
}

# Choose optimization parameters (max iterations, population size, CPUs)
choose_optimization_params() {
    if ! is_prompt_enabled "optimization_params"; then
        local default_max_iter=$(get_default_value "max_iterations")
        local default_pop_size=$(get_default_value "population_size")
        local default_cpus=$(get_default_value "cpus")
        if [ -n "$default_max_iter" ] && [ -n "$default_pop_size" ] && [ -n "$default_cpus" ]; then
            max_iterations="$default_max_iter"
            population_size="$default_pop_size"
            cpus="$default_cpus"
            echo -e "${CYAN}Using default optimization parameters: max_iter=${max_iterations}, pop_size=${population_size}, cpus=${cpus}${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Configure optimization parameters:${RESET}"
    
    # Max iterations
    while true; do
        read -p "Enter maximum optimization iterations [default: 500]: " max_iterations
        if [ -z "$max_iterations" ]; then
            max_iterations=500
            break
        elif [[ "$max_iterations" =~ ^[0-9]+$ ]] && [ "$max_iterations" -ge 50 ] && [ "$max_iterations" -le 2000 ]; then
            break
        else
            echo -e "${RED}Invalid value. Please enter a number between 50 and 2000.${RESET}"
        fi
    done

    # Population size
    while true; do
        read -p "Enter population size [default: 13]: " population_size
        if [ -z "$population_size" ]; then
            population_size=13
            break
        elif [[ "$population_size" =~ ^[0-9]+$ ]] && [ "$population_size" -ge 4 ] && [ "$population_size" -le 100 ]; then
            break
        else
            echo -e "${RED}Invalid value. Please enter a number between 4 and 100.${RESET}"
        fi
    done

    # Number of CPUs
    local max_cpus=$(nproc 2>/dev/null || echo "16")
    while true; do
        read -p "Enter number of CPU cores to use [default: 1, max: $max_cpus]: " cpus
        if [ -z "$cpus" ]; then
            cpus=1
            break
        elif [[ "$cpus" =~ ^[0-9]+$ ]] && [ "$cpus" -ge 1 ] && [ "$cpus" -le "$max_cpus" ]; then
            break
        else
            echo -e "${RED}Invalid value. Please enter a number between 1 and $max_cpus.${RESET}"
        fi
    done

    echo -e "${GREEN}Optimization parameters set: max_iter=${max_iterations}, pop_size=${population_size}, cpus=${cpus}${RESET}"
}

# Choose mapping options
choose_mapping_options() {
    if ! is_prompt_enabled "mapping_options"; then
        local default_enable_mapping=$(get_default_value "enable_mapping")
        local default_run_mapped_sim=$(get_default_value "run_mapped_simulation")
        if [ -n "$default_enable_mapping" ]; then
            enable_mapping="$default_enable_mapping"
            run_mapped_simulation="$default_run_mapped_sim"
            echo -e "${CYAN}Using default mapping options: enable_mapping=${enable_mapping}, run_mapped_simulation=${run_mapped_simulation}${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Configure electrode mapping options:${RESET}"
    echo -e "${YELLOW}⚠️  Electrode mapping finds the nearest EEG net electrodes to the optimized positions.${RESET}"
    echo -e "${YELLOW}   This feature may increase computation time and memory usage.${RESET}"
    echo

    while true; do
        read -p "Enable electrode mapping to EEG net positions? (y/n) [default: n]: " enable_mapping_input
        if [ -z "$enable_mapping_input" ]; then
            enable_mapping="false"
            break
        elif [[ "$enable_mapping_input" =~ ^[yY]$ ]]; then
            enable_mapping="true"
            break
        elif [[ "$enable_mapping_input" =~ ^[nN]$ ]]; then
            enable_mapping="false"
            break
        else
            echo -e "${RED}Invalid choice. Please enter 'y' for yes or 'n' for no.${RESET}"
        fi
    done

    if [ "$enable_mapping" = "true" ]; then
        while true; do
            read -p "Run additional simulation with mapped electrodes? (y/n) [default: n]: " run_mapped_sim_input
            if [ -z "$run_mapped_sim_input" ]; then
                run_mapped_simulation="false"
                break
            elif [[ "$run_mapped_sim_input" =~ ^[yY]$ ]]; then
                run_mapped_simulation="true"
                break
            elif [[ "$run_mapped_sim_input" =~ ^[nN]$ ]]; then
                run_mapped_simulation="false"
                break
            else
                echo -e "${RED}Invalid choice. Please enter 'y' for yes or 'n' for no.${RESET}"
            fi
        done
    else
        run_mapped_simulation="false"
    fi

    echo -e "${GREEN}Mapping options set: enable_mapping=${enable_mapping}, run_mapped_simulation=${run_mapped_simulation}${RESET}"
}

# Choose quiet mode option
choose_quiet_mode() {
    if ! is_prompt_enabled "quiet_mode"; then
        local default_quiet=$(get_default_value "quiet_mode")
        if [ -n "$default_quiet" ]; then
            quiet_mode="$default_quiet"
            echo -e "${CYAN}Using default quiet mode: ${quiet_mode}${RESET}"
            return
        fi
    fi

    while true; do
        read -p "Hide optimization steps output? (y/n) [default: y]: " quiet_input
        if [ -z "$quiet_input" ]; then
            quiet_mode="true"
            break
        elif [[ "$quiet_input" =~ ^[yY]$ ]]; then
            quiet_mode="true"
            break
        elif [[ "$quiet_input" =~ ^[nN]$ ]]; then
            quiet_mode="false"
            break
        else
            echo -e "${RED}Invalid choice. Please enter 'y' for yes or 'n' for no.${RESET}"
        fi
    done
}

# Function to choose ROI method
choose_roi_method() {
    echo "Choose ROI definition method:"
    echo "1. spherical (define ROI as a sphere)"
    echo "2. atlas (use atlas-based ROI)"
    while true; do
        read -p "Enter your choice (1 or 2): " roi_choice
        case "$roi_choice" in
            1) 
                export ROI_METHOD="spherical"
                setup_spherical_roi
                break 
                ;;
            2) 
                export ROI_METHOD="atlas"
                setup_atlas_roi "$1"
                break 
                ;;
            *) 
                echo "Invalid choice. Please enter 1 or 2."
                ;;
        esac
    done
}

# Add this helper function for numeric validation
validate_numeric_input() {
    local value="$1"
    local name="$2"
    local allow_negative="$3"

    if [ "$allow_negative" = "true" ]; then
        if ! [[ "$value" =~ ^-?[0-9]+\.?[0-9]*$ ]]; then
            print_error "$name must be a number"
            return 1
        fi
    else
        if ! [[ "$value" =~ ^[0-9]+\.?[0-9]*$ ]]; then
            print_error "$name must be a positive number"
            return 1
        fi
    fi
    return 0
}

# Function to get validated numeric input
get_numeric_input() {
    local prompt="$1"
    local var_name="$2"
    local allow_negative="$3"
    local value=""

    while true; do
        echo -e "${CYAN}$prompt${RESET}"
        read -p "> " value
        
        if validate_numeric_input "$value" "$var_name" "$allow_negative"; then
            echo "$value"
            return 0
        fi
    done
}

# Add this helper function for coordinate validation
validate_coordinates() {
    local coords="$1"
    local name="$2"
    
    # Check if input matches the pattern "x,y,z" where x,y,z are numbers (can be negative)
    if ! [[ "$coords" =~ ^-?[0-9]+\.?[0-9]*,-?[0-9]+\.?[0-9]*,-?[0-9]+\.?[0-9]*$ ]]; then
        print_error "$name must be three comma-separated numbers (x,y,z)"
        return 1
    fi
    return 0
}

# Function to get validated coordinate input
get_coordinate_input() {
    local prompt="$1"
    local var_name="$2"
    local coords=""

    while true; do
        echo -e "${CYAN}$prompt (format: x,y,z)${RESET}"
        read -p "> " coords
        
        if validate_coordinates "$coords" "$var_name"; then
            echo "$coords"
            return 0
        fi
    done
}

# Add this helper function for coordinate and radius validation
validate_coordinates_and_radius() {
    local input="$1"
    local name="$2"
    
    # Check if input matches the pattern "x,y,z,r" where x,y,z can be negative, r must be positive
    if ! [[ "$input" =~ ^-?[0-9]+\.?[0-9]*,-?[0-9]+\.?[0-9]*,-?[0-9]*\.?[0-9]*,[0-9]+\.?[0-9]*$ ]]; then
        print_error "$name must be four comma-separated numbers (x,y,z,radius) where radius is positive"
        return 1
    fi
    return 0
}

# Function to get validated coordinate and radius input
get_coordinate_and_radius_input() {
    local prompt="$1"
    local var_name="$2"
    while true; do
        echo -e "${BOLD}$prompt${RESET}"
        echo -e "${CYAN}Enter as comma-separated values: x,y,z,radius${RESET}"
        echo -e "${CYAN}Example: 10,-5,20,5 for coordinates (10,-5,20) with 5mm radius${RESET}"
        read -p "> " COORD_RADIUS_INPUT
        if validate_coordinates_and_radius "$COORD_RADIUS_INPUT" "$var_name"; then
            return 0
        fi
    done
}

# Modify the setup_spherical_roi function
setup_spherical_roi() {
    print_section_header "Spherical ROI Configuration"
    echo
    get_coordinate_and_radius_input "Define ROI sphere location and size (in mm):" "Input"
    IFS=',' read -r ROI_X ROI_Y ROI_Z ROI_RADIUS <<< "$COORD_RADIUS_INPUT"
    print_success "Sphere defined at (${ROI_X}, ${ROI_Y}, ${ROI_Z})mm with radius ${ROI_RADIUS}mm"
    export ROI_X ROI_Y ROI_Z ROI_RADIUS
}

# Function to list available atlases
list_atlases() {
    local subject_id=$1
    local atlas_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id/segmentation"
    
    if [ ! -d "$atlas_dir" ]; then
        echo "Error: Atlas directory not found: $atlas_dir"
        return 1
    fi

    echo "Available Atlases:"
    echo "-------------------"
    
    # Reset global variables
    ATLAS_LIST=()
    ATLAS_LIST_LENGTH=0
    ATLAS_DIR="$atlas_dir"
    
    # Find all unique atlas types by looking at .annot files
    local i=1
    for annot_file in "$atlas_dir"/*.annot; do
        if [ -f "$annot_file" ]; then
            # Extract the atlas name from the filename
            local base_name=$(basename "$annot_file")
            local atlas_name=${base_name#*.}  # Remove hemisphere prefix
            local atlas_name=${atlas_name%.annot}   # Remove .annot suffix
            
            # Skip if we've already processed this atlas type
            if [[ " ${ATLAS_LIST[*]} " =~ " ${atlas_name} " ]]; then
                continue
            fi
            
            # Check if both hemispheres exist
            if [ -f "$atlas_dir/lh.${atlas_name}.annot" ] && [ -f "$atlas_dir/rh.${atlas_name}.annot" ]; then
                printf "%d. %s\n" $i "$atlas_name"
                ATLAS_LIST[$i]="$atlas_name"
                ((i++))
            fi
        fi
    done
    
    if [ $i -eq 1 ]; then
        echo "No annotation files found in $atlas_dir"
        return 1
    fi
    
    ATLAS_LIST_LENGTH=$((i-1))
    echo
    return 0
}

# Function to show atlas regions using read_annot.py
show_atlas_regions() {
    local subject_id=$1
    local annot_file=$2
    
    echo "Loading atlas regions..."
    simnibs_python "$script_dir/../utils/read_annot.py" "$ATLAS_DIR/$annot_file"
    
    if [ $? -ne 0 ]; then
        echo "Error reading annotation file"
        return 1
    fi
}

# Function to setup atlas ROI with region listing
setup_atlas_roi() {
    local subject_id=$1
    local selected_atlas=""
    local selected_hemi=""
    
    # Initialize global arrays
    ATLAS_LIST=()
    
    while true; do
        # List available atlases
        list_atlases "$subject_id"
        
        if [ $? -ne 0 ]; then
            echo "Failed to find any atlases. Please check the SimNIBS segmentation directory."
            exit 1
        fi
        
        # Add option to list regions
        echo "$((ATLAS_LIST_LENGTH + 1)). List Regions (view regions in a specific atlas)"
        echo
        
        # Choose atlas
        read -p "Enter your choice (1-$((ATLAS_LIST_LENGTH + 1))): " atlas_choice
        
        if [ "$atlas_choice" = "$((ATLAS_LIST_LENGTH + 1))" ]; then
            # Show atlas selection for region listing
            echo "Choose which atlas to list regions from:"
            list_atlases "$subject_id"
            read -p "Enter atlas number: " list_choice
            
            if [[ "$list_choice" =~ ^[0-9]+$ ]] && [ "$list_choice" -ge 1 ] && [ "$list_choice" -le "$ATLAS_LIST_LENGTH" ]; then
                selected_list_atlas="${ATLAS_LIST[$list_choice]}"
                
                # Choose hemisphere
                echo "Choose hemisphere:"
                echo "1. Left (lh)"
                echo "2. Right (rh)"
                read -p "Enter choice (1 or 2): " hemi_choice
                
                case "$hemi_choice" in
                    1) selected_hemi="lh";;
                    2) selected_hemi="rh";;
                    *) echo "Invalid choice. Please enter 1 or 2."; continue;;
                esac
                
                echo "Regions in selected atlas (${selected_hemi}):"
                show_atlas_regions "$subject_id" "${selected_hemi}.${selected_list_atlas}.annot"
            else
                echo "Invalid choice. Please enter a number between 1 and $ATLAS_LIST_LENGTH."
            fi
            echo
            continue
        fi
        
        if [[ "$atlas_choice" =~ ^[0-9]+$ ]] && [ "$atlas_choice" -ge 1 ] && [ "$atlas_choice" -le "$ATLAS_LIST_LENGTH" ]; then
            selected_atlas="${ATLAS_LIST[$atlas_choice]}"
            
            # Choose hemisphere
            echo "Choose hemisphere:"
            echo "1. Left (lh)"
            echo "2. Right (rh)"
            read -p "Enter choice (1 or 2): " hemi_choice
            
            case "$hemi_choice" in
                1) selected_hemi="lh";;
                2) selected_hemi="rh";;
                *) echo "Invalid choice. Please enter 1 or 2."; continue;;
            esac
            
            # Get ROI label
            while true; do
                echo "Enter the ROI label number from the selected atlas:"
                read -p "Label number (or 'l' to list regions again): " roi_label
                
                if [ "$roi_label" = "l" ] || [ "$roi_label" = "L" ]; then
                    show_atlas_regions "$subject_id" "${selected_hemi}.${selected_atlas}.annot"
                    continue
                fi
                
                if [[ "$roi_label" =~ ^[0-9]+$ ]]; then
                    # Verify the label exists in the atlas by checking read_annot.py output
                    if show_atlas_regions "$subject_id" "${selected_hemi}.${selected_atlas}.annot" | grep -q "^[[:space:]]*$roi_label:"; then
                        break
                    else
                        echo "Invalid label. This ID does not exist in the selected atlas."
                    fi
                else
                    echo "Invalid label. Please enter a number or 'l' to list regions."
                fi
            done

            # Set the full path to the atlas and export hemisphere
            export ATLAS_PATH="$ATLAS_DIR/${selected_hemi}.${selected_atlas}.annot"
            export SELECTED_HEMISPHERE="$selected_hemi"
            export ROI_LABEL="$roi_label"
            export ROI_METHOD="atlas"
            break
        else
            echo "Invalid choice. Please enter a number between 1 and $((ATLAS_LIST_LENGTH + 1))."
        fi
    done
    
    # Debug output to verify environment variables
    echo "Selected atlas configuration:"
    echo "ATLAS_PATH: $ATLAS_PATH"
    echo "SELECTED_HEMISPHERE: $SELECTED_HEMISPHERE"
    echo "ROI_LABEL: $ROI_LABEL"
    echo "ROI_METHOD: $ROI_METHOD"
}

# Function to setup non-ROI for focality with region listing
setup_non_roi() {
    if [ "$goal" != "focality" ]; then
        return
    fi

    echo -e "${GREEN}Choose non-ROI definition method:${RESET}"
    echo "1. everything_else (use everything outside the ROI)"
    echo "2. specific (define a specific non-ROI region)"
    while true; do
        read -p "Enter your choice (1 or 2): " non_roi_choice
        case "$non_roi_choice" in
            1) 
                non_roi_method="everything_else"
                break 
                ;;
            2) 
                non_roi_method="specific"
                if [ "$ROI_METHOD" = "spherical" ]; then
                    print_section_header "Spherical Non-ROI Configuration"
                    echo
                    get_coordinate_and_radius_input "Define non-ROI sphere location and size (in mm):" "Input"
                    IFS=',' read -r NON_ROI_X NON_ROI_Y NON_ROI_Z NON_ROI_RADIUS <<< "$COORD_RADIUS_INPUT"
                    print_success "Sphere defined at (${NON_ROI_X}, ${NON_ROI_Y}, ${NON_ROI_Z})mm with radius ${NON_ROI_RADIUS}mm"
                    export NON_ROI_X NON_ROI_Y NON_ROI_Z NON_ROI_RADIUS
                else  # atlas-based ROI
                    # List available atlases
                    list_atlases "$first_subject"
                    
                    if [ $? -ne 0 ]; then
                        echo -e "${RED}Failed to find any atlases. Please check the SimNIBS segmentation directory.${RESET}"
                        echo -e "${YELLOW}Defaulting to 'everything_else' method.${RESET}"
                        non_roi_method="everything_else"
                        break
                    fi
                    
                    # Add option to list regions
                    echo "$((ATLAS_LIST_LENGTH + 1)). List Regions (view regions in a specific atlas)"
                    echo
                    
                    # Choose atlas
                    read -p "Enter your choice (1-$((ATLAS_LIST_LENGTH + 1))): " atlas_choice
                    
                    if [ "$atlas_choice" = "$((ATLAS_LIST_LENGTH + 1))" ]; then
                        # Show atlas selection for region listing
                        echo "Choose which atlas to list regions from:"
                        list_atlases "$first_subject"
                        read -p "Enter atlas number: " list_choice
                        
                        if [[ "$list_choice" =~ ^[0-9]+$ ]] && [ "$list_choice" -ge 1 ] && [ "$list_choice" -le "$ATLAS_LIST_LENGTH" ]; then
                            selected_non_roi_atlas="${ATLAS_LIST[$list_choice]}"
                            
                            # Choose hemisphere
                            echo "Choose hemisphere:"
                            echo "1. Left (lh)"
                            echo "2. Right (rh)"
                            read -p "Enter choice (1 or 2): " hemi_choice
                            
                            case "$hemi_choice" in
                                1) selected_non_roi_hemi="lh";;
                                2) selected_non_roi_hemi="rh";;
                                *) echo "Invalid choice. Please enter 1 or 2."; continue;;
                            esac
                            
                            echo "Regions in selected atlas (${selected_non_roi_hemi}):"
                            show_atlas_regions "$first_subject" "${selected_non_roi_hemi}.${selected_non_roi_atlas}.annot"
                        else
                            echo -e "${RED}Invalid choice. Please enter a number between 1 and $ATLAS_LIST_LENGTH.${RESET}"
                        fi
                        echo
                        continue
                    fi
                    
                    if [[ "$atlas_choice" =~ ^[0-9]+$ ]] && [ "$atlas_choice" -ge 1 ] && [ "$atlas_choice" -le "$ATLAS_LIST_LENGTH" ]; then
                        selected_non_roi_atlas="${ATLAS_LIST[$atlas_choice]}"
                        
                        # Choose hemisphere
                        echo "Choose hemisphere:"
                        echo "1. Left (lh)"
                        echo "2. Right (rh)"
                        read -p "Enter choice (1 or 2): " hemi_choice
                        
                        case "$hemi_choice" in
                            1) selected_non_roi_hemi="lh";;
                            2) selected_non_roi_hemi="rh";;
                            *) echo "Invalid choice. Please enter 1 or 2."; continue;;
                        esac
                        
                        # Show regions for selected atlas and hemisphere
                        echo "Regions in selected atlas (${selected_non_roi_hemi}):"
                        show_atlas_regions "$first_subject" "${selected_non_roi_hemi}.${selected_non_roi_atlas}.annot"
                        
                        # Get ROI label
                        while true; do
                            echo "Enter the non-ROI label number from the selected atlas:"
                            read -p "Label number (or 'l' to list regions again): " non_roi_label
                            
                            if [ "$non_roi_label" = "l" ] || [ "$non_roi_label" = "L" ]; then
                                show_atlas_regions "$first_subject" "${selected_non_roi_hemi}.${selected_non_roi_atlas}.annot"
                                continue
                            fi
                            
                            if [[ "$non_roi_label" =~ ^[0-9]+$ ]]; then
                                # Verify the label exists in the atlas
                                if show_atlas_regions "$first_subject" "${selected_non_roi_hemi}.${selected_non_roi_atlas}.annot" | grep -q "^[[:space:]]*$non_roi_label:"; then
                                    break
                                else
                                    echo -e "${RED}Invalid label. This ID does not exist in the selected atlas.${RESET}"
                                fi
                            else
                                echo -e "${RED}Invalid label. Please enter a number or 'l' to list regions.${RESET}"
                            fi
                        done

                        # Set the non-ROI atlas information
                        export NON_ROI_ATLAS_PATH="$ATLAS_DIR/${selected_non_roi_hemi}.${selected_non_roi_atlas}.annot"
                        export NON_ROI_HEMISPHERE="$selected_non_roi_hemi"
                        export NON_ROI_LABEL="$non_roi_label"

                        echo -e "\n${GREEN}Selected non-ROI configuration:${RESET}"
                        echo "NON_ROI_ATLAS_PATH: $NON_ROI_ATLAS_PATH"
                        echo "NON_ROI_HEMISPHERE: $NON_ROI_HEMISPHERE"
                        echo "NON_ROI_LABEL: $NON_ROI_LABEL"
                    else
                        echo -e "${RED}Invalid choice. Please enter a number between 1 and $ATLAS_LIST_LENGTH.${RESET}"
                        continue
                    fi
                fi
                break 
                ;;
            *) 
                echo -e "${RED}Invalid choice. Please enter 1 or 2.${RESET}" 
                ;;
        esac
    done
}

# Add this function near the other utility functions
print_section_header() {
    local title="$1"
    echo -e "\n${BG_BLUE}${BOLD}=== $title ===${RESET}"
}

print_error() {
    echo -e "${BOLD_RED}ERROR: $1${RESET}"
}

print_warning() {
    echo -e "${BOLD_YELLOW}WARNING: $1${RESET}"
}

print_success() {
    echo -e "${BOLD_GREEN}✓ $1${RESET}"
}

print_parameter() {
    local param_name="$1"
    local param_value="$2"
    echo -e "${BLUE}$param_name:${RESET} $param_value"
}

# Add this helper function to get the label name from number
get_label_name() {
    local atlas_file="$1"
    local label_number="$2"
    # Use read_annot.py to get the label name
    local label_name=$(simnibs_python "$script_dir/../utils/read_annot.py" "$atlas_file" | grep "^[[:space:]]*$label_number:" | cut -d':' -f2 | cut -d'|' -f1 | xargs)
    echo "$label_name"
}

# Function to show welcome message
show_welcome_message() {
    clear  # Clear the screen before starting
    echo -e "${BOLD_CYAN}╔════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD_CYAN}║     TI-CSC Flex Search Optimizer      ║${RESET}"
    echo -e "${BOLD_CYAN}╚════════════════════════════════════════╝${RESET}"
    echo -e "${CYAN}Version 2.0 - $(date +%Y)${RESET}"
    echo -e "${CYAN}Optimize electrode positions for targeted stimulation${RESET}\n"
}

# Function to show confirmation dialog
show_confirmation_dialog() {
    echo -e "\n${BOLD_CYAN}Configuration Summary${RESET}"
    echo -e "----------------------------------------"
    echo -e "${BOLD}Selected Parameters:${RESET}"
    
    # Subject Information
    echo -e "\n${BOLD_CYAN}Subject Information:${RESET}"
    local subject_list=""
    for num in ${subject_choices//,/ }; do
        if [ -n "$subject_list" ]; then
            subject_list+=", "
        fi
        subject_list+="${subjects[$((num-1))]}"
    done
    echo -e "Subjects: ${CYAN}$subject_list${RESET}"
    
    # Optimization Parameters
    echo -e "\n${BOLD_CYAN}Optimization Parameters:${RESET}"
    echo -e "Goal: ${CYAN}$goal${RESET}"
    echo -e "Post-processing Method: ${CYAN}$postproc${RESET}"
    
    # Electrode Configuration
    echo -e "\n${BOLD_CYAN}Electrode Configuration:${RESET}"
    echo -e "EEG Net: ${CYAN}$eeg_net${RESET}"
    echo -e "Electrode Radius: ${CYAN}${radius}mm${RESET}"
    echo -e "Electrode Current: ${CYAN}${current}mA${RESET}"
    
    # Optimization Settings
    echo -e "\n${BOLD_CYAN}Optimization Settings:${RESET}"
    echo -e "Max Iterations: ${CYAN}$max_iterations${RESET}"
    echo -e "Population Size: ${CYAN}$population_size${RESET}"
    echo -e "CPU Cores: ${CYAN}$cpus${RESET}"
    echo -e "Quiet Mode: ${CYAN}$quiet_mode${RESET}"
    
    # Mapping Options
    echo -e "\n${BOLD_CYAN}Mapping Options:${RESET}"
    echo -e "Enable Mapping: ${CYAN}$enable_mapping${RESET}"
    if [ "$enable_mapping" = "true" ]; then
        echo -e "Run Mapped Simulation: ${CYAN}$run_mapped_simulation${RESET}"
    fi
    
    # ROI Configuration
    echo -e "\n${BOLD_CYAN}ROI Configuration:${RESET}"
    echo -e "ROI Method: ${CYAN}$ROI_METHOD${RESET}"
    if [ "$ROI_METHOD" = "atlas" ]; then
        echo -e "Atlas: ${CYAN}$(basename "$ATLAS_PATH")${RESET}"
        echo -e "Hemisphere: ${CYAN}$SELECTED_HEMISPHERE${RESET}"
        local roi_label_name=$(get_label_name "$ATLAS_PATH" "$ROI_LABEL")
        echo -e "ROI Label: ${CYAN}$ROI_LABEL - $roi_label_name${RESET}"
    else
        echo -e "ROI Coordinates: ${CYAN}(${ROI_X}, ${ROI_Y}, ${ROI_Z})${RESET}"
        echo -e "ROI Radius: ${CYAN}${ROI_RADIUS}mm${RESET}"
    fi
    
    # Focality Settings (if applicable)
    if [ "$goal" = "focality" ]; then
        echo -e "\n${BOLD_CYAN}Focality Settings:${RESET}"
        echo -e "Non-ROI Method: ${CYAN}$non_roi_method${RESET}"
        echo -e "Threshold Values: ${CYAN}$THRESHOLD_VALUES${RESET}"
        if [ "$non_roi_method" = "specific" ]; then
            if [ "$ROI_METHOD" = "atlas" ]; then
                echo -e "Non-ROI Atlas: ${CYAN}$(basename "$NON_ROI_ATLAS_PATH")${RESET}"
                echo -e "Non-ROI Hemisphere: ${CYAN}$NON_ROI_HEMISPHERE${RESET}"
                local non_roi_label_name=$(get_label_name "$NON_ROI_ATLAS_PATH" "$NON_ROI_LABEL")
                echo -e "Non-ROI Label: ${CYAN}$NON_ROI_LABEL - $non_roi_label_name${RESET}"
            else
                echo -e "Non-ROI Coordinates: ${CYAN}(${NON_ROI_X}, ${NON_ROI_Y}, ${NON_ROI_Z})${RESET}"
                echo -e "Non-ROI Radius: ${CYAN}${NON_ROI_RADIUS}mm${RESET}"
            fi
        fi
    fi
    
    echo -e "\n${BOLD_YELLOW}Please review the configuration above.${RESET}"
    echo -e "${YELLOW}Do you want to proceed with the optimization? (y/n)${RESET}"
    read -p " " confirm
    
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo -e "${RED}Optimization cancelled by user.${RESET}"
        exit 0
    fi
}

# Main script execution
show_welcome_message

# Collect all necessary inputs with section headers
print_section_header "Subject Selection"
choose_subjects

# Get the first selected subject for initial setup
first_subject="${selected_subjects[0]}"

print_section_header "Optimization Parameters"
choose_goal
choose_postproc

print_section_header "Electrode Configuration"
choose_eeg_net
choose_electrode_params

print_section_header "Optimization Settings"
choose_optimization_params
choose_mapping_options
choose_quiet_mode

print_section_header "ROI Configuration"
choose_roi_method "$first_subject"

# Setup non-ROI if goal is focality
if [ "$goal" = "focality" ]; then
    print_section_header "Non-ROI Configuration"
    setup_non_roi
fi

# Show confirmation dialog before proceeding
show_confirmation_dialog

# Process each subject
for subject_id in "${selected_subjects[@]}"; do
    print_section_header "Processing Subject: $subject_id"
    
    # Build the command with all required arguments
    cmd="simnibs_python \"$flex_search_dir/flex-search.py\""
    cmd+=" --subject \"$subject_id\""
    cmd+=" --goal \"$goal\""
    cmd+=" --postproc \"$postproc\""
    cmd+=" --eeg-net \"$eeg_net\""
    cmd+=" --radius \"$radius\""
    cmd+=" --current \"$current\""
    cmd+=" --roi-method \"$ROI_METHOD\""
    
    # Add optimization parameters
    cmd+=" --max-iterations \"$max_iterations\""
    cmd+=" --population-size \"$population_size\""
    cmd+=" --cpus \"$cpus\""
    
    # Add mapping options
    if [ "$enable_mapping" = "true" ]; then
        cmd+=" --enable-mapping"
        if [ "$run_mapped_simulation" = "false" ]; then
            cmd+=" --disable-mapping-simulation"
        fi
    fi
    
    # Add quiet mode
    if [ "$quiet_mode" = "true" ]; then
        cmd+=" --quiet"
    fi
    
    # Add non-ROI arguments if goal is focality
    if [ "$goal" = "focality" ] && [ -n "$non_roi_method" ]; then
        cmd+=" --non-roi-method \"$non_roi_method\""
        if [ -n "$THRESHOLD_VALUES" ]; then
            cmd+=" --thresholds \"$THRESHOLD_VALUES\""
        fi
    fi
    
    # Execute the command
    echo -e "\n${CYAN}Executing optimization...${RESET}"
    if eval "$cmd"; then
        print_success "Successfully completed flex-search for subject $subject_id"
    else
        print_error "Failed to complete flex-search for subject $subject_id"
        echo -e "${YELLOW}Check the logs above for more details${RESET}"
    fi
done

print_success "All optimizations completed!" 