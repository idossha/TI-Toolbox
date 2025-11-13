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

import sys
import argparse
import time
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime

# Add parent directory to path to enable benchmark module imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

# Available benchmarks and their main functions
BENCHMARKS = {
    'dicom': ('benchmark.dicom', 'main'),
    'charm': ('benchmark.charm', 'main'),
    'recon': ('benchmark.recon', 'main'),
    'leadfield': ('benchmark.leadfield', 'main'),
    'flex': ('benchmark.flex', 'main'),
    'ex_search': ('benchmark.ex_search', 'main'),
}

# Benchmark descriptions for better UX
BENCHMARK_DESCRIPTIONS = {
    'dicom': 'DICOM to NIfTI conversion',
    'charm': 'Headreco (charm) mesh generation',
    'recon': 'FreeSurfer recon-all surface reconstruction',
    'leadfield': 'Leadfield matrix computation',
    'flex': 'Flexible electrode position optimization',
    'ex_search': 'Exhaustive electrode search optimization',
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


def run_benchmark(benchmark_name: str, continue_on_error: bool = False) -> Tuple[bool, float, str]:
    """
    Run a single benchmark.

    Args:
        benchmark_name: Name of the benchmark to run
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
        print(f"\n✓ Benchmark '{benchmark_name}' completed successfully")
        print(f"  Duration: {elapsed:.2f}s ({elapsed/60:.2f} minutes)")
        return True, elapsed, ""

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

Available benchmarks: charm, recon, dicom, flex, leadfield, ex_search
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
            success, elapsed, error_msg = run_benchmark(benchmark, args.continue_on_error)
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
