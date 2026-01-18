#!/usr/bin/env simnibs_python
"""
Example Data Manager for TI-Toolbox

This module handles the automatic copying of example data to BIDS-compliant
locations when a new project is initialized. It copies anatomical NIfTI files
for ernie and MNI152 subjects to their respective anat folders for immediate
use in TI-Toolbox workflows.

Author: TI-Toolbox Development Team
"""

import os
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tit.core.paths import get_path_manager

# Set up logging (no console output)
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
logger.setLevel(logging.INFO)
logger.propagate = False  # Prevent propagation to root logger


class ExampleDataManager:
    """Manages copying of example data to BIDS-compliant project structure."""

    def __init__(self, toolbox_root: str, project_dir: str):
        """
        Initialize the Example Data Manager.

        Args:
            toolbox_root: Path to the TI-toolbox root directory
            project_dir: Path to the target project directory
        """
        self.toolbox_root = Path(toolbox_root)
        self.project_dir = Path(project_dir)
        self.example_data_dir = self.toolbox_root / "resources" / "example_data"

        # Define mapping of example data to BIDS structure
        self.data_mapping = self._create_data_mapping()

    def _create_data_mapping(self) -> Dict[str, Dict[str, str]]:
        """
        Create mapping of example data files to their BIDS-compliant destinations.

        Returns:
            Dictionary mapping source paths to destination paths
        """
        mapping = {
            # Ernie subject data - only NIfTI files
            "ernie": {
                "T1.nii.gz": "sub-ernie/anat/sub-ernie_T1w.nii.gz",
                "T2_reg.nii.gz": "sub-ernie/anat/sub-ernie_T2w.nii.gz",
            },
            # MNI152 template data
            "MNI152": {"T1.nii.gz": "sub-MNI152/anat/sub-MNI152_T1w.nii.gz"},
        }

        return mapping

    def check_example_data_exists(self) -> bool:
        """
        Check if example data directory exists and contains expected data.

        Returns:
            True if example data is available, False otherwise
        """
        if not self.example_data_dir.exists():
            logger.warning(f"Example data directory not found: {self.example_data_dir}")
            return False

        # Check for key example subjects
        key_subjects = ["ernie", "MNI152"]
        for subject in key_subjects:
            subject_dir = self.example_data_dir / subject
            if not subject_dir.exists():
                logger.warning(f"Key example subject not found: {subject}")
                return False

        return True

    def is_new_project(self) -> bool:
        """
        Determine if this is a new project that should receive example data.

        A project is considered new if:
        1. No subject directories exist yet
        2. Example data hasn't been copied before
        3. No actual user data is present

        Returns:
            True if this is a new project, False otherwise
        """
        # Check for existing subject directories
        subject_dirs = list(self.project_dir.glob("sub-*"))
        if subject_dirs:
            logger.info(
                "Found existing subject directories, skipping example data copy"
            )
            return False

        # Check project status file if it exists to see if example data was already copied
        pm = get_path_manager()
        pm.project_dir = str(self.project_dir)
        status_file = Path(pm.path("ti_toolbox_status"))
        if status_file.exists():
            try:
                import json

                with open(status_file, "r") as f:
                    status_data = json.load(f)

                # Check if example data was already copied
                if status_data.get("example_data_copied", False):
                    logger.info(
                        "Example data already copied according to project status"
                    )
                    return False

            except Exception as e:
                logger.warning(f"Could not read project status file: {e}")

        # Check for any user-created NIfTI files in the project root
        user_nifti_files = list(self.project_dir.glob("*.nii.gz"))
        if user_nifti_files:
            logger.info("Found existing user NIfTI files, skipping example data copy")
            return False

        # Check for sourcedata directory with actual content (indicates user data)
        sourcedata_dir = self.project_dir / "sourcedata"
        if sourcedata_dir.exists():
            sourcedata_content = list(sourcedata_dir.rglob("*.dcm")) + list(
                sourcedata_dir.rglob("*.nii.gz")
            )
            if sourcedata_content:
                logger.info(
                    "Found existing user data in sourcedata, skipping example data copy"
                )
                return False

        return True

    def copy_file_or_directory(self, src_path: Path, dst_path: Path) -> bool:
        """
        Copy a file or directory from source to destination.

        Args:
            src_path: Source path
            dst_path: Destination path

        Returns:
            True if copy was successful, False otherwise
        """
        try:
            # Create parent directories if they don't exist
            dst_path.parent.mkdir(parents=True, exist_ok=True)

            if src_path.is_file():
                shutil.copy2(src_path, dst_path)
                logger.info(f"Copied file: {src_path.name} -> {dst_path}")
            elif src_path.is_dir():
                if dst_path.exists():
                    shutil.rmtree(dst_path)
                shutil.copytree(src_path, dst_path)
                logger.info(f"Copied directory: {src_path.name} -> {dst_path}")
            else:
                logger.warning(f"Source path does not exist: {src_path}")
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to copy {src_path} to {dst_path}: {e}")
            return False

    def copy_example_data(self) -> Tuple[bool, List[str]]:
        """
        Copy example data to the project directory using BIDS structure.
        Ensures all necessary BIDS directories are created.

        Returns:
            Tuple of (success: bool, copied_subjects: List[str])
        """
        if not self.check_example_data_exists():
            return False, []

        if not self.is_new_project():
            logger.info("Project is not new, skipping example data copy")
            return False, []

        logger.info(f"Copying example data to new project: {self.project_dir}")

        # Initialize path manager and ensure core BIDS directories exist
        pm = get_path_manager()
        pm.project_dir = str(self.project_dir)

        core_dirs = [
            pm.ensure_dir("sourcedata"),
            pm.ensure_dir("ti_toolbox"),
            pm.ensure_dir("simnibs"),
            pm.ensure_dir("freesurfer"),
            pm.ensure_dir("ti_toolbox_config"),
        ]

        for dir_path in core_dirs:
            Path(dir_path).mkdir(parents=True, exist_ok=True)

        copied_subjects = []
        total_operations = 0
        successful_operations = 0

        # Process each subject's data according to the mapping
        for subject_key, file_mapping in self.data_mapping.items():
            subject_src_dir = self.example_data_dir / subject_key

            if not subject_src_dir.exists():
                logger.warning(f"Subject directory not found: {subject_src_dir}")
                continue

            logger.info(f"Processing subject: {subject_key}")
            subject_copied = False

            # Copy each file/directory for this subject
            for src_name, dst_relative_path in file_mapping.items():
                src_path = subject_src_dir / src_name
                dst_path = self.project_dir / dst_relative_path

                total_operations += 1
                if self.copy_file_or_directory(src_path, dst_path):
                    successful_operations += 1
                    subject_copied = True

            if subject_copied:
                # Extract subject ID from the mapping for tracking
                subject_id = list(file_mapping.values())[0].split("/")[
                    0
                ]  # Get subject ID from first mapping
                copied_subjects.append(subject_id)
                logger.info(f"Successfully copied example data for {subject_id}")

        # Copy the readme file to the project root for reference if it exists
        readme_src = self.example_data_dir / "readme.txt"
        if readme_src.exists():
            readme_dst = self.project_dir / "EXAMPLE_DATA_README.txt"
            total_operations += 1
            if self.copy_file_or_directory(readme_src, readme_dst):
                successful_operations += 1

        # Update project status to indicate example data was copied
        self._update_project_status(copied_subjects)

        success = successful_operations == total_operations
        if success:
            logger.info(
                f"Successfully copied example data for {len(copied_subjects)} subjects"
            )
        else:
            logger.warning(
                f"Copied {successful_operations}/{total_operations} items successfully"
            )

        return success, copied_subjects

    def _update_project_status(self, copied_subjects: List[str]) -> None:
        """
        Update the project status file to indicate example data was copied.

        Args:
            copied_subjects: List of subject IDs that were copied
        """
        try:
            import json
            from datetime import datetime

            # Create the status directory if it doesn't exist
            pm = get_path_manager()
            pm.project_dir = str(self.project_dir)
            status_dir = Path(pm.ensure_dir("ti_toolbox_info"))
            status_dir.mkdir(parents=True, exist_ok=True)

            status_file = status_dir / "project_status.json"

            # Load existing status or create new one
            if status_file.exists():
                with open(status_file, "r") as f:
                    status_data = json.load(f)
            else:
                status_data = {
                    "project_created": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "config_created": False,
                    "user_preferences": {"show_welcome": True},
                    "project_metadata": {
                        "name": self.project_dir.name,
                        "path": str(self.project_dir),
                        "version": "unknown",
                    },
                }

            # Update with example data information
            status_data["example_data_copied"] = True
            status_data["example_data_timestamp"] = datetime.now().isoformat()
            status_data["example_subjects"] = copied_subjects
            status_data["last_updated"] = datetime.now().isoformat()

            # Write updated status
            with open(status_file, "w") as f:
                json.dump(status_data, f, indent=2)

            logger.info(f"Updated project status with example data information")

        except Exception as e:
            logger.error(f"Failed to update project status: {e}")

    def create_bids_dataset_description(self) -> None:
        """
        Create BIDS dataset_description.json file for the project.
        Only creates if it doesn't already exist (loader.sh may have created it).
        """
        try:
            desc_file = self.project_dir / "dataset_description.json"

            # Skip if already exists
            if desc_file.exists():
                logger.info("BIDS dataset_description.json already exists, skipping")
                return

            dataset_desc = {
                "Name": f"TI-Toolbox Project: {self.project_dir.name}",
                "BIDSVersion": "1.10.0",
                "DatasetType": "raw",
                "Authors": ["TI-Toolbox User"],
                "Description": "TI-Toolbox project with example data (ernie and MNI152) for temporal interference analysis",
                "License": "CC BY-NC 4.0",
                "Acknowledgements": "Example data provided by SimNIBS team. Ernie subject includes T1/T2 anatomical NIfTI files. MNI152 template provided for reference.",
                "ReferencesAndLinks": [
                    "https://simnibs.github.io/",
                    "https://github.com/idossha/TI-Toolbox",
                ],
            }

            with open(desc_file, "w") as f:
                import json

                json.dump(dataset_desc, f, indent=2)

            logger.info("Created BIDS dataset_description.json")

        except Exception as e:
            logger.error(f"Failed to create dataset description: {e}")

    def create_bids_readme(self) -> None:
        """
        Create BIDS README file for the project.
        Only creates if it doesn't already exist (loader.sh may have created it).
        """
        try:
            readme_file = self.project_dir / "README"

            # Skip if already exists
            if readme_file.exists():
                logger.info("BIDS README already exists, skipping")
                return

            project_name = self.project_dir.name
            readme_content = f"""# {project_name}

This is a BIDS-compliant neuroimaging dataset generated by TI-Toolbox for temporal interference (TI) stimulation modeling and analysis.

## Overview

This project contains structural MRI data and derivatives for simulating and analyzing temporal interference electric field patterns in the brain.

## Example Data

This project includes example data for testing and demonstration:
- **sub-ernie**: Example subject with T1w and T2w anatomical scans (provided by SimNIBS)
- **sub-MNI152**: Standard MNI152 template for reference

## Dataset Structure

- `sourcedata/` - Raw DICOM source files
- `sub-*/` - Subject-level BIDS-formatted neuroimaging data (NIfTI files)
- `derivatives/` - Processed data and analysis results
  - `freesurfer/` - FreeSurfer anatomical segmentation and surface reconstructions
  - `SimNIBS/` - SimNIBS head models and electric field simulations
  - `ti-toolbox/` - TI-Toolbox simulation results and analyses
- `code/ti-toolbox/` - Configuration files for the toolbox

## Software

Data processing and simulations were performed using:
- **TI-Toolbox** - Temporal interference modeling pipeline
- **FreeSurfer** - Cortical reconstruction and volumetric segmentation
- **SimNIBS** - Finite element modeling for electric field simulations

## More Information

For more information about TI-Toolbox, visit:
- GitHub: https://github.com/idossha/TI-Toolbox
- Documentation: https://idossha.github.io/TI-toolbox/

## BIDS Compliance

This dataset follows the Brain Imaging Data Structure (BIDS) specification for organizing and describing neuroimaging data. For more information about BIDS, visit: https://bids.neuroimaging.io/
"""

            with open(readme_file, "w") as f:
                f.write(readme_content)

            logger.info("Created BIDS README file")

        except Exception as e:
            logger.error(f"Failed to create README: {e}")


def setup_example_data(toolbox_root: str, project_dir: str) -> Tuple[bool, List[str]]:
    """
    Main function to set up example data in a new project.

    Args:
        toolbox_root: Path to the TI-toolbox root directory
        project_dir: Path to the target project directory

    Returns:
        Tuple of (success: bool, copied_subjects: List[str])
    """
    try:
        manager = ExampleDataManager(toolbox_root, project_dir)
        success, subjects = manager.copy_example_data()

        if success and subjects:
            # Create BIDS dataset description and README
            manager.create_bids_dataset_description()
            manager.create_bids_readme()

        return success, subjects

    except Exception as e:
        logger.error(f"Error setting up example data: {e}")
        return False, []


if __name__ == "__main__":
    """Command-line interface for testing."""
    import sys

    if len(sys.argv) != 3:
        print("Usage: python example_data_manager.py <toolbox_root> <project_dir>")
        sys.exit(1)

    toolbox_root = sys.argv[1]
    project_dir = sys.argv[2]

    success, subjects = setup_example_data(toolbox_root, project_dir)

    if success:
        print(
            f"✓ Successfully set up example data with subjects: {', '.join(subjects)}"
        )
    else:
        print("✗ Failed to set up example data")
        sys.exit(1)
