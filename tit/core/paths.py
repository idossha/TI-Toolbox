#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox Path Management
Centralized path management for the entire TI-Toolbox codebase.

This module provides a professional path management system for BIDS-compliant
directory structures, handling project directories, subject paths, and common
path patterns consistently across all tools.

Usage:
    # Use the singleton instance
    from tit.core import get_path_manager

    pm = get_path_manager()
    subjects = pm.list_subjects()
    m2m_dir = pm.path("m2m", subject_id="001")
    sim_dir = pm.path("simulation", subject_id="001", simulation_name="montage1")
"""

import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Iterable, Tuple, Mapping, Any
from functools import lru_cache

from . import constants as const


class _CompiledTemplate:
    """
    Fast path template renderer.

    Avoids repeated `str.format()` by pre-parsing each segment into
    literal chunks + placeholder names.
    """

    __slots__ = ("_segments", "required_entities")

    def __init__(
        self,
        segments: Tuple[Tuple[Tuple[str, Optional[str]], ...], ...],
        required_entities: Tuple[str, ...],
    ):
        # segments: tuple[ segment -> tuple[(literal, field_name_or_None)] ]
        self._segments = segments
        self.required_entities = required_entities

    @staticmethod
    def _parse_segment(s: str) -> Tuple[Tuple[str, Optional[str]], ...]:
        """
        Parse "sub-{subject_id}" into: [("sub-", None), ("", "subject_id")].

        Supports only `{name}` placeholders (no format specs).
        """
        out: List[Tuple[str, Optional[str]]] = []
        i = 0
        n = len(s)
        while i < n:
            j = s.find("{", i)
            if j < 0:
                out.append((s[i:], None))
                break
            if j > i:
                out.append((s[i:j], None))
            k = s.find("}", j + 1)
            if k < 0:
                # Treat unmatched "{" as literal.
                out.append((s[j:], None))
                break
            name = s[j + 1 : k].strip()
            out.append(("", name or ""))
            i = k + 1
        return tuple(out)

    @classmethod
    def compile(cls, parts: Iterable[str]) -> "_CompiledTemplate":
        parsed: List[Tuple[Tuple[str, Optional[str]], ...]] = []
        required: List[str] = []
        for p in parts:
            seg = cls._parse_segment(str(p))
            parsed.append(seg)
            for lit, name in seg:
                if name:
                    required.append(name)
        # De-dupe required while preserving order.
        seen = set()
        required_dedup: List[str] = []
        for r in required:
            if r not in seen:
                seen.add(r)
                required_dedup.append(r)
        return cls(tuple(parsed), tuple(required_dedup))

    def render_parts(self, entities: Mapping[str, Any]) -> Tuple[str, ...]:
        rendered: List[str] = []
        for seg in self._segments:
            # `seg` is a sequence of (literal, field) pairs.
            if len(seg) == 1 and seg[0][1] is None:
                # Pure literal.
                rendered.append(seg[0][0])
                continue
            buf: List[str] = []
            for lit, field in seg:
                if field is None:
                    if lit:
                        buf.append(lit)
                else:
                    buf.append(str(entities.get(field, "")))
            rendered.append("".join(buf))
        return tuple(rendered)


def _freeze_kwargs(kwargs: Mapping[str, Any]) -> Tuple[Tuple[str, str], ...]:
    """Deterministic, hashable kwargs representation for caching."""
    if not kwargs:
        return tuple()
    return tuple(
        sorted(
            ((str(k), "" if v is None else str(v)) for k, v in kwargs.items()),
            key=lambda kv: kv[0],
        )
    )


def _ensure_compiled_templates(cls: "PathManager") -> None:
    """Initialize module-level compiled templates once from `PathManager._TEMPLATES`."""
    if _COMPILED_TEMPLATES:
        return
    for k, parts in cls._TEMPLATES.items():
        _COMPILED_TEMPLATES[str(k)] = _CompiledTemplate.compile(parts)


# Compile templates once at import time for speed (and to centralize conventions).
_COMPILED_TEMPLATES: Dict[str, _CompiledTemplate] = {}


@lru_cache(maxsize=8192)
def _cached_render(
    project_dir: str, key: str, frozen_items: Tuple[Tuple[str, str], ...]
) -> str:
    tpl = _COMPILED_TEMPLATES.get(key)
    if tpl is None:
        raise KeyError(f"Unknown path key: {key}")
    entities = dict(frozen_items)
    parts = tpl.render_parts(entities)
    return os.path.join(project_dir, *parts)


class PathManager:
    """
    Centralized path management for TI-Toolbox.

    This class provides consistent path resolution across all components:
    - Project directory detection
    - Subject listing and validation
    - Common path patterns (derivatives, SimNIBS, m2m, etc.)
    - BIDS-compliant directory structure handling

    Usage:
        pm = PathManager()
        pm.project_dir = "/path/to/project"  # Explicit set
        print(pm.project_dir)                # Get current
        print(pm.project_dir_name)           # Just the name
    """

    def __init__(self, project_dir: Optional[str] = None):
        """
        Initialize the path manager.

        Args:
            project_dir: Optional explicit project directory. If not provided,
                        auto-detection from environment variables is attempted
                        on first access of project_dir property.
        """
        self._project_dir: Optional[str] = None
        _ensure_compiled_templates(self.__class__)

        if project_dir:
            self.project_dir = project_dir  # Use setter for validation

    @property
    def project_dir(self) -> Optional[str]:
        """
        Get/set the project directory path.

        Auto-detects from environment on first access if not set.
        Setting validates the path exists.

        Usage:
            pm.project_dir = "/path/to/project"  # set
            path = pm.project_dir                # get
        """
        if self._project_dir is None:
            # Auto-detect from environment
            project_dir = os.environ.get(const.ENV_PROJECT_DIR)
            if project_dir and os.path.isdir(project_dir):
                self._project_dir = project_dir
            # Only fall back to PROJECT_DIR_NAME if PROJECT_DIR wasn't usable.
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
        """Get the project directory name (basename of project_dir)."""
        if self._project_dir:
            return os.path.basename(self._project_dir)
        return os.environ.get(const.ENV_PROJECT_DIR_NAME)

    # -------------------------------------------------------------------------
    # Fast template-based resolver (reduces method count + code bloat).
    # -------------------------------------------------------------------------

    _TEMPLATES = {
        # core roots
        "derivatives": (const.DIR_DERIVATIVES,),
        "sourcedata": (const.DIR_SOURCEDATA,),
        "simnibs": (const.DIR_DERIVATIVES, const.DIR_SIMNIBS),
        "freesurfer": (const.DIR_DERIVATIVES, "freesurfer"),
        "simnibs_subject": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
        ),
        "m2m": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            f"{const.DIR_M2M_PREFIX}{{subject_id}}",
        ),
        "simulations": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            "Simulations",
        ),
        "simulation": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            "Simulations",
            "{simulation_name}",
        ),
        # freesurfer
        "freesurfer_subject": (
            const.DIR_DERIVATIVES,
            "freesurfer",
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
        ),
        "freesurfer_mri": (
            const.DIR_DERIVATIVES,
            "freesurfer",
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            "mri",
        ),
        # m2m subfolders
        "eeg_positions": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            f"{const.DIR_M2M_PREFIX}{{subject_id}}",
            const.DIR_EEG_POSITIONS,
        ),
        "m2m_rois": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            f"{const.DIR_M2M_PREFIX}{{subject_id}}",
            const.DIR_ROIS,
        ),
        "t1": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            f"{const.DIR_M2M_PREFIX}{{subject_id}}",
            const.FILE_T1,
        ),
        "leadfields": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            const.DIR_LEADFIELDS,
        ),
        # ti-toolbox derivatives
        "ti_toolbox": (const.DIR_DERIVATIVES, const.DIR_TI_TOOLBOX),
        "ti_toolbox_info": (
            const.DIR_DERIVATIVES,
            const.DIR_TI_TOOLBOX,
            const.DIR_TI_TOOLBOX_INFO,
        ),
        "ti_toolbox_status": (
            const.DIR_DERIVATIVES,
            const.DIR_TI_TOOLBOX,
            const.DIR_TI_TOOLBOX_INFO,
            "project_status.json",
        ),
        "ti_logs": (
            const.DIR_DERIVATIVES,
            const.DIR_TI_TOOLBOX,
            const.DIR_LOGS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
        ),
        "ti_logs_group": (
            const.DIR_DERIVATIVES,
            const.DIR_TI_TOOLBOX,
            const.DIR_LOGS,
            "group_analysis",
        ),
        "ti_reports": (const.DIR_DERIVATIVES, const.DIR_TI_TOOLBOX, const.DIR_REPORTS),
        "ti_stats_data": (const.DIR_DERIVATIVES, const.DIR_TI_TOOLBOX, "stats", "data"),
        # config directory
        "ti_toolbox_config": (
            const.DIR_CODE,
            const.DIR_CODE_TI_TOOLBOX,
            const.DIR_CONFIG,
        ),
        "montage_config": (
            const.DIR_CODE,
            const.DIR_CODE_TI_TOOLBOX,
            const.DIR_CONFIG,
            const.FILE_MONTAGE_LIST,
        ),
        "extensions_config": (
            const.DIR_CODE,
            const.DIR_CODE_TI_TOOLBOX,
            const.DIR_CONFIG,
            "extensions.json",
        ),
        # TI outputs
        "ti_mesh": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            "Simulations",
            "{simulation_name}",
            "TI",
            "mesh",
            "{simulation_name}_TI" + const.EXT_MESH,
        ),
        "ti_central_surface": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            "Simulations",
            "{simulation_name}",
            "TI",
            "mesh",
            "surfaces",
            "{simulation_name}_TI_central" + const.EXT_MESH,
        ),
        # mTI outputs
        "mti_mesh_dir": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            "Simulations",
            "{simulation_name}",
            "mTI",
            "mesh",
        ),
        "ti_mesh_dir": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            "Simulations",
            "{simulation_name}",
            "TI",
            "mesh",
        ),
        # preprocessing / sourcedata
        "bids_subject": (f"{const.PREFIX_SUBJECT}{{subject_id}}",),
        "bids_anat": (f"{const.PREFIX_SUBJECT}{{subject_id}}", "anat"),
        "bids_dwi": (f"{const.PREFIX_SUBJECT}{{subject_id}}", const.DIR_DWI),
        "sourcedata": (const.DIR_SOURCEDATA,),
        "sourcedata_subject": (
            const.DIR_SOURCEDATA,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
        ),
        "sourcedata_dicom": (
            const.DIR_SOURCEDATA,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            "{modality}",
            "dicom",
        ),
        # QSIPrep/QSIRecon derivatives
        "qsiprep": (const.DIR_DERIVATIVES, const.DIR_QSIPREP),
        "qsiprep_subject": (
            const.DIR_DERIVATIVES,
            const.DIR_QSIPREP,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
        ),
        "qsirecon": (const.DIR_DERIVATIVES, const.DIR_QSIRECON),
        "qsirecon_subject": (
            const.DIR_DERIVATIVES,
            const.DIR_QSIRECON,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
        ),
        # ex/flex
        "ex_search": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            const.DIR_EX_SEARCH,
        ),
        "ex_search_run": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            const.DIR_EX_SEARCH,
            "{run_name}",
        ),
        "flex_search": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            const.DIR_FLEX_SEARCH,
        ),
        "flex_search_run": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            const.DIR_FLEX_SEARCH,
            "{search_name}",
        ),
        "flex_electrode_positions": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            const.DIR_FLEX_SEARCH,
            "{search_name}",
            "electrode_positions.json",
        ),
        # tissue analysis
        "tissue_labeling": (
            const.DIR_DERIVATIVES,
            const.DIR_SIMNIBS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
            f"{const.DIR_M2M_PREFIX}{{subject_id}}",
            "segmentation",
            "Labeling.nii.gz",
        ),
        "tissue_analysis_output": (
            const.DIR_DERIVATIVES,
            const.DIR_TI_TOOLBOX,
            const.DIR_TISSUE_ANALYSIS,
            f"{const.PREFIX_SUBJECT}{{subject_id}}",
        ),
    }

    def path(self, key: str, /, **kwargs) -> str:
        """
        Resolve a canonical path by key from predefined templates.

        This is the primary path resolution method. It provides fast, cached access
        to all standard TI-Toolbox paths using pre-compiled templates.

        Parameters
        ----------
        key : str
            Path template key (e.g., 'm2m', 'simulation', 'ti_mesh')
        **kwargs
            Required entities for the template (e.g., subject_id='001', simulation_name='montage1')

        Returns
        -------
        str
            Resolved absolute path

        Raises
        ------
        RuntimeError
            If project_dir is not resolved
        KeyError
            If key is unknown
        ValueError
            If required template entities are missing

        Examples
        --------
        >>> pm = PathManager()
        >>> m2m_path = pm.path("m2m", subject_id="001")
        >>> sim_path = pm.path("simulation", subject_id="001", simulation_name="montage1")
        >>> mesh_path = pm.path("ti_mesh", subject_id="001", simulation_name="montage1")

        Notes
        -----
        - Results are cached for performance (8192 entry LRU cache)
        - All paths are resolved relative to project_dir
        - Template entities are type-checked and missing entities raise ValueError
        """
        if not self.project_dir:
            raise RuntimeError(
                "Project directory not resolved. Set PROJECT_DIR_NAME or PROJECT_DIR in Docker."
            )
        tpl = _COMPILED_TEMPLATES.get(key)
        if tpl is None:
            raise KeyError(f"Unknown path key: {key}")
        missing = [e for e in tpl.required_entities if e not in kwargs]
        if missing:
            raise ValueError(
                f"Missing required path entities for {key!r}: {', '.join(missing)}"
            )
        return _cached_render(self.project_dir, key, _freeze_kwargs(kwargs))

    def path_optional(self, key: str, /, **kwargs) -> Optional[str]:
        """
        Resolve a path without raising exceptions.

        Similar to path() but returns None instead of raising exceptions.
        Useful for checking if paths exist or can be resolved without error handling.

        Parameters
        ----------
        key : str
            Path template key
        **kwargs
            Template entities (e.g., subject_id='001')

        Returns
        -------
        str or None
            Resolved path if successful, None otherwise

        Examples
        --------
        >>> pm = PathManager()
        >>> m2m_path = pm.path_optional("m2m", subject_id="001")
        >>> if m2m_path:
        ...     print(f"m2m exists at {m2m_path}")

        Notes
        -----
        Returns None if:
        - project_dir is not resolved
        - key is unknown
        - required entities are missing
        """
        if not self.project_dir:
            return None
        tpl = _COMPILED_TEMPLATES.get(key)
        if tpl is None:
            return None
        # Optional resolver: if required entities are missing, return None.
        for e in tpl.required_entities:
            if e not in kwargs:
                return None
        try:
            return _cached_render(self.project_dir, key, _freeze_kwargs(kwargs))
        except KeyError:
            return None

    def list_flex_search_runs(self, subject_id: str) -> List[str]:
        """
        List flex-search run folders that contain electrode_positions.json.
        Uses os.scandir for efficiency.
        """
        root = self.path_optional("flex_search", subject_id=subject_id)
        if not root or not os.path.isdir(root):
            return []
        out: List[str] = []
        fname = "electrode_positions.json"
        try:
            with os.scandir(root) as it:
                for entry in it:
                    if not entry.is_dir():
                        continue
                    if entry.name.startswith("."):
                        continue
                    if os.path.isfile(os.path.join(entry.path, fname)):
                        out.append(entry.name)
        except OSError:
            return []
        out.sort()
        return out

    # -------------------------------------------------------------------------
    # Small helper API (reduces repetition in call sites)
    # -------------------------------------------------------------------------

    def exists(self, key: str, /, **kwargs) -> bool:
        """
        Check if a path exists.

        Parameters
        ----------
        key : str
            Path template key
        **kwargs
            Template entities

        Returns
        -------
        bool
            True if path can be resolved and exists on filesystem

        Examples
        --------
        >>> pm = PathManager()
        >>> if pm.exists("m2m", subject_id="001"):
        ...     print("m2m directory exists")
        """
        p = self.path_optional(key, **kwargs)
        return bool(p and os.path.exists(p))

    def is_dir(self, key: str, /, **kwargs) -> bool:
        """
        Check if a path exists and is a directory.

        Parameters
        ----------
        key : str
            Path template key
        **kwargs
            Template entities

        Returns
        -------
        bool
            True if path can be resolved and is an existing directory

        Examples
        --------
        >>> pm = PathManager()
        >>> if pm.is_dir("simulations", subject_id="001"):
        ...     simulations = pm.list_simulations("001")
        """
        p = self.path_optional(key, **kwargs)
        return bool(p and os.path.isdir(p))

    def is_file(self, key: str, /, **kwargs) -> bool:
        """
        Check if a path exists and is a file.

        Parameters
        ----------
        key : str
            Path template key
        **kwargs
            Template entities

        Returns
        -------
        bool
            True if path can be resolved and is an existing file

        Examples
        --------
        >>> pm = PathManager()
        >>> if pm.is_file("ti_mesh", subject_id="001", simulation_name="montage1"):
        ...     print("TI mesh file exists")
        """
        p = self.path_optional(key, **kwargs)
        return bool(p and os.path.isfile(p))

    def ensure_dir(self, key: str, /, **kwargs) -> str:
        """Resolve a directory path and create it (parents=True, exist_ok=True)."""
        p = self.path(key, **kwargs)
        os.makedirs(p, exist_ok=True)
        return p

    def list_subjects(self) -> List[str]:
        """
        List all available subjects in the project.

        Returns:
            List of subject IDs (without 'sub-' prefix), sorted naturally
        """
        simnibs_dir = self.path_optional("simnibs")
        if not simnibs_dir or not os.path.isdir(simnibs_dir):
            return []

        subjects = []
        for item in os.listdir(simnibs_dir):
            if not item.startswith(const.PREFIX_SUBJECT):
                continue
            subject_id = item.replace(const.PREFIX_SUBJECT, "")
            # Only list subjects that have an m2m folder (SimNIBS-ready).
            if self.is_dir("m2m", subject_id=subject_id):
                subjects.append(subject_id)

        # Sort subjects naturally (001, 002, 010, 100)
        subjects.sort(
            key=lambda x: [
                int(c) if c.isdigit() else c.lower() for c in re.split("([0-9]+)", x)
            ]
        )
        return subjects

    def list_simulations(self, subject_id: str) -> List[str]:
        """
        List all simulations for a subject.

        Args:
            subject_id: Subject ID

        Returns:
            List of simulation names, sorted alphabetically
        """
        sim_root = self.path_optional("simulations", subject_id=subject_id)
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

    # -------------------------------------------------------------------------
    # Analysis outputs (Analyzer / Group Analyzer)
    # -------------------------------------------------------------------------

    @staticmethod
    def analysis_space_dir_name(space: str) -> str:
        """Map analyzer space ('mesh'|'voxel') to folder name ('Mesh'|'Voxel')."""
        return "Mesh" if str(space).lower() == "mesh" else "Voxel"

    @staticmethod
    def _atlas_name_clean(atlas_name_or_path: str) -> str:
        s = str(atlas_name_or_path or "unknown_atlas")
        # If this is a path, reduce to basename and strip common extensions.
        s = os.path.basename(s)
        for ext in (".nii.gz", ".nii", ".mgz"):
            if s.endswith(ext):
                s = s[: -len(ext)]
                break
        return s.replace("+", "_").replace(".", "_")

    @staticmethod
    def spherical_analysis_name(
        x: float, y: float, z: float, radius: float, coordinate_space: str
    ) -> str:
        """Match GUI/CLI naming: sphere_x.._y.._z.._r.._{_MNI|_subject}."""
        coord_space_suffix = (
            "_MNI" if str(coordinate_space).upper() == "MNI" else "_subject"
        )
        return f"sphere_x{x:.2f}_y{y:.2f}_z{z:.2f}_r{float(radius)}{coord_space_suffix}"

    @classmethod
    def cortical_analysis_name(
        cls,
        *,
        whole_head: bool,
        region: Optional[str],
        atlas_name: Optional[str] = None,
        atlas_path: Optional[str] = None,
    ) -> str:
        """Match GUI/CLI naming for cortical analysis folders."""
        atlas_clean = cls._atlas_name_clean(atlas_name or atlas_path or "unknown_atlas")
        if whole_head:
            return f"whole_head_{atlas_clean}"
        region_val = str(region or "").strip()
        if not region_val:
            raise ValueError(
                "region is required for cortical analysis unless whole_head=True"
            )
        return f"region_{region_val}_{atlas_clean}"

    def get_analysis_space_dir(
        self, subject_id: str, simulation_name: str, space: str
    ) -> Optional[str]:
        """Get base analysis dir: .../Simulations/<sim>/Analyses/<Mesh|Voxel>."""
        sim_dir = self.path_optional(
            "simulation", subject_id=subject_id, simulation_name=simulation_name
        )
        if not sim_dir:
            return None
        return os.path.join(
            sim_dir, const.DIR_ANALYSIS, self.analysis_space_dir_name(space)
        )

    def get_analysis_output_dir(
        self,
        *,
        subject_id: str,
        simulation_name: str,
        space: str,
        analysis_type: str,
        coordinates: Optional[List[float]] = None,
        radius: Optional[float] = None,
        coordinate_space: str = "subject",
        whole_head: bool = False,
        region: Optional[str] = None,
        atlas_name: Optional[str] = None,
        atlas_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Centralized analysis output directory used by GUI/CLI.
        Returns the folder but does NOT create it.
        """
        base = self.get_analysis_space_dir(subject_id, simulation_name, space)
        if not base:
            return None

        at = str(analysis_type).lower()
        if at == "spherical":
            if not coordinates or len(coordinates) != 3 or radius is None:
                raise ValueError(
                    "coordinates(3) and radius are required for spherical analysis output path"
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

    def get_derivatives_dir(self) -> Optional[str]:
        """Get the derivatives directory path."""
        return self.path_optional("derivatives")

    def list_eeg_caps(self, subject_id: str) -> List[str]:
        """
        List available EEG cap files for a subject.

        Args:
            subject_id: Subject ID

        Returns:
            List of EEG cap CSV filenames, sorted alphabetically
        """
        eeg_pos_dir = self.path_optional("eeg_positions", subject_id=subject_id)
        if not eeg_pos_dir or not os.path.isdir(eeg_pos_dir):
            return []

        caps = []
        for file in os.listdir(eeg_pos_dir):
            if file.endswith(const.EXT_CSV) and not file.startswith("."):
                caps.append(file)

        caps.sort()
        return caps

    def validate_subject_structure(self, subject_id: str) -> Dict[str, any]:
        """
        Validate that a subject has the required directory structure.

        Args:
            subject_id: Subject ID

        Returns:
            Dictionary with validation results:
            - 'valid': bool indicating if structure is valid
            - 'missing': list of missing required components
            - 'warnings': list of optional missing components
        """
        results = {"valid": True, "missing": [], "warnings": []}

        # Check subject directory
        subject_dir = self.path_optional("simnibs_subject", subject_id=subject_id)
        if not subject_dir or not os.path.isdir(subject_dir):
            results["valid"] = False
            results["missing"].append(
                f"Subject directory: {const.PREFIX_SUBJECT}{subject_id}"
            )
            return results

        # Check m2m directory
        if not self.is_dir("m2m", subject_id=subject_id):
            results["valid"] = False
            results["missing"].append(
                f"m2m directory: {const.DIR_M2M_PREFIX}{subject_id}"
            )

        # Check for EEG positions (optional warning)
        if not self.is_dir("eeg_positions", subject_id=subject_id):
            results["warnings"].append(const.WARNING_NO_EEG_POSITIONS)

        return results


# ============================================================================
# SINGLETON PATTERN
# ============================================================================

_path_manager_instance: Optional[PathManager] = None


def get_path_manager() -> PathManager:
    """
    Get the global PathManager singleton instance.

    Returns:
        The global path manager instance
    """
    global _path_manager_instance
    if _path_manager_instance is None:
        _path_manager_instance = PathManager()
    return _path_manager_instance


def reset_path_manager():
    """
    Reset the global PathManager singleton instance.
    Useful for testing or when project directory changes.
    """
    global _path_manager_instance
    _path_manager_instance = None
    try:
        _cached_render.cache_clear()
    except Exception:
        pass
