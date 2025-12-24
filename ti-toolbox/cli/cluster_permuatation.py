#!/usr/bin/env simnibs_python
"""
Permutation Analysis CLI - Unified cluster-based permutation testing

A Python-based command-line interface for unified permutation testing
supporting both group comparison and correlation analysis.

Usage:
    simnibs_python permutation_analysis_cli.py --csv subjects.csv --name analysis --analysis-type group_comparison

Or make it executable and run directly:
    ./permutation_analysis_cli.py --csv subjects.csv --name analysis --analysis-type correlation
"""

import sys
import os
from pathlib import Path

# Add TI-Toolbox to path
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir))

import click
from stats import permutation_analysis

@click.command(context_settings=dict(help_option_names=['-h', '--help']),
                epilog="""
EXAMPLES:

  Group Comparison (binary outcomes):
    %(prog)s --csv subjects.csv --name group_analysis --analysis-type group_comparison

  Correlation Analysis (continuous outcomes):
    %(prog)s --csv behavioral_data.csv --name corr_analysis --analysis-type correlation --use-weights

CSV FORMAT:

  Group Comparison:
    subject_id,simulation_name,response
    070,ICP_RHIPPO,1    # responder
    071,ICP_RHIPPO,0    # non-responder

  Correlation Analysis:
    subject_id,simulation_name,effect_size,weight
    070,ICP_RHIPPO,0.45,25.0    # continuous outcome + optional weight
    071,ICP_RHIPPO,0.32,30.0

REQUIRED FILES:
  - CSV file with subject configurations (see format above)
  - NIfTI files for each subject/simulation in TI-Toolbox BIDS structure
""")
@click.option('--csv', '-c', required=True,
              type=click.Path(exists=True, dir_okay=False),
              help='Path to CSV file with subject configurations (see CSV FORMAT below)')
@click.option('--name', '-n', required=True,
              help='Analysis name (used for output directory)')
@click.option('--analysis-type', required=True,
              type=click.Choice(['group_comparison', 'correlation']),
              help='Type of analysis: group_comparison (binary) or correlation (continuous)')
@click.option('--test-type',
              type=click.Choice(['unpaired', 'paired']),
              help='Statistical test type for group comparison (default: unpaired)')
@click.option('--alternative',
              type=click.Choice(['two-sided', 'greater', 'less']),
              help='Alternative hypothesis (default: two-sided)')
@click.option('--correlation-type',
              type=click.Choice(['pearson', 'spearman']),
              help='Type of correlation for correlation analysis (default: pearson)')
@click.option('--cluster-threshold', '-t', default=0.05, type=float,
              help='P-value threshold for cluster formation (default: 0.05)')
@click.option('--cluster-stat',
              type=click.Choice(['mass', 'size']), default='mass',
              help='Cluster statistic: mass or size (default: mass)')
@click.option('--n-permutations', '-p', default=1000, type=int,
              help='Number of permutations (default: 1000)')
@click.option('--alpha', '-a', default=0.05, type=float,
              help='Cluster-level significance threshold (default: 0.05)')
@click.option('--n-jobs', '-j', default=-1, type=int,
              help='Number of parallel jobs: -1=all cores, 1=sequential (default: -1)')
@click.option('--use-weights', is_flag=True,
              help='Use weights from CSV if available (correlation analysis only)')
@click.option('--tissue-type',
              type=click.Choice(['grey', 'white', 'all']), default='grey',
              help='Tissue type for NIfTI files (default: grey)')
@click.option('--nifti-pattern', default=None,
              help='Custom NIfTI filename pattern (overrides --tissue-type)')
@click.option('--quiet', '-q', is_flag=True,
              help='Suppress progress output')
@click.option('--save-perm-log', is_flag=True,
              help='Save detailed permutation log file')
