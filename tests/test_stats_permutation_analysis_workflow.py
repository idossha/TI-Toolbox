#!/usr/bin/env simnibs_python
"""
Deeper workflow tests for tit/stats/permutation_analysis.py

We exercise the group_comparison and correlation workflows far enough to cover:
- diagnostics / observed cluster labeling
- plot function calls
- NIfTI output creation (nib.Nifti1Image + nib.save)
- summary file writing

All heavy statistical computations are mocked.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _template_img(shape=(3, 3, 1)):
    # mimic nibabel image interface used (affine/header)
    return SimpleNamespace(affine=np.eye(4), header=MagicMock())


@pytest.mark.unit
def test_group_comparison_workflow_writes_outputs(tmp_path: Path):
    from tit.stats import permutation_analysis as pa

    outdir = tmp_path / "out"
    outdir.mkdir()
    cfg = pa.DEFAULT_CONFIG_GROUP_COMPARISON.copy()
    cfg.update(
        dict(
            n_permutations=2,
            n_jobs=1,
            cluster_threshold=0.05,
            atlas_files=[],
        )
    )

    # small responder/non-responder data
    responders = np.zeros((3, 3, 1, 2), dtype=float)
    non_resp = np.zeros((3, 3, 1, 2), dtype=float)
    responders[1, 1, 0, :] = [1.0, 2.0]
    non_resp[1, 1, 0, :] = [0.0, 0.0]

    pvals = np.ones((3, 3, 1), dtype=float)
    pvals[1, 1, 0] = 0.001
    tstats = np.zeros((3, 3, 1), dtype=float)
    tstats[1, 1, 0] = 5.0
    valid = np.ones((3, 3, 1), dtype=bool)

    sig_mask = np.zeros((3, 3, 1), dtype=np.uint8)
    sig_mask[1, 1, 0] = 1
    sig_clusters = [{"id": 1, "size": 1, "stat_value": 5.0, "p_value": 0.01}]

    fake_logger = MagicMock()

    with (
        patch.object(
            pa,
            "load_subject_data",
            return_value=(
                responders,
                non_resp,
                _template_img(),
                ["r1", "r2"],
                ["n1", "n2"],
            ),
        ),
        patch.object(pa, "ttest_voxelwise", return_value=(pvals, tstats, valid)),
        patch.object(
            pa,
            "cluster_based_correction",
            return_value=(
                sig_mask,
                1.0,
                sig_clusters,
                np.array([1.0, 2.0]),
                [],
                {"sizes": np.array([1]), "masses": np.array([5.0])},
            ),
        ),
        patch.object(
            pa,
            "cluster_analysis",
            return_value=[{"cluster_id": 1, "size": 1, "center_mni": (0.0, 0.0, 0.0)}],
        ),
        patch.object(pa, "plot_permutation_null_distribution") as plot_null,
        patch.object(pa, "plot_cluster_size_mass_correlation") as plot_corr,
        patch.object(pa, "atlas_overlap_analysis", return_value={}),
        patch.object(pa, "nib") as nib,
    ):

        nib.Nifti1Image.side_effect = lambda data, affine, header: (
            data,
            affine,
            header,
        )
        nib.save = MagicMock()

        res = pa._run_group_comparison_analysis(
            subject_configs=[],
            CONFIG=cfg,
            output_dir=str(outdir),
            logger=fake_logger,
            log_callback=lambda m: None,
            analysis_start_time=0.0,
            log_file=str(outdir / "log.txt"),
            stop_callback=None,
        )

    assert res["output_dir"] == str(outdir)
    # plots called
    plot_null.assert_called_once()
    plot_corr.assert_called_once()
    # several nifti saves should happen
    assert nib.save.call_count >= 4
    # summary file should be written
    assert (outdir / "analysis_summary.txt").exists()


@pytest.mark.unit
def test_correlation_workflow_writes_outputs(tmp_path: Path):
    from tit.stats import permutation_analysis as pa

    outdir = tmp_path / "out"
    outdir.mkdir()
    cfg = pa.DEFAULT_CONFIG_CORRELATION.copy()
    cfg.update(dict(n_permutations=2, n_jobs=1, cluster_threshold=0.05, atlas_files=[]))

    # subject_data (x,y,z,n_subjects)
    subject_data = np.zeros((3, 3, 1, 3), dtype=float)
    subject_data[1, 1, 0, :] = [0.0, 1.0, 2.0]
    eff = np.array([0.1, 0.2, 0.3], dtype=float)
    weights = np.array([1.0, 1.0, 1.0], dtype=float)

    r = np.zeros((3, 3, 1), dtype=float)
    t = np.zeros((3, 3, 1), dtype=float)
    p = np.ones((3, 3, 1), dtype=float)
    r[1, 1, 0] = 0.9
    t[1, 1, 0] = 3.0
    p[1, 1, 0] = 0.001
    valid = np.ones((3, 3, 1), dtype=bool)

    sig_mask = np.zeros((3, 3, 1), dtype=np.uint8)
    sig_mask[1, 1, 0] = 1
    sig_clusters = [{"id": 1, "size": 1, "stat_value": 3.0, "p_value": 0.01}]

    fake_logger = MagicMock()

    with (
        patch.object(
            pa,
            "load_subject_data",
            return_value=(
                subject_data,
                eff,
                weights,
                _template_img(),
                ["s1", "s2", "s3"],
            ),
        ),
        patch.object(pa, "correlation_voxelwise", return_value=(r, t, p, valid)),
        patch.object(
            pa,
            "correlation_cluster_correction",
            return_value=(
                sig_mask,
                1.0,
                sig_clusters,
                np.array([1.0, 2.0]),
                [],
                {"sizes": np.array([1]), "masses": np.array([3.0])},
            ),
        ),
        patch.object(
            pa,
            "cluster_analysis",
            return_value=[{"cluster_id": 1, "size": 1, "center_mni": (0.0, 0.0, 0.0)}],
        ),
        patch.object(pa, "plot_permutation_null_distribution") as plot_null,
        patch.object(pa, "plot_cluster_size_mass_correlation") as plot_corr,
        patch.object(pa, "atlas_overlap_analysis", return_value={}),
        patch.object(pa, "nib") as nib,
    ):

        nib.Nifti1Image.side_effect = lambda data, affine, header: (
            data,
            affine,
            header,
        )
        nib.save = MagicMock()

        res = pa._run_correlation_analysis(
            subject_configs=[],
            CONFIG=cfg,
            output_dir=str(outdir),
            logger=fake_logger,
            log_callback=lambda m: None,
            analysis_start_time=0.0,
            log_file=str(outdir / "log.txt"),
            stop_callback=None,
        )

    assert res["output_dir"] == str(outdir)
    plot_null.assert_called_once()
    plot_corr.assert_called_once()
    assert nib.save.call_count >= 5  # mask, r, t, p, thresholded r, avg field etc.
    assert (outdir / "analysis_summary.txt").exists()
