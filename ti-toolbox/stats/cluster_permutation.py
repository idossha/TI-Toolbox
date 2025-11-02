#!/usr/bin/env simnibs_python
"""

Cluster-based permutation testing for TI-Toolbox

This script performs non-parametric voxelwise statistical analysis to identify
brain regions with significantly different current intensity between responders
and non-responders using cluster-based permutation correction.

Integrated with TI-Toolbox BIDS structure.

Usage:
    from ti_toolbox.stats import cluster_permutation
    cluster_permutation.run_analysis(config)

For GUI usage, see gui/extentions/cbp.py
"""

import os
import sys
import numpy as np
import warnings
warnings.filterwarnings('ignore')
import logging
from datetime import datetime
import time
from pathlib import Path

# Import from modular utilities (relative imports for stats module)
import gc
try:
    from .stats_utils import ttest_voxelwise, cluster_based_correction, cluster_analysis
    from .atlas_utils import atlas_overlap_analysis
    from .visualization import plot_permutation_null_distribution, plot_cluster_size_mass_correlation
    from .reporting import generate_summary
except ImportError:
    # Fallback for direct execution
    from stats_utils import ttest_voxelwise, cluster_based_correction, cluster_analysis
    from atlas_utils import atlas_overlap_analysis
    from visualization import plot_permutation_null_distribution, plot_cluster_size_mass_correlation
    from reporting import generate_summary

# Import TI-Toolbox core modules
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from core import get_path_manager
    from core import constants as const
    from core import nifti
except ImportError:
    print("Warning: Could not import TI-Toolbox core modules. Some features may not work.")
    get_path_manager = None
    const = None
    nifti = None

import nibabel as nib
import pandas as pd


# ==============================================================================
# TI-TOOLBOX INTEGRATED DATA LOADING
# ==============================================================================

