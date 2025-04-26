#!/bin/bash

###########################################
# Ido Haber / ihaber@wisc.edu
# October 15, 2024
# optimized for TI-CSC analyzer
# This script is used to run a simulation pipeline for a given subject. 
###########################################

set -e  # Exit immediately if a command exits with a non-zero status

umask 0000  # Set umask to 0000 to ensure all created files and directories have permissions 777

project_dir="/mnt/$PROJECT_DIR_NAME"
subject_dir="$project_dir/Subjects"
simulation_dir="$project_dir/Simulations"
utils_dir="$project_dir/utils"

# Ensure that necessary scripts have execution permissions
# Use find to avoid errors if no .sh files are found
find . -type f -name "*.sh" -exec chmod +x {} \;

# Ensure utils_dir exists and set permissions
if [ ! -d "$utils_dir" ]; then
    mkdir -p "$utils_dir"
    chmod 777 "$utils_dir"
    echo "Created utils directory at $utils_dir with permissions 777."
else
    chmod 777 "$utils_dir"
fi

# Function to validate ROI input (format: X Y Z)
validate_coordinates() {
    local coords=$1
    if [[ ! $coords =~ ^[0-9]+\ [0-9]+\ [0-9]+$ ]]; then
        echo "Invalid format. Please enter in the format X Y Z (e.g., 50 60 70)."
        return 1
    fi
    return 0
}

# Function to validate electrode pair input (format: E1,E2)
validate_pair() {
    local pair=$1
    if [[ ! $pair =~ ^E[0-9]+,E[0-9]+$ ]]; then
        echo "Invalid format. Please enter in the format E1,E2 (e.g., E10,E11)."
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
    echo "Created and initialized $montage_file with permissions 777."
    new_montage_added=true
else
    chmod 777 "$montage_file"
fi

# Ensure roi_list.json exists and set permissions
roi_file="$utils_dir/roi_list.json"
if [ ! -f "$roi_file" ]; then
    cat <<EOL > "$roi_file"
{
  "ROIs": {}
}
EOL
    chmod 777 "$roi_file"
    echo "Created and initialized $roi_file with permissions 777."
    new_roi_added=true
else
    chmod 777 "$roi_file"
fi

# List available subjects based on the project directory input
list_subjects() {
    subjects=()
    i=1
    for subject_path in "$subject_dir"/m2m_*; do
        if [ -d "$subject_path" ]; then
            subject_id=$(basename "$subject_path" | sed 's/m2m_//')
            subjects+=("$subject_id")
            echo "$i. $subject_id"
            ((i++))
        fi
    done
}

# Function to handle invalid input and reprompt
reprompt() {
    echo "Invalid input. Please try again."
}

# Prompt user to choose subjects, ensure valid numeric input
choose_subjects() {
    echo "Choose subjects by entering the corresponding numbers (comma-separated, e.g., 1,2):"
    list_subjects
    while true; do
        read -p "Enter the numbers of the subjects to analyze: " subject_choices
        if [[ "$subject_choices" =~ ^[0-9,]+$ ]]; then
            IFS=',' read -r -a selected_subjects <<< "$subject_choices"
            for num in "${selected_subjects[@]}"; do
                if [[ $num -le 0 || $num -gt ${#subjects[@]} ]]; then
                    reprompt
                    continue 2  # Reprompt the user
                fi
            done
            break
        else
            reprompt
        fi
    done
}

# Prompt user for simulation type and ensure valid choice
choose_simulation_type() {
    echo "What type of simulation do you want to run?"
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
        echo "Which anisotropic type?"
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

# Prompt for simulation mode and ensure valid input
choose_simulation_mode() {
    while true; do
        read -p "Unipolar or Multipolar simulation? Enter U or M: " sim_mode
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



# Function to prompt and select montages
prompt_montages() {
    while true; do
        montages=$(jq -r ".${montage_type} | keys[]" "$montage_file")

        echo "Available montages:"
        montage_array=($montages)
        half_count=$(( (${#montage_array[@]} + 1) / 2 ))

        for (( i=0; i<half_count; i++ )); do
            left="${montage_array[$i]}"
            right="${montage_array[$((i + half_count))]}"
            printf "%2d. %-20s" $((i + 1)) "$left"
            if [ -n "$right" ]; then
                printf "%2d. %s" $((i + 1 + half_count)) "$right"
            fi
            printf "\n"
        done

        echo "$(( ${#montage_array[@]} + 1 )). Add a new montage?"

        read -p "Enter the numbers of the montages to simulate (comma-separated): " montage_choices
        if [[ ! "$montage_choices" =~ ^[0-9,]+$ ]]; then
            reprompt
            continue
        fi

        IFS=',' read -r -a selected_numbers <<< "$montage_choices"
        selected_montages=()
        new_montage_added=false

        for number in "${selected_numbers[@]}"; do
            if [ "$number" -eq "$(( ${#montage_array[@]} + 1 ))" ]; then
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
                new_montage_added=true
                break  # Re-prompt the user with the updated montage list
            else
                selected_montage=$(echo "$montages" | sed -n "${number}p")
                if [ -n "$selected_montage" ]; then
                    selected_montages+=("$selected_montage")
                else
                    echo "Invalid montage number: $number. Please try again."
                    continue 2  # Reprompt montage selection
                fi
            fi
        done

        if ! $new_montage_added; then
            break
        fi
    done
}

# Function to prompt and select ROIs
prompt_rois() {
    while true; do
        rois=$(jq -r '.ROIs | keys[]' "$roi_file")

        echo "Available ROIs:"
        roi_array=($rois)
        for (( i=0; i<${#roi_array[@]}; i++ )); do
            echo "$((i+1)). ${roi_array[$i]}"
        done

        echo "$(( ${#roi_array[@]} + 1 )). Add a new ROI"

        read -p "Enter the numbers of the ROIs to analyze (comma-separated): " roi_choices
        if [[ ! "$roi_choices" =~ ^[0-9,]+$ ]]; then
            reprompt
            continue
        fi

        IFS=',' read -r -a selected_rois <<< "$roi_choices"
        selected_roi_names=()
        new_roi_added=false

        for roi in "${selected_rois[@]}"; do
            if [ "$roi" -eq "$(( ${#roi_array[@]} + 1 ))" ]; then
                read -p "Enter new ROI name: " new_roi_name
                valid=false
                until $valid; do
                    read -p "Enter Voxel Coordinates (format: X Y Z): " new_coordinates
                    validate_coordinates "$new_coordinates" && valid=true
                done
                jq ".ROIs[\"$new_roi_name\"]=\"$new_coordinates\"" "$roi_file" > temp.json && mv temp.json "$roi_file"
                chmod 777 "$roi_file"
                new_roi_added=true
                break  # Re-prompt the user with the updated ROI list
            else
                roi_name=$(echo "$rois" | sed -n "${roi}p")
                if [ -n "$roi_name" ]; then
                    selected_roi_names+=("$roi_name")
                else
                    echo "Invalid ROI number: $roi. Please try again."
                    continue 2  # Reprompt ROI selection
                fi
            fi
        done

        if ! $new_roi_added; then
            break
        fi
    done
}

# Prompt the user to select montages and ROIs
choose_subjects
choose_simulation_type
choose_simulation_mode
prompt_montages
prompt_rois

# Echo a summary of all selections
echo " "
echo "#####################################################"
echo "Simulation Summary"
echo " "
echo "Subjects: ${subjects[*]}"
echo "Type: $sim_type_text"
echo "Montage type: $montage_type_text"
echo "Montages: ${selected_montages[*]}"
echo "ROIs: ${selected_roi_names[*]}"
echo "#####################################################"
echo " "

# Loop through selected subjects and run the pipeline
for subject_index in "${selected_subjects[@]}"; do
    subject_id="${subjects[$((subject_index-1))]}"

    # Call the appropriate main pipeline script with the gathered parameters
    ./"$main_script" "$subject_id" "$conductivity" "$subject_dir" "$simulation_dir" "$sim_mode" "${selected_montages[@]}" -- "${selected_roi_names[@]}"

    # Call sphere-creator.sh with the selected ROIs
    echo "Calling sphere-creator.sh with ROIs: ${selected_roi_names[@]}"
    ./sphere-creater.sh "$subject_id" "$simulation_dir" "${selected_roi_names[@]}"
done

# Output success message if new montages or ROIs were added
if [ "$new_montage_added" = true ]; then
    echo "New montage added to montage_list.json."
fi

if [ "$new_roi_added" = true ]; then
    echo "New ROI added to roi_list.json."
fi

echo "All tasks completed successfully for subject ID: $subject_id"
