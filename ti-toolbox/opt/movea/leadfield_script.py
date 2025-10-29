#!/usr/bin/env python3
"""
MOVEA Leadfield Generation Script
Runs as subprocess for instant termination support
"""

import os
import sys
import time
import logging
from pathlib import Path

# Add parent directories to path to access ti-toolbox modules
script_dir = os.path.dirname(os.path.abspath(__file__))
opt_dir = os.path.dirname(script_dir)  # opt/
toolbox_dir = os.path.dirname(opt_dir)  # ti-toolbox/
sys.path.insert(0, toolbox_dir)

from tools import logging_util
from core import get_path_manager

# Check arguments
if len(sys.argv) != 4:
    print("Usage: leadfield_script.py <m2m_dir> <eeg_cap_file> <project_dir>")
    sys.exit(1)

m2m_dir = sys.argv[1]
eeg_cap_file = sys.argv[2]  # Just the filename, e.g., "EEG10-10_Cutini_2011.csv"
project_dir = sys.argv[3]

# Initialize logger
log_file = os.environ.get('TI_LOG_FILE')
if not log_file:
    time_stamp = time.strftime('%Y%m%d_%H%M%S')
    subject_id = os.path.basename(m2m_dir).replace('m2m_', '')
    pm = get_path_manager()
    log_dir = pm.get_logs_dir(subject_id)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'MOVEA_leadfield_{time_stamp}.log')

# Use get_logger (not get_file_only_logger) so stdout goes to GUI subprocess capture
logger = logging_util.get_logger('MOVEA_Leadfield', log_file, overwrite=False)
logging_util.configure_external_loggers(['simnibs', 'mesh_io', 'sim_struct'], logger)

logger.info("="*60)
logger.info("MOVEA LEADFIELD GENERATION")
logger.info("="*60)
logger.info(f"M2M Directory: {m2m_dir}")
logger.info(f"EEG Cap File: {eeg_cap_file}")
logger.info(f"Project Directory: {project_dir}")

# Import MOVEA leadfield generator from opt.movea
try:
    from opt.movea import LeadfieldGenerator
except ImportError as e:
    logger.error(f"Failed to import MOVEA modules: {e}")
    sys.exit(1)

# Get paths
subject_id = os.path.basename(m2m_dir).replace('m2m_', '')
subject_derivatives = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}')
movea_leadfield_dir = os.path.join(subject_derivatives, 'MOVEA', 'leadfields')
os.makedirs(movea_leadfield_dir, exist_ok=True)

# Check if leadfield already exists
net_name = eeg_cap_file.replace('.csv', '')
lfm_filename = f"{net_name}_leadfield.npy"
pos_filename = f"{net_name}_positions.npy"
lfm_path = os.path.join(movea_leadfield_dir, lfm_filename)
pos_path = os.path.join(movea_leadfield_dir, pos_filename)

if os.path.exists(lfm_path) and os.path.exists(pos_path):
    logger.error(f"Leadfield already exists: {lfm_filename}")
    logger.error("Delete existing files first or choose a different EEG net")
    sys.exit(1)

# Progress callback to send to stdout (captured by GUI)
def progress_callback(message, msg_type='info'):
    if msg_type == 'error':
        logger.error(message)
    elif msg_type == 'warning':
        logger.warning(message)
    else:
        logger.info(message)

# Create leadfield generator
gen = LeadfieldGenerator(m2m_dir, progress_callback=progress_callback)

try:
    # Use the complete workflow method (handles everything: cleanup, generate, convert, save)
    lfm_path, pos_path, lfm_shape = gen.generate_and_save_numpy(
        output_dir=movea_leadfield_dir,
        eeg_cap_file=eeg_cap_file,
        cleanup_intermediate=True
    )
    
    logger.info("")
    logger.info("="*60)
    logger.info("LEADFIELD GENERATION COMPLETE!")
    logger.info("="*60)
    logger.info(f"Saved: {lfm_filename}")
    logger.info(f"Saved: {pos_filename}")
    logger.info(f"Electrodes: {lfm_shape[0]}")
    logger.info(f"Voxels: {lfm_shape[1]}")
    logger.info("="*60)
    
    # Print paths for GUI to capture
    print(f"LFM_PATH:{lfm_path}")
    print(f"POS_PATH:{pos_path}")
    
except Exception as e:
    import traceback
    logger.error(f"Leadfield generation failed: {str(e)}")
    logger.error(traceback.format_exc())
    sys.exit(1)

