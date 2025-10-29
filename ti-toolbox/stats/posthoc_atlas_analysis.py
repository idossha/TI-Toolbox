#!/usr/bin/env python3
"""
Post-hoc atlas overlap analysis for existing significant voxel masks

This script allows you to test an existing significant voxel mask against 
one or more atlases without re-running the full statistical analysis.

Usage:
    python posthoc_atlas_analysis.py --mask <mask_file> --atlases <atlas1> <atlas2> ...

Or edit the configuration section below and run:
    python posthoc_atlas_analysis.py
"""

import numpy as np
import pandas as pd
import nibabel as nib
from nibabel.processing import resample_from_to
import os
import sys
import argparse

def check_and_resample_atlas(atlas_img, reference_img, atlas_name):
    """
    Check if atlas dimensions match reference, resample if needed
    """
    atlas_shape = atlas_img.shape
    ref_shape = reference_img.shape
    
    print(f"  Atlas shape: {atlas_shape}")
    print(f"  Reference shape: {ref_shape[:3]}")
    
    # Check if dimensions match (only compare spatial dimensions)
    if atlas_shape[:3] != ref_shape[:3]:
        print(f"  ⚠ Dimensions don't match! Resampling atlas...")
        
        try:
            # Create a clean 3D reference image for resampling
            # Extract just the first 3D volume if reference is 4D
            if len(ref_shape) > 3:
                ref_data_3d = reference_img.get_fdata()[:, :, :, 0]
            else:
                ref_data_3d = reference_img.get_fdata()
            
            # Create a new 3D reference image with standard 4x4 affine
            ref_img_3d = nib.Nifti1Image(
                ref_data_3d.astype(np.float32),
                reference_img.affine[:4, :4],  # Ensure 4x4 affine matrix
                None
            )
            
            # Ensure atlas is also 3D with 4x4 affine
            atlas_data_raw = atlas_img.get_fdata()
            if len(atlas_data_raw.shape) > 3:
                atlas_data_raw = atlas_data_raw[:, :, :, 0]
            
            atlas_img_3d = nib.Nifti1Image(
                atlas_data_raw.astype(np.float32),
                atlas_img.affine[:4, :4],  # Ensure 4x4 affine matrix
                None
            )
            
            # Resample atlas to match reference image
            resampled_atlas = resample_from_to(
                atlas_img_3d, 
                ref_img_3d, 
                order=0  # Use nearest neighbor for label data
            )
            
            atlas_data = resampled_atlas.get_fdata().astype(int)
            print(f"  ✓ Resampled to: {atlas_data.shape}")
            
        except Exception as e:
            print(f"  ✗ Resampling failed: {e}")
            print(f"  Attempting alternative resampling method...")
            
            # Fallback: use scipy for resampling
            from scipy.ndimage import zoom
            
            atlas_data_raw = atlas_img.get_fdata()
            if len(atlas_data_raw.shape) > 3:
                atlas_data_raw = atlas_data_raw[:, :, :, 0]
            
            # Calculate zoom factors
            zoom_factors = [
                ref_shape[i] / atlas_shape[i] for i in range(3)
            ]
            
            # Resample using nearest neighbor
            atlas_data = zoom(atlas_data_raw, zoom_factors, order=0).astype(int)
            
            print(f"  ✓ Resampled to: {atlas_data.shape}")
    else:
        print(f"  ✓ Dimensions match!")
        atlas_data = atlas_img.get_fdata().astype(int)
        
        # Ensure 3D
        if len(atlas_data.shape) > 3:
            atlas_data = atlas_data[:, :, :, 0]
    
    return atlas_data

