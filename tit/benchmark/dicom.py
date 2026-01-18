#!/usr/bin/env python3
"""
DICOM Benchmark - DICOM to NIfTI conversion

Benchmarks dcm2niix conversion performance.

Usage:
  python -m tit.benchmark.dicom --config benchmark_config.yaml
  python -m tit.benchmark.dicom --subject-source /path/to/subject/dir
"""

import sys
import os
import json
import shutil
from pathlib import Path
from datetime import datetime
import argparse

from tit.benchmark.core import (
    BenchmarkTimer,
    BenchmarkResult,
    get_hardware_info,
    print_benchmark_result,
    save_benchmark_result,
)
from tit.benchmark.logger import BenchmarkLogger, create_benchmark_log_file
from tit.benchmark.config import BenchmarkConfig, merge_config_with_args
from tit.pre.dicom2nifti import run_dicom_to_nifti


class ProjectSetup:
    """Handles BIDS project setup for DICOM/NIfTI data."""

    def __init__(
        self, project_dir: Path, subject_source: Path, subject_id: str, logger
    ):
        self.project_dir = project_dir
        self.subject_source = subject_source
        self.subject_id = subject_id
        self.bids_subject_id = f"sub-{subject_id}"
        self.logger = logger
        self.use_mnt = os.path.exists("/mnt")

        # Set up directory paths
        if self.use_mnt:
            base_dir = Path("/mnt") / project_dir.name
            self.logger.info(f"Container detected - using /mnt path: {base_dir}")
        else:
            base_dir = project_dir

        self.subject_dir = base_dir / self.bids_subject_id
        self.sourcedata_dir = self.subject_source

        # Create output directory
        self.subject_dir.mkdir(parents=True, exist_ok=True)

        # Create BIDS dataset description
        desc_file = self.subject_dir.parent / "dataset_description.json"
        if not desc_file.exists():
            desc_file.write_text(
                json.dumps(
                    {"Name": "TI-Toolbox DICOM Benchmark", "BIDSVersion": "1.6.0"}
                )
            )

    def process_sequences(self):
        """Check for T1w and T2w sequences in subject source."""
        sequences_found, total_dicom_count, total_nifti_count = [], 0, 0

        for sequence in ["T1w", "T2w"]:
            sequence_dir = self.subject_source / sequence

            # Check for DICOM files
            dicom_count = self._check_dicom_files(sequence, sequence_dir)
            if dicom_count > 0:
                sequences_found.append(sequence)
                total_dicom_count += dicom_count
            else:
                # Check for NIfTI files
                nifti_count = self._check_nifti_files(sequence)
                if nifti_count > 0:
                    sequences_found.append(sequence)
                    total_nifti_count += nifti_count

        self._log_results(sequences_found, total_dicom_count, total_nifti_count)
        return sequences_found, total_dicom_count > 0, total_nifti_count > 0

    def _check_dicom_files(self, sequence: str, sequence_dir: Path) -> int:
        """Check for DICOM files for a sequence."""
        dicom_dir = sequence_dir / "dicom"

        if dicom_dir.exists():
            # Uncompressed DICOM files
            dicom_files = [f for f in dicom_dir.glob("*") if f.is_file()]
            if dicom_files:
                self.logger.info(
                    f"Found {len(dicom_files)} {sequence} DICOM files in {dicom_dir}"
                )
                return len(dicom_files)

        elif sequence_dir.exists():
            # Compressed DICOM files
            tgz_files = list(sequence_dir.glob("*.tgz"))
            if tgz_files:
                self.logger.info(
                    f"Found {len(tgz_files)} {sequence} compressed DICOM files in {sequence_dir}"
                )
                return len(tgz_files)

        return 0

    def _check_nifti_files(self, sequence: str) -> int:
        """Check for existing NIfTI files for a sequence."""
        anat_dir = self.subject_dir / "anat"

        # Check if files already exist in the output location
        nifti_files = []
        if anat_dir.exists():
            nifti_files.extend(
                anat_dir.glob(f"{self.bids_subject_id}_{sequence}.nii.gz")
            )
            nifti_files.extend(anat_dir.glob(f"{self.bids_subject_id}_{sequence}.nii"))

        if nifti_files:
            self.logger.info(
                f"Found {len(nifti_files)} existing {sequence} NIfTI files in {anat_dir}"
            )
            return len(nifti_files)

        return 0

    def _log_results(self, sequences_found, dicom_count, nifti_count):
        """Log processing results."""
        if sequences_found:
            self.logger.info(
                f"Found sequences: {', '.join(sequences_found)} "
                f"(DICOM: {dicom_count}, NIfTI: {nifti_count})"
            )
        else:
            self.logger.warning("No T1w or T2w DICOM or NIfTI files found")
        self.logger.info(f"Project ready: {self.subject_dir.parent}")


