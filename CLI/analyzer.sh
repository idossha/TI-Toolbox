#!/bin/bash

###########################################
# Ido Haber / ihaber@wisc.edu
# March 2024
# Optimized for TI-CSC analyzer
# This script is used to run analysis on simulation results for a given subject.
###########################################

set -e  # Exit immediately if a command exits with a non-zero status

# Base directories
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
analyzer_dir="$script_dir/../analyzer"

# Get the project directory from environment variable or use default
if [ -z "$PROJECT_DIR_NAME" ]; then
    echo -e "${YELLOW}Warning: PROJECT_DIR_NAME not set, using 'project_dir' as default${RESET}"
    PROJECT_DIR_NAME="project_dir"
fi
project_dir="/mnt/$PROJECT_DIR_NAME"

# Define color variables
BOLD='\033[1m'
RESET='\033[0m'
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD_CYAN='\033[1;36m'
YELLOW='\033[0;33m'

# Function to handle invalid input and reprompt
reprompt() {
    echo -e "${RED}Invalid input. Please try again.${RESET}"
}

# Function to list available subjects
list_subjects() {
    subjects=()
    echo -e "${YELLOW}Looking for subjects in: $project_dir/derivatives/SimNIBS/${RESET}"
    
    if [ ! -d "$project_dir" ]; then
        echo -e "${RED}Error: Project directory not found: $project_dir${RESET}"
        echo -e "${RED}Make sure PROJECT_DIR_NAME environment variable is set correctly${RESET}"
        exit 1
    fi
    
    if [ ! -d "$project_dir/derivatives/SimNIBS" ]; then
        echo -e "${RED}Error: SimNIBS directory not found: $project_dir/derivatives/SimNIBS${RESET}"
        exit 1
    fi
    
    # Find all subject directories
    while IFS= read -r -d $'\0' dir; do
        if [ -d "$dir" ]; then
            sub_id=$(basename "$dir" | sed 's/sub-//')
            echo -e "${YELLOW}Found subject: $sub_id${RESET}"
            subjects+=("$sub_id")
        fi
    done < <(find "$project_dir/derivatives/SimNIBS" -maxdepth 1 -name "sub-*" -type d -print0)
    
    if [ ${#subjects[@]} -eq 0 ]; then
        echo -e "${RED}No subjects found${RESET}"
        exit 1
    fi
    
    echo -e "${BOLD_CYAN}Available Subjects:${RESET}"
    echo "-------------------"
    for i in "${!subjects[@]}"; do
        printf "%3d. %-25s\n" $(( i + 1 )) "${subjects[$i]}"
    done
    echo
}

# Function to list available simulations for a subject
list_simulations() {
    local subject_id=$1
    simulations=()
    local sim_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations"
    
    echo -e "${YELLOW}Looking for simulations in: $sim_dir${RESET}"
    
    if [ ! -d "$sim_dir" ]; then
        echo -e "${RED}Error: Simulations directory not found: $sim_dir${RESET}"
        exit 1
    fi
    
    # Find all simulation directories
    while IFS= read -r -d $'\0' dir; do
        if [ -d "$dir" ]; then
            sim_name=$(basename "$dir")
            echo -e "${YELLOW}Found simulation: $sim_name${RESET}"
            simulations+=("$sim_name")
        fi
    done < <(find "$sim_dir" -maxdepth 1 -mindepth 1 -type d -print0)
    
    if [ ${#simulations[@]} -eq 0 ]; then
        echo -e "${RED}No simulations found for subject $subject_id${RESET}"
        exit 1
    fi
    
    echo -e "${BOLD_CYAN}Available Simulations for subject $subject_id:${RESET}"
    echo "----------------------------------------"
    for i in "${!simulations[@]}"; do
        printf "%3d. %-25s\n" $(( i + 1 )) "${simulations[$i]}"
    done
    echo
}

# Function to list available mesh analysis types
list_analysis_types() {
    echo -e "${BOLD_CYAN}Available Mesh Analysis Types:${RESET}"
    echo "----------------------"
    echo "1. Analyze Whole Head - Analyze all regions in the specified atlas"
    echo "2. Analyze Sphere - Analyze a spherical region of interest"
    echo "3. Analyze Cortex - Analyze a specific cortical region"
}

# Main script execution
echo -e "${BOLD_CYAN}TI-CSC Analysis Tool${RESET}"
echo "===================="

# List and select subject
list_subjects

while true; do
    echo -e "\n${BOLD}Select subject number (1-${#subjects[@]}):${RESET}"
    read -r subject_num
    
    if [[ "$subject_num" =~ ^[0-9]+$ ]] && \
       (( subject_num >= 1 && subject_num <= ${#subjects[@]} )); then
        subject_id="${subjects[$((subject_num-1))]}"
        break
    fi
    reprompt
done

# List and select simulation
list_simulations "$subject_id"

while true; do
    echo -e "\n${BOLD}Select simulation number (1-${#simulations[@]}):${RESET}"
    read -r sim_num
    
    if [[ "$sim_num" =~ ^[0-9]+$ ]] && \
       (( sim_num >= 1 && sim_num <= ${#simulations[@]} )); then
        sim_name="${simulations[$((sim_num-1))]}"
        break
    fi
    reprompt
done

# List and select analysis type
list_analysis_types

while true; do
    echo -e "\n${BOLD}Select analysis type (1-3):${RESET}"
    read -r analysis_type
    if [[ "$analysis_type" =~ ^[1-3]$ ]]; then
        break
    fi
    reprompt
done

# Set up paths
mesh_file="$project_dir/derivatives/SimNIBS/sub-$subject_id/Simulations/$sim_name/TI/mesh/${subject_id}_${sim_name}_TI.msh"
analysis_dir="$project_dir/derivatives/SimNIBS/sub-$subject_id/analysis/$sim_name"

# Verify mesh file exists
if [ ! -f "$mesh_file" ]; then
    echo -e "${RED}Error: Mesh file not found: $mesh_file${RESET}"
    exit 1
fi

# Create analysis directory if it doesn't exist
mkdir -p "$analysis_dir"

# Build command based on analysis type
case "$analysis_type" in
    1)  # Whole Head Analysis
        cmd=("simnibs_python" "$analyzer_dir/mesh_analyzer.py"
             "--subject" "$subject_id"
             "--mesh" "$mesh_file"
             "--analysis-type" "whole_head"
             "--output-dir" "$analysis_dir"
             "--atlas" "HCP_MMP1"
             "--field" "TI_max"
             "--subject-dir" "$project_dir/derivatives/SimNIBS/sub-$subject_id"
             "--visualize")
        ;;
    2)  # Sphere Analysis
        echo -e "\n${BOLD}Enter sphere center coordinates (x,y,z in mm):${RESET}"
        read -r coords
        echo -e "${BOLD}Enter sphere radius (mm):${RESET}"
        read -r radius
        
        cmd=("simnibs_python" "$analyzer_dir/mesh_analyzer.py"
             "--subject" "$subject_id"
             "--mesh" "$mesh_file"
             "--analysis-type" "sphere"
             "--output-dir" "$analysis_dir"
             "--coords" "$coords"
             "--radius" "$radius"
             "--field" "TI_max"
             "--subject-dir" "$project_dir/derivatives/SimNIBS/sub-$subject_id")
        ;;
    3)  # Cortex Analysis
        echo -e "\n${BOLD}Enter target region name:${RESET}"
        read -r region
        
        cmd=("simnibs_python" "$analyzer_dir/mesh_analyzer.py"
             "--subject" "$subject_id"
             "--mesh" "$mesh_file"
             "--analysis-type" "cortex"
             "--output-dir" "$analysis_dir"
             "--region" "$region"
             "--atlas" "HCP_MMP1"
             "--field" "TI_max"
             "--subject-dir" "$project_dir/derivatives/SimNIBS/sub-$subject_id"
             "--visualize")
        ;;
esac

# Execute analysis
echo -e "${GREEN}Executing analysis...${RESET}"
echo -e "${CYAN}Command: ${cmd[*]}${RESET}"

"${cmd[@]}"

# Check execution status
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Analysis completed successfully${RESET}"
    echo -e "${GREEN}Results saved in: $analysis_dir${RESET}"
else
    echo -e "${RED}Analysis failed${RESET}"
fi 
