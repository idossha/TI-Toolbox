#!/usr/bin/env python3
"""
FSL-based ROI Extraction Module for TI-Toolbox Classifier

Uses FSL tools for accurate ROI averaging and feature extraction.
"""

import numpy as np
import nibabel as nib
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import logging
import subprocess
import tempfile
import os


class FSLROIExtractor:
    """Handles FSL-based ROI averaging and feature extraction."""
    
    def __init__(self, atlas_manager, project_dir: str, logger: logging.Logger = None):
        """
        Initialize FSL ROI extractor.
        
        Args:
            atlas_manager: AtlasManager instance
            project_dir: Path to TI-Toolbox project directory
            logger: Logger instance
        """
        self.atlas_manager = atlas_manager
        self.project_dir = Path(project_dir)
        self.logger = logger or logging.getLogger(__name__)
        
        # Verify FSL availability
        self._verify_fsl_installation()
    
    def _verify_fsl_installation(self):
        """Verify FSL tools are available."""
        try:
            result = subprocess.run(['which', 'fslmaths'], capture_output=True, text=True)
            if result.returncode == 0:
                self.logger.info("✓ FSL tools available for ROI extraction")
                return True
            else:
                self.logger.warning("FSL tools not found - ROI extraction may fail")
                return False
        except Exception as e:
            self.logger.warning(f"Could not verify FSL installation: {e}")
            return False
    
    def extract_roi_features_with_fsl(self, file_paths: List[Path], 
                                    results_dir: Path) -> Tuple[np.ndarray, List[int], List[Path]]:
        """
        Extract ROI features using FSL tools for maximum accuracy.
        
        Args:
            file_paths: List of normalized NIfTI file paths
            results_dir: Directory to save ROI-averaged NIfTI files
            
        Returns:
            (roi_features_array, roi_ids, roi_nifti_paths)
        """
        self.logger.info("="*80)
        self.logger.info("FSL-BASED ROI FEATURE EXTRACTION")
        self.logger.info("="*80)
        self.logger.info("Using FSL tools for precise ROI averaging")
        
        # Create ROI features directory NEXT TO results directory with atlas separation
        # Structure: roi_features/{atlas_name}/sub-*_ROI_averaged_intensities.nii.gz
        atlas_name = self.atlas_manager.atlas_name
        roi_features_dir = results_dir.parent / "roi_features" / atlas_name
        roi_features_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"ROI features will be saved to: {roi_features_dir}")
        self.logger.info(f"Atlas-specific directory: {atlas_name}")
        
        # Get unique ROI IDs from atlas
        unique_roi_ids = np.unique(self.atlas_manager.atlas_data)
        unique_roi_ids = unique_roi_ids[unique_roi_ids != 0]  # Remove background
        
        self.logger.info(f"Extracting features for {len(unique_roi_ids)} ROIs using FSL")
        self.logger.info(f"Processing {len(file_paths)} subjects")
        
        # Initialize feature matrix
        n_subjects = len(file_paths)
        n_rois = len(unique_roi_ids)
        roi_features = np.zeros((n_subjects, n_rois))
        roi_nifti_paths = []
        
        # Track caching statistics
        cached_count = 0
        processed_count = 0
        
        # Process each subject (with caching)
        for subj_idx, file_path in enumerate(file_paths):
            subject_id = self._extract_subject_id(file_path)
            subject_roi_nifti = roi_features_dir / f"sub-{subject_id}_ROI_averaged_intensities.nii.gz"
            
            # Check if ROI features already exist
            if subject_roi_nifti.exists():
                self.logger.info(f"✓ Using existing ROI features for subject {subj_idx + 1}/{n_subjects}: {subject_roi_nifti.name}")
                
                # Load existing features
                subject_features = self._load_existing_roi_features(subject_roi_nifti, unique_roi_ids)
                
                if subject_features is not None:
                    roi_features[subj_idx, :] = subject_features
                    roi_nifti_paths.append(subject_roi_nifti)
                    cached_count += 1
                    continue  # Skip to next subject
                else:
                    self.logger.warning(f"Existing ROI file corrupted for {subject_id}, regenerating...")
            
            # Generate ROI features if not cached or corrupted
            if not subject_roi_nifti.exists() or roi_features[subj_idx, :].sum() == 0:
                self.logger.info(f"Processing subject {subj_idx + 1}/{n_subjects}: {file_path.name}")
                
                # Extract ROI features for this subject
                subject_features = self._extract_subject_roi_features_fsl(
                    file_path, unique_roi_ids, subject_roi_nifti
                )
                
                if subject_features is not None:
                    roi_features[subj_idx, :] = subject_features
                    roi_nifti_paths.append(subject_roi_nifti)
                    processed_count += 1
                else:
                    self.logger.error(f"Failed to extract features for {file_path.name}")
                    roi_nifti_paths.append(None)
        
        # Filter out failed subjects
        valid_subjects = [i for i, path in enumerate(roi_nifti_paths) if path is not None]
        
        if len(valid_subjects) < len(file_paths):
            self.logger.warning(f"Only {len(valid_subjects)}/{len(file_paths)} subjects processed successfully")
            roi_features = roi_features[valid_subjects, :]
            roi_nifti_paths = [roi_nifti_paths[i] for i in valid_subjects]
        
        # Log caching statistics
        self.logger.info("="*60)
        self.logger.info("FSL ROI EXTRACTION SUMMARY")
        self.logger.info("="*60)
        self.logger.info(f"✓ Total subjects: {n_subjects}")
        self.logger.info(f"✓ Used cached: {cached_count}")
        self.logger.info(f"✓ Newly processed: {processed_count}")
        self.logger.info(f"✓ Final feature matrix: {roi_features.shape}")
        self.logger.info(f"✓ ROI features directory: {roi_features_dir}")
        self.logger.info("="*60)
        
        return roi_features, list(unique_roi_ids), roi_nifti_paths
    
    def _extract_subject_roi_features_fsl(self, field_path: Path, roi_ids: np.ndarray, 
                                        output_nifti: Path) -> Optional[np.ndarray]:
        """
        Extract ROI features for a single subject using FSL.
        
        Args:
            field_path: Path to subject's TI field NIfTI
            roi_ids: Array of ROI IDs to extract
            output_nifti: Path to save ROI-averaged NIfTI
            
        Returns:
            Array of ROI-averaged intensities
        """
        try:
            # Create temporary atlas file if needed
            with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as temp_atlas:
                atlas_temp_path = temp_atlas.name
            
            # Save atlas to temporary file for FSL operations
            atlas_img = nib.Nifti1Image(
                self.atlas_manager.atlas_data.astype(np.int16),
                affine=nib.load(str(field_path)).affine,  # Use same affine as field
                header=nib.load(str(field_path)).header
            )
            nib.save(atlas_img, atlas_temp_path)
            
            # Initialize ROI-averaged data
            field_img = nib.load(str(field_path))
            roi_averaged_data = np.zeros_like(self.atlas_manager.atlas_data, dtype=np.float32)
            roi_features = np.zeros(len(roi_ids))
            
            # Process each ROI using FSL
            for roi_idx, roi_id in enumerate(roi_ids):
                # Create ROI mask using fslmaths
                with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as temp_roi_mask:
                    roi_mask_path = temp_roi_mask.name
                
                # Create binary mask for this ROI: atlas == roi_id
                mask_cmd = [
                    'fslmaths', atlas_temp_path,
                    '-thr', str(roi_id), '-uthr', str(roi_id),
                    '-bin', roi_mask_path
                ]
                
                subprocess.run(mask_cmd, check=True, capture_output=True)
                
                # Calculate mean intensity in this ROI using fslstats
                stats_cmd = [
                    'fslstats', str(field_path),
                    '-k', roi_mask_path,  # Use ROI mask
                    '-M'  # Calculate mean
                ]
                
                result = subprocess.run(stats_cmd, check=True, capture_output=True, text=True)
                mean_intensity = float(result.stdout.strip())
                
                # Store feature
                roi_features[roi_idx] = mean_intensity
                
                # Fill ROI-averaged NIfTI with this mean value
                roi_mask = self.atlas_manager.atlas_data == roi_id
                roi_averaged_data[roi_mask] = mean_intensity
                
                # Clean up temporary ROI mask
                os.unlink(roi_mask_path)
                
                # Log progress for large ROIs
                if roi_idx % 50 == 0:
                    roi_name = self.atlas_manager.atlas_labels.get(roi_id, f"ROI_{roi_id}")
                    self.logger.debug(f"  ROI {roi_idx + 1}/{len(roi_ids)}: {roi_name} = {mean_intensity:.4f}")
            
            # Save ROI-averaged NIfTI file
            roi_nifti_img = nib.Nifti1Image(
                roi_averaged_data,
                affine=field_img.affine,
                header=field_img.header
            )
            nib.save(roi_nifti_img, str(output_nifti))
            
            self.logger.debug(f"✓ Saved ROI-averaged NIfTI: {output_nifti.name}")
            
            # Clean up temporary atlas
            os.unlink(atlas_temp_path)
            
            return roi_features
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FSL command failed: {e.stderr}")
            return None
        except Exception as e:
            self.logger.error(f"FSL ROI extraction failed: {e}")
            return None
    
    def _extract_subject_id(self, file_path: Path) -> str:
        """Extract subject ID from file path."""
        # Try to extract from path structure
        path_parts = file_path.parts
        for part in path_parts:
            if part.startswith('sub-'):
                return part.replace('sub-', '')
        
        # Fallback - try to extract from filename
        filename = file_path.name
        if 'sub-' in filename:
            import re
            match = re.search(r'sub-(\w+)', filename)
            if match:
                return match.group(1)
        
        return "unknown"
    
    def _load_existing_roi_features(self, roi_nifti_path: Path, expected_roi_ids: np.ndarray) -> Optional[np.ndarray]:
        """
        Load existing ROI features from cached NIfTI file.
        
        Args:
            roi_nifti_path: Path to existing ROI-averaged NIfTI
            expected_roi_ids: Expected ROI IDs for validation
            
        Returns:
            Array of ROI features or None if invalid
        """
        try:
            # Load the ROI-averaged NIfTI
            roi_img = nib.load(str(roi_nifti_path))
            roi_data = roi_img.get_fdata()
            
            # Extract features for each expected ROI
            features = np.zeros(len(expected_roi_ids))
            
            for i, roi_id in enumerate(expected_roi_ids):
                # Find voxels for this ROI in the atlas
                roi_mask = self.atlas_manager.atlas_data == roi_id
                
                if np.sum(roi_mask) > 0:
                    # Get the ROI-averaged value (should be constant within ROI)
                    roi_values = roi_data[roi_mask]
                    # Take the mean (should be the same value for all voxels in ROI)
                    features[i] = np.mean(roi_values[roi_values > 0]) if np.sum(roi_values > 0) > 0 else 0
                else:
                    features[i] = 0
            
            # Validate that we got reasonable features
            if np.sum(features) == 0:
                self.logger.warning(f"Loaded ROI features are all zero - file may be corrupted")
                return None
            
            return features
            
        except Exception as e:
            self.logger.warning(f"Error loading existing ROI features: {e}")
            return None
    
    def create_group_averaged_niftis(self, responder_niftis: List[Path], 
                                   nonresponder_niftis: List[Path],
                                   results_dir: Path):
        """
        Create group-averaged ROI NIfTI files.
        
        Args:
            responder_niftis: List of responder ROI-averaged NIfTI files
            nonresponder_niftis: List of non-responder ROI-averaged NIfTI files
            results_dir: Directory to save group averages
        """
        try:
            self.logger.info("Creating group-averaged ROI NIfTI files...")
            
            # Load all responder data
            resp_data = []
            for nifti_path in responder_niftis:
                if nifti_path and nifti_path.exists():
                    img = nib.load(str(nifti_path))
                    resp_data.append(img.get_fdata())
            
            # Load all non-responder data
            nonresp_data = []
            for nifti_path in nonresponder_niftis:
                if nifti_path and nifti_path.exists():
                    img = nib.load(str(nifti_path))
                    nonresp_data.append(img.get_fdata())
            
            if len(resp_data) == 0 or len(nonresp_data) == 0:
                self.logger.warning("Insufficient data for group averaging")
                return
            
            # Calculate group averages
            resp_avg = np.mean(resp_data, axis=0)
            nonresp_avg = np.mean(nonresp_data, axis=0)
            difference = resp_avg - nonresp_avg
            
            # Use first responder as template for affine/header
            template_img = nib.load(str(responder_niftis[0]))
            
            # Save group averages with atlas-specific naming
            group_dir = results_dir / "group_averages"
            group_dir.mkdir(parents=True, exist_ok=True)
            
            atlas_name = self.atlas_manager.atlas_name
            
            # Responder average with atlas-specific naming
            resp_img = nib.Nifti1Image(resp_avg, template_img.affine, template_img.header)
            resp_path = group_dir / f"responders_ROI_averaged_{atlas_name}_MNI.nii.gz"
            nib.save(resp_img, str(resp_path))
            
            # Non-responder average
            nonresp_img = nib.Nifti1Image(nonresp_avg, template_img.affine, template_img.header)
            nonresp_path = group_dir / f"nonresponders_ROI_averaged_{atlas_name}_MNI.nii.gz"
            nib.save(nonresp_img, str(nonresp_path))
            
            # Difference map
            diff_img = nib.Nifti1Image(difference, template_img.affine, template_img.header)
            diff_path = group_dir / f"difference_responders_vs_nonresponders_ROI_averaged_{atlas_name}_MNI.nii.gz"
            nib.save(diff_img, str(diff_path))
            
            self.logger.info(f"✓ Group-averaged ROI NIfTI files saved:")
            self.logger.info(f"  • {resp_path.name}")
            self.logger.info(f"  • {nonresp_path.name}")
            self.logger.info(f"  • {diff_path.name}")
            
        except Exception as e:
            self.logger.error(f"Failed to create group-averaged NIfTIs: {e}")
