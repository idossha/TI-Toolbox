#!/usr/bin/env python3
"""
TI-Toolbox Analysis Entry Point

This is the main entry point for running TI-Toolbox analyses.
It provides a clean command-line interface to run analyses using configuration files.

Usage Examples:
    python main.py                                              # Run with default settings
    python main.py --help                                       # Show help
    python main.py --all-regions                               # Run all regions
    python main.py --region Left_Insula --optimization max     # Run specific analysis
    python main.py --region sphere_x36.10_y14.14_z0.33_r5     # Run spherical target
    python main.py --questions Q3 pairwise                     # Run specific questions
    python main.py --config custom_settings.yaml              # Use custom config

Author: TI-Toolbox Research Team
Date: July 2024
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

# Import the analysis runner
from pipeline import AnalysisRunner


def create_parser() -> argparse.ArgumentParser:
    """
    Create and configure the command line argument parser.
    
    Returns:
        argparse.ArgumentParser: Configured argument parser
    """
    parser = argparse.ArgumentParser(
        description="TI-Toolbox Analysis Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run analysis with default settings
  python main.py
  
  # Run analysis for specific region and optimization type
  python main.py --region Left_Insula --optimization max
  
  # Run spherical target analysis
  python main.py --region sphere_x36.10_y14.14_z0.33_r5 --optimization max
  
  # Run all regions and optimization types
  python main.py --all-regions
  
  # Use custom configuration file
  python main.py --config custom_settings.yaml
  
  # Run specific research questions only
  python main.py --questions Q3 pairwise
  
  # Validate configuration and data only
  python main.py --validate-only

  # Quick ad-hoc comparison using explicit CSVs
  python main.py --region Right_Hippocampus --optimization max \
                 --questions pairwise \
                 --file-a case_studies/data_flex/Right_Hippocampus_max_mapped3.csv \
                 --file-b case_studies/data_flex/Right_Hippocampus_max_mapped5.csv \
                 --skip-validation
        """
    )
    
    parser.add_argument(
        '--config', '-c',
        default='settings.yaml',
        help='Path to configuration file (default: settings.yaml)'
    )
    
    parser.add_argument(
        '--region', '-r',
        help='Target region to analyze (e.g., Left_Insula, Right_Hippocampus, sphere_x36.10_y14.14_z0.33_r5)'
    )
    
    parser.add_argument(
        '--optimization', '-o',
        help='Optimization type to analyze (max, normal)'
    )
    
    parser.add_argument(
        '--all-regions', '-a',
        action='store_true',
        help='Run analysis for all regions and optimization types'
    )
    
    parser.add_argument(
        '--questions', '-q',
        nargs='+',
        choices=['Q3', 'pairwise'],
        help='Specific research questions to run (default: all configured questions)'
    )
    
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate configuration and data availability'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    # Optional quick overrides to reduce setup friction
    parser.add_argument(
        '--data-dir',
        help='Override data directory containing CSVs (absolute or relative to repo root)'
    )
    parser.add_argument(
        '--file-a',
        help='Explicit CSV path for first condition (e.g., mapped3)'
    )
    parser.add_argument(
        '--file-b',
        help='Explicit CSV path for second condition (e.g., mapped5)'
    )
    parser.add_argument(
        '--cond-a',
        help='Name of the first condition (e.g., mapped3). If both cond-a and cond-b are provided, runs a custom pairwise comparison only.'
    )
    parser.add_argument(
        '--cond-b',
        help='Name of the second condition (e.g., mapped5).'
    )
    parser.add_argument(
        '--label-a',
        help='Optional label to display for condition A in plots/results (defaults to cond-a)'
    )
    parser.add_argument(
        '--label-b',
        help='Optional label to display for condition B in plots/results (defaults to cond-b)'
    )
    parser.add_argument(
        '--skip-validation',
        action='store_true',
        help='Skip data file existence validation (use with explicit file overrides)'
    )
    
    return parser


def main() -> int:
    """
    Main entry point for the TI-Toolbox analysis.
    
    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    # Parse command line arguments
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        # Initialize analysis runner
        print("🔧 Initializing TI-Toolbox Analysis Runner...")
        pairwise_override = {}
        if args.file_a or args.file_b:
            pairwise_override = {
                'file_a': args.file_a,
                'file_b': args.file_b,
            }

        runner = AnalysisRunner(
            args.config,
            data_dir_override=args.data_dir,
            pairwise_override=pairwise_override or None,
            skip_validation=args.skip_validation,
        )
        
        # Validate data availability
        print("📊 Validating data availability...")
        if not runner.validate_data_availability():
            print("❌ Data validation failed. Please check your data files.")
            return 1
        
        if args.validate_only:
            print("✅ Configuration and data validation passed.")
            return 0
        
        # Run analysis based on arguments
        # Custom quick comparison path: if both conds provided, run single custom comparison and exit
        if args.cond_a and args.cond_b and args.region and args.optimization:
            print("🚀 Running one-off custom comparison with optional explicit files...")
            results = runner.run_custom_comparison(
                region=args.region,
                optimization_type=args.optimization,
                condition_a=args.cond_a,
                condition_b=args.cond_b,
                file_a=args.file_a,
                file_b=args.file_b,
                label_a=args.label_a,
                label_b=args.label_b,
            )
        elif args.all_regions:
            print("🚀 Running analysis for all regions and optimization types...")
            results = runner.run_all_analyses()
            
        elif args.region and args.optimization:
            print(f"🎯 Running analysis for {args.region} ({args.optimization})...")
            results = runner.run_single_analysis(
                args.region, 
                args.optimization, 
                args.questions
            )
            
        else:
            # Use default settings from configuration
            print("⚙️  Using default settings from configuration...")
            default_region, default_optimization = runner.config.get_default_region()
            print(f"🎯 Running analysis for {default_region} ({default_optimization})...")
            results = runner.run_single_analysis(
                default_region,
                default_optimization,
                args.questions
            )
        
        # Print summary
        runner.print_analysis_summary(results)
        
        print("✅ Analysis completed successfully!")
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️  Analysis interrupted by user.")
        return 1
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main()) 