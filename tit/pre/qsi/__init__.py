#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
QSI (QSIPrep / QSIRecon) integration for TI-Toolbox.

Provides Docker-out-of-Docker (DooD) integration for running QSIPrep and
QSIRecon as sibling containers from within the SimNIBS container.  The
primary use case is preprocessing DWI data to extract DTI tensors for
SimNIBS anisotropic conductivity simulations.

Public API
----------
run_qsiprep
    Run the QSIPrep DWI preprocessing pipeline.
run_qsirecon
    Run the QSIRecon DWI reconstruction pipeline.
extract_dti_tensor
    Extract a DTI tensor and register it to the SimNIBS T1 grid.
check_dti_tensor_exists
    Check whether an extracted DTI tensor already exists.

Configuration Classes
---------------------
QSIPrepConfig
    Configuration dataclass for QSIPrep runs.
QSIReconConfig
    Configuration dataclass for QSIRecon runs.
ResourceConfig
    Resource allocation (CPU, memory, OMP threads) for QSI containers.
ReconSpec
    Enum of available QSIRecon reconstruction specifications.
QSIAtlas
    Enum of available atlases for connectivity analysis.

See Also
--------
tit.pre : Parent preprocessing package.
tit.pre.structural.run_pipeline : Full pipeline that can invoke QSI steps.
"""

from .qsiprep import run_qsiprep
from .qsirecon import run_qsirecon
from .dti_extractor import extract_dti_tensor, check_dti_tensor_exists
from .config import QSIPrepConfig, QSIReconConfig, ReconSpec, QSIAtlas, ResourceConfig

__all__ = [
    "run_qsiprep",
    "run_qsirecon",
    "extract_dti_tensor",
    "check_dti_tensor_exists",
    "QSIPrepConfig",
    "QSIReconConfig",
    "ReconSpec",
    "QSIAtlas",
    "ResourceConfig",
]
