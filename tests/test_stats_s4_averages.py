"""The stats run's own average / difference maps average only where every subject has a field.

A 0 in a subject's map is outside its warped grey matter, not a field value (the same rule as
the voxel test and ``python -m tit.stats.nifti_average``). ``average_responders`` /
``average_non_responders`` / ``difference_map`` (group comparison) and ``average_efield``
(correlation) took a plain ``np.mean``, so a voxel one subject lacked came out as a mean shrunk
by that zero, and a difference of two such means mixed coverage with field.

Expected values are ``np.mean`` over the covered voxels computed here from the arrays the test
feeds in, never read back from the code under test.

Run: ``.venv/bin/python -m pytest tests/test_stats_s4_averages.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from tests.stats_real_scipy import real_scipy  # noqa: F401  (fixture)
from tests.test_stats_cluster_bookkeeping import _config, _groups, _patch_runner


def test_covered_mean_is_zero_where_any_subject_lacks_a_value():
    from tit.stats.nifti import covered_mean

    data = np.array([[[[2.0, 4.0, 6.0]], [[2.0, 0.0, 6.0]]]], dtype=np.float32)
    mean, covered = covered_mean(data)
    assert mean.dtype == np.float32
    np.testing.assert_array_equal(covered, [[[True], [False]]])
    np.testing.assert_allclose(mean, [[[4.0], [0.0]]])


def test_group_comparison_maps_average_only_the_covered_voxels(
    real_scipy, init_pm, monkeypatch  # noqa: F811
):
    resp, non = _groups()
    lacks_resp, lacks_non = (0, 0, 0), (1, 1, 1)  # inside the constant background
    resp[lacks_resp + (1,)] = 0.0  # responder 1 has no field at this voxel
    non[lacks_non + (2,)] = 0.0
    perm = _patch_runner(monkeypatch, (resp, non), [])
    saved = {}
    monkeypatch.setattr(
        perm,
        "_save_nifti",
        lambda data, template, path: saved.__setitem__(path.rsplit("/", 1)[-1], data),
    )
    perm.run_group_comparison(_config(cluster_threshold=0.01))

    avg_r, avg_n = saved["average_responders.nii.gz"], saved["average_non_responders.nii.gz"]
    diff = saved["difference_map.nii.gz"]
    assert avg_r[lacks_resp] == 0 and avg_n[lacks_non] == 0
    # A voxel either group lacks has no difference; elsewhere it is mean minus mean.
    assert diff[lacks_resp] == 0 and diff[lacks_non] == 0
    keep = np.ones(resp.shape[:3], bool)
    keep[lacks_resp] = keep[lacks_non] = False
    np.testing.assert_allclose(avg_r[keep], resp.mean(-1)[keep], rtol=1e-6)
    np.testing.assert_allclose(avg_n[keep], non.mean(-1)[keep], rtol=1e-6)
    np.testing.assert_allclose(
        diff[keep], (resp.mean(-1) - non.mean(-1))[keep], rtol=1e-5, atol=1e-6
    )
    # the shrunk plain mean the old code wrote there: (1 + 0 + 1) / 3
    assert resp.mean(-1)[lacks_resp] == pytest.approx(2 / 3)


def test_correlation_average_efield_averages_only_the_covered_voxels(
    real_scipy, init_pm, monkeypatch  # noqa: F811
):
    import tit.stats.permutation as perm
    from tit.stats.config import CorrelationConfig

    rng = np.random.default_rng(1)
    data = (rng.random((4, 4, 4, 4)) + 0.1).astype(np.float32)
    lacks = (0, 0, 0)
    data[lacks + (2,)] = 0.0
    template = SimpleNamespace(affine=np.eye(4), header=None)
    saved = {}
    monkeypatch.setattr(
        perm, "load_group_data_ti_toolbox", lambda d, **_: (data, template, ["a"] * 4)
    )
    monkeypatch.setattr(
        perm,
        "_save_nifti",
        lambda arr, template, path: saved.__setitem__(path.rsplit("/", 1)[-1], arr),
    )
    monkeypatch.setattr(perm, "plot_permutation_null_distribution", lambda *a, **k: None)
    monkeypatch.setattr(perm, "plot_cluster_size_mass_correlation", lambda *a, **k: None)
    subjects = [
        CorrelationConfig.Subject(f"s{i}", "T", float(i), 1.0) for i in range(4)
    ]
    perm.run_correlation(
        CorrelationConfig(
            analysis_name="avg", subjects=subjects, n_permutations=20, n_jobs=1
        )
    )

    avg = saved["average_efield.nii.gz"]
    assert avg[lacks] == 0
    other = np.ones(data.shape[:3], bool)
    other[lacks] = False
    np.testing.assert_allclose(avg[other], data.mean(-1)[other], rtol=1e-6)
