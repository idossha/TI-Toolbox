#!/usr/bin/env simnibs_python
"""
Unified Cluster-Based Permutation Testing for TI-Toolbox

This script provides unified cluster-based permutation testing for both:
1. Group comparison analysis (binary responder/non-responder classification)
2. Correlation analysis (continuous outcome measures)

Supports both t-test and correlation-based statistical approaches with
cluster-based permutation correction for multiple comparisons.

Usage:
    from ti_toolbox.stats import permutation_analysis
    # Group comparison
    results = permutation_analysis.run_analysis(
        subject_configs, analysis_name, analysis_type='group_comparison'
    )
    # Correlation analysis
    results = permutation_analysis.run_analysis(
        subject_configs, analysis_name, analysis_type='correlation'
    )

For GUI usage, see gui/extensions/permutation_analysis.py
"""

import nibabel as nib
import pandas as pd
import numpy as np

import os
import sys
import warnings
warnings.filterwarnings('ignore')
import logging
from datetime import datetime
import time
from pathlib import Path
import gc

from .stats_utils import (
    ttest_voxelwise, cluster_based_correction,
    correlation_voxelwise, correlation_cluster_correction,
    cluster_analysis
)
from .atlas_utils import atlas_overlap_analysis
from .visualization import plot_permutation_null_distribution, plot_cluster_size_mass_correlation
from .reporting import generate_summary, generate_correlation_summary

# Import TI-Toolbox core modules
sys.path.insert(0, str(Path(__file__).parent.parent))
from core import get_path_manager
from core import constants as const
from core import nifti
from tools import logging_util


# ==============================================================================
# UNIFIED DATA LOADING
# ==============================================================================

def load_subject_data(subject_configs, nifti_file_pattern=None, analysis_type='group_comparison'):
    """
    Unified data loading for both group comparison and correlation analysis

    Parameters:
    -----------
    subject_configs : list of dict
        Subject configurations (format depends on analysis_type)
    nifti_file_pattern : str, optional
        Pattern for NIfTI files
    analysis_type : str
        Either 'group_comparison' or 'correlation'

    Returns:
    --------
    For group_comparison:
        responders, non_responders, template_img, resp_ids, non_resp_ids
    For correlation:
        subject_data, effect_sizes, weights, template_img, subject_ids
    """
    if analysis_type == 'group_comparison':
        return load_subject_data_group_comparison(subject_configs, nifti_file_pattern)
    elif analysis_type == 'correlation':
        return load_subject_data_correlation(subject_configs, nifti_file_pattern)
    else:
        raise ValueError(f"Unknown analysis_type: {analysis_type}")


def load_subject_data_group_comparison(subject_configs, nifti_file_pattern=None):
    """
    Load subject data for group comparison analysis (binary outcomes)
    """
    if nifti_file_pattern is None:
        nifti_file_pattern = "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"

    # Separate configs by response
    responder_configs = [c for c in subject_configs if c['response'] == 1]
    non_responder_configs = [c for c in subject_configs if c['response'] == 0]

    if len(responder_configs) == 0 or len(non_responder_configs) == 0:
        raise ValueError("Need at least one responder and one non-responder")

    # Load responders
    responders, template_img, responder_ids = nifti.load_group_data_ti_toolbox(
        responder_configs,
        nifti_file_pattern=nifti_file_pattern,
        dtype=np.float32
    )

    # Load non-responders
    non_responders, _, non_responder_ids = nifti.load_group_data_ti_toolbox(
        non_responder_configs,
        nifti_file_pattern=nifti_file_pattern,
        dtype=np.float32
    )

    print(f"\nLoaded {len(responder_ids)} responders: {responder_ids}")
    print(f"Loaded {len(non_responder_ids)} non-responders: {non_responder_ids}")
    print(f"Responders shape: {responders.shape}")
    print(f"Non-responders shape: {non_responders.shape}")

    return responders, non_responders, template_img, responder_ids, non_responder_ids


def load_subject_data_correlation(subject_configs, nifti_file_pattern=None):
    """
    Load subject data for correlation analysis (continuous outcomes)
    """
    if nifti_file_pattern is None:
        nifti_file_pattern = "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"

    # Check for required fields
    required_fields = ['subject_id', 'simulation_name', 'effect_size']
    for config in subject_configs:
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field '{field}' in subject config")

    # Load all subjects
    subject_data, template_img, subject_ids = nifti.load_group_data_ti_toolbox(
        subject_configs,
        nifti_file_pattern=nifti_file_pattern,
        dtype=np.float32
    )

    # Build a lookup from subject_id to config for successfully loaded subjects
    config_lookup = {c['subject_id']: c for c in subject_configs}

    # Extract effect sizes and weights only for successfully loaded subjects
    effect_sizes = []
    weights_list = []
    has_weights = 'weight' in subject_configs[0]

    for sid in subject_ids:
        config = config_lookup[sid]
        effect_sizes.append(config['effect_size'])
        if has_weights:
            weights_list.append(config.get('weight', 1.0))

    effect_sizes = np.array(effect_sizes, dtype=np.float64)
    weights = np.array(weights_list, dtype=np.float64) if has_weights else None

    print(f"\nLoaded {len(subject_ids)} subjects: {subject_ids}")
    print(f"Effect sizes: mean={np.mean(effect_sizes):.3f}, std={np.std(effect_sizes):.3f}")
    print(f"Effect size range: [{np.min(effect_sizes):.3f}, {np.max(effect_sizes):.3f}]")
    if weights is not None:
        print(f"Weights: mean={np.mean(weights):.3f}, range=[{np.min(weights):.3f}, {np.max(weights):.3f}]")
    print(f"Data shape: {subject_data.shape}")

    return subject_data, effect_sizes, weights, template_img, subject_ids


def prepare_config_from_csv(csv_file, analysis_type='group_comparison'):
    """
    Load subject configurations from CSV file

    Parameters:
    -----------
    csv_file : str
        Path to CSV file
    analysis_type : str
        Either 'group_comparison' or 'correlation'

    Returns:
    --------
    list of dict : Subject configurations
    """
    df = pd.read_csv(csv_file)

    if analysis_type == 'group_comparison':
        # Validate required columns for group comparison
        required_cols = ['subject_id', 'simulation_name', 'response']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"CSV file missing required column: '{col}' for group comparison")

        configs = []
        for _, row in df.iterrows():
            # Handle both 'sub-XXX' and 'XXX' formats
            subject_id = str(row['subject_id']).replace('sub-', '')

            configs.append({
                'subject_id': subject_id,
                'simulation_name': row['simulation_name'],
                'response': int(row['response'])
            })

    elif analysis_type == 'correlation':
        # Validate required columns for correlation
        required_cols = ['subject_id', 'simulation_name', 'effect_size']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"CSV file missing required column: '{col}' for correlation analysis")

        configs = []
        skipped_rows = 0
        for _, row in df.iterrows():
            # Skip rows with missing required fields
            if pd.isna(row['subject_id']) or pd.isna(row['simulation_name']) or pd.isna(row['effect_size']):
                skipped_rows += 1
                continue

            # Handle both 'sub-XXX' and 'XXX' formats
            # Also handle float-to-string conversion (e.g., 101.0 -> "101")
            raw_id = row['subject_id']
            if isinstance(raw_id, float):
                # Convert float to int then to string (101.0 -> "101")
                subject_id = str(int(raw_id))
            else:
                subject_id = str(raw_id).replace('sub-', '')
                # Also handle string representations of floats like "101.0"
                if subject_id.endswith('.0'):
                    subject_id = subject_id[:-2]

            config = {
                'subject_id': subject_id,
                'simulation_name': str(row['simulation_name']),
                'effect_size': float(row['effect_size'])
            }

            # Add weight if present
            if 'weight' in df.columns and pd.notna(row.get('weight')):
                config['weight'] = float(row['weight'])

            configs.append(config)

        if skipped_rows > 0:
            print(f"Note: Skipped {skipped_rows} rows with missing required fields")

        if len(configs) == 0:
            raise ValueError("No valid subject configurations found in CSV file")

    else:
        raise ValueError(f"Unknown analysis_type: {analysis_type}")

    return configs


