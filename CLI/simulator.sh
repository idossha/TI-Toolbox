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
simulator_dir="$script_dir/../simulator"
project_dir="/mnt/$PROJECT_DIR_NAME"
ti_csc_dir="$project_dir/ti-csc"
config_dir="$ti_csc_dir/config"
montage_file="$config_dir/montage_list.json"

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

# Function to list available subjects based on the project directory input
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

# Function to run the actual simulation
run_simulation() {
    # Process selected subjects
    IFS=',' read -r -a selected_subjects <<< "$subject_choices"
    
    # Detect if we're in direct execution mode (from GUI)
    is_direct_mode=false
    if [[ "$1" == "--run-direct" || "$DIRECT_MODE" == "true" ]]; then
        is_direct_mode=true
        # Ensure current is set when in direct mode
        if [[ -z "$CURRENT" ]]; then
            echo -e "${RED}Error: Current value not set in direct mode${RESET}"
            exit 1
        fi
        # Set current_a from CURRENT environment variable
        current_a="$CURRENT"
    fi
    
    # Ensure ti-csc directory exists
    if [ ! -d "$ti_csc_dir" ]; then
        mkdir -p "$ti_csc_dir"
        chmod 777 "$ti_csc_dir"
        echo -e "${GREEN}Created ti-csc directory at $ti_csc_dir with permissions 777.${RESET}"
    else
        chmod 777 "$ti_csc_dir"
    fi
    
    # Ensure montage_list.json exists in ti-csc config dir
    if [ ! -f "$montage_file" ]; then
        echo -e "${GREEN}Creating montage file at $montage_file${RESET}"
        cat > "$montage_file" << EOL
{
    "nets": {
        "EGI_template.csv": {
            "uni_polar_montages": {},
            "multi_polar_montages": {}
        }
    }
}
EOL
        chmod 777 "$montage_file"
    else
        # Ensure the file has the correct permissions
        chmod 777 "$montage_file"
    fi
    
    for subject_num in "${selected_subjects[@]}"; do
        # Get the subject ID
        if [[ "$is_direct_mode" == "true" ]]; then
            # In direct mode, use subject IDs directly
            subject_id="$subject_num"
        elif [[ "$subject_num" =~ ^[0-9]+$ ]]; then
            # If it's a number and not in direct mode, get the subject from the array
            if [[ $subject_num -le 0 || $subject_num -gt ${#subjects[@]} ]]; then
                echo -e "${RED}Invalid subject number: $subject_num${RESET}"
                continue
            fi
            subject_id=${subjects[$((subject_num-1))]}
        else
            # If it's not a number, use it directly as subject ID
            subject_id="$subject_num"
        fi
        
        echo -e "${CYAN}Processing subject: $subject_id${RESET}"
        
        # Construct paths for BIDS structure
        subject_dir="$project_dir/sub-$subject_id"
        derivatives_dir="$project_dir/derivatives"
        simnibs_dir="$derivatives_dir/SimNIBS/sub-$subject_id"
        simulation_dir="$simnibs_dir/Simulations"
        m2m_dir="$simnibs_dir/m2m_$subject_id"
        
        echo -e "${CYAN}Subject directory: $subject_dir${RESET}"
        echo -e "${CYAN}Simulation directory: $simulation_dir${RESET}"
        echo -e "${CYAN}m2m directory: $m2m_dir${RESET}"
        
        # Verify m2m directory exists
        if [ ! -d "$m2m_dir" ]; then
            echo -e "${RED}Error: m2m directory doesn't exist: $m2m_dir${RESET}"
            continue
        fi
        
        # Create simulation directory if it doesn't exist
        mkdir -p "$simulation_dir"
        chmod 777 "$simulation_dir"
        
        # Export variables for TI.py to find the correct config directory
        export CONFIG_DIR="$ti_csc_dir/config"
        
        # Set electrode parameters
        electrode_shape="${ELECTRODE_SHAPE:-rect}"
        dimensions="${DIMENSIONS:-50,50}"
        thickness="${THICKNESS:-5}"
        current="${CURRENT:-2.0,2.0}"
        
        # Build command - use project_dir instead of subject_dir to prevent double subject ID
        cmd=("$simulator_dir/$main_script" "$subject_id" "$conductivity" "$project_dir" "$simulation_dir" "$sim_mode" "$current" "$electrode_shape" "$dimensions" "$thickness" "$eeg_net")
        
        # Add montages - ensure these are actual montage names
        for montage in "${selected_montages[@]}"; do
            # Skip if montage name looks like a path or option
            if [[ $montage == /* || $montage == -* ]]; then
                echo -e "${YELLOW}Warning: Skipping invalid montage name: $montage${RESET}"
                continue
            fi
            cmd+=("$montage")
        done
        
        # Add end marker
        cmd+=("--")
        
        echo -e "${GREEN}Executing: ${cmd[*]}${RESET}"
        echo -e "${CYAN}Command breakdown:${RESET}"
        echo -e "${CYAN}- Script: $simulator_dir/$main_script${RESET}"
        echo -e "${CYAN}- Subject ID: $subject_id${RESET}"
        echo -e "${CYAN}- Conductivity: $conductivity${RESET}"
        echo -e "${CYAN}- Project directory: $project_dir${RESET}"
        echo -e "${CYAN}- Simulation directory: $simulation_dir${RESET}"
        echo -e "${CYAN}- Simulation mode: $sim_mode${RESET}"
        echo -e "${CYAN}- Current (channels): $current${RESET}"
        echo -e "${CYAN}- Electrode shape: $electrode_shape${RESET}"
        echo -e "${CYAN}- Dimensions: $dimensions mm${RESET}"
        echo -e "${CYAN}- Thickness: $thickness mm${RESET}"
        echo -e "${CYAN}- Montages: ${selected_montages[*]}${RESET}"
        
        # Execute simulation
        "${cmd[@]}"
        
        # Check execution status
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}Simulation completed successfully for subject: $subject_id${RESET}"
        else
            echo -e "${RED}Simulation failed for subject: $subject_id${RESET}"
        fi
    done
    
    # Skip report generation in direct mode - GUI will handle it
    if [[ "$is_direct_mode" != "true" ]]; then
        echo -e "${CYAN}Generating simulation reports...${RESET}"
        
        # Check if we have Python available
        python_cmd=""
        if command -v python3 &> /dev/null; then
            python_cmd="python3"
        elif command -v python &> /dev/null; then
            python_cmd="python"
        else
            echo -e "${YELLOW}Warning: Python not found. Skipping report generation.${RESET}"
            return
        fi
        
        # Path to the report generator
        report_generator_path="$script_dir/../GUI/simulation_report_generator.py"
        
        if [ ! -f "$report_generator_path" ]; then
            echo -e "${YELLOW}Warning: Simulation report generator not found. Skipping report generation.${RESET}"
            return
        fi
        
        # Generate reports for each processed subject
        reports_generated=0
        for subject_num in "${selected_subjects[@]}"; do
            subject_id="$subject_num"  # In direct mode, use subject IDs directly
            
            echo -e "${CYAN}Generating report for subject: $subject_id${RESET}"
            
            # Create a temporary Python script to generate the report
            temp_script=$(mktemp)
            cat > "$temp_script" << EOF
#!/usr/bin/env python3
import sys
import os
sys.path.append('$script_dir/../GUI')

from simulation_report_generator import SimulationReportGenerator
import datetime

try:
    # Initialize report generator
    session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_gen = SimulationReportGenerator('$project_dir', session_id)
    
    # Add simulation parameters
    current_parts = '$current'.split(',')
    current_1 = float(current_parts[0]) * 1000 if len(current_parts) > 0 else 1.0  # Convert A to mA
    current_2 = float(current_parts[1]) * 1000 if len(current_parts) > 1 else 1.0  # Convert A to mA
    
    report_gen.add_simulation_parameters(
        '$conductivity', '$sim_mode', '$eeg_net', 
        current_1, current_2, False
    )
    
    # Add electrode parameters
    dimensions = '$dimensions'.split(',')
    report_gen.add_electrode_parameters(
        '$electrode_shape', [float(dimensions[0]), float(dimensions[1])], float('$thickness')
    )
    
    # Add subject
    m2m_path = os.path.join('$project_dir', 'derivatives', 'SimNIBS', 'sub-$subject_id', 'm2m_$subject_id')
    report_gen.add_subject('$subject_id', m2m_path, 'completed')
    
    # Add montages
    montage_type = 'unipolar' if '$sim_mode' == 'U' else 'multipolar'
    montages = [$(printf "'%s'," "${selected_montages[@]}" | sed 's/,$//')]
    for montage in montages:
        if montage and montage != '--':  # Skip empty montages and end marker
            report_gen.add_montage(montage, [['E1', 'E2']], montage_type)
    
    # Generate report
    report_path = report_gen.generate_report()
    if report_path:
        print(f"✅ Report generated: {report_path}")
    else:
        print("❌ Failed to generate report")
        
except Exception as e:
    print(f"❌ Error generating report: {str(e)}")
    import traceback
    traceback.print_exc()
EOF
            
            # Run the report generation
            if $python_cmd "$temp_script"; then
                ((reports_generated++))
            fi
            
            # Clean up temporary script
            rm -f "$temp_script"
        done
        
        # Summary
        if [ $reports_generated -gt 0 ]; then
            echo -e "${GREEN}✅ Generated $reports_generated simulation report(s)${RESET}"
            echo -e "${CYAN}Reports saved to: $project_dir/derivatives/reports/${RESET}"
        else
            echo -e "${YELLOW}⚠️ No reports were generated${RESET}"
        fi
    fi
}

# Check if direct execution from GUI is requested
if [[ "$1" == "--run-direct" ]]; then
    echo "Running in direct execution mode from GUI"
    
    # Set direct mode flag
    export DIRECT_MODE=true
    
    # Check for required environment variables
    if [[ -z "$SUBJECTS" || -z "$CONDUCTIVITY" || -z "$SIM_MODE" || -z "$SELECTED_MONTAGES" || -z "$EEG_NET" ]]; then
        echo -e "${RED}Error: Missing required environment variables for direct execution.${RESET}"
        echo "Required: SUBJECTS, CONDUCTIVITY, SIM_MODE, SELECTED_MONTAGES, EEG_NET"
        exit 1
    fi
    
    # Set variables from environment without prompting
    subject_choices="$SUBJECTS"
    conductivity="$CONDUCTIVITY"
    sim_mode="$SIM_MODE"
    eeg_net="$EEG_NET"
    
    # Set up mode-specific variables
    if [[ "$sim_mode" == "U" ]]; then
        montage_type="uni_polar_montages"
        main_script="main-TI.sh"
        montage_type_text="Unipolar"
    elif [[ "$sim_mode" == "M" ]]; then
        montage_type="multi_polar_montages"
        main_script="main-mTI.sh"
        montage_type_text="Multipolar"
    fi
    
    # Parse selected montages
    selected_montages=($SELECTED_MONTAGES)
    
    # Set electrode parameters
    electrode_shape="${ELECTRODE_SHAPE:-rect}"
    dimensions="${DIMENSIONS:-50,50}"
    thickness="${THICKNESS:-5}"
    current="${CURRENT:-2.0,2.0}"
    
    # Skip to execution
    echo "Running simulation with:"
    echo "  - Subjects: $subject_choices"
    echo "  - Simulation type: $conductivity"
    echo "  - Mode: $montage_type_text"
    echo "  - EEG Net: $eeg_net"
    echo "  - Montages: ${selected_montages[*]}"
    echo "  - Electrode shape: $electrode_shape"
    echo "  - Dimensions: $dimensions mm"
    echo "  - Thickness: $thickness mm" 
    echo "  - Current (channels): $current A"
    
    # List available subjects to set the subjects array
    list_subjects
    
    # Jump directly to execution
    run_simulation "--run-direct"
    exit 0
fi

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

# Ensure ti-csc directory exists and set permissions
if [ ! -d "$ti_csc_dir" ]; then
    mkdir -p "$ti_csc_dir"
    chmod 777 "$ti_csc_dir"
    echo -e "${GREEN}Created ti-csc directory at $ti_csc_dir with permissions 777.${RESET}"
else
    chmod 777 "$ti_csc_dir"
fi

# Function to validate electrode pair input
validate_pair() {
    local pair=$1
    # Split the input by comma and count parts
    IFS=',' read -ra parts <<< "$pair"
    if [ ${#parts[@]} -ne 2 ] || [ -z "${parts[0]}" ] || [ -z "${parts[1]}" ]; then
        echo -e "${RED}Invalid format. Please enter two inputs separated by a comma (e.g., x,y or Fp1,Fp2 or E010,E020).${RESET}"
        return 1
    fi
    return 0
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
        # Get the montages for the selected net and mode
        if [[ "$sim_mode" == "U" ]]; then
            montage_type="uni_polar_montages"
            montage_type_text="Unipolar"
        else
            montage_type="multi_polar_montages"
            montage_type_text="Multipolar"
        fi

        # Get montages for the current subject's net
        montage_data=$(jq -r --arg net "$selected_eeg_net" --arg type "$montage_type" '.nets[$net][$type] // empty' "$montage_file")
        
        if [ -z "$montage_data" ] || [ "$montage_data" == "null" ]; then
            echo -e "${YELLOW}No montages found for net $selected_eeg_net. Creating new entry.${RESET}"
            # Initialize empty montage list for this net and type if it doesn't exist
            jq --arg net "$selected_eeg_net" --arg type "$montage_type" \
               'if .nets[$net] then . else .nets[$net] = {($type): {}} end' "$montage_file" > temp.json && mv temp.json "$montage_file"
            montage_data="{}"
        fi

        montage_names=($(echo "$montage_data" | jq -r 'keys[]'))
        total_montages=${#montage_names[@]}

        echo -e "${BOLD_CYAN}Available Montages for $selected_eeg_net (${montage_type_text}):${RESET}"
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

                # Add new montage to the correct net and type
                new_montage=$(jq -n --arg name "$new_montage_name" --argjson pairs "[[\"${pair1//,/\",\"}\"], [\"${pair2//,/\",\"}\"]]" '{($name): $pairs}')
                jq --arg net "$selected_eeg_net" --arg type "$montage_type" --argjson montage "$new_montage" \
                   '.nets[$net][$type] += $montage' "$montage_file" > temp.json && mv temp.json "$montage_file"
                chmod 777 "$montage_file"
                echo -e "${GREEN}New montage '$new_montage_name' added successfully for net $selected_eeg_net.${RESET}"
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

# Choose electrode shape
choose_electrode_shape() {
    if ! is_prompt_enabled "electrode_shape"; then
        local default_shape=$(get_default_value "electrode_shape")
        if [ -n "$default_shape" ]; then
            electrode_shape="$default_shape"
            echo -e "${CYAN}Using default electrode shape: $electrode_shape${RESET}"
            return
        fi
    fi

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

# Choose electrode dimensions
choose_electrode_dimensions() {
    if ! is_prompt_enabled "electrode_dimensions"; then
        local default_dims=$(get_default_value "electrode_dimensions")
        if [ -n "$default_dims" ]; then
            dimensions="$default_dims"
            echo -e "${CYAN}Using default electrode dimensions: $dimensions mm${RESET}"
            return
        fi
    fi

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

# Choose electrode thickness
choose_electrode_thickness() {
    if ! is_prompt_enabled "electrode_thickness"; then
        local default_thick=$(get_default_value "electrode_thickness")
        if [ -n "$default_thick" ]; then
            thickness="$default_thick"
            echo -e "${CYAN}Using default electrode thickness: $thickness mm${RESET}"
            return
        fi
    fi

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

# Function to show welcome message
show_welcome_message() {
    clear  # Clear the screen before starting
    echo -e "${BOLD_CYAN}╔════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD_CYAN}║        TI-CSC Simulator Tool          ║${RESET}"
    echo -e "${BOLD_CYAN}╚════════════════════════════════════════╝${RESET}"
    echo -e "${CYAN}Version 2.0 - $(date +%Y)${RESET}"
    echo -e "${CYAN}Run simulations with customizable electrode configurations${RESET}\n"
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
        local current_subject="${subjects[$((num-1))]}"
        subject_list+="${current_subject} (EEG Net: ${subject_eeg_nets[$current_subject]:-EGI_template.csv})"
    done
    echo -e "Subjects: ${CYAN}$subject_list${RESET}"
    
    # Simulation Parameters
    echo -e "\n${BOLD_CYAN}Simulation Parameters:${RESET}"
    echo -e "Simulation Type: ${CYAN}${sim_type_text}${RESET}"
    echo -e "Mode: ${CYAN}${montage_type_text}${RESET}"
    echo -e "Selected Montages: ${CYAN}${selected_montages[*]}${RESET}"
    
    # Electrode Configuration
    echo -e "\n${BOLD_CYAN}Electrode Configuration:${RESET}"
    echo -e "Shape: ${CYAN}${electrode_shape}${RESET}"
    echo -e "Dimensions: ${CYAN}${dimensions} mm${RESET}"
    echo -e "Thickness: ${CYAN}${thickness} mm${RESET}"
    echo -e "Current (channels): ${CYAN}${current}${RESET}"
    
    echo -e "\n${BOLD_YELLOW}Please review the configuration above.${RESET}"
    echo -e "${YELLOW}Do you want to proceed with the simulation? (y/n)${RESET}"
    read -p " " confirm
    
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo -e "${RED}Simulation cancelled by user.${RESET}"
        exit 0
    fi
}

# Choose EEG net for a subject
choose_eeg_net() {
    local subject_id=$1
    local derivatives_dir="$project_dir/derivatives"
    local simnibs_dir="$derivatives_dir/SimNIBS/sub-$subject_id"
    local m2m_dir="$simnibs_dir/m2m_${subject_id}"
    local eeg_dir="$m2m_dir/eeg_positions"
    
    # Check if eeg_positions directory exists
    if [ ! -d "$eeg_dir" ]; then
        echo -e "${RED}Error: EEG positions directory not found at $eeg_dir${RESET}"
        echo -e "${YELLOW}Using default EGI_template.csv${RESET}"
        selected_eeg_net="EGI_template.csv"
        return
    fi
    
    # Find all CSV files in the directory
    local csv_files=()
    while IFS= read -r -d '' file; do
        csv_files+=("$(basename "$file")")
    done < <(find "$eeg_dir" -name "*.csv" -print0)
    
    # Check if any CSV files were found
    if [ ${#csv_files[@]} -eq 0 ]; then
        echo -e "${YELLOW}No EEG net files found in $eeg_dir. Using default EGI_template.csv${RESET}"
        selected_eeg_net="EGI_template.csv"
        return
    fi
    
    # Display available EEG nets
    echo -e "${BOLD_CYAN}Available EEG nets:${RESET}"
    echo "-------------------"
    for i in "${!csv_files[@]}"; do
        printf "%3d. %s\n" $((i+1)) "${csv_files[i]}"
    done
    echo
    
    # Prompt user to select an EEG net
    local valid_selection=false
    until $valid_selection; do
        read -p "Select an EEG net (1-${#csv_files[@]}): " selection
        if [[ "$selection" =~ ^[0-9]+$ ]] && [ "$selection" -ge 1 ] && [ "$selection" -le "${#csv_files[@]}" ]; then
            selected_eeg_net="${csv_files[$((selection-1))]}"
            valid_selection=true
        else
            echo -e "${RED}Invalid selection. Please try again.${RESET}"
        fi
    done
    
    echo -e "${GREEN}Selected EEG net: $selected_eeg_net${RESET}"
}

# Function to choose tissue conductivities
choose_tissue_conductivities() {
    # Define tissue conductivity defaults
    declare -A tissue_defaults=(
        ["White Matter"]=0.126
        ["Gray Matter"]=0.275
        ["CSF"]=1.654
        ["Bone"]=0.01
        ["Scalp"]=0.465
        ["Eye balls"]=0.5
        ["Compact Bone"]=0.008
        ["Spongy Bone"]=0.025
        ["Blood"]=0.6
        ["Muscle"]=0.16
        ["Silicone Rubber"]=29.4
        ["Saline"]=1.0
    )

    declare -A tissue_numbers=(
        ["White Matter"]=1
        ["Gray Matter"]=2
        ["CSF"]=3
        ["Bone"]=4
        ["Scalp"]=5
        ["Eye balls"]=6
        ["Compact Bone"]=7
        ["Spongy Bone"]=8
        ["Blood"]=9
        ["Muscle"]=10
        ["Silicone Rubber"]=100
        ["Saline"]=500
    )

    # Initialize empty array for custom conductivities
    declare -A custom_conductivities

    while true; do
        echo -e "\n${BOLD_CYAN}Tissue Conductivity Settings${RESET}"
        echo -e "----------------------------------------"
        echo -e "${BOLD}Available Tissues:${RESET}\n"
        
        # Display all tissues with their current values
        local i=1
        for tissue in "${!tissue_defaults[@]}"; do
            local current_value=${custom_conductivities[$tissue]:-${tissue_defaults[$tissue]}}
            local tissue_num=${tissue_numbers[$tissue]}
            printf "%2d. %-20s [%3d] Current: %7.3f S/m\n" $i "$tissue" "$tissue_num" "$current_value"
            ((i++))
        done

        echo -e "\n${GREEN}Enter tissue number to modify (or 0 to continue):${RESET}"
        read -p " " selection

        if [[ "$selection" == "0" ]]; then
            break
        fi

        if [[ "$selection" =~ ^[0-9]+$ ]] && [ "$selection" -ge 1 ] && [ "$selection" -le "${#tissue_defaults[@]}" ]; then
            local tissue_name=$(echo "${!tissue_defaults[@]}" | tr ' ' '\n' | sed -n "${selection}p")
            local current_value=${tissue_defaults[$tissue_name]}
            
            echo -e "\n${CYAN}Current conductivity for $tissue_name: $current_value S/m${RESET}"
            echo -e "${GREEN}Enter new conductivity value (S/m) or press enter to keep current:${RESET}"
            read -p " " new_value

            if [[ "$new_value" =~ ^[0-9]*\.?[0-9]+$ ]]; then
                custom_conductivities[$tissue_name]=$new_value
                echo -e "${GREEN}Updated conductivity for $tissue_name to $new_value S/m${RESET}"
            elif [ -z "$new_value" ]; then
                echo -e "${YELLOW}Keeping current value${RESET}"
            else
                echo -e "${RED}Invalid input. Please enter a valid number.${RESET}"
            fi
        else
            echo -e "${RED}Invalid selection. Please try again.${RESET}"
        fi
    done

    # Export the custom conductivities as environment variables for the Python scripts
    for tissue in "${!custom_conductivities[@]}"; do
        local tissue_num=${tissue_numbers[$tissue]}
        export "TISSUE_COND_${tissue_num}=${custom_conductivities[$tissue]}"
    done
}

# Main script execution
show_welcome_message

# Collect all necessary inputs in the specified order
choose_subjects
choose_simulation_type
choose_simulation_mode
choose_tissue_conductivities

# For each selected subject, choose an EEG net
declare -A subject_eeg_nets
for subject_num in "${selected_subjects[@]}"; do
    subject_id="${subjects[$((subject_num-1))]}"
    echo -e "\n${BOLD_CYAN}Selecting EEG net for subject: $subject_id${RESET}"
    choose_eeg_net "$subject_id"
    subject_eeg_nets["$subject_id"]="$selected_eeg_net"
done

prompt_montages
choose_electrode_shape
choose_electrode_dimensions
choose_electrode_thickness
choose_intensity

# Show confirmation dialog before proceeding
show_confirmation_dialog

# Loop through selected subjects and run the pipeline
for subject_num in "${selected_subjects[@]}"; do
    subject_id="${subjects[$((subject_num-1))]}"
    subject_dir="$project_dir/sub-$subject_id"
    simulation_dir="$subject_dir/SimNIBS/Simulations"
    eeg_net="${subject_eeg_nets[$subject_id]:-EGI_template.csv}"  # Use default if not set

    # Create simulation directory if it doesn't exist
    mkdir -p "$simulation_dir"

    # Call the appropriate main pipeline script with the gathered parameters
    "$simulator_dir/$main_script" "$subject_id" "$conductivity" "$project_dir" "$simulation_dir" "$sim_mode" "$current" "$electrode_shape" "$dimensions" "$thickness" "$eeg_net" "${selected_montages[@]}" -- "${selected_roi_names[@]}"
done

# Output success message if new montages or ROIs were added
if [ "$new_montage_added" = true ]; then
    echo -e "${GREEN}New montage added to montage_list.json.${RESET}"
fi

echo -e "${GREEN}All tasks completed successfully.${RESET}"

# Generate simulation reports automatically
echo -e "${CYAN}Generating simulation reports...${RESET}"

# Check if we have Python available and the report generator
python_cmd=""
if command -v python3 &> /dev/null; then
    python_cmd="python3"
elif command -v python &> /dev/null; then
    python_cmd="python"
else
    echo -e "${YELLOW}Warning: Python not found. Skipping report generation.${RESET}"
    exit 0
fi

# Path to the report generator
report_generator_path="$script_dir/../GUI/simulation_report_generator.py"

if [ ! -f "$report_generator_path" ]; then
    echo -e "${YELLOW}Warning: Simulation report generator not found. Skipping report generation.${RESET}"
    exit 0
fi

# Generate reports for each processed subject
reports_generated=0
for subject_num in "${selected_subjects[@]}"; do
    if [[ "$is_direct_mode" == "true" ]]; then
        subject_id="$subject_num"
    else
        subject_id="${subjects[$((subject_num-1))]}"
    fi
    
    echo -e "${CYAN}Generating report for subject: $subject_id${RESET}"
    
    # Create a temporary Python script to generate the report
    temp_script=$(mktemp)
    cat > "$temp_script" << EOF
#!/usr/bin/env python3
import sys
import os
sys.path.append('$script_dir/../GUI')

from simulation_report_generator import SimulationReportGenerator
import datetime

try:
    # Initialize report generator
    session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_gen = SimulationReportGenerator('$project_dir', session_id)
    
    # Add simulation parameters
    current_parts = '$current'.split(',')
    current_1 = float(current_parts[0]) * 1000 if len(current_parts) > 0 else 1.0  # Convert A to mA
    current_2 = float(current_parts[1]) * 1000 if len(current_parts) > 1 else 1.0  # Convert A to mA
    
    # Collect custom conductivities from environment variables
    import os
    custom_conductivities = {}
    for env_var in os.environ:
        if env_var.startswith('TISSUE_COND_'):
            tissue_num = int(env_var.replace('TISSUE_COND_', ''))
            conductivity_value = float(os.environ[env_var])
            custom_conductivities[tissue_num] = conductivity_value
    
    report_gen.add_simulation_parameters(
        '$conductivity', '$sim_mode', '${subject_eeg_nets[$subject_id]:-EGI_template.csv}', 
        current_1, current_2, False,  # Use actual current values from CLI
        conductivities=custom_conductivities if custom_conductivities else None
    )
    
    # Add electrode parameters
    dimensions = '$dimensions'.split(',')
    report_gen.add_electrode_parameters(
        '$electrode_shape', [float(dimensions[0]), float(dimensions[1])], float('$thickness')
    )
    
    # Add subject
    m2m_path = os.path.join('$project_dir', 'derivatives', 'SimNIBS', 'sub-$subject_id', 'm2m_$subject_id')
    report_gen.add_subject('$subject_id', m2m_path, 'completed')
    
    # Add montages
    montage_type = 'unipolar' if '$sim_mode' == 'U' else 'multipolar'
    montages = [$(printf "'%s'," "${selected_montages[@]}" | sed 's/,$//')]
    for montage in montages:
        if montage:  # Skip empty montages
            report_gen.add_montage(montage, [['E1', 'E2']], montage_type)
    
    # Generate report
    report_path = report_gen.generate_report()
    if report_path:
        print(f"✅ Report generated: {report_path}")
    else:
        print("❌ Failed to generate report")
        
except Exception as e:
    print(f"❌ Error generating report: {str(e)}")
    import traceback
    traceback.print_exc()
EOF
    
    # Run the report generation
    if $python_cmd "$temp_script"; then
        ((reports_generated++))
    fi
    
    # Clean up temporary script
    rm -f "$temp_script"
done

# Summary
if [ $reports_generated -gt 0 ]; then
    echo -e "${GREEN}✅ Generated $reports_generated simulation report(s)${RESET}"
    echo -e "${CYAN}Reports saved to: $project_dir/derivatives/reports/${RESET}"
else
    echo -e "${YELLOW}⚠️ No reports were generated${RESET}"
fi
