#!/usr/bin/env python3
"""
TI-Toolbox Classifier v2.0 - Production Ready

Modular, clean implementation of the voxel-wise TI field classifier
following Albizu et al. (2020) methodology.
"""

import numpy as np
import pandas as pd
import nibabel as nib
from pathlib import Path
from typing import Dict, List, Tuple, Any
import logging
import time
import sys

# Add core modules to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from core.data_loader import DataLoader
    from core.atlas_manager import AtlasManager  
    from core.feature_extractor import FeatureExtractor
    from core.model_trainer import ModelTrainer
    from core.qa_reporter import QAReporter
    from core.fsl_roi_extractor import FSLROIExtractor
    from core.plotting import TIClassifierPlotter
except ImportError as e:
    print(f"Error importing core modules: {e}")
    print("Make sure all core modules are properly installed")
    sys.exit(1)


class TIClassifier:
    """
    Production-ready TI field classifier.
    
    This modular implementation provides:
    - Clean separation of concerns
    - Robust error handling
    - Comprehensive QA reporting
    - Both voxel-wise and ROI-based analysis
    """
    
    def __init__(self, project_dir: str, output_dir: str = None,
                 resolution_mm: int = 1, p_value_threshold: float = 0.01,
                 n_jobs: int = -1, use_roi_features: bool = False,
                 atlas_name: str = "HarvardOxford-cort-maxprob-thr0-1mm"):
        """
        Initialize TI classifier.
        
        Args:
            project_dir: Path to TI-Toolbox project directory
            output_dir: Output directory for results
            resolution_mm: Resolution in mm (1=original, 2-4=downsampled)
            p_value_threshold: P-value threshold for feature selection
            n_jobs: Number of CPU cores (-1=all)
            use_roi_features: Use FSL ROI-averaged features instead of voxel-wise
            atlas_name: Name of atlas to use (HarvardOxford-cort-maxprob-thr0-1mm or MNI_Glasser_HCP_v1.0)
        """
        self.project_dir = Path(project_dir)
        self.resolution_mm = resolution_mm
        self.p_value_threshold = p_value_threshold
        self.n_jobs = n_jobs
        self.use_roi_features = use_roi_features
        
        # Set up output directory
        if output_dir is None:
            self.output_dir = self.project_dir / "derivatives" / "ti-toolbox" / "classifier" / "results"
        else:
            self.output_dir = Path(output_dir)
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up logging
        self.logger = self._setup_logging()
        
        # Validate atlas name
        if not AtlasManager.validate_atlas_name(atlas_name):
            supported = list(AtlasManager.get_supported_atlases().keys())
            raise ValueError(f"Unsupported atlas '{atlas_name}'. Supported: {supported}")
        
        # Initialize core components
        self.data_loader = DataLoader(project_dir, resolution_mm, self.logger)
        self.atlas_manager = AtlasManager(project_dir, atlas_name, self.logger)
        self.feature_extractor = FeatureExtractor(
            self.atlas_manager.atlas_data, 
            self.atlas_manager.atlas_labels,
            n_jobs, self.logger
        )
        self.model_trainer = ModelTrainer(n_jobs, self.logger)
        self.qa_reporter = QAReporter(self.output_dir, self.atlas_manager, self.logger)
        self.fsl_roi_extractor = FSLROIExtractor(self.atlas_manager, project_dir, self.logger)
        self.plotter = TIClassifierPlotter(self.output_dir, self.logger)
        
        # Results storage
        self.results = {}
        self.training_data = None
    
    def _setup_logging(self) -> logging.Logger:
        """Setup production-level logging."""
        logger = logging.getLogger('TIClassifier')
        logger.setLevel(logging.INFO)
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # File handler
        log_file = self.output_dir / 'ti_classifier.log'
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    
    def train(self, response_file: str) -> Dict[str, Any]:
        """
        Train the classifier.
        
        Args:
            response_file: Path to CSV file with response data
            
        Returns:
            Training results dictionary
        """
        start_time = time.time()
        
        try:
            self.logger.info("="*80)
            self.logger.info("TI-TOOLBOX CLASSIFIER v2.0 - TRAINING")
            self.logger.info("="*80)
            
            # Step 1: Load and validate data
            self.logger.info("Step 1: Loading and validating data...")
            responder_paths, nonresponder_paths, metadata = self.data_loader.load_response_data(response_file)
            
            if len(responder_paths) < 3 or len(nonresponder_paths) < 3:
                raise ValueError(f"Insufficient data: {len(responder_paths)} responders, {len(nonresponder_paths)} non-responders (need ≥3 each)")
            
            # Validate data consistency
            all_paths = responder_paths + nonresponder_paths
            if not self.data_loader.validate_data_consistency(all_paths):
                raise ValueError("Data validation failed - inconsistent file properties")
            
            # Step 2: Load and process voxel data
            self.logger.info("Step 2: Loading voxel data...")
            resp_data, nonresp_data, template_shape = self._load_and_process_data(
                responder_paths, nonresponder_paths
            )
            
            # Step 3: Resample atlas and verify alignment
            self.logger.info("Step 3: Resampling atlas and verifying alignment...")
            template_img = nib.load(str(responder_paths[0]))
            if self.resolution_mm > 1:
                template_img = self._downsample_nifti(template_img, self.resolution_mm)
            
            if not self.atlas_manager.resample_atlas_to_match(template_shape, template_img.affine):
                raise ValueError("Atlas resampling failed")
            
            # Update feature extractor with resampled atlas
            self.feature_extractor.atlas_data = self.atlas_manager.atlas_data
            
            # Step 4: Generate QA report
            self.logger.info("Step 4: Generating QA report...")
            self.qa_reporter.create_comprehensive_report(
                responder_paths, nonresponder_paths, template_shape, 
                self.resolution_mm, self.use_roi_features
            )
            
            # Step 5: Feature extraction and training
            if self.use_roi_features:
                self.logger.info("Step 5: Training with FSL ROI-averaged features...")
                # Need to pass the file paths for FSL processing
                all_file_paths = responder_paths + nonresponder_paths
                results = self._train_roi_based(resp_data, nonresp_data, template_shape, all_file_paths)
            else:
                self.logger.info("Step 5: Training with voxel-wise features...")
                results = self._train_voxel_wise(resp_data, nonresp_data)
            
            # Step 6: Save results and organize NIfTI files
            self.logger.info("Step 6: Saving results and organizing NIfTI files...")
            self._save_results(results, responder_paths, nonresponder_paths)
            
            # Copy reference files to results/niftis
            self._copy_reference_files_to_results()
            
            # Generate FreeSurfer visualization command
            self._generate_freeview_command(results)
            
            # Step 7: Generate comprehensive plots
            self.logger.info("Step 7: Generating comprehensive visualization plots...")
            self._generate_plots(results, resp_data, nonresp_data)
            
            # Calculate elapsed time
            elapsed_time = time.time() - start_time
            time_str = f"{elapsed_time:.1f} seconds" if elapsed_time < 60 else f"{elapsed_time/60:.1f} minutes"
            
            self.logger.info("="*80)
            self.logger.info("TRAINING COMPLETED SUCCESSFULLY")
            self.logger.info(f"Method: {results['method']}")
            self.logger.info(f"Accuracy: {results['cv_accuracy']:.1f}% ± {results['cv_std']:.1f}%")
            self.logger.info(f"ROC-AUC: {results['roc_auc']:.3f}")
            self.logger.info(f"Training time: {time_str}")
            self.logger.info("="*80)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Training failed: {e}")
            import traceback
            self.logger.debug(f"Full traceback: {traceback.format_exc()}")
            raise
    
    def _load_and_process_data(self, responder_paths: List[Path], 
                             nonresponder_paths: List[Path]) -> Tuple[np.ndarray, np.ndarray, tuple]:
        """Load and process voxel data from NIfTI files."""
        # Load template
        template_img = nib.load(str(responder_paths[0]))
        if self.resolution_mm > 1:
            template_img = self._downsample_nifti(template_img, self.resolution_mm)
        
        template_shape = template_img.shape
        
        self.logger.info(f"Template shape: {template_shape}")
        self.logger.info(f"Resolution: {self.resolution_mm}mm")
        
        # Load all data
        resp_data = []
        for path in responder_paths:
            img = nib.load(str(path))
            if self.resolution_mm > 1:
                img = self._downsample_nifti(img, self.resolution_mm)
            data = img.get_fdata().flatten()
            resp_data.append(data)
        
        nonresp_data = []
        for path in nonresponder_paths:
            img = nib.load(str(path))
            if self.resolution_mm > 1:
                img = self._downsample_nifti(img, self.resolution_mm)
            data = img.get_fdata().flatten()
            nonresp_data.append(data)
        
        resp_array = np.array(resp_data)
        nonresp_array = np.array(nonresp_data)
        
        self.logger.info(f"Loaded: {resp_array.shape[0]} responders, {nonresp_array.shape[0]} non-responders")
        self.logger.info(f"Voxels per subject: {resp_array.shape[1]:,}")
        
        return resp_array, nonresp_array, template_shape
    
    def _train_roi_based(self, resp_data: np.ndarray, nonresp_data: np.ndarray,
                        template_shape: tuple, file_paths: List[Path]) -> Dict[str, Any]:
        """Train using FSL-based ROI-averaged features."""
        # Use FSL ROI extractor for maximum accuracy
        all_file_paths = file_paths  # This should be the loaded file paths
        
        # Extract ROI features using FSL
        roi_features, roi_ids, roi_nifti_paths = self.fsl_roi_extractor.extract_roi_features_with_fsl(
            all_file_paths, self.output_dir
        )
        
        # Split into responder/non-responder based on original data sizes
        n_responders = resp_data.shape[0]
        resp_features = roi_features[:n_responders, :]
        nonresp_features = roi_features[n_responders:, :]
        
        # Create group-averaged NIfTI files
        resp_niftis = roi_nifti_paths[:n_responders]
        nonresp_niftis = roi_nifti_paths[n_responders:]
        
        self.fsl_roi_extractor.create_group_averaged_niftis(
            resp_niftis, nonresp_niftis, self.output_dir
        )
        
        return self.model_trainer.train_roi_based(resp_features, nonresp_features, roi_ids)
    
    def _train_voxel_wise(self, resp_data: np.ndarray, nonresp_data: np.ndarray) -> Dict[str, Any]:
        """Train using voxel-wise features."""
        return self.model_trainer.train_voxel_wise(
            resp_data, nonresp_data, self.feature_extractor, self.p_value_threshold
        )
    
    def _downsample_nifti(self, img: nib.Nifti1Image, target_resolution: int) -> nib.Nifti1Image:
        """Downsample NIfTI image to target resolution."""
        if target_resolution == 1:
            return img
        
        from scipy.ndimage import zoom
        
        current_res = np.array(img.header.get_zooms()[:3])
        zoom_factors = current_res / target_resolution
        
        data = img.get_fdata()
        if len(data.shape) == 4:
            zoom_factors = np.append(zoom_factors, 1.0)
        
        # Use field averaging for proper downsampling
        from scipy.ndimage import uniform_filter
        
        if target_resolution > 1:
            block_sizes = 1.0 / zoom_factors
            if len(data.shape) == 3:
                averaged = uniform_filter(data, size=block_sizes, mode='constant')
                step_sizes = [int(np.round(bs)) for bs in block_sizes]
                downsampled = averaged[::step_sizes[0], ::step_sizes[1], ::step_sizes[2]]
            else:  # 4D
                downsampled_slices = []
                for t in range(data.shape[3]):
                    slice_3d = data[:, :, :, t]
                    averaged = uniform_filter(slice_3d, size=block_sizes[:3], mode='constant')
                    step_sizes = [int(np.round(bs)) for bs in block_sizes[:3]]
                    downsampled_slice = averaged[::step_sizes[0], ::step_sizes[1], ::step_sizes[2]]
                    downsampled_slices.append(downsampled_slice)
                downsampled = np.stack(downsampled_slices, axis=3)
        else:
            downsampled = data
        
        # Create new image with updated affine
        new_affine = img.affine.copy()
        for i in range(3):
            new_affine[i, i] *= (1/zoom_factors[i])
        
        new_img = nib.Nifti1Image(downsampled, new_affine, img.header)
        
        # Update header zooms
        if len(downsampled.shape) == 4:
            new_zooms = np.ones(4)
            new_zooms[:3] = target_resolution
            new_zooms[3] = img.header.get_zooms()[3]
        else:
            new_zooms = np.ones(3) * target_resolution
        
        new_img.header.set_zooms(new_zooms)
        
        return new_img
    
    def _save_results(self, results: Dict[str, Any], responder_paths: List[Path], 
                     nonresponder_paths: List[Path]):
        """Save training results and generate outputs."""
        # Save model
        import joblib
        model_path = self.output_dir / 'ti_classifier_model.pkl'
        joblib.dump(self.model_trainer.model, model_path)
        self.logger.info(f"Model saved: {model_path}")
        
        # Save performance metrics
        perf_df = pd.DataFrame([{
            'Metric': 'CV_Accuracy',
            'Value': f"{results['cv_accuracy']:.1f}% ± {results['cv_std']:.1f}%"
        }, {
            'Metric': 'ROC_AUC', 
            'Value': f"{results['roc_auc']:.3f}"
        }, {
            'Metric': 'Method',
            'Value': results['method']
        }])
        
        perf_path = self.output_dir / 'performance_metrics.csv'
        perf_df.to_csv(perf_path, index=False)
        
        # Create voxel-wise NIfTI outputs if in voxel mode
        if not self.use_roi_features:
            self._create_voxelwise_nifti_outputs(results, responder_paths, nonresponder_paths)
        
        # Save ROI importance if available
        if 'roi_importance' in results:
            roi_importance_df = pd.DataFrame(results['roi_importance'])
            
            # Add ROI names if available
            if self.atlas_manager.atlas_labels:
                roi_importance_df['roi_name'] = roi_importance_df['roi_id'].map(
                    lambda x: self.atlas_manager.atlas_labels.get(x, f"ROI_{x}")
                )
            
            # Sort by importance and save
            roi_importance_df = roi_importance_df.sort_values('abs_weight', ascending=False)
            roi_path = self.output_dir / 'roi_importance.csv'
            roi_importance_df.to_csv(roi_path, index=False)
            self.logger.info(f"ROI importance saved: {roi_path}")
            
            # Log top 10 most important ROIs
            self.logger.info("Top 10 Most Important ROIs:")
            for i, row in roi_importance_df.head(10).iterrows():
                roi_name = row.get('roi_name', f"ROI_{row['roi_id']}")
                weight = row['weight']
                direction = "Responder" if weight > 0 else "Non-responder"
                self.logger.info(f"  {i+1:2d}. {roi_name}: {weight:.4f} ({direction})")
        
        # Save summary
        summary = {
            'accuracy': float(results['cv_accuracy']),
            'accuracy_std': float(results['cv_std']),
            'auc': float(results['roc_auc']),
            'method': results['method'],
            'n_responders': len(responder_paths),
            'n_nonresponders': len(nonresponder_paths),
            'resolution_mm': self.resolution_mm,
            'use_roi_features': self.use_roi_features
        }
        
        if 'confidence_interval' in results:
            ci = results['confidence_interval']
            summary['ci_lower'] = float(ci[0])
            summary['ci_upper'] = float(ci[1])
        
        import json
        summary_path = self.output_dir / 'results_summary.json'
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        self.logger.info(f"Results saved to: {self.output_dir}")
    
    def _create_voxelwise_nifti_outputs(self, results: Dict[str, Any], 
                                       responder_paths: List[Path], nonresponder_paths: List[Path]):
        """Create voxel-wise NIfTI output files from training results."""
        self.logger.info("Creating voxel-wise NIfTI output files...")
        
        # Load template for creating output NIfTI files
        template_path = responder_paths[0]
        template_img = nib.load(str(template_path))
        if self.resolution_mm > 1:
            template_img = self._downsample_nifti(template_img, self.resolution_mm)
        
        template_shape = template_img.shape
        if len(template_shape) == 4:
            template_shape = template_shape[:3]
        
        # 1. Create SVM weights map
        if 'weights' in results:
            weights_data = np.zeros(template_shape)
            weights_flat = results['weights']
            weights_data.flat[:len(weights_flat)] = weights_flat
            
            weights_img = nib.Nifti1Image(weights_data, template_img.affine, template_img.header)
            weights_path = self.output_dir / 'svm_weights_MNI.nii.gz'
            nib.save(weights_img, str(weights_path))
            self.logger.info(f"✓ SVM weights saved: {weights_path.name}")
        
        # 2. Create group averages and statistical maps
        self._create_group_averages_and_stats(responder_paths, nonresponder_paths, template_img)
        
        # 3. Create significant voxels mask (if we have statistical info)
        self._create_significance_mask(template_img)
    
    def _create_group_averages_and_stats(self, responder_paths: List[Path], 
                                        nonresponder_paths: List[Path], template_img: nib.Nifti1Image):
        """Create group average maps and statistical comparisons."""
        from scipy import stats
        
        # Load all responder data
        resp_data_list = []
        for path in responder_paths:
            img = nib.load(str(path))
            if self.resolution_mm > 1:
                img = self._downsample_nifti(img, self.resolution_mm)
            data = img.get_fdata()
            if len(data.shape) == 4:
                data = data[:, :, :, 0]
            resp_data_list.append(data)
        
        # Load all non-responder data
        nonresp_data_list = []
        for path in nonresponder_paths:
            img = nib.load(str(path))
            if self.resolution_mm > 1:
                img = self._downsample_nifti(img, self.resolution_mm)
            data = img.get_fdata()
            if len(data.shape) == 4:
                data = data[:, :, :, 0]
            nonresp_data_list.append(data)
        
        # Convert to arrays
        resp_array = np.array(resp_data_list)  # Shape: (n_resp, x, y, z)
        nonresp_array = np.array(nonresp_data_list)  # Shape: (n_nonresp, x, y, z)
        
        # Calculate group averages
        resp_avg = np.mean(resp_array, axis=0)
        nonresp_avg = np.mean(nonresp_array, axis=0)
        difference = resp_avg - nonresp_avg
        
        # Save group averages
        resp_avg_img = nib.Nifti1Image(resp_avg, template_img.affine, template_img.header)
        resp_avg_path = self.output_dir / 'average_responders_MNI.nii.gz'
        nib.save(resp_avg_img, str(resp_avg_path))
        self.logger.info(f"✓ Responder average saved: {resp_avg_path.name}")
        
        nonresp_avg_img = nib.Nifti1Image(nonresp_avg, template_img.affine, template_img.header)
        nonresp_avg_path = self.output_dir / 'average_nonresponders_MNI.nii.gz'
        nib.save(nonresp_avg_img, str(nonresp_avg_path))
        self.logger.info(f"✓ Non-responder average saved: {nonresp_avg_path.name}")
        
        diff_img = nib.Nifti1Image(difference, template_img.affine, template_img.header)
        diff_path = self.output_dir / 'difference_resp_vs_nonresp_MNI.nii.gz'
        nib.save(diff_img, str(diff_path))
        self.logger.info(f"✓ Group difference saved: {diff_path.name}")
        
        # Calculate voxel-wise t-statistics
        t_stats = np.zeros_like(resp_avg)
        p_values = np.zeros_like(resp_avg)
        
        for i in range(resp_avg.shape[0]):
            for j in range(resp_avg.shape[1]):
                for k in range(resp_avg.shape[2]):
                    resp_vals = resp_array[:, i, j, k]
                    nonresp_vals = nonresp_array[:, i, j, k]
                    
                    # Only calculate if there's variance in the data
                    if np.var(resp_vals) > 0 or np.var(nonresp_vals) > 0:
                        try:
                            t_stat, p_val = stats.ttest_ind(resp_vals, nonresp_vals, equal_var=False)
                            if not np.isnan(t_stat) and not np.isnan(p_val):
                                t_stats[i, j, k] = t_stat
                                p_values[i, j, k] = p_val
                        except:
                            pass
        
        # Save statistical maps
        t_stats_img = nib.Nifti1Image(t_stats, template_img.affine, template_img.header)
        t_stats_path = self.output_dir / 't_statistics_MNI.nii.gz'
        nib.save(t_stats_img, str(t_stats_path))
        self.logger.info(f"✓ T-statistics saved: {t_stats_path.name}")
        
        p_values_img = nib.Nifti1Image(p_values, template_img.affine, template_img.header)
        p_values_path = self.output_dir / 'p_values_MNI.nii.gz'
        nib.save(p_values_img, str(p_values_path))
        self.logger.info(f"✓ P-values saved: {p_values_path.name}")
    
    def _create_significance_mask(self, template_img: nib.Nifti1Image):
        """Create significant voxels mask based on p-values."""
        p_values_path = self.output_dir / 'p_values_MNI.nii.gz'
        
        if p_values_path.exists():
            p_values_img = nib.load(str(p_values_path))
            p_values_data = p_values_img.get_fdata()
            
            # Create significance mask (p < 0.05, uncorrected)
            sig_mask = (p_values_data < 0.05) & (p_values_data > 0)
            
            sig_mask_img = nib.Nifti1Image(sig_mask.astype(int), template_img.affine, template_img.header)
            sig_mask_path = self.output_dir / 'significant_voxels_mask_MNI.nii.gz'
            nib.save(sig_mask_img, str(sig_mask_path))
            self.logger.info(f"✓ Significance mask saved: {sig_mask_path.name}")
            
            n_sig_voxels = np.sum(sig_mask)
            self.logger.info(f"  Found {n_sig_voxels:,} significant voxels (p < 0.05)")
    
    def _copy_reference_files_to_results(self):
        """Copy atlas and MNI template to results directory for reference."""
        results_nifti_dir = self.output_dir / "niftis"
        results_nifti_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy MNI template
        possible_mni_paths = [
            Path("/ti-toolbox/assets/atlas/MNI152_T1_1mm.nii.gz"),
            Path("/ti-toolbox/assets/base-niftis/MNI152_T1_1mm.nii.gz"),
            self.project_dir / "assets" / "atlas" / "MNI152_T1_1mm.nii.gz",
            self.project_dir / "assets" / "base-niftis" / "MNI152_T1_1mm.nii.gz"
        ]
        
        for mni_path in possible_mni_paths:
            if mni_path.exists():
                import shutil
                mni_copy = results_nifti_dir / "MNI152_T1_1mm_template.nii.gz"
                shutil.copy2(mni_path, mni_copy)
                self.logger.info(f"✓ Copied MNI template to results: {mni_copy.name}")
                break
        
        # Copy Harvard-Oxford atlas
        if self.atlas_manager.atlas_path.exists():
            import shutil
            atlas_copy = results_nifti_dir / f"{self.atlas_manager.atlas_path.name}"
            shutil.copy2(self.atlas_manager.atlas_path, atlas_copy)
            self.logger.info(f"✓ Copied atlas to results: {atlas_copy.name}")
            
            # Also copy atlas labels
            labels_path = self.atlas_manager.atlas_path.with_suffix('.txt')
            if labels_path.exists():
                labels_copy = results_nifti_dir / f"{labels_path.name}"
                shutil.copy2(labels_path, labels_copy)
                self.logger.info(f"✓ Copied atlas labels to results: {labels_copy.name}")
    
    def _generate_freeview_command(self, results: Dict[str, Any]):
        """Generate FreeSurfer visualization command for results."""
        try:
            # Find MNI template
            mni_template = None
            possible_mni_paths = [
                Path("/ti-toolbox/assets/atlas/MNI152_T1_1mm.nii.gz"),
                Path("/ti-toolbox/assets/base-niftis/MNI152_T1_1mm.nii.gz"),
                self.output_dir / "niftis" / "MNI152_T1_1mm_template.nii.gz"
            ]
            
            for path in possible_mni_paths:
                if path.exists():
                    mni_template = path
                    break
            
            if mni_template is None:
                self.logger.warning("MNI template not found - cannot generate FreeSurfer command")
                return
            
            # Build command based on analysis type
            cmd_parts = ["freeview", "-v", str(mni_template)]
            
            if self.use_roi_features:
                # ROI-based results
                atlas_name = self.atlas_manager.atlas_name
                diff_map = self.output_dir / "group_averages" / f"difference_responders_vs_nonresponders_ROI_averaged_{atlas_name}_MNI.nii.gz"
                if diff_map.exists():
                    cmd_parts.extend(["-v", f"{diff_map}:colormap=heat:opacity=0.8"])
                
                resp_avg = self.output_dir / "group_averages" / f"responders_ROI_averaged_{atlas_name}_MNI.nii.gz"
                if resp_avg.exists():
                    cmd_parts.extend(["-v", f"{resp_avg}:colormap=hot:opacity=0.6"])
            else:
                # Voxel-wise results
                # Add statistical maps in order of importance
                svm_weights = self.output_dir / "svm_weights_MNI.nii.gz"
                if svm_weights.exists():
                    cmd_parts.extend(["-v", f"{svm_weights}:colormap=heat:opacity=0.8"])
                
                t_stats = self.output_dir / "t_statistics_MNI.nii.gz"
                if t_stats.exists():
                    cmd_parts.extend(["-v", f"{t_stats}:colormap=hot:opacity=0.7"])
                
                sig_voxels = self.output_dir / "significant_voxels_mask_MNI.nii.gz"
                if sig_voxels.exists():
                    cmd_parts.extend(["-v", f"{sig_voxels}:colormap=binary:opacity=0.5"])
                
                # Add group averages
                diff_map = self.output_dir / "difference_resp_vs_nonresp_MNI.nii.gz"
                if diff_map.exists():
                    cmd_parts.extend(["-v", f"{diff_map}:colormap=cool:opacity=0.6"])
                
                resp_avg = self.output_dir / "average_responders_MNI.nii.gz"
                if resp_avg.exists():
                    cmd_parts.extend(["-v", f"{resp_avg}:colormap=summer:opacity=0.4"])
            
            # Save command
            cmd_file = self.output_dir / 'freeview_command.sh'
            with open(cmd_file, 'w') as f:
                f.write("#!/bin/bash\n")
                if self.use_roi_features:
                    f.write("# FreeSurfer visualization for TI-Toolbox ROI-based results\n")
                    f.write("# Layer order: MNI template → ROI difference map → Responder averages\n\n")
                else:
                    f.write("# FreeSurfer visualization for TI-Toolbox voxel-wise results\n")
                    f.write("# Layer order: MNI template → SVM weights → T-statistics → Significant voxels → Group differences\n\n")
                f.write(" ".join([f'"{part}"' if ' ' in part else part for part in cmd_parts]))
                f.write("\n")
            
            # Make executable
            import stat
            cmd_file.chmod(cmd_file.stat().st_mode | stat.S_IEXEC)
            
            self.logger.info("="*80)
            self.logger.info("FREEVIEW VISUALIZATION")
            self.logger.info("="*80)
            self.logger.info(f"FreeSurfer command saved: {cmd_file}")
            if self.use_roi_features:
                self.logger.info("To visualize ROI-based results:")
            else:
                self.logger.info("To visualize voxel-wise results:")
            self.logger.info(f"  {cmd_file}")
            self.logger.info("="*80)
            
        except Exception as e:
            self.logger.warning(f"Could not generate FreeSurfer command: {e}")
    
    def _generate_plots(self, results: Dict[str, Any], resp_data: np.ndarray, nonresp_data: np.ndarray):
        """Generate comprehensive visualization plots."""
        try:
            # Prepare training data for plotting
            training_data = {
                'resp_data': resp_data,
                'nonresp_data': nonresp_data,
                'resolution_mm': self.resolution_mm,
                'use_roi_features': self.use_roi_features
            }
            
            # Create all plots
            self.plotter.create_all_plots(results, training_data)
            
            # Create summary report
            self.plotter.create_summary_report(results, training_data)
            
            self.logger.info("="*80)
            self.logger.info("VISUALIZATION PLOTS GENERATED")
            self.logger.info("="*80)
            self.logger.info(f"Plots directory: {self.plotter.plots_dir}")
            self.logger.info("Generated files:")
            self.logger.info("  • performance_metrics.png/pdf - ROC curves, accuracy, confusion matrix")
            self.logger.info("  • weight_interpretation.png/pdf - Current intensity analysis")
            self.logger.info("  • roi_ranking.png/pdf - Brain region importance ranking")
            self.logger.info("  • dosing_analysis.png/pdf - Group comparisons and PCA clustering")
            self.logger.info("  • classification_report.txt - Comprehensive analysis summary")
            self.logger.info("="*80)
            
        except Exception as e:
            self.logger.error(f"Plot generation failed: {e}")
            import traceback
            self.logger.debug(f"Full traceback: {traceback.format_exc()}")