def setup_project(project_dir: Path, subject_source: Path, subject_id: str, logger):
    """Set up BIDS project with DICOM or NIfTI data from subject directory."""
    setup = ProjectSetup(project_dir, subject_source, subject_id, logger)
    sequences_found, dicom_found, nifti_found = setup.process_sequences()
    return setup.subject_dir, subject_id, dicom_found, nifti_found


class ConversionRunner:
    """Handles DICOM to NIfTI conversion execution."""

    def __init__(
        self, subject_dir: Path, dicom_script: Path, logger, debug_mode: bool = True
    ):
        self.subject_dir = subject_dir
        self.dicom_script = dicom_script
        self.logger = logger
        self.debug_mode = debug_mode
        self.subject_id = subject_dir.name.replace("sub-", "")

    def run_conversion(self):
        """Run the DICOM conversion and return benchmark result."""
        timer = BenchmarkTimer(
            "dicom_conversion",
            metadata={
                "subject_id": self.subject_id,
                "dicom_script": str(self.dicom_script),
                "debug_mode": self.debug_mode,
            },
        )
        timer.start()

        try:
            self.logger.info(f"Running DICOM conversion for: {self.subject_id}")

            run_dicom_to_nifti(
                str(self.subject_dir.parent),
                self.subject_id,
                logger=self.logger,
            )

            result = timer.stop(success=True)
            result.metadata["nifti_output"] = str(self.subject_dir / "anat")
            return result

        except Exception as e:
            self.logger.error(f"DICOM conversion failed: {e}")
            return timer.stop(success=False, error_message=str(e))


def create_success_result(
    subject_id: str, dicom_script: Path, debug_mode: bool, subject_dir: Path, note: str
):
    """Create a successful benchmark result (no actual conversion run)."""
    now = datetime.now()
    return BenchmarkResult(
        process_name="dicom_conversion",
        start_time=now.isoformat(),
        end_time=now.isoformat(),
        duration_seconds=0.0,
        duration_formatted="0.000s",
        peak_memory_mb=0.0,
        avg_cpu_percent=0.0,
        hardware_info=get_hardware_info(),
        metadata={
            "subject_id": subject_id,
            "dicom_script": str(dicom_script),
            "debug_mode": debug_mode,
            "nifti_output": str(subject_dir / "anat"),
            "note": note,
        },
        success=True,
        error_message=None,
    )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark DICOM to NIfTI conversion")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--subject-source", type=Path)
    parser.add_argument("--subject-id", type=str)
    parser.add_argument("--dicom-script", type=Path)
    parser.add_argument("--no-debug", action="store_true")
    args = parser.parse_args()

    # Load configuration
    config = BenchmarkConfig(args.config)
    merged = merge_config_with_args(config, args, "dicom")

    # Extract paths
    project_dir = Path(merged["project_dir"])
    output_dir = Path(merged["output_dir"])
    dicom_script = Path(merged["dicom_script"])
    subject_id = merged.get("subject_id", "benchmark_dicom")
    debug_mode = merged.get("debug_mode", True)

    # Get subject source
    source_key = "subject_source" if "subject_source" in merged else "dicom_source"
    if not merged.get(source_key):
        print(f"Error: {source_key} not found in configuration")
        sys.exit(1)
    subject_source = Path(merged[source_key])

    # Validate paths
    if not subject_source.exists():
        print(f"Error: Subject source not found: {subject_source}")
        sys.exit(1)
    if not dicom_script.exists():
        print(f"Error: dicom2nifti.py not found: {dicom_script}")
        sys.exit(1)

    # Setup logging
    log_file = create_benchmark_log_file("dicom", output_dir, subject_id)
    logger = BenchmarkLogger("dicom_benchmark", log_file, debug_mode, True)
    logger.header("DICOM CONVERSION BENCHMARK")
    logger.info(f"Subject source: {subject_source}")

    try:
        # Setup project
        subject_dir, subject_id, has_dicom, has_nifti = setup_project(
            project_dir, subject_source, subject_id, logger
        )

        # Run conversion or skip
        if has_nifti:
            logger.info("NIfTI files found. Skipping DICOM conversion.")
            result = create_success_result(
                subject_id,
                dicom_script,
                debug_mode,
                subject_dir,
                "NIfTI files already available",
            )
        elif not has_dicom:
            logger.info("No DICOM or NIfTI files found.")
            result = create_success_result(
                subject_id, dicom_script, debug_mode, subject_dir, "No files found"
            )
        else:
            result = ConversionRunner(
                subject_dir, dicom_script, logger, debug_mode
            ).run_conversion()

        # Save results
        print_benchmark_result(result)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_benchmark_result(
            result, output_dir / f"dicom_benchmark_{subject_id}_{timestamp}.json"
        )
        save_benchmark_result(
            result, output_dir / f"dicom_benchmark_{subject_id}_latest.json"
        )
        logger.info(f"Results saved to {output_dir}")

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
