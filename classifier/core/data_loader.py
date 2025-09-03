#!/usr/bin/env python3
"""
Data Loading Module for TI-Toolbox Classifier

Handles loading and validation of NIfTI files and response data.
"""

import numpy as np
import pandas as pd
import nibabel as nib
from pathlib import Path
from typing import List, Tuple, Optional
import logging


class DataLoader:
    """Handles loading and validation of training data."""
    
    def __init__(self, project_dir: str, resolution_mm: int = 1, logger: logging.Logger = None):
        """
        Initialize data loader.
        
        Args:
            project_dir: Path to TI-Toolbox project directory
            resolution_mm: Target resolution for analysis
            logger: Logger instance
        """
        self.project_dir = Path(project_dir)
        self.resolution_mm = resolution_mm
        self.logger = logger or logging.getLogger(__name__)
    
    def load_response_data(self, response_file: str) -> Tuple[List[Path], List[Path], pd.DataFrame]:
        """
        Load response data and find corresponding NIfTI files.
        
        Args:
            response_file: Path to CSV file with columns: subject_id, response, [simulation_name]
            
        Returns:
            Tuple of (responder_nifti_paths, nonresponder_nifti_paths, metadata_df)
        """
        self.logger.info(f"Loading response data from: {response_file}")
        
        # Load response data
        df = pd.read_csv(response_file)
        
        # Validate required columns
        required_cols = ['subject_id', 'response']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"Response file must have columns: {required_cols}")
        
        # Clean subject IDs
        df['subject_id'] = df['subject_id'].astype(str).str.replace('sub-', '', regex=False)
        
        # Find NIfTI files
        responder_paths = []
        nonresponder_paths = []
        metadata_records = []
        
        for _, row in df.iterrows():
            subject_id = row['subject_id']
            response = int(row['response'])
            
            # Get simulation name if provided
            if 'simulation_name' in row and pd.notna(row['simulation_name']):
                simulation_name = str(row['simulation_name'])
            else:
                simulation_name = self._find_default_simulation(subject_id)
            
            if not simulation_name:
                self.logger.warning(f"No simulation found for subject {subject_id}")
                continue
            
            # Find pre-computed MNI NIfTI file
            nifti_path = self._find_precomputed_mni_file(subject_id, simulation_name)
            
            if nifti_path and nifti_path.exists():
                if response > 0:
                    responder_paths.append(nifti_path)
                    group = "responder"
                else:
                    nonresponder_paths.append(nifti_path)
                    group = "non_responder"
                
                metadata_records.append({
                    'subject_id': subject_id,
                    'simulation_name': simulation_name,
                    'response': response,
                    'group': group,
                    'nifti_path': str(nifti_path)
                })
            else:
                self.logger.warning(f"NIfTI not found for {subject_id}/{simulation_name}")
        
        metadata_df = pd.DataFrame(metadata_records)
        
        self.logger.info(f"Data loaded: {len(responder_paths)} responders, {len(nonresponder_paths)} non-responders")
        
        return responder_paths, nonresponder_paths, metadata_df
    
    def _find_default_simulation(self, subject_id: str) -> Optional[str]:
        """Find default simulation for a subject."""
        sim_dir = self.project_dir / "derivatives" / "SimNIBS" / f"sub-{subject_id}" / "Simulations"
        
        if sim_dir.exists():
            # Look for any simulation directory
            for sim_path in sim_dir.iterdir():
                if sim_path.is_dir() and (sim_path / "TI").exists():
                    return sim_path.name
        
        return None
    
    def _find_precomputed_mni_file(self, subject_id: str, simulation_name: str) -> Optional[Path]:
        """Find pre-computed MNI-space TI NIfTI file."""
        # Expected MNI path patterns - your exact naming scheme
        mni_patterns = [
            f"grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",  # Your exact pattern
            f"{simulation_name}_TI_MNI_MNI_TI_max.nii.gz",      # Without grey prefix
            f"grey_{simulation_name}_TI_MNI_max.nii.gz",        # Alternative
            f"{simulation_name}_TI_MNI_max.nii.gz",             # Simpler alternative
        ]
        
        # Base directory - matches your structure
        base_dir = self.project_dir / "derivatives" / "SimNIBS" / f"sub-{subject_id}" / "Simulations" / simulation_name / "TI" / "niftis"
        
        # Try each pattern
        for pattern in mni_patterns:
            nifti_path = base_dir / pattern
            if nifti_path.exists():
                return nifti_path
        
        # Try without niftis subdirectory
        base_dir = base_dir.parent
        for pattern in mni_patterns:
            nifti_path = base_dir / pattern
            if nifti_path.exists():
                return nifti_path
        
        return None
    
    def validate_data_consistency(self, file_paths: List[Path]) -> bool:
        """
        Validate that all NIfTI files have consistent shapes and properties.
        
        Args:
            file_paths: List of NIfTI file paths to validate
            
        Returns:
            True if all files are consistent, False otherwise
        """
        if not file_paths:
            return False
        
        reference_img = nib.load(str(file_paths[0]))
        reference_shape = reference_img.shape
        reference_affine = reference_img.affine
        
        self.logger.info(f"Validating {len(file_paths)} files against reference:")
        self.logger.info(f"  Reference shape: {reference_shape}")
        self.logger.info(f"  Reference voxel size: {reference_img.header.get_zooms()[:3]}")
        
        inconsistent_files = []
        
        for i, path in enumerate(file_paths[1:], 1):
            try:
                img = nib.load(str(path))
                
                if img.shape != reference_shape:
                    inconsistent_files.append(f"{path.name}: shape {img.shape} vs {reference_shape}")
                elif not np.allclose(img.affine, reference_affine, atol=1e-3):
                    inconsistent_files.append(f"{path.name}: different affine transformation")
                    
            except Exception as e:
                inconsistent_files.append(f"{path.name}: error loading - {e}")
        
        if inconsistent_files:
            self.logger.error(f"Found {len(inconsistent_files)} inconsistent files:")
            for issue in inconsistent_files:
                self.logger.error(f"  • {issue}")
            return False
        else:
            self.logger.info("✓ All files are consistent")
            return True
