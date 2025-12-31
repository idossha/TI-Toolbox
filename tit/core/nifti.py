#!/usr/bin/env simnibs_python
"""
TI-Toolbox NIfTI Module

TI-Toolbox specific NIfTI file operations.
Provides functions for loading subject and group data from TI-Toolbox BIDS structure.
"""

import os
import sys
import gc
import numpy as np
import nibabel as nib
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Union

# Import TI-Toolbox core modules
from . import get_path_manager
from . import constants as const

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

    project_dir = pm.project_dir
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
    
    # Format the filename pattern
    filename = nifti_file_pattern.format(
        subject_id=subject_id,
        simulation_name=simulation_name
    )
    filepath = os.path.join(nifti_dir, filename)
    
    # Load the file (inline basic loading)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"NIfTI file not found: {filepath}")

    img = nib.load(filepath)
    data = img.get_fdata(dtype=dtype)

    # Ensure 3D data (squeeze out extra dimensions if present)
    while data.ndim > 3:
        data = np.squeeze(data, axis=-1)

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
# EXAMPLE USAGE
# ==============================================================================

if __name__ == "__main__":
    print("TI-Toolbox NIfTI Module")
    print("=" * 50)
    print("\nThis module provides TI-Toolbox specific NIfTI utilities.")
    print("\nMain functions:")
    print("  - load_subject_nifti_ti_toolbox(): Load single subject from TI-Toolbox")
    print("  - load_group_data_ti_toolbox(): Load group data from TI-Toolbox")
    print("  - load_grouped_subjects_ti_toolbox(): Load subjects organized by groups")
    print("\nFor detailed usage, see function docstrings.")

