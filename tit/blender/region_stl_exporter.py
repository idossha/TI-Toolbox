#!/usr/bin/env simnibs_python
"""
MSH to STL Converter: Extract cortical regions from atlas and export as STL files

This script processes all cortical regions in a specified atlas, creates ROI meshes 
with preserved field values, and exports each region as an individual STL file.

Usage:
    python cortical_regions_to_stl.py --mesh /path/to/surface.msh --m2m /path/to/m2m_001 --atlas DK40 --field TI_max --output-dir /path/to/output

Dependencies:
    - numpy
    - simnibs
    - subprocess (for msh2cortex operations)
"""
import numpy as np
import simnibs

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Import shared utilities
from .utils import write_binary_stl, create_roi_mesh, extract_roi_region_no_zeros


def generate_surface_mesh(field_mesh_path, subject_dir):
    """
    Generate a surface mesh from the field mesh using msh2cortex if not already generated.
    This is used for cortical analysis.
    
    Returns:
        str: Path to the generated surface mesh file
    """
    # Get the base name of the input mesh
    input_name = os.path.basename(field_mesh_path)
    base_name = os.path.splitext(input_name)[0]
    
    # Create surface mesh in the same directory as the input mesh
    mesh_dir = os.path.dirname(field_mesh_path)
    surface_mesh_path = os.path.join(mesh_dir, f"{base_name}_central.msh")
    
    # If we already have a valid surface mesh, return it
    if os.path.exists(surface_mesh_path):
        return surface_mesh_path
        
    # Run msh2cortex command only for this specific field mesh
    cmd = [
        'msh2cortex',
        '-i', field_mesh_path,
        '-m', subject_dir,
        '-o', mesh_dir
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
    
    return surface_mesh_path



def process_region_to_stl(surface_mesh, atlas, region_name, field_name, output_dir, atlas_type, temp_dir):
    """
    Process a single region: create ROI mesh and convert to STL.
    
    Args:
        surface_mesh: The surface mesh object
        atlas: The atlas object
        region_name: Name of the region to process
        field_name: Name of the field to preserve
        output_dir: Output directory for STL files
        atlas_type: Type of atlas (for subdirectory)
        temp_dir: Temporary directory for intermediate files
        
    Returns:
        bool: True if successful, False if skipped
    """
    try:
        # Get ROI mask for this region
        roi_mask = atlas[region_name]
        
        # Check if we have any nodes in the ROI
        roi_nodes_count = np.sum(roi_mask)
        if roi_nodes_count == 0:
            return False
        
        # Get the field values within the ROI
        field_values = surface_mesh.field[field_name].value
        field_values_in_roi = field_values[roi_mask]
        
        # Filter for positive values in ROI
        positive_mask = field_values_in_roi > 0
        field_values_positive = field_values_in_roi[positive_mask]
        
        # Check if we have any positive values in the ROI
        positive_count = len(field_values_positive)
        if positive_count == 0:
            return False
        
        # Create ROI mesh
        temp_mesh_path = create_roi_mesh(surface_mesh, roi_mask, field_values, field_name, region_name, temp_dir)
        
        # Load the ROI mesh for STL conversion
        roi_mesh = simnibs.read_msh(temp_mesh_path)
        
        # Get the ROI field values for STL extraction
        roi_field_values = roi_mesh.field[field_name].value
        
        # Extract ROI region (remove zero values)
        vertices, faces = extract_roi_region_no_zeros(roi_mesh, roi_field_values, return_field_values=False)
        
        if vertices is None or faces is None:
            return False
        
        # Create output directory structure (unified: use 'regions' subfolder)
        cortical_stls_dir = os.path.join(output_dir, "cortical_stls")
        regions_output_dir = os.path.join(cortical_stls_dir, "regions")
        os.makedirs(regions_output_dir, exist_ok=True)
        
        # Write STL file
        stl_path = os.path.join(regions_output_dir, f"{region_name}.stl")
        write_binary_stl(vertices, faces, stl_path, "Generated from SimNIBS ROI mesh")
        
        # Clean up temporary mesh file
        os.remove(temp_mesh_path)
        
        return True
        
    except Exception as e:
        return False

def main():
    """Main function to process all cortical regions and export as STL files."""
    print("Starting...")
    parser = argparse.ArgumentParser(description='Convert cortical regions from atlas to STL files')
    parser.add_argument('--mesh', help='Input cortical surface mesh (.msh) from msh2cortex')
    parser.add_argument('--gm-mesh', help='Input tetrahedral GM .msh (volumetric); will run msh2cortex')
    parser.add_argument('--m2m', required=True, help='Subject m2m directory')
    parser.add_argument('--output-dir', required=True, help='Output directory for STL files')
    parser.add_argument('--atlas', default='DK40', help='Atlas name (default: DK40)')
    parser.add_argument('--surface', default='central', choices=['central', 'pial', 'white'], help='Cortical surface to extract when using --gm-mesh (default: central)')
    parser.add_argument('--msh2cortex', help='Path to msh2cortex executable (optional override)')
    parser.add_argument('--field', default='TI_max', help='Field name to preserve (default: TI_max)')
    parser.add_argument('--skip-regions', action='store_true', help='Do not export individual region STLs')
    parser.add_argument('--skip-whole-gm', action='store_true', help='Do not export the whole GM STL')
    parser.add_argument('--regions', help='Comma-separated list of region names to export (subset)')
    parser.add_argument('--keep-meshes', action='store_true', help='Keep individual cortical region meshes as .msh files')
    
    args = parser.parse_args()
    
    # Determine mesh path
    mesh_path = args.mesh
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Load the surface mesh
            surface_mesh = simnibs.read_msh(mesh_path)
            
            # Check if field exists
            if args.field not in surface_mesh.field:
                sys.exit(1)
            
            # Load the atlas
            atlas = simnibs.subject_atlas(args.atlas, args.m2m)
            
            # Process each region
            selected_regions = None
            if args.regions:
                selected_regions = set([r.strip() for r in args.regions.split(',') if r.strip()])
            if not args.skip_regions:
                print("Converting...")
                converted_count = 0
                for region_name in atlas.keys():
                    if selected_regions and region_name not in selected_regions:
                        continue
                    if process_region_to_stl(
                        surface_mesh, atlas, region_name, args.field, 
                        args.output_dir, args.atlas, temp_dir
                    ):
                        converted_count += 1
                print(f"Converted {converted_count} cortical regions.")
            
            # Export whole GM if requested
            if not args.skip_whole_gm:
                try:
                    # Build output path: gm_<simulation_name>.stl
                    base_name = os.path.basename(mesh_path)
                    name_wo_ext = os.path.splitext(base_name)[0]
                    # Attempt to parse simulation name before "_TI"
                    sim_name = name_wo_ext.split('_TI')[0]
                    cortical_stls_dir = os.path.join(args.output_dir, "cortical_stls")
                    os.makedirs(cortical_stls_dir, exist_ok=True)
                    # Unified whole GM filename
                    whole_stl_path = os.path.join(cortical_stls_dir, "whole_gm.stl")

                    # Extract all triangular elements from the surface mesh
                    triangular_elements = surface_mesh.elm.elm_type == 2
                    triangle_nodes = surface_mesh.elm.node_number_list[triangular_elements] - 1
                    if triangle_nodes.ndim == 1:
                        triangle_nodes = triangle_nodes.reshape(-1, 3)

                    unique_vertices = np.unique(triangle_nodes.flatten())
                    vertex_mapping = {old: new for new, old in enumerate(unique_vertices)}
                    remapped_triangles = np.array([
                        [vertex_mapping[idx] for idx in tri]
                    for tri in triangle_nodes])
                    vertices = surface_mesh.nodes.node_coord[unique_vertices]

                    write_binary_stl(vertices, remapped_triangles, whole_stl_path, "Generated from SimNIBS ROI mesh")
                except Exception:
                    pass
            
        except Exception as e:
            sys.exit(1)
    
    print(f"Output: {os.path.join(args.output_dir, 'cortical_stls')}")
    print("Finishing...")

if __name__ == "__main__":
    main()
