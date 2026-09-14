"""2026-09-13: real TI metrics and exact replay geometry without a FEM solve.

Run: simnibs_python -m pytest tests/numerical/test_flex_candidate_metrics.py -q.
A clean subprocess avoids the host suite's SimNIBS mocks. Parallel carriers
have envelope 2*min(amplitude1, amplitude2), an independent analytical oracle.
Real dataset timing/RSS budgets belong to the serial benchmark, not this test.
"""

import subprocess
import sys
import textwrap

import pytest


def test_real_envelopes_observation_split_invariance_and_scale_law(tmp_path):
    probe = subprocess.run(
        [sys.executable, "-c", "import simnibs"], capture_output=True, text=True
    )
    if probe.returncode:
        pytest.skip("real SimNIBS unavailable; run with simnibs_python in the image")
    source = r"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from simnibs.optimization.tes_flex_optimization.tes_flex_optimization import postprocess_e
from tit.opt.flex.candidates import CandidateRecorder, summarize_fields
from tit.opt.flex.objectives import install_ratio_search, make_objective, threshold_free_focality

# Parallel carriers: envelope is twice the smaller carrier amplitude.
a = np.array([[1.,0,0], [2.,0,0], [3.,0,0]])
b = np.array([[3.,0,0], [2.,0,0], [1.,0,0]])
envelope = postprocess_e(e=a, e2=b, dirvec=None, type="max_TI")
np.testing.assert_allclose(envelope, [2.,4.,2.], atol=1e-14)
metrics = summarize_fields([[envelope, np.full(7, 1.)]])
assert abs(metrics["roi_mean"] - 8./3.) < 1e-14
assert abs(metrics["target_background_ratio"] - 8./3.) < 1e-14
assert summarize_fields([[envelope, np.zeros(7)]])["target_background_ratio"] is None
# Authored nonuniform oracle distinguishes the three objectives and p95 from mean.
# ROI 0..1000 has arithmetic mean 500 and linear 99.9th percentile 999.
# Background [1,1,1,5] has mean2, p95=4.4, max5.
roi = np.arange(1001, dtype=float)
background = np.array([1.,1.,1.,5.])
assert make_objective("mean")(roi, background) == -500.
# Allow only floating-point interpolation roundoff at the percentile.
assert abs(make_objective("max")(roi, background) + 999.) < 1e-12
assert make_objective("focality_tf")(roi, background) == -250.
assert make_objective("focality_tf", intensity_weight=1.)(roi, background) == -125000.
assert summarize_fields([[roi, background]])["target_background_ratio"] == 250.
# Pure focality prefers2/.5 over6/2; intensity emphasis reverses that ranking.
a_roi, a_bg = np.array([2.]), np.array([.5])
b_roi, b_bg = np.array([6.]), np.array([2.])
assert make_objective("focality_tf", intensity_weight=0.)(a_roi,a_bg) < make_objective("focality_tf", intensity_weight=0.)(b_roi,b_bg)
assert make_objective("focality_tf", intensity_weight=1.)(a_roi,a_bg) > make_objective("focality_tf", intensity_weight=1.)(b_roi,b_bg)
# A dimensionless contrast must be invariant under a change of current units;
# the intensity-weighted variant deliberately follows the specified power law.
for weight in [0., .5, 1.]:
    baseline = threshold_free_focality(envelope, np.ones(7), weight)
    scaled = threshold_free_focality(4*envelope, 4*np.ones(7), weight)
    assert abs(scaled / baseline - 4**weight) < 1e-12
assert threshold_free_focality(np.zeros(3), np.ones(7)) == 0
for background in [np.zeros(7), np.full(7,1e-13), -np.ones(7), np.full(7,np.nan), np.full(7,np.inf)]:
    assert threshold_free_focality(envelope, background) == 0
assert threshold_free_focality(np.array([-1.,4.,2.]), np.ones(7)) == 0

raw = [[a, np.tile([.1,0,0], (7,1))], [b, np.tile([9.,0,0], (7,1))]]
def build(observe):
    opt = SimpleNamespace(n_test=0,n_sim=0, e_postproc="max_TI",
         _goal_dir=[None,None], electrode_pos_opt=None,
         electrode=[],get_electrode_pos_from_array=lambda x:x,
         get_nodes_electrode=lambda **kwargs:None,
         update_field=lambda **kwargs: raw if observe else [[a],[b]],
         _observation_only_non_roi=observe)
    install_ratio_search(opt, make_objective("mean"), base_mA=2., ratios=[(1.,3.),(2.,2.),(3.,1.)])
    return opt
baseline, observed = build(False), build(True)
assert baseline.goal_fun([.1,.2,.3]) == observed.goal_fun([.1,.2,.3])
assert baseline._best_current_split == observed._best_current_split
assert baseline.n_sim == observed.n_sim == 1
assert len(observed._candidate_postprocessed[0]) == 2
# Real envelope row counts ensure an observation really was computed.
assert observed._candidate_postprocessed[0][1].shape == (7,)

