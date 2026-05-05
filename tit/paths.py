#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""BIDS-compliant path management for TI-Toolbox.

Provides a singleton :class:`PathManager` that resolves all file and
directory paths within a BIDS-structured TI-Toolbox project.  Paths cover
subject anatomical data, SimNIBS derivatives, FreeSurfer outputs, analysis
results, and optimization runs.

Public API
----------
PathManager
    Central path resolver — instantiated as a singleton via
    :func:`get_path_manager`.
get_path_manager
    Return (and optionally initialise) the global ``PathManager`` singleton.
reset_path_manager
    Destroy the singleton so the next call creates a fresh instance.

Examples
--------
>>> from tit.paths import get_path_manager
>>> pm = get_path_manager("/data/project")
>>> pm.list_simnibs_subjects()
['001', '002']
>>> pm.m2m("001")
'/data/project/derivatives/SimNIBS/sub-001/m2m_001'

See Also
--------
tit.constants : Project-wide constants used for directory/file names.
"""

import hashlib
import os
import re

from . import constants as const


class PathManager:
    """BIDS-compliant path resolution for TI-Toolbox projects.

    Provides methods to resolve file and directory paths within a
    BIDS-structured project, including subject anatomical data, SimNIBS
    derivatives, FreeSurfer outputs, optimization runs, and analysis results.

    The project directory can be set explicitly or auto-detected from the
    ``PROJECT_DIR`` / ``PROJECT_DIR_NAME`` environment variables (useful
    inside Docker containers).

    Parameters
    ----------
    project_dir : str or None, optional
        Root directory of the BIDS project.  If *None*, the directory is
        auto-detected from environment variables on first access.

    Attributes
    ----------
    project_dir : str or None
        Resolved project root, or *None* if not yet set / detected.
    project_dir_name : str or None
        Basename of :attr:`project_dir`.

    See Also
    --------
    get_path_manager : Obtain the global singleton instance.
    reset_path_manager : Destroy the singleton for testing or re-init.
    """

    def __init__(self, project_dir: str | None = None):
        self._project_dir: str | None = None
        if project_dir:
            self.project_dir = project_dir

    # ------------------------------------------------------------------
    # Core properties
    # ------------------------------------------------------------------

    @property
    def project_dir(self) -> str | None:
        """Project root directory, auto-detected from environment if unset."""
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
    def project_dir_name(self) -> str | None:
        """Basename of :attr:`project_dir`, or the ``PROJECT_DIR_NAME`` env var."""
        if self._project_dir:
            return os.path.basename(self._project_dir)
        return os.environ.get(const.ENV_PROJECT_DIR_NAME)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _root(self) -> str:
        """Return project_dir or raise if unset."""
        root = self.project_dir
        if root is None:
            raise RuntimeError("Project directory not set")
        return root

    # ------------------------------------------------------------------
    # Project-level paths (zero args)
    # ------------------------------------------------------------------

    def derivatives(self) -> str:
        """Path to ``<project>/derivatives/``."""
        return os.path.join(self._root(), "derivatives")

    def sourcedata(self) -> str:
        """Path to ``<project>/sourcedata/``."""
        return os.path.join(self._root(), "sourcedata")

    def simnibs(self) -> str:
        """Path to ``<project>/derivatives/SimNIBS/``."""
        return os.path.join(self._root(), "derivatives", "SimNIBS")

    def freesurfer(self) -> str:
        """Path to ``<project>/derivatives/freesurfer/``."""
        return os.path.join(self._root(), "derivatives", "freesurfer")

    def ti_toolbox(self) -> str:
        """Path to ``<project>/derivatives/ti-toolbox/``."""
        return os.path.join(self._root(), "derivatives", "ti-toolbox")

    def config_dir(self) -> str:
        """Path to ``<project>/code/ti-toolbox/config/``."""
        return os.path.join(self._root(), "code", "ti-toolbox", "config")

    def montage_config(self) -> str:
        """Path to the ``montage_list.json`` configuration file."""
        return os.path.join(self.config_dir(), "montage_list.json")

    def project_status(self) -> str:
        """Path to the ``project_status.json`` file."""
        return os.path.join(self.config_dir(), "project_status.json")

    def extensions_config(self) -> str:
        """Path to the ``extensions.json`` configuration file.

        Uses the user-level config directory so that extension
        preferences persist across projects and container restarts.
        """
        return os.path.join(self.user_config_dir(), "extensions.json")

    @staticmethod
    def user_config_dir() -> str:
        """Path to the user-level config directory.

        Returns the directory that persists across projects and container
        restarts.  Inside Docker this is ``/root/.config/ti-toolbox``
        (mounted from the host by the Electron launcher).  Outside Docker
        the platform-native config directory is used:

        - **macOS**: ``~/.config/ti-toolbox``
        - **Linux**: ``$XDG_CONFIG_HOME/ti-toolbox`` (default ``~/.config``)
        - **Windows**: ``%APPDATA%/ti-toolbox``

        The directory is created if it does not exist.

        Returns
        -------
        str
            Absolute path to the user config directory.
        """
        import platform as _platform

        def _usable_dir(path: str | None) -> str | None:
            if not path:
                return None
            try:
                os.makedirs(path, exist_ok=True)
            except OSError:
                return None
            return path if os.path.isdir(path) else None

        # Inside Docker the Electron launcher mounts the host config here.
        # Prefer the in-container mount when present; TIT_USER_CONFIG is a
        # host-side path used by docker-compose and may not exist in-container.
        docker_path = _usable_dir(const.USER_CONFIG_CONTAINER_PATH)
        if docker_path:
            return docker_path

        # Explicit override for non-standard/container-less launches.
        env_path = _usable_dir(os.environ.get("TIT_USER_CONFIG"))
        if env_path:
            return env_path

        # Outside Docker: platform-native paths
        system = _platform.system()
        if system == "Darwin":
            # Use ~/.config (NOT ~/Library/Application Support which is
            # Electron's userData dir).  Matches env.js getUserConfigDir().
            base = os.path.join(os.path.expanduser("~"), ".config")
        elif system == "Windows":
            base = os.environ.get(
                "APPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
            )
        else:  # Linux / other
            base = os.environ.get(
                "XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config")
            )

        config_dir = os.path.join(base, "ti-toolbox")
        os.makedirs(config_dir, exist_ok=True)
        return config_dir

    def reports(self) -> str:
        """Path to ``<project>/derivatives/ti-toolbox/reports/``."""
        return os.path.join(self.ti_toolbox(), "reports")

    def stats_data(self) -> str:
        """Path to ``<project>/derivatives/ti-toolbox/stats/data/``."""
        return os.path.join(self.ti_toolbox(), "stats", "data")

    def stats_output(self, analysis_type: str, analysis_name: str) -> str:
        """Path to a specific statistics output directory.

        Parameters
        ----------
        analysis_type : str
            Type of statistical analysis (e.g., ``"permutation"``).
        analysis_name : str
            Name of the analysis run.

        Returns
        -------
        str
            Absolute path to the output directory.
        """
        return os.path.join(self.ti_toolbox(), "stats", analysis_type, analysis_name)

    def logs_group(self) -> str:
        """Path to group-analysis log directory."""
        return os.path.join(self.ti_toolbox(), "logs", "group_analysis")

    def qsiprep(self) -> str:
        """Path to ``<project>/derivatives/qsiprep/``."""
        return os.path.join(self._root(), "derivatives", "qsiprep")

    def qsirecon(self) -> str:
        """Path to ``<project>/derivatives/qsirecon/``."""
        return os.path.join(self._root(), "derivatives", "qsirecon")

    # ------------------------------------------------------------------
    # Subject-level paths (sid: str)
    # ------------------------------------------------------------------

    def sub(self, sid: str) -> str:
        """Path to ``derivatives/SimNIBS/sub-{sid}/``.

        Parameters
        ----------
        sid : str
            Subject identifier (without ``sub-`` prefix).

        Returns
        -------
        str
            Absolute path to the subject's SimNIBS directory.
        """
        return os.path.join(self._root(), "derivatives", "SimNIBS", f"sub-{sid}")

    def m2m(self, sid: str) -> str:
        """Path to the ``m2m_{sid}`` head-model directory for *sid*."""
        return os.path.join(self.sub(sid), f"m2m_{sid}")

    def eeg_positions(self, sid: str) -> str:
        """Path to the EEG electrode-position directory for *sid*."""
        return os.path.join(self.m2m(sid), "eeg_positions")

    def rois(self, sid: str) -> str:
        """Path to the ROI directory for *sid*."""
        return os.path.join(self.m2m(sid), "ROIs")

    def t1(self, sid: str) -> str:
        """Path to the T1-weighted NIfTI image for *sid*."""
        return os.path.join(self.m2m(sid), "T1.nii.gz")

    def segmentation(self, sid: str) -> str:
        """Path to the segmentation directory for *sid*."""
        return os.path.join(self.m2m(sid), "segmentation")

    def tissue_labeling(self, sid: str) -> str:
        """Path to the tissue labeling NIfTI for *sid*."""
        return os.path.join(self.segmentation(sid), "labeling.nii.gz")

    def leadfields(self, sid: str) -> str:
        """Path to the leadfields directory for *sid*."""
        return os.path.join(self.sub(sid), "leadfields")

    def simulations(self, sid: str) -> str:
        """Path to ``Simulations/`` for *sid*."""
        return os.path.join(self.sub(sid), "Simulations")

    def logs(self, sid: str) -> str:
        """Path to per-subject log directory for *sid*."""
        return os.path.join(self.ti_toolbox(), "logs", f"sub-{sid}")

    def tissue_analysis_output(self, sid: str) -> str:
        """Path to tissue-analysis output directory for *sid*."""
        return os.path.join(self.ti_toolbox(), "tissue_analysis", f"sub-{sid}")

    def bids_subject(self, sid: str) -> str:
        """Path to ``<project>/sub-{sid}/`` (raw BIDS subject root)."""
        return os.path.join(self._root(), f"sub-{sid}")

    def bids_anat(self, sid: str) -> str:
        """Path to ``<project>/sub-{sid}/anat/``."""
        return os.path.join(self.bids_subject(sid), "anat")

    def bids_dwi(self, sid: str) -> str:
        """Path to ``<project>/sub-{sid}/dwi/``."""
        return os.path.join(self.bids_subject(sid), "dwi")

    def sourcedata_subject(self, sid: str) -> str:
        """Path to ``sourcedata/sub-{sid}/``."""
        return os.path.join(self.sourcedata(), f"sub-{sid}")

    def freesurfer_subject(self, sid: str) -> str:
        """Path to ``derivatives/freesurfer/sub-{sid}/``."""
        return os.path.join(self.freesurfer(), f"sub-{sid}")

    def freesurfer_mri(self, sid: str) -> str:
        """Path to ``derivatives/freesurfer/sub-{sid}/mri/``."""
        return os.path.join(self.freesurfer_subject(sid), "mri")

    def qsiprep_subject(self, sid: str) -> str:
        """Path to ``derivatives/qsiprep/sub-{sid}/``."""
        return os.path.join(self.qsiprep(), f"sub-{sid}")

    def qsirecon_subject(self, sid: str) -> str:
        """Path to ``derivatives/qsirecon/sub-{sid}/``."""
        return os.path.join(self.qsirecon(), f"sub-{sid}")

    def ex_search(self, sid: str) -> str:
        """Path to exhaustive-search results for *sid*."""
        return os.path.join(self.sub(sid), "ex-search")

    def flex_search(self, sid: str) -> str:
        """Path to flex-search results for *sid*."""
        return os.path.join(self.sub(sid), "flex-search")

    # ------------------------------------------------------------------
    # Subject + simulation paths
    # ------------------------------------------------------------------

    def simulation(self, sid: str, sim: str) -> str:
        """Path to a named simulation directory for *sid*."""
        return os.path.join(self.simulations(sid), sim)

    def ti_mesh(self, sid: str, sim: str) -> str:
        """Path to the TI mesh file (``{sim}_TI.msh``)."""
        return os.path.join(self.simulation(sid, sim), "TI", "mesh", f"{sim}_TI.msh")

    def ti_mesh_dir(self, sid: str, sim: str) -> str:
        """Path to the TI mesh directory."""
        return os.path.join(self.simulation(sid, sim), "TI", "mesh")

    def ti_central_surface(self, sid: str, sim: str) -> str:
        """Path to the TI central cortical surface mesh."""
        return os.path.join(
            self.simulation(sid, sim), "TI", "mesh", "surfaces", f"{sim}_TI_central.msh"
        )

    def mti_mesh_dir(self, sid: str, sim: str) -> str:
        """Path to the mTI mesh directory."""
        return os.path.join(self.simulation(sid, sim), "mTI", "mesh")

    def analysis_dir(self, sid: str, sim: str, space: str) -> str:
        """Path to the analysis directory for a given analysis space.

        Parameters
        ----------
        sid : str
            Subject identifier.
        sim : str
            Simulation name.
        space : str
            Analysis space — ``"mesh"`` or ``"voxel"``.

        Returns
        -------
        str
            Absolute path to ``Analyses/Mesh/`` or ``Analyses/Voxel/``.
        """
        folder = "Mesh" if space.lower() == "mesh" else "Voxel"
        return os.path.join(self.simulation(sid, sim), "Analyses", folder)

    # ------------------------------------------------------------------
    # Subject + run/name paths
    # ------------------------------------------------------------------

    def sourcedata_dicom(self, sid: str, modality: str) -> str:
        """Path to DICOM source data for *sid* and *modality*."""
        return os.path.join(self.sourcedata_subject(sid), modality, "dicom")

    def ex_search_run(self, sid: str, run: str) -> str:
        """Path to a specific exhaustive-search run directory."""
        return os.path.join(self.ex_search(sid), run)

    def flex_search_run(self, sid: str, name: str) -> str:
        """Path to a specific flex-search run directory."""
        return os.path.join(self.flex_search(sid), name)

    def flex_electrode_positions(self, sid: str, name: str) -> str:
        """Path to ``electrode_positions.json`` for a flex-search run."""
        return os.path.join(self.flex_search_run(sid, name), "electrode_positions.json")

    def flex_manifest(self, sid: str, name: str) -> str:
        """Path to ``flex_meta.json`` for a flex-search run."""
        return os.path.join(self.flex_search_run(sid, name), "flex_meta.json")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def ensure(self, path: str) -> str:
        """Create a directory (with parents) if it does not exist.

        Parameters
        ----------
        path : str
            Directory path to create.

        Returns
        -------
        str
            The same *path*, for convenient chaining.
        """
        os.makedirs(path, exist_ok=True)
        return path

    # ------------------------------------------------------------------
    # Listing helpers
    # ------------------------------------------------------------------

    def list_simnibs_subjects(self) -> list[str]:
        """List subject IDs that have a SimNIBS head-model (m2m) folder.

        Returns
        -------
        list of str
            Naturally sorted subject identifiers (without the ``sub-`` prefix).
            Returns an empty list if the SimNIBS directory does not exist.
        """
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

    def list_simulations(self, sid: str) -> list[str]:
        """List simulation folder names for a subject.

        Parameters
        ----------
        sid : str
            Subject identifier.

        Returns
        -------
        list of str
            Alphabetically sorted simulation directory names.  Returns an
            empty list if the ``Simulations/`` directory does not exist.
        """
        sim_root = self.simulations(sid)

        try:
            simulations: list[str] = []
            with os.scandir(sim_root) as it:
                for entry in it:
                    if entry.is_dir() and not entry.name.startswith("."):
                        simulations.append(entry.name)
            simulations.sort()
            return simulations
        except OSError:
            return []

    def list_eeg_caps(self, sid: str) -> list[str]:
        """List EEG cap CSV filenames for a subject.

        Parameters
        ----------
        sid : str
            Subject identifier.

        Returns
        -------
        list of str
            Sorted CSV filenames found in the ``eeg_positions/`` directory.
        """
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

    def list_flex_search_runs(self, sid: str) -> list[str]:
        """List flex-search run directories containing result metadata.

        Only directories that contain ``flex_meta.json`` or
        ``electrode_positions.json`` are included.

        Parameters
        ----------
        sid : str
            Subject identifier.

        Returns
        -------
        list of str
            Sorted run directory names.
        """
        root = self.flex_search(sid) if self.project_dir else None
        if not root or not os.path.isdir(root):
            return []

        try:
            out: list[str] = []
            with os.scandir(root) as it:
                for entry in it:
                    if not entry.is_dir() or entry.name.startswith("."):
                        continue
                    if os.path.isfile(
                        os.path.join(entry.path, "flex_meta.json")
                    ) or os.path.isfile(
                        os.path.join(entry.path, "electrode_positions.json")
                    ):
                        out.append(entry.name)
            out.sort()
            return out
        except OSError:
            return []

    # ------------------------------------------------------------------
    # Analysis naming helpers
    # ------------------------------------------------------------------

    @staticmethod
    def spherical_analysis_name(
        x: float, y: float, z: float, radius: float, coordinate_space: str
    ) -> str:
        """Build a canonical folder name for a spherical ROI analysis.

        Parameters
        ----------
        x, y, z : float
            Centre coordinates of the sphere (mm).
        radius : float
            Sphere radius (mm).
        coordinate_space : str
            ``"MNI"`` or ``"subject"``.

        Returns
        -------
        str
            Folder name, e.g. ``"sphere_x0.00_y0.00_z0.00_r5.0_MNI"``.
        """
        coord_space_suffix = (
            "_MNI" if str(coordinate_space).upper() == "MNI" else "_subject"
        )
        return f"sphere_x{x:.2f}_y{y:.2f}_z{z:.2f}_r{float(radius)}{coord_space_suffix}"

    @staticmethod
    def _atlas_name_clean(atlas_name_or_path: str) -> str:
        """Sanitise an atlas name or path into a filesystem-safe string."""
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
        region: str | None,
        atlas_name: str | None = None,
        atlas_path: str | None = None,
    ) -> str:
        """Build a canonical folder name for a cortical/atlas analysis.

        Parameters
        ----------
        whole_head : bool
            If *True*, the analysis covers the whole head (no region filter).
        region : str or None
            Atlas region label(s).  Multiple regions are ``+``-separated.
        atlas_name : str or None, optional
            Human-readable atlas name.
        atlas_path : str or None, optional
            Filesystem path to the atlas file (used as fallback for naming).

        Returns
        -------
        str
            Folder name, e.g. ``"cortical_precentral_DK40"`` or
            ``"whole_head_DK40"``.

        Raises
        ------
        ValueError
            If *whole_head* is *False* and *region* is empty or *None*.
        """
        atlas_clean = cls._atlas_name_clean(atlas_name or atlas_path or "unknown_atlas")
        if whole_head:
            return f"whole_head_{atlas_clean}"
        region_val = str(region or "").strip()
        if not region_val:
            raise ValueError(
                "region is required for cortical analysis unless whole_head=True"
            )
        if "+" in region_val:
            n = len(region_val.split("+"))
            h = hashlib.md5(region_val.encode()).hexdigest()[:8]
            return f"cortical_{n}regions_{atlas_clean}_{h}"
        return f"cortical_{region_val}_{atlas_clean}"

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
        region: str | None = None,
        atlas_name: str | None = None,
        atlas_path: str | None = None,
    ) -> str:
        """Return the analysis output directory path (does not create it).

        Delegates to :meth:`spherical_analysis_name` or
        :meth:`cortical_analysis_name` depending on *analysis_type*.

        Parameters
        ----------
        sid : str
            Subject identifier.
        sim : str
            Simulation name.
        space : str
            Analysis space (``"mesh"`` or ``"voxel"``).
        analysis_type : str
            ``"spherical"`` or ``"cortical"``.
        coordinates : sequence of float or None, optional
            ``(x, y, z)`` centre for spherical analysis.
        radius : float or None, optional
            Sphere radius in mm (required when *analysis_type* is
            ``"spherical"``).
        coordinate_space : str, optional
            ``"MNI"`` or ``"subject"``.  Default is ``"subject"``.
        whole_head : bool, optional
            Whether cortical analysis covers the whole head.
        region : str or None, optional
            Atlas region label(s) for cortical analysis.
        atlas_name : str or None, optional
            Atlas name for cortical analysis.
        atlas_path : str or None, optional
            Atlas file path for cortical analysis.

        Returns
        -------
        str
            Absolute path to the analysis output directory.

        Raises
        ------
        ValueError
            If required parameters for the chosen *analysis_type* are
            missing or invalid.

        See Also
        --------
        spherical_analysis_name : Naming convention for spherical ROIs.
        cortical_analysis_name : Naming convention for cortical/atlas ROIs.
        """
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

_path_manager_instance: PathManager | None = None


def get_path_manager(project_dir: str | None = None) -> PathManager:
    """Return the global :class:`PathManager` singleton.

    Creates a new instance on the first call.  If *project_dir* is provided,
    the singleton's :attr:`~PathManager.project_dir` is (re)set.

    Parameters
    ----------
    project_dir : str or None, optional
        Project root directory.  When *None*, the existing value (or
        environment auto-detection) is used.

    Returns
    -------
    PathManager
        The shared singleton instance.

    See Also
    --------
    reset_path_manager : Destroy the singleton for testing or re-init.
    """
    global _path_manager_instance
    if _path_manager_instance is None:
        _path_manager_instance = PathManager()
    if project_dir is not None:
        _path_manager_instance.project_dir = project_dir
    return _path_manager_instance


def reset_path_manager() -> None:
    """Destroy the singleton so the next call creates a fresh instance.

    Primarily used in test fixtures to prevent cross-test contamination.

    See Also
    --------
    get_path_manager : Obtain the singleton instance.
    """
    global _path_manager_instance
    _path_manager_instance = None
