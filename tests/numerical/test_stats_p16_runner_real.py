"""Group statistics runners end to end with the real libraries (p16, 2026-10-22).

The host tests (``tests/test_stats_corr_alignment.py``, ``test_stats_cluster_sign.py``,
``test_stats_cluster_bookkeeping.py``, ``test_stats_null_plot.py``) replace the NIfTI loader.
Here the data path is real: subjects are NIfTI files written with nibabel into a scratch
project and ``tit.stats.nifti`` reads them. The two figures are recorded, not drawn: this leg
keeps pandas mocked, which real seaborn cannot import around (the figure's content is pinned on
the host by ``tests/test_stats_null_plot.py``).

Pins:

* a correlation listing one subject twice gives each row its own effect size
  (``analysis_summary.txt``), and a planted ``r ~ -1`` block reports ``peak_r`` = its most
  negative ``r`` (independent reference: ``np.corrcoef`` per voxel) under a summary that names
  the two-sided test;
* two touching opposite-sign clusters are two summary entries with their mass and p, and each
  centre equals ``nibabel.affines.apply_affine`` of the block centroid (a second
  implementation of the affine map);
* a run with no candidate cluster asks for no null-distribution figure; one with candidates
  does, with the configured alpha.

Run (container): ``simnibs_python -m pytest tests/numerical/test_stats_p16_runner_real.py -q``.
"""

import os
import re

import numpy as np
import pytest

pytestmark = pytest.mark.unit

AFFINE = np.array(
    [
        [2.0, 0.25, 0.0, -20.0],
        [0.0, 2.0, 0.5, -30.0],
        [0.1, 0.0, 2.0, -10.0],
        [0, 0, 0, 1],
    ]
)


def _write(pm, sid, sim, data):
    import nibabel as nib

    folder = os.path.join(pm.simulation(sid, sim), "TI", "niftis")
    os.makedirs(folder, exist_ok=True)
    nib.save(
        nib.Nifti1Image(data.astype(np.float32), AFFINE),
        os.path.join(folder, f"grey_{sim}_TI_MNI_MNI_TI_max.nii.gz"),
    )


@pytest.fixture
def seeded(monkeypatch):
    """Reproducible permutation draws; returns the list of null-figure requests."""
    import tit.stats.permutation as perm

    figures = []
    monkeypatch.setattr(
        perm, "plot_permutation_null_distribution", lambda *a, **k: figures.append(k)
    )
    monkeypatch.setattr(
        perm, "plot_cluster_size_mass_correlation", lambda *a, **k: None
    )
    state = np.random.get_state()
    np.random.seed(20261022)
    yield figures
    np.random.set_state(state)


def test_correlation_rows_and_signed_peak(init_pm, seeded):
    from tit.stats import CorrelationConfig, run_correlation

    rng = np.random.default_rng(0)
    block = (slice(3, 7), slice(3, 7), slice(3, 7))
    # (subject, simulation, effect): s1 appears twice with different effects.
    rows = [("s1", "A", 1.0), ("s1", "B", 5.0), ("s2", "A", 2.0)]
    rows += [(f"s{i}", "A", float(i)) for i in range(3, 7)]
    effects = np.array([e for _, _, e in rows])
    stack = []
    for sid, sim, e in rows:
        data = np.ones((10, 10, 10))
        data[block] = 10.0 - e + rng.random((4, 4, 4)) * 1e-2
        _write(init_pm, sid, sim, data)
        stack.append(data.astype(np.float32))
    voxels = np.stack(stack, axis=-1)[block].reshape(-1, len(rows)).astype(np.float64)
    r_ref = np.array([np.corrcoef(v, effects)[0, 1] for v in voxels])

    cfg = CorrelationConfig(
        analysis_name="p16_corr",
        subjects=[CorrelationConfig.Subject(s, sim, e) for s, sim, e in rows],
        n_permutations=199,
        n_jobs=1,
        use_weights=False,
    )
    result = run_correlation(cfg)
    with open(os.path.join(result.output_dir, "analysis_summary.txt")) as fh:
        summary = fh.read()
    lines = summary.splitlines()

    start = lines.index("Per-Subject Effect Sizes:")
    assert lines[start + 1 : start + 1 + len(rows)] == [
        f"  {s}: {e:.4f}" for s, _, e in rows
    ]
    (cluster,) = result.clusters
    assert cluster["size"] == 64
    assert cluster["peak_r"] == pytest.approx(r_ref.min(), abs=1e-6)
    assert cluster["mean_r"] == pytest.approx(r_ref.mean(), abs=1e-6)
    assert "positive correlations only" not in summary
    assert "Alternative hypothesis: two-sided" in lines
    assert [f["alternative"] for f in seeded] == ["two-sided"]