# Production builder dispatch and recorder: bypass only mesh/FEM preparation,
# supplying authored raw parallel-carrier fields. No score path is mocked.
# Positive envelope1..1001: mean501,p99.9=1000, backgroundmean2.
# Both-zero carrier vectors are excluded here: upstream maxTI has a singular
# normalization there; nonfinite rejection is covered independently above.
from tit.opt.config import FlexConfig
from tit.paths import get_path_manager
from tit.opt.flex.builder import build_optimization
from tit.opt.flex.runtime import integration_module
get_path_manager(sys.argv[1])
cls = integration_module().TesFlexOptimization
original_update = cls.update_field
def authored_field(self, **kwargs):
    samples = [np.arange(1,1002, dtype=float)]
    if self._n_roi == 2:
        samples.append(np.array([1.,1.,1.,5.]))
    # Identical parallel carriers at half desired envelope amplitude.
    fields = [np.column_stack((x/2, np.zeros_like(x), np.zeros_like(x))) for x in samples]
    return [fields, [x.copy() for x in fields]]
cls.update_field = authored_field
try:
    for goal, weight, expected in [("mean",0.,-501.), ("max",0.,-1000.), ("focality_tf",0.,-250.5), ("focality_tf",1.,-125500.5)]:
        for ratio in [False, True]:
            folder = Path(sys.argv[1])/f"builder-{goal}-{weight}-{ratio}"
            cfg = FlexConfig(subject_id="fixture",goal=goal,postproc="max_TI",current_mA=2.,
                electrode=FlexConfig.ElectrodeConfig(),roi=FlexConfig.SphericalROI(x=0,y=0,z=0,radius=5),
                intensity_weight=weight,optimize_current_ratio=ratio,ratio_levels=3,
                output_folder=str(folder))
            built = build_optimization(cfg)
            built._n_roi = 2 if goal == "focality_tf" else 1
            built._goal_dir = [None]*built._n_roi
            built.e_postproc = ["max_TI"]*built._n_roi
            if isinstance(built.goal,str): built.goal = [built.goal]
            built.weights = np.ones(built._n_roi)
            built.goal_fun_value = [[]]
            built.AUC = [[]]
            built.integral_focality = [[]]
            built.track_focality = False
            built.get_electrode_pos_from_array = lambda x: [[np.asarray(x)]]
            for pair in built.electrode:
                pair._prepare()
                for array in pair._electrode_arrays:
                    for electrode in array.electrodes: electrode.posmat = np.eye(4)
            value = built.goal_fun(np.array([.1,.2,.3]))
            # Roundoff only: native99.9 percentile linear interpolation.
            assert abs(value-expected) < 1e-9, (goal,weight,ratio,value,expected)
            assert built._candidate_recorder.valid == 1
            recorded = json.loads((folder/"candidate_geometry.jsonl").read_text())
            assert abs(recorded["objective"]-expected) < 1e-9
            if ratio: assert built._best_current_split == (2.,2.)
finally:
    cls.update_field = original_update

# Recorded physical pose/current reconstitutes the same SimNIBS electrode.
from simnibs.optimization.tes_flex_optimization.electrode_layout import ElectrodeArrayPair, create_tdcs_session_from_array
pairs = []
for _ in range(2):
    pair = ElectrodeArrayPair()
    pair.radius, pair.length_x, pair.length_y = [0], [12.], [8.]
    pair.current = [.002, -.002]
    pair._prepare()
    for array in pair._electrode_arrays:
        for electrode in array.electrodes:
            # SimNIBS's rectangular helper uses a reflected x axis. The
            # recorder must preserve its centre/y/normal and canonicalize x.
            electrode.posmat = np.array([[0.,-1.,0.,11.],[-1.,0.,0.,23.],[0.,0.,1.,37.],[0.,0.,0.,1.]])
    pairs.append(pair)
opt = SimpleNamespace(output_folder=sys.argv[1],electrode=pairs,electrode_pos=[[[.1,.2,.3]]],_candidate_postprocessed=[[envelope]])
config = {"goal":"mean", "electrode":{"shape":"rect","dimensions":[12.,8.],"gel_thickness":5.}}
recorder = CandidateRecorder(opt, config)
recorder.fields_valid = True
recorder.record([.1,.2,.3], -8./3.)
record = json.loads((Path(sys.argv[1])/"candidate_geometry.jsonl").read_text())
for channel, pair in enumerate(pairs):
    for original, saved in zip([e for a in pair._electrode_arrays for e in a.electrodes], record["electrodes"][channel]):
        original.posmat = np.asarray(saved["posmat"])
        assert np.linalg.det(np.asarray(saved["source_posmat"])[:3,:3]) == -1.
        assert np.linalg.det(original.posmat[:3,:3]) == 1.
        assert saved["current_A"] == original.ele_current
    session = create_tdcs_session_from_array(pair, "fixture.msh", "fixture-output", thickness=record["electrodes"][channel][0]["thickness"])
    for electrode in session.poslists[0].electrode:
        assert np.array_equal(electrode.centre, [11.,23.,37.])
        assert np.array_equal(electrode.pos_ydir, [-9.,23.,37.])
        assert list(electrode.dimensions) == [12.,8.]
        assert electrode.thickness == [5.,2.]
"""
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source), str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
