"""Build real SimNIBS sessions from asymmetric authored poses; never run FEM.

The subprocess excludes host scientific mocks. This proves session construction,
not meshing or field equality. Run with simnibs_python inside the image.
"""

import subprocess
import sys
from pathlib import Path

import pytest


def test_real_simnibs_ti_and_mti_session_replay():
    root = Path(__file__).resolve().parents[2]
    probe = subprocess.run(
        [sys.executable, "-c", "import simnibs"], capture_output=True, text=True
    )
    if probe.returncode:
        pytest.skip("real SimNIBS unavailable; use simnibs_python in the image")
    code = """
from simnibs.simulation.sim_struct import SESSION
from tests.test_candidate_replay import build_session, assert_session
for pair_count in (2, 4):
    assert_session(build_session(pair_count, SESSION()), pair_count)
"""
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=root, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
