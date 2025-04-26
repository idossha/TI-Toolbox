#!/usr/bin/env python3

import copy
import os
import re
import sys  # Added for better exception handling
import numpy as np
from itertools import product
from simnibs import mesh_io
from simnibs.utils import TI_utils as TI

'''
Ido Haber - ihaber@wisc.edu
October 3, 2024
Optimized for optimizer pipeline

This script is designed for performing Temporal Interference (TI) simulations 
based on two types of leadfields:

1. Volumetric Leadfield:
   - Used for calculating TI_max, the maximal amplitude of the TI field in the volume.

2. Surface Leadfield:
   - Used for calculating TI_localnorm, the TI amplitude along the local normal orientation in gray matter.

The script generates all possible electrode pair combinations, calculates the corresponding electric fields, 
and exports the results in mesh format for further visualization.
'''

# Define color variables
BOLD = '\033[1m'
UNDERLINE = '\033[4m'
RESET = '\033[0m'
RED = '\033[0;31m'     # Red for errors
GREEN = '\033[0;32m'   # Green for success messages and prompts
CYAN = '\033[0;36m'    # Cyan for actions being performed
BOLD_CYAN = '\033[1;36m'

# Function to generate all combinations
def generate_combinations(E1_plus, E1_minus, E2_plus, E2_minus):
    print(f"{CYAN}Generating all electrode pair combinations...{RESET}")
    combinations = []
    for e1p, e1m in product(E1_plus, E1_minus):
        for e2p, e2m in product(E2_plus, E2_minus):
            combinations.append(((e1p, e1m), (e2p, e2m)))
    print(f"{GREEN}Total combinations generated: {len(combinations)}{RESET}")
    return combinations

# Function to get user input for electrode lists
def get_electrode_list(prompt):
    pattern = re.compile(r'^E\d{3}$')  # Match 'E' followed by exactly three digits
    while True:
        user_input = input(f"{GREEN}{prompt}{RESET}").strip()
        # Replace commas with spaces and split into a list
        electrodes = user_input.replace(',', ' ').split()
        # Validate electrodes
        if all(pattern.match(e) for e in electrodes):
            print(f"{GREEN}Electrode list accepted: {electrodes}{RESET}")
            return electrodes
        else:
            print(f"{RED}Invalid input. Please enter electrodes in the format E###, e.g., E001, E100.{RESET}")

# Get the intensity of stimulation from user input
def get_intensity(prompt):
    while True:
        try:
            intensity_mV = float(input(f"{GREEN}{prompt}{RESET}").strip())
            intensity_V = intensity_mV / 1000.0  # Convert mV to V
            print(f"{GREEN}Intensity of stimulation set to {intensity_V} V{RESET}")
            return intensity_V
        except ValueError:
            print(f"{RED}Please enter a valid number for the intensity of stimulation.{RESET}")