# ==============================================================================
# CONFIGURATION
# ==============================================================================

DEFAULT_CONFIG_GROUP_COMPARISON = {
    # Analysis type
    'analysis_type': 'group_comparison',

    # Statistical parameters
    'test_type': 'unpaired',        # 'paired' or 'unpaired' t-test
    'alternative': 'two-sided',       # 'two-sided', 'greater' (resp > non-resp), or 'less'
    'cluster_threshold': 0.05,      # p < 0.05 for cluster formation
    'cluster_stat': 'mass',         # 'size' (voxel count) or 'mass' (sum of t-values)
    'n_permutations': 1000,         # Number of permutations
    'alpha': 0.05,                  # Cluster-level significance
    'n_jobs': -1,                   # Number of parallel jobs (-1 = all cores)

    # Group and metric labels (customize for your study)
    'group1_name': 'Responders',
    'group2_name': 'Non-Responders',
    'value_metric': 'Current Intensity',

    # Tissue type selection: 'grey', 'white', or 'all'
    'tissue_type': 'grey',

    # File pattern for NIfTI files (auto-generated from tissue_type if not provided)
    'nifti_file_pattern': None,

    # Atlas files (optional)
    'atlas_files': []
}

DEFAULT_CONFIG_CORRELATION = {
    # Analysis type
    'analysis_type': 'correlation',

    # Statistical parameters
    'correlation_type': 'pearson',   # 'pearson' or 'spearman'
    'cluster_threshold': 0.05,       # p < 0.05 for cluster formation
    'cluster_stat': 'mass',          # 'size' (voxel count) or 'mass' (sum of t-values)
    'n_permutations': 1000,          # Number of permutations
    'alpha': 0.05,                   # Cluster-level significance
    'n_jobs': -1,                    # Number of parallel jobs (-1 = all cores)
    'use_weights': True,             # Use weights if available in CSV

    # Labels for reports
    'effect_metric': 'Effect Size',  # Name of the outcome measure
    'field_metric': 'Electric Field Magnitude',

    # Tissue type selection: 'grey', 'white', or 'all'
    'tissue_type': 'grey',

    # File pattern for NIfTI files (auto-generated from tissue_type if not provided)
    'nifti_file_pattern': None,

    # Atlas files (optional)
    'atlas_files': []
}


# ==============================================================================
# LOGGING SETUP
# ==============================================================================

def setup_logging(output_dir, analysis_type='group_comparison', callback_handler=None):
    """
    Set up logging for unified analysis

    Parameters:
    -----------
    output_dir : str
        Directory where log file will be saved
    analysis_type : str
        Type of analysis for log naming
    callback_handler : logging.Handler, optional
        Callback handler for GUI integration

    Returns:
    --------
    logger : logging.Logger
        Configured logger instance
    log_file : str
        Path to log file
    """
    if logging_util is None:
        raise ImportError("logging_util module not available")

    # Create timestamp for log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"{analysis_type}_analysis_{timestamp}.log")

    # Create logger
    logger_name = f"{'GroupComparison' if analysis_type == 'group_comparison' else 'Correlation'}Analysis"
    logger = logging_util.get_logger(logger_name, log_file, overwrite=True)

    # If callback handler provided (for GUI), suppress console output and add callback
    if callback_handler:
        logging_util.suppress_console_output(logger)
        logger.addHandler(callback_handler)

    # Configure external loggers
    external_loggers = ['scipy', 'numpy', 'nibabel', 'pandas', 'matplotlib']
    logging_util.configure_external_loggers(external_loggers, logger)

    return logger, log_file


# ==============================================================================
# MAIN WORKFLOW
# ==============================================================================

