import pandas as pd
import sys
import re
import os
import csv

'''
Ido Haber - ihaber@wisc.edu
September 2, 2024
Optimized for optimizer pipeline

This script updates the output CSV file by merging data from the summary CSV.
It extracts specific metrics related to TI simulations and maps them to the 
corresponding mesh names in the output CSV.

Key Features:
- Maps mesh names from the summary CSV to the format used in the output CSV.
- Extracts specific percentile and focality metrics for inclusion in the output.
- Merges the data based on mesh names and updates the output CSV file.
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

def map_mesh_names(mesh_name):
    # Convert output.csv mesh name to summary.csv mesh name format
    return "TI_field_" + mesh_name.replace(" <> ", "_and_") + ".msh"

def update_output_csv(project_dir, subject_name):
    # Define paths according to BIDS structure
    simnibs_dir = os.path.join(project_dir, "derivatives", "SimNIBS")
    subject_dir = os.path.join(simnibs_dir, f"sub-{subject_name}")
    ex_search_dir = os.path.join(subject_dir, "ex-search")
    roi_dir = os.path.join(subject_dir, f"m2m_{subject_name}", "ROIs")
    
    # Get ROI coordinates from the first ROI file
    roi_list_path = os.path.join(roi_dir, 'roi_list.txt')
    try:
        with open(roi_list_path, 'r') as file:
            first_roi_name = file.readline().strip()
            # Extract just the filename without path
            first_roi_name = os.path.basename(first_roi_name)
            first_roi = os.path.join(roi_dir, first_roi_name)
    except FileNotFoundError:
        print(f"Error: ROI list file not found at {roi_list_path}")
        sys.exit(1)
    
    coords = get_roi_coordinates(first_roi)
    if not coords:
        print("Error: Could not read coordinates from ROI file")
        sys.exit(1)
    
    # Create directory name from coordinates
    coord_dir = f"xyz_{int(coords[0])}_{int(coords[1])}_{int(coords[2])}"
    opt_directory = os.path.join(ex_search_dir, coord_dir)
    
    summary_csv_path = os.path.join(opt_directory, "results", "summary.csv")
    output_csv_path = os.path.join(opt_directory, "output.csv")
    
    # Load the summary CSV
    summary_df = pd.read_csv(summary_csv_path)
    print("Summary CSV columns:", summary_df.columns.tolist())  # Print column names for debugging
    
    # Columns to extract
    columns_to_extract = [
        'PercentileValue_95', 'PercentileValue_99.9', 'FocalityValue_50', 'XYZ_Max'
    ]
    
    # Ensure the columns exist in the summary CSV
    missing_columns = [col for col in columns_to_extract if col not in summary_df.columns]
    if missing_columns:
        print(f"Error: Missing columns in summary.csv: {', '.join(missing_columns)}")
        sys.exit(1)
    
    # Extract the necessary columns and map FileName
    summary_df['Mesh'] = summary_df['FileName'].apply(lambda x: re.sub(r"TI_field_(.*?)\.msh", r"\1", x).replace("_and_", " <> "))
    extracted_df = summary_df[['Mesh'] + columns_to_extract]
    
    # Load the output CSV
    output_df = pd.read_csv(output_csv_path)
    print("Output CSV columns:", output_df.columns.tolist())  # Print column names for debugging
    
    # Ensure 'Mesh' exists in output_df
    if 'Mesh' not in output_df.columns:
        print("Error: 'Mesh' column is missing in output.csv")
        sys.exit(1)
    
    # Merge the dataframes on Mesh
    merged_df = pd.merge(output_df, extracted_df, on='Mesh', how='left')
    
    # Save the updated output CSV
    merged_df.to_csv(output_csv_path, index=False)
    print(f"Updated {output_csv_path} with new columns from summary.csv")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: update_output_csv.py <project_dir> <subject_name>")
        sys.exit(1)
    
    project_dir = sys.argv[1]
    subject_name = sys.argv[2]
    
    update_output_csv(project_dir, subject_name)

