#!/usr/bin/env python3
"""
Quality Assurance Reporter for TI-Toolbox Classifier

Generates comprehensive QA reports for atlas-field alignment analysis.
"""

import numpy as np
import pandas as pd
import nibabel as nib
from pathlib import Path
from typing import List, Dict
import logging
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


class QAReporter:
    """Generates quality assurance reports and visualizations."""
    
    def __init__(self, output_dir: Path, atlas_manager, logger: logging.Logger = None):
        """
        Initialize QA reporter.
        
        Args:
            output_dir: Directory to save QA reports
            atlas_manager: AtlasManager instance
            logger: Logger instance
        """
        self.output_dir = output_dir
        self.atlas_manager = atlas_manager
        self.logger = logger or logging.getLogger(__name__)
        
        # Create QA directory
        self.qa_dir = output_dir / "QA"
        self.qa_dir.mkdir(exist_ok=True)
    
    def create_comprehensive_report(self, responder_paths: List[Path], 
                                  nonresponder_paths: List[Path],
                                  template_shape: tuple, resolution_mm: int,
                                  use_roi_features: bool = False):
        """
        Create comprehensive QA report.
        
        Args:
            responder_paths: Paths to responder NIfTI files
            nonresponder_paths: Paths to non-responder NIfTI files
            template_shape: Shape of processed data
            resolution_mm: Resolution used
            use_roi_features: Whether ROI features were used
        """
        self.logger.info("="*80)
        self.logger.info("CREATING QUALITY ASSURANCE REPORT")
        self.logger.info("="*80)
        
        # A. Create detailed file log
        self._create_file_log(responder_paths, nonresponder_paths, resolution_mm, use_roi_features)
        
        # B. Create atlas information report
        self._create_atlas_report(template_shape, resolution_mm)
        
        # C. Create overlay visualizations
        self._create_overlay_images(responder_paths, template_shape, resolution_mm)
        
        # D. Create detailed overlap metrics
        self._create_overlap_metrics(responder_paths, nonresponder_paths, template_shape, resolution_mm)
        
        self.logger.info(f"✓ Quality Assurance report created in: {self.qa_dir}")
        self.logger.info("  Files created:")
        self.logger.info("    • QA.log - File paths and resolutions")
        self.logger.info("    • atlas_info.txt - Atlas details and ROI list")
        self.logger.info("    • overlay_before_resampling.png - Original alignment")
        if resolution_mm > 1:
            self.logger.info("    • overlay_after_resampling.png - Post-resampling alignment")
            self.logger.info("    • before_after_resampling_comparison.png - Side-by-side comparison")
        self.logger.info("    • overlap_metrics.csv - Per-subject overlap analysis")
        self.logger.info("    • overlap_summary.txt - Summary statistics and interpretation")
        self.logger.info("=" * 80)
    
    def _create_file_log(self, responder_paths: List[Path], nonresponder_paths: List[Path],
                        resolution_mm: int, use_roi_features: bool):
        """Create detailed file log."""
        qa_log_path = self.qa_dir / "QA.log"
        
        with open(qa_log_path, 'w') as qa_log:
            qa_log.write("TI-TOOLBOX CLASSIFIER QUALITY ASSURANCE REPORT\n")
            qa_log.write("=" * 60 + "\n")
            qa_log.write(f"Generated: {pd.Timestamp.now()}\n")
            qa_log.write(f"Resolution: {resolution_mm}mm\n")
            qa_log.write(f"Use ROI features: {use_roi_features}\n\n")
            
            qa_log.write("SUBJECT FILES AND PATHS:\n")
            qa_log.write("-" * 30 + "\n")
            
            # Log responder files
            qa_log.write("Responders:\n")
            for i, path in enumerate(responder_paths):
                self._log_file_info(qa_log, i+1, path)
            
            # Log non-responder files
            qa_log.write("Non-responders:\n")
            for i, path in enumerate(nonresponder_paths):
                self._log_file_info(qa_log, i+1, path)
    
    def _log_file_info(self, qa_log, index: int, path: Path):
        """Log information about a single file."""
        try:
            img = nib.load(str(path))
            qa_log.write(f"  {index:2d}. {path.name}\n")
            qa_log.write(f"      Path: {path}\n")
            qa_log.write(f"      Shape: {img.shape}\n")
            qa_log.write(f"      Voxel size: {img.header.get_zooms()[:3]}\n")
            qa_log.write(f"      Data range: {np.min(img.get_fdata()):.4f} to {np.max(img.get_fdata()):.4f}\n\n")
        except Exception as e:
            qa_log.write(f"  {index:2d}. ERROR loading {path}: {e}\n\n")
    
    def _create_atlas_report(self, template_shape: tuple, resolution_mm: int):
        """Create atlas information report."""
        atlas_info_path = self.qa_dir / "atlas_info.txt"
        
        with open(atlas_info_path, 'w') as f:
            f.write("ATLAS INFORMATION\n")
            f.write("=" * 40 + "\n\n")
            
            f.write(f"Atlas file: {self.atlas_manager.atlas_path}\n")
            f.write(f"Atlas exists: {self.atlas_manager.atlas_path.exists()}\n")
            
            if self.atlas_manager.atlas_path.exists():
                original_atlas = nib.load(str(self.atlas_manager.atlas_path))
                f.write(f"Original atlas shape: {original_atlas.shape}\n")
                f.write(f"Original atlas voxel size: {original_atlas.header.get_zooms()[:3]}\n")
                f.write(f"Original atlas affine:\n{original_atlas.affine}\n\n")
            
            if self.atlas_manager.atlas_data is not None:
                f.write(f"Processed atlas shape: {self.atlas_manager.atlas_data.shape}\n")
                f.write(f"Target data shape: {template_shape}\n")
                f.write(f"Resolution used: {resolution_mm}mm\n\n")
                
                unique_labels = np.unique(self.atlas_manager.atlas_data)
                f.write(f"Atlas labels found: {len(unique_labels)}\n")
                f.write(f"Non-zero labels: {len(unique_labels[unique_labels > 0])}\n\n")
                
                f.write("AVAILABLE ROI NAMES:\n")
                f.write("-" * 20 + "\n")
                if self.atlas_manager.atlas_labels:
                    for roi_id in sorted(unique_labels[unique_labels > 0])[:50]:
                        roi_name = self.atlas_manager.atlas_labels.get(int(roi_id), f"Unknown_{int(roi_id)}")
                        voxel_count = np.sum(self.atlas_manager.atlas_data == roi_id)
                        f.write(f"ROI {int(roi_id):3d}: {roi_name:<30} ({voxel_count:,} voxels)\n")
                    
                    if len(unique_labels) > 51:
                        f.write(f"... and {len(unique_labels) - 51} more ROIs\n")
    
    def _create_overlay_images(self, responder_paths: List[Path], template_shape: tuple, resolution_mm: int):
        """Create overlay visualization images."""
        try:
            if len(responder_paths) == 0:
                return
            
            first_subject_path = responder_paths[0]
            
            # ALWAYS create before resampling visualization
            original_img = nib.load(str(first_subject_path))
            original_data = original_img.get_fdata()
            if len(original_data.shape) == 4:
                original_data = original_data[:, :, :, 0]
            
            original_atlas = nib.load(str(self.atlas_manager.atlas_path))
            original_atlas_data = original_atlas.get_fdata()
            
            self._create_overlay_plot(
                original_data, original_atlas_data,
                self.qa_dir / "overlay_before_resampling.png",
                "BEFORE RESAMPLING - Original Resolution",
                f"Field: {original_data.shape}, Atlas: {original_atlas_data.shape}"
            )
            
            # Create AFTER resampling visualization if downsampling occurred
            if resolution_mm > 1:
                self.logger.info(f"Creating after-resampling overlay for {resolution_mm}mm resolution...")
                
                # Downsample the field data to target resolution
                downsampled_field = self._downsample_for_qa(original_img, resolution_mm)
                downsampled_field_data = downsampled_field.get_fdata()
                if len(downsampled_field_data.shape) == 4:
                    downsampled_field_data = downsampled_field_data[:, :, :, 0]
                
                # Use the resampled atlas data (should match the field)
                resampled_atlas_data = self.atlas_manager.atlas_data
                
                self._create_overlay_plot(
                    downsampled_field_data, resampled_atlas_data,
                    self.qa_dir / "overlay_after_resampling.png",
                    f"AFTER RESAMPLING - {resolution_mm}mm Resolution",
                    f"Field: {downsampled_field_data.shape}, Atlas: {resampled_atlas_data.shape}"
                )
                
                # Create comparison plot showing before vs after
                self._create_before_after_comparison(
                    original_data, original_atlas_data,
                    downsampled_field_data, resampled_atlas_data,
                    resolution_mm
                )
            else:
                self.logger.info("No downsampling performed - skipping after-resampling overlay")
            
        except Exception as e:
            self.logger.warning(f"Could not create overlay QA images: {e}")
    
    def _downsample_for_qa(self, img: nib.Nifti1Image, target_resolution: int) -> nib.Nifti1Image:
        """Downsample image for QA visualization (matches main classifier method)."""
        if target_resolution == 1:
            return img
        
        from scipy.ndimage import zoom, uniform_filter
        
        current_res = np.array(img.header.get_zooms()[:3])
        zoom_factors = current_res / target_resolution
        
        data = img.get_fdata()
        if len(data.shape) == 4:
            zoom_factors = np.append(zoom_factors, 1.0)
        
        # Use field averaging for proper downsampling (same as main classifier)
        if target_resolution > 1:
            block_sizes = 1.0 / zoom_factors
            if len(data.shape) == 3:
                averaged = uniform_filter(data, size=block_sizes, mode='constant')
                step_sizes = [int(np.round(bs)) for bs in block_sizes]
                downsampled_data = averaged[::step_sizes[0], ::step_sizes[1], ::step_sizes[2]]
            else:  # 4D
                downsampled_slices = []
                for t in range(data.shape[3]):
                    slice_3d = data[:, :, :, t]
                    averaged = uniform_filter(slice_3d, size=block_sizes[:3], mode='constant')
                    step_sizes = [int(np.round(bs)) for bs in block_sizes[:3]]
                    downsampled_slice = averaged[::step_sizes[0], ::step_sizes[1], ::step_sizes[2]]
                    downsampled_slices.append(downsampled_slice)
                downsampled_data = np.stack(downsampled_slices, axis=3)
        else:
            downsampled_data = data
        
        # Create new affine
        new_affine = img.affine.copy()
        for i in range(3):
            new_affine[i, i] *= (1/zoom_factors[i])
        
        new_img = nib.Nifti1Image(downsampled_data, new_affine, img.header)
        
        # Update header zooms
        if len(downsampled_data.shape) == 4:
            new_zooms = np.ones(4)
            new_zooms[:3] = target_resolution
            new_zooms[3] = img.header.get_zooms()[3]
        else:
            new_zooms = np.ones(3) * target_resolution
        
        new_img.header.set_zooms(new_zooms)
        
        return new_img
    
    def _create_before_after_comparison(self, original_field, original_atlas, 
                                      resampled_field, resampled_atlas, resolution_mm):
        """Create side-by-side comparison of before vs after resampling."""
        try:
            fig, axes = plt.subplots(2, 4, figsize=(20, 10))
            
            # Ensure original data shapes are compatible
            if original_field.shape != original_atlas.shape:
                self.logger.warning(f"Original shape mismatch: field {original_field.shape} vs atlas {original_atlas.shape}")
                min_orig_shape = tuple(min(f, a) for f, a in zip(original_field.shape, original_atlas.shape))
                original_field = original_field[:min_orig_shape[0], :min_orig_shape[1], :min_orig_shape[2]]
                original_atlas = original_atlas[:min_orig_shape[0], :min_orig_shape[1], :min_orig_shape[2]]
            
            # Ensure resampled data shapes are compatible
            if resampled_field.shape != resampled_atlas.shape:
                self.logger.warning(f"Resampled shape mismatch: field {resampled_field.shape} vs atlas {resampled_atlas.shape}")
                min_resamp_shape = tuple(min(f, a) for f, a in zip(resampled_field.shape, resampled_atlas.shape))
                resampled_field = resampled_field[:min_resamp_shape[0], :min_resamp_shape[1], :min_resamp_shape[2]]
                resampled_atlas = resampled_atlas[:min_resamp_shape[0], :min_resamp_shape[1], :min_resamp_shape[2]]
            
            # Get middle slices for both resolutions
            orig_mid_z = original_field.shape[2] // 2
            resamp_mid_z = resampled_field.shape[2] // 2
            
            # Before resampling (top row)
            axes[0, 0].imshow(original_field[:, :, orig_mid_z], cmap='hot')
            axes[0, 0].set_title(f'Original Field\n{original_field.shape}')
            axes[0, 0].axis('off')
            
            axes[0, 1].imshow(original_atlas[:, :, orig_mid_z] > 0, cmap='gray')
            axes[0, 1].set_title(f'Original Atlas\n{original_atlas.shape}')
            axes[0, 1].axis('off')
            
            axes[0, 2].imshow(original_field[:, :, orig_mid_z], cmap='hot', alpha=0.8)
            axes[0, 2].imshow(original_atlas[:, :, orig_mid_z] > 0, cmap='gray', alpha=0.3)
            axes[0, 2].set_title('Original Overlay')
            axes[0, 2].axis('off')
            
            # Calculate original overlap
            orig_overlap = np.sum((original_field > 0) & (original_atlas > 0))
            orig_field_voxels = np.sum(original_field > 0)
            orig_coverage = orig_overlap / orig_field_voxels * 100 if orig_field_voxels > 0 else 0
            axes[0, 3].text(0.5, 0.5, f'Original\nCoverage: {orig_coverage:.1f}%\nVoxels: {orig_field_voxels:,}', 
                           ha='center', va='center', transform=axes[0, 3].transAxes, fontsize=12)
            axes[0, 3].axis('off')
            
            # After resampling (bottom row)
            axes[1, 0].imshow(resampled_field[:, :, resamp_mid_z], cmap='hot')
            axes[1, 0].set_title(f'Resampled Field ({resolution_mm}mm)\n{resampled_field.shape}')
            axes[1, 0].axis('off')
            
            axes[1, 1].imshow(resampled_atlas[:, :, resamp_mid_z] > 0, cmap='gray')
            axes[1, 1].set_title(f'Resampled Atlas\n{resampled_atlas.shape}')
            axes[1, 1].axis('off')
            
            axes[1, 2].imshow(resampled_field[:, :, resamp_mid_z], cmap='hot', alpha=0.8)
            axes[1, 2].imshow(resampled_atlas[:, :, resamp_mid_z] > 0, cmap='gray', alpha=0.3)
            axes[1, 2].set_title('Resampled Overlay')
            axes[1, 2].axis('off')
            
            # Calculate resampled overlap
            resamp_overlap = np.sum((resampled_field > 0) & (resampled_atlas > 0))
            resamp_field_voxels = np.sum(resampled_field > 0)
            resamp_coverage = resamp_overlap / resamp_field_voxels * 100 if resamp_field_voxels > 0 else 0
            axes[1, 3].text(0.5, 0.5, f'Resampled\nCoverage: {resamp_coverage:.1f}%\nVoxels: {resamp_field_voxels:,}', 
                           ha='center', va='center', transform=axes[1, 3].transAxes, fontsize=12)
            axes[1, 3].axis('off')
            
            plt.suptitle(f"Resampling Comparison: 1mm → {resolution_mm}mm", fontsize=16)
            plt.tight_layout()
            plt.savefig(self.qa_dir / "before_after_resampling_comparison.png", dpi=300, bbox_inches='tight')
            plt.close()
            
            self.logger.info("✓ Created before/after resampling comparison plot")
            
        except Exception as e:
            self.logger.warning(f"Could not create before/after comparison: {e}")
    
    def _create_overlay_plot(self, field_data: np.ndarray, atlas_data: np.ndarray,
                           output_path: Path, title: str, subtitle: str):
        """Create overlay plot showing field and atlas alignment."""
        fig, axes = plt.subplots(2, 3, figsize=(15, 10))
        
        # Ensure data shapes are compatible
        if field_data.shape != atlas_data.shape:
            self.logger.warning(f"Shape mismatch: field {field_data.shape} vs atlas {atlas_data.shape}")
            # Use the smaller dimensions to avoid index errors
            min_shape = tuple(min(f, a) for f, a in zip(field_data.shape, atlas_data.shape))
            field_data = field_data[:min_shape[0], :min_shape[1], :min_shape[2]]
            atlas_data = atlas_data[:min_shape[0], :min_shape[1], :min_shape[2]]
        
        # Get middle slices (use the actual data shape)
        mid_x = field_data.shape[0] // 2
        mid_y = field_data.shape[1] // 2
        mid_z = field_data.shape[2] // 2
        
        # Overlay views
        axes[0, 0].imshow(field_data[mid_x, :, :], cmap='hot', alpha=0.8)
        axes[0, 0].imshow(atlas_data[mid_x, :, :] > 0, cmap='gray', alpha=0.3)
        axes[0, 0].set_title(f'Sagittal (x={mid_x})')
        axes[0, 0].axis('off')
        
        axes[0, 1].imshow(field_data[:, mid_y, :], cmap='hot', alpha=0.8)
        axes[0, 1].imshow(atlas_data[:, mid_y, :] > 0, cmap='gray', alpha=0.3)
        axes[0, 1].set_title(f'Coronal (y={mid_y})')
        axes[0, 1].axis('off')
        
        axes[0, 2].imshow(field_data[:, :, mid_z], cmap='hot', alpha=0.8)
        axes[0, 2].imshow(atlas_data[:, :, mid_z] > 0, cmap='gray', alpha=0.3)
        axes[0, 2].set_title(f'Axial (z={mid_z})')
        axes[0, 2].axis('off')
        
        # Individual views
        axes[1, 0].imshow(field_data[mid_x, :, :], cmap='hot')
        axes[1, 0].set_title('Field Only - Sagittal')
        axes[1, 0].axis('off')
        
        axes[1, 1].imshow(field_data[:, mid_y, :], cmap='hot')
        axes[1, 1].set_title('Field Only - Coronal')
        axes[1, 1].axis('off')
        
        axes[1, 2].imshow(atlas_data[:, :, mid_z] > 0, cmap='gray')
        axes[1, 2].set_title('Atlas Only - Axial')
        axes[1, 2].axis('off')
        
        plt.suptitle(f"{title}\n{subtitle}", fontsize=14)
        plt.tight_layout()
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
    
    def _create_overlap_metrics(self, responder_paths: List[Path], nonresponder_paths: List[Path],
                              template_shape: tuple, resolution_mm: int):
        """Create detailed overlap metrics analysis."""
        self.logger.info("Creating overlap metrics analysis...")
        
        metrics_path = self.qa_dir / "overlap_metrics.csv"
        metrics_data = []
        
        # Analyze each subject
        all_paths = [(path, "responder") for path in responder_paths] + \
                   [(path, "non_responder") for path in nonresponder_paths]
        
        for i, (path, group) in enumerate(all_paths):
            try:
                # Load subject data
                img = nib.load(str(path))
                field_data = img.get_fdata()
                if len(field_data.shape) == 4:
                    field_data = field_data[:, :, :, 0]
                
                # Downsample field data to match atlas resolution if needed
                if resolution_mm > 1:
                    # Use the same downsampling method as the main classifier
                    field_img = nib.Nifti1Image(field_data, img.affine, img.header)
                    downsampled_field_img = self._downsample_for_qa(field_img, resolution_mm)
                    field_data = downsampled_field_img.get_fdata()
                    if len(field_data.shape) == 4:
                        field_data = field_data[:, :, :, 0]
                
                # Ensure field and atlas have the same shape
                atlas_data = self.atlas_manager.atlas_data
                if field_data.shape != atlas_data.shape:
                    self.logger.warning(f"Shape mismatch for {path.name}: field {field_data.shape} vs atlas {atlas_data.shape}")
                    # Crop to smallest common shape to avoid broadcast errors
                    min_shape = tuple(min(f, a) for f, a in zip(field_data.shape, atlas_data.shape))
                    field_data = field_data[:min_shape[0], :min_shape[1], :min_shape[2]]
                    atlas_data = atlas_data[:min_shape[0], :min_shape[1], :min_shape[2]]
                else:
                    atlas_data = self.atlas_manager.atlas_data
                
                field_data_flat = field_data.flatten()
                atlas_data_flat = atlas_data.flatten()
                
                # Calculate overlap metrics
                field_voxels = np.sum(field_data_flat > 0)
                atlas_voxels = np.sum(atlas_data_flat > 0)
                overlap_voxels = np.sum((field_data_flat > 0) & (atlas_data_flat > 0))
                field_outside_atlas = np.sum((field_data_flat > 0) & (atlas_data_flat == 0))
                
                # Calculate percentages
                field_in_atlas_pct = (overlap_voxels / field_voxels * 100) if field_voxels > 0 else 0
                field_outside_atlas_pct = (field_outside_atlas / field_voxels * 100) if field_voxels > 0 else 0
                atlas_coverage_pct = (overlap_voxels / atlas_voxels * 100) if atlas_voxels > 0 else 0
                
                metrics_data.append({
                    'subject_id': path.parent.parent.parent.name,
                    'group': group,
                    'file_name': path.name,
                    'field_voxels': field_voxels,
                    'atlas_voxels': atlas_voxels,
                    'overlap_voxels': overlap_voxels,
                    'field_in_atlas_pct': field_in_atlas_pct,
                    'field_outside_atlas_pct': field_outside_atlas_pct,
                    'atlas_coverage_pct': atlas_coverage_pct
                })
                
            except Exception as e:
                self.logger.warning(f"Error analyzing {path}: {e}")
        
        # Save metrics
        if metrics_data:
            metrics_df = pd.DataFrame(metrics_data)
            metrics_df.to_csv(metrics_path, index=False)
            
            # Create summary
            self._create_overlap_summary(metrics_data)
    
    def _create_overlap_summary(self, metrics_data: List[Dict]):
        """Create overlap summary with interpretation."""
        summary_path = self.qa_dir / "overlap_summary.txt"
        
        with open(summary_path, 'w') as f:
            f.write("OVERLAP ANALYSIS SUMMARY\n")
            f.write("=" * 40 + "\n\n")
            
            if metrics_data:
                field_in_atlas_values = [m['field_in_atlas_pct'] for m in metrics_data]
                field_outside_values = [m['field_outside_atlas_pct'] for m in metrics_data]
                atlas_coverage_values = [m['atlas_coverage_pct'] for m in metrics_data]
                
                f.write(f"Number of subjects analyzed: {len(metrics_data)}\n\n")
                f.write("FIELD-ATLAS OVERLAP STATISTICS:\n")
                f.write(f"Field in atlas: {np.mean(field_in_atlas_values):.1f}% ± {np.std(field_in_atlas_values):.1f}%\n")
                f.write(f"Field outside atlas: {np.mean(field_outside_values):.1f}% ± {np.std(field_outside_values):.1f}%\n")
                f.write(f"Atlas coverage: {np.mean(atlas_coverage_values):.1f}% ± {np.std(atlas_coverage_values):.1f}%\n\n")
                
                # Interpretation
                avg_field_in_atlas = np.mean(field_in_atlas_values)
                f.write("INTERPRETATION:\n")
                if avg_field_in_atlas < 50:
                    f.write("❌ CRITICAL: Most field data is outside atlas regions!\n")
                    f.write("   This indicates severe coordinate misalignment.\n")
                    f.write("   Consider using FSL normalization for better alignment.\n")
                elif avg_field_in_atlas < 70:
                    f.write("⚠️  WARNING: Significant field data outside atlas.\n")
                    f.write("   Some alignment issues may be present.\n")
                else:
                    f.write("✓ GOOD: Most field data aligns with atlas regions.\n")
                    f.write("   Alignment appears correct.\n")
