#!/bin/bash

##############################################
# Ido Haber - ihaber@wisc.edu
# September 2, 2024
# Optimized for optimizer pipeline
#
# This script helps the user maintain a clean project directory 
# by allowing selective retention of .msh files and removing unwanted files 
# to reduce clutter.
#
# It prompts the user to select specific .msh files for simulation, 
# and optionally deletes the remaining .msh files and all .opt files.
##############################################


project_dir=$PROJECT_DIR
subject_name=$SUBJECT_NAME

# Define the opt directory
opt_directory="$project_dir/Simulations/opt_$subject_name"

# List all .msh files with numbers next to them
echo "Here are the .msh files in the opt directory:"
msh_files=($(ls "$opt_directory"/*.msh))
for i in "${!msh_files[@]}"; do
    echo "$i: ${msh_files[$i]}"
done

# Prompt the user to select .msh files to simulate
read -p "Enter the numbers of the .msh files you want to simulate (separated by spaces): " -a selected_files

# Validate the selection
for num in "${selected_files[@]}"; do
    if ! [[ $num =~ ^[0-9]+$ ]] || [[ $num -lt 0 ]] || [[ $num -ge ${#msh_files[@]} ]]; then
        echo "Invalid selection: $num. Exiting."
        exit 1
    fi
done

# Display selected files
echo "You have selected the following files:"
for num in "${selected_files[@]}"; do
    echo "${msh_files[$num]}"
done

# Prompt the user if they want to delete the remaining .msh files and all .opt files
read -p "Do you want to delete the rest of the .msh files and all the .opt files? (y/n) " delete_choice
case "$delete_choice" in 
  y|Y ) 
    read -p "Are you sure you want to delete the remaining .msh files and all the .opt files? This action cannot be undone. (y/n) " confirm_delete
    case "$confirm_delete" in
      y|Y ) 
        # Delete remaining .msh files
        for i in "${!msh_files[@]}"; do
            if [[ ! " ${selected_files[@]} " =~ " $i " ]]; then
                rm -f "${msh_files[$i]}"
            fi
        done
        # Delete all .opt files
        rm -f "$opt_directory"/*.opt
        echo "Remaining .msh files and all .opt files deleted."
        ;;
      n|N ) 
        echo "Files not deleted."
        ;;
      * ) 
        echo "Invalid choice. Files not deleted."
        ;;
    esac
    ;;
  n|N ) 
    echo "Files not deleted."
    ;;
  * ) 
    echo "Invalid choice. Files not deleted."
    ;;
esac

echo "All tasks completed successfully."

