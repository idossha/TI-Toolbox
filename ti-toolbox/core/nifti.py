#!/usr/bin/env python3
"""
NIfTI Utilities Module

Centralized utilities for NIfTI file operations in TI-Toolbox.
Provides reusable functions for loading, saving, averaging, and manipulating
NIfTI files with consistent error handling and memory management.
"""

import os
import sys
import gc
import numpy as np
import nibabel as nib
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Union

# Import TI-Toolbox core modules
try:
    from . import get_path_manager
    from . import constants as const
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core import get_path_manager
    from core import constants as const


# ==============================================================================
# LOADING FUNCTIONS
# ==============================================================================

def load_nifti(filepath: str, dtype=np.float32) -> Tuple[np.ndarray, nib.Nifti1Image]:
    """
    Load a single NIfTI file
    
    Parameters:
    -----------
    filepath : str
        Path to NIfTI file (.nii or .nii.gz)
    dtype : numpy dtype, optional
        Data type to load (default: float32 for memory efficiency)
    
    Returns:
    --------
    data : ndarray
        NIfTI data array
    img : nibabel Nifti1Image
        NIfTI image object (for affine/header)
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"NIfTI file not found: {filepath}")
    
    img = nib.load(filepath)
    data = img.get_fdata(dtype=dtype)
    
    # Ensure 3D data (squeeze out extra dimensions if present)
    while data.ndim > 3:
        data = np.squeeze(data, axis=-1)
    
    return data, img


def load_multiple_niftis(
    filepaths: List[str],
    dtype=np.float32,
    verify_shape: bool = True,
    verify_affine: bool = True
) -> Tuple[np.ndarray, nib.Nifti1Image]:
    """
    Load multiple NIfTI files and stack them into a 4D array
    
    Parameters:
    -----------
    filepaths : list of str
        List of NIfTI file paths
    dtype : numpy dtype, optional
        Data type to load (default: float32)
    verify_shape : bool, optional
        Verify all files have the same shape (default: True)
    verify_affine : bool, optional
        Verify all files have the same affine (default: True)
    
    Returns:
    --------
    data_4d : ndarray (x, y, z, n_files)
        4D array with all loaded data
    template_img : nibabel Nifti1Image
        Template image from first file (for affine/header)
    """
    if len(filepaths) == 0:
        raise ValueError("No files provided to load")
    
    # Load first file as reference
    first_data, first_img = load_nifti(filepaths[0], dtype=dtype)
    reference_shape = first_data.shape
    reference_affine = first_img.affine
    
    data_list = [first_data]
    
    # Load remaining files
    for filepath in filepaths[1:]:
        data, img = load_nifti(filepath, dtype=dtype)
        
        # Verify shape
        if verify_shape and data.shape != reference_shape:
            raise ValueError(
                f"Shape mismatch: {os.path.basename(filepath)} has shape {data.shape}, "
                f"expected {reference_shape}"
            )
        
        # Verify affine
        if verify_affine and not np.allclose(img.affine, reference_affine, atol=1e-6):
            raise ValueError(
                f"Affine mismatch: {os.path.basename(filepath)} has different affine "
                f"than reference"
            )
        
        data_list.append(data)
        del img  # Free memory
    
    # Stack into 4D array
    data_4d = np.stack(data_list, axis=-1).astype(dtype)
    
    # Clean up
    del data_list
    gc.collect()
    
    return data_4d, first_img


# ==============================================================================
# SAVING FUNCTIONS
# ==============================================================================

def save_nifti(
    data: np.ndarray,
    affine: np.ndarray,
    header: nib.Nifti1Header,
    filepath: str,
    dtype=np.float32
) -> str:
    """
    Save data as NIfTI file
    
    Parameters:
    -----------
    data : ndarray
        Data to save
    affine : ndarray
        Affine transformation matrix
    header : nibabel header
        NIfTI header
    filepath : str
        Output file path
    dtype : numpy dtype, optional
        Data type for output (default: float32)
    
    Returns:
    --------
    filepath : str
        Path to saved file
    """
    # Create output directory if needed
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    
    # Create and save image
    img = nib.Nifti1Image(data.astype(dtype), affine, header)
    nib.save(img, filepath)
    
    return filepath


def save_nifti_like(
    data: np.ndarray,
    reference_img: nib.Nifti1Image,
    filepath: str,
    dtype=np.float32
) -> str:
    """
    Save data as NIfTI using reference image for affine/header
    
    Parameters:
    -----------
    data : ndarray
        Data to save
    reference_img : nibabel Nifti1Image
        Reference image for affine and header
    filepath : str
        Output file path
    dtype : numpy dtype, optional
        Data type for output (default: float32)
    
    Returns:
    --------
    filepath : str
        Path to saved file
    """
    return save_nifti(data, reference_img.affine, reference_img.header, filepath, dtype)


# ==============================================================================
# AVERAGING FUNCTIONS
# ==============================================================================

def average_niftis(
    filepaths: List[str],
    dtype=np.float32,
    verify_shape: bool = True,
    verify_affine: bool = True
) -> Tuple[np.ndarray, nib.Nifti1Image]:
    """
    Average multiple NIfTI files
    
    Parameters:
    -----------
    filepaths : list of str
        List of NIfTI file paths to average
    dtype : numpy dtype, optional
        Data type for computation (default: float32)
    verify_shape : bool, optional
        Verify all files have the same shape (default: True)
    verify_affine : bool, optional
        Verify all files have the same affine (default: True)
    
    Returns:
    --------
    average_data : ndarray
        Averaged data
    template_img : nibabel Nifti1Image
        Template image from first file
    """
    if len(filepaths) < 2:
        raise ValueError("Need at least 2 NIfTI files to average")
    
    # Load all files
    data_4d, template_img = load_multiple_niftis(
        filepaths,
        dtype=dtype,
        verify_shape=verify_shape,
        verify_affine=verify_affine
    )
    
    # Compute average
    average_data = np.mean(data_4d, axis=-1).astype(dtype)
    
    # Clean up
    del data_4d
    gc.collect()
    
    return average_data, template_img


def average_niftis_save(
    filepaths: List[str],
    output_path: str,
    dtype=np.float32,
    verify_shape: bool = True,
    verify_affine: bool = True
) -> str:
    """
    Average multiple NIfTI files and save the result
    
    Parameters:
    -----------
    filepaths : list of str
        List of NIfTI file paths to average
    output_path : str
        Path for output file
    dtype : numpy dtype, optional
        Data type for computation and output (default: float32)
    verify_shape : bool, optional
        Verify all files have the same shape (default: True)
    verify_affine : bool, optional
        Verify all files have the same affine (default: True)
    
    Returns:
    --------
    output_path : str
        Path to saved file
    """
    average_data, template_img = average_niftis(
        filepaths,
        dtype=dtype,
        verify_shape=verify_shape,
        verify_affine=verify_affine
    )
    
    return save_nifti_like(average_data, template_img, output_path, dtype)


# ==============================================================================
# TI-TOOLBOX INTEGRATED LOADING
# ==============================================================================

def load_subject_nifti_ti_toolbox(
    subject_id: str,
    simulation_name: str,
    nifti_file_pattern: str = "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",
    dtype=np.float32
) -> Tuple[np.ndarray, nib.Nifti1Image, str]:
    """
    Load a NIfTI file from TI-Toolbox BIDS structure
    
    Parameters:
    -----------
    subject_id : str
        Subject ID (e.g., '070')
    simulation_name : str
        Simulation name (e.g., 'ICP_RHIPPO')
    nifti_file_pattern : str, optional
        Pattern for NIfTI files. Default: 'grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz'
        Available variables: {subject_id}, {simulation_name}
    dtype : numpy dtype, optional
        Data type to load (default: float32)
    
    Returns:
    --------
    data : ndarray
        NIfTI data
    img : nibabel Nifti1Image
        NIfTI image object
    filepath : str
        Full path to the loaded file
    """
    pm = get_path_manager() if get_path_manager else None
    
    # Construct file path using TI-Toolbox path structure
    if pm:
        project_dir = pm.get_project_dir()
        if not project_dir:
            raise ValueError("Project directory not found. Is PROJECT_DIR_NAME set?")
        
        nifti_dir = os.path.join(
            project_dir,
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{subject_id}",
            "Simulations",
            simulation_name,
            "TI",
            "niftis"
        )
    else:
        # Fallback: assume we're in container environment
        project_dir = os.environ.get('PROJECT_DIR', '/mnt')
        nifti_dir = os.path.join(
            project_dir,
            "derivatives",
            "SimNIBS",
            f"sub-{subject_id}",
            "Simulations",
            simulation_name,
            "TI",
            "niftis"
        )
    
    # Format the filename pattern
    filename = nifti_file_pattern.format(
        subject_id=subject_id,
        simulation_name=simulation_name
    )
    filepath = os.path.join(nifti_dir, filename)
    
    # Load the file
    data, img = load_nifti(filepath, dtype=dtype)
    
    return data, img, filepath


def load_group_data_ti_toolbox(
    subject_configs: List[Dict],
    nifti_file_pattern: str = "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",
    dtype=np.float32
) -> Tuple[np.ndarray, nib.Nifti1Image, List[str]]:
    """
    Load multiple subjects from TI-Toolbox BIDS structure
    
    Parameters:
    -----------
    subject_configs : list of dict
        List of subject configurations with keys:
        - 'subject_id': Subject ID (e.g., '070')
        - 'simulation_name': Simulation name (e.g., 'ICP_RHIPPO')
    nifti_file_pattern : str, optional
        Pattern for NIfTI files
    dtype : numpy dtype, optional
        Data type to load (default: float32)
    
    Returns:
    --------
    data_4d : ndarray (x, y, z, n_subjects)
        4D array with all loaded data
    template_img : nibabel Nifti1Image
        Template image from first subject
    subject_ids : list of str
        List of successfully loaded subject IDs
    """
    data_list = []
    subject_ids = []
    template_img = None
    template_affine = None
    template_header = None
    
    for config in subject_configs:
        subject_id = config['subject_id']
        simulation_name = config['simulation_name']
        
        try:
            data, img, filepath = load_subject_nifti_ti_toolbox(
                subject_id,
                simulation_name,
                nifti_file_pattern,
                dtype=dtype
            )
            
            # Store template image from first subject
            if template_img is None:
                template_img = img
                template_affine = img.affine.copy()
                template_header = img.header.copy()
            
            data_list.append(data)
            subject_ids.append(subject_id)
            
            # Clear the image object to free memory
            del img
            
        except FileNotFoundError as e:
            print(f"Warning: File not found for subject {subject_id} - {e}")
            continue
        except Exception as e:
            print(f"Warning: Error loading subject {subject_id} - {e}")
            continue
    
    if len(data_list) == 0:
        raise ValueError("No subjects could be loaded successfully")
    
    # Stack into 4D array
    data_4d = np.stack(data_list, axis=-1).astype(dtype)
    
    # Recreate minimal template image
    template_img = nib.Nifti1Image(data_4d[..., 0], template_affine, template_header)
    
    # Clean up
    del data_list
    gc.collect()
    
    return data_4d, template_img, subject_ids


def load_grouped_subjects_ti_toolbox(
    subject_configs: List[Dict],
    nifti_file_pattern: str = "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",
    dtype=np.float32
) -> Tuple[Dict[str, np.ndarray], nib.Nifti1Image, Dict[str, List[str]]]:
    """
    Load subjects organized by groups from TI-Toolbox BIDS structure
    
    Parameters:
    -----------
    subject_configs : list of dict
        List of subject configurations with keys:
        - 'subject_id': Subject ID (e.g., '070')
        - 'simulation_name': Simulation name (e.g., 'ICP_RHIPPO')
        - 'group': Group name (e.g., 'group1', 'Responders', etc.)
    nifti_file_pattern : str, optional
        Pattern for NIfTI files
    dtype : numpy dtype, optional
        Data type to load (default: float32)
    
    Returns:
    --------
    groups_data : dict of str -> ndarray
        Dictionary mapping group names to 4D arrays (x, y, z, n_subjects)
    template_img : nibabel Nifti1Image
        Template image from first subject
    groups_ids : dict of str -> list of str
        Dictionary mapping group names to lists of subject IDs
    """
    # Organize configs by group
    groups = {}
    for config in subject_configs:
        group_name = config.get('group', 'default')
        if group_name not in groups:
            groups[group_name] = []
        groups[group_name].append(config)
    
    # Load each group
    groups_data = {}
    groups_ids = {}
    template_img = None
    
    for group_name, group_configs in groups.items():
        data_4d, img, subject_ids = load_group_data_ti_toolbox(
            group_configs,
            nifti_file_pattern,
            dtype=dtype
        )
        
        groups_data[group_name] = data_4d
        groups_ids[group_name] = subject_ids
        
        # Use first group's image as template
        if template_img is None:
            template_img = img
    
    return groups_data, template_img, groups_ids


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def compute_difference(
    data1: np.ndarray,
    data2: np.ndarray,
    dtype=np.float32
) -> np.ndarray:
    """
    Compute difference between two NIfTI data arrays
    
    Parameters:
    -----------
    data1 : ndarray
        First data array
    data2 : ndarray
        Second data array
    dtype : numpy dtype, optional
        Data type for result (default: float32)
    
    Returns:
    --------
    difference : ndarray
        data1 - data2
    """
    if data1.shape != data2.shape:
        raise ValueError(f"Shape mismatch: {data1.shape} vs {data2.shape}")
    
    return (data1 - data2).astype(dtype)


def get_valid_mask(data: np.ndarray, threshold: float = 0.0) -> np.ndarray:
    """
    Create a mask of valid (non-zero) voxels
    
    Parameters:
    -----------
    data : ndarray
        Input data
    threshold : float, optional
        Threshold for validity (default: 0.0)
    
    Returns:
    --------
    mask : ndarray (bool)
        Boolean mask of valid voxels
    """
    return data > threshold


def verify_nifti_compatibility(
    filepath1: str,
    filepath2: str,
    check_affine: bool = True,
    check_shape: bool = True
) -> bool:
    """
    Verify two NIfTI files are compatible for operations
    
    Parameters:
    -----------
    filepath1 : str
        Path to first NIfTI file
    filepath2 : str
        Path to second NIfTI file
    check_affine : bool, optional
        Check if affines match (default: True)
    check_shape : bool, optional
        Check if shapes match (default: True)
    
    Returns:
    --------
    compatible : bool
        True if files are compatible
    """
    img1 = nib.load(filepath1)
    img2 = nib.load(filepath2)
    
    if check_shape and img1.shape != img2.shape:
        return False
    
    if check_affine and not np.allclose(img1.affine, img2.affine, atol=1e-6):
        return False
    
    return True


# ==============================================================================
# EXAMPLE USAGE
# ==============================================================================

if __name__ == "__main__":
    print("NIfTI Utilities Module")
    print("=" * 50)
    print("\nThis module provides reusable NIfTI utilities for TI-Toolbox.")
    print("\nMain functions:")
    print("  - load_nifti(): Load a single NIfTI file")
    print("  - save_nifti_like(): Save data using reference image")
    print("  - average_niftis(): Average multiple NIfTI files")
    print("  - load_group_data_ti_toolbox(): Load group data from TI-Toolbox")
    print("  - load_grouped_subjects_ti_toolbox(): Load subjects organized by groups")
    print("\nFor detailed usage, see function docstrings.")

