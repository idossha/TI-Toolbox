"""The fsaverage group comparison treats degenerate and paired inputs like the volume path (p16).

Pins (2026-10-22), each against ``tit.stats.engine.ttest_voxelwise`` on the same numbers laid
out as a volume, and against ``scipy.stats.ttest_ind`` as the reference t-test:

(a) 1 responder vs 1 non-responder: every t is ``nan`` (0/0 variance), so no vertex can be
    tested and the run raises "No voxel could be tested" -- v3.1.x reported success with
    0 clusters.
(b) paired test with 2 vs 1 subjects: the run raises "Paired test requires equal sample sizes"
    -- v3.1.x died on a numpy broadcast error.
(c) a vertex block with zero within-group variance and different group means: scipy gives
    ``t = +/-inf`` there; those vertices leave the analysis (t = 0, p = 1 in the map, as the
    volume path writes them), so no ``inf`` reaches a cluster's ``stat_value`` or
    ``null_distribution.csv``; the run log counts only the vertices left to test.

The adjacency is a chain (``tests/stats_real_scipy.chain_adjacency``) and the loader returns a
synthetic matrix, as ``testmap/stats_repro/repro_surface.py`` did; ``surface_stats.msh`` goes
through the host's mocked SimNIBS writer, the CSVs are real files.

Run: ``.venv/bin/python -m pytest tests/test_stats_surface_parity.py -q -p no:cacheprovider``.
"""

import csv
import logging
import warnings

import numpy as np
import pytest

from tests.stats_real_scipy import (  # noqa: F401  (fixtures)
    chain_adjacency,
    graph_components,
    real_scipy,
    seeded_permutations,
)

N_VERTICES = 60
DEGENERATE = slice(10, 20)
EFFECT = slice(40, 50)


def _config(responses, test_type="unpaired", name="parity", n_permutations=40):
    from tit.stats.config import GroupComparisonConfig

    subjects = [
        GroupComparisonConfig.Subject(f"s{i}", "S", r) for i, r in enumerate(responses)
    ]
    return GroupComparisonConfig(
        analysis_name=name,
        subjects=subjects,
        space=GroupComparisonConfig.AnalysisSpace.FSAVERAGE,
        test_type=test_type,
        n_permutations=n_permutations,
        n_jobs=1,
    )


@pytest.fixture
def surface(graph_components, init_pm, monkeypatch):
    """``tit.stats.surface`` with a chain adjacency and a loader returning ``matrix``."""
    import tit.stats.surface as surface

    monkeypatch.setattr(
        surface, "build_fsaverage_adjacency", lambda s: chain_adjacency(N_VERTICES)
    )
    captured = {}
    real_write = surface._write_surface_outputs

    def spy_write(output_dir, config, metadata, maps, *rest):
        captured["maps"] = maps
        return real_write(output_dir, config, metadata, maps, *rest)

    monkeypatch.setattr(surface, "_write_surface_outputs", spy_write)

    def use(matrix):
        monkeypatch.setattr(
            surface,
            "load_group_surface_data",
            lambda pairs, field, spacing: (matrix, [p[0] for p in pairs]),
        )
        return surface, captured

    return use


def _volume_error(resp, non, test_type="unpaired"):
    """The volume path's error for the same data laid out as (N, 1, 1, n)."""
    from tit.stats.engine import ttest_voxelwise

    with pytest.raises(ValueError) as err:
        ttest_voxelwise(
            resp[:, None, None, :],
            non[:, None, None, :],
            test_type=test_type,
            log=logging.getLogger("test"),
        )
    return str(err.value)


def test_one_vs_one_raises_like_the_volume_path(surface):
    rng = np.random.default_rng(1)
    data = rng.random((N_VERTICES, 2)) + 0.1
    mod, _ = surface(data)

    with pytest.raises(ValueError, match="No voxel could be tested") as err:
        mod.run_surface_group_comparison(_config([1, 0], name="one_vs_one"))
    assert str(err.value) == _volume_error(data[:, :1], data[:, 1:])
    assert "zero within-group variance" in str(err.value)


def test_paired_with_unequal_groups_raises_like_the_volume_path(surface):
    rng = np.random.default_rng(2)
    data = rng.random((N_VERTICES, 3)) + 0.1
    mod, _ = surface(data)

    with pytest.raises(ValueError) as err:
        mod.run_surface_group_comparison(
            _config([1, 1, 0], test_type="paired", name="paired_2v1")
        )
    assert str(err.value) == "Paired test requires equal sample sizes: 2 vs 1"
    assert str(err.value) == _volume_error(data[:, :2], data[:, 2:], "paired")


def test_relabelling_that_separates_a_tied_block_adds_no_inf_to_the_null(
    surface, seeded_permutations
):
    """2 vs 2 with a block valued (5, 1 | 5, 1): observed t = 0, finite, so it stays in the
    analysis; one relabelling in three puts both 5s in one group, where scipy's t is inf.
    Such a permutation must not put an infinite cluster mass into the null."""
    rng = np.random.default_rng(4)
    data = rng.random((N_VERTICES, 4)) + 0.1
    data[20:26] = [5.0, 1.0, 5.0, 1.0]
    mod, _ = surface(data)

    result = mod.run_surface_group_comparison(_config([1, 1, 0, 0], name="tied"))

    with open(f"{result.output_dir}/null_distribution.csv") as fh:
        null = [float(r["max_cluster_stat"]) for r in csv.DictReader(fh)]
    assert len(null) == 40
    assert all(np.isfinite(null))


def _degenerate_fixture():
    """5 vs 5: a degenerate block (constant 5 vs constant 1) and a real effect block."""
    rng = np.random.default_rng(3)
    data = rng.random((N_VERTICES, 10)) + 0.1
    data[DEGENERATE, :5] = 5.0
    data[DEGENERATE, 5:] = 1.0
    data[EFFECT, :5] = 5.0 + rng.random((10, 5)) * 0.01
    data[EFFECT, 5:] = 1.0 + rng.random((10, 5)) * 0.01
    return data


def test_reference_t_test_is_infinite_on_the_degenerate_block(real_scipy):
    """The fixture really is degenerate by scipy's own reading, not only by ours."""
    data = _degenerate_fixture()
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter(
            "ignore"
        )  # scipy warns about the zero variance it is given
        t = real_scipy.ttest_ind(data[DEGENERATE, :5], data[DEGENERATE, 5:], axis=1)
    assert np.all(np.isposinf(t.statistic))


def test_degenerate_vertices_leave_the_analysis(surface, seeded_permutations):
    from tit.stats.engine import ttest_voxelwise

    data = _degenerate_fixture()
    mod, captured = surface(data)
    result = mod.run_surface_group_comparison(
        _config([1] * 5 + [0] * 5, name="degenerate")
    )

    # Something significant exists, so "no inf" below is not vacuous.
    assert result.n_significant_clusters >= 1
    assert all(np.isfinite(c["stat_value"]) for c in result.clusters)
    clustered = {v for c in result.clusters for v in c["vertices"]}
    assert clustered.isdisjoint(range(N_VERTICES)[DEGENERATE])
    assert set(range(N_VERTICES)[EFFECT]) <= clustered
    # Every fixture vertex has data (values >= 0.1); only the DEGENERATE block is excluded, so
    # the run tests N_VERTICES - 10 vertices, and its log says so.
    n_tested = N_VERTICES - len(range(N_VERTICES)[DEGENERATE])
    with open(result.log_file) as fh:
        assert f"valid vertices={n_tested}  paired=False" in fh.read()

    with open(f"{result.output_dir}/null_distribution.csv") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 40
    assert all(np.isfinite(float(r["max_cluster_stat"])) for r in rows)
    with open(f"{result.output_dir}/significant_clusters.csv") as fh:
        assert all(np.isfinite(float(r["stat_value"])) for r in csv.DictReader(fh))

    # Same t and p maps as the volume path on the same numbers.
    p_vol, t_vol, _ = ttest_voxelwise(
        data[:, None, None, :5],
        data[:, None, None, 5:],
        log=logging.getLogger("test"),
    )
    t_surf, p_surf = captured["maps"]["t"], captured["maps"]["p"]
    assert np.all(t_surf[DEGENERATE] == 0.0) and np.all(p_surf[DEGENERATE] == 1.0)
    np.testing.assert_allclose(t_surf, t_vol.ravel(), rtol=1e-4)
    np.testing.assert_allclose(p_surf, p_vol.ravel(), rtol=1e-4, atol=1e-12)
