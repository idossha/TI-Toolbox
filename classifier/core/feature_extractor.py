#!/usr/bin/env python3
"""
Feature Extraction Module for TI-Toolbox Classifier

Handles both voxel-wise and ROI-averaged feature extraction.
"""

import numpy as np
from scipy import stats
from typing import Tuple, List
import logging
from joblib import Parallel, delayed


class FeatureExtractor:
    """Handles feature extraction for classification."""
    
    def __init__(self, atlas_data: np.ndarray = None, atlas_labels: dict = None, 
                 n_jobs: int = -1, logger: logging.Logger = None):
        """
        Initialize feature extractor.
        
        Args:
            atlas_data: Atlas data array
            atlas_labels: Atlas ROI labels
            n_jobs: Number of CPU cores for parallel processing
            logger: Logger instance
        """
        self.atlas_data = atlas_data
        self.atlas_labels = atlas_labels
        self.n_jobs = n_jobs
        self.logger = logger or logging.getLogger(__name__)
    
    def extract_voxel_features(self, resp_data: np.ndarray, nonresp_data: np.ndarray,
                              p_threshold: float = 0.01) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Extract voxel-wise features using t-tests.
        
        Args:
            resp_data: Responder data (n_subjects, n_voxels)
            nonresp_data: Non-responder data (n_subjects, n_voxels)
            p_threshold: P-value threshold for significance
            
        Returns:
            (significant_mask, t_statistics, p_values)
        """
        n_voxels = resp_data.shape[1]
        
        # Pre-filter active voxels
        resp_max = np.max(resp_data, axis=0)
        nonresp_max = np.max(nonresp_data, axis=0)
        active_mask = (resp_max > 0) | (nonresp_max > 0)
        n_active = np.sum(active_mask)
        
        self.logger.info(f"Active voxels: {n_active:,} / {n_voxels:,} ({n_active/n_voxels*100:.2f}%)")
        
        # Initialize arrays
        t_stats = np.zeros(n_voxels)
        p_values = np.ones(n_voxels)
        
        if n_active > 0:
            active_indices = np.where(active_mask)[0]
            
            def process_voxel(i):
                resp_vals = resp_data[:, i]
                nonresp_vals = nonresp_data[:, i]
                
                if np.var(resp_vals) == 0 and np.var(nonresp_vals) == 0:
                    return i, 0, 1.0
                
                try:
                    t_stat, p_val = stats.ttest_ind(resp_vals, nonresp_vals, equal_var=False)
                    if not np.isnan(p_val):
                        return i, t_stat, p_val
                except:
                    pass
                return i, 0, 1.0
            
            # Parallel processing
            n_jobs_actual = self.n_jobs if self.n_jobs > 0 else -1
            self.logger.info(f"Using {n_jobs_actual} CPU cores for parallel processing")
            
            results = Parallel(n_jobs=n_jobs_actual, verbose=1)(
                delayed(process_voxel)(i) for i in active_indices
            )
            
            # Update arrays
            for i, t_stat, p_val in results:
                t_stats[i] = t_stat
                p_values[i] = p_val
        
        significant_mask = p_values < p_threshold
        n_sig = np.sum(significant_mask)
        
        self.logger.info(f"Significant voxels: {n_sig:,} / {n_active:,} active ({n_sig/max(n_active,1)*100:.2f}%)")
        
        return significant_mask, t_stats, p_values
    
    def extract_roi_features_deprecated(self):
        """
        DEPRECATED: Old ROI extraction method.
        Now using FSL-based ROI extraction for better accuracy.
        """
        raise NotImplementedError("Use FSL-based ROI extraction instead")
    
    def perform_feature_selection_fold(self, resp_data: np.ndarray, nonresp_data: np.ndarray,
                                     p_threshold: float) -> np.ndarray:
        """
        Perform feature selection within a CV fold.
        
        Args:
            resp_data: Responder data for this fold
            nonresp_data: Non-responder data for this fold
            p_threshold: P-value threshold
            
        Returns:
            Boolean mask of significant voxels
        """
        n_voxels = resp_data.shape[1]
        
        def process_voxel_fold(voxel_idx):
            resp_vals = resp_data[:, voxel_idx]
            nonresp_vals = nonresp_data[:, voxel_idx]
            
            if np.var(resp_vals) == 0 and np.var(nonresp_vals) == 0:
                return voxel_idx, 1.0
                
            try:
                _, p_val = stats.ttest_ind(resp_vals, nonresp_vals, equal_var=False)
                if not np.isnan(p_val):
                    return voxel_idx, p_val
            except:
                pass
            return voxel_idx, 1.0
        
        # Parallel processing
        n_jobs_actual = self.n_jobs if self.n_jobs > 0 else -1
        results = Parallel(n_jobs=n_jobs_actual, verbose=0)(
            delayed(process_voxel_fold)(i) for i in range(n_voxels)
        )
        
        # Update p_values array
        p_values = np.ones(n_voxels)
        for voxel_idx, p_val in results:
            p_values[voxel_idx] = p_val
        
        significant_mask = p_values < p_threshold
        return significant_mask
