#!/usr/bin/env simnibs_python
"""
GPU Acceleration module for TI Exhaustive Search.

This module provides GPU-accelerated computation for electric field calculations
and TI envelope computations using CuPy (CUDA backend for NVIDIA GPUs).

GPU acceleration is OPTIONAL and controlled by the USE_GPU environment variable.
Default behavior: CPU computation (no GPU required).

Requirements:
- NVIDIA GPU with CUDA Compute Capability 6.0+
- NVIDIA Docker runtime (nvidia-docker2)
- Docker image built with ENABLE_GPU=1
"""

import os
import numpy as np
from typing import Tuple, Optional, Any


# GPU Backend Detection (CUDA only)
GPU_AVAILABLE = False
GPU_BACKEND = None

try:
    import cupy as cp
    if cp.cuda.is_available():
        GPU_AVAILABLE = True
        GPU_BACKEND = "CUDA"
except ImportError:
    pass


class GPUAccelerator:
    """GPU acceleration manager for TI field calculations using CUDA."""

    def __init__(self, logger, use_gpu: bool = False):
        """
        Initialize GPU accelerator.

        Args:
            logger: Logger instance for status messages
            use_gpu: Whether to use GPU acceleration (default: False)
        """
        self.logger = logger
        self.use_gpu = use_gpu and GPU_AVAILABLE
        self.backend = "CUDA" if self.use_gpu else "CPU"
        self.xp = None

        if self.use_gpu:
            import cupy as cp
            self.xp = cp
            device = cp.cuda.Device()
            mem_info = device.mem_info
            self.logger.info("="*80)
            self.logger.info("GPU Acceleration ENABLED")
            self.logger.info("="*80)
            self.logger.info(f"Backend: CUDA")
            self.logger.info(f"Device: {device.name}")
            self.logger.info(f"Memory: {mem_info[1] / 1e9:.2f} GB total, {mem_info[0] / 1e9:.2f} GB free")
            self.logger.info(f"Compute Capability: {device.compute_capability}")
            self.logger.info("="*80)
        else:
            self.xp = np
            if use_gpu and not GPU_AVAILABLE:
                self.logger.warning("="*80)
                self.logger.warning("GPU requested but not available - falling back to CPU")
                self.logger.warning("="*80)
                self.logger.warning("To enable GPU acceleration:")
                self.logger.warning("  1. Build image with: --build-arg ENABLE_GPU=1")
                self.logger.warning("  2. Run container with: --gpus all")
                self.logger.warning("  3. Set environment: USE_GPU=1")
                self.logger.warning("="*80)
            else:
                self.logger.info("GPU Acceleration DISABLED - Using CPU")

    def to_device(self, array: np.ndarray) -> Any:
        """
        Transfer array to GPU if GPU is enabled.

        Args:
            array: NumPy array to transfer

        Returns:
            CuPy array if GPU enabled, otherwise original NumPy array
        """
        if self.use_gpu:
            return self.xp.asarray(array)
        return array

    def to_host(self, array: Any) -> np.ndarray:
        """
        Transfer array back to CPU memory.

        Args:
            array: GPU or CPU array

        Returns:
            NumPy array on CPU
        """
        if self.use_gpu and hasattr(array, 'get'):
            return array.get()
        return np.asarray(array)

    def get_field_gpu(self, electrode_config: list, leadfield: Any, idx_lf: Any) -> np.ndarray:
        """
        GPU-accelerated electric field calculation.

        This mirrors SimNIBS TI.get_field() but runs on GPU.

        Args:
            electrode_config: [positive_electrode, negative_electrode, current_A]
            leadfield: Leadfield matrix
            idx_lf: Leadfield indices

        Returns:
            Electric field array (on CPU)
        """
        if not self.use_gpu:
            # Fall back to SimNIBS CPU implementation
            from simnibs.utils import TI_utils as TI
            return TI.get_field(electrode_config, leadfield, idx_lf)

        # GPU implementation
        pos_elec, neg_elec, current = electrode_config

        # Transfer leadfield to GPU if not already there
        leadfield_gpu = self.to_device(leadfield)

        # Get electrode indices
        if isinstance(idx_lf, dict):
            pos_idx = idx_lf.get(pos_elec)
            neg_idx = idx_lf.get(neg_elec)
        else:
            # Handle array-based indexing
            pos_idx = idx_lf[pos_elec]
            neg_idx = idx_lf[neg_elec]

        # Compute field on GPU: field = current * (leadfield[pos] - leadfield[neg])
        field_gpu = current * (leadfield_gpu[pos_idx] - leadfield_gpu[neg_idx])

        # Transfer back to CPU for compatibility
        return self.to_host(field_gpu)

    def get_maxTI_gpu(self, ef1: np.ndarray, ef2: np.ndarray) -> np.ndarray:
        """
        GPU-accelerated TI modulation envelope calculation.

        This mirrors SimNIBS TI.get_maxTI() but runs on GPU.

        Args:
            ef1: Electric field from first channel (E1)
            ef2: Electric field from second channel (E2)

        Returns:
            TI modulation envelope (on CPU)
        """
        if not self.use_gpu:
            # Fall back to SimNIBS CPU implementation
            from simnibs.utils import TI_utils as TI
            return TI.get_maxTI(ef1, ef2)

        # Transfer to GPU
        ef1_gpu = self.to_device(ef1)
        ef2_gpu = self.to_device(ef2)

        # Compute TI envelope: TI_max = sqrt(|E1|^2 + |E2|^2 + 2*|E1|*|E2|) / 2
        # This is the maximum modulation amplitude
        e1_mag = self.xp.linalg.norm(ef1_gpu, axis=-1) if ef1_gpu.ndim > 1 else self.xp.abs(ef1_gpu)
        e2_mag = self.xp.linalg.norm(ef2_gpu, axis=-1) if ef2_gpu.ndim > 1 else self.xp.abs(ef2_gpu)

        ti_max_gpu = self.xp.sqrt(e1_mag**2 + e2_mag**2 + 2*e1_mag*e2_mag) / 2

        # Transfer back to CPU
        return self.to_host(ti_max_gpu)

    def calculate_roi_metrics_gpu(self, ti_field_roi: np.ndarray, roi_volumes: np.ndarray,
                                  ti_field_gm: np.ndarray, gm_volumes: np.ndarray) -> dict:
        """
        GPU-accelerated ROI metrics calculation.

        Args:
            ti_field_roi: TI field values in ROI
            roi_volumes: Volume of each ROI element
            ti_field_gm: TI field values in gray matter
            gm_volumes: Volume of each gray matter element

        Returns:
            Dictionary with computed metrics
        """
        if not self.use_gpu:
            # CPU implementation
            timax_roi = float(np.max(ti_field_roi)) if len(ti_field_roi) > 0 else 0.0
            timean_roi = float(np.average(ti_field_roi, weights=roi_volumes)) if len(ti_field_roi) > 0 else 0.0
            timean_gm = float(np.average(ti_field_gm, weights=gm_volumes)) if len(ti_field_gm) > 0 else 0.0
            focality = (timean_roi / timean_gm) if timean_gm > 0 else 0.0

            return {
                'TImax_ROI': timax_roi,
                'TImean_ROI': timean_roi,
                'TImean_GM': timean_gm,
                'Focality': focality,
                'n_elements': len(ti_field_roi)
            }

        # GPU implementation
        ti_roi_gpu = self.to_device(ti_field_roi)
        roi_vols_gpu = self.to_device(roi_volumes)
        ti_gm_gpu = self.to_device(ti_field_gm)
        gm_vols_gpu = self.to_device(gm_volumes)

        # Compute metrics on GPU
        timax_roi = float(self.to_host(self.xp.max(ti_roi_gpu))) if len(ti_field_roi) > 0 else 0.0

        if len(ti_field_roi) > 0:
            timean_roi = float(self.to_host(self.xp.average(ti_roi_gpu, weights=roi_vols_gpu)))
        else:
            timean_roi = 0.0

        if len(ti_field_gm) > 0:
            timean_gm = float(self.to_host(self.xp.average(ti_gm_gpu, weights=gm_vols_gpu)))
        else:
            timean_gm = 0.0

        focality = (timean_roi / timean_gm) if timean_gm > 0 else 0.0

        return {
            'TImax_ROI': timax_roi,
            'TImean_ROI': timean_roi,
            'TImean_GM': timean_gm,
            'Focality': focality,
            'n_elements': len(ti_field_roi)
        }


def get_gpu_info() -> dict:
    """
    Get information about available GPU resources.

    Returns:
        Dictionary with GPU availability and device information
    """
    info = {
        'available': GPU_AVAILABLE,
        'backend': GPU_BACKEND,
        'devices': []
    }

    if GPU_AVAILABLE:
        try:
            import cupy as cp
            n_devices = cp.cuda.runtime.getDeviceCount()
            for i in range(n_devices):
                with cp.cuda.Device(i):
                    device = cp.cuda.Device()
                    mem_info = device.mem_info
                    info['devices'].append({
                        'id': i,
                        'name': device.name,
                        'memory_total': mem_info[1],
                        'memory_free': mem_info[0],
                        'compute_capability': device.compute_capability
                    })
        except Exception as e:
            info['error'] = str(e)

    return info