# Function to process lead field and generate the meshes
def process_leadfield(leadfield_type, E1_plus, E1_minus, E2_plus, E2_minus, intensity, project_dir, subject_name):
    print(f"{CYAN}Starting processing for {leadfield_type} leadfield...{RESET}")
    
    # Construct leadfield directory and HDF5 file path
    leadfield_dir = os.path.join(project_dir, f"Subjects/leadfield_{leadfield_type}_{subject_name}")
    leadfield_hdf = os.path.join(leadfield_dir, f"{subject_name}_leadfield_{os.getenv('EEG_CAP', 'EGI_template')}.hdf5")
    
    print(f"{CYAN}Leadfield Directory: {leadfield_dir}{RESET}")
    print(f"{CYAN}Leadfield HDF5 Path: {leadfield_hdf}{RESET}")
    
    # Attempt to load leadfield
    try:
        print(f"{CYAN}Loading leadfield from {leadfield_hdf}...{RESET}")
        leadfield, mesh, idx_lf = TI.load_leadfield(leadfield_hdf)
        print(f"{GREEN}Leadfield loaded successfully.{RESET}")
    except Exception as e:
        print(f"{RED}Error loading leadfield: {e}{RESET}")
        return
    
    # Set the output directory based on the project directory and subject name
    output_dir = os.path.join(project_dir, f"Simulations/opt_{subject_name}")
    print(f"{CYAN}Output Directory: {output_dir}{RESET}")
    
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        print(f"{CYAN}Output directory does not exist. Creating {output_dir}...{RESET}")
        os.makedirs(output_dir)
        print(f"{GREEN}Output directory created.{RESET}")
    else:
        print(f"{GREEN}Output directory already exists.{RESET}")
    
    # Generate all electrode pair combinations
    all_combinations = generate_combinations(E1_plus, E1_minus, E2_plus, E2_minus)
    total_combinations = len(all_combinations)  # Calculate total configurations
    print(f"{CYAN}Starting TI simulation for {total_combinations} electrode combinations...{RESET}")
    
    # Iterate through all combinations of electrode pairs
    for i, ((e1p, e1m), (e2p, e2m)) in enumerate(all_combinations):
        print(f"{CYAN}Processing combination {i+1}/{total_combinations}: "
              f"{e1p}-{e1m} and {e2p}-{e2m}{RESET}")
        TIpair1 = [e1p, e1m, intensity]
        TIpair2 = [e2p, e2m, intensity]
    
        # Get fields for the two pairs
        try:
            print(f"{CYAN}Calculating fields for {e1p}-{e1m} and {e2p}-{e2m}...{RESET}")
            ef1 = TI.get_field(TIpair1, leadfield, idx_lf)
            ef2 = TI.get_field(TIpair2, leadfield, idx_lf)
            print(f"{GREEN}Fields calculated successfully.{RESET}")
        except Exception as e:
            print(f"{RED}Error calculating fields for electrodes {e1p}, {e1m}, {e2p}, {e2m}: {e}{RESET}")
            continue
    
        # Add to mesh for later visualization
        mout = copy.deepcopy(mesh)
        print(f"{CYAN}Deep copied mesh for modification.{RESET}")
    
        # Calculate the maximal TI amplitude for vol
        print(f"{CYAN}Calculating TI_max for the current electrode pair...{RESET}")
        try:
            TImax = TI.get_maxTI(ef1, ef2)
            print(f"{GREEN}TI_max calculated: {TImax}{RESET}")
        except Exception as e:
            print(f"{RED}Error calculating TI_max: {e}{RESET}")
            continue
    
        mout.add_element_field(TImax, "TImax")  # for visualization
        mesh_filename = os.path.join(output_dir, f"TI_field_{e1p}_{e1m}_and_{e2p}_{e2m}.msh")
        visible_field = "TImax"
        print(f"{CYAN}Mesh Filename: {mesh_filename}{RESET}")
    
        # Save the updated mesh with a unique name in the output directory
        try:
            print(f"{CYAN}Writing mesh to file...{RESET}")
            mesh_io.write_msh(mout, mesh_filename)
            print(f"{GREEN}Mesh written to {mesh_filename}.{RESET}")
        except Exception as e:
            print(f"{RED}Error writing mesh to file: {e}{RESET}")
            continue
        
        # Attempt to create an optimized view of the mesh
        try:
            print(f"{CYAN}Creating optimized view for mesh...{RESET}")
            v = mout.view(
                visible_tags=[1, 2, 1006],
                visible_fields=visible_field,
            )
            v.write_opt(mesh_filename)
            print(f"{GREEN}Optimized view written to {mesh_filename}.{RESET}")
        except Exception as e:
            print(f"{RED}Error creating optimized view: {e}{RESET}")
            continue
    
        # Progress indicator (formatted as 003/256)
        progress_str = f"{i+1:03}/{total_combinations}"
        print(f"{BOLD}Progress: {progress_str} - Mesh saved.{RESET}\n")
    
    print(f"{BOLD_CYAN}TI simulation and mesh generation completed for subject {subject_name}.{RESET}")

if __name__ == "__main__":
    # Check for required environment variables
    project_dir = os.getenv('PROJECT_DIR')
    subject_name = os.getenv('SUBJECT_NAME')
    if not project_dir or not subject_name:
        print(f"{RED}Error: PROJECT_DIR and SUBJECT_NAME environment variables must be set.{RESET}")
        sys.exit(1)
    
    print(f"{BOLD_CYAN}Starting TI Simulation for Subject: {subject_name}{RESET}")
    print(f"{BOLD_CYAN}Project Directory: {project_dir}{RESET}\n")
    
    # Get electrode lists from user input
    E1_plus = get_electrode_list("Enter electrodes for E1_plus separated by spaces or commas (format E###): ")
    E1_minus = get_electrode_list("Enter electrodes for E1_minus separated by spaces or commas (format E###): ")
    E2_plus = get_electrode_list("Enter electrodes for E2_plus separated by spaces or commas (format E###): ")
    E2_minus = get_electrode_list("Enter electrodes for E2_minus separated by spaces or commas (format E###): ")
    
    # Get intensity of stimulation
    intensity = get_intensity("Intensity of stimulation in mV: ")
    
    print(f"\n{BOLD_CYAN}Electrode Configuration:{RESET}")
    print(f"E1_plus: {E1_plus}")
    print(f"E1_minus: {E1_minus}")
    print(f"E2_plus: {E2_plus}")
    print(f"E2_minus: {E2_minus}")
    print(f"Stimulation Intensity: {intensity} V\n")
    
    # Start processing leadfield
    process_leadfield("vol", E1_plus, E1_minus, E2_plus, E2_minus, intensity, project_dir, subject_name)

