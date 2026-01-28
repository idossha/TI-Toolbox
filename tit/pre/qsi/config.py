#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Configuration dataclasses and enums for QSI integration.

This module defines type-safe configuration objects for QSIPrep and QSIRecon
Docker runs, including resource allocation and pipeline specifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from tit.core import constants as const


class ReconSpec(str, Enum):
    """
    Available QSIRecon reconstruction specifications.

    Each spec defines a complete reconstruction pipeline with specific
    algorithms and output formats.
    """

    MRTRIX_MULTISHELL_MSMT_ACT_FAST = "mrtrix_multishell_msmt_ACT-fast"
    MULTISHELL_SCALARFEST = "multishell_scalarfest"
    DIPY_DKI = "dipy_dki"
    DIPY_MAPMRI = "dipy_mapmri"
    AMICO_NODDI = "amico_noddi"
    PYAFQ_TRACTOMETRY = "pyafq_tractometry"
    MRTRIX_MULTISHELL_MSMT_PYAFQ_TRACTOMETRY = (
        "mrtrix_multishell_msmt_pyafq_tractometry"
    )
    DSI_STUDIO_GQI = "dsi_studio_gqi"
    DSI_STUDIO_AUTOTRACK = "dsi_studio_autotrack"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "ReconSpec":
        """Convert string to ReconSpec enum."""
        for spec in cls:
            if spec.value == value:
                return spec
        raise ValueError(f"Unknown recon spec: {value}")

    @classmethod
    def list_all(cls) -> List[str]:
        """Return list of all spec values."""
        return [spec.value for spec in cls]


class QSIAtlas(str, Enum):
    """
    Available atlases for QSIRecon connectivity analysis.

    These atlases can be used for structural connectivity matrix generation.
    """

    AAL116 = "AAL116"
    AICHA384EXT = "AICHA384Ext"
    BRAINNETOME246EXT = "Brainnetome246Ext"
    GORDON333EXT = "Gordon333Ext"
    MICCAI2012 = "MICCAI2012"
    SCHAEFER100 = "Schaefer100"
    SCHAEFER200 = "Schaefer200"
    SCHAEFER400 = "Schaefer400"
    POWER264EXT = "power264Ext"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "QSIAtlas":
        """Convert string to QSIAtlas enum."""
        for atlas in cls:
            if atlas.value == value:
                return atlas
        raise ValueError(f"Unknown atlas: {value}")

    @classmethod
    def list_all(cls) -> List[str]:
        """Return list of all atlas values."""
        return [atlas.value for atlas in cls]


@dataclass
class ResourceConfig:
    """
    Resource allocation configuration for QSI containers.

    Attributes
    ----------
    cpus : int
        Number of CPUs to allocate to the container.
    memory_gb : int
        Memory limit in gigabytes.
    omp_threads : int
        Number of OpenMP threads (affects ANTS, MRtrix, etc.).
    """

    # If None, the DooD container will inherit the *current container's*
    # cgroup limits (CPU/memory). This prevents hard-coded caps (e.g. 32GB)
    # from unintentionally starving sibling containers.
    cpus: Optional[int] = None
    memory_gb: Optional[int] = None
    omp_threads: int = const.QSI_DEFAULT_OMP_THREADS

    def __post_init__(self) -> None:
        if self.cpus is not None and self.cpus < 1:
            raise ValueError("cpus must be >= 1")
        if self.memory_gb is not None and self.memory_gb < 4:
            raise ValueError("memory_gb must be >= 4")
        if self.omp_threads < 1:
            raise ValueError("omp_threads must be >= 1")


@dataclass
class QSIPrepConfig:
    """
    Configuration for a QSIPrep run.

    Attributes
    ----------
    subject_id : str
        Subject identifier (without 'sub-' prefix).
    output_resolution : float
        Target output resolution in mm (default: 2.0).
    resources : ResourceConfig
        Resource allocation settings.
    image_tag : str
        Docker image tag for QSIPrep.
    skip_bids_validation : bool
        Whether to skip BIDS validation (useful for non-BIDS datasets).
    denoise_method : str
        Denoising method: 'dwidenoise', 'patch2self', or 'none'.
    unringing_method : str
        Unringing method: 'mrdegibbs', 'rpg', or 'none'.
    distortion_group_merge : str
        Method for merging distortion groups: 'concatenate', 'average', or 'none'.
    """

    subject_id: str
    output_resolution: float = const.QSI_DEFAULT_OUTPUT_RESOLUTION
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    image_tag: str = const.QSI_DEFAULT_IMAGE_TAG
    skip_bids_validation: bool = True
    denoise_method: str = "dwidenoise"
    unringing_method: str = "mrdegibbs"
    distortion_group_merge: str = "none"

    def __post_init__(self) -> None:
        if not self.subject_id:
            raise ValueError("subject_id is required")
        if self.output_resolution <= 0:
            raise ValueError("output_resolution must be positive")
        valid_denoise = {"dwidenoise", "patch2self", "none"}
        if self.denoise_method not in valid_denoise:
            raise ValueError(f"denoise_method must be one of {valid_denoise}")
        valid_unring = {"mrdegibbs", "rpg", "none"}
        if self.unringing_method not in valid_unring:
            raise ValueError(f"unringing_method must be one of {valid_unring}")


@dataclass
class QSIReconConfig:
    """
    Configuration for a QSIRecon run.

    Attributes
    ----------
    subject_id : str
        Subject identifier (without 'sub-' prefix).
    recon_specs : List[str]
        List of reconstruction specs to run. Defaults to ['dipy_dki'].
    atlases : Optional[List[str]]
        List of atlases for connectivity analysis. None = no connectivity.
    use_gpu : bool
        Whether to enable GPU acceleration (requires NVIDIA Docker runtime).
    resources : ResourceConfig
        Resource allocation settings.
    image_tag : str
        Docker image tag for QSIRecon.
    skip_odf_reports : bool
        Whether to skip ODF report generation (saves time).
    """

    subject_id: str
    recon_specs: List[str] = field(default_factory=lambda: ["mrtrix_multishell_msmt_ACT-fast"])
    atlases: Optional[List[str]] = field(default_factory=lambda: ["Schaefer100", "AAL116"])
    use_gpu: bool = False
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    image_tag: str = const.QSI_DEFAULT_IMAGE_TAG
    skip_odf_reports: bool = True

    def __post_init__(self) -> None:
        if not self.subject_id:
            raise ValueError("subject_id is required")
        if not self.recon_specs:
            raise ValueError("At least one recon_spec is required")
        # Validate recon specs
        valid_specs = set(const.QSI_RECON_SPECS)
        for spec in self.recon_specs:
            if spec not in valid_specs:
                raise ValueError(
                    f"Unknown recon spec: {spec}. Valid specs: {valid_specs}"
                )
        # Validate atlases if provided
        if self.atlases:
            valid_atlases = set(const.QSI_ATLASES)
            for atlas in self.atlases:
                if atlas not in valid_atlases:
                    raise ValueError(
                        f"Unknown atlas: {atlas}. Valid atlases: {valid_atlases}"
                    )
