"""
Atlas processing utilities for neuroimaging

This module contains functions for:
- Loading and resampling atlases
- Computing atlas overlap with significant clusters
"""

import numpy as np
import nibabel as nib
from nibabel.processing import resample_from_to
import os


def check_and_resample_atlas(atlas_img, reference_img, atlas_name, verbose=True):
    """
    Check if atlas dimensions match reference, resample if needed
    
    Parameters:
    -----------
    atlas_img : nibabel image
        Atlas to check/resample
    reference_img : nibabel image
        Reference image (from subject data)
    atlas_name : str
        Name of atlas for logging
    verbose : bool
        Print information
    
    Returns:
    --------
    atlas_data : ndarray
        Atlas data in correct dimensions
    """
    atlas_shape = atlas_img.shape
    ref_shape = reference_img.shape
    
    if verbose:
        print(f"  Atlas shape: {atlas_shape}")
        print(f"  Reference shape: {ref_shape[:3]}")
    
    # Check if dimensions match (only compare spatial dimensions)
    if atlas_shape[:3] != ref_shape[:3]:
        if verbose:
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
            if verbose:
                print(f"  ✓ Resampled to: {atlas_data.shape}")
                
        except Exception as e:
            if verbose:
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
            
            if verbose:
                print(f"  ✓ Resampled to: {atlas_data.shape}")
    else:
        if verbose:
            print(f"  ✓ Dimensions match!")
        atlas_data = atlas_img.get_fdata().astype(int)
        
        # Ensure 3D
        if len(atlas_data.shape) > 3:
            atlas_data = atlas_data[:, :, :, 0]
    
    return atlas_data


def atlas_overlap_analysis(sig_mask, atlas_files, data_dir, reference_img=None, verbose=True):
    """
    Analyze overlap between significant voxels and atlas regions
    
    Parameters:
    -----------
    sig_mask : ndarray (x, y, z)
        Binary mask of significant voxels
    atlas_files : list of str
        List of atlas file names
    data_dir : str
        Directory containing atlas files
    reference_img : nibabel image, optional
        Reference image for resampling
    verbose : bool
        Print progress information
    
    Returns:
    --------
    results : dict
        Dictionary mapping atlas names to DataFrames of region overlap statistics
    """
    if verbose:
        print("\n" + "="*60)
        print("ATLAS OVERLAP ANALYSIS")
        print("="*60)
    
    results = {}
    
    for atlas_file in atlas_files:
        atlas_path = os.path.join(data_dir, atlas_file)
        if not os.path.exists(atlas_path):
            if verbose:
                print(f"Warning: Atlas file not found - {atlas_file}")
            continue
        
        if verbose:
            print(f"\n--- {atlas_file} ---")
        atlas_img = nib.load(atlas_path)
        
        # Check dimensions and resample if needed
        if reference_img is not None:
            atlas_data = check_and_resample_atlas(atlas_img, reference_img, atlas_file, verbose)
        else:
            atlas_data = atlas_img.get_fdata().astype(int)
        
        # Get unique regions (excluding 0 = background)
        regions = np.unique(atlas_data[atlas_data > 0])
        
        region_counts = []
        for region_id in regions:
            region_mask = (atlas_data == region_id)
            overlap = np.sum(sig_mask & region_mask)
            
            if overlap > 0:
                region_counts.append({
                    'region_id': int(region_id),
                    'overlap_voxels': int(overlap),
                    'region_size': int(np.sum(region_mask))
                })
        
        # Sort by overlap count
        region_counts = sorted(region_counts, key=lambda x: x['overlap_voxels'], reverse=True)
        
        if verbose:
            print(f"\nTop regions by significant voxel count:")
            for i, r in enumerate(region_counts[:15], 1):
                pct = 100 * r['overlap_voxels'] / r['region_size']
                print(f"{i:2d}. Region {r['region_id']:3d}: {r['overlap_voxels']:4d} sig. voxels "
                      f"({pct:.1f}% of region)")
        
        results[atlas_file] = region_counts
    
    return results

