#!/usr/bin/env python3
"""
Configuration Loader for TI-Toolbox Analysis

This module handles loading and validating the analysis configuration from YAML files.
It provides a centralized way to manage all analysis parameters and settings.

Author: TI-Toolbox Research Team
Date: July 2024
"""

import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging


class ConfigLoader:
    """
    A class to load and validate analysis configuration from YAML files.
    
    This class provides methods to load configuration files, validate settings,
    and provide easy access to configuration parameters.
    """
    
    def __init__(self, config_file: str = "settings.yaml"):
        """
        Initialize the ConfigLoader.
        
        Args:
            config_file (str): Path to the configuration file
        """
        self.config_file = Path(config_file)
        self.config = None
        self.logger = logging.getLogger(__name__)
        
        # Load configuration
        self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """
        Load configuration from YAML file.
        
        Returns:
            Dict[str, Any]: Configuration dictionary
        """
        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")
        
        try:
            with open(self.config_file, 'r') as f:
                self.config = yaml.safe_load(f)
            
            self.logger.info(f"Configuration loaded from {self.config_file}")
            return self.config
            
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing configuration file: {e}")
        except Exception as e:
            raise RuntimeError(f"Error loading configuration: {e}")
    
    def get_analysis_settings(self) -> Dict[str, Any]:
        """Get analysis settings from configuration."""
        return self.config.get('analysis', {})
    
    def get_data_settings(self) -> Dict[str, Any]:
        """Get data settings from configuration."""
        return self.config.get('data', {})
    
    def get_statistics_settings(self) -> Dict[str, Any]:
        """Get statistics settings from configuration."""
        return self.config.get('statistics', {})
    
    def get_plotting_settings(self) -> Dict[str, Any]:
        """Get plotting settings from configuration."""
        return self.config.get('plotting', {})
    
    def get_pipeline_settings(self) -> Dict[str, Any]:
        """Get pipeline settings from configuration."""
        return self.config.get('pipeline', {})
    
    def get_validation_settings(self) -> Dict[str, Any]:
        """Get validation settings from configuration."""
        return self.config.get('validation', {})
    
    def get_regions(self) -> List[Dict[str, Any]]:
        """Get list of available regions from configuration."""
        data_settings = self.get_data_settings()
        return data_settings.get('regions', [])
    
    def get_conditions(self) -> List[str]:
        """Get list of available conditions from configuration."""
        data_settings = self.get_data_settings()
        return data_settings.get('conditions', [])
    
    def get_questions(self) -> List[str]:
        """Get list of research questions to run from configuration."""
        analysis_settings = self.get_analysis_settings()
        return analysis_settings.get('questions', [])
    
    def get_output_dirs(self) -> Dict[str, Path]:
        """Get output directory paths from configuration."""
        analysis_settings = self.get_analysis_settings()
        output_settings = analysis_settings.get('output', {})
        
        # Convert relative paths to absolute paths
        # Save results next to the data directory, not next to analysis directory
        data_dir = self.get_data_dir()
        data_parent_dir = data_dir.parent
        results_dir = data_parent_dir / output_settings.get('results_dir', 'results/tables')
        figures_dir = data_parent_dir / output_settings.get('figures_dir', 'results/figures')
        
        return {
            'results': results_dir,
            'figures': figures_dir
        }
    
    def get_data_dir(self) -> Path:
        """Get data directory path from configuration."""
        data_settings = self.get_data_settings()
        data_dir = data_settings.get('data_dir', 'data/processed')
        
        # Convert relative path to absolute path
        # The data directory is relative to the case_studies directory
        analysis_dir = Path(__file__).parent
        case_studies_dir = analysis_dir.parent
        return case_studies_dir / data_dir
    
    def validate_config(self) -> bool:
        """
        Validate the loaded configuration.
        
        Returns:
            bool: True if configuration is valid
        """
        try:
            # Check required sections
            required_sections = ['analysis', 'data', 'statistics', 'plotting', 'pipeline']
            for section in required_sections:
                if section not in self.config:
                    raise ValueError(f"Missing required configuration section: {section}")
            
            # Validate regions
            regions = self.get_regions()
            if not regions:
                raise ValueError("No regions defined in configuration")
            
            for region in regions:
                if 'name' not in region:
                    raise ValueError("Region missing 'name' field")
                if 'optimization_types' not in region:
                    raise ValueError(f"Region '{region['name']}' missing 'optimization_types' field")
            
            # Validate conditions
            conditions = self.get_conditions()
            if not conditions:
                raise ValueError("No conditions defined in configuration")
            
            # Validate questions
            questions = self.get_questions()
            if not questions:
                raise ValueError("No research questions defined in configuration")
            
            valid_questions = ['Q3', 'pairwise']
            for question in questions:
                if question not in valid_questions:
                    raise ValueError(f"Invalid research question: {question}")
            
            self.logger.info("Configuration validation passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Configuration validation failed: {e}")
            raise
    
    def get_region_combinations(self) -> List[tuple]:
        """
        Get all valid region and optimization type combinations.
        
        Returns:
            List[tuple]: List of (region_name, optimization_type) tuples
        """
        combinations = []
        regions = self.get_regions()
        
        for region in regions:
            region_name = region['name']
            optimization_types = region['optimization_types']
            
            for opt_type in optimization_types:
                combinations.append((region_name, opt_type))
        
        return combinations
    
    def get_default_region(self) -> tuple:
        """
        Get the default region and optimization type.
        
        Returns:
            tuple: (region_name, optimization_type)
        """
        pipeline_settings = self.get_pipeline_settings()
        default_settings = pipeline_settings.get('default', {})
        
        region = default_settings.get('region', 'Left_Insula')
        optimization_type = default_settings.get('optimization_type', 'max')
        
        return (region, optimization_type)
    
    def should_run_all_regions(self) -> bool:
        """Check if all regions should be run automatically."""
        pipeline_settings = self.get_pipeline_settings()
        return pipeline_settings.get('run_all_regions', False)
    
    def setup_logging(self):
        """Setup logging based on configuration."""
        pipeline_settings = self.get_pipeline_settings()
        logging_settings = pipeline_settings.get('logging', {})
        
        level = getattr(logging, logging_settings.get('level', 'INFO'))
        log_file = logging_settings.get('log_file', 'analysis.log')
        save_logs = logging_settings.get('save_logs', True)
        
        # Configure logging
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_file) if save_logs else logging.NullHandler()
            ]
        )


def load_config(config_file: str = "settings.yaml") -> ConfigLoader:
    """
    Convenience function to load configuration.
    
    Args:
        config_file (str): Path to configuration file
        
    Returns:
        ConfigLoader: Configured ConfigLoader instance
    """
    config_loader = ConfigLoader(config_file)
    config_loader.setup_logging()
    config_loader.validate_config()
    return config_loader 