#!/usr/bin/env simnibs_python
"""
Post-processing utilities for TI simulations.

This module handles all post-simulation processing including:
- TI/mTI field calculation
- Field extraction (GM/WM mesh creation)
- NIfTI transformation
- T1 to MNI conversion
- File organization
"""

import glob
import os
import shutil
import subprocess
import numpy as np
from copy import deepcopy
from typing import List, Optional

from simnibs import mesh_io
from simnibs.utils import TI_utils as TI

from tit.sim.config import SimulationMode, MontageConfig
from tit.core.calc import get_TI_vectors


class PostProcessor:
    """Post-processor for TI simulation results."""

    def __init__(self, subject_id: str, conductivity_type: str, m2m_dir: str, logger):
        """
        Initialize post-processor.

        Args:
            subject_id: Subject identifier
            conductivity_type: Conductivity type string
            m2m_dir: Path to m2m directory
            logger: Logger instance
        """
        self.subject_id = subject_id
        self.conductivity_type = conductivity_type
        self.m2m_dir = m2m_dir
        self.logger = logger

        # Path to tools directory
        self.tools_dir = os.path.join(os.path.dirname(__file__), "..", "tools")

    def process_ti_results(
        self,
        hf_dir: str,
        output_dir: str,
        nifti_dir: str,
        surface_overlays_dir: str,
        hf_mesh_dir: str,
        hf_nifti_dir: str,
        hf_analysis_dir: str,
        documentation_dir: str,
        montage_name: str,
    ) -> str:
        """
        Process 2-pair TI simulation results with full pipeline.

        Args:
            hf_dir: High-frequency output directory (SimNIBS writes here)
            output_dir: TI mesh output directory
            nifti_dir: TI NIfTI output directory
            surface_overlays_dir: Surface overlays output directory
            hf_mesh_dir: High-frequency mesh output directory
            hf_nifti_dir: High-frequency NIfTI output directory
            hf_analysis_dir: High-frequency analysis output directory
            documentation_dir: Documentation output directory
            montage_name: Montage name

        Returns:
            Path to output TI mesh file
        """
        self.logger.info(f"Processing TI results for {montage_name}")

        # Step 1: Calculate TI field
        ti_path = self._calculate_ti_field(hf_dir, output_dir, montage_name)

        # Step 2: Calculate TI normal (cortical surface)
        self._process_ti_normal(hf_dir, output_dir, montage_name)

        # Step 3: Extract GM/WM fields
        self.logger.info("Field extraction: Started")
        self._extract_fields(ti_path, output_dir, f"{montage_name}_TI")
        self.logger.info("Field extraction: ✓ Complete")

        # Step 4: Convert to NIfTI
        self.logger.info("NIfTI transformation: Started")
        self._transform_to_nifti(output_dir, nifti_dir)
        self.logger.info("NIfTI transformation: ✓ Complete")

        # Step 5: Organize files
        self._organize_ti_files(
            hf_dir=hf_dir,
            hf_mesh_dir=hf_mesh_dir,
            hf_nifti_dir=hf_nifti_dir,
            hf_analysis_dir=hf_analysis_dir,
            surface_overlays_dir=surface_overlays_dir,
            documentation_dir=documentation_dir,
        )

        # Step 6: Convert T1 to MNI space
        self._convert_t1_to_mni()

        self.logger.info(f"Saved TI mesh: {ti_path}")
        return ti_path

    def process_mti_results(
        self,
        hf_dir: str,
        ti_dir: str,
        mti_dir: str,
        mti_nifti_dir: str,
        hf_mesh_dir: str,
        hf_analysis_dir: str,
        documentation_dir: str,
        montage_name: str,
    ) -> str:
        """
        Process 4-pair mTI simulation results with full pipeline.

        Args:
            hf_dir: High-frequency output directory
            ti_dir: TI intermediate output directory
            mti_dir: mTI final output directory
            mti_nifti_dir: mTI NIfTI output directory
            hf_mesh_dir: High-frequency mesh output directory
            hf_analysis_dir: High-frequency analysis output directory
            documentation_dir: Documentation output directory
            montage_name: Montage name

        Returns:
            Path to output mTI mesh file
        """
        self.logger.info(f"Processing mTI results for {montage_name}")

        # Step 1: Load 4 HF meshes
        hf_meshes = []
        for i in range(1, 5):
            mesh_file = os.path.join(
                hf_dir, f"{self.subject_id}_TDCS_{i}_{self.conductivity_type}.msh"
            )

            if not os.path.exists(mesh_file):
                raise FileNotFoundError(f"Mesh file not found: {mesh_file}")

            m = mesh_io.read_msh(mesh_file)
            tags_keep = np.hstack((np.arange(1, 100), np.arange(1001, 1100)))
            m = m.crop_mesh(tags=tags_keep)
            hf_meshes.append(m)

        # Step 2: Calculate TI pairs (AB and CD)
        ti_ab_vectors = get_TI_vectors(
            hf_meshes[0].field["E"].value, hf_meshes[1].field["E"].value
        )
        ti_cd_vectors = get_TI_vectors(
            hf_meshes[2].field["E"].value, hf_meshes[3].field["E"].value
        )

        # Step 3: Save intermediate TI meshes
        self._save_ti_intermediate(
            hf_meshes[0], ti_ab_vectors, ti_dir, f"{montage_name}_TI_AB.msh"
        )
        self._save_ti_intermediate(
            hf_meshes[0], ti_cd_vectors, ti_dir, f"{montage_name}_TI_CD.msh"
        )

        # Step 4: Calculate and save final mTI
        mti_field = TI.get_maxTI(ti_ab_vectors, ti_cd_vectors)
        mout = deepcopy(hf_meshes[0])
        mout.elmdata = []
        mout.add_element_field(mti_field, "TI_Max")

        mti_path = os.path.join(mti_dir, f"{montage_name}_mTI.msh")
        mesh_io.write_msh(mout, mti_path)
        mout.view(visible_tags=[1002, 1006], visible_fields="TI_Max").write_opt(
            mti_path
        )

        # Step 5: Extract GM/WM fields for mTI
        self.logger.info("Field extraction: Started")
        self._extract_fields(mti_path, mti_dir, f"{montage_name}_mTI")
        self.logger.info("Field extraction: ✓ Complete")

        # Step 6: Extract GM/WM fields for intermediate TI meshes
        ti_ab_path = os.path.join(ti_dir, f"{montage_name}_TI_AB.msh")
        ti_cd_path = os.path.join(ti_dir, f"{montage_name}_TI_CD.msh")
        if os.path.exists(ti_ab_path):
            self._extract_fields(ti_ab_path, ti_dir, f"{montage_name}_TI_AB")
        if os.path.exists(ti_cd_path):
            self._extract_fields(ti_cd_path, ti_dir, f"{montage_name}_TI_CD")

        # Step 7: Convert mTI meshes to NIfTI
        self.logger.info("NIfTI transformation: Started")
        self._transform_to_nifti(mti_dir, mti_nifti_dir)
        self.logger.info("NIfTI transformation: ✓ Complete")

        # Step 8: Organize HF files with mTI naming
        self._organize_mti_files(
            hf_dir=hf_dir,
            hf_mesh_dir=hf_mesh_dir,
            hf_analysis_dir=hf_analysis_dir,
            documentation_dir=documentation_dir,
        )

        # Step 9: Convert T1 to MNI space
        self._convert_t1_to_mni()

        self.logger.info(f"Saved mTI mesh: {mti_path}")
        return mti_path

    def _calculate_ti_field(
        self, hf_dir: str, output_dir: str, montage_name: str
    ) -> str:
        """
        Calculate TI max field from HF simulation results.

        Args:
            hf_dir: High-frequency output directory
            output_dir: Output directory for TI mesh
            montage_name: Montage name

        Returns:
            Path to TI mesh file
        """
        # Load mesh files
        m1_file = os.path.join(
            hf_dir, f"{self.subject_id}_TDCS_1_{self.conductivity_type}.msh"
        )
        m2_file = os.path.join(
            hf_dir, f"{self.subject_id}_TDCS_2_{self.conductivity_type}.msh"
        )

        m1 = mesh_io.read_msh(m1_file)
        m2 = mesh_io.read_msh(m2_file)

        # Crop to brain tissues
        tags_keep = np.hstack((np.arange(1, 100), np.arange(1001, 1100)))
        m1 = m1.crop_mesh(tags=tags_keep)
        m2 = m2.crop_mesh(tags=tags_keep)

        # Calculate TI max
        TImax = TI.get_maxTI(m1.field["E"].value, m2.field["E"].value)

        # Save TI max mesh
        mout = deepcopy(m1)
        mout.elmdata = []
        mout.add_element_field(TImax, "TI_max")

        ti_path = os.path.join(output_dir, f"{montage_name}_TI.msh")
        mesh_io.write_msh(mout, ti_path)
        mout.view(visible_tags=[1002, 1006], visible_fields=["TI_max"]).write_opt(
            ti_path
        )

        return ti_path

    def _process_ti_normal(self, hf_dir: str, output_dir: str, montage_name: str):
        """
        Calculate and save TI normal component on cortical surface.

        Args:
            hf_dir: High-frequency output directory
            output_dir: TI output directory
            montage_name: Montage name
        """
        overlays_dir = os.path.join(hf_dir, "subject_overlays")
        central_1 = os.path.join(
            overlays_dir,
            f"{self.subject_id}_TDCS_1_{self.conductivity_type}_central.msh",
        )
        central_2 = os.path.join(
            overlays_dir,
            f"{self.subject_id}_TDCS_2_{self.conductivity_type}_central.msh",
        )

        if not (os.path.exists(central_1) and os.path.exists(central_2)):
            self.logger.debug(
                "Central surface meshes not found, skipping TI_normal calculation"
            )
            return

        cm1 = mesh_io.read_msh(central_1)
        cm2 = mesh_io.read_msh(central_2)

        # Get E-field vectors
        if hasattr(cm1, "field") and "E" in cm1.field:
            ef1_c = cm1.field["E"]
            ef2_c = cm2.field["E"]
        else:
            # Reconstruct from E_normal and normals
            normals = cm1.nodes_normals().value
            ef1_c = type(
                "", (), {"value": cm1.field["E_normal"].value.reshape(-1, 1) * normals}
            )()
            ef2_c = type(
                "", (), {"value": cm2.field["E_normal"].value.reshape(-1, 1) * normals}
            )()

        # Calculate TI normal
        TI_normal = TI.get_dirTI(ef1_c.value, ef2_c.value, cm1.nodes_normals().value)

        # Save mesh
        mout_c = deepcopy(cm1)
        mout_c.nodedata = []
        mout_c.add_node_field(TI_normal, "TI_normal")

        normal_path = os.path.join(output_dir, f"{montage_name}_normal.msh")
        mesh_io.write_msh(mout_c, normal_path)
        mout_c.view(visible_fields=["TI_normal"]).write_opt(normal_path)

        self.logger.debug(f"Saved TI_normal mesh: {normal_path}")

    def _save_ti_intermediate(
        self, base_mesh, ti_vectors, output_dir: str, filename: str
    ):
        """
        Save intermediate TI vector field mesh.

        Args:
            base_mesh: Base mesh to copy structure from
            ti_vectors: TI vector field data
            output_dir: Output directory
            filename: Output filename
        """
        mout = deepcopy(base_mesh)
        mout.elmdata = []
        mout.add_element_field(ti_vectors, "TI_vectors")

        output_path = os.path.join(output_dir, filename)
        mesh_io.write_msh(mout, output_path)
        mout.view(visible_tags=[1002, 1006], visible_fields=["TI_vectors"]).write_opt(
            output_path
        )

        self.logger.debug(f"Saved intermediate TI mesh: {output_path}")

    def _extract_fields(self, input_mesh: str, output_dir: str, base_name: str):
        """
        Extract grey matter and white matter fields from mesh.

        Args:
            input_mesh: Path to input mesh file
            output_dir: Output directory for extracted meshes
            base_name: Base name for output files
        """
        self.logger.debug(
            f"Extracting GM/WM fields from {os.path.basename(input_mesh)}"
        )

        gm_output = os.path.join(output_dir, f"grey_{base_name}.msh")
        wm_output = os.path.join(output_dir, f"white_{base_name}.msh")

        # Use field_extract.py tool
        field_extract_script = os.path.join(self.tools_dir, "field_extract.py")

        if os.path.exists(field_extract_script):
            try:
                result = subprocess.run(
                    [
                        "simnibs_python",
                        field_extract_script,
                        input_mesh,
                        "--gm_output_file",
                        gm_output,
                        "--wm_output_file",
                        wm_output,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode != 0:
                    self.logger.warning(f"Field extraction warning: {result.stderr}")
            except subprocess.TimeoutExpired:
                self.logger.warning("Field extraction timed out")
            except Exception as e:
                self.logger.warning(f"Field extraction failed: {e}")
        else:
            # Fallback: Direct extraction using simnibs
            try:
                full_mesh = mesh_io.read_msh(input_mesh)

                # Extract grey matter mesh (tag #2)
                gm_mesh = full_mesh.crop_mesh(tags=[2])
                mesh_io.write_msh(gm_mesh, gm_output)

                # Extract white matter mesh (tag #1)
                wm_mesh = full_mesh.crop_mesh(tags=[1])
                mesh_io.write_msh(wm_mesh, wm_output)

                self.logger.debug(f"Extracted GM/WM meshes to {output_dir}")
            except Exception as e:
                self.logger.warning(f"Direct field extraction failed: {e}")

    def _transform_to_nifti(self, mesh_dir: str, output_dir: str):
        """
        Transform mesh files to NIfTI format.

        Args:
            mesh_dir: Directory containing mesh files
            output_dir: Output directory for NIfTI files
        """
        self.logger.debug(f"Converting meshes to NIfTI: {mesh_dir} -> {output_dir}")

        mesh2nii_script = os.path.join(self.tools_dir, "mesh2nii_loop.sh")

        if os.path.exists(mesh2nii_script):
            try:
                result = subprocess.run(
                    [
                        "bash",
                        mesh2nii_script,
                        self.subject_id,
                        self.m2m_dir,
                        mesh_dir,
                        output_dir,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                if result.returncode != 0:
                    self.logger.warning(f"NIfTI conversion warning: {result.stderr}")
            except subprocess.TimeoutExpired:
                self.logger.warning("NIfTI conversion timed out")
            except Exception as e:
                self.logger.warning(f"NIfTI conversion failed: {e}")
        else:
            # Fallback: Direct conversion using SimNIBS tools
            self._direct_nifti_conversion(mesh_dir, output_dir)

    def _direct_nifti_conversion(self, mesh_dir: str, output_dir: str):
        """
        Direct NIfTI conversion using SimNIBS tools.

        Args:
            mesh_dir: Directory containing mesh files
            output_dir: Output directory for NIfTI files
        """
        mesh_files = glob.glob(os.path.join(mesh_dir, "*.msh"))

        for mesh_file in mesh_files:
            base_name = os.path.basename(mesh_file).replace(".msh", "")

            # Skip surface meshes (e.g., *_normal.msh)
            if "normal" in base_name:
                self.logger.debug(f"Skipping surface mesh: {base_name}")
                continue

            try:
                # Convert to MNI space
                mni_output = os.path.join(output_dir, f"{base_name}_MNI.nii.gz")
                result = subprocess.run(
                    [
                        "subject2mni",
                        "-i",
                        mesh_file,
                        "-m",
                        self.m2m_dir,
                        "-o",
                        mni_output,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

                # Convert to subject space
                subject_output = os.path.join(output_dir, f"{base_name}_subject.nii.gz")
                result = subprocess.run(
                    ["msh2nii", mesh_file, self.m2m_dir, subject_output],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )

            except Exception as e:
                self.logger.warning(f"NIfTI conversion failed for {mesh_file}: {e}")

    def _convert_t1_to_mni(self):
        """Convert T1 to MNI space."""
        t1_file = os.path.join(self.m2m_dir, "T1.nii.gz")
        output_file = os.path.join(self.m2m_dir, f"T1_{self.subject_id}")

        # Check if already converted
        if os.path.exists(f"{output_file}_MNI.nii.gz"):
            self.logger.debug("T1 already converted to MNI space")
            return

        if not os.path.exists(t1_file):
            self.logger.debug("T1 file not found, skipping MNI conversion")
            return

        self.logger.debug("Converting T1 to MNI space")

        try:
            result = subprocess.run(
                ["subject2mni", "-i", t1_file, "-m", self.m2m_dir, "-o", output_file],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                self.logger.warning(f"T1 to MNI conversion warning: {result.stderr}")
        except Exception as e:
            self.logger.warning(f"T1 to MNI conversion failed: {e}")

    def _organize_ti_files(
        self,
        hf_dir: str,
        hf_mesh_dir: str,
        hf_nifti_dir: str,
        hf_analysis_dir: str,
        surface_overlays_dir: str,
        documentation_dir: str,
    ):
        """
        Organize TI simulation output files into proper directories.

        Args:
            hf_dir: Source high-frequency directory
            hf_mesh_dir: Destination for HF mesh files
            hf_nifti_dir: Destination for HF NIfTI files
            hf_analysis_dir: Destination for analysis files
            surface_overlays_dir: Destination for surface overlay files
            documentation_dir: Destination for documentation files
        """
        self.logger.debug("Organizing TI output files")

        # Move high frequency mesh files
        for pattern in ["TDCS_1", "TDCS_2"]:
            for ext in [".geo", "scalar.msh", "scalar.msh.opt"]:
                for file in glob.glob(os.path.join(hf_dir, f"*{pattern}*{ext}")):
                    dest = os.path.join(hf_mesh_dir, os.path.basename(file))
                    self._safe_move(file, dest)

        # Handle subject_volumes directory
        subject_volumes_dir = os.path.join(hf_dir, "subject_volumes")
        if os.path.isdir(subject_volumes_dir):
            for file in os.listdir(subject_volumes_dir):
                src = os.path.join(subject_volumes_dir, file)
                dest = os.path.join(hf_nifti_dir, file)
                self._safe_move(src, dest)
            self._safe_rmdir(subject_volumes_dir)

        # Handle subject_overlays directory
        subject_overlays_dir = os.path.join(hf_dir, "subject_overlays")
        if os.path.isdir(subject_overlays_dir):
            for file in os.listdir(subject_overlays_dir):
                src = os.path.join(subject_overlays_dir, file)
                dest = os.path.join(surface_overlays_dir, file)
                self._safe_move(src, dest)
            self._safe_rmdir(subject_overlays_dir)

        # Move fields_summary.txt
        fields_summary = os.path.join(hf_dir, "fields_summary.txt")
        if os.path.exists(fields_summary):
            self._safe_move(
                fields_summary, os.path.join(hf_analysis_dir, "fields_summary.txt")
            )

        # Move log and mat files to documentation
        for pattern in ["simnibs_simulation_*.log", "simnibs_simulation_*.mat"]:
            for file in glob.glob(os.path.join(hf_dir, pattern)):
                dest = os.path.join(documentation_dir, os.path.basename(file))
                self._safe_move(file, dest)

    def _organize_mti_files(
        self,
        hf_dir: str,
        hf_mesh_dir: str,
        hf_analysis_dir: str,
        documentation_dir: str,
    ):
        """
        Organize mTI simulation output files with renamed HF files.

        Args:
            hf_dir: Source high-frequency directory
            hf_mesh_dir: Destination for HF mesh files
            hf_analysis_dir: Destination for analysis files
            documentation_dir: Destination for documentation files
        """
        self.logger.debug("Organizing mTI output files")

        # Rename and move HF files (1,2,3,4 -> A,B,C,D)
        letter_map = {1: "A", 2: "B", 3: "C", 4: "D"}

        for i, letter in letter_map.items():
            for ext in [".geo", "scalar.msh", "scalar.msh.opt"]:
                pattern = f"*TDCS_{i}*{ext}"
                for file in glob.glob(os.path.join(hf_dir, pattern)):
                    filename = os.path.basename(file)
                    new_filename = filename.replace(f"TDCS_{i}", f"TDCS_{letter}")
                    dest = os.path.join(hf_mesh_dir, new_filename)
                    self._safe_move(file, dest)

        # Clean up subject_volumes directory (not needed for mTI)
        subject_volumes_dir = os.path.join(hf_dir, "subject_volumes")
        if os.path.isdir(subject_volumes_dir):
            shutil.rmtree(subject_volumes_dir, ignore_errors=True)

        # Move fields_summary.txt
        fields_summary = os.path.join(hf_dir, "fields_summary.txt")
        if os.path.exists(fields_summary):
            self._safe_move(
                fields_summary, os.path.join(hf_analysis_dir, "fields_summary.txt")
            )

        # Move log and mat files to documentation
        for pattern in ["simnibs_simulation_*.log", "simnibs_simulation_*.mat"]:
            for file in glob.glob(os.path.join(hf_dir, pattern)):
                dest = os.path.join(documentation_dir, os.path.basename(file))
                self._safe_move(file, dest)

    def _safe_move(self, src: str, dest: str):
        """
        Safely move a file, logging any errors.

        Args:
            src: Source file path
            dest: Destination file path
        """
        try:
            if os.path.exists(src):
                shutil.move(src, dest)
                self.logger.debug(
                    f"Moved {os.path.basename(src)} to {os.path.dirname(dest)}"
                )
        except Exception as e:
            self.logger.warning(f"Failed to move {src} to {dest}: {e}")

    def _safe_rmdir(self, path: str):
        """
        Safely remove an empty directory.

        Args:
            path: Directory path
        """
        try:
            if os.path.isdir(path) and not os.listdir(path):
                os.rmdir(path)
        except Exception as e:
            self.logger.warning(f"Failed to remove directory {path}: {e}")