def run_analysis(subject_configs, analysis_name, config=None, output_callback=None,
                 callback_handler=None, progress_callback=None, stop_callback=None):
    """
    Run unified cluster-based permutation analysis

    Parameters:
    -----------
    subject_configs : list of dict or str
        Either a list of subject configurations or path to CSV file
    analysis_name : str
        Name for this analysis (used for output directory)
    config : dict, optional
        Configuration dictionary (merged with defaults based on analysis_type)
    output_callback : callable, optional
        Callback function for status updates (for GUI integration)
    callback_handler : logging.Handler, optional
        Callback handler for GUI console integration
    progress_callback : callable, optional
        Callback function for progress updates
    stop_callback : callable, optional
        Callback function to check if analysis should be stopped

    Returns:
    --------
    dict : Results dictionary (structure depends on analysis_type)
    """
    # Determine analysis type from config or default
    analysis_type = 'group_comparison'  # default
    if config and 'analysis_type' in config:
        analysis_type = config['analysis_type']

    # Merge config with appropriate defaults
    if analysis_type == 'group_comparison':
        CONFIG = DEFAULT_CONFIG_GROUP_COMPARISON.copy()
    elif analysis_type == 'correlation':
        CONFIG = DEFAULT_CONFIG_CORRELATION.copy()
    else:
        raise ValueError(f"Unknown analysis_type: {analysis_type}")

    if config:
        CONFIG.update(config)

    # Ensure analysis_type is set in CONFIG
    CONFIG['analysis_type'] = analysis_type

    # Callback helper
    def log_callback(msg):
        if output_callback:
            output_callback(msg)

    # Start timing
    analysis_start_time = time.time()

    # Set up output directory
    pm = get_path_manager() if get_path_manager else None
    if pm:
        project_dir = pm.project_dir
        derivatives_dir = pm.get_derivatives_dir()
        output_dir = os.path.join(
            derivatives_dir,
            const.DIR_TI_TOOLBOX,
            'stats',
            analysis_type,
            analysis_name
        )
    else:
        project_dir = os.environ.get('PROJECT_DIR', '/mnt')
        output_dir = os.path.join(
            project_dir,
            'derivatives',
            'ti-toolbox',
            'stats',
            analysis_type,
            analysis_name
        )

    os.makedirs(output_dir, exist_ok=True)

    # Set up logging
    if callback_handler:
        logger, log_file = setup_logging(output_dir, analysis_type, callback_handler)
    else:
        logger, log_file = setup_logging(output_dir, analysis_type)

    # Log header
    analysis_title = "CLUSTER-BASED PERMUTATION TESTING" if analysis_type == 'group_comparison' else "CORRELATION-BASED CLUSTER PERMUTATION TESTING"
    subtitle = "" if analysis_type == 'group_comparison' else "(ACES-style analysis for continuous outcomes)"

    logger.info("="*70)
    logger.info(analysis_title)
    if subtitle:
        logger.info(subtitle)
    logger.info("="*70)
    logger.info(f"Analysis started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Analysis name: {analysis_name}")
    logger.info(f"Analysis type: {analysis_type}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Log file: {log_file}")
    logger.info("")

    log_callback(f"Starting {analysis_type} analysis: {analysis_name}")

    # Construct nifti_file_pattern from tissue_type
    if CONFIG.get('nifti_file_pattern') is None:
        tissue_type = CONFIG.get('tissue_type', 'grey')
        if tissue_type == 'grey':
            CONFIG['nifti_file_pattern'] = 'grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz'
        elif tissue_type == 'white':
            CONFIG['nifti_file_pattern'] = 'white_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz'
        elif tissue_type == 'all':
            CONFIG['nifti_file_pattern'] = '{simulation_name}_TI_MNI_MNI_TI_max.nii.gz'
        else:
            raise ValueError(f"Invalid tissue_type: '{tissue_type}'. Must be 'grey', 'white', or 'all'")

    # Log configuration
    logger.info("CONFIGURATION:")
    if analysis_type == 'group_comparison':
        logger.info(f"  Statistical test: {CONFIG['test_type'].capitalize()} t-test")
        alt_text = {
            'two-sided': 'two-sided (≠)',
            'greater': f"one-sided ({CONFIG['group1_name']} > {CONFIG['group2_name']})",
            'less': f"one-sided ({CONFIG['group1_name']} < {CONFIG['group2_name']})"
        }
        logger.info(f"  Alternative hypothesis: {alt_text.get(CONFIG['alternative'], CONFIG['alternative'])}")
    else:
        logger.info(f"  Correlation type: {CONFIG['correlation_type'].capitalize()}")

    cluster_stat_name = "Cluster Size" if CONFIG['cluster_stat'] == 'size' else "Cluster Mass"
    logger.info(f"  Cluster statistic: {cluster_stat_name}")
    logger.info(f"  Cluster threshold: {CONFIG['cluster_threshold']}")
    logger.info(f"  Number of permutations: {CONFIG['n_permutations']}")
    logger.info(f"  Alpha level: {CONFIG['alpha']}")
    logger.info(f"  Parallel jobs: {CONFIG['n_jobs']}")
    logger.info(f"  Tissue type: {CONFIG.get('tissue_type', 'grey')}")
    logger.info(f"  NIfTI pattern: {CONFIG['nifti_file_pattern']}")
    logger.info("")

    # Load subject configurations
    if isinstance(subject_configs, str):
        logger.info(f"Loading subject configurations from: {subject_configs}")
        subject_configs = prepare_config_from_csv(subject_configs, analysis_type)

    # Branch based on analysis type
    if analysis_type == 'group_comparison':
        return _run_group_comparison_analysis(
            subject_configs, CONFIG, output_dir, logger, log_callback,
            analysis_start_time, log_file, stop_callback
        )
    else:  # correlation
        return _run_correlation_analysis(
            subject_configs, CONFIG, output_dir, logger, log_callback,
            analysis_start_time, log_file, stop_callback
        )


