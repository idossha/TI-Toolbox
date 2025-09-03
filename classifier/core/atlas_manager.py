#!/usr/bin/env python3
"""
Atlas Management Module for TI-Toolbox Classifier

Handles atlas loading, resampling, and alignment verification.
"""

import numpy as np
import nibabel as nib
from pathlib import Path
from typing import Dict, Optional, Tuple
import logging
import tempfile
import subprocess
import os


class AtlasManager:
    """Manages atlas loading, resampling, and alignment verification."""
    
    # Validated atlases with correct dimensions for TI-Toolbox
    SUPPORTED_ATLASES = {
        "HarvardOxford-cort-maxprob-thr0-1mm": {
            "description": "Harvard-Oxford Cortical Atlas (48 ROIs)",
            "filename": "HarvardOxford-cort-maxprob-thr0-1mm.nii.gz",
            "labels_file": "HarvardOxford-cort-maxprob-thr0-1mm.txt"
        },
        "MNI_Glasser_HCP_v1.0": {
            "description": "MNI Glasser HCP Atlas (360 ROIs)",
            "filename": "MNI_Glasser_HCP_v1.0.nii.gz", 
            "labels_file": "MNI_Glasser_HCP_v1.0.txt"
        }
    }
    
    def __init__(self, project_dir: str, atlas_name: str = "HarvardOxford-cort-maxprob-thr0-1mm", 
                 logger: logging.Logger = None):
        """
        Initialize atlas manager.
        
        Args:
            project_dir: Path to TI-Toolbox project directory
            atlas_name: Name of atlas to use (must be in SUPPORTED_ATLASES)
            logger: Logger instance
        """
        self.project_dir = Path(project_dir)
        
        # Validate atlas name
        if atlas_name not in self.SUPPORTED_ATLASES:
            raise ValueError(
                f"Unsupported atlas: '{atlas_name}'. "
                f"Supported atlases: {list(self.SUPPORTED_ATLASES.keys())}"
            )
        
        self.atlas_name = atlas_name
        self.atlas_info = self.SUPPORTED_ATLASES[atlas_name]
        self.logger = logger or logging.getLogger(__name__)
        
        # Atlas properties
        self.atlas_path = self._find_atlas()
        self.atlas_data = None
        self.atlas_labels = None
        
        # Load atlas
        self._load_atlas()
    
    def _find_atlas(self) -> Path:
        """Find specified atlas in validated TI-Toolbox atlas directory."""
        atlas_filename = self.atlas_info["filename"]
        
        # Prioritize TI-Toolbox standard atlas locations
        possible_paths = [
            # Primary: Docker mount (standard TI-Toolbox location)
            Path("/ti-toolbox/assets/atlas") / atlas_filename,
            # Secondary: Project relative (for development/testing)
            self.project_dir / "assets" / "atlas" / atlas_filename,
            # Tertiary: TI-toolbox installation directory
            Path(__file__).parent.parent.parent / "assets" / "atlas" / atlas_filename,
        ]
        
        for path in possible_paths:
            if path.exists():
                self.logger.info(f"Found validated atlas: {path}")
                return path
        
        # If not found, return the primary expected path with warning
        expected_path = Path("/ti-toolbox/assets/atlas") / atlas_filename
        self.logger.warning(f"Atlas not found in expected locations. Expected: {expected_path}")
        return expected_path
    
    def _load_atlas(self):
        """Load atlas and labels."""
        try:
            if self.atlas_path.exists():
                self.logger.info(f"Loading atlas from: {self.atlas_path}")
                atlas_img = nib.load(str(self.atlas_path))
                self.atlas_data = atlas_img.get_fdata()
                
                # Load atlas labels using validated filename
                labels_filename = self.atlas_info["labels_file"]
                possible_label_paths = [
                    # Primary: Same directory as atlas
                    self.atlas_path.parent / labels_filename,
                    # Secondary: TI-Toolbox standard locations
                    Path("/ti-toolbox/assets/atlas") / labels_filename,
                    self.project_dir / "assets" / "atlas" / labels_filename,
                ]
                
                labels_loaded = False
                for labels_path in possible_label_paths:
                    if labels_path.exists():
                        self.atlas_labels = self._load_atlas_labels(labels_path)
                        self.logger.info(f"Loaded {len(self.atlas_labels)} ROI labels from {labels_path.name}")
                        labels_loaded = True
                        break
                
                if not labels_loaded:
                    self.logger.warning(f"Atlas labels not found. Tried: {[str(p) for p in possible_label_paths]}")
            else:
                self.logger.warning(f"Atlas not found: {self.atlas_path}")
                
        except Exception as e:
            self.logger.error(f"Error loading atlas: {e}")
    
    def _load_atlas_labels(self, labels_path: Path) -> Dict[int, str]:
        """Load atlas ROI labels from text file."""
        labels = {}
        try:
            with open(labels_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            try:
                                roi_id = int(parts[0])
                                roi_name = parts[1].strip().replace('-', ' ')
                                labels[roi_id] = roi_name
                            except (ValueError, IndexError):
                                continue
        except Exception as e:
            self.logger.error(f"Error loading atlas labels: {e}")
        return labels
    
    def resample_atlas_to_match(self, target_shape: tuple, target_affine: np.ndarray) -> bool:
        """
        Resample atlas to match target data dimensions.
        
        Args:
            target_shape: Target shape (3D)
            target_affine: Target affine transformation
            
        Returns:
            True if successful, False otherwise
        """
        if self.atlas_data is None:
            self.logger.warning("No atlas loaded, skipping resampling")
            return False
            
        original_shape = self.atlas_data.shape
        if original_shape[:3] == target_shape[:3]:
            self.logger.info("Atlas already matches target resolution")
            return True
            
        self.logger.info(f"Resampling atlas from {original_shape} to {target_shape[:3]} using FreeSurfer mri_convert")
        
        try:
            # Use FreeSurfer's mri_convert for proper resampling
            resampled_atlas = self._resample_with_freesurfer(target_shape, target_affine)
            if resampled_atlas is not None:
                self.atlas_data = resampled_atlas
                self.logger.info(f"✓ Atlas resampled to: {self.atlas_data.shape}")
                return True
            else:
                # Fallback to scipy
                self.logger.warning("FreeSurfer not available, using scipy downsampling")
                self._resample_with_scipy(target_shape)
                return True
                
        except Exception as e:
            self.logger.error(f"Atlas resampling failed: {e}")
            return False
    
    def _resample_with_freesurfer(self, target_shape: tuple, target_affine: np.ndarray) -> Optional[np.ndarray]:
        """Resample atlas using FreeSurfer's mri_convert."""
        import tempfile
        import subprocess
        
        # Create temporary files
        with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as temp_template:
            template_path = temp_template.name
        
        with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as temp_output:
            output_path = temp_output.name
        
        try:
            # Create template image
            template_img = nib.Nifti1Image(np.zeros(target_shape[:3]), target_affine)
            nib.save(template_img, template_path)
            
            # Run mri_convert
            cmd = [
                'mri_convert',
                '--reslice_like', template_path,
                str(self.atlas_path),
                output_path
            ]
            
            self.logger.debug(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            # Load resampled atlas
            resampled_img = nib.load(output_path)
            resampled_data = resampled_img.get_fdata()
            
            self.logger.info("✓ Atlas resampled using FreeSurfer mri_convert")
            return resampled_data
            
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"mri_convert failed: {e.stderr}")
            return None
        except FileNotFoundError:
            self.logger.warning("mri_convert not found (FreeSurfer not installed)")
            return None
        finally:
            # Clean up temporary files
            for temp_file in [template_path, output_path]:
                try:
                    if os.path.exists(temp_file):
                        os.unlink(temp_file)
                except:
                    pass
    
    def _resample_with_scipy(self, target_shape: tuple):
        """Fallback resampling using scipy."""
        from scipy.ndimage import zoom
        
        zoom_factors = [target_shape[i] / self.atlas_data.shape[i] for i in range(3)]
        self.atlas_data = zoom(self.atlas_data, zoom_factors, order=0)
        
        self.logger.warning(f"Atlas resampled using scipy to: {self.atlas_data.shape}")
        self.logger.warning("⚠️  This may cause coordinate misalignment")
    
    def verify_alignment(self, data_shape: tuple, field_data: np.ndarray = None) -> Dict[str, float]:
        """
        Verify atlas-data alignment and calculate overlap metrics.
        
        Args:
            data_shape: Shape of the data to compare against
            field_data: Optional field data for overlap analysis
            
        Returns:
            Dictionary with alignment metrics
        """
        if self.atlas_data is None:
            return {'error': 'No atlas loaded'}
        
        data_shape_3d = data_shape[:3]
        atlas_shape = self.atlas_data.shape
        
        metrics = {
            'shapes_match': data_shape_3d == atlas_shape,
            'atlas_coverage_pct': 0,
            'field_in_atlas_pct': 0,
            'field_outside_atlas_pct': 0
        }
        
        if metrics['shapes_match']:
            # Calculate atlas coverage
            n_atlas_voxels = np.sum(self.atlas_data > 0)
            total_voxels = np.prod(atlas_shape)
            metrics['atlas_coverage_pct'] = n_atlas_voxels / total_voxels * 100
            
            # Calculate field overlap if provided
            if field_data is not None:
                field_voxels = np.sum(field_data > 0)
                overlap_voxels = np.sum((field_data > 0) & (self.atlas_data > 0))
                field_outside = np.sum((field_data > 0) & (self.atlas_data == 0))
                
                if field_voxels > 0:
                    metrics['field_in_atlas_pct'] = overlap_voxels / field_voxels * 100
                    metrics['field_outside_atlas_pct'] = field_outside / field_voxels * 100
                
                if n_atlas_voxels > 0:
                    metrics['atlas_field_coverage_pct'] = overlap_voxels / n_atlas_voxels * 100
        
        return metrics
    
    def get_roi_list(self) -> Dict[int, str]:
        """Get list of available ROIs."""
        if self.atlas_labels is None:
            return {}
        return self.atlas_labels.copy()
    
    def load_atlas_colors(self) -> Dict[int, tuple]:
        """Load atlas colors from LUT file."""
        roi_colors = {}
        
        possible_lut_paths = [
            self.project_dir / "assets" / "atlas" / "MNI_Glasser_HCP_v1.0.txt",
            self.atlas_path.with_suffix('.txt'),
            self.atlas_path.parent / "MNI_Glasser_HCP_v1.0.txt"
        ]
        
        for lut_path in possible_lut_paths:
            if lut_path.exists():
                self.logger.debug(f"Loading atlas colors from: {lut_path}")
                with open(lut_path, 'r') as f:
                    for line in f:
                        if line.startswith('#') or not line.strip():
                            continue
                        parts = line.strip().split('\t')
                        if len(parts) >= 6:
                            try:
                                roi_id = int(parts[0])
                                roi_name = parts[1]
                                r, g, b, a = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
                                roi_colors[roi_id] = (roi_name, r, g, b, a)
                            except (ValueError, IndexError):
                                continue
                        elif len(parts) >= 5:
                            try:
                                roi_id = int(parts[0])
                                roi_name = parts[1]
                                r, g, b = int(parts[2]), int(parts[3]), int(parts[4])
                                roi_colors[roi_id] = (roi_name, r, g, b, 255)
                            except (ValueError, IndexError):
                                continue
                
                self.logger.debug(f"Loaded colors for {len(roi_colors)} ROIs")
                break
        
        return roi_colors
    
    @classmethod
    def get_supported_atlases(cls) -> Dict[str, str]:
        """Get dictionary of supported atlas names and descriptions."""
        return {name: info["description"] for name, info in cls.SUPPORTED_ATLASES.items()}
    
    @classmethod
    def validate_atlas_name(cls, atlas_name: str) -> bool:
        """Check if atlas name is supported."""
        return atlas_name in cls.SUPPORTED_ATLASES
    
    def get_atlas_info(self) -> Dict[str, str]:
        """Get information about the current atlas."""
        return {
            "name": self.atlas_name,
            "description": self.atlas_info["description"],
            "filename": self.atlas_info["filename"],
            "labels_file": self.atlas_info["labels_file"],
            "path": str(self.atlas_path),
            "loaded": self.atlas_data is not None,
            "labels_loaded": self.atlas_labels is not None,
            "n_rois": len(self.atlas_labels) if self.atlas_labels else 0
        }
