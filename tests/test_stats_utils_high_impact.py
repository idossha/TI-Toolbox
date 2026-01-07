#!/usr/bin/env simnibs_python
"""
High-impact tests for tit/stats/stats_utils.py

These tests aim to cover core statistical utilities with tiny deterministic inputs.
"""

from __future__ import annotations

import numpy as np
import pytest


@pytest.mark.unit
def test_pval_from_histogram_all_tails():
    from tit.stats.stats_utils import pval_from_histogram

    null = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    obs = np.array([1.5, -1.5])

    # two-sided: compare abs
    p2 = pval_from_histogram(obs, null, tail=0)
    assert p2.shape == (2,)
    assert np.all((0 <= p2) & (p2 <= 1))

    # upper: null >= obs
    pu = pval_from_histogram(obs, null, tail=1)
    assert pu[0] == np.mean(null >= 1.5)

    # lower: null <= obs
    pl = pval_from_histogram(obs, null, tail=-1)
    assert pl[1] == np.mean(null <= -1.5)


@pytest.mark.unit
def test_correlation_weighted_and_spearman_preranked_paths():
    from tit.stats.stats_utils import correlation

    # 3 voxels, 5 subjects
    voxel = np.array(
        [
            [0, 1, 2, 3, 4],
            [1, 1, 1, 1, 1],  # constant (std=0) => r=0 via valid_mask
            [4, 3, 2, 1, 0],
        ],
        dtype=float,
    )
    eff = np.array([0, 1, 2, 3, 4], dtype=float)
    w = np.array([1, 2, 3, 4, 5], dtype=float)

    r_w, t_w, p_w = correlation(voxel, eff, correlation_type="pearson", weights=w)
    assert r_w.shape == (3,)
    assert p_w.shape == (3,)
    assert r_w[1] == 0  # constant voxel row

    # Spearman with preranked voxel_data skips rankdata on voxel_data
    voxel_ranked = np.apply_along_axis(lambda x: np.argsort(np.argsort(x)) + 1, 1, voxel)
    r_s, t_s, p_s = correlation(voxel_ranked, eff, correlation_type="spearman", voxel_data_preranked=True)
    assert r_s.shape == (3,)
    assert np.all((0 <= p_s) & (p_s <= 1))


@pytest.mark.unit
def test_correlation_voxelwise_validations_and_masking():
    from tit.stats.stats_utils import correlation_voxelwise

    # shape (x,y,z,n_subjects) = (2,2,1,3)
    data = np.zeros((2, 2, 1, 3), dtype=float)
    data[0, 0, 0, :] = [0.0, 0.0, 1.0]  # valid voxel (non-zero in some subjects)
    effect = np.array([0.1, 0.2, 0.3], dtype=float)

    r, t, p, mask = correlation_voxelwise(data, effect, verbose=False)
    assert mask.sum() == 1
    assert p.shape == (2, 2, 1)

    # Mismatched lengths
    with pytest.raises(ValueError):
        correlation_voxelwise(data, np.array([0.1, 0.2]), verbose=False)

    # Too few subjects
    with pytest.raises(ValueError):
        correlation_voxelwise(np.zeros((1, 1, 1, 2)), np.array([0.1, 0.2]), verbose=False)


@pytest.mark.unit
def test_ttests_alternatives_and_error():
    from tit.stats.stats_utils import ttest_ind, ttest_rel

    # 2 voxels, responders=3, non-responders=3
    test = np.array(
        [
            [1, 1, 1, 0, 0, 0],
            [1, 2, 3, 1, 2, 3],  # identical => t=0
        ],
        dtype=float,
    )
    t, p = ttest_ind(test, n_resp=3, n_non_resp=3, alternative="two-sided")
    assert t.shape == (2,)
    assert p.shape == (2,)

    _t, _p = ttest_ind(test, n_resp=3, n_non_resp=3, alternative="greater")
    _t, _p = ttest_ind(test, n_resp=3, n_non_resp=3, alternative="less")
    with pytest.raises(ValueError):
        ttest_ind(test, n_resp=3, n_non_resp=3, alternative="bogus")

    # Paired: 2 voxels, pairs=3
    paired = np.array(
        [
            [1, 2, 3, 1, 2, 3],
            [1, 1, 1, 0, 0, 0],
        ],
        dtype=float,
    )
    t2, p2 = ttest_rel(paired, n_resp=3, alternative="two-sided")
    assert t2.shape == (2,)
    with pytest.raises(ValueError):
        ttest_rel(paired, n_resp=3, alternative="nope")