def posthoc_atlas_overlap(mask_file, atlas_files, output_dir=None):
    """
    Perform atlas overlap analysis on an existing significant voxel mask
    
    Parameters:
    -----------
    mask_file : str
        Path to binary mask NIfTI file
    atlas_files : list of str
        Paths to atlas NIfTI files
    output_dir : str, optional
        Directory to save CSV outputs (defaults to mask file directory)
    """
    
    print("="*70)
    print("POST-HOC ATLAS OVERLAP ANALYSIS")
    print("="*70)
    
    # Load mask
    print(f"\nLoading mask: {mask_file}")
    mask_img = nib.load(mask_file)
    sig_mask = mask_img.get_fdata().astype(bool)
    
    total_sig_voxels = np.sum(sig_mask)
    print(f"Total significant voxels: {total_sig_voxels}")
    
    if total_sig_voxels == 0:
        print("Warning: No significant voxels in mask!")
        return
    
    # Set output directory
    if output_dir is None:
        output_dir = os.path.dirname(mask_file)
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Process each atlas
    all_results = {}
    
    for atlas_file in atlas_files:
        if not os.path.exists(atlas_file):
            print(f"\n⚠ Warning: Atlas file not found - {atlas_file}")
            continue
        
        atlas_name = os.path.basename(atlas_file)
        print(f"\n{'='*70}")
        print(f"Processing: {atlas_name}")
        print(f"{'='*70}")
        
        # Load atlas
        atlas_img = nib.load(atlas_file)
        
        # Check dimensions and resample if needed
        atlas_data = check_and_resample_atlas(atlas_img, mask_img, atlas_name)
        
        # Get unique regions
        regions = np.unique(atlas_data[atlas_data > 0])
        print(f"Found {len(regions)} regions in atlas")
        
        # Calculate overlap for each region
        results = []
        for region_id in regions:
            region_mask = (atlas_data == region_id)
            region_size = np.sum(region_mask)
            overlap = np.sum(sig_mask & region_mask)
            
            if overlap > 0:
                pct_of_region = 100 * overlap / region_size
                pct_of_significant = 100 * overlap / total_sig_voxels
                
                results.append({
                    'region_id': int(region_id),
                    'overlap_voxels': int(overlap),
                    'region_total_voxels': int(region_size),
                    'pct_of_region': round(pct_of_region, 2),
                    'pct_of_all_significant': round(pct_of_significant, 2)
                })
        
        if not results:
            print(f"No overlapping regions found for {atlas_name}")
            continue
        
        # Convert to DataFrame and sort
        df = pd.DataFrame(results)
        df = df.sort_values('overlap_voxels', ascending=False)
        
        # Save to CSV
        atlas_basename = os.path.splitext(os.path.basename(atlas_file))[0]
        if atlas_basename.endswith('.nii'):
            atlas_basename = os.path.splitext(atlas_basename)[0]
        
        output_file = os.path.join(output_dir, f"posthoc_overlap_{atlas_basename}.csv")
        df.to_csv(output_file, index=False)
        
        print(f"\n✓ Saved {len(df)} regions to: {output_file}")
        print(f"\nTop 10 regions by overlap:")
        for i, (idx, row) in enumerate(df.head(10).iterrows(), 1):
            print(f"  {i:2d}. Region {int(row['region_id']):4d}: "
                  f"{int(row['overlap_voxels']):5d} voxels "
                  f"({row['pct_of_region']:5.1f}% of region, "
                  f"{row['pct_of_all_significant']:5.1f}% of sig. voxels)")
        
        all_results[atlas_name] = df
    
    # Generate summary report
    summary_file = os.path.join(output_dir, "posthoc_atlas_summary.txt")
    with open(summary_file, 'w') as f:
        f.write("="*70 + "\n")
        f.write("POST-HOC ATLAS OVERLAP ANALYSIS SUMMARY\n")
        f.write("="*70 + "\n\n")
        
        f.write(f"Mask file: {mask_file}\n")
        f.write(f"Total significant voxels: {total_sig_voxels}\n\n")
        
        for atlas_name, df in all_results.items():
            f.write(f"\n{atlas_name}\n")
            f.write("-"*70 + "\n")
            f.write(f"Regions with overlap: {len(df)}\n\n")
            f.write("Top 20 regions:\n")
            for i, (idx, row) in enumerate(df.head(20).iterrows(), 1):
                f.write(f"{i:2d}. Region {int(row['region_id']):4d}: "
                       f"{int(row['overlap_voxels']):5d} voxels "
                       f"({row['pct_of_region']:5.1f}% of region)\n")
            f.write("\n")
    
    print(f"\n{'='*70}")
    print("POST-HOC ANALYSIS COMPLETE!")
    print(f"{'='*70}")
    print(f"Summary saved to: {summary_file}")
    print(f"\nCSV files saved to: {output_dir}")

def main():
    parser = argparse.ArgumentParser(
        description='Post-hoc atlas overlap analysis for significant voxel masks'
    )
    parser.add_argument('--mask', type=str, 
                       help='Path to binary mask NIfTI file')
    parser.add_argument('--atlases', nargs='+', type=str,
                       help='Paths to atlas NIfTI files')
    parser.add_argument('--output', type=str, default=None,
                       help='Output directory for results (default: same as mask)')
    
    args = parser.parse_args()
    
    # If no arguments provided, use default configuration
    if args.mask is None and args.atlases is None:
        print("No arguments provided. Using default configuration...")
        print("(Edit this script or use --mask and --atlases arguments)\n")
        
        # DEFAULT CONFIGURATION - EDIT THESE
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(project_root, "output")
        assets_dir = os.path.join(project_root, "assets")
        
        mask_file = os.path.join(output_dir, "significant_voxels_mask.nii.gz")
        
        # List all atlases you want to test
        atlas_files = [
            os.path.join(assets_dir, "HarvardOxford-cort-maxprob-thr0-1mm.nii.gz"),
            os.path.join(assets_dir, "Talairach-labels-1mm.nii.gz"),
            os.path.join(assets_dir, "MNI_Glasser_HCP_v1.0.nii.gz"),
            # Add more atlases here as needed
            # os.path.join(assets_dir, "your_new_atlas.nii.gz"),
        ]
        
    else:
        # Use command line arguments
        mask_file = args.mask
        atlas_files = args.atlases
        output_dir = args.output
        
        if not os.path.exists(mask_file):
            print(f"Error: Mask file not found: {mask_file}")
            sys.exit(1)
    
    # Run analysis
    posthoc_atlas_overlap(mask_file, atlas_files, output_dir)

if __name__ == "__main__":
    main()

