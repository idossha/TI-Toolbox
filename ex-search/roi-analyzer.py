
#!/usr/bin/env python3

import os
import re
import pandas as pd
import subprocess
import json
import csv


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

# Get the project directory and subject name from environment variables
project_dir = os.getenv('PROJECT_DIR')
subject_name = os.getenv('SUBJECT_NAME')

# Set the directories based on project directory and subject name
opt_directory = os.path.join(project_dir, f'Simulations/opt_{subject_name}')
roi_directory = os.path.join(project_dir, f'Subjects/m2m_{subject_name}/ROIs')

# Read the list of ROI files from the correct ROI directory
roi_list_path = os.path.join(roi_directory, 'roi_list.txt')
with open(roi_list_path, 'r') as file:
    position_files = [line.strip() for line in file]

# Create a dictionary to hold the data
mesh_data = {}

# Get the list of .msh files in the opt directory and count the total number
msh_files = [f for f in os.listdir(opt_directory) if f.endswith('.msh')]
total_files = len(msh_files)  # Total number of files to process

# Iterate over all .msh files in the opt directory with progress indicator
for i, msh_file in enumerate(msh_files):
    msh_file_path = os.path.join(opt_directory, msh_file)

    # Progress indicator (formatted as 001/100)
    progress_str = f"{i+1:03}/{total_files}"
    print(f"{progress_str} Processing {msh_file_path}")
    
    # Use only the file name part for mesh_key
    mesh_key = os.path.basename(msh_file_path)
    mesh_data[mesh_key] = {}

    # Iterate over all position files
    for pos_file in position_files:
        pos_base = os.path.splitext(os.path.basename(pos_file))[0]  # Extract the base name of the position file without extension
        print(f"  Using position file {pos_file}")

        # Run the command to generate CSV files in the ROI directory
        try:
            print(f"Running command: get_fields_at_coordinates -s {pos_file} -m {msh_file_path} --method linear")
            subprocess.run(["get_fields_at_coordinates", "-s", pos_file, "-m", msh_file_path, "--method", "linear"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running get_fields_at_coordinates: {e}")
            continue
        
        # The generated CSV files will be in the ROI directory with names based on the position file and field names
        ti_max_csv = os.path.join(roi_directory, f"{pos_base}_TImax.csv")
        from_volume_csv = os.path.join(roi_directory, f"{pos_base}_from_volume.csv")
        
        # Process the TImax CSV file
        if os.path.exists(ti_max_csv):
            print(f"Found TImax CSV file: {ti_max_csv}")
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
                print(f"Error processing TImax file {ti_max_csv}: {e}")
            finally:
                os.remove(ti_max_csv)
        else:
            print(f"    TImax CSV file {ti_max_csv} not found. Skipping this file.")


# Save the dictionary to a file for later use
json_output_path = os.path.join(opt_directory, 'mesh_data.json')
with open(json_output_path, 'w') as json_file:
    json.dump(mesh_data, json_file, indent=4)

print(f"Dictionary saved to {json_output_path}")

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
csv_output_path = os.path.join(opt_directory, 'output.csv')
with open(csv_output_path, 'w', newline='') as file:
    writer = csv.writer(file)
    writer.writerows(csv_data)

print(f'CSV file created successfully at {csv_output_path}.')