def load_subject_data_ti_toolbox(subject_configs, nifti_file_pattern=None):
    """
    Load subject data from TI-Toolbox BIDS structure
    
    Parameters:
    -----------
    subject_configs : list of dict
        List of subject configurations with keys:
        - 'subject_id': Subject ID (e.g., '070')
        - 'simulation_name': Simulation name (e.g., 'ICP_RHIPPO')
        - 'response': Response classification (1 for responder, 0 for non-responder)
    nifti_file_pattern : str, optional
        Pattern for NIfTI files. Default: 'grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz'
        Available variables: {subject_id}, {simulation_name}
    
    Returns:
    --------
    responders : ndarray (x, y, z, n_subjects)
        4D array of responder data
    non_responders : ndarray (x, y, z, n_subjects)
        4D array of non-responder data
    template_img : nibabel image
        Template image for affine/header information
    responder_ids : list
        List of responder subject IDs
    non_responder_ids : list
        List of non-responder subject IDs
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


def prepare_config_from_csv(csv_file):
    """
    Load subject configurations from CSV file
    
    Parameters:
    -----------
    csv_file : str
        Path to CSV file with columns: subject_id, simulation_name, response
        
    Returns:
    --------
    list of dict : Subject configurations
    """
    df = pd.read_csv(csv_file)
    
    configs = []
    for _, row in df.iterrows():
        # Handle both 'sub-XXX' and 'XXX' formats
        subject_id = str(row['subject_id']).replace('sub-', '')
        
        configs.append({
            'subject_id': subject_id,
            'simulation_name': row['simulation_name'],
            'response': int(row['response'])
        })
    
    return configs


# ==============================================================================
# CONFIGURATION
# ==============================================================================

DEFAULT_CONFIG = {
    # Statistical parameters
    'test_type': 'unpaired',        # 'paired' or 'unpaired' t-test
    'alternative': 'two-sided',       # 'two-sided', 'greater' (resp > non-resp), or 'less'
    'cluster_threshold': 0.05,      # p < 0.05 for cluster formation
    'cluster_stat': 'mass',         # 'size' (voxel count) or 'mass' (sum of t-values)
    'n_permutations': 1000,         # Number of permutations
    'alpha': 0.05,                  # Cluster-level significance
    'n_jobs': -1,                   # Number of parallel jobs (-1 = all cores, 1 = sequential)
    
    # Group and metric labels (customize for your study)
    'group1_name': 'Responders',
    'group2_name': 'Non-Responders',
    'value_metric': 'Current Intensity',
    
    # File pattern for NIfTI files
    'nifti_file_pattern': 'grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz',
    
    # Atlas files (optional, relative to TI-toolbox/resources/atlas/)
    'atlas_files': []  # Can add atlas files if available
}


# ==============================================================================
# LOGGING SETUP
# ==============================================================================

def setup_logging(output_dir):
    """
    Set up logging to both file and console
    
    Parameters:
    -----------
    output_dir : str
        Directory where log file will be saved
    
    Returns:
    --------
    logger : logging.Logger
        Configured logger instance
    log_file : str
        Path to log file
    """
    # Create timestamp for log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(output_dir, f"analysis_{timestamp}.log")
    
    # Create logger
    logger = logging.getLogger('VoxelwiseAnalysis')
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    logger.handlers = []
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter('%(message)s')
    
    # File handler (detailed)
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)
    
    # Console handler (simple)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    return logger, log_file


# ==============================================================================
# MAIN WORKFLOW
# ==============================================================================

def run_analysis(subject_configs, analysis_name, config=None, output_callback=None):
    """
    Run cluster-based permutation analysis
    
    Parameters:
    -----------
    subject_configs : list of dict or str
        Either a list of subject configurations or path to CSV file
        Each config should have: subject_id, simulation_name, response
    analysis_name : str
        Name for this analysis (used for output directory)
    config : dict, optional
        Configuration dictionary (merged with DEFAULT_CONFIG)
    output_callback : callable, optional
        Callback function for status updates (for GUI integration)
        
    Returns:
    --------
    dict : Results dictionary with keys:
        - 'output_dir': Path to output directory
        - 'sig_mask': Significant voxels mask
        - 'clusters': List of cluster information
        - 'log_file': Path to log file
    """
    # Merge config with defaults
    CONFIG = DEFAULT_CONFIG.copy()
    if config:
        CONFIG.update(config)
    
    # Callback helper
    def log_callback(msg):
        if output_callback:
            output_callback(msg)
    
    # Start timing
    analysis_start_time = time.time()
    
    # Set up output directory in TI-Toolbox BIDS structure
    pm = get_path_manager() if get_path_manager else None
    if pm:
        project_dir = pm.get_project_dir()
        derivatives_dir = pm.get_derivatives_dir()
        output_dir = os.path.join(
            derivatives_dir,
            const.DIR_TI_TOOLBOX,
            'stats',
            analysis_name
        )
    else:
        # Fallback
        project_dir = os.environ.get('PROJECT_DIR', '/mnt')
        output_dir = os.path.join(
            project_dir,
            'derivatives',
            'ti-toolbox',
            'stats',
            analysis_name
        )
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Set up logging
    logger, log_file = setup_logging(output_dir)
    
    logger.info("="*70)
    logger.info("CLUSTER-BASED PERMUTATION TESTING - TI-TOOLBOX")
    logger.info("="*70)
    logger.info(f"Analysis started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Analysis name: {analysis_name}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Log file: {log_file}")
    logger.info("")
    log_callback(f"Starting analysis: {analysis_name}")
    
    # Log configuration
    logger.info("CONFIGURATION:")
    logger.info(f"  Statistical test: {CONFIG['test_type'].capitalize()} t-test")
    alt_text = {
        'two-sided': 'two-sided (≠)',
        'greater': f"one-sided ({CONFIG['group1_name']} > {CONFIG['group2_name']})",
        'less': f"one-sided ({CONFIG['group1_name']} < {CONFIG['group2_name']})"
    }
    logger.info(f"  Alternative hypothesis: {alt_text.get(CONFIG['alternative'], CONFIG['alternative'])}")
    cluster_stat_name = "Cluster Size" if CONFIG['cluster_stat'] == 'size' else "Cluster Mass"
    logger.info(f"  Cluster statistic: {cluster_stat_name}")
    logger.info(f"  Cluster threshold: {CONFIG['cluster_threshold']}")
    logger.info(f"  Number of permutations: {CONFIG['n_permutations']}")
    logger.info(f"  Alpha level: {CONFIG['alpha']}")
    logger.info(f"  Parallel jobs: {CONFIG['n_jobs']}")
    logger.info(f"  Group 1: {CONFIG['group1_name']}")
    logger.info(f"  Group 2: {CONFIG['group2_name']}")
    logger.info(f"  Metric: {CONFIG['value_metric']}")
    logger.info(f"  NIfTI pattern: {CONFIG['nifti_file_pattern']}")
    logger.info("")
    
    # Load subject configurations
    if isinstance(subject_configs, str):
        # CSV file path provided
        logger.info(f"Loading subject configurations from: {subject_configs}")
        subject_configs = prepare_config_from_csv(subject_configs)
    
    # -------------------------------------------------------------------------
    # 1. LOAD DATA
    # -------------------------------------------------------------------------
    logger.info("\n[1/8] LOADING SUBJECT DATA")
    logger.info("-" * 70)
    log_callback("Loading subject data...")
    step_start = time.time()
    
    responders, non_responders, template_img, resp_ids, non_resp_ids = load_subject_data_ti_toolbox(
        subject_configs,
        nifti_file_pattern=CONFIG['nifti_file_pattern']
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
    
    # Report memory usage
    try:
        import psutil
        process = psutil.Process()
        mem_info = process.memory_info()
        logger.info(f"  Memory usage: {mem_info.rss / (1024**3):.2f} GB")
    except:
        pass
    
    logger.info(f"\nStep completed in {time.time() - step_start:.2f} seconds")
    
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
    
    # Log observed clusters before permutation correction
    from scipy.ndimage import label as scipy_label
    observed_mask = (p_values < CONFIG['cluster_threshold']) & valid_mask
    observed_labeled, n_observed_clusters = scipy_label(observed_mask)
    
    logger.info(f"\nObserved clusters at p < {CONFIG['cluster_threshold']} (before permutation correction):")
    logger.info(f"Total clusters found: {n_observed_clusters}")
    
    if n_observed_clusters > 0:
        observed_cluster_sizes = []
        for cluster_id in range(1, n_observed_clusters + 1):
            size = np.sum(observed_labeled == cluster_id)
            observed_cluster_sizes.append(size)
        
        observed_cluster_sizes.sort(reverse=True)
        
        logger.info(f"\nTop 10 largest observed clusters (before permutation correction):")
        for i, size in enumerate(observed_cluster_sizes[:10], 1):
            logger.info(f"  Cluster {i:2d}: {size:6d} voxels")
        
        logger.info(f"\nLargest observed cluster: {observed_cluster_sizes[0]} voxels")
        logger.info(f"Total voxels in all clusters: {sum(observed_cluster_sizes)}")
    
    # -------------------------------------------------------------------------
    # 3. CLUSTER-BASED PERMUTATION CORRECTION
    # -------------------------------------------------------------------------
    logger.info("\n[3/8] APPLYING CLUSTER-BASED PERMUTATION CORRECTION")
    logger.info("-" * 70)
    log_callback(f"Running permutation testing ({CONFIG['n_permutations']} permutations)...")
    step_start = time.time()
    
    # Set up permutation log file path
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
    logger.info("NEXT STEPS:")
    logger.info("  - Visualize results in NIfTI Viewer tab")
    logger.info("  - Review analysis summary for detailed statistics")
    logger.info("  - Check permutation details for validation")
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


def main():
    """
    Command-line interface for cluster-based permutation testing
    """
    import argparse
    import multiprocessing
    
    # Ensure proper multiprocessing initialization
    if hasattr(multiprocessing, 'set_start_method'):
        try:
            multiprocessing.set_start_method('fork', force=True)
        except RuntimeError:
            pass  # Already set
    
    parser = argparse.ArgumentParser(
        description='Cluster-Based Permutation Testing for TI-Toolbox',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with CSV file
  python cluster_permutation.py --csv subjects.csv --name my_analysis
  
  # With custom parameters
  python cluster_permutation.py --csv subjects.csv --name my_analysis \\
      --n-permutations 1000 --n-jobs 4 --cluster-threshold 0.01
  
  # Using cluster mass instead of size
  python cluster_permutation.py --csv subjects.csv --name my_analysis \\
      --cluster-stat mass --n-permutations 500
  
  # One-sided test (responders > non-responders)
  python cluster_permutation.py --csv subjects.csv --name my_analysis \\
      --alternative greater

CSV Format:
  subject_id,simulation_name,response
  070,ICP_RHIPPO,1
  071,ICP_RHIPPO,0
  ...
  
  Where response: 1 = responder, 0 = non-responder
        """
    )
    
    # Required arguments
    parser.add_argument('--csv', '-c', required=True,
                        help='Path to CSV file with subject configurations')
    parser.add_argument('--name', '-n', required=True,
                        help='Analysis name (used for output directory)')
    
    # Statistical parameters
    parser.add_argument('--test-type', choices=['unpaired', 'paired'], default='unpaired',
                        help='Statistical test type (default: unpaired)')
    parser.add_argument('--alternative', choices=['two-sided', 'greater', 'less'], 
                        default='two-sided',
                        help='Alternative hypothesis (default: two-sided)')
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
    
    # Optional parameters
    parser.add_argument('--group1-name', default='Responders',
                        help='Name for group 1 in reports (default: Responders)')
    parser.add_argument('--group2-name', default='Non-Responders',
                        help='Name for group 2 in reports (default: Non-Responders)')
    parser.add_argument('--value-metric', default='Current Intensity',
                        help='Name of the measured metric (default: Current Intensity)')
    parser.add_argument('--nifti-pattern', 
                        default='grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz',
                        help='NIfTI filename pattern (default: grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz)')
    
    # Flags
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Suppress progress output')
    parser.add_argument('--save-perm-log', action='store_true',
                        help='Save detailed permutation log file')
    
    args = parser.parse_args()
    
    # Build configuration
    config = {
        'test_type': args.test_type,
        'alternative': args.alternative,
        'cluster_threshold': args.cluster_threshold,
        'cluster_stat': args.cluster_stat,
        'n_permutations': args.n_permutations,
        'alpha': args.alpha,
        'n_jobs': args.n_jobs,
        'group1_name': args.group1_name,
        'group2_name': args.group2_name,
        'value_metric': args.value_metric,
        'nifti_file_pattern': args.nifti_pattern,
    }
    
    # Print header
    if not args.quiet:
        print("="*70)
        print("CLUSTER-BASED PERMUTATION TESTING - TI-TOOLBOX")
        print("="*70)
        print(f"CSV file: {args.csv}")
        print(f"Analysis name: {args.name}")
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
            print(f"Significant clusters: {results['n_significant_clusters']}")
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