def _run_group_comparison_analysis(subject_configs, CONFIG, output_dir, logger, log_callback,
                                   analysis_start_time, log_file, stop_callback):
    """Run group comparison analysis workflow"""

    # -------------------------------------------------------------------------
    # 1. LOAD DATA
    # -------------------------------------------------------------------------
    logger.info("\n[1/8] LOADING SUBJECT DATA")
    logger.info("-" * 70)
    log_callback("Loading subject data...")
    step_start = time.time()

    responders, non_responders, template_img, resp_ids, non_resp_ids = load_subject_data(
        subject_configs,
        nifti_file_pattern=CONFIG['nifti_file_pattern'],
        analysis_type='group_comparison'
    )

    logger.info(f"Loaded {responders.shape[-1]} {CONFIG['group1_name']}: {resp_ids}")
    logger.info(f"Loaded {non_responders.shape[-1]} {CONFIG['group2_name']}: {non_resp_ids}")
    logger.info(f"Image shape: {responders.shape[:3]}")

    # Data diagnostics
    resp_mean = np.mean(responders[responders > 0]) if np.any(responders > 0) else 0
    non_resp_mean = np.mean(non_responders[non_responders > 0]) if np.any(non_responders > 0) else 0
    resp_max = np.max(responders)
    non_resp_max = np.max(non_responders)
    resp_nonzero = np.sum(responders > 0)
    non_resp_nonzero = np.sum(non_responders > 0)

    logger.info(f"\nDATA DIAGNOSTICS:")
    logger.info(f"  Responders - Mean (non-zero): {resp_mean:.6f}, Max: {resp_max:.6f}, Non-zero voxels: {resp_nonzero}")
    logger.info(f"  Non-Responders - Mean (non-zero): {non_resp_mean:.6f}, Max: {non_resp_max:.6f}, Non-zero voxels: {non_resp_nonzero}")
    logger.info(f"  Data appears valid: {resp_max > 0 and non_resp_max > 0}")

    try:
        import psutil
        process = psutil.Process()
        mem_info = process.memory_info()
        logger.info(f"  Memory usage: {mem_info.rss / (1024**3):.2f} GB")
    except:
        pass

    logger.info(f"\nStep completed in {time.time() - step_start:.2f} seconds")

    if stop_callback and stop_callback():
        logger.warning("Analysis stopped by user during data loading")
        raise KeyboardInterrupt("Analysis stopped by user")

    # -------------------------------------------------------------------------
    # 2. VOXELWISE STATISTICAL TEST
    # -------------------------------------------------------------------------
    logger.info("\n[2/8] RUNNING VOXELWISE STATISTICAL TESTS")
    logger.info("-" * 70)
    log_callback("Running voxelwise statistical tests...")
    step_start = time.time()

    p_values, t_statistics, valid_mask = ttest_voxelwise(
        responders,
        non_responders,
        test_type=CONFIG['test_type'],
        alternative=CONFIG['alternative']
    )

    n_valid = np.sum(valid_mask)
    logger.info(f"Tested {n_valid} valid voxels")
    logger.info(f"Minimum p-value: {np.min(p_values[valid_mask]):.6e}")
    logger.info(f"Maximum p-value: {np.max(p_values[valid_mask]):.6e}")
    logger.info(f"Voxels with p<0.01: {np.sum((p_values < 0.01) & valid_mask)}")
    logger.info(f"Voxels with p<0.05: {np.sum((p_values < 0.05) & valid_mask)}")
    logger.info(f"Voxels with p<0.10: {np.sum((p_values < 0.10) & valid_mask)}")

    # T-statistic diagnostics
    t_nonzero = np.sum(t_statistics != 0)
    if t_nonzero > 0:
        logger.info(f"\nT-STATISTIC DIAGNOSTICS:")
        logger.info(f"  Non-zero t-statistics: {t_nonzero}")
        logger.info(f"  Min t-stat: {np.min(t_statistics[t_statistics != 0]):.4f}")
        logger.info(f"  Max t-stat: {np.max(t_statistics):.4f}")
        logger.info(f"  Mean |t-stat|: {np.mean(np.abs(t_statistics[t_statistics != 0])):.4f}")
    else:
        logger.info(f"\nWARNING: All t-statistics are zero!")

    logger.info(f"\nStep completed in {time.time() - step_start:.2f} seconds")

    # Log observed clusters before permutation correction (vectorized for speed)
    from scipy.ndimage import label as scipy_label
    observed_mask = (p_values < CONFIG['cluster_threshold']) & valid_mask
    observed_labeled, n_observed_clusters = scipy_label(observed_mask)

    logger.info(f"\nObserved clusters at p < {CONFIG['cluster_threshold']} (before permutation correction):")
    logger.info(f"Total clusters found: {n_observed_clusters}")

    if n_observed_clusters > 0:
        # Vectorized cluster size computation using bincount
        cluster_labels_flat = observed_labeled.ravel()
        observed_cluster_sizes = np.bincount(cluster_labels_flat, minlength=n_observed_clusters + 1)[1:]
        observed_cluster_sizes_sorted = np.sort(observed_cluster_sizes)[::-1]

        logger.info(f"\nTop 10 largest observed clusters (before permutation correction):")
        for i, size in enumerate(observed_cluster_sizes_sorted[:10], 1):
            logger.info(f"  Cluster {i:2d}: {size:6d} voxels")

        logger.info(f"\nLargest observed cluster: {observed_cluster_sizes_sorted[0]} voxels")
        logger.info(f"Total voxels in all clusters: {np.sum(observed_cluster_sizes)}")

    if stop_callback and stop_callback():
        logger.warning("Analysis stopped by user before permutation testing")
        raise KeyboardInterrupt("Analysis stopped by user")

    # -------------------------------------------------------------------------
    # 3. CLUSTER-BASED PERMUTATION CORRECTION
    # -------------------------------------------------------------------------
    logger.info("\n[3/8] APPLYING CLUSTER-BASED PERMUTATION CORRECTION")
    logger.info("-" * 70)
    log_callback(f"Running permutation testing ({CONFIG['n_permutations']} permutations)...")
    step_start = time.time()

    permutation_log_file = os.path.join(output_dir, 'permutation_details.txt')

    sig_mask, cluster_threshold, sig_clusters, null_distribution, all_clusters, correlation_data = cluster_based_correction(
        responders,
        non_responders,
        p_values,
        valid_mask,
        cluster_threshold=CONFIG['cluster_threshold'],
        n_permutations=CONFIG['n_permutations'],
        alpha=CONFIG['alpha'],
        test_type=CONFIG['test_type'],
        alternative=CONFIG['alternative'],
        cluster_stat=CONFIG['cluster_stat'],
        t_statistics=t_statistics,
        n_jobs=CONFIG['n_jobs'],
        logger=logger,
        save_permutation_log=True,
        permutation_log_file=permutation_log_file,
        subject_ids_resp=resp_ids,
        subject_ids_non_resp=non_resp_ids
    )

    if CONFIG['cluster_stat'] == 'size':
        logger.info(f"Cluster size threshold: {cluster_threshold:.1f} voxels")
    else:
        logger.info(f"Cluster mass threshold: {cluster_threshold:.2f}")
    logger.info(f"Significant clusters found: {len(sig_clusters)}")
    logger.info(f"Total significant voxels: {np.sum(sig_mask)}")
    logger.info(f"Step completed in {time.time() - step_start:.2f} seconds")

    # -------------------------------------------------------------------------
    # 4. CLUSTER ANALYSIS
    # -------------------------------------------------------------------------
    logger.info("\n[4/8] ANALYZING SIGNIFICANT CLUSTERS")
    logger.info("-" * 70)
    log_callback(f"Analyzing {len(sig_clusters)} significant clusters...")
    step_start = time.time()

    clusters = cluster_analysis(sig_mask, template_img.affine)

    if clusters:
        logger.info(f"Largest cluster: {clusters[0]['size']} voxels")
        logger.info(f"MNI center: ({clusters[0]['center_mni'][0]:.1f}, "
                   f"{clusters[0]['center_mni'][1]:.1f}, {clusters[0]['center_mni'][2]:.1f})")
    logger.info(f"Step completed in {time.time() - step_start:.2f} seconds")

    # -------------------------------------------------------------------------
    # 5. PLOT PERMUTATION NULL DISTRIBUTION
    # -------------------------------------------------------------------------
    logger.info("\n[5/8] PLOTTING PERMUTATION NULL DISTRIBUTION")
    logger.info("-" * 70)
    log_callback("Generating visualization plots...")
    step_start = time.time()

    perm_plot_file = os.path.join(output_dir, 'permutation_null_distribution.pdf')
    plot_permutation_null_distribution(
        null_distribution,
        cluster_threshold,
        all_clusters,
        perm_plot_file,
        alpha=CONFIG['alpha'],
        cluster_stat=CONFIG['cluster_stat']
    )

    # Plot cluster size vs mass correlation
    correlation_plot_file = os.path.join(output_dir, 'cluster_size_mass_correlation.pdf')
    plot_cluster_size_mass_correlation(
        correlation_data['sizes'],
        correlation_data['masses'],
        correlation_plot_file
    )

    logger.info(f"Step completed in {time.time() - step_start:.2f} seconds")

    # -------------------------------------------------------------------------
    # 6. GENERATE AVERAGE MAPS
    # -------------------------------------------------------------------------
    logger.info("\n[6/8] GENERATING AVERAGE INTENSITY MAPS")
    logger.info("-" * 70)
    log_callback("Generating average intensity maps...")
    step_start = time.time()

    # Average responders (compute in float32 to save memory)
    avg_responders = np.mean(responders, axis=-1).astype(np.float32)
    avg_resp_file = os.path.join(output_dir, 'average_responders.nii.gz')
    # Save NIfTI file
    os.makedirs(os.path.dirname(avg_resp_file) or ".", exist_ok=True)
    img = nib.Nifti1Image(avg_responders, template_img.affine, template_img.header)
    nib.save(img, avg_resp_file)
    logger.info(f"Saved: average_responders.nii.gz")

    # Average non-responders (compute in float32 to save memory)
    avg_non_responders = np.mean(non_responders, axis=-1).astype(np.float32)
    avg_non_resp_file = os.path.join(output_dir, 'average_non_responders.nii.gz')
    # Save NIfTI file
    os.makedirs(os.path.dirname(avg_non_resp_file) or ".", exist_ok=True)
    img = nib.Nifti1Image(avg_non_responders, template_img.affine, template_img.header)
    nib.save(img, avg_non_resp_file)
    logger.info(f"Saved: average_non_responders.nii.gz")

    # Difference map
    diff_map = (avg_responders - avg_non_responders).astype(np.float32)
    diff_file = os.path.join(output_dir, 'difference_map.nii.gz')
    # Save NIfTI file
    os.makedirs(os.path.dirname(diff_file) or ".", exist_ok=True)
    img = nib.Nifti1Image(diff_map, template_img.affine, template_img.header)
    nib.save(img, diff_file)
    logger.info(f"Saved: difference_map.nii.gz")

    logger.info(f"Mean difference in brain: {np.mean(diff_map[valid_mask]):.4f}")
    logger.info(f"Max absolute difference: {np.max(np.abs(diff_map[valid_mask])):.4f}")
    logger.info(f"Step completed in {time.time() - step_start:.2f} seconds")

    # -------------------------------------------------------------------------
    # 7. ATLAS OVERLAP ANALYSIS
    # -------------------------------------------------------------------------
    logger.info("\n[7/8] PERFORMING ATLAS OVERLAP ANALYSIS")
    logger.info("-" * 70)
    log_callback("Performing atlas overlap analysis...")
    step_start = time.time()

    # Only run atlas analysis if atlas files are configured
    atlas_results = {}
    if CONFIG.get('atlas_files') and len(CONFIG['atlas_files']) > 0:
        # Get TI-Toolbox resources directory for atlases
        ti_toolbox_root = Path(__file__).parent.parent.parent
        atlas_dir = ti_toolbox_root / 'resources' / 'atlas'

        if atlas_dir.exists():
            atlas_results = atlas_overlap_analysis(
                sig_mask,
                CONFIG['atlas_files'],
                str(atlas_dir),
                reference_img=template_img
            )
        else:
            logger.info("Atlas directory not found, skipping atlas analysis")
    else:
        logger.info("No atlas files configured, skipping atlas analysis")

    for atlas_name, regions in atlas_results.items():
        if regions:
            logger.info(f"{atlas_name}: {len(regions)} regions with overlap")
    logger.info(f"Step completed in {time.time() - step_start:.2f} seconds")

    # -------------------------------------------------------------------------
    # 8. SAVE OUTPUTS
    # -------------------------------------------------------------------------
    logger.info("\n[8/8] SAVING RESULTS")
    logger.info("-" * 70)
    log_callback("Saving final results...")
    step_start = time.time()

    # Binary mask
    output_mask = os.path.join(output_dir, 'significant_voxels_mask.nii.gz')
    # Save NIfTI file
    os.makedirs(os.path.dirname(output_mask) or ".", exist_ok=True)
    img = nib.Nifti1Image(sig_mask.astype(np.uint8), template_img.affine, template_img.header)
    nib.save(img, output_mask)
    logger.info(f"Saved: significant_voxels_mask.nii.gz")

    # P-values map (as -log10 for visualization)
    log_p = -np.log10(p_values + 1e-10)
    log_p[~valid_mask] = 0
    output_pvalues = os.path.join(output_dir, 'pvalues_map.nii.gz')
    # Save NIfTI file
    os.makedirs(os.path.dirname(output_pvalues) or ".", exist_ok=True)
    img = nib.Nifti1Image(log_p, template_img.affine, template_img.header)
    nib.save(img, output_pvalues)
    logger.info(f"Saved: pvalues_map.nii.gz")

    # Summary report
    output_summary = os.path.join(output_dir, 'analysis_summary.txt')

    # Prepare parameters dictionary for summary
    summary_params = {
        'cluster_threshold': CONFIG['cluster_threshold'],
        'cluster_stat': CONFIG['cluster_stat'],
        'n_permutations': CONFIG['n_permutations'],
        'alpha': CONFIG['alpha'],
        'n_jobs': CONFIG['n_jobs']
    }

    generate_summary(
        responders,
        non_responders,
        sig_mask,
        cluster_threshold,
        clusters,
        atlas_results,
        output_summary,
        correction_method="cluster",
        params=summary_params,
        group1_name=CONFIG['group1_name'],
        group2_name=CONFIG['group2_name'],
        value_metric=CONFIG['value_metric'],
        test_type=CONFIG['test_type'],
        observed_cluster_sizes=observed_cluster_sizes if n_observed_clusters > 0 else None
    )
    logger.info(f"Saved: analysis_summary.txt")
    logger.info(f"Step completed in {time.time() - step_start:.2f} seconds")

    # -------------------------------------------------------------------------
    # COMPLETE
    # -------------------------------------------------------------------------
    total_time = time.time() - analysis_start_time
    hours, remainder = divmod(total_time, 3600)
    minutes, seconds = divmod(remainder, 60)

    logger.info("\n" + "="*70)
    logger.info("ANALYSIS COMPLETE!")
    logger.info("="*70)
    logger.info(f"Total analysis time: {int(hours)}h {int(minutes)}m {seconds:.1f}s")
    logger.info(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")
    logger.info("OUTPUT FILES:")
    logger.info(f"  1. Binary mask: {output_mask}")
    logger.info(f"  2. P-values map (-log10): {output_pvalues}")
    logger.info(f"  3. Summary report: {output_summary}")
    logger.info(f"  4. Average {CONFIG['group1_name']}: {avg_resp_file}")
    logger.info(f"  5. Average {CONFIG['group2_name']}: {avg_non_resp_file}")
    logger.info(f"  6. Difference map: {diff_file}")
    logger.info(f"  7. Permutation null distribution plot: {perm_plot_file}")
    logger.info(f"  8. Cluster size-mass correlation plot: {correlation_plot_file}")
    logger.info(f"  9. Permutation details log: {permutation_log_file}")
    logger.info(f"  10. Log file: {log_file}")
    logger.info("")

    log_callback("Analysis complete!")

    # Clean up large arrays to free memory
    del responders
    del non_responders
    del p_values
    del t_statistics
    del avg_responders
    del avg_non_responders
    del diff_map
    del null_distribution
    del correlation_data
    gc.collect()

    # Close log handlers
    for handler in logger.handlers:
        handler.close()
        logger.removeHandler(handler)

    # Return results
    return {
        'output_dir': output_dir,
        'sig_mask': sig_mask,
        'clusters': clusters,
        'log_file': log_file,
        'n_responders': len(resp_ids),
        'n_non_responders': len(non_resp_ids),
        'n_significant_voxels': np.sum(sig_mask),
        'n_significant_clusters': len(sig_clusters),
        'cluster_threshold': cluster_threshold,
        'analysis_time': total_time
    }


def _run_correlation_analysis(subject_configs, CONFIG, output_dir, logger, log_callback,
                              analysis_start_time, log_file, stop_callback):
    """Run correlation analysis workflow"""

    # -------------------------------------------------------------------------
    # 1. LOAD DATA
    # -------------------------------------------------------------------------
    logger.info("\n[1/7] LOADING SUBJECT DATA")
    logger.info("-" * 70)
    log_callback("Loading subject data...")
    step_start = time.time()

    subject_data, effect_sizes, weights, template_img, subject_ids = load_subject_data(
        subject_configs,
        nifti_file_pattern=CONFIG['nifti_file_pattern'],
        analysis_type='correlation'
    )

    # Handle weights based on config
    if not CONFIG['use_weights']:
        weights = None

    n_subjects = len(subject_ids)
    logger.info(f"Loaded {n_subjects} subjects")
    logger.info(f"Subject IDs: {subject_ids}")
    logger.info(f"Effect sizes: {effect_sizes}")
    if weights is not None:
        logger.info(f"Weights: {weights}")
    logger.info(f"Image shape: {subject_data.shape[:3]}")

    # Data diagnostics
    data_mean = np.mean(subject_data[subject_data > 0]) if np.any(subject_data > 0) else 0
    data_max = np.max(subject_data)
    logger.info(f"\nDATA DIAGNOSTICS:")
    logger.info(f"  E-field mean (non-zero): {data_mean:.6f}")
    logger.info(f"  E-field max: {data_max:.6f}")
    logger.info(f"  Effect size mean: {np.mean(effect_sizes):.4f}")
    logger.info(f"  Effect size std: {np.std(effect_sizes):.4f}")

    logger.info(f"\nStep completed in {time.time() - step_start:.2f} seconds")

    if stop_callback and stop_callback():
        raise KeyboardInterrupt("Analysis stopped by user")

    # -------------------------------------------------------------------------
    # 2. VOXELWISE CORRELATION
    # -------------------------------------------------------------------------
    logger.info("\n[2/7] COMPUTING VOXELWISE CORRELATIONS")
    logger.info("-" * 70)
    log_callback("Computing voxelwise correlations...")
    step_start = time.time()

    r_values, t_statistics, p_values, valid_mask = correlation_voxelwise(
        subject_data,
        effect_sizes,
        weights=weights,
        correlation_type=CONFIG['correlation_type'],
        verbose=True
    )

    n_valid = np.sum(valid_mask)
    logger.info(f"Computed correlations for {n_valid} valid voxels")
    logger.info(f"Correlation range: [{np.min(r_values[valid_mask]):.4f}, {np.max(r_values[valid_mask]):.4f}]")
    logger.info(f"Mean |r|: {np.mean(np.abs(r_values[valid_mask])):.4f}")
    logger.info(f"Max positive r: {np.max(r_values[valid_mask]):.4f}")
    logger.info(f"Max negative r: {np.min(r_values[valid_mask]):.4f}")

    # Count significant voxels at different thresholds
    logger.info(f"\nUncorrected significant voxels:")
    logger.info(f"  p < 0.01: {np.sum((p_values < 0.01) & valid_mask)}")
    logger.info(f"  p < 0.05: {np.sum((p_values < 0.05) & valid_mask)}")
    logger.info(f"  p < 0.10: {np.sum((p_values < 0.10) & valid_mask)}")

    logger.info(f"\nStep completed in {time.time() - step_start:.2f} seconds")

    # Log observed clusters before permutation correction (vectorized for speed)
    from scipy.ndimage import label as scipy_label, sum as ndimage_sum
    observed_mask = (p_values < CONFIG['cluster_threshold']) & valid_mask
    observed_labeled, n_observed_clusters = scipy_label(observed_mask)

    logger.info(f"\nObserved clusters at p < {CONFIG['cluster_threshold']} (before permutation correction):")
    logger.info(f"Total clusters found: {n_observed_clusters}")

    if n_observed_clusters > 0:
        # Vectorized cluster size computation using bincount
        cluster_labels_flat = observed_labeled.ravel()
        observed_cluster_sizes = np.bincount(cluster_labels_flat, minlength=n_observed_clusters + 1)[1:]

        # Vectorized cluster mass computation using ndimage.sum
        cluster_indices = list(range(1, n_observed_clusters + 1))
        observed_cluster_masses = ndimage_sum(t_statistics, observed_labeled, cluster_indices)
        observed_cluster_masses = np.array(observed_cluster_masses)

        # Sort by cluster statistic
        if CONFIG['cluster_stat'] == 'size':
            sort_idx = np.argsort(observed_cluster_sizes)[::-1]
        else:
            sort_idx = np.argsort(observed_cluster_masses)[::-1]

        observed_cluster_sizes_sorted = observed_cluster_sizes[sort_idx]
        observed_cluster_masses_sorted = observed_cluster_masses[sort_idx]

        logger.info(f"\nTop 10 largest observed clusters (before permutation correction):")
        for i in range(min(10, len(observed_cluster_sizes_sorted))):
            if CONFIG['cluster_stat'] == 'size':
                logger.info(f"  Cluster {i+1:2d}: {observed_cluster_sizes_sorted[i]:6d} voxels, mass={observed_cluster_masses_sorted[i]:.2f}")
            else:
                logger.info(f"  Cluster {i+1:2d}: mass={observed_cluster_masses_sorted[i]:.2f}, {observed_cluster_sizes_sorted[i]:6d} voxels")

        if CONFIG['cluster_stat'] == 'size':
            logger.info(f"\nLargest observed cluster: {observed_cluster_sizes_sorted[0]} voxels")
        else:
            logger.info(f"\nLargest observed cluster mass: {observed_cluster_masses_sorted[0]:.2f}")
        logger.info(f"Total voxels in all clusters: {np.sum(observed_cluster_sizes)}")

    if stop_callback and stop_callback():
        raise KeyboardInterrupt("Analysis stopped by user")

    # -------------------------------------------------------------------------
    # 3. CLUSTER-BASED PERMUTATION CORRECTION
    # -------------------------------------------------------------------------
    logger.info("\n[3/7] APPLYING CLUSTER-BASED PERMUTATION CORRECTION")
    logger.info("-" * 70)
    log_callback(f"Running permutation testing ({CONFIG['n_permutations']} permutations)...")
    step_start = time.time()

    permutation_log_file = os.path.join(output_dir, 'permutation_details.txt')

    sig_mask, cluster_threshold, sig_clusters, null_distribution, all_clusters, correlation_data = \
        correlation_cluster_correction(
            subject_data,
            effect_sizes,
            r_values,
            t_statistics,
            p_values,
            valid_mask,
            weights=weights,
            correlation_type=CONFIG['correlation_type'],
            cluster_threshold=CONFIG['cluster_threshold'],
            n_permutations=CONFIG['n_permutations'],
            alpha=CONFIG['alpha'],
            cluster_stat=CONFIG['cluster_stat'],
            alternative=CONFIG.get('alternative', 'two-sided'),  # Default to two-sided if not specified
            n_jobs=CONFIG['n_jobs'],
            logger=logger,
            save_permutation_log=True,
            permutation_log_file=permutation_log_file,
            subject_ids=subject_ids
        )

    if CONFIG['cluster_stat'] == 'size':
        logger.info(f"Cluster size threshold: {cluster_threshold:.1f} voxels")
    else:
        logger.info(f"Cluster mass threshold: {cluster_threshold:.2f}")
    logger.info(f"Significant clusters found: {len(sig_clusters)}")
    logger.info(f"Total significant voxels: {np.sum(sig_mask)}")
    logger.info(f"Step completed in {time.time() - step_start:.2f} seconds")

    # -------------------------------------------------------------------------
    # 4. CLUSTER ANALYSIS
    # -------------------------------------------------------------------------
    logger.info("\n[4/7] ANALYZING SIGNIFICANT CLUSTERS")
    logger.info("-" * 70)
    log_callback(f"Analyzing {len(sig_clusters)} significant clusters...")
    step_start = time.time()

    clusters = cluster_analysis(sig_mask, template_img.affine)

    # Add correlation info to clusters
    for cluster in clusters:
        cluster_mask = sig_mask == 1  # Binary mask
        from scipy.ndimage import label as scipy_label
        labeled, _ = scipy_label(sig_mask)
        for i, c in enumerate(clusters):
            c_mask = labeled == c['cluster_id']
            c['mean_r'] = np.mean(r_values[c_mask])
            c['peak_r'] = np.max(r_values[c_mask])
            c['mean_t'] = np.mean(t_statistics[c_mask])

    if clusters:
        logger.info(f"Largest cluster: {clusters[0]['size']} voxels")
        logger.info(f"  Mean r: {clusters[0].get('mean_r', 'N/A'):.4f}")
        logger.info(f"  Peak r: {clusters[0].get('peak_r', 'N/A'):.4f}")
        logger.info(f"  MNI center: ({clusters[0]['center_mni'][0]:.1f}, "
                   f"{clusters[0]['center_mni'][1]:.1f}, {clusters[0]['center_mni'][2]:.1f})")
    logger.info(f"Step completed in {time.time() - step_start:.2f} seconds")

    # -------------------------------------------------------------------------
    # 5. GENERATE PLOTS
    # -------------------------------------------------------------------------
    logger.info("\n[5/7] GENERATING VISUALIZATION PLOTS")
    logger.info("-" * 70)
    log_callback("Generating visualization plots...")
    step_start = time.time()

    # Permutation null distribution
    perm_plot_file = os.path.join(output_dir, 'permutation_null_distribution.pdf')
    plot_permutation_null_distribution(
        null_distribution,
        cluster_threshold,
        all_clusters,
        perm_plot_file,
        alpha=CONFIG['alpha'],
        cluster_stat=CONFIG['cluster_stat']
    )

    # Cluster size vs mass correlation
    if len(correlation_data['sizes']) > 0:
        correlation_plot_file = os.path.join(output_dir, 'cluster_size_mass_correlation.pdf')
        plot_cluster_size_mass_correlation(
            correlation_data['sizes'],
            correlation_data['masses'],
            correlation_plot_file
        )

    logger.info(f"Step completed in {time.time() - step_start:.2f} seconds")

    # -------------------------------------------------------------------------
    # 6. ATLAS OVERLAP ANALYSIS
    # -------------------------------------------------------------------------
    logger.info("\n[6/7] PERFORMING ATLAS OVERLAP ANALYSIS")
    logger.info("-" * 70)
    log_callback("Performing atlas overlap analysis...")
    step_start = time.time()

    atlas_results = {}
    if CONFIG.get('atlas_files') and len(CONFIG['atlas_files']) > 0:
        ti_toolbox_root = Path(__file__).parent.parent.parent
        atlas_dir = ti_toolbox_root / 'resources' / 'atlas'

        if atlas_dir.exists():
            atlas_results = atlas_overlap_analysis(
                sig_mask,
                CONFIG['atlas_files'],
                str(atlas_dir),
                reference_img=template_img
            )
        else:
            logger.info("Atlas directory not found, skipping atlas analysis")
    else:
        logger.info("No atlas files configured, skipping atlas analysis")

    for atlas_name, regions in atlas_results.items():
        if regions:
            logger.info(f"{atlas_name}: {len(regions)} regions with overlap")
    logger.info(f"Step completed in {time.time() - step_start:.2f} seconds")

    # -------------------------------------------------------------------------
    # 7. SAVE OUTPUTS
    # -------------------------------------------------------------------------
    logger.info("\n[7/7] SAVING RESULTS")
    logger.info("-" * 70)
    log_callback("Saving final results...")
    step_start = time.time()

    # Significant voxels mask
    output_mask = os.path.join(output_dir, 'significant_voxels_mask.nii.gz')
    img = nib.Nifti1Image(sig_mask.astype(np.uint8), template_img.affine, template_img.header)
    nib.save(img, output_mask)
    logger.info(f"Saved: significant_voxels_mask.nii.gz")

    # Correlation map
    output_r = os.path.join(output_dir, 'correlation_map.nii.gz')
    img = nib.Nifti1Image(r_values.astype(np.float32), template_img.affine, template_img.header)
    nib.save(img, output_r)
    logger.info(f"Saved: correlation_map.nii.gz")

    # T-statistics map
    output_t = os.path.join(output_dir, 't_statistics_map.nii.gz')
    img = nib.Nifti1Image(t_statistics.astype(np.float32), template_img.affine, template_img.header)
    nib.save(img, output_t)
    logger.info(f"Saved: t_statistics_map.nii.gz")

    # P-values map (as -log10 for visualization)
    log_p = -np.log10(p_values + 1e-10)
    log_p[~valid_mask] = 0
    output_pvalues = os.path.join(output_dir, 'pvalues_map.nii.gz')
    img = nib.Nifti1Image(log_p, template_img.affine, template_img.header)
    nib.save(img, output_pvalues)
    logger.info(f"Saved: pvalues_map.nii.gz")

    # Thresholded correlation map (only significant voxels)
    r_thresholded = r_values.copy()
    r_thresholded[sig_mask == 0] = 0
    output_r_thresh = os.path.join(output_dir, 'correlation_map_thresholded.nii.gz')
    img = nib.Nifti1Image(r_thresholded.astype(np.float32), template_img.affine, template_img.header)
    nib.save(img, output_r_thresh)
    logger.info(f"Saved: correlation_map_thresholded.nii.gz")

    # Average E-field map
    avg_efield = np.mean(subject_data, axis=-1).astype(np.float32)
    avg_efield_file = os.path.join(output_dir, 'average_efield.nii.gz')
    img = nib.Nifti1Image(avg_efield, template_img.affine, template_img.header)
    nib.save(img, avg_efield_file)
    logger.info(f"Saved: average_efield.nii.gz")

    # Summary report
    output_summary = os.path.join(output_dir, 'analysis_summary.txt')
    summary_params = {
        'correlation_type': CONFIG['correlation_type'],
        'cluster_threshold': CONFIG['cluster_threshold'],
        'cluster_stat': CONFIG['cluster_stat'],
        'n_permutations': CONFIG['n_permutations'],
        'alpha': CONFIG['alpha'],
        'use_weights': weights is not None
    }

    generate_correlation_summary(
        subject_data,
        effect_sizes,
        r_values,
        sig_mask,
        cluster_threshold,
        clusters,
        atlas_results,
        output_summary,
        params=summary_params,
        effect_metric=CONFIG['effect_metric'],
        subject_ids=subject_ids,
        weights=weights
    )
    logger.info(f"Saved: analysis_summary.txt")
    logger.info(f"Step completed in {time.time() - step_start:.2f} seconds")

    # -------------------------------------------------------------------------
    # COMPLETE
    # -------------------------------------------------------------------------
    total_time = time.time() - analysis_start_time
    hours, remainder = divmod(total_time, 3600)
    minutes, seconds = divmod(remainder, 60)

    logger.info("\n" + "="*70)
    logger.info("ANALYSIS COMPLETE!")
    logger.info("="*70)
    logger.info(f"Total analysis time: {int(hours)}h {int(minutes)}m {seconds:.1f}s")
    logger.info(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")
    logger.info("OUTPUT FILES:")
    logger.info(f"  1. Significant voxels mask: {output_mask}")
    logger.info(f"  2. Correlation map (r values): {output_r}")
    logger.info(f"  3. Thresholded correlation map: {output_r_thresh}")
    logger.info(f"  4. T-statistics map: {output_t}")
    logger.info(f"  5. P-values map (-log10): {output_pvalues}")
    logger.info(f"  6. Average E-field: {avg_efield_file}")
    logger.info(f"  7. Analysis summary: {output_summary}")
    logger.info(f"  8. Permutation plot: {perm_plot_file}")
    logger.info(f"  9. Log file: {log_file}")
    logger.info("")
    logger.info("INTERPRETATION:")
    logger.info("  - Positive correlations indicate regions where higher E-field")
    logger.info(f"    magnitude is associated with higher {CONFIG['effect_metric']}")
    logger.info("  - To find negative correlations, invert your effect size values")
    logger.info("    and re-run the analysis")
    logger.info("")

    log_callback("Analysis complete!")

    # Clean up large arrays to free memory (keep returned variables)
    del subject_data
    del effect_sizes
    del weights
    del t_statistics
    del p_values
    del valid_mask
    gc.collect()

    for handler in logger.handlers:
        handler.close()
        logger.removeHandler(handler)

    return {
        'output_dir': output_dir,
        'sig_mask': sig_mask,
        'r_values': r_values,
        'clusters': clusters,
        'log_file': log_file,
        'n_subjects': n_subjects,
        'n_significant_voxels': np.sum(sig_mask),
        'n_significant_clusters': len(sig_clusters),
        'cluster_threshold': cluster_threshold,
        'analysis_time': total_time
    }


# Placeholder for the rest of the implementation
# The full implementation would continue with the remaining steps for both analysis types

def main():
    """
    Command-line interface for unified permutation analysis
    """
    import argparse
    import multiprocessing

    # Ensure proper multiprocessing initialization
    if hasattr(multiprocessing, 'set_start_method'):
        try:
            multiprocessing.set_start_method('fork', force=True)
        except RuntimeError:
            pass

    parser = argparse.ArgumentParser(
        description='Unified Cluster-Based Permutation Testing for TI-Toolbox',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Group comparison analysis
  python permutation_analysis.py --csv subjects.csv --name my_analysis \\
      --analysis-type group_comparison

  # Correlation analysis
  python permutation_analysis.py --csv subjects.csv --name my_analysis \\
      --analysis-type correlation

Group Comparison CSV Format:
  subject_id,simulation_name,response
  070,ICP_RHIPPO,1
  071,ICP_RHIPPO,0

Correlation CSV Format:
  subject_id,simulation_name,effect_size,weight
  070,ICP_RHIPPO,0.45,25
  071,ICP_RHIPPO,0.32,30

Tissue Types:
  --tissue-type controls which NIfTI files are loaded:
    grey  : grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz
    white : white_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz
    all   : {simulation_name}_TI_MNI_MNI_TI_max.nii.gz (no prefix)
        """
    )

    # Required arguments
    parser.add_argument('--csv', '-c', required=True,
                        help='Path to CSV file with subject configurations')
    parser.add_argument('--name', '-n', required=True,
                        help='Analysis name (used for output directory)')
    parser.add_argument('--analysis-type', required=True,
                        choices=['group_comparison', 'correlation'],
                        help='Type of analysis to perform')

    # Statistical parameters (common)
    parser.add_argument('--cluster-threshold', '-t', type=float, default=0.05,
                        help='P-value threshold for cluster formation (default: 0.05)')
    parser.add_argument('--cluster-stat', choices=['mass', 'size'], default='mass',
                        help='Cluster statistic: mass (sum of t-values) or size (voxel count) (default: mass)')
    parser.add_argument('--n-permutations', '-p', type=int, default=1000,
                        help='Number of permutations (default: 1000)')
    parser.add_argument('--alpha', '-a', type=float, default=0.05,
                        help='Cluster-level significance threshold (default: 0.05)')
    parser.add_argument('--n-jobs', '-j', type=int, default=-1,
                        help='Number of parallel jobs: -1=all cores, 1=sequential (default: -1)')

    # Group comparison specific parameters
    parser.add_argument('--test-type', choices=['unpaired', 'paired'], default='unpaired',
                        help='Statistical test type for group comparison (default: unpaired)')
    parser.add_argument('--alternative', choices=['two-sided', 'greater', 'less'],
                        default='two-sided',
                        help='Alternative hypothesis for group comparison (default: two-sided)')

    # Correlation specific parameters
    parser.add_argument('--correlation-type', choices=['pearson', 'spearman'],
                        default='pearson',
                        help='Type of correlation for correlation analysis (default: pearson)')
    parser.add_argument('--use-weights', action='store_true',
                        help='Use weights from CSV if available (correlation analysis)')

    # Optional parameters
    parser.add_argument('--tissue-type', choices=['grey', 'white', 'all'],
                        default='grey',
                        help='Tissue type for NIfTI files: grey (grey matter), '
                             'white (white matter), or all (all tissues, no prefix). '
                             '(default: grey)')
    parser.add_argument('--nifti-pattern', default=None,
                        help='Custom NIfTI filename pattern (overrides --tissue-type)')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Suppress progress output')

    args = parser.parse_args()

    # Build configuration
    config = {
        'analysis_type': args.analysis_type,
        'cluster_threshold': args.cluster_threshold,
        'cluster_stat': args.cluster_stat,
        'n_permutations': args.n_permutations,
        'alpha': args.alpha,
        'n_jobs': args.n_jobs,
        'tissue_type': args.tissue_type,
        'nifti_file_pattern': args.nifti_pattern,  # None triggers auto-generation
    }

    # Add analysis-specific parameters
    if args.analysis_type == 'group_comparison':
        config.update({
            'test_type': args.test_type,
            'alternative': args.alternative,
        })
    else:  # correlation
        config.update({
            'correlation_type': args.correlation_type,
            'use_weights': args.use_weights,
        })

    # Print header
    if not args.quiet:
        print("="*70)
        print("UNIFIED CLUSTER-BASED PERMUTATION TESTING - TI-TOOLBOX")
        print("="*70)
        print(f"Analysis type: {args.analysis_type}")
        print(f"CSV file: {args.csv}")
        print(f"Analysis name: {args.name}")
        print(f"Tissue type: {args.tissue_type}")
        print(f"Permutations: {args.n_permutations}")
        print(f"Parallel jobs: {args.n_jobs if args.n_jobs != -1 else 'all cores'}")
        print(f"Cluster statistic: {args.cluster_stat}")
        print(f"Cluster threshold: p < {args.cluster_threshold}")
        print("="*70)
        print()

    # Run analysis
    try:
        results = run_analysis(
            subject_configs=args.csv,
            analysis_name=args.name,
            config=config,
            output_callback=None if args.quiet else print
        )

        # Print summary
        if not args.quiet:
            print()
            print("="*70)
            print("ANALYSIS COMPLETE!")
            print("="*70)
            print(f"Output directory: {results['output_dir']}")
            if 'n_significant_clusters' in results:
                print(f"Significant clusters: {results['n_significant_clusters']}")
            if 'n_significant_voxels' in results:
                print(f"Significant voxels: {results['n_significant_voxels']}")
            print(f"Analysis time: {results['analysis_time']:.1f} seconds")
            print("="*70)

        return 0

    except Exception as e:
        print(f"\nERROR: {str(e)}", file=sys.stderr)
        if not args.quiet:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
