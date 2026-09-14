"""Real SciPy/SimNIBS boundary tests without FEM or subject data.

Run in the image: simnibs_python -m pytest tests/numerical/test_flex_optimizer_contract.py -q
The subprocess excludes host conftest mocks. Quadratic optimum and rigid pose are
analytic fixtures; these checks do not claim head-mesh or final-field accuracy.
"""

import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = r"""
import importlib.util
from pathlib import Path
import numpy as np
from types import SimpleNamespace
from simnibs.optimization.tes_flex_optimization.electrode_layout import ElectrodeArrayPair, create_tdcs_session_from_array
from tit.opt.flex.builder import configure_optimizer_options
import logging

from tit.opt.flex.runtime import integration_module
module = integration_module()
assert Path(module.__file__).resolve() == Path("resources/map-electrodes/tes_flex_optimization.py").resolve()
opt = module.TesFlexOptimization()
opt._prepared = True
for name in ("_set_logger", "_finish_logger", "_log_summary_preopt", "_log_summary_postopt", "_save_optimized_positions"):
    setattr(opt, name, lambda: None)
opt.run_final_electrode_simulation = False
opt._optimizer_options_std.update(bounds=[(-1.0, 1.0)], init_vals=[0.0], maxiter=3, popsize=5, disp=False)
configure_optimizer_options(opt, SimpleNamespace(max_iterations=None, population_size=None, tolerance=None, mutation="0.7", recombination=None), logging.getLogger("fixture"))
opt.get_electrode_pos_from_array = lambda x: [[np.asarray(x).copy()]]
opt.get_nodes_electrode = lambda electrode_pos: [{0: np.array([0])}]
def goal(x):
    opt.n_sim += 1
    return float(x[0] ** 2)
opt.goal_fun = goal
# Exercise the production default save_mat=True with real SciPy serialization.
import io
import tempfile
import scipy.io
with tempfile.TemporaryDirectory() as folder:
    opt.output_folder = folder
    opt.electrode = []
    opt.goal = ["mean"]
    opt.run()
    mat_files = list(Path(folder).glob("*.mat"))
    assert len(mat_files) == 1
    assert scipy.io.loadmat(mat_files[0], simplify_cells=True)["goal"] == "mean"
    mat_files[0].unlink()
    messages = io.StringIO()
    handler = logging.StreamHandler(messages)
    module.logger.addHandler(handler)
    opt.goal = [lambda fields: 0.0]
    opt.run()
    assert not list(Path(folder).glob("*.mat"))
    assert "Skipping MATLAB configuration export" in messages.getvalue()
    # Ratio scoring wraps goal_fun while opt.goal itself remains a native string.
    opt.goal = ["mean"]
    opt._candidate_recorder = SimpleNamespace(
        config={"optimize_current_ratio": True},
        finalize=lambda accepted: setattr(accepted, "_accepted_candidate_valid", True))
    opt.run()
    assert not list(Path(folder).glob("*.mat"))
    del opt._candidate_recorder
    module.logger.removeHandler(handler)
assert opt.optim_funvalue == 0.0
assert np.array_equal(opt.optim_parameters, [0.0])

# A useful finite candidate at an iteration cap is not solver convergence.
opt._optimizer_options_std["maxiter"] = 0
opt.run(save_mat=False)
assert opt.optim_funvalue == 0.0
assert opt.optimizer_termination["global"]["success"] is False
assert opt.optimizer_termination["global"]["iterations"] == 0
assert "Maximum number" in opt.optimizer_termination["global"]["message"]


# Invalid geometry must not survive even if an optimizer returns a finite penalty.
opt.n_sim = 0
opt.goal_fun = lambda x: 2.0
opt.run(save_mat=False)
assert np.isinf(opt.optim_funvalue)

pair = ElectrodeArrayPair()
pair.radius = [0]
pair.length_x = [12.0]
pair.length_y = [8.0]
pair.current = [0.002, -0.002]
pair._prepare()
pose = np.eye(4)
pose[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
pose[:3, 3] = [11, 23, 37]
for array in pair._electrode_arrays:
    for electrode in array.electrodes:
        electrode.posmat = pose.copy()
session = create_tdcs_session_from_array(pair, "fixture.msh", "fixture-output", thickness=[5.0, 2.0])
for electrode in session.poslists[0].electrode:
    assert electrode.thickness == [5.0, 2.0]
    assert list(electrode.dimensions) == [12.0, 8.0]
    assert np.array_equal(electrode.centre, [11, 23, 37])
    assert np.array_equal(electrode.pos_ydir, [-9, 23, 37])
"""


def test_real_scipy_mutation_validity_and_simnibs_pose_contract():
    root = Path(__file__).resolve().parents[2]
    probe = subprocess.run(
        [sys.executable, "-c", "import simnibs"], capture_output=True, text=True
    )
    if probe.returncode:
        pytest.skip(
            "real SimNIBS unavailable; run this test with simnibs_python in the image"
        )
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT], cwd=root, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
