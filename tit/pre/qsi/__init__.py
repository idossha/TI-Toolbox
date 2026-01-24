#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
QSI (QSIPrep/QSIRecon) Integration for TI-Toolbox.

This module provides Docker-out-of-Docker (DooD) integration for running
QSIPrep and QSIRecon as sibling containers from within the SimNIBS container.

The primary use case is preprocessing DWI data to extract DTI tensors for
SimNIBS anisotropic conductivity simulations.

Public API:
    - run_qsiprep: Run QSIPrep preprocessing pipeline
    - run_qsirecon: Run QSIRecon reconstruction pipeline
    - extract_dti_tensor: Extract DTI tensor for SimNIBS integration

Configuration Classes:
    - QSIPrepConfig: Configuration for QSIPrep runs
    - QSIReconConfig: Configuration for QSIRecon runs
    - ReconSpec: Enum of available reconstruction specifications
    - QSIAtlas: Enum of available atlases for connectivity analysis
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
