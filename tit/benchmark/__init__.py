"""
TI-Toolbox Benchmarking Module

A comprehensive benchmarking suite for measuring performance of TI-Toolbox 
preprocessing and optimization steps.

Components:
- core: Core benchmarking utilities (timers, hardware info, results)
- logger: Benchmark-specific logging utilities with auto-flush
- charm: SimNIBS charm (m2m) creation benchmarking
- recon: FreeSurfer recon-all benchmarking
- dicom: DICOM to NIfTI conversion benchmarking
- flex: Flex-search optimization benchmarking with multi-start

Usage:
    # Run from command line
    simnibs_python tit/benchmark/charm.py
    simnibs_python tit/benchmark/recon.py
    simnibs_python tit/benchmark/dicom.py
    simnibs_python tit/benchmark/flex.py
    
    # Or use Python API
    from tit.benchmark import BenchmarkTimer, print_hardware_info
"""

from .core import (
    BenchmarkTimer,
    HardwareInfo,
    BenchmarkResult,
    get_hardware_info,
    print_hardware_info,
    save_benchmark_result,
    load_benchmark_result,
    print_benchmark_result
)

__all__ = [
    'BenchmarkTimer',
    'HardwareInfo',
    'BenchmarkResult',
    'get_hardware_info',
    'print_hardware_info',
    'save_benchmark_result',
    'load_benchmark_result',
    'print_benchmark_result'
]

__version__ = '1.0.0'

