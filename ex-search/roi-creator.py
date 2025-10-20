#!/usr/bin/env python3

import os
import csv
import sys
import subprocess


# Define color variables
BOLD = '\033[1m'
UNDERLINE = '\033[4m'
RESET = '\033[0m'
RED = '\033[0;31m'     # Red for errors
GREEN = '\033[0;32m'   # Green for success messages and prompts
CYAN = '\033[0;36m'    # Cyan for actions being performed
BOLD_CYAN = '\033[1;36m'

def save_roi_to_csv(roi_name, coordinates, directory):
    if not os.path.exists(directory):
        os.makedirs(directory)
    file_path = os.path.join(directory, f"{roi_name}.csv")
    try:
        with open(file_path, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(coordinates)
        return file_path
    except Exception as e:
        print(f"{RED}Error saving ROI to CSV: {e}{RESET}")
        sys.exit(1)

def list_existing_rois(directory):
    existing_rois = []
    if os.path.exists(directory):
        for file_name in os.listdir(directory):
            if file_name.endswith('.csv'):
                existing_rois.append(file_name[:-4])
    return existing_rois

def read_roi_coordinates(roi_name, directory):
    file_path = os.path.join(directory, f"{roi_name}.csv")
    if os.path.exists(file_path):
        with open(file_path, mode='r') as file:
            reader = csv.reader(file)
            coordinates = next(reader)
            coordinates = [float(coord.strip()) for coord in coordinates]
            return coordinates
    return []

def call_view_nifti(roi_directory):
    # Extract subject name from m2m directory path
    subject_name = os.path.basename(os.path.dirname(roi_directory)).replace('m2m_', '')
    
    # Get paths according to BIDS structure
    m2m_dir = os.path.dirname(roi_directory)
    subject_dir = os.path.dirname(m2m_dir)
    
    # Construct the path to the T1-weighted MRI in BIDS format
    t1_mri_path = os.path.join(subject_dir, 'anat', f'sub-{subject_name}_space-MNI305_T1w.nii.gz')
    
    # Check if the MRI file exists
    if not os.path.exists(t1_mri_path):
        # Fallback to m2m directory if BIDS T1 not found
        t1_mri_path = os.path.join(m2m_dir, 'T1.nii.gz')
        if not os.path.exists(t1_mri_path):
            print(f"{RED}Error: MRI file not found at {t1_mri_path}{RESET}")
            sys.exit(1)
    
    # Command to open Freeview
    freeview_command = ['freeview', t1_mri_path]
    
    try:
        # Start Freeview and wait for it to close, suppressing output
        print(f"{CYAN}Launching Freeview. Please select your ROI coordinates and close Freeview when done.{RESET}")
        with open(os.devnull, 'w') as FNULL:
            subprocess.call(freeview_command, stdout=FNULL, stderr=FNULL)
    except FileNotFoundError:
        print(f"{RED}Error: Freeview not found. Please ensure Freeview is installed and in your PATH.{RESET}")
        sys.exit(1)

def ensure_roi_list(directory, roi_filename):
    """Ensure the roi_list.txt file exists and contains the specified ROI."""
    roi_list_path = os.path.join(directory, 'roi_list.txt')
    try:
        # Create directory if it doesn't exist
        if not os.path.exists(directory):
            os.makedirs(directory)
        
        # If file doesn't exist or we're updating it
        with open(roi_list_path, 'w') as file:
            file.write(f"{roi_filename}\n")
        
        print(f"{CYAN}Updated ROI list file at {roi_list_path}{RESET}")
    except Exception as e:
        print(f"{RED}Error updating roi_list.txt: {e}{RESET}")
        sys.exit(1)

def main():
    # Check if the ROI directory is passed as an argument
    if len(sys.argv) < 2:
        print(f"{RED}Error: ROI directory path is required as an argument.{RESET}")
        sys.exit(1)

    roi_directory = sys.argv[1]

    # List existing ROIs
    existing_rois = list_existing_rois(roi_directory)

    # Display existing ROIs and their coordinates
    print(f"\n{BOLD_CYAN}Available ROIs:{RESET}")
    if existing_rois:
        for idx, roi in enumerate(existing_rois, start=1):
            coordinates = read_roi_coordinates(roi, roi_directory)
            print(f"  {idx}. {roi}: {coordinates}")
    else:
        print("  No existing ROIs found.")
    
    # Add option to add a new ROI
    option_add_new = len(existing_rois) + 1
    print(f"  {option_add_new}. Add a new ROI")
    print(" ")

    # Prompt user to select an ROI or add a new one
    while True:
        try:
            choice = int(input(f"{GREEN}Select an ROI by entering the corresponding number (1-{option_add_new}): {RESET}"))
            if 1 <= choice <= option_add_new:
                break
            else:
                print(f"{RED}Invalid selection. Please enter a number between 1 and {option_add_new}.{RESET}")
        except ValueError:
            print(f"{RED}Invalid input. Please enter a numeric value.{RESET}")

    if choice == option_add_new:
        # User chooses to add a new ROI
        while True:
            open_freeview = input(f"{GREEN}Do you want to open Freeview for visual reference? (yes/no): {RESET}").strip().lower()
            if open_freeview in ['yes', 'y']:
                call_view_nifti(roi_directory)
                break
            elif open_freeview in ['no', 'n']:
                break
            else:
                print(f"{RED}Invalid input. Please enter 'yes' or 'no'.{RESET}")

        # Prompt for ROI name after Freeview is launched (or closed)
        while True:
            roi_name = input(f"{GREEN}Enter the name of the new ROI: {RESET}").strip()
            if roi_name:
                break
            else:
                print(f"{RED}ROI name cannot be empty. Please enter a valid name.{RESET}")

        # Prompt user to enter coordinates
        while True:
            coords_input = input(f"{GREEN}Enter RAS coordinates for ROI '{roi_name}' (x y z): {RESET}")
            coords_input = coords_input.replace(',', ' ').split()
            if len(coords_input) != 3:
                print(f"{RED}Please enter exactly three values for x, y, and z.{RESET}")
                continue
            try:
                coordinates = [float(coord.strip()) for coord in coords_input]
                break
            except ValueError:
                print(f"{RED}Invalid input. Please enter numeric values for coordinates.{RESET}")

        # Save the ROI to a CSV file
        roi_file = save_roi_to_csv(roi_name, coordinates, roi_directory)
        roi_filename = os.path.basename(roi_file)

    else:
        # User selects an existing ROI
        selected_roi = existing_rois[choice - 1]
        coordinates = read_roi_coordinates(selected_roi, roi_directory)
        print(f"{GREEN}You have selected ROI '{selected_roi}' with coordinates {coordinates}.{RESET}")
        roi_filename = f"{selected_roi}.csv"

    # Always ensure the roi_list.txt is updated with the selected/created ROI
    ensure_roi_list(roi_directory, roi_filename)

if __name__ == "__main__":
    main()

