#!/usr/bin/env python3
"""
Leadfield Benchmark - Leadfield matrix generation

Benchmarks leadfield generation performance with different electrode configurations.

Usage:
  python -m benchmark.leadfield --config benchmark_config.yaml
  python -m benchmark.leadfield --m2m-dir /path/to/m2m_101 --electrode-csv GSN-HydroCel-185.csv
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.core import (
    BenchmarkTimer, print_hardware_info, print_benchmark_result, save_benchmark_result
)
from benchmark.logger import BenchmarkLogger, create_benchmark_log_file
from benchmark.config import BenchmarkConfig, merge_config_with_args
from opt.leadfield import LeadfieldGenerator


def find_electrode_csv(m2m_dir: Path, electrode_csv: str, logger):
    """Find electrode CSV file in various locations."""
    search_paths = [
        m2m_dir / "eeg_positions" / electrode_csv,
        Path(__file__).parent.parent.parent / "resources" / "amv" / electrode_csv,
        Path(__file__).parent.parent.parent / "resources" / "ElectrodeCaps_MNI" / electrode_csv
    ]
    
    for path in search_paths:
        if path.exists():
            logger.info(f"Found electrode CSV: {path}")
            return path
    
    raise FileNotFoundError(f"Electrode CSV not found: {electrode_csv}")


def setup_project(project_dir: Path, m2m_dir: Path, logger):
    """Set up benchmark project structure."""
    m2m_name = m2m_dir.name
    if not m2m_name.startswith("m2m_"):
        raise ValueError(f"Invalid m2m directory name: {m2m_name}")
    
    subject_id = m2m_name.replace("m2m_", "")
    bids_subject_id = f"sub-{subject_id}"
    
    # Detect container and set paths
    if os.path.exists("/mnt"):
        subject_dir = Path("/mnt") / project_dir.name / bids_subject_id
    else:
        subject_dir = project_dir / bids_subject_id
    
    leadfields_dir = subject_dir / "leadfields"
    leadfields_dir.mkdir(parents=True, exist_ok=True)
    
    return subject_dir, subject_id, leadfields_dir


def run_benchmark(subject_id, leadfields_dir, m2m_dir, electrode_csv_path, 
                  electrode_csv_name, tissues, output_dir, logger):
    """Run leadfield generation benchmark."""
    print_hardware_info()
    
    logger.separator("=", 70)
    logger.info("LEADFIELD GENERATION BENCHMARK")
    logger.separator("=", 70)
    logger.info(f"Subject: {subject_id}")
    logger.info(f"Electrode CSV: {electrode_csv_name}")
    logger.info(f"Tissues: {tissues}")
    logger.separator("=", 70)
    
    # Start benchmark
    net_name = electrode_csv_name.replace('.csv', '')
    metadata = {
        "subject_id": subject_id,
        "electrode_csv": electrode_csv_name,
        "tissues": tissues,
        "net_name": net_name
    }
    
    timer = BenchmarkTimer("leadfield_generation", metadata=metadata)
    timer.start()
    
    try:
        # Generate leadfield (pass full m2m_dir path)
        generator = LeadfieldGenerator(subject_dir=str(m2m_dir), electrode_cap=net_name)
        
        logger.info("Generating leadfield matrix...")
        result = generator.generate_leadfield(
            output_dir=str(leadfields_dir),
            tissues=tissues,
            eeg_cap_path=str(electrode_csv_path),
            cleanup=True
        )
        
        benchmark_result = timer.stop(success=True)
        
        # Add file information to metadata
        benchmark_result.metadata.update({
            'output_files': {
                'hdf5': result.get('hdf5'),
                'npy_leadfield': result.get('npy_leadfield'),
                'npy_positions': result.get('npy_positions')
            },
            'leadfield_shape': list(generator.lfm.shape) if generator.lfm is not None else None
        })
        
        return benchmark_result
        
    except Exception as e:
        logger.error(f"Leadfield generation failed: {e}")
        return timer.stop(success=False, error_message=str(e))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark leadfield generation")
    parser.add_argument("--config", type=Path, help="Path to configuration file")
    parser.add_argument("--project-dir", type=Path, help="Project directory")
    parser.add_argument("--output-dir", type=Path, help="Output directory")
    parser.add_argument("--m2m-dir", type=Path, help="Path to m2m directory")
    parser.add_argument("--electrode-csv", type=str, help="Electrode CSV filename")
    parser.add_argument("--tissues", type=str, help="Comma-separated tissue types")
    parser.add_argument("--no-debug", action="store_true")
    
    args = parser.parse_args()
    
    # Load and merge configuration
    config = BenchmarkConfig(args.config)
    merged = merge_config_with_args(config, args, 'leadfield')
    
    # Extract configuration
    project_dir = Path(merged['project_dir'])
    output_dir = Path(merged['output_dir'])
    m2m_dir = Path(merged['m2m_dir'])
    electrode_csv = merged.get('electrode_csv', 'GSN-HydroCel-185.csv')
    debug_mode = merged.get('debug_mode', True)
    
    # Parse tissues
    tissues_config = merged.get('tissues', [1, 2])
    tissues = [int(x) for x in tissues_config] if isinstance(tissues_config, list) else \
              [int(x.strip()) for x in tissues_config.split(",")]
    
    if not m2m_dir.exists():
        print(f"Error: m2m directory not found: {m2m_dir}")
        sys.exit(1)
    
    # Setup logging
    subject_id = m2m_dir.name.replace("m2m_", "")
    log_file = create_benchmark_log_file("leadfield", output_dir, subject_id)
    logger = BenchmarkLogger("leadfield_benchmark", log_file, debug_mode, True)
    
    logger.header("LEADFIELD GENERATION BENCHMARK")
    logger.info(f"m2m: {m2m_dir}")
    logger.info(f"Electrode CSV: {electrode_csv}")
    
    try:
        # Setup project
        subject_dir, subject_id, leadfields_dir = setup_project(project_dir, m2m_dir, logger)
        
        # Find electrode CSV
        electrode_csv_path = find_electrode_csv(m2m_dir, electrode_csv, logger)
        
        # Run benchmark
        result = run_benchmark(
            subject_id, leadfields_dir, m2m_dir, electrode_csv_path,
            electrode_csv, tissues, output_dir, logger
        )
        
        # Save results
        print_benchmark_result(result)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        net_name = electrode_csv.replace('.csv', '')
        result_file = output_dir / f"leadfield_benchmark_{subject_id}_{net_name}_{timestamp}.json"
        save_benchmark_result(result, result_file)
        
        latest_file = output_dir / f"leadfield_benchmark_{subject_id}_{net_name}_latest.json"
        save_benchmark_result(result, latest_file)
        
        logger.info(f"Results saved: {result_file}")
        
    except KeyboardInterrupt:
        logger.warning("Benchmark interrupted")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
