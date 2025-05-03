#!/bin/bash

###########################################
# Ido Haber / ihaber@wisc.edu
# October 31, 2024
# Optimized for TI-CSC analyzer
# This script is used to run a simulation pipeline for a given subject.
###########################################

set -e  # Exit immediately if a command exits with a non-zero status

umask 0000  # Set umask to 0000 to ensure all created files and directories have permissions 777

# Base directories
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
simulator_dir="$script_dir/simulator"
project_dir="/mnt/$PROJECT_DIR_NAME"
utils_dir="$project_dir/utils"
config_file="$project_dir/config/sim_config.json"

# Define color variables
BOLD='\033[1m'
UNDERLINE='\033[4m'
RESET='\033[0m'
RED='\033[0;31m' #Red for errors or important exit messages.
GREEN='\033[0;32m' #Green for successful completions.
CYAN='\033[0;36m' #Cyan for actions being performed.
BOLD_CYAN='\033[1;36m'
YELLOW='\033[0;33m' #Yellow for warnings or important notices

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

# Ensure that necessary scripts have execution permissions
find "$simulator_dir" -type f -name "*.sh" -exec chmod +x {} \;

# Ensure utils_dir exists and set permissions
if [ ! -d "$utils_dir" ]; then
    mkdir -p "$utils_dir"
    chmod 777 "$utils_dir"
    echo -e "${GREEN}Created utils directory at $utils_dir with permissions 777.${RESET}"
else
    chmod 777 "$utils_dir"
fi

# Function to validate electrode pair input (format: E1,E2)
validate_pair() {
    local pair=$1
    if [[ ! $pair =~ ^E[0-9]+,E[0-9]+$ ]]; then
        echo -e "${RED}Invalid format. Please enter in the format E1,E2 (e.g., E10,E11).${RESET}"
        return 1
    fi
    return 0
}

# Ensure montage_list.json exists and set permissions
montage_file="$utils_dir/montage_list.json"
if [ ! -f "$montage_file" ]; then
    cat <<EOL > "$montage_file"
{
  "uni_polar_montages": {},
  "multi_polar_montages": {}
}
EOL
    chmod 777 "$montage_file"
    echo -e "${GREEN}Created and initialized $montage_file with permissions 777.${RESET}"
    new_montage_added=true
else
    chmod 777 "$montage_file"
fi

# Function to handle invalid input and reprompt
reprompt() {
    echo -e "${RED}Invalid input. Please try again.${RESET}"
}