def main(csv, name, analysis_type, test_type, alternative, correlation_type,
         cluster_threshold, cluster_stat, n_permutations, alpha, n_jobs,
         use_weights, tissue_type, nifti_pattern, quiet, save_perm_log):
    """
    Unified Cluster-Based Permutation Testing CLI

    Performs non-parametric statistical analysis using cluster-based permutation correction.
    Supports both group comparison (binary outcomes) and correlation analysis (continuous outcomes).

    REQUIREMENTS:
    - CSV file with subject configurations (format depends on analysis type)
    - NIfTI files in TI-Toolbox BIDS structure
    - SimNIBS environment with required dependencies

    For examples and CSV format details, run: permutation_analysis_cli.py --help
    """

    # Validate CSV file format based on analysis type
    try:
        import pandas as pd
        df = pd.read_csv(csv)

        if analysis_type == 'group_comparison':
            required_cols = ['subject_id', 'simulation_name', 'response']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                click.echo(f"ERROR: CSV file missing required columns for group comparison: {missing_cols}", err=True)
                click.echo("Required columns: subject_id, simulation_name, response", err=True)
                return 1
        else:  # correlation
            required_cols = ['subject_id', 'simulation_name', 'effect_size']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                click.echo(f"ERROR: CSV file missing required columns for correlation analysis: {missing_cols}", err=True)
                click.echo("Required columns: subject_id, simulation_name, effect_size", err=True)
                return 1

        click.echo(f"✓ CSV file validated: {len(df)} subjects found")

    except Exception as e:
        click.echo(f"ERROR: Could not validate CSV file: {e}", err=True)
        return 1

    # Build configuration dictionary
    config = {
        'analysis_type': analysis_type,
        'cluster_threshold': cluster_threshold,
        'cluster_stat': cluster_stat,
        'n_permutations': n_permutations,
        'alpha': alpha,
        'n_jobs': n_jobs,
        'tissue_type': tissue_type,
        'nifti_file_pattern': nifti_pattern,
    }

    # Add analysis-specific parameters
    if analysis_type == 'group_comparison':
        if test_type is not None:
            config['test_type'] = test_type
        if alternative is not None:
            config['alternative'] = alternative
    else:  # correlation
        if correlation_type is not None:
            config['correlation_type'] = correlation_type
        config['use_weights'] = use_weights

    # Print header if not quiet
    if not quiet:
        print("=" * 70)
        print("UNIFIED CLUSTER-BASED PERMUTATION TESTING - TI-TOOLBOX")
        print("=" * 70)
        print(f"Analysis type: {analysis_type}")
        print(f"CSV file: {csv}")
        print(f"Analysis name: {name}")
        print(f"Tissue type: {tissue_type}")
        print(f"Permutations: {n_permutations}")
        if analysis_type == 'group_comparison':
            print(f"Test type: {config.get('test_type', 'unpaired')}")
            print(f"Alternative: {config.get('alternative', 'two-sided')}")
        else:
            print(f"Correlation type: {config.get('correlation_type', 'pearson')}")
            print(f"Use weights: {use_weights}")
        print(f"Parallel jobs: {n_jobs if n_jobs != -1 else 'all cores'}")
        print(f"Cluster statistic: {cluster_stat}")
        print(f"Cluster threshold: p < {cluster_threshold}")
        print("=" * 70)
        print()

    try:
        # Run analysis
        results = permutation_analysis.run_analysis(
            subject_configs=csv,
            analysis_name=name,
            config=config,
            output_callback=None if quiet else print
        )

        # Print results if not quiet
        if not quiet:
            print()
            print("=" * 70)
            print("ANALYSIS COMPLETE!")
            print("=" * 70)
            print(f"Output directory: {results['output_dir']}")
            if 'n_significant_clusters' in results:
                print(f"Significant clusters: {results['n_significant_clusters']}")
            if 'n_significant_voxels' in results:
                print(f"Significant voxels: {results['n_significant_voxels']}")
            print(f"Analysis time: {results['analysis_time']:.1f} seconds")
            print("=" * 70)

        return 0

    except Exception as e:
        if not quiet:
            print(f"\nERROR: {str(e)}", file=sys.stderr)
            import traceback
            traceback.print_exc()
        else:
            print(f"ERROR: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
