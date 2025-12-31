#!/usr/bin/env python3
"""
Configuration management for TI-Toolbox benchmarking suite.

This module provides a flexible configuration system that allows users to:
1. Define data paths and parameters in a YAML config file
2. Override config values via command-line arguments
3. Use sensible defaults when no config is provided

Config file format (benchmark_config.yaml):
---
# Global settings
output_dir: /path/to/benchmark_results
keep_project: false
debug_mode: true

# Charm benchmark configuration
charm:
  project_dir: /path/to/project
  ernie_data: /path/to/ernie/data
  charm_script: /path/to/charm.sh
  clean: false

# Recon-all benchmark configuration
recon:
  project_dir: /path/to/project
  ernie_data: /path/to/ernie/data
  recon_script: /path/to/recon-all.sh
  parallel: false
  clean: false

# DICOM benchmark configuration
dicom:
  project_dir: /path/to/project
  subject_source: /path/to/subject/dir
  dicom_script: /path/to/tit/pre/dicom2nifti.sh

# Flex-search benchmark configuration
flex:
  project_dir: /path/to/project
  ernie_data: /path/to/ernie/data
  multistart: [1, 3, 5]
  iterations: 500
  popsize: 13
  cpus: 1
  opt_goal: mean
  postproc: max_TI
  roi_center: [0, 0, 0]
  roi_radius: 10.0
  electrode_radius: 4.0
  electrode_current: 1.0
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
import json

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class BenchmarkConfig:
    """Configuration manager for benchmarking suite."""
    
    DEFAULT_CONFIG_FILENAME = "benchmark_config.yaml"
    
    def __init__(self, config_file: Optional[Path] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_file: Path to YAML config file. If None, will search for
                        default config file in current directory and toolbox root.
        """
        self.config_file = config_file
        self.config = {}
        self._load_config()
        self._apply_defaults()
    
    def _find_default_config(self) -> Optional[Path]:
        """Search for default config file in common locations."""
        search_paths = [
            Path.cwd() / self.DEFAULT_CONFIG_FILENAME,
            Path.home() / ".tit" / self.DEFAULT_CONFIG_FILENAME,
        ]
        
        # Add toolbox root if we can find it
        try:
            script_dir = Path(__file__).parent
            toolbox_root = script_dir.parent.parent
            search_paths.append(toolbox_root / self.DEFAULT_CONFIG_FILENAME)
        except:
            pass
        
        for path in search_paths:
            if path.exists():
                return path
        
        return None
    
    def _load_config(self):
        """Load configuration from YAML file."""
        if self.config_file is None:
            self.config_file = self._find_default_config()
        
        if self.config_file is None:
            # No config file found, use empty config (will use defaults)
            return
        
        if not self.config_file.exists():
            print(f"Warning: Config file not found: {self.config_file}")
            return
        
        if not YAML_AVAILABLE:
            print("Warning: PyYAML not installed. Install with: pip install pyyaml")
            print("Falling back to default configuration.")
            return
        
        try:
            with open(self.config_file, 'r') as f:
                self.config = yaml.safe_load(f) or {}
            print(f"Loaded configuration from: {self.config_file}")
        except Exception as e:
            print(f"Error loading config file: {e}")
            print("Using default configuration.")
    
    def _apply_defaults(self):
        """Apply default values for missing configuration."""
        # Detect toolbox root
        try:
            script_dir = Path(__file__).parent
            toolbox_root = script_dir.parent.parent
        except:
            toolbox_root = Path.cwd()
        
        # Global defaults
        if 'output_dir' not in self.config:
            self.config['output_dir'] = str(Path.cwd() / "benchmark_results")
        
        if 'keep_project' not in self.config:
            self.config['keep_project'] = False
        
        if 'debug_mode' not in self.config:
            self.config['debug_mode'] = True
        
        # Charm defaults
        if 'charm' not in self.config:
            self.config['charm'] = {}
        
        charm = self.config['charm']
        if 'ernie_data' not in charm:
            charm['ernie_data'] = str(toolbox_root / "resources" / "example_data" / "ernie")
        if 'charm_script' not in charm:
            charm['charm_script'] = str(toolbox_root / "tit" / "pre" / "charm.sh")
        if 'project_dir' not in charm:
            charm['project_dir'] = str(Path("/mnt/tit-benchmark") if os.path.exists("/mnt") 
                                       else Path("/tmp/tit-benchmark"))
        if 'clean' not in charm:
            charm['clean'] = False
        
        # Recon defaults
        if 'recon' not in self.config:
            self.config['recon'] = {}
        
        recon = self.config['recon']
        if 'ernie_data' not in recon:
            recon['ernie_data'] = str(toolbox_root / "resources" / "example_data" / "ernie")
        if 'recon_script' not in recon:
            recon['recon_script'] = str(toolbox_root / "tit" / "pre" / "recon-all.sh")
        if 'project_dir' not in recon:
            recon['project_dir'] = str(Path("/mnt/tit-benchmark-recon") if os.path.exists("/mnt")
                                       else Path("/tmp/tit-benchmark-recon"))
        if 'parallel' not in recon:
            recon['parallel'] = False
        if 'clean' not in recon:
            recon['clean'] = False
        
        # DICOM defaults
        if 'dicom' not in self.config:
            self.config['dicom'] = {}
        
        dicom = self.config['dicom']
        if 'dicom_script' not in dicom:
            dicom['dicom_script'] = str(toolbox_root / "tit" / "pre" / "dicom2nifti.sh")
        if 'project_dir' not in dicom:
            dicom['project_dir'] = str(Path("/mnt/tit-benchmark-dicom") if os.path.exists("/mnt")
                                       else Path("/tmp/tit-benchmark-dicom"))
        if 'subject_source' not in dicom and 'dicom_source' not in dicom:
            dicom['subject_source'] = None
        
        # Flex defaults
        if 'flex' not in self.config:
            self.config['flex'] = {}
        
        flex = self.config['flex']
        if 'ernie_data' not in flex:
            flex['ernie_data'] = str(toolbox_root / "resources" / "example_data" / "ernie")
        if 'project_dir' not in flex:
            flex['project_dir'] = str(Path("/mnt/tit-benchmark-flex") if os.path.exists("/mnt")
                                      else Path("/tmp/tit-benchmark-flex"))
        if 'multistart' not in flex:
            flex['multistart'] = [1, 3, 5]
        if 'iterations' not in flex:
            flex['iterations'] = 500
        if 'popsize' not in flex:
            flex['popsize'] = 13
        if 'cpus' not in flex:
            flex['cpus'] = 1
        if 'opt_goal' not in flex:
            flex['opt_goal'] = "mean"
        if 'postproc' not in flex:
            flex['postproc'] = "max_TI"
        if 'roi_center' not in flex:
            flex['roi_center'] = [0, 0, 0]
        if 'roi_radius' not in flex:
            flex['roi_radius'] = 10.0
        if 'electrode_radius' not in flex:
            flex['electrode_radius'] = 4.0
        if 'electrode_current' not in flex:
            flex['electrode_current'] = 1.0
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self.config.get(key, default)
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get a configuration section."""
        return self.config.get(section, {})
    
    def get_charm_config(self) -> Dict[str, Any]:
        """Get charm benchmark configuration."""
        return self.get_section('charm')
    
    def get_recon_config(self) -> Dict[str, Any]:
        """Get recon-all benchmark configuration."""
        return self.get_section('recon')
    
    def get_dicom_config(self) -> Dict[str, Any]:
        """Get DICOM benchmark configuration."""
        return self.get_section('dicom')
    
    def get_flex_config(self) -> Dict[str, Any]:
        """Get flex-search benchmark configuration."""
        return self.get_section('flex')
    
    def print_config(self):
        """Print current configuration."""
        print("\n" + "="*70)
        print("BENCHMARK CONFIGURATION")
        print("="*70)
        
        if self.config_file:
            print(f"\nConfig file: {self.config_file}")
        else:
            print("\nUsing default configuration (no config file found)")
        
        print("\nGlobal Settings:")
        print(f"  output_dir: {self.config.get('output_dir')}")
        print(f"  keep_project: {self.config.get('keep_project')}")
        print(f"  debug_mode: {self.config.get('debug_mode')}")
        
        print("\nCharm Configuration:")
        charm = self.get_charm_config()
        for key, value in charm.items():
            print(f"  {key}: {value}")
        
        print("\nRecon Configuration:")
        recon = self.get_recon_config()
        for key, value in recon.items():
            print(f"  {key}: {value}")
        
        print("\nDICOM Configuration:")
        dicom = self.get_dicom_config()
        for key, value in dicom.items():
            print(f"  {key}: {value}")
        
        print("\nFlex Configuration:")
        flex = self.get_flex_config()
        for key, value in flex.items():
            print(f"  {key}: {value}")
        
        print("="*70 + "\n")
    
    def save_example_config(self, output_path: Path):
        """Save an example configuration file."""
        example_config = {
            'output_dir': str(Path.cwd() / "benchmark_results"),
            'keep_project': False,
            'debug_mode': True,
            'charm': {
                'project_dir': '/tmp/tit-benchmark',
                'ernie_data': '/path/to/resources/example_data/ernie',
                'charm_script': '/path/to/tit/pre/charm.sh',
                'clean': False
            },
            'recon': {
                'project_dir': '/tmp/tit-benchmark-recon',
                'ernie_data': '/path/to/resources/example_data/ernie',
                'recon_script': '/path/to/tit/pre/recon-all.sh',
                'parallel': False,
                'clean': False
            },
            'dicom': {
                'project_dir': '/tmp/tit-benchmark-dicom',
                'subject_source': '/path/to/subject/dir',
                'dicom_script': '/path/to/tit/pre/dicom2nifti.sh'
            },
            'flex': {
                'project_dir': '/tmp/tit-benchmark-flex',
                'ernie_data': '/path/to/resources/example_data/ernie',
                'multistart': [1, 3, 5],
                'iterations': 500,
                'popsize': 13,
                'cpus': 1,
                'opt_goal': 'mean',
                'postproc': 'max_TI',
                'roi_center': [0, 0, 0],
                'roi_radius': 10.0,
                'electrode_radius': 4.0,
                'electrode_current': 1.0
            }
        }
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if YAML_AVAILABLE:
            with open(output_path, 'w') as f:
                yaml.dump(example_config, f, default_flow_style=False, sort_keys=False)
            print(f"Example config saved to: {output_path}")
        else:
            # Fallback to JSON if YAML not available
            json_path = output_path.with_suffix('.json')
            with open(json_path, 'w') as f:
                json.dump(example_config, f, indent=2)
            print(f"Example config saved to: {json_path} (YAML not available)")


def merge_config_with_args(config: BenchmarkConfig, args, benchmark_type: str) -> Dict[str, Any]:
    """
    Merge configuration file values with command-line arguments.
    Command-line arguments take precedence over config file values.
    
    Args:
        config: BenchmarkConfig instance
        args: Parsed command-line arguments
        benchmark_type: Type of benchmark ('charm', 'recon', 'dicom', 'flex')
    
    Returns:
        Dictionary with merged configuration
    """
    # Get base config for this benchmark type
    section_config = config.get_section(benchmark_type)
    merged = section_config.copy()
    
    # Add global settings
    merged['output_dir'] = config.get('output_dir')
    merged['keep_project'] = config.get('keep_project')
    merged['debug_mode'] = config.get('debug_mode')
    
    # Override with command-line arguments (if provided)
    for key, value in vars(args).items():
        if value is not None:  # Only override if argument was explicitly provided
            # Handle special cases
            if key == 'no_debug':
                merged['debug_mode'] = not value
            elif key == 'config':
                continue  # Skip the config file argument itself
            elif key == 'keep_project':
                # Only override if explicitly set to True (action="store_true")
                # If False, it means the flag wasn't provided, so keep config value
                if value is True:
                    merged[key] = value
            else:
                merged[key] = value
    
    return merged


def main():
    """CLI for generating example config files."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="TI-Toolbox Benchmark Configuration Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate example config file
  python -m tit.benchmark.config --generate
  
  # Generate config at specific location
  python -m tit.benchmark.config --generate --output my_config.yaml
  
  # Show current configuration
  python -m tit.benchmark.config --show
  
  # Show configuration from specific file
  python -m tit.benchmark.config --show --config my_config.yaml
"""
    )
    
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate an example configuration file"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.cwd() / "benchmark_config.yaml",
        help="Output path for generated config (default: ./benchmark_config.yaml)"
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show current configuration"
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file to show"
    )
    
    args = parser.parse_args()
    
    if args.generate:
        config = BenchmarkConfig()
        config.save_example_config(args.output)
        print(f"\nExample configuration file created: {args.output}")
        print("\nEdit this file to customize paths and parameters for your system.")
        print("Then place it in one of these locations:")
        print("  1. Current directory: ./benchmark_config.yaml")
        print("  2. Home directory: ~/.tit/benchmark_config.yaml")
        print(f"  3. TI-Toolbox root: <toolbox-root>/benchmark_config.yaml")
        print("\nOr specify it with --config when running benchmarks.")
    
    elif args.show:
        config = BenchmarkConfig(args.config)
        config.print_config()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

