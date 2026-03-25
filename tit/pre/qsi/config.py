#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Configuration dataclasses and enums for QSI integration.

This module defines type-safe configuration objects for QSIPrep and QSIRecon
Docker runs, including resource allocation and pipeline specifications.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self

from tit import constants as const


class ReconSpec(StrEnum):
    """
    Available QSIRecon reconstruction specifications.

    Each spec defines a complete reconstruction pipeline with specific
    algorithms and output formats.
    """

    MRTRIX_MULTISHELL_MSMT_ACT_HSVS = "mrtrix_multishell_msmt_ACT-hsvs"
    MRTRIX_MULTISHELL_MSMT_ACT_FAST = "mrtrix_multishell_msmt_ACT-fast"
    MRTRIX_MULTISHELL_MSMT_NOACT = "mrtrix_multishell_msmt_noACT"
    MRTRIX_SINGLESHELL_SS3T_ACT_HSVS = "mrtrix_singleshell_ss3t_ACT-hsvs"
    MRTRIX_SINGLESHELL_SS3T_ACT_FAST = "mrtrix_singleshell_ss3t_ACT-fast"
    MRTRIX_SINGLESHELL_SS3T_NOACT = "mrtrix_singleshell_ss3t_noACT"
    DSI_STUDIO_GQI = "dsi_studio_gqi"
    DSI_STUDIO_AUTOTRACK = "dsi_studio_autotrack"
    DIPY_DKI = "dipy_dki"
    DIPY_MAPMRI = "dipy_mapmri"
    DIPY_3DSHORE = "dipy_3dshore"
    AMICO_NODDI = "amico_noddi"
    PYAFQ_TRACTOMETRY = "pyafq_tractometry"
    MRTRIX_MULTISHELL_MSMT_PYAFQ_TRACTOMETRY = (
        "mrtrix_multishell_msmt_pyafq_tractometry"
    )
    SS3T_FOD_AUTOTRACK = "ss3t_fod_autotrack"
    MULTISHELL_SCALARFEST = "multishell_scalarfest"
    HBCD_SCALAR_MAPS = "hbcd_scalar_maps"
    TORTOISE = "TORTOISE"
    REORIENT_FSLSTD = "reorient_fslstd"
    CSDSI_3DSHORE = "csdsi_3dshore"
    ABCD_RECON = "abcd_recon"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Convert string to ReconSpec enum."""
        for spec in cls:
            if spec.value == value:
                return spec
        raise ValueError(f"Unknown recon spec: {value}")

    @classmethod
    def list_all(cls) -> list[str]:
        """Return list of all spec values."""
        return [spec.value for spec in cls]


class QSIAtlas(StrEnum):
    """
    Available atlases for QSIRecon connectivity analysis.

    These atlases can be used for structural connectivity matrix generation.
    The 4S series combines Schaefer cortical parcels with 56 subcortical ROIs.
    """

    S4_156 = "4S156Parcels"
    S4_256 = "4S256Parcels"
    S4_356 = "4S356Parcels"
    S4_456 = "4S456Parcels"
    S4_556 = "4S556Parcels"
    S4_656 = "4S656Parcels"
    S4_756 = "4S756Parcels"
    S4_856 = "4S856Parcels"
    S4_956 = "4S956Parcels"
    S4_1056 = "4S1056Parcels"
    AAL116 = "AAL116"
    BRAINNETOME246EXT = "Brainnetome246Ext"
    AICHA384EXT = "AICHA384Ext"
    GORDON333EXT = "Gordon333Ext"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> Self:
        """Convert string to QSIAtlas enum."""
        for atlas in cls:
            if atlas.value == value:
                return atlas
        raise ValueError(f"Unknown atlas: {value}")

    @classmethod
    def list_all(cls) -> list[str]:
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
    cpus: int | None = None
    memory_gb: int | None = None
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
    image_tag: str = const.QSI_QSIPREP_IMAGE_TAG
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
    recon_specs : list[str]
        List of reconstruction specs to run. Defaults to ['dsi_studio_gqi'].
    atlases : list[str] | None
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
    recon_specs: list[str] = field(
        default_factory=lambda: [const.QSI_DEFAULT_RECON_SPEC]
    )
    atlases: list[str] | None = field(
        default_factory=lambda: list(const.QSI_DEFAULT_ATLASES)
    )
    use_gpu: bool = False
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    image_tag: str = const.QSI_QSIRECON_IMAGE_TAG
    skip_odf_reports: bool = True

    def __post_init__(self) -> None:
        if not self.subject_id:
            raise ValueError("subject_id is required")
        if not self.recon_specs:
            raise ValueError("At least one recon_spec is required")
        valid_specs = set(const.QSI_RECON_SPECS)
        for spec in self.recon_specs:
            if spec not in valid_specs:
                raise ValueError(
                    f"Unknown recon spec: {spec}. Valid specs: {valid_specs}"
                )
        if self.atlases:
            valid_atlases = set(const.QSI_ATLASES)
            for atlas in self.atlases:
                if atlas not in valid_atlases:
                    raise ValueError(
                        f"Unknown atlas: {atlas}. Valid atlases: {valid_atlases}"
                    )
