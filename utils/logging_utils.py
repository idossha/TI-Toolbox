"""
Shared logging utilities for TI-CSC tools.

This module provides unified logging functionality that can be used across all tools
in the TI-CSC toolbox (simulator, analyzer, etc.). It provides consistent logging
behavior with configurable output locations and formats.

Example Usage:
    ```python
    from utils.logging_utils import setup_logging, get_logger
    
    # Setup logging for a tool
    logger = setup_logging(output_dir="/path/to/output", tool_name="analyzer")
    logger.info("Starting analysis...")
    logger.debug("Processing montage: %s", montage_name)
    ```
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional, Union
import argparse

# ANSI color codes for console output
BOLD = '\033[1m'
UNDERLINE = '\033[4m'
RESET = '\033[0m'
RED = '\033[0;31m'     # Red for errors
GREEN = '\033[0;32m'   # Green for success
CYAN = '\033[0;36m'    # Cyan for actions
YELLOW = '\033[0;33m'  # Yellow for warnings

class ColoredFormatter(logging.Formatter):
    """Custom formatter for colored console output."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[0;36m',    # Cyan
        'INFO': '\033[0;32m',     # Green
        'WARNING': '\033[0;33m',  # Yellow
        'ERROR': '\033[0;31m',    # Red
        'CRITICAL': '\033[1;31m', # Bold Red
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record):
        # Add color to the level name
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)

def setup_logging(output_dir: str, tool_name: str, debug: bool = False) -> logging.Logger:
    """
    Initialize logging for a tool.
    
    Args:
        output_dir (str): Directory where the log file will be created
        tool_name (str): Name of the tool (e.g., 'analyzer', 'simulator')
        debug (bool, optional): Whether to enable debug logging. Defaults to False.
        
    Returns:
        logging.Logger: Configured logger instance
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Create log file path
    log_file = os.path.join(output_dir, f"{tool_name}_pipeline.log")
    
    # Configure logging format
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Configure file handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    # Configure console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColoredFormatter(log_format, date_format))
    
    # Get or create logger
    logger = logging.getLogger(tool_name)
    
    # Set logging level based on debug flag
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Remove any existing handlers
    logger.handlers = []
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Log initial message
    logger.info(f"Started {tool_name} pipeline")
    logger.info(f"Log file created at: {log_file}")
    if debug:
        logger.debug("Debug logging enabled")
    
    return logger

def get_logger(tool_name: str) -> logging.Logger:
    """
    Get an existing logger for a tool.
    
    Args:
        tool_name (str): Name of the tool to get logger for
        
    Returns:
        logging.Logger: Logger instance or None if not initialized
    """
    return logging.getLogger(tool_name)

def log_analysis_params(logger: logging.Logger, params: Union[dict, argparse.Namespace]):
    """
    Log analysis parameters.
    
    Args:
        logger (logging.Logger): Logger instance
        params (Union[dict, argparse.Namespace]): Parameters to log, can be either a dictionary or argparse.Namespace
    """
    logger.info("Analysis Parameters:")
    
    # Convert Namespace to dictionary if needed
    if isinstance(params, argparse.Namespace):
        params_dict = vars(params)
    else:
        params_dict = params
    
    for key, value in params_dict.items():
        logger.info(f"- {key}: {value}")

def log_results(logger: logging.Logger, results: dict, analysis_type: str):
    """
    Log analysis results.
    
    Args:
        logger (logging.Logger): Logger instance
        results (dict): Dictionary of results to log
        analysis_type (str): Type of analysis (e.g., 'analyzer', 'simulator')
    """
    logger.info(f"{analysis_type.capitalize()} Results:")
    for key, value in results.items():
        if isinstance(value, (int, float)):
            logger.info(f"- {key}: {value:.6f}")
        else:
            logger.info(f"- {key}: {value}")

def log_simulation_params(logger, params):
    """
    Log simulation parameters for the simulator tool.
    
    Args:
        logger (logging.Logger): Logger instance
        params (dict): Dictionary containing simulation parameters
    """
    logger.info("Simulation Parameters:")
    logger.info(f"- Subject ID: {params.get('subject_id')}")
    logger.info(f"- Conductivity: {params.get('conductivity')}")
    logger.info(f"- Simulation Mode: {params.get('sim_mode')}")
    logger.info(f"- Intensity: {params.get('intensity')} A")
    logger.info(f"- Electrode Shape: {params.get('electrode_shape')}")
    logger.info(f"- Electrode Dimensions: {params.get('dimensions')} mm")
    logger.info(f"- Electrode Thickness: {params.get('thickness')} mm")
    logger.info(f"- Montages: {params.get('montages', [])}")
    logger.info("-" * 50)

def log_region_stats(logger, stats):
    """
    Log statistics for a region (analyzer-specific).
    
    Args:
        logger (logging.Logger): Logger instance
        stats (dict): Region statistics
    """
    if 'mean_value' in stats and stats['mean_value'] is not None:
        logger.info(f"- Mean Value: {stats['mean_value']:.6f}")
    if 'max_value' in stats and stats['max_value'] is not None:
        logger.info(f"- Max Value: {stats['max_value']:.6f}")
    if 'min_value' in stats and stats['min_value'] is not None:
        logger.info(f"- Min Value: {stats['min_value']:.6f}")
    if 'nodes_in_roi' in stats:
        logger.info(f"- Nodes in ROI: {stats['nodes_in_roi']}")
    if 'voxels_in_roi' in stats:
        logger.info(f"- Voxels in ROI: {stats['voxels_in_roi']}") 