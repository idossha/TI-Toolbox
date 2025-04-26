#!/Users/idohaber/Applications/SimNIBS-4.1/bin/simnibs_python
# -*- coding: utf-8 -*-
import argparse
import os
from simnibs import mesh_io

##############################################
# Ido Haber - ihaber@wisc.edu
# October 16, 2024
# Optimized for optimizer pipeline
# - Extracts both grey matter (GM) and white matter (WM) meshes and saves them in the same directory.
##############################################

def main(input_file, gm_output_file=None, wm_output_file=None):
    """
    Load the original mesh
    Crop the mesh to include grey matter (tag #2) and white matter (tag #1)
    Save these meshes to separate files
    """
    # Load the original mesh
    full_mesh = mesh_io.read_msh(input_file)
    
    # Extract grey matter mesh (tag #2)
    gm_mesh = full_mesh.crop_mesh(tags=[2])
    
    # Extract white matter mesh (tag #1)
    wm_mesh = full_mesh.crop_mesh(tags=[1])
    
    # Prepare output file paths
    input_dir = os.path.dirname(input_file)
    input_filename = os.path.basename(input_file)
    
    if gm_output_file is None:
        gm_output_file = os.path.join(input_dir, "grey_" + input_filename)
    if wm_output_file is None:
        wm_output_file = os.path.join(input_dir, "white_" + input_filename)
    
    # Save grey matter mesh
    mesh_io.write_msh(gm_mesh, gm_output_file)
    print(f"Grey matter mesh saved to {gm_output_file}")
    
    # Save white matter mesh
    mesh_io.write_msh(wm_mesh, wm_output_file)
    print(f"White matter mesh saved to {wm_output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Extract grey and white matter meshes from a full mesh file.')
    parser.add_argument('input_file', type=str, help='Path to the input mesh file')
    parser.add_argument('--gm_output_file', type=str, help='Path to the output grey matter mesh file', default=None)
    parser.add_argument('--wm_output_file', type=str, help='Path to the output white matter mesh file', default=None)
    args = parser.parse_args()
    main(args.input_file, args.gm_output_file, args.wm_output_file)