def main():
    """Command line interface."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='TI-Toolbox Classifier v2.0 - Production Ready',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Basic training:
    %(prog)s --project-dir /path/to/project --response-file responses.csv
  
  ROI-based training (recommended for small samples):
    %(prog)s --project-dir /path/to/project --response-file responses.csv --roi-features
  
  Custom settings:
    %(prog)s --project-dir /path/to/project --response-file responses.csv \\
      --resolution 3 --p-threshold 0.05 --roi-features
        """
    )
    
    parser.add_argument('--project-dir', required=True,
                       help='Path to TI-Toolbox project directory')
    parser.add_argument('--response-file', required=True,
                       help='Path to CSV file with response data')
    parser.add_argument('--output-dir',
                       help='Output directory (default: project/derivatives/ti-toolbox/classifier/results)')
    
    # Analysis settings
    parser.add_argument('--resolution', type=int, default=1, choices=[1, 2, 3, 4],
                       help='Resolution in mm (1=original, 2-4=downsampled, default: 1)')
    parser.add_argument('--p-threshold', type=float, default=0.01,
                       help='P-value threshold for feature selection (default: 0.01)')
    parser.add_argument('--cores', type=int, default=-1,
                       help='Number of CPU cores (-1=all, default: -1)')
    parser.add_argument('--roi-features', action='store_true',
                       help='Use ROI-averaged features (recommended for <50 subjects)')
    
    args = parser.parse_args()
    
    # Initialize and train classifier
    classifier = TIClassifier(
        project_dir=args.project_dir,
        output_dir=args.output_dir,
        resolution_mm=args.resolution,
        p_value_threshold=args.p_threshold,
        n_jobs=args.cores,
        use_roi_features=args.roi_features
    )
    
    try:
        results = classifier.train(args.response_file)
        
        print("\n" + "="*80)
        print("TRAINING COMPLETED SUCCESSFULLY")
        print("="*80)
        print(f"Accuracy: {results['cv_accuracy']:.1f}% ± {results['cv_std']:.1f}%")
        print(f"ROC-AUC: {results['roc_auc']:.3f}")
        print(f"Method: {results['method']}")
        print(f"Results saved to: {classifier.output_dir}")
        print("="*80)
        
        return 0
        
    except Exception as e:
        print(f"\nTraining failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
