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
flex_search_dir="$script_dir/flex-search"
project_dir="/mnt/$PROJECT_DIR_NAME"
subject_dir="$project_dir/Subjects"
analysis_dir="$project_dir/Analysis"
utils_dir="$project_dir/utils"
config_file="$project_dir/flex_config.json"

# Define color variables
BOLD='\033[1m'
UNDERLINE='\033[4m'
RESET='\033[0m'
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD_CYAN='\033[1;36m'
YELLOW='\033[0;33m'

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
    for subject_path in "$subject_dir"/m2m_*; do
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
            IFS=',' read -r -a selected_subjects <<< "$subject_choices"
            valid_input=true
            for num in "${selected_subjects[@]}"; do
                if [[ $num -le 0 || $num -gt ${#subjects[@]} ]]; then
                    echo -e "${RED}Invalid subject number: $num. Please try again.${RESET}"
                    valid_input=false
                    break
                fi
            done
            if $valid_input; then
                break
            fi
        else
            echo -e "${RED}Invalid input. Please enter numbers separated by commas.${RESET}"
        fi
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
    while true; do
        read -p "Enter your choice (1 or 2): " goal_choice
        case "$goal_choice" in
            1) goal="mean"; break ;;
            2) goal="focality"; break ;;
            *) echo -e "${RED}Invalid choice. Please enter 1 or 2.${RESET}" ;;
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
    local eeg_dir="$subject_dir/m2m_$subject_id/eeg_positions"
    
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
    first_subject="${subjects[$((${selected_subjects[0]}-1))]}"
    
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

# Function to list available atlases for a subject
list_atlases() {
    local subject_id=$1
    local label_dir="$subject_dir/m2m_$subject_id/label"
    
    if [ ! -d "$label_dir" ]; then
        echo -e "${RED}Error: Label directory not found for subject $subject_id${RESET}"
        return 1
    fi

    echo -e "${BOLD_CYAN}Available atlases:${RESET}"
    echo "-------------------"
    
    # Initialize array for atlases
    atlases=()
    index=1
    
    # List all .annot files and extract base names
    for atlas_file in "$label_dir"/*.annot; do
        if [ -f "$atlas_file" ]; then
            atlas_name=$(basename "$atlas_file")
            atlases+=("$atlas_name")
            printf "%3d. %s\n" "$index" "$atlas_name"
            ((index++))
        fi
    done
    
    if [ ${#atlases[@]} -eq 0 ]; then
        echo -e "${YELLOW}No atlas files found in $label_dir${RESET}"
        return 1
    fi
    
    echo
    return 0
}

# Choose ROI definition method and parameters
choose_roi_method() {
    if ! is_prompt_enabled "roi_method"; then
        local default_value=$(get_default_value "roi_method")
        if [ -n "$default_value" ]; then
            roi_method="$default_value"
            echo -e "${CYAN}Using default ROI method: $roi_method${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Choose ROI definition method:${RESET}"
    echo "1. Spherical (define by coordinates and radius)"
    echo "2. Cortical (use atlas-based parcellation)"
    while true; do
        read -p "Enter your choice (1 or 2): " roi_choice
        case "$roi_choice" in
            1) 
                roi_method="spherical"
                echo -e "${GREEN}Enter spherical ROI parameters in subject space:${RESET}"
                while true; do
                    read -p "X coordinate (mm): " roi_x
                    read -p "Y coordinate (mm): " roi_y
                    read -p "Z coordinate (mm): " roi_z
                    read -p "Radius (mm): " roi_radius
                    if [[ "$roi_x" =~ ^-?[0-9]+\.?[0-9]*$ ]] && \
                       [[ "$roi_y" =~ ^-?[0-9]+\.?[0-9]*$ ]] && \
                       [[ "$roi_z" =~ ^-?[0-9]+\.?[0-9]*$ ]] && \
                       [[ "$roi_radius" =~ ^[0-9]+\.?[0-9]*$ ]]; then
                        export ROI_X="$roi_x"
                        export ROI_Y="$roi_y"
                        export ROI_Z="$roi_z"
                        export ROI_RADIUS="$roi_radius"
                        break
                    else
                        echo -e "${RED}Invalid input. Please enter valid numbers.${RESET}"
                    fi
                done
                break 
                ;;
            2)  
                roi_method="cortical"
                # Get the first subject to list available atlases
                first_subject="${subjects[$((${selected_subjects[0]}-1))]}"
                
                if ! list_atlases "$first_subject"; then
                    echo -e "${RED}Failed to list atlases. Please check the subject directory.${RESET}"
                    return 1
                fi

                while true; do
                    read -p "Enter the number of the atlas to use: " atlas_choice
                    if [[ "$atlas_choice" =~ ^[0-9]+$ ]] && [ "$atlas_choice" -ge 1 ] && [ "$atlas_choice" -le "${#atlases[@]}" ]; then
                        selected_atlas="${atlases[$((atlas_choice-1))]}"
                        echo -e "${GREEN}Enter the label value for your target region:${RESET}"
                        read -p "Label value: " label_value
                        if [[ "$label_value" =~ ^[0-9]+$ ]]; then
                            export ROI_LABEL="$label_value"
                            export ATLAS_PATH="$selected_atlas"
                            break
                        else
                            echo -e "${RED}Invalid label value. Please enter a positive integer.${RESET}"
                        fi
                    else
                        echo -e "${RED}Invalid choice. Please enter a number between 1 and ${#atlases[@]}.${RESET}"
                    fi
                done
                break 
                ;;
            *) echo -e "${RED}Invalid choice. Please enter 1 or 2.${RESET}" ;;
        esac
    done
}

# Main script execution
echo -e "${BOLD_CYAN}TI-CSC Flex Search Optimization Tool${RESET}"
echo "----------------------------------------"

# Create necessary directories
mkdir -p "$analysis_dir"

# Collect all necessary inputs
choose_subjects
choose_goal
choose_postproc
choose_eeg_net
choose_electrode_params
choose_roi_method

# Loop through selected subjects and run the optimization
for subject_index in "${selected_subjects[@]}"; do
    subject_id="${subjects[$((subject_index-1))]}"
    output_dir="$analysis_dir/opt_${subject_id}"
    mkdir -p "$output_dir"

    echo -e "\n${BOLD_CYAN}Processing subject: ${subject_id}${RESET}"
    echo "Output directory: $output_dir"

    # Export necessary environment variables
    export SUBJECT_ID="$subject_id"
    export PROJECT_DIR="$project_dir"
    export OUTPUT_DIR="$output_dir"

    # Call the flex-search Python script with all parameters
    simnibs_python "$flex_search_dir/flex-search.py" \
        --subject "$subject_id" \
        --goal "$goal" \
        --postproc "$postproc" \
        --eeg-net "$eeg_net" \
        --radius "$radius" \
        --current "$current" \
        --roi-method "$roi_method" \
        --output-dir "$output_dir"

    # Check if the optimization was successful
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Optimization completed successfully for subject $subject_id.${RESET}"
    else
        echo -e "${RED}Optimization failed for subject $subject_id.${RESET}"
        continue
    fi
done

echo -e "${GREEN}All optimizations completed.${RESET}" 