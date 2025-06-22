#!/usr/bin/env python3

import os
import re
import pandas as pd
import subprocess
import json
import csv
import sys
import time

# Add logging utility import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils import logging_util


'''
Ido Haber - ihaber@wisc.edu
October 3, 2024
Optimized for optimizer pipeline

This script analyzes mesh files in the simulation directory by extracting 
fields at specific ROI coordinates and compiling the results into a structured format.

Key Features:
- Reads ROI files and extracts TImax and TInorm values from mesh files.
- Stores the results in a JSON file for easy access and further analysis.
- Formats the extracted data and writes it to a CSV file for reporting.
- Performs cleanup by removing intermediate CSV files after processing.
'''

def get_roi_coordinates(roi_file):
    """Read coordinates from a ROI CSV file."""
    try:
        with open(roi_file, 'r') as f:
            reader = csv.reader(f)
            coords = next(reader)
            return [float(coord.strip()) for coord in coords]
    except Exception as e:
        print(f"Error reading coordinates from {roi_file}: {e}")
        return None

# Get the project directory and subject name from environment variables
project_dir = os.getenv('PROJECT_DIR')
subject_name = os.getenv('SUBJECT_NAME')

if not project_dir or not subject_name:
    print("Error: PROJECT_DIR and SUBJECT_NAME environment variables must be set")
    sys.exit(1)

# Initialize logger
log_file = os.environ.get('TI_LOG_FILE')
if not log_file:
    # If not provided, create a new log file (fallback behavior)
    time_stamp = time.strftime('%Y%m%d_%H%M%S')
    derivatives_dir = os.path.join(project_dir, 'derivatives')
    log_dir = os.path.join(derivatives_dir, 'logs', f'sub-{subject_name}')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'roi_analyzer_{time_stamp}.log')

# Initialize our main logger
logger = logging_util.get_logger('ROI-Analyzer', log_file, overwrite=False)

# Configure external loggers
logging_util.configure_external_loggers(['simnibs'], logger)

# Set the directories based on BIDS structure
simnibs_dir = os.path.join(project_dir, "derivatives", "SimNIBS")
subject_dir = os.path.join(simnibs_dir, f"sub-{subject_name}")
m2m_dir = os.path.join(subject_dir, f"m2m_{subject_name}")
ex_search_dir = os.path.join(subject_dir, "ex-search")
roi_directory = os.path.join(m2m_dir, 'ROIs')

# Read the list of ROI files from the ROI directory
roi_list_path = os.path.join(roi_directory, 'roi_list.txt')
try:
    with open(roi_list_path, 'r') as file:
        position_files = [os.path.join(roi_directory, line.strip()) for line in file]
except FileNotFoundError:
    print(f"Error: ROI list file not found at {roi_list_path}")
    sys.exit(1)

# Verify that all ROI files exist
missing_files = [f for f in position_files if not os.path.exists(f)]
if missing_files:
    logger.error("The following ROI files are missing:")
    for f in missing_files:
        logger.error(f"  - {f}")
    sys.exit(1)

# Get coordinates from the first ROI file to create the directory name
first_roi_file = position_files[0]
coords = get_roi_coordinates(first_roi_file)
if not coords:
    logger.error("Could not read coordinates from ROI file")
    sys.exit(1)

# Create directory name from coordinates
coord_dir = f"xyz_{int(coords[0])}_{int(coords[1])}_{int(coords[2])}"
opt_directory = os.path.join(ex_search_dir, coord_dir)

# Create analysis directory if it doesn't exist
analysis_dir = os.path.join(opt_directory, "analysis")
if not os.path.exists(analysis_dir):
    os.makedirs(analysis_dir)

# Create a dictionary to hold the data
mesh_data = {}

# Get the list of .msh files in the opt directory and count the total number
msh_files = [f for f in os.listdir(opt_directory) if f.endswith('.msh')]
total_files = len(msh_files)  # Total number of files to process

logger.info(f"Found {total_files} mesh files to process")

# Iterate over all .msh files in the opt directory with progress indicator
for i, msh_file in enumerate(msh_files):
    msh_file_path = os.path.join(opt_directory, msh_file)

    # Progress indicator (formatted as 001/100)
    progress_str = f"{i+1:03}/{total_files}"
    logger.info(f"{progress_str} Processing {msh_file_path}")
    
    # Use only the file name part for mesh_key
    mesh_key = os.path.basename(msh_file_path)
    mesh_data[mesh_key] = {}

    # Iterate over all position files
    for pos_file in position_files:
        pos_base = os.path.splitext(os.path.basename(pos_file))[0]  # Extract the base name of the position file without extension
        logger.debug(f"Using position file: {pos_file}")

        # Run the command to generate CSV files in the ROI directory
        try:
            cmd = ["get_fields_at_coordinates", "-s", pos_file, "-m", msh_file_path, "--method", "linear"]
            logger.debug(f"Running command: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running get_fields_at_coordinates: {e}")
            continue
        
        # The generated CSV files will be in the current directory with names based on the position file and field names
        ti_max_csv = os.path.join(roi_directory, f"{pos_base}_TImax.csv")
        from_volume_csv = os.path.join(roi_directory, f"{pos_base}_from_volume.csv")
        
        # Process the TImax CSV file
        if os.path.exists(ti_max_csv):
            logger.debug(f"Found TImax CSV file: {ti_max_csv}")
            try:
                # Read the CSV file into a dataframe without headers
                df_ti_max = pd.read_csv(ti_max_csv, header=None)
                
                # Ensure all data can be converted to float
                df_ti_max = df_ti_max.apply(pd.to_numeric, errors='coerce')
                df_ti_max = df_ti_max.dropna()  # Drop rows with non-numeric data
                
                # Extract values from the dataframe
                ti_max_values = df_ti_max[0].tolist()  # Assuming the TImax CSV has values in the first column
                
                # Store the values in the dictionary
                if 'TImax' not in mesh_data[mesh_key]:
                    mesh_data[mesh_key]['TImax'] = ti_max_values[0] if ti_max_values else None
            except Exception as e:
                logger.error(f"Error processing TImax file {ti_max_csv}: {e}")
            finally:
                if os.path.exists(ti_max_csv):
                    os.remove(ti_max_csv)
        else:
            logger.warning(f"TImax CSV file {ti_max_csv} not found")


# Save the dictionary to a file for later use
json_output_path = os.path.join(analysis_dir, 'mesh_data.json')
with open(json_output_path, 'w') as json_file:
    json.dump(mesh_data, json_file, indent=4)

logger.info(f"Dictionary saved to: {json_output_path}")

# Prepare the CSV data
header = ['Mesh', 'TImax']
csv_data = [header]

for mesh_name, data in mesh_data.items():
    # Format the mesh name as "E076_E172 <> E097_E162"
    parts = re.findall(r'E\d{3}_E\d{3}', mesh_name)
    if len(parts) == 2:
        formatted_mesh_name = f"{parts[0]} <> {parts[1]}"
    else:
        formatted_mesh_name = mesh_name  # Fallback to the original name if the pattern doesn't match
    
    ti_max_value = data.get('TImax', '')
    
    row = [formatted_mesh_name, ti_max_value]
    csv_data.append(row)

# Write to CSV file
csv_output_path = os.path.join(analysis_dir, 'final_output.csv')
with open(csv_output_path, 'w', newline='') as file:
    writer = csv.writer(file)
    writer.writerows(csv_data)

logger.info(f"CSV file created successfully at: {csv_output_path}")

