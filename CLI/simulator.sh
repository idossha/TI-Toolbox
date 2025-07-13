#!/bin/bash

###########################################
# Ido Haber / ihaber@wisc.edu
# June, 2025
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
        # Ensure FLEX_MONTAGES_FILE is available to child processes
        export FLEX_MONTAGES_FILE
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
        
        # Source the reporting utilities
        reporting_script="$script_dir/../utils/bash_reporting.sh"
        if [ -f "$reporting_script" ]; then
            source "$reporting_script"
            
            # Initialize reporting
            init_reporting "$project_dir"
            
            # Generate reports for each processed subject
            reports_generated=0
            for subject_num in "${selected_subjects[@]}"; do
                if [[ "$is_direct_mode" == "true" ]]; then
                    subject_id="$subject_num"
                else
                    subject_id="${subjects[$((subject_num-1))]}"
                fi
                
                echo -e "${CYAN}Generating report for subject: $subject_id${RESET}"
                
                # Create a unique simulation session ID for this CLI run
                cli_session_id="CLI_$(date +%Y%m%d_%H%M%S)"
                
                # Check for completion reports from this session
                completion_files=()
                temp_dir="$project_dir/derivatives/temp"
                if [[ -d "$temp_dir" ]]; then
                    # Look for completion files from this subject
                    while IFS= read -r -d '' completion_file; do
                        completion_files+=("$completion_file")
                    done < <(find "$temp_dir" -name "simulation_completion_${subject_id}_*.json" -print0 2>/dev/null)
                fi
                
                # Generate Python script to create CLI report
                temp_script=$(mktemp "${TMPDIR:-/tmp}/cli_report_XXXXXX.py")
                cat > "$temp_script" <<EOF
#!/usr/bin/env python3
import sys
import os
import json
import datetime

# Add utils to path
sys.path.insert(0, '$script_dir/../utils')
from simulation_report_generator import SimulationReportGenerator

project_dir = '$project_dir'
subject_id = '$subject_id'
session_id = '$cli_session_id'

try:
    # Create report generator
    generator = SimulationReportGenerator(project_dir, session_id)
    
    # Add simulation parameters (basic defaults for CLI)
    generator.add_simulation_parameters(
        conductivity_type='$conductivity',
        simulation_mode='$sim_mode',
        eeg_net='${subject_eeg_nets[$subject_id]:-EGI_template.csv}',
        intensity_ch1=${current_ma_1:-5.0},
        intensity_ch2=${current_ma_2:-1.0},
        quiet_mode=False
    )
    
    # Add electrode parameters
    dimensions_list = '$dimensions'.split(',')
    generator.add_electrode_parameters(
        shape='$electrode_shape',
        dimensions=[float(dimensions_list[0]), float(dimensions_list[1])],
        thickness=float('$thickness')
    )
    
    # Add subject
    bids_subject_id = f"sub-{subject_id}"
    m2m_path = os.path.join(project_dir, 'derivatives', 'SimNIBS', bids_subject_id, f'm2m_{subject_id}')
    generator.add_subject(subject_id, m2m_path, 'completed')
    
    # Process any completion reports
    completion_files = ${completion_files[@]@Q}
    for completion_file in completion_files:
        if os.path.exists(completion_file):
            with open(completion_file, 'r') as f:
                completion_data = json.load(f)
            
            # Add simulation results for each completed simulation
            for sim in completion_data.get('completed_simulations', []):
                montage_name = sim['montage_name']
                
                # Add montage info
                generator.add_montage(
                    montage_name=montage_name,
                    electrode_pairs=[['E1', 'E2'], ['E3', 'E4']],  # Default pairs
                    montage_type='unipolar' if '$sim_mode' == 'U' else 'multipolar'
                )
                
                # Get expected output files
                simulations_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', bids_subject_id, 'Simulations', montage_name)
                ti_dir = os.path.join(simulations_dir, 'TI')
                nifti_dir = os.path.join(ti_dir, 'niftis')
                
                output_files = {'TI': [], 'niftis': []}
                if os.path.exists(nifti_dir):
                    nifti_files = [f for f in os.listdir(nifti_dir) if f.endswith('.nii.gz')]
                    output_files['niftis'] = [os.path.join(nifti_dir, f) for f in nifti_files]
                    ti_files = [f for f in nifti_files if 'TI_max' in f]
                    output_files['TI'] = [os.path.join(nifti_dir, f) for f in ti_files]
                
                # Add simulation result
                generator.add_simulation_result(
                    subject_id=subject_id,
                    montage_name=montage_name,
                    output_files=output_files,
                    duration=None,
                    status='completed'
                )
            
            # Clean up completion report
            os.remove(completion_file)
    
    # Generate report
    report_path = generator.generate_report()
    print(f"✅ CLI Report generated: {report_path}")
    
except Exception as e:
    print(f"❌ Error generating CLI report: {str(e)}")
    import traceback
    traceback.print_exc()
EOF
                
                # Run the report generation
                if python3 "$temp_script"; then
                    ((reports_generated++))
                fi
                
                # Clean up temporary script
                rm -f "$temp_script"
            done
            
            # Summary
            if [ $reports_generated -gt 0 ]; then
                echo -e "${GREEN}✅ Generated $reports_generated simulation report(s)${RESET}"
                echo -e "${CYAN}Reports saved to: $project_dir/derivatives/reports/sub-{subjectID}/${RESET}"
            else
                echo -e "${YELLOW}⚠️ No reports were generated${RESET}"
            fi
        else
            echo -e "${YELLOW}⚠️ Reporting utilities not found. Skipping report generation.${RESET}"
        fi

        # Clean up temporary flex montages file
if [[ -n "$temp_flex_file" && -f "$temp_flex_file" ]]; then
    rm -f "$temp_flex_file"
    echo -e "${CYAN}Cleaned up temporary flex montages file${RESET}"
fi

# Clean up simulation completion files (interactive mode)
cleanup_completion_files

    fi

} # Close run_simulation function

# Function to parse flex-search names into proper format
parse_flex_search_name() {
    local search_name="$1"
    local electrode_type="$2"
    
    # Handle new cortical search format: lh_DK40_14_mean_maxTI
    if [[ "$search_name" == lh_* ]] || [[ "$search_name" == rh_* ]]; then
        IFS='_' read -ra parts <<< "$search_name"
        if [ ${#parts[@]} -ge 5 ]; then
            local hemisphere="${parts[0]}"      # e.g., 'lh'
            local atlas="${parts[1]}"           # e.g., 'DK40'
            local region="${parts[2]}"          # e.g., '14'
            local goal="${parts[3]}"            # e.g., 'mean'
            local post_proc="${parts[4]}"       # e.g., 'maxTI'
            
            echo "flex_${hemisphere}_${atlas}_${region}_${goal}_${post_proc}_${electrode_type}"
            return
        fi
    fi
    
    # Handle legacy cortical search format: lh.101_DK40_14_mean (for backward compatibility)
    if [[ "$search_name" == lh.* ]] || [[ "$search_name" == rh.* ]]; then
        IFS='_' read -ra parts <<< "$search_name"
        if [ ${#parts[@]} -ge 3 ]; then
            local hemisphere_region="${parts[0]}"
            local atlas="${parts[1]}"
            local goal_postproc="${parts[*]:2}"
            goal_postproc="${goal_postproc// /_}"
            
            # Extract hemisphere and region
            if [[ "$hemisphere_region" == *"."* ]]; then
                local hemisphere="${hemisphere_region%.*}"
                local region="${hemisphere_region#*.}"
            else
                local hemisphere="unknown"
                local region="$hemisphere_region"
            fi
            
            # Split goal and postProc if possible
            if [[ "$goal_postproc" == *"_"* ]]; then
                local goal="${goal_postproc%%_*}"
                local post_proc="${goal_postproc#*_}"
            else
                local goal="$goal_postproc"
                local post_proc="default"
            fi
            
            echo "flex_${hemisphere}_${atlas}_${region}_${goal}_${post_proc}_${electrode_type}"
            return
        fi
    fi
    
    # Handle new subcortical search format: subcortical_atlas_region_goal_postprocess
    if [[ "$search_name" == subcortical_* ]]; then
        IFS='_' read -ra parts <<< "$search_name"
        if [ ${#parts[@]} -ge 5 ]; then
            local hemisphere="subcortical"
            local atlas="${parts[1]}"
            local region="${parts[2]}"
            local goal="${parts[3]}"
            local post_proc="${parts[4]}"
            
            echo "flex_${hemisphere}_${atlas}_${region}_${goal}_${post_proc}_${electrode_type}"
            return
        fi
    fi
    
    # Handle new spherical search format: sphere_x0y0z0r10_mean_normalTI
    if [[ "$search_name" == sphere_* ]]; then
        IFS='_' read -ra parts <<< "$search_name"
        if [ ${#parts[@]} -ge 4 ]; then
            local hemisphere="spherical"
            local coordinates="${parts[1]}"     # e.g., 'x0y0z0r10'
            local goal="${parts[2]}"            # e.g., 'mean'
            local post_proc="${parts[3]}"       # e.g., 'normalTI'
            
            echo "flex_${hemisphere}_coordinates_${coordinates}_${goal}_${post_proc}_${electrode_type}"
            return
        fi
    fi
    
    # Legacy spherical coordinates or other formats (for backward compatibility)
    if [[ "$search_name" == *"_"* ]] && [[ "$search_name" =~ [0-9] ]]; then
        IFS='_' read -ra parts <<< "$search_name"
        local hemisphere="spherical"
        local atlas="coordinates"
        local region="${parts[*]:0:$((${#parts[@]}-1))}"
        region="${region// /_}"
        local goal="${parts[-1]}"
        [ -z "$goal" ] && goal="optimization"
        local post_proc="default"
        
        echo "flex_${hemisphere}_${atlas}_${region}_${goal}_${post_proc}_${electrode_type}"
        return
    fi
    
    # Fallback for unrecognized formats
    echo "flex_unknown_unknown_${search_name}_optimization_default_${electrode_type}"
}

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

# Choose between regular montage and flex-search simulation
choose_simulation_framework() {
    if ! is_prompt_enabled "simulation_framework"; then
        local default_value=$(get_default_value "simulation_framework")
        if [ -n "$default_value" ]; then
            simulation_framework="$default_value"
            echo -e "${CYAN}Using default simulation framework: $simulation_framework${RESET}"
            return
        fi
    fi

    echo -e "${GREEN}Choose simulation framework:${RESET}"
    echo "1. Montage Simulation (traditional electrode placement)"
    echo "2. Flex-Search Simulation (from optimization results)"
    
    while true; do
        read -p "Enter your choice (1 or 2): " framework_choice
        if [[ "$framework_choice" == "1" ]]; then
            simulation_framework="montage"
            export SIMULATION_MODE="MONTAGE"
            break
        elif [[ "$framework_choice" == "2" ]]; then
            simulation_framework="flex"
            export SIMULATION_MODE="FLEX"
            break
        else
            reprompt
        fi
    done
}

# Choose simulation mode with configuration support
choose_simulation_mode() {
    if [[ "$simulation_framework" == "flex" ]]; then
        # For flex-search, always use FLEX_TI mode
        sim_mode="FLEX_TI"
        montage_type="flex_temporal_interference"
        main_script="main-TI.sh"
        montage_type_text="Flex-Search TI"
        echo -e "${CYAN}Using Flex-Search TI mode${RESET}"
        return
    fi

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

# Choose flex-search outputs and electrode types
choose_flex_search_outputs() {
    if ! is_prompt_enabled "flex_outputs"; then
        local default_value=$(get_default_value "flex_outputs")
        if [ -n "$default_value" ]; then
            selected_flex_outputs=($default_value)
            echo -e "${CYAN}Using default flex-search outputs: ${selected_flex_outputs[*]}${RESET}"
            return
        fi
    fi

    echo -e "${BOLD_CYAN}Available Flex-Search Outputs:${RESET}"
    echo "----------------------------------------"
    
    # Find all flex-search outputs for selected subjects
    local flex_outputs=()
    local flex_output_paths=()
    local flex_output_details=()
    
    for subject_num in "${selected_subjects[@]}"; do
        local subject_id="${subjects[$((subject_num-1))]}"
        local flex_search_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/flex-search"
        
        if [ -d "$flex_search_dir" ]; then
            for search_dir in "$flex_search_dir"/*; do
                if [ -d "$search_dir" ]; then
                    local search_name=$(basename "$search_dir")
                    local mapping_file="$search_dir/electrode_mapping.json"
                    
                    if [ -f "$mapping_file" ]; then
                        # Parse JSON to get details
                        local details=$(python3 -c "
import json
import sys
try:
    with open('$mapping_file', 'r') as f:
        data = json.load(f)
    eeg_net = data.get('eeg_net', 'Unknown')
    n_electrodes = len(data.get('optimized_positions', []))
    print(f'{n_electrodes} electrodes | {eeg_net}')
except:
    print('Unable to parse')
")
                        
                        flex_outputs+=("$subject_id | $search_name")
                        flex_output_paths+=("$mapping_file")
                        flex_output_details+=("$details")
                    fi
                fi
            done
        fi
    done
    
    if [ ${#flex_outputs[@]} -eq 0 ]; then
        echo -e "${RED}No flex-search outputs found for selected subjects${RESET}"
        echo -e "${YELLOW}Please run flex-search optimization first${RESET}"
        exit 1
    fi
    
    # Display available outputs
    for i in "${!flex_outputs[@]}"; do
        printf "%3d. %-40s | %s\n" $((i+1)) "${flex_outputs[i]}" "${flex_output_details[i]}"
    done
    echo
    
    # Choose outputs
    read -p "Enter the numbers of the flex-search outputs to simulate (comma-separated): " flex_choices
    if [[ ! "$flex_choices" =~ ^[0-9,]+$ ]]; then
        echo -e "${RED}Invalid input. Please enter numbers separated by commas.${RESET}"
        choose_flex_search_outputs
        return
    fi
    
    IFS=',' read -r -a selected_numbers <<< "$flex_choices"
    selected_flex_outputs=()
    selected_flex_paths=()
    
    for number in "${selected_numbers[@]}"; do
        if (( number > 0 && number <= ${#flex_outputs[@]} )); then
            selected_flex_outputs+=("${flex_outputs[$((number - 1))]}")
            selected_flex_paths+=("${flex_output_paths[$((number - 1))]}")
        else
            echo -e "${RED}Invalid output number: $number. Please try again.${RESET}"
            choose_flex_search_outputs
            return
        fi
    done
    
    # Choose electrode types
    echo -e "\n${GREEN}Choose electrode types to simulate:${RESET}"
    echo "1. Mapped electrodes only (use EEG net positions)"
    echo "2. Optimized electrodes only (use XYZ coordinates)"
    echo "3. Both mapped and optimized"
    
    while true; do
        read -p "Enter your choice (1, 2, or 3): " electrode_type_choice
        case "$electrode_type_choice" in
            1)
                use_mapped=true
                use_optimized=false
                electrode_type_text="Mapped"
                break
                ;;
            2)
                use_mapped=false
                use_optimized=true
                electrode_type_text="Optimized"
                break
                ;;
            3)
                use_mapped=true
                use_optimized=true
                electrode_type_text="Both"
                break
                ;;
            *)
                reprompt
                ;;
        esac
    done
    
    echo -e "${CYAN}Selected ${#selected_flex_outputs[@]} flex-search output(s) with $electrode_type_text electrode type(s)${RESET}"
    
    # Create temporary flex montages file
    temp_flex_file=$(mktemp --suffix=.json)
    
    # Create a temporary script to process the flex montages
    temp_script=$(mktemp --suffix=.py)
    cat > "$temp_script" << 'EOF'
import json
import sys
import os

flex_montages = []

# Get parameters from command line
if len(sys.argv) < 3:
    print("Usage: script.py use_mapped use_optimized file1 file2 ...")
    sys.exit(1)

use_mapped = sys.argv[1] == 'true'
use_optimized = sys.argv[2] == 'true'
flex_paths = sys.argv[3:]  # Rest are file paths

# Process each selected output
for path in flex_paths:
    try:
        with open(path, 'r') as f:
            mapping_data = json.load(f)
        
        # Extract subject ID from path: /path/to/derivatives/SimNIBS/sub-101/flex-search/search_name/electrode_mapping.json
        path_parts = path.split('/')
        subject_part = [part for part in path_parts if part.startswith('sub-')][0]
        subject_id = subject_part.replace('sub-', '')
        search_name = path_parts[-2]  # Extract search name from path
        
        if use_mapped:
            mapped_labels = mapping_data.get('mapped_labels', [])
            eeg_net = mapping_data.get('eeg_net', 'EGI_template.csv')
            
            if len(mapped_labels) >= 4:
                # Parse search_name for new naming format using bash function
                # Note: This is within a Python script, so we'll do the parsing in Python
                import subprocess
                import os
                
                # Get the search name and parse it
                script_dir = os.path.dirname(os.path.abspath(__file__))
                
                # Simple Python parsing logic (equivalent to bash function)
                def parse_flex_search_name_py(search_name, electrode_type):
                    # Handle new cortical search format: lh_DK40_14_mean_maxTI
                    if search_name.startswith(('lh_', 'rh_')):
                        parts = search_name.split('_')
                        if len(parts) >= 5:
                            hemisphere = parts[0]       # e.g., 'lh'
                            atlas = parts[1]            # e.g., 'DK40'
                            region = parts[2]           # e.g., '14'
                            goal = parts[3]             # e.g., 'mean'
                            post_proc = parts[4]        # e.g., 'maxTI'
                            
                            return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
                    
                    # Handle legacy cortical search format: lh.101_DK40_14_mean (for backward compatibility)
                    elif search_name.startswith(('lh.', 'rh.')):
                        parts = search_name.split('_')
                        if len(parts) >= 3:
                            hemisphere_region = parts[0]  # e.g., 'lh.101'
                            atlas = parts[1]  # e.g., 'DK40'
                            goal_postproc = '_'.join(parts[2:])  # e.g., '14_mean'
                            
                            # Extract hemisphere and region
                            if '.' in hemisphere_region:
                                hemisphere, region = hemisphere_region.split('.', 1)
                            else:
                                hemisphere = 'unknown'
                                region = hemisphere_region
                            
                            # Split goal and postProc if possible
                            if '_' in goal_postproc:
                                goal_parts = goal_postproc.split('_')
                                goal = goal_parts[0]
                                post_proc = '_'.join(goal_parts[1:])
                            else:
                                goal = goal_postproc
                                post_proc = 'default'
                            
                            return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
                    
                    # Handle new subcortical search format: subcortical_atlas_region_goal_postprocess
                    elif search_name.startswith('subcortical_'):
                        parts = search_name.split('_')
                        if len(parts) >= 5:
                            hemisphere = 'subcortical'
                            atlas = parts[1]
                            region = parts[2]
                            goal = parts[3]
                            post_proc = parts[4]
                            
                            return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
                    
                    # Handle new spherical search format: sphere_x0y0z0r10_mean_normalTI
                    elif search_name.startswith('sphere_'):
                        parts = search_name.split('_')
                        if len(parts) >= 4:
                            hemisphere = 'spherical'
                            coordinates = parts[1]     # e.g., 'x0y0z0r10'
                            goal = parts[2]            # e.g., 'mean'
                            post_proc = parts[3]       # e.g., 'normalTI'
                            
                            return f"flex_{hemisphere}_coordinates_{coordinates}_{goal}_{post_proc}_{electrode_type}"
                    
                    # Legacy spherical coordinates or other formats (for backward compatibility)
                    elif '_' in search_name and any(char.isdigit() for char in search_name):
                        parts = search_name.split('_')
                        hemisphere = 'spherical'
                        atlas = 'coordinates'
                        region = '_'.join(parts[:-1])  # Everything except goal
                        goal = parts[-1] if parts else 'optimization'
                        post_proc = 'default'
                        
                        return f"flex_{hemisphere}_{atlas}_{region}_{goal}_{post_proc}_{electrode_type}"
                    
                    # Fallback for unrecognized formats
                    else:
                        return f"flex_unknown_unknown_{search_name}_optimization_default_{electrode_type}"
                
                montage_name = parse_flex_search_name_py(search_name, 'mapped')
                
                montage_data = {
                    'name': montage_name,
                    'type': 'flex_mapped',
                    'eeg_net': eeg_net,
                    'electrode_labels': mapped_labels[:4],
                    'pairs': [[mapped_labels[0], mapped_labels[1]], [mapped_labels[2], mapped_labels[3]]]
                }
                flex_montages.append(montage_data)
        
        if use_optimized:
            optimized_positions = mapping_data.get('optimized_positions', [])
            
            if len(optimized_positions) >= 4:
                montage_name = parse_flex_search_name_py(search_name, 'optimized')
                
                montage_data = {
                    'name': montage_name,
                    'type': 'flex_optimized',
                    'electrode_positions': optimized_positions[:4],
                    'pairs': [[optimized_positions[0], optimized_positions[1]], 
                             [optimized_positions[2], optimized_positions[3]]]
                }
                flex_montages.append(montage_data)
    except Exception as e:
        print(f'Error processing {path}: {e}', file=sys.stderr)

# Write the flex montages file to the output file specified in environment
output_file = os.environ.get('TEMP_FLEX_FILE')
if output_file:
    with open(output_file, 'w') as f:
        json.dump(flex_montages, f, indent=2)
    print(f'Created flex montages file with {len(flex_montages)} montages')
else:
    print("Error: TEMP_FLEX_FILE environment variable not set")
    sys.exit(1)
EOF
    
    # Set environment variable for the temp file
    export TEMP_FLEX_FILE="$temp_flex_file"
    
    # Run the Python script with proper arguments
    python3 "$temp_script" "$use_mapped" "$use_optimized" "${selected_flex_paths[@]}"
    
    # Clean up the temporary script
    rm -f "$temp_script"

    # Export the flex montages file for the simulation
    export FLEX_MONTAGES_FILE="$temp_flex_file"
    export SIMULATION_MODE="flex"
    
    echo -e "${GREEN}Created flex montages file: $temp_flex_file${RESET}"
}

# Choose montages with configuration support
prompt_montages() {
    if [[ "$simulation_framework" == "flex" ]]; then
        choose_flex_search_outputs
        return
    fi
    
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
            intensity_a=$(echo "$intensity_ma * 0.001" | bc -l)
            # Set both channels to the same current value
            current="${intensity_a},${intensity_a}"
            echo -e "${CYAN}Using default intensity: ${intensity_ma}mA (${intensity_a}A)${RESET}"
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
    
    # Convert mA to A and set the current for both channels
    intensity_a=$(echo "$intensity_ma * 0.001" | bc -l)
    current="${intensity_a},${intensity_a}"
    echo -e "${CYAN}Setting current to ${intensity_a}A for both channels${RESET}"
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
        
        if [[ "$simulation_framework" == "flex" ]]; then
            subject_list+="${current_subject}"
        else
            subject_list+="${current_subject} (EEG Net: ${subject_eeg_nets[$current_subject]:-EGI_template.csv})"
        fi
    done
    echo -e "Subjects: ${CYAN}$subject_list${RESET}"
    
    if [[ "$simulation_framework" == "flex" ]]; then
        echo -e "EEG Nets: ${CYAN}Determined from flex-search optimization results${RESET}"
    fi
    
    # Simulation Parameters
    echo -e "\n${BOLD_CYAN}Simulation Parameters:${RESET}"
    echo -e "Simulation Type: ${CYAN}${sim_type_text}${RESET}"
    echo -e "Framework: ${CYAN}$(if [[ "$simulation_framework" == "flex" ]]; then echo "Flex-Search"; else echo "Traditional Montage"; fi)${RESET}"
    echo -e "Mode: ${CYAN}${montage_type_text}${RESET}"
    
    if [[ "$simulation_framework" == "flex" ]]; then
        echo -e "Selected Flex-Search Outputs: ${CYAN}${selected_flex_outputs[*]}${RESET}"
        echo -e "Electrode Types: ${CYAN}${electrode_type_text}${RESET}"
    else
        echo -e "Selected Montages: ${CYAN}${selected_montages[*]}${RESET}"
    fi
    
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

# Check if direct execution from GUI is requested FIRST
if [[ "$1" == "--run-direct" ]]; then
    echo "Running in direct execution mode from GUI"
    is_direct_mode="true"
    
    # Extract parameters from environment variables
    subject_choices="$SUBJECT_CHOICES"
    sim_type="$SIM_TYPE"
    simulation_framework="$SIMULATION_FRAMEWORK"
    sim_mode="$SIM_MODE"
    conductivity="$CONDUCTIVITY"
    current="$CURRENT"
    electrode_shape="$ELECTRODE_SHAPE"
    dimensions="$DIMENSIONS"
    thickness="$THICKNESS"
    temp_flex_file="$FLEX_MONTAGES_FILE"
    
    # Parse subjects from environment
    IFS=',' read -ra selected_subjects <<< "$subject_choices"
    
    # Set simulation mode based on framework
    if [[ "$simulation_framework" == "flex" ]]; then
        sim_mode="FLEX_TI"  # Force TI mode for flex-search
    fi
    
    # Set selected montages from environment
    echo "Debug: SELECTED_MONTAGES env var: '$SELECTED_MONTAGES'"
    if [[ -n "$SELECTED_MONTAGES" ]]; then
        IFS=',' read -ra selected_montages <<< "$SELECTED_MONTAGES"
        echo "Debug: Parsed selected_montages array: ${selected_montages[@]}"
        echo "Debug: Number of parsed montages: ${#selected_montages[@]}"
    else
        selected_montages=()
        echo "Debug: No montages in environment variable"
    fi
    
    # Set up EEG nets for each subject (only for montage mode)
    declare -A subject_eeg_nets
    if [[ "$simulation_framework" != "flex" ]]; then
        # For regular montages, get EEG nets from environment
        if [[ -n "$EEG_NETS" ]]; then
            IFS=',' read -ra eeg_net_list <<< "$EEG_NETS"
            for i in "${!selected_subjects[@]}"; do
                subject_num="${selected_subjects[i]}"
                subject_id="$subject_num"  # In direct mode, use subject IDs directly
                if [[ $i -lt ${#eeg_net_list[@]} ]]; then
                    subject_eeg_nets["$subject_id"]="${eeg_net_list[i]}"
                else
                    subject_eeg_nets["$subject_id"]="EGI_template.csv"
                fi
            done
        fi
    fi
    
    # Export environment variables for the simulation
    export SELECTED_MONTAGES
    export SIMULATION_MODE="$simulation_framework"
    export FLEX_MONTAGES_FILE="$temp_flex_file"
    
    # Determine simulator directory and main script
    simulator_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../simulator"
    if [[ "$sim_type" == "TI" ]]; then
        main_script="main-TI.sh"
    else
        main_script="main-mTI.sh"
    fi
    
    # Process each subject
    for subject_num in "${selected_subjects[@]}"; do
        subject_id="$subject_num"  # In direct mode, use subject IDs directly
        subject_dir="$project_dir/sub-$subject_id"
        derivatives_dir="$project_dir/derivatives"
        simnibs_dir="$derivatives_dir/SimNIBS/sub-$subject_id"
        simulation_dir="$simnibs_dir/Simulations"
        
        # Set EEG net based on simulation framework
        if [[ "$simulation_framework" == "flex" ]]; then
            eeg_net="flex_mode"  # Placeholder - actual EEG nets come from JSON files
        else
            eeg_net="${subject_eeg_nets[$subject_id]:-EGI_template.csv}"
        fi
        
        # Create simulation directory if it doesn't exist
        mkdir -p "$simulation_dir"
        
        # For flex-search mode, create a separate temporary file for each subject
        if [[ "$simulation_framework" == "flex" ]]; then
            # Create subject-specific temporary flex montages file
            subject_temp_flex_file=$(mktemp --suffix=_${subject_id}.json)
            if [[ -f "$temp_flex_file" ]]; then
                # Copy the original flex montages file to the subject-specific file
                cp "$temp_flex_file" "$subject_temp_flex_file"
                echo "Created subject-specific flex montages file for $subject_id: $subject_temp_flex_file"
                # Set the environment variable for this specific subject
                export FLEX_MONTAGES_FILE="$subject_temp_flex_file"
            else
                echo "Warning: Original flex montages file not found: $temp_flex_file"
                unset FLEX_MONTAGES_FILE
            fi
        fi
        
        # Debug output for montages
        echo "Debug: Selected montages array: ${selected_montages[@]}"
        echo "Debug: Number of montages: ${#selected_montages[@]}"
        
        echo "Executing: $simulator_dir/$main_script $subject_id $conductivity $project_dir $simulation_dir $sim_mode $current $electrode_shape $dimensions $thickness $eeg_net ${selected_montages[@]} --"
        
        # Call the appropriate main pipeline script
        if [[ "$simulation_framework" == "flex" ]]; then
            # For flex-search, pass empty montages array and rely on FLEX_MONTAGES_FILE
            "$simulator_dir/$main_script" "$subject_id" "$conductivity" "$project_dir" "$simulation_dir" "$sim_mode" "$current" "$electrode_shape" "$dimensions" "$thickness" "$eeg_net" --
        else
            # For regular montages, pass the selected montages
            "$simulator_dir/$main_script" "$subject_id" "$conductivity" "$project_dir" "$simulation_dir" "$sim_mode" "$current" "$electrode_shape" "$dimensions" "$thickness" "$eeg_net" "${selected_montages[@]}" --
        fi
        
        # Clean up subject-specific temp file after this subject's simulation
        if [[ "$simulation_framework" == "flex" ]] && [[ -n "$subject_temp_flex_file" ]] && [[ -f "$subject_temp_flex_file" ]]; then
            rm -f "$subject_temp_flex_file"
            echo "Cleaned up subject-specific flex montages file for $subject_id"
        fi
    done
    
    # Clean up temporary files
if [[ -n "$temp_flex_file" && -f "$temp_flex_file" ]]; then
    rm -f "$temp_flex_file"
    echo -e "${CYAN}Cleaned up temporary flex montages file${RESET}"
fi

# Clean up simulation completion files
cleanup_completion_files() {
    local temp_dir="$project_dir/derivatives/temp"
    if [[ -d "$temp_dir" ]]; then
        local cleaned_count=0
        for completion_file in "$temp_dir"/simulation_completion_*.json; do
            if [[ -f "$completion_file" ]]; then
                rm -f "$completion_file"
                ((cleaned_count++))
                echo -e "${CYAN}Cleaned up completion file: $(basename "$completion_file")${RESET}"
            fi
        done
        
        if [[ $cleaned_count -gt 0 ]]; then
            echo -e "${GREEN}Cleaned up $cleaned_count completion file(s)${RESET}"
        fi
        
        # Remove temp directory if empty
        if [[ -d "$temp_dir" && -z "$(ls -A "$temp_dir")" ]]; then
            rmdir "$temp_dir"
            echo -e "${CYAN}Removed empty temp directory${RESET}"
        fi
    fi
}

cleanup_completion_files

echo "Direct execution completed"
exit 0
fi

# Main script execution (interactive mode)
show_welcome_message

# Collect all necessary inputs in the specified order
choose_subjects
choose_simulation_type
choose_simulation_framework
choose_simulation_mode
choose_tissue_conductivities

# For each selected subject, choose an EEG net (only for montage mode)
declare -A subject_eeg_nets
if [[ "$simulation_framework" != "flex" ]]; then
    for subject_num in "${selected_subjects[@]}"; do
        subject_id="${subjects[$((subject_num-1))]}"
        echo -e "\n${BOLD_CYAN}Selecting EEG net for subject: $subject_id${RESET}"
        choose_eeg_net "$subject_id"
        subject_eeg_nets["$subject_id"]="$selected_eeg_net"
    done
else
    echo -e "\n${CYAN}Flex-search mode: EEG nets will be taken from optimization results${RESET}"
fi

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
    
    # Set EEG net based on simulation framework
    if [[ "$simulation_framework" == "flex" ]]; then
        eeg_net="flex_mode"  # Placeholder - actual EEG nets come from JSON files
    else
        eeg_net="${subject_eeg_nets[$subject_id]:-EGI_template.csv}"  # Use selected or default
    fi

    # Create simulation directory if it doesn't exist
    mkdir -p "$simulation_dir"

    # Call the appropriate main pipeline script with the gathered parameters
    # Create a unique simulation session ID for CLI runs
    if [[ -z "$SIMULATION_SESSION_ID" ]]; then
        export SIMULATION_SESSION_ID="CLI_$(date +%Y%m%d_%H%M%S)_${subject_id}"
    fi
    
    if [[ "$simulation_framework" == "flex" ]]; then
        # For flex-search, export environment variables and pass empty montages array
        export FLEX_MONTAGES_FILE="$temp_flex_file"
        export SIMULATION_MODE="flex"
        export SELECTED_MONTAGES=""
        "$simulator_dir/$main_script" "$subject_id" "$conductivity" "$project_dir" "$simulation_dir" "$sim_mode" "$current" "$electrode_shape" "$dimensions" "$thickness" "$eeg_net" --
    else
        # For regular montages, pass the selected montages
        "$simulator_dir/$main_script" "$subject_id" "$conductivity" "$project_dir" "$simulation_dir" "$sim_mode" "$current" "$electrode_shape" "$dimensions" "$thickness" "$eeg_net" "${selected_montages[@]}" --
    fi
done

# Output success message if new montages or ROIs were added
if [ "$new_montage_added" = true ]; then
    echo -e "${GREEN}New montage added to montage_list.json.${RESET}"
fi

echo -e "${GREEN}All tasks completed successfully.${RESET}"

# Generate simulation reports automatically
echo -e "${CYAN}Generating simulation reports...${RESET}"

# Source the reporting utilities
reporting_script="$script_dir/../utils/bash_reporting.sh"
if [ -f "$reporting_script" ]; then
    source "$reporting_script"
elif [ -f "/development/utils/bash_reporting.sh" ]; then
    source "/development/utils/bash_reporting.sh"
    
    # Initialize reporting
    init_reporting "$project_dir"
    
    # Generate reports for each processed subject
    reports_generated=0
    for subject_num in "${selected_subjects[@]}"; do
        if [[ "$is_direct_mode" == "true" ]]; then
            subject_id="$subject_num"
        else
            subject_id="${subjects[$((subject_num-1))]}"
        fi
        
        echo -e "${CYAN}Generating report for subject: $subject_id${RESET}"
        
        # Use bash reporting utilities
        if create_simulation_report "" "" "" "$subject_id"; then
            ((reports_generated++))
            echo -e "${GREEN}✅ Report generated for subject: $subject_id${RESET}"
        else
            echo -e "${YELLOW}⚠️ Could not generate report for subject: $subject_id${RESET}"
        fi
    done
else
    # Fallback: use Python directly with new utilities
    python_cmd=""
    if command -v python3 &> /dev/null; then
        python_cmd="python3"
    elif command -v python &> /dev/null; then
        python_cmd="python"
    else
        echo -e "${YELLOW}Warning: Python not found. Skipping report generation.${RESET}"
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
sys.path.append('$script_dir/../utils')

from report_util import create_simulation_report
import datetime

try:
    # Create simulation log with parameters
    simulation_log = {
        'simulation_parameters': {
            'conductivity_type': '$conductivity',
            'simulation_mode': '$sim_mode',
            'eeg_net': '${subject_eeg_nets[$subject_id]:-EGI_template.csv}',
            'intensity_ch1': $(echo '$current' | cut -d',' -f1 | awk '{print $1 * 1000}'),  # Convert A to mA
            'intensity_ch2': $(echo '$current' | cut -d',' -f2 | awk '{print $1 * 1000}'),  # Convert A to mA
            'quiet_mode': False
        },
        'electrode_parameters': {
            'shape': '$electrode_shape',
            'dimensions': [$(echo '$dimensions' | sed 's/,/, /g')],
            'thickness': $thickness
        },
        'subjects': [{
            'subject_id': '$subject_id',
            'm2m_path': '$project_dir/derivatives/SimNIBS/sub-$subject_id/m2m_$subject_id',
            'status': 'completed'
        }],
        'montages': []
    }
    
    # Add montages
    montage_type = 'unipolar' if '$sim_mode' == 'U' else 'multipolar'
    montages = [$(printf "'%s'," "${selected_montages[@]}" | sed 's/,$//')]
    
    # Load montage file to get actual electrode pairs
    import json
    import os
    
    montage_file = os.path.join('$project_dir', 'montage_list.json')
    montage_data = {}
    if os.path.exists(montage_file):
        try:
            with open(montage_file, 'r') as f:
                montage_data = json.load(f)
        except:
            pass
    
    for montage in montages:
        if montage:  # Skip empty montages
            # Try to get actual electrode pairs from the montage file
            electrode_pairs = [['E1', 'E2']]  # Default fallback
            
            # Look for the montage in the appropriate net and type
            net_type = 'uni_polar_montages' if '$sim_mode' == 'U' else 'multi_polar_montages'
            eeg_net = '${subject_eeg_nets[$subject_id]:-EGI_template.csv}'
            
            if ('nets' in montage_data and 
                eeg_net in montage_data['nets'] and 
                net_type in montage_data['nets'][eeg_net] and 
                montage in montage_data['nets'][eeg_net][net_type]):
                electrode_pairs = montage_data['nets'][eeg_net][net_type][montage]
            
            simulation_log['montages'].append({
                'name': montage,  # Changed from 'montage_name' to 'name' for consistency
                'electrode_pairs': electrode_pairs,
                'montage_type': montage_type
            })
    
    # Generate report
    report_path = create_simulation_report(
        project_dir='$project_dir',
        simulation_log=simulation_log,
        subject_id='$subject_id'
    )
    
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
fi

# Summary
if [ $reports_generated -gt 0 ]; then
    echo -e "${GREEN}✅ Generated $reports_generated simulation report(s)${RESET}"
    echo -e "${CYAN}Reports saved to: $project_dir/derivatives/reports/sub-{subjectID}/${RESET}"
else
    echo -e "${YELLOW}⚠️ No reports were generated${RESET}"
fi

# Clean up temporary flex montages file
if [[ -n "$temp_flex_file" && -f "$temp_flex_file" ]]; then
    rm -f "$temp_flex_file"
    echo -e "${CYAN}Cleaned up temporary flex montages file${RESET}"
fi
