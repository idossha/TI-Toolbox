#!/usr/bin/env python3
"""Utilities to make SimNIBS behave consistently on every platform.

Currently we only need two tweaks:
1.  Limit numerical libraries to a single OpenMP thread – this greatly
    reduces memory usage and avoids PETSC segmentation faults on
    Apple-silicon MacBooks and on hosts with many cores.
2.  Disable `KMP_AFFINITY` on macOS/arm64 (it is already disabled inside
    the Docker image, so we replicate the same behaviour when the script
    is executed outside Docker).
"""
from __future__ import annotations

import os
import platform
from typing import NoReturn, Optional  # noqa: F401 – exported for callers


def apply_common_env_fixes() -> None:
    """Apply process-wide environment tweaks."""

    # 1) single-threaded BLAS / OpenMP
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")

    # 2) KMP_AFFINITY only needed on Apple-silicon when *not* in Docker
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        os.environ.setdefault("KMP_AFFINITY", "disabled") 