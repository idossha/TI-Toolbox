"""Correlation effect sizes and weights follow config rows, not subject ids (p16, 2026-10-22).

Pins: a correlation whose config lists one subject twice (two simulations of one person) gives
each row its own effect size and weight -- in the vector the voxelwise correlation and the
permutation engine see, in ``analysis_summary.txt``, and identically in the volume and
fsaverage paths. The v3.1.x volume path looked effect sizes up by ``subject_id``, so both rows
of ``101`` got the last row's 5.0 (and its weight), while the surface path was positional.

Expected values are the config rows themselves (row order is the loader's column order:
``tit.stats.nifti.load_group_data_ti_toolbox`` stacks one volume per row). Real scipy runs the
statistics (``tests/stats_real_scipy.py``); the loader is replaced by a synthetic array.

Run: ``.venv/bin/python -m pytest tests/test_stats_corr_alignment.py -q -p no:cacheprovider``.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from tests.stats_real_scipy import (  # noqa: F401  (fixtures)
    chain_adjacency,
    graph_components,
    real_scipy,
)

# (subject_id, simulation, effect_size, weight) -- 101 appears twice with different values.
ROWS = [
    ("101", "A", 1.0, 1.0),
    ("101", "B", 5.0, 2.0),
    ("LA", "A", 2.0, 3.0),
    ("CHN", "A", 3.0, 4.0),
]


def _config(**kw):
    from tit.stats.config import CorrelationConfig

    subjects = [CorrelationConfig.Subject(s, sim, e, w) for s, sim, e, w in ROWS]
    return CorrelationConfig(
        analysis_name=kw.pop("analysis_name", "dup"),
        subjects=subjects,
        n_permutations=20,
        n_jobs=1,
        **kw,
    )


@pytest.fixture
def volume_run(real_scipy, init_pm, monkeypatch):
    """Run the volume correlation on a synthetic (4,4,4,4) stack; record what the stats saw."""
    import tit.stats.permutation as perm

    rng = np.random.default_rng(7)
    data = (rng.random((4, 4, 4, len(ROWS))) + 0.1).astype(np.float32)
    template = SimpleNamespace(affine=np.eye(4), header=None)
    loaded_rows = []

    def fake_load(subject_dicts, **_):
        loaded_rows.extend(
            (d["subject_id"], d["simulation_name"]) for d in subject_dicts
        )
        return data, template, [d["subject_id"] for d in subject_dicts]

    seen = {}
    real_corr = perm.correlation_voxelwise
    # The class the runner holds: an older test module may have reloaded the engine module.
    real_correct = perm.PermutationEngine.correct_correlation

    def spy_corr(subject_data, effect_sizes, weights=None, **kw):
        seen["voxelwise"] = (
            np.array(effect_sizes),
            None if weights is None else np.array(weights),
        )
        return real_corr(subject_data, effect_sizes, weights=weights, **kw)

    def spy_correct(self, subject_data, effect_sizes, **kw):
        w = kw.get("weights")
        seen["engine"] = (np.array(effect_sizes), None if w is None else np.array(w))
        return real_correct(self, subject_data, effect_sizes, **kw)

    monkeypatch.setattr(perm, "load_group_data_ti_toolbox", fake_load)
    monkeypatch.setattr(perm, "correlation_voxelwise", spy_corr)
    monkeypatch.setattr(perm.PermutationEngine, "correct_correlation", spy_correct)
    monkeypatch.setattr(perm, "_save_nifti", lambda *a, **k: None)
    monkeypatch.setattr(
        perm, "plot_permutation_null_distribution", lambda *a, **k: None
    )
    monkeypatch.setattr(
        perm, "plot_cluster_size_mass_correlation", lambda *a, **k: None
    )

    def run(**kw):
        result = perm.run_correlation(_config(**kw))
        return result, seen, loaded_rows

    return run


def test_volume_effect_sizes_and_weights_follow_config_rows(volume_run):
    _, seen, loaded = volume_run(use_weights=True)

    assert loaded == [(s, sim) for s, sim, _, _ in ROWS]
    expected_effects = np.array([e for _, _, e, _ in ROWS])
    expected_weights = np.array([w for _, _, _, w in ROWS])
    for stage in ("voxelwise", "engine"):
        effects, weights = seen[stage]
        np.testing.assert_array_equal(effects, expected_effects, err_msg=stage)
        np.testing.assert_array_equal(weights, expected_weights, err_msg=stage)


def test_summary_lists_each_row_with_its_own_effect_and_weight(volume_run):
    result, _, _ = volume_run(use_weights=True)

    with open(f"{result.output_dir}/analysis_summary.txt") as fh:
        lines = fh.read().splitlines()
    start = lines.index("Per-Subject Effect Sizes:")
    listed = lines[start + 1 : start + 1 + len(ROWS)]
    assert listed == [f"  {s}: {e:.4f}, weight={w:.2f}" for s, _, e, w in ROWS]


def test_unweighted_summary_lists_rows_in_config_order(volume_run):
    result, seen, _ = volume_run(use_weights=False)

    assert seen["voxelwise"][1] is None
    with open(f"{result.output_dir}/analysis_summary.txt") as fh:
        lines = fh.read().splitlines()
    start = lines.index("Per-Subject Effect Sizes:")
    assert lines[start + 1 : start + 1 + len(ROWS)] == [
        f"  {s}: {e:.4f}" for s, _, e, _ in ROWS
    ]


def test_volume_and_surface_paths_see_the_same_effect_vector(
    volume_run, graph_components, monkeypatch
):
    """The fsaverage path was already positional; the volume path must agree with it."""
    import tit.stats.surface as surface
    from tit.stats.config import CorrelationConfig

    _, seen, _ = volume_run(use_weights=True)

    n_vertices = 12
    rng = np.random.default_rng(3)
    monkeypatch.setattr(
        surface,
        "load_group_surface_data",
        lambda pairs, field, spacing: (
            rng.random((n_vertices, len(pairs))) + 0.1,
            [p[0] for p in pairs],
        ),
    )
    monkeypatch.setattr(
        surface, "build_fsaverage_adjacency", lambda s: chain_adjacency(n_vertices)
    )
    calls = []
    real_corr = surface.correlation

    def spy(data, eff, **kw):
        calls.append((np.array(eff), kw.get("weights")))
        return real_corr(data, eff, **kw)

    monkeypatch.setattr(surface, "correlation", spy)
    cfg = _config(analysis_name="dup_surface", use_weights=True)
    cfg.space = CorrelationConfig.AnalysisSpace.FSAVERAGE
    surface.run_surface_correlation(cfg)

    surface_effects, surface_weights = calls[0]  # the observed (unpermuted) map
    np.testing.assert_array_equal(surface_effects, seen["voxelwise"][0])
    np.testing.assert_array_equal(np.asarray(surface_weights), seen["voxelwise"][1])