# Function to list available subjects based on the project directory input
list_subjects() {
    subjects=()
    for subject_path in "$project_dir"/*/SimNIBS/m2m_*; do
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
            for num in "${selected_subjects[@]}"; do
                if [[ $num -le 0 || $num -gt ${#subjects[@]} ]]; then
                    reprompt
                    continue 2
                fi
            done
            break
        else
            reprompt
        fi
    done
}

# Choose simulation type with configuration support
choose_simulation_type() {
    if ! is_prompt_enabled "conductivity"; then
        local default_value=$(get_default_value "conductivity")
        if [ -n "$default_value" ]; then
            conductivity="$default_value"
            sim_type_text="$(tr '[:lower:]' '[:upper:]' <<< ${default_value:0:1})${default_value:1}"
            echo -e "${CYAN}Using default conductivity: $conductivity${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}What type of simulation do you want to run?${RESET}"
    echo "1. Isotropic"
    echo "2. Anisotropic"
    while true; do
        read -p "Enter your choice (1 or 2): " sim_type
        if [[ "$sim_type" == "1" ]]; then
            conductivity="scalar"
            sim_type_text="Isotropic"
            break
        elif [[ "$sim_type" == "2" ]]; then
            choose_anisotropic_type
            break
        else
            reprompt
        fi
    done
}

# Prompt user for anisotropic type and ensure valid choice
choose_anisotropic_type() {
    anisotropic_selected=false
    while [ "$anisotropic_selected" = false ]; do
        echo -e "${GREEN}Which anisotropic type?${RESET}"
        echo "1. vn"
        echo "2. dir"
        echo "3. mc"
        echo "4. Explain the difference"
        read -p "Enter your choice (1, 2, 3, or 4): " anisotropic_type
        case "$anisotropic_type" in
            1) conductivity="vn"; anisotropic_selected=true; sim_type_text="Anisotropic (vn)" ;;
            2) conductivity="dir"; anisotropic_selected=true; sim_type_text="Anisotropic (dir)" ;;
            3) conductivity="mc"; anisotropic_selected=true; sim_type_text="Anisotropic (mc)" ;;
            4) echo "Explanation of the different anisotropic types..." ;;
            *) reprompt ;;
        esac
    done
}

# Choose simulation mode with configuration support
choose_simulation_mode() {
    if ! is_prompt_enabled "sim_mode"; then
        local default_value=$(get_default_value "sim_mode")
        if [ -n "$default_value" ]; then
            sim_mode="$default_value"
            if [[ "$sim_mode" == "U" ]]; then
                montage_type="uni_polar_montages"
                main_script="main-TI.sh"
                montage_type_text="Unipolar"
            elif [[ "$sim_mode" == "M" ]]; then
                montage_type="multi_polar_montages"
                main_script="main-mTI.sh"
                montage_type_text="Multipolar"
            fi
            echo -e "${CYAN}Using default simulation mode: $sim_mode${RESET}"
            return
        fi
    fi

    while true; do
        read -p "$(echo -e "${GREEN}Unipolar or Multipolar simulation? Enter U or M: ${RESET}")" sim_mode
        if [[ "$sim_mode" == "U" ]]; then
            montage_type="uni_polar_montages"
            main_script="main-TI.sh"
            montage_type_text="Unipolar"
            break
        elif [[ "$sim_mode" == "M" ]]; then
            montage_type="multi_polar_montages"
            main_script="main-mTI.sh"
            montage_type_text="Multipolar"
            break
        else
            reprompt
        fi
    done
}

# Choose montages with configuration support
prompt_montages() {
    if ! is_prompt_enabled "montages"; then
        local default_value=$(get_default_value "montages")
        if [ -n "$default_value" ]; then
            selected_montages=($default_value)
            echo -e "${CYAN}Using default montages: ${selected_montages[*]}${RESET}"
            return
        fi
    fi

    while true; do
        montage_data=$(jq -r ".${montage_type}" "$montage_file")
        montage_names=($(echo "$montage_data" | jq -r 'keys[]'))
        total_montages=${#montage_names[@]}

        echo -e "${BOLD_CYAN}Available Montages (${montage_type_text}):${RESET}"
        echo "-----------------------------------------"

        for (( index=0; index<total_montages; index++ )); do
            montage_name="${montage_names[$index]}"
            pairs=$(echo "$montage_data" | jq -r --arg name "$montage_name" '.[$name][] | join(",")' | paste -sd '; ' -)
            printf "%3d. %-25s Pairs: %s\n" $(( index + 1 )) "$montage_name" "$pairs"
        done

        echo
        echo -e "${GREEN}$(( total_montages + 1 )). Add a new montage?${RESET}"
        echo

        read -p "Enter the numbers of the montages to simulate (comma-separated): " montage_choices
        if [[ ! "$montage_choices" =~ ^[0-9,]+$ ]]; then
            reprompt
            continue
        fi

        IFS=',' read -r -a selected_numbers <<< "$montage_choices"
        selected_montages=()
        new_montage_added=false

        for number in "${selected_numbers[@]}"; do
            if [ "$number" -eq "$(( total_montages + 1 ))" ]; then
                read -p "Enter a name for the new montage: " new_montage_name
                valid=false
                until $valid; do
                    read -p "Enter Pair 1 (format: E1,E2): " pair1
                    validate_pair "$pair1" && valid=true
                done
                valid=false
                until $valid; do
                    read -p "Enter Pair 2 (format: E1,E2): " pair2
                    validate_pair "$pair2" && valid=true
                done
                new_montage=$(jq -n --arg name "$new_montage_name" --argjson pairs "[[\"${pair1//,/\",\"}\"], [\"${pair2//,/\",\"}\"]]" '{($name): $pairs}')
                jq ".${montage_type} += $new_montage" "$montage_file" > temp.json && mv temp.json "$montage_file"
                chmod 777 "$montage_file"
                echo -e "${GREEN}New montage '$new_montage_name' added successfully.${RESET}"
                new_montage_added=true
                break
            else
                if (( number > 0 && number <= total_montages )); then
                    selected_montages+=("${montage_names[$((number - 1))]}")
                else
                    echo -e "${RED}Invalid montage number: $number. Please try again.${RESET}"
                    continue 2
                fi
            fi
        done

        if ! $new_montage_added; then
            break
        fi
    done
}

# Choose intensity with configuration support
choose_intensity() {
    if ! is_prompt_enabled "intensity"; then
        local default_value=$(get_default_value "intensity")
        if [ -n "$default_value" ]; then
            intensity_ma="$default_value"
            intensity=$(echo "$intensity_ma * 0.001" | bc -l)
            echo -e "${CYAN}Using default intensity: ${intensity_ma}mA${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Choose stimulation intensity in mA:${RESET}"
    read -p " " intensity_ma
    # Validate that intensity is a positive number
    if ! [[ "$intensity_ma" =~ ^[0-9]+\.?[0-9]*$ ]]; then
        echo -e "${RED}Invalid intensity. Please enter a positive number.${RESET}"
        choose_intensity
        return
    fi
    intensity=$(echo "$intensity_ma * 0.001" | bc -l)
}

# Choose electrode geometry with configuration support
choose_electrode_geometry() {
    # Handle electrode shape
    if ! is_prompt_enabled "electrode_shape"; then
        local default_shape=$(get_default_value "electrode_shape")
        if [ -n "$default_shape" ]; then
            electrode_shape="$default_shape"
            echo -e "${CYAN}Using default electrode shape: $electrode_shape${RESET}"
        else
            prompt_electrode_shape
        fi
    else
        prompt_electrode_shape
    fi

    # Handle electrode dimensions
    if ! is_prompt_enabled "electrode_dimensions"; then
        local default_dims=$(get_default_value "electrode_dimensions")
        if [ -n "$default_dims" ]; then
            dimensions="$default_dims"
            echo -e "${CYAN}Using default electrode dimensions: $dimensions mm${RESET}"
        else
            prompt_electrode_dimensions
        fi
    else
        prompt_electrode_dimensions
    fi

    # Handle electrode thickness
    if ! is_prompt_enabled "electrode_thickness"; then
        local default_thick=$(get_default_value "electrode_thickness")
        if [ -n "$default_thick" ]; then
            thickness="$default_thick"
            echo -e "${CYAN}Using default electrode thickness: $thickness mm${RESET}"
        else
            prompt_electrode_thickness
        fi
    else
        prompt_electrode_thickness
    fi
}

# Helper functions for electrode geometry prompts
prompt_electrode_shape() {
    while true; do
        echo -e "${GREEN}Choose electrode shape (rect/ellipse):${RESET}"
        read -p " " electrode_shape
        if [[ "$electrode_shape" == "rect" || "$electrode_shape" == "ellipse" ]]; then
            break
        else
            echo -e "${RED}Invalid shape. Please enter 'rect' or 'ellipse'.${RESET}"
        fi
    done
}

prompt_electrode_dimensions() {
    while true; do
        echo -e "${GREEN}Enter electrode dimensions (x,y in mm, comma-separated):${RESET}"
        read -p " " dimensions
        if [[ "$dimensions" =~ ^[0-9]+\.?[0-9]*,[0-9]+\.?[0-9]*$ ]]; then
            break
        else
            echo -e "${RED}Invalid dimensions. Please enter two numbers separated by comma (e.g., 8,8).${RESET}"
        fi
    done
}

prompt_electrode_thickness() {
    while true; do
        echo -e "${GREEN}Enter electrode thickness (in mm):${RESET}"
        read -p " " thickness
        if [[ "$thickness" =~ ^[0-9]+\.?[0-9]*$ ]]; then
            break
        else
            echo -e "${RED}Invalid thickness. Please enter a positive number.${RESET}"
        fi
    done
}

# Main script execution
choose_subjects
choose_simulation_type
choose_simulation_mode
prompt_montages
choose_intensity
choose_electrode_geometry

# Loop through selected subjects and run the pipeline
for subject_index in "${selected_subjects[@]}"; do
    subject_id="${subjects[$((subject_index-1))]}"
    subject_dir="$project_dir/$subject_id"
    simulation_dir="$subject_dir/SimNIBS/Simulations"

    # Create simulation directory if it doesn't exist
    mkdir -p "$simulation_dir"

    # Call the appropriate main pipeline script with the gathered parameters
    "$simulator_dir/$main_script" "$subject_id" "$conductivity" "$project_dir" "$simulation_dir" "$sim_mode" "$intensity" "$electrode_shape" "$dimensions" "$thickness" "${selected_montages[@]}" -- "${selected_roi_names[@]}"

done

# Output success message if new montages or ROIs were added
if [ "$new_montage_added" = true ]; then
    echo -e "${GREEN}New montage added to montage_list.json.${RESET}"
fi

echo -e "${GREEN}All tasks completed successfully.${RESET}"
