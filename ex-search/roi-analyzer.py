#!/usr/bin/env python3

import os
import re
import pandas as pd
import subprocess
import json
import csv
import sys
import time
import numpy as np
import logging

# Add logging utility import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils import logging_util


'''
Ido Haber - ihaber@wisc.edu

This script analyzes mesh files in the simulation directory by extracting 
fields at specific ROI coordinates and compiling the results into a structured format.

Key Features:
- Reads ROI files and extracts TImax values from mesh files.
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
        # Use logger if available, otherwise print
        try:
            logger.error(f"Error reading coordinates from {roi_file}: {e}")
        except NameError:
            print(f"Error reading coordinates from {roi_file}: {e}")
        return None

def generate_roi_sphere_points(center_coords, radius=3.0, num_points=20):
    """Generate multiple sampling points in a sphere around the ROI center.
    
    Args:
        center_coords: [x, y, z] center coordinates
        radius: Radius in mm for sampling sphere
        num_points: Number of points to sample within sphere
    
    Returns:
        List of [x, y, z] coordinates
    """
    points = [center_coords]  # Always include the center point
    
    # Generate random points in a sphere
    np.random.seed(42)  # For reproducible results
    for _ in range(num_points - 1):
        # Generate random point in unit sphere using rejection sampling
        while True:
            x = np.random.uniform(-1, 1)
            y = np.random.uniform(-1, 1) 
            z = np.random.uniform(-1, 1)
            if x*x + y*y + z*z <= 1:
                break
        
        # Scale to desired radius and translate to center
        scaled_point = [
            center_coords[0] + x * radius,
            center_coords[1] + y * radius, 
            center_coords[2] + z * radius
        ]
        points.append(scaled_point)
    
    return points

# Get the project directory and subject name from environment variables
project_dir = os.getenv('PROJECT_DIR')
subject_name = os.getenv('SUBJECT_NAME')

if not project_dir or not subject_name:
    print("Error: PROJECT_DIR and SUBJECT_NAME environment variables must be set")
    sys.exit(1)

# Initialize logger
# Check if log file path is provided through environment variable (from GUI)
shared_log_file = os.environ.get('TI_LOG_FILE')

if shared_log_file:
    # Use shared log file and shared logger name for unified logging
    logger_name = 'Ex-Search'
    log_file = shared_log_file
    
    # When running from GUI, create a file-only logger to avoid console output
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    
    # Remove any existing handlers
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    
    # Add only file handler (no console handler) when running from GUI
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(file_handler)
else:
    # CLI usage: create individual log file with both console and file output
    logger_name = 'ROI-Analyzer'
    time_stamp = time.strftime('%Y%m%d_%H%M%S')
    log_file = f'roi_analyzer_{time_stamp}.log'
    logger = logging_util.get_logger(logger_name, log_file, overwrite=False)

# Configure external loggers
logging_util.configure_external_loggers(['simnibs'], logger)

# Set the directories based on BIDS structure
simnibs_dir = os.path.join(project_dir, "derivatives", "SimNIBS")
subject_dir = os.path.join(simnibs_dir, f"sub-{subject_name}")
m2m_dir = os.path.join(subject_dir, f"m2m_{subject_name}")
ex_search_dir = os.path.join(subject_dir, "ex-search")
roi_directory = os.path.join(m2m_dir, 'ROIs')

# Read the list of ROI files - use custom file if provided, otherwise default roi_list.txt
custom_roi_list = os.getenv('ROI_LIST_FILE')
if custom_roi_list and os.path.exists(custom_roi_list):
    roi_list_path = custom_roi_list
    logger.info(f"Using custom ROI list: {roi_list_path}")
else:
    roi_list_path = os.path.join(roi_directory, 'roi_list.txt')
    logger.info(f"Using default ROI list: {roi_list_path}")

try:
    with open(roi_list_path, 'r') as file:
        position_files = [os.path.join(roi_directory, line.strip()) for line in file]
except FileNotFoundError:
    logger.error(f"ROI list file not found at {roi_list_path}")
    sys.exit(1)

# Verify that all ROI files exist
missing_files = [f for f in position_files if not os.path.exists(f)]
if missing_files:
    logger.error("The following ROI files are missing:")
    for f in missing_files:
        logger.error(f"  - {f}")
    sys.exit(1)

# Get directory name - use GUI environment variables if available, otherwise fall back to coordinates
roi_name = os.getenv('ROI_NAME')
selected_eeg_net = os.getenv('SELECTED_EEG_NET')

if roi_name and selected_eeg_net:
    # Use GUI-provided ROI name and EEG net for directory naming
    output_dir_name = f"{roi_name}_{selected_eeg_net}"
    opt_directory = os.path.join(ex_search_dir, output_dir_name)
    logger.info(f"Using GUI-selected ROI directory: {output_dir_name}")
else:
    # CLI usage: coordinate-based naming
    first_roi_file = position_files[0]
    coords = get_roi_coordinates(first_roi_file)
    if not coords:
        logger.error("Could not read coordinates from ROI file")
        sys.exit(1)

    # Create directory name from coordinates
    coord_dir = f"xyz_{int(coords[0])}_{int(coords[1])}_{int(coords[2])}"
    opt_directory = os.path.join(ex_search_dir, coord_dir)
    logger.info(f"Using coordinate-based directory: {coord_dir}")

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

        # Get ROI center coordinates and generate sampling sphere
        roi_coords = get_roi_coordinates(pos_file)
        if not roi_coords:
            logger.error(f"Could not read ROI coordinates from {pos_file}")
            continue
            
        # Generate multiple sampling points in a 3mm sphere around ROI center
        sampling_points = generate_roi_sphere_points(roi_coords, radius=3.0, num_points=20)
        
        # Create temporary multi-point coordinates file
        temp_coords_file = os.path.join(roi_directory, f"{pos_base}_sampling_points.csv")
        try:
            with open(temp_coords_file, 'w', newline='') as f:
                writer = csv.writer(f)
                for point in sampling_points:
                    writer.writerow([f"{point[0]:.3f}", f"{point[1]:.3f}", f"{point[2]:.3f}"])
        except Exception as e:
            logger.error(f"Error creating temporary coordinates file: {e}")
            continue

        # Run the command to generate CSV files using multiple sampling points
        try:
            cmd = ["get_fields_at_coordinates", "-s", temp_coords_file, "-m", msh_file_path, "--method", "linear"]
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running get_fields_at_coordinates: {e}")
            continue
        finally:
            # Clean up temporary file
            if os.path.exists(temp_coords_file):
                os.remove(temp_coords_file)
        
        # The generated CSV files will be in the current directory with names based on the sampling points file
        sampling_base = f"{pos_base}_sampling_points"
        ti_max_csv = os.path.join(roi_directory, f"{sampling_base}_TImax.csv")
        from_volume_csv = os.path.join(roi_directory, f"{sampling_base}_from_volume.csv")
        
        # Process the TImax CSV file
        if os.path.exists(ti_max_csv):
            try:
                # Read the CSV file into a dataframe without headers
                df_ti_max = pd.read_csv(ti_max_csv, header=None)
                
                # Ensure all data can be converted to float
                df_ti_max = df_ti_max.apply(pd.to_numeric, errors='coerce')
                df_ti_max = df_ti_max.dropna()  # Drop rows with non-numeric data
                
                # Extract values from the dataframe
                ti_max_values = df_ti_max[0].tolist()  # Assuming the TImax CSV has values in the first column
                
                if ti_max_values:
                    # Calculate both max and mean for ROI analysis
                    roi_max = max(ti_max_values)
                    roi_mean = sum(ti_max_values) / len(ti_max_values)
                    
                    # Store both values in the dictionary
                    mesh_data[mesh_key]['TImax_ROI'] = roi_max
                    mesh_data[mesh_key]['TImean_ROI'] = roi_mean
                else:
                    mesh_data[mesh_key]['TImax_ROI'] = None
                    mesh_data[mesh_key]['TImean_ROI'] = None
                    logger.warning(f"No valid TI values found for {mesh_key}")
                    
            except Exception as e:
                logger.error(f"Error processing TImax file {ti_max_csv}: {e}")
                mesh_data[mesh_key]['TImax_ROI'] = None
                mesh_data[mesh_key]['TImean_ROI'] = None
            finally:
                if os.path.exists(ti_max_csv):
                    os.remove(ti_max_csv)
        else:
            logger.warning(f"TImax CSV file {ti_max_csv} not found")
            mesh_data[mesh_key]['TImax_ROI'] = None
            mesh_data[mesh_key]['TImean_ROI'] = None


# Save the dictionary to a file for later use
json_output_path = os.path.join(analysis_dir, 'mesh_data.json')
with open(json_output_path, 'w') as json_file:
    json.dump(mesh_data, json_file, indent=4)

logger.info(f"Dictionary saved to: {json_output_path}")

# Prepare the CSV data with properly named columns
header = ['Mesh', 'TImax_ROI', 'TImean_ROI']
csv_data = [header]

for mesh_name, data in mesh_data.items():
    # Format the mesh name to match mesh field analyzer format
    # Convert "TI_field_O1_F7_and_T7_Pz.msh" to "O1_F7 <> T7_Pz"
    formatted_mesh_name = re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name).replace("_and_", " <> ")
    
    # Ensure we use proper column names for ROI field values
    ti_max_roi = data.get('TImax_ROI', '')
    ti_mean_roi = data.get('TImean_ROI', '')
    
    # Format numbers properly if they exist
    if ti_max_roi and ti_max_roi != '':
        ti_max_roi = f"{float(ti_max_roi):.4f}"
    if ti_mean_roi and ti_mean_roi != '':
        ti_mean_roi = f"{float(ti_mean_roi):.4f}"
    
    row = [formatted_mesh_name, ti_max_roi, ti_mean_roi]
    csv_data.append(row)

# Write to CSV file
csv_output_path = os.path.join(analysis_dir, 'final_output.csv')
with open(csv_output_path, 'w', newline='') as file:
    writer = csv.writer(file)
    writer.writerows(csv_data)

logger.info(f"CSV file created successfully at: {csv_output_path}")
logger.info(f"Enhanced ROI analysis completed with {len(mesh_data)} simulations")
logger.info("ROI sampling: 3mm radius sphere with 20 points around ROI center")
logger.info("ROI metrics: TImax_ROI (peak field in ROI), TImean_ROI (average field in ROI)")

