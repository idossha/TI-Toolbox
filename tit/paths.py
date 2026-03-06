#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox Path Management
Centralized path management for the entire TI-Toolbox codebase.

Usage:
    from tit.paths import PathManager, get_path_manager

    pm = get_path_manager()
    subjects = pm.list_subjects()
    m2m_dir = pm.m2m("001")
    sim_dir = pm.simulation("001", "montage1")
"""

import os
import re
from typing import Optional, List

from . import constants as const


class PathManager:
    """Centralized BIDS-compliant path management for TI-Toolbox."""

    def __init__(self, project_dir: Optional[str] = None):
        self._project_dir: Optional[str] = None
        if project_dir:
            self.project_dir = project_dir

    # ------------------------------------------------------------------
    # Core properties
    # ------------------------------------------------------------------

    @property
    def project_dir(self) -> Optional[str]:
        """Get/set the project directory. Auto-detects from environment if unset."""
        if self._project_dir is None:
            project_dir = os.environ.get(const.ENV_PROJECT_DIR)
            if project_dir and os.path.isdir(project_dir):
                self._project_dir = project_dir
            if self._project_dir is None:
                project_dir_name = os.environ.get(const.ENV_PROJECT_DIR_NAME)
                if project_dir_name:
                    mnt_path = os.path.join(const.DOCKER_MOUNT_PREFIX, project_dir_name)
                    if os.path.isdir(mnt_path):
                        self._project_dir = mnt_path
        return self._project_dir

    @project_dir.setter
    def project_dir(self, path: str) -> None:
        if not os.path.isdir(path):
            raise ValueError(f"Project directory does not exist: {path}")
        self._project_dir = path

    @property
    def project_dir_name(self) -> Optional[str]:
        """Return the basename of project_dir."""
        if self._project_dir:
            return os.path.basename(self._project_dir)
        return os.environ.get(const.ENV_PROJECT_DIR_NAME)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _root(self) -> str:
        """Return project_dir or raise if unset."""
        root = self.project_dir
        if not root:
            raise RuntimeError("Project directory not set.")
        return root

    # ------------------------------------------------------------------
    # Project-level paths (zero args)
    # ------------------------------------------------------------------

    def derivatives(self) -> str:
        return os.path.join(self._root(), "derivatives")

    def sourcedata(self) -> str:
        return os.path.join(self._root(), "sourcedata")

    def simnibs(self) -> str:
        return os.path.join(self._root(), "derivatives", "SimNIBS")

    def freesurfer(self) -> str:
        return os.path.join(self._root(), "derivatives", "freesurfer")

    def ti_toolbox(self) -> str:
        return os.path.join(self._root(), "derivatives", "ti-toolbox")

    def config_dir(self) -> str:
        return os.path.join(self._root(), "code", "ti-toolbox", "config")

    def montage_config(self) -> str:
        return os.path.join(self.config_dir(), "montage_list.json")

    def project_status(self) -> str:
        return os.path.join(self.config_dir(), "project_status.json")

    def extensions_config(self) -> str:
        return os.path.join(self.config_dir(), "extensions.json")

    def reports(self) -> str:
        return os.path.join(self.ti_toolbox(), "reports")

    def stats_data(self) -> str:
        return os.path.join(self.ti_toolbox(), "stats", "data")

    def stats_output(self, analysis_type: str, analysis_name: str) -> str:
        return os.path.join(self.ti_toolbox(), "stats", analysis_type, analysis_name)

    def logs_group(self) -> str:
        return os.path.join(self.ti_toolbox(), "logs", "group_analysis")

    def qsiprep(self) -> str:
        return os.path.join(self._root(), "derivatives", "qsiprep")

    def qsirecon(self) -> str:
        return os.path.join(self._root(), "derivatives", "qsirecon")

    # ------------------------------------------------------------------
    # Subject-level paths (sid: str)
    # ------------------------------------------------------------------

    def sub(self, sid: str) -> str:
        return os.path.join(self._root(), "derivatives", "SimNIBS", f"sub-{sid}")

    def m2m(self, sid: str) -> str:
        return os.path.join(self.sub(sid), f"m2m_{sid}")

    def eeg_positions(self, sid: str) -> str:
        return os.path.join(self.m2m(sid), "eeg_positions")

    def rois(self, sid: str) -> str:
        return os.path.join(self.m2m(sid), "ROIs")

    def t1(self, sid: str) -> str:
        return os.path.join(self.m2m(sid), "T1.nii.gz")

    def tissue_labeling(self, sid: str) -> str:
        return os.path.join(self.m2m(sid), "segmentation", "Labeling.nii.gz")

    def leadfields(self, sid: str) -> str:
        return os.path.join(self.sub(sid), "leadfields")

    def simulations(self, sid: str) -> str:
        return os.path.join(self.sub(sid), "Simulations")

    def logs(self, sid: str) -> str:
        return os.path.join(self.ti_toolbox(), "logs", f"sub-{sid}")

    def tissue_analysis_output(self, sid: str) -> str:
        return os.path.join(self.ti_toolbox(), "tissue_analysis", f"sub-{sid}")

    def bids_subject(self, sid: str) -> str:
        return os.path.join(self._root(), f"sub-{sid}")

    def bids_anat(self, sid: str) -> str:
        return os.path.join(self.bids_subject(sid), "anat")

    def bids_dwi(self, sid: str) -> str:
        return os.path.join(self.bids_subject(sid), "dwi")

    def sourcedata_subject(self, sid: str) -> str:
        return os.path.join(self.sourcedata(), f"sub-{sid}")

    def freesurfer_subject(self, sid: str) -> str:
        return os.path.join(self.freesurfer(), f"sub-{sid}")

    def freesurfer_mri(self, sid: str) -> str:
        return os.path.join(self.freesurfer_subject(sid), "mri")

    def qsiprep_subject(self, sid: str) -> str:
        return os.path.join(self.qsiprep(), f"sub-{sid}")

    def qsirecon_subject(self, sid: str) -> str:
        return os.path.join(self.qsirecon(), f"sub-{sid}")

    def ex_search(self, sid: str) -> str:
        return os.path.join(self.sub(sid), "ex-search")

    def flex_search(self, sid: str) -> str:
        return os.path.join(self.sub(sid), "flex-search")

    # ------------------------------------------------------------------
    # Subject + simulation paths
    # ------------------------------------------------------------------

    def simulation(self, sid: str, sim: str) -> str:
        return os.path.join(self.simulations(sid), sim)

    def ti_mesh(self, sid: str, sim: str) -> str:
        return os.path.join(self.simulation(sid, sim), "TI", "mesh", f"{sim}_TI.msh")

    def ti_mesh_dir(self, sid: str, sim: str) -> str:
        return os.path.join(self.simulation(sid, sim), "TI", "mesh")

    def ti_central_surface(self, sid: str, sim: str) -> str:
        return os.path.join(
            self.simulation(sid, sim), "TI", "mesh", "surfaces", f"{sim}_TI_central.msh"
        )

    def mti_mesh_dir(self, sid: str, sim: str) -> str:
        return os.path.join(self.simulation(sid, sim), "mTI", "mesh")

    def analysis_dir(self, sid: str, sim: str, space: str) -> str:
        folder = "Mesh" if space.lower() == "mesh" else "Voxel"
        return os.path.join(self.simulation(sid, sim), "Analyses", folder)

    # ------------------------------------------------------------------
    # Subject + run/name paths
    # ------------------------------------------------------------------

    def sourcedata_dicom(self, sid: str, modality: str) -> str:
        return os.path.join(self.sourcedata_subject(sid), modality, "dicom")

    def ex_search_run(self, sid: str, run: str) -> str:
        return os.path.join(self.ex_search(sid), run)

    def flex_search_run(self, sid: str, name: str) -> str:
        return os.path.join(self.flex_search(sid), name)

    def flex_electrode_positions(self, sid: str, name: str) -> str:
        return os.path.join(self.flex_search_run(sid, name), "electrode_positions.json")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def ensure(self, path: str) -> str:
        """Create directory (with parents) and return path."""
        os.makedirs(path, exist_ok=True)
        return path

    # ------------------------------------------------------------------
    # Listing helpers
    # ------------------------------------------------------------------

    def list_subjects(self) -> List[str]:
        """List subject IDs (without 'sub-' prefix) that have an m2m folder."""
        simnibs_dir = self.simnibs() if self.project_dir else None
        if not simnibs_dir or not os.path.isdir(simnibs_dir):
            return []

        subjects = []
        for item in os.listdir(simnibs_dir):
            if not item.startswith(const.PREFIX_SUBJECT):
                continue
            sid = item.replace(const.PREFIX_SUBJECT, "", 1)
            if os.path.isdir(self.m2m(sid)):
                subjects.append(sid)

        subjects.sort(
            key=lambda x: [
                int(c) if c.isdigit() else c.lower() for c in re.split("([0-9]+)", x)
            ]
        )
        return subjects

    def list_all_subjects(self) -> List[str]:
        """List all subject IDs found anywhere in the project.

        Merges subjects from:
        1. ``list_subjects()`` (those with m2m directories)
        2. ``sub-*`` directories under the project root
        3. ``sub-*`` directories under derivatives/SimNIBS

        Returns:
            Sorted, deduplicated list of subject IDs (without 'sub-' prefix).
        """
        all_sids: set[str] = set(self.list_subjects())
        root = self._root()

        # Scan project root for sub-* dirs
        if os.path.isdir(root):
            for entry in os.scandir(root):
                if entry.is_dir() and entry.name.startswith(const.PREFIX_SUBJECT):
                    all_sids.add(entry.name.removeprefix(const.PREFIX_SUBJECT))

        # Scan SimNIBS derivatives for sub-* dirs without m2m
        simnibs_dir = self.simnibs()
        if os.path.isdir(simnibs_dir):
            for entry in os.scandir(simnibs_dir):
                if entry.is_dir() and entry.name.startswith(const.PREFIX_SUBJECT):
                    all_sids.add(entry.name.removeprefix(const.PREFIX_SUBJECT))

        return sorted(
            all_sids,
            key=lambda x: [
                int(c) if c.isdigit() else c.lower() for c in re.split("([0-9]+)", x)
            ],
        )

    def list_simulations(self, sid: str) -> List[str]:
        """List simulation folder names for a subject."""
        sim_root = self.simulations(sid) if self.project_dir else None
        if not sim_root or not os.path.isdir(sim_root):
            return []

        simulations: List[str] = []
        try:
            with os.scandir(sim_root) as it:
                for entry in it:
                    if entry.is_dir() and not entry.name.startswith("."):
                        simulations.append(entry.name)
        except OSError:
            return []
        simulations.sort()
        return simulations

    def list_eeg_caps(self, sid: str) -> List[str]:
        """List EEG cap CSV files for a subject."""
        eeg_pos_dir = self.eeg_positions(sid) if self.project_dir else None
        if not eeg_pos_dir or not os.path.isdir(eeg_pos_dir):
            return []

        caps = [
            f
            for f in os.listdir(eeg_pos_dir)
            if f.endswith(const.EXT_CSV) and not f.startswith(".")
        ]
        caps.sort()
        return caps

    def list_flex_search_runs(self, sid: str) -> List[str]:
        """List flex-search run folders that contain electrode_positions.json."""
        root = self.flex_search(sid) if self.project_dir else None
        if not root or not os.path.isdir(root):
            return []

        out: List[str] = []
        fname = "electrode_positions.json"
        try:
            with os.scandir(root) as it:
                for entry in it:
                    if not entry.is_dir() or entry.name.startswith("."):
                        continue
                    if os.path.isfile(os.path.join(entry.path, fname)):
                        out.append(entry.name)
        except OSError:
            return []
        out.sort()
        return out

    # ------------------------------------------------------------------
    # Analysis naming helpers
    # ------------------------------------------------------------------

    @staticmethod
    def spherical_analysis_name(
        x: float, y: float, z: float, radius: float, coordinate_space: str
    ) -> str:
        """Return folder name for a spherical analysis."""
        coord_space_suffix = (
            "_MNI" if str(coordinate_space).upper() == "MNI" else "_subject"
        )
        return f"sphere_x{x:.2f}_y{y:.2f}_z{z:.2f}_r{float(radius)}{coord_space_suffix}"

    @staticmethod
    def _atlas_name_clean(atlas_name_or_path: str) -> str:
        s = str(atlas_name_or_path or "unknown_atlas")
        s = os.path.basename(s)
        for ext in (".nii.gz", ".nii", ".mgz"):
            if s.endswith(ext):
                s = s[: -len(ext)]
                break
        return s.replace("+", "_").replace(".", "_")

    @classmethod
    def cortical_analysis_name(
        cls,
        *,
        whole_head: bool,
        region: Optional[str],
        atlas_name: Optional[str] = None,
        atlas_path: Optional[str] = None,
    ) -> str:
        """Return folder name for a cortical analysis."""
        atlas_clean = cls._atlas_name_clean(atlas_name or atlas_path or "unknown_atlas")
        if whole_head:
            return f"whole_head_{atlas_clean}"
        region_val = str(region or "").strip()
        if not region_val:
            raise ValueError(
                "region is required for cortical analysis unless whole_head=True"
            )
        return f"region_{region_val}_{atlas_clean}"

    def analysis_output_dir(
        self,
        *,
        sid: str,
        sim: str,
        space: str,
        analysis_type: str,
        coordinates=None,
        radius=None,
        coordinate_space: str = "subject",
        whole_head: bool = False,
        region: Optional[str] = None,
        atlas_name: Optional[str] = None,
        atlas_path: Optional[str] = None,
    ) -> str:
        """Return analysis output directory path (does not create it)."""
        base = self.analysis_dir(sid, sim, space)
        at = str(analysis_type).lower()
        if at == "spherical":
            if not coordinates or len(coordinates) != 3 or radius is None:
                raise ValueError(
                    "coordinates(3) and radius required for spherical analysis"
                )
            name = self.spherical_analysis_name(
                float(coordinates[0]),
                float(coordinates[1]),
                float(coordinates[2]),
                float(radius),
                coordinate_space,
            )
        else:
            name = self.cortical_analysis_name(
                whole_head=bool(whole_head),
                region=region,
                atlas_name=atlas_name,
                atlas_path=atlas_path,
            )
        return os.path.join(base, name)


# ============================================================================
# SINGLETON
# ============================================================================

_path_manager_instance: Optional[PathManager] = None


def get_path_manager(project_dir: Optional[str] = None) -> PathManager:
    """Return the global PathManager singleton."""
    global _path_manager_instance
    if _path_manager_instance is None:
        _path_manager_instance = PathManager()
    if project_dir is not None:
        _path_manager_instance.project_dir = project_dir
    return _path_manager_instance


def reset_path_manager() -> None:
    """Reset the global PathManager singleton (useful for testing)."""
    global _path_manager_instance
    _path_manager_instance = None