def _group_subjects(init_pm, blocks, name_offset=0):
    from tit.stats import GroupComparisonConfig

    rng = np.random.default_rng(1)
    subjects = []
    for i in range(10):
        responder = i < 5
        data = np.ones((12, 12, 12))
        for region, (resp_value, non_value) in blocks:
            data[region] = (resp_value if responder else non_value) + rng.random(
                (4, 4, 4)
            ) * 0.01
        sid = f"g{i + name_offset}"
        _write(init_pm, sid, "T", data)
        subjects.append(GroupComparisonConfig.Subject(sid, "T", int(responder)))
    return subjects


def test_touching_clusters_are_listed_separately(init_pm, seeded):
    import nibabel as nib

    from tit.stats import GroupComparisonConfig, run_group_comparison

    pos = (slice(2, 6), slice(3, 7), slice(3, 7))
    neg = (slice(6, 10), slice(3, 7), slice(3, 7))
    subjects = _group_subjects(init_pm, [(pos, (5.0, 1.0)), (neg, (1.0, 6.0))])
    cfg = GroupComparisonConfig(
        analysis_name="p16_touch",
        subjects=subjects,
        n_permutations=199,
        n_jobs=1,
        cluster_threshold=0.01,
    )
    result = run_group_comparison(cfg)
    with open(os.path.join(result.output_dir, "analysis_summary.txt")) as fh:
        lines = fh.read().splitlines()

    assert result.n_significant_clusters == 2 == len(result.clusters)
    assert "Number of Clusters: 2" in lines
    entries = [line for line in lines if re.match(r"\d+\. Cluster \d+: ", line)]
    assert len(entries) == 2
    masses = []
    for line in entries:
        m = re.fullmatch(r"\d+\. Cluster \d+: 64 voxels, mass = (\S+), p = (\S+)", line)
        assert m, line
        masses.append(float(m.group(1)))
        assert float(m.group(2)) < cfg.alpha
    assert sorted(np.sign(masses)) == [-1.0, 1.0]
    assert abs(masses[0]) >= abs(masses[1])  # header: by |cluster mass|, largest first

    want = sorted(
        tuple(np.round(nib.affines.apply_affine(AFFINE, c), 6))
        for c in ([3.5, 4.5, 4.5], [7.5, 4.5, 4.5])
    )
    got = sorted(tuple(np.round(c["center_mni"], 6)) for c in result.clusters)
    assert got == want
    assert [f["alpha"] for f in seeded] == [cfg.alpha]


def test_no_candidate_cluster_writes_no_null_figure(init_pm, seeded):
    from tit.stats import GroupComparisonConfig, run_group_comparison

    subjects = _group_subjects(init_pm, [], name_offset=100)
    cfg = GroupComparisonConfig(
        analysis_name="p16_none",
        subjects=subjects,
        n_permutations=20,
        n_jobs=1,
        cluster_threshold=1e-12,
    )
    # A background identical across subjects is degenerate everywhere; add per-subject noise.
    rng = np.random.default_rng(2)
    for s in subjects:
        _write(init_pm, s.subject_id, "T", 1.0 + rng.random((12, 12, 12)))
    result = run_group_comparison(cfg)

    assert result.n_significant_clusters == 0
    assert seeded == []
    with open(os.path.join(result.output_dir, "analysis_summary.txt")) as fh:
        assert "no candidate clusters; threshold not computed" in fh.read()
