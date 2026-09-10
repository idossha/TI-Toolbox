#!/usr/bin/env python3
"""Verify the scientific ABI and standalone Blender boundary in the built image.

Run with simnibs_python. The only pip-check exceptions are SimNIBS's intentionally
removed GUI packages and MKL/TBB supplied by Conda, whose libraries load below.
"""

from __future__ import annotations

import ctypes
import importlib
from importlib import metadata
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys


def unexpected_dependency_errors(output: str) -> list[str]:
    """Allow only documented headless omissions and verified Conda runtime providers."""
    allowed = re.compile(
        r"simnibs 4\.6\.0 requires (gmsh|pyqt5|mkl|tbb), which is not installed\.", re.I
    )
    return [
        line
        for line in output.splitlines()
        if line.strip()
        and line != "No broken requirements found."
        and not allowed.fullmatch(line)
    ]


def main() -> int:
    import numpy as np

    if metadata.version("simnibs") != "4.6.0":
        raise RuntimeError("scientific runtime requires SimNIBS 4.6.0")
    if np.__version__ != "2.3.5":
        raise RuntimeError(f"scientific NumPy must be 2.3.5, found {np.__version__}")
    if importlib.util.find_spec("bpy") is not None:
        raise RuntimeError("bpy must not be installed in the scientific environment")
    for module in (
        "scipy",
        "h5py",
        "numba",
        "simnibs",
        "simnibs.segmentation",
        "brainnet",
        "samseg.gems",
        "mumps",
        "petsc4py.PETSc",
        "torch",
    ):
        importlib.import_module(module)
        print(f"IMPORT {module} OK", flush=True)
    np.testing.assert_allclose(
        np.linalg.solve(np.diag([2.0, 3.0]), [4.0, 9.0]), [2.0, 3.0]
    )
    for library in ("libmkl_rt.so.2", "libtbb.so.12"):
        ctypes.CDLL(str(Path(sys.prefix) / "lib" / library))
        print(f"CONDA LIBRARY {library} OK", flush=True)
    check = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        text=True,
        capture_output=True,
        check=False,
    )
    errors = unexpected_dependency_errors(check.stdout + check.stderr)
    if (
        check.returncode not in (0, 1)
        or errors
        or (check.returncode and not check.stdout.strip())
    ):
        raise RuntimeError(
            f"unexpected dependency failures: {errors or check.returncode}"
        )
    print(
        "HEADLESS EXCEPTIONS: gmsh/PyQt5 intentionally removed; MKL/TBB verified as Conda libraries",
        flush=True,
    )
    print(f"SIMNIBS {metadata.version('simnibs')} / NUMPY {np.__version__}", flush=True)
    # This executable has its own Python3.11/NumPy1.26.4; never pass the scientific Python path.
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH"}
    }
    expression = "import bpy,numpy; assert bpy.app.version == (4,4,3), bpy.app.version; assert numpy.__version__ == '1.26.4', numpy.__version__; print('BLENDER 4.4.3 / NUMPY 1.26.4 OK')"
    subprocess.run(
        [
            os.environ.get("TIT_BLENDER_BIN", "/opt/blender/blender"),
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python-expr",
            expression,
        ],
        check=True,
        env=env,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
