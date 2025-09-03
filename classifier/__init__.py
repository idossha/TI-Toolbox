"""
TI-Toolbox Classifier v2.0 - Production Ready

Machine learning classification for TI (Temporal Interference) field analysis
following Albizu et al. (2020) methodology.
"""

from .ti_classifier import TIClassifier

__all__ = ['TIClassifier']

# Version information
__version__ = "2.0.0"
__author__ = "TI-Toolbox Development Team"
__description__ = "Production-ready TI field classifier with modular architecture"

# Analysis modes
class AnalysisMode:
    VOXEL_WISE = "voxel_wise"
    ROI_AVERAGED = "roi_averaged"

# Default configuration
class Config:
    DEFAULT_RESOLUTION_MM = 1
    DEFAULT_P_THRESHOLD = 0.01
    DEFAULT_N_JOBS = -1
    
    # Recommended settings
    SMALL_SAMPLE_RESOLUTION = 2  # mm
    LARGE_SAMPLE_RESOLUTION = 1  # mm
    SMALL_SAMPLE_THRESHOLD = 50  # subjects
    
    # Atlas information
    ATLAS_NAME = "HarvardOxford-cort-maxprob-thr0-1mm"
    ATLAS_REGIONS = 48  # Harvard-Oxford cortical regions
    
    # Expected QA metrics
    MIN_ATLAS_COVERAGE = 60.0  # %
    MIN_FIELD_COVERAGE = 50.0  # %
    MAX_VARIABILITY = 5.0      # %

def get_recommended_settings(n_subjects: int) -> dict:
    """Get recommended settings based on sample size."""
    if n_subjects < Config.SMALL_SAMPLE_THRESHOLD:
        return {
            'use_roi_features': True,
            'resolution_mm': Config.SMALL_SAMPLE_RESOLUTION,
            'p_value_threshold': 0.05,
            'analysis_mode': AnalysisMode.ROI_AVERAGED
        }
    else:
        return {
            'use_roi_features': False,
            'resolution_mm': Config.LARGE_SAMPLE_RESOLUTION,
            'p_value_threshold': 0.01,
            'analysis_mode': AnalysisMode.VOXEL_WISE
        }