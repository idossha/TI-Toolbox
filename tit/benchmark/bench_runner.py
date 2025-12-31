#!/usr/bin/env python3
"""
Sequential Benchmark Runner for TI-Toolbox.

Allows running multiple benchmarks in a custom order with options for
error handling, progress tracking, and result reporting.

Usage:
    python bench_runner.py --benchmarks charm,recon,dicom --config benchmark_config.yaml
    python bench_runner.py --benchmarks flex,ex_search --continue-on-error
    python bench_runner.py --all --dry-run  # Show what would run
    python bench_runner.py --list  # Show available benchmarks
"""

import yaml

import argparse
import glob
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Available benchmarks and their main functions
BENCHMARKS = {
    # Preprocessing & Mesh Generation
    'dicom': ('tit.benchmark.dicom', 'main'),
    'charm': ('tit.benchmark.charm', 'main'),
    'recon': ('tit.benchmark.recon', 'main'),
    # Optimization & Simulation
    'leadfield': ('tit.benchmark.leadfield', 'main'),
    'flex': ('tit.benchmark.flex', 'main'),
    'ex_search': ('tit.benchmark.ex_search', 'main'),
    'simulator': ('tit.benchmark.simulator', 'main'),
    # Analysis Tools
    'tissue_analyzer': ('tit.benchmark.tissue_analyzer', 'main'),
    'mesh_analyzer': ('tit.benchmark.mesh_analyzer', 'main'),
    'voxel_analyzer': ('tit.benchmark.voxel_analyzer', 'main'),
}

# Benchmark descriptions for better UX
BENCHMARK_DESCRIPTIONS = {
    # Preprocessing & Mesh Generation
    'dicom': 'DICOM to NIfTI conversion',
    'charm': 'Headreco (charm) mesh generation',
    'recon': 'FreeSurfer recon-all surface reconstruction',
    # Optimization & Simulation
    'leadfield': 'Leadfield matrix computation',
    'flex': 'Flexible electrode position optimization',
    'ex_search': 'Exhaustive electrode search optimization',
    'simulator': 'TI/mTI electrode montage simulation',
    # Analysis Tools
    'tissue_analyzer': 'Tissue volume and thickness analysis (CSF, bone, skin)',
    'mesh_analyzer': 'Surface-based field analysis (mesh)',
    'voxel_analyzer': 'Volumetric field analysis (NIfTI)',
}


def load_config(config_path: str) -> Dict[str, Any]:
    """Load benchmark configuration from YAML file."""
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file '{config_path}' not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error: Failed to parse configuration file: {e}")
        sys.exit(1)


def parse_benchmark_result(output_dir: Path, benchmark_name: str) -> Tuple[Optional[bool], Optional[str]]:
    """
    Parse the latest benchmark result file to determine actual success status.

    Args:
        output_dir: Directory where benchmark results are saved
        benchmark_name: Name of the benchmark

    Returns:
        Tuple of (success: bool or None, error_message: str or None)
        Returns (None, None) if no result file found
    """
    try:
        # Find the latest result file for this benchmark
        if benchmark_name == 'ex_search':
            # ex_search saves: ex_search_benchmark_{subject_id}_{leadfield_name}_latest.json
            pattern = "ex_search_benchmark_*_latest.json"
        elif benchmark_name == 'flex':
            # flex saves: flex_benchmark_{subject_id}_summary_{timestamp}.json
            # Find the most recent summary file
            pattern = "flex_benchmark_*_summary_*.json"
        elif benchmark_name == 'tissue_analyzer':
            # tissue_analyzer saves multiple files per tissue type
            # Look for summary file: tissue_analyzer_benchmark_{subject_id}_summary_{timestamp}.json
            pattern = "tissue_analyzer_benchmark_*_summary_*.json"
        elif benchmark_name in ['mesh_analyzer', 'voxel_analyzer']:
            # These analyzers save: {analyzer}_benchmark_{subject_id}_{analysis_type}_latest.json
            pattern = f"{benchmark_name}_benchmark_*_latest.json"
        elif benchmark_name in ['dicom', 'charm', 'recon', 'leadfield', 'simulator']:
            # These benchmarks use the standard benchmark result format
            pattern = f"{benchmark_name}_benchmark_*_latest.json"
        else:
            return None, None

        # Find matching files
        result_files = list(output_dir.glob(pattern))
        if not result_files:
            return None, None

        # Get the most recent file
        latest_file = max(result_files, key=lambda p: p.stat().st_mtime)

        # Parse the result file
        with open(latest_file, 'r') as f:
            result_data = json.load(f)

        # Extract success and error info based on benchmark type
        if benchmark_name == 'flex':
            # For flex, check if any of the results succeeded
            results = result_data.get('results', [])
            success = any(r.get('success', False) for r in results)
            if not success and results:
                error_message = "All optimization runs failed"
            else:
                error_message = None
        elif benchmark_name == 'tissue_analyzer':
            # For tissue_analyzer, check if all tissue types succeeded
            results = result_data.get('results', [])
            success = all(r.get('success', False) for r in results) if results else False
            if not success and results:
                failed_tissues = [r.get('tissue_type', 'unknown') for r in results if not r.get('success', False)]
                error_message = f"Failed tissue types: {', '.join(failed_tissues)}"
            else:
                error_message = None
        else:
            # For other benchmarks, check the top-level success field
            success = result_data.get('success')
            error_message = result_data.get('error_message')

        return success, error_message

    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        print(f"Warning: Could not parse benchmark result file: {e}")
        return None, None


def run_benchmark(benchmark_name: str, output_dir: Path, continue_on_error: bool = False) -> Tuple[bool, float, str]:
    """
    Run a single benchmark.

    Args:
        benchmark_name: Name of the benchmark to run
        output_dir: Directory where benchmark results are saved
        continue_on_error: Whether to continue if benchmark fails

    Returns:
        Tuple of (success: bool, elapsed_time: float, error_msg: str)
    """
    if benchmark_name not in BENCHMARKS:
        error_msg = f"Unknown benchmark '{benchmark_name}'"
        print(f"Error: {error_msg}")
        return False, 0.0, error_msg

    module_name, func_name = BENCHMARKS[benchmark_name]

    try:
        print(f"\n{'='*70}")
        print(f"Starting benchmark: {benchmark_name.upper()}")
        desc = BENCHMARK_DESCRIPTIONS.get(benchmark_name, "")
        if desc:
            print(f"Description: {desc}")
        print(f"{'='*70}")

        # Import the benchmark module dynamically
        module = __import__(module_name, fromlist=[func_name])
        benchmark_func = getattr(module, func_name)

        # Save original argv and replace with clean argv for the benchmark
        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0]]  # Keep only script name

        try:
            # Run the benchmark
            start_time = time.time()
            benchmark_func()
            end_time = time.time()
        finally:
            # Restore original argv
            sys.argv = original_argv

        elapsed = end_time - start_time

        # Check the actual benchmark result from the saved file
        actual_success, actual_error_msg = parse_benchmark_result(output_dir, benchmark_name)

        if actual_success is not None:
            # Use the actual result from the benchmark file
            success = actual_success
            error_msg = actual_error_msg or ""
            if success:
                print(f"\n✓ Benchmark '{benchmark_name}' completed successfully")
            else:
                print(f"\n✗ Benchmark '{benchmark_name}' failed (internal error)")
                if actual_error_msg:
                    print(f"  Error: {actual_error_msg}")
        else:
            # Fallback to assuming success if no result file found
            print(f"\n✓ Benchmark '{benchmark_name}' completed (no result file to check)")
            success = True
            error_msg = ""

        print(f"  Duration: {elapsed:.2f}s ({elapsed/60:.2f} minutes)")
        return success, elapsed, error_msg

    except KeyboardInterrupt:
        print(f"\n✗ Benchmark '{benchmark_name}' interrupted by user")
        raise
    except Exception as e:
        elapsed = time.time() - start_time if 'start_time' in locals() else 0.0
        error_msg = str(e)
        print(f"\n✗ Error running benchmark '{benchmark_name}': {error_msg}")

        if not continue_on_error:
            print("Stopping sequential execution due to error.")
            return False, elapsed, error_msg
        else:
            print("Continuing to next benchmark...")
            return False, elapsed, error_msg


def save_results_summary(results: List[Tuple[str, bool, float, str]], 
                         output_dir: Path, total_time: float):
    """Save benchmark results to JSON file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_duration_seconds": total_time,
        "total_duration_formatted": f"{total_time/60:.2f} minutes",
        "benchmarks": []
    }
    
    for benchmark_name, success, elapsed, error_msg in results:
        summary["benchmarks"].append({
            "name": benchmark_name,
            "description": BENCHMARK_DESCRIPTIONS.get(benchmark_name, ""),
            "success": success,
            "duration_seconds": elapsed,
            "duration_formatted": f"{elapsed:.2f}s",
            "error_message": error_msg if error_msg else None
        })
    
    # Save timestamped and latest files
    output_dir.mkdir(parents=True, exist_ok=True)
    results_file = output_dir / f"bench_runner_{timestamp}.json"
    latest_file = output_dir / "bench_runner_latest.json"
    
    with open(results_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    with open(latest_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\nResults saved to: {results_file}")
    return results_file


def main():
    """Main entry point for sequential benchmark runner."""
    parser = argparse.ArgumentParser(
        prog="bench_runner.py",
        description="Run TI-Toolbox benchmarks sequentially in custom order",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run specific benchmarks in order
  python bench_runner.py --benchmarks charm,recon,dicom

  # Run all benchmarks
  python bench_runner.py --all

  # Run with custom config and continue on errors
  python bench_runner.py --benchmarks flex,ex_search --config my_config.yaml --continue-on-error

  # Dry run to see what would be executed
  python bench_runner.py --all --dry-run

  # List available benchmarks
  python bench_runner.py --list

Available benchmarks: 
  Preprocessing: dicom, charm, recon
  Optimization: leadfield, flex, ex_search, simulator
  Analysis: tissue_analyzer, mesh_analyzer, voxel_analyzer
        """
    )

    parser.add_argument(
        '--benchmarks', '-b',
        type=str,
        help='Comma-separated list of benchmarks to run in order (e.g., "charm,recon,dicom")'
    )

    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Run all available benchmarks in default order'
    )

    parser.add_argument(
        '--config', '-c',
        type=str,
        default='benchmark_config.yaml',
        help='Path to benchmark configuration file (default: benchmark_config.yaml)'
    )

    parser.add_argument(
        '--continue-on-error',
        action='store_true',
        help='Continue running remaining benchmarks even if one fails'
    )

    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List available benchmarks and exit'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what benchmarks would run without actually running them'
    )
    
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path.cwd() / "benchmark_results",
        help='Directory to save benchmark results (default: ./benchmark_results)'
    )

    args = parser.parse_args()

    # List available benchmarks if requested
    if args.list:
        print("Available benchmarks:")
        print()
        for name in sorted(BENCHMARKS.keys()):
            desc = BENCHMARK_DESCRIPTIONS.get(name, "")
            print(f"  {name:12} - {desc}")
        print()
        sys.exit(0)

    # Determine which benchmarks to run
    if args.all:
        benchmark_order = list(BENCHMARKS.keys())
    elif args.benchmarks:
        benchmark_order = [b.strip() for b in args.benchmarks.split(',')]
        # Validate benchmark names
        invalid = [b for b in benchmark_order if b not in BENCHMARKS]
        if invalid:
            print(f"Error: Unknown benchmarks: {', '.join(invalid)}")
            print(f"Available benchmarks: {', '.join(sorted(BENCHMARKS.keys()))}")
            sys.exit(1)
    else:
        print("Error: Must specify --benchmarks or --all")
        parser.print_help()
        sys.exit(1)

    # Load configuration
    try:
        config = load_config(args.config)
        print(f"Using configuration: {args.config}")
    except Exception as e:
        print(f"Warning: Could not load config: {e}")
        config = {}

    # Display execution plan
    print(f"\n{'='*70}")
    print("BENCHMARK EXECUTION PLAN")
    print(f"{'='*70}")
    print(f"Configuration: {args.config}")
    print(f"Output directory: {args.output_dir}")
    print(f"Continue on error: {args.continue_on_error}")
    print(f"\nRunning {len(benchmark_order)} benchmark(s) in sequence:")
    for i, benchmark in enumerate(benchmark_order, 1):
        desc = BENCHMARK_DESCRIPTIONS.get(benchmark, "")
        print(f"  {i}. {benchmark:12} - {desc}")
    print(f"{'='*70}")

    # Dry run mode - just show what would run
    if args.dry_run:
        print("\nDry run mode - no benchmarks will be executed.")
        sys.exit(0)

    # Track results
    results = []
    overall_start = time.time()

    try:
        for benchmark in benchmark_order:
            success, elapsed, error_msg = run_benchmark(benchmark, args.output_dir, args.continue_on_error)
            results.append((benchmark, success, elapsed, error_msg))

            if not success and not args.continue_on_error:
                break

    except KeyboardInterrupt:
        print("\n\nBenchmark run interrupted by user.")
        overall_end = time.time()
        total_elapsed = overall_end - overall_start
        
        if results:
            print("\nPartial results:")
            for benchmark, success, elapsed, _ in results:
                status = "✓ PASSED" if success else "✗ FAILED"
                print(f"  {benchmark.upper():12} {status} ({elapsed:.2f}s)")
        
        sys.exit(130)

    # Print summary
    overall_end = time.time()
    total_elapsed = overall_end - overall_start

    print(f"\n{'='*70}")
    print("BENCHMARK RUN COMPLETE")
    print(f"{'='*70}")
    print(f"Total time: {total_elapsed:.2f}s ({total_elapsed/60:.2f} minutes)")
    print("\nResults:")

    success_count = 0
    for benchmark, success, elapsed, error_msg in results:
        status = "✓ PASSED" if success else "✗ FAILED"
        timing = f"({elapsed:.2f}s)" if elapsed > 0 else ""
        print(f"  {benchmark.upper():12} {status:10} {timing}")
        if not success and error_msg:
            print(f"               Error: {error_msg}")
        if success:
            success_count += 1

    print(f"\nSummary: {success_count}/{len(results)} benchmarks passed")
    
    # Save results to file
    try:
        save_results_summary(results, args.output_dir, total_elapsed)
    except Exception as e:
        print(f"Warning: Failed to save results summary: {e}")

    # Exit with appropriate code
    if success_count == len(results):
        print("\n✓ All benchmarks completed successfully!")
        sys.exit(0)
    else:
        print(f"\n✗ {len(results) - success_count} benchmark(s) failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
