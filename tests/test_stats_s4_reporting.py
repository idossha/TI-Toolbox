"""S4-3 / S4-5 / S4-6 / S4-8 -- cluster bookkeeping, the written summary, the log, the seed.

What this pins (2026-10-31)
    S4-3  ``_identify_significant_clusters`` tested only labels 1..10,000; negative clusters are
          numbered after every positive one, so past 10,000 positives a strong negative cluster
          was never tested. Every label is tested now, and "top clusters" are the most extreme
          by the oriented statistic, not the first by label number.
    S4-5  ``analysis_summary.txt`` states the alternative hypothesis, the voxel statistic, the
          cluster connectivity (6-connected faces), the voxel-inclusion rule and the seed; the
          default ``value_metric`` is a field magnitude, not "Current Intensity"; "Mean ... in
          Significant Voxels" is written per sign, not pooled over opposite effects.
    S4-6  A paired run's permutation log names each permutation's sign-flip vector; it indexed
          the subject ids with the +/-1 flips.
    S4-8  Volume permutations take an optional seed through a local ``np.random.Generator``:
          the same seed gives the same null, the global numpy state is untouched, and the seed
          actually used is written in the summary.

Where the expectations come from
    Hand-built label volumes (cluster sizes and masses are set by construction), group means
    computed here with ``np.mean`` over the voxels of each sign, and the sign-flip vectors
    re-applied by hand to the paired data to reproduce each logged permutation's maximum.

Run: ``.venv/bin/python -m pytest tests/test_stats_s4_reporting.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import logging
import re

import numpy as np
import pytest

from tests.stats_real_scipy import real_scipy  # noqa: F401  (fixture)
from tests.test_stats_cluster_bookkeeping import _config, _groups, _patch_runner

_LOG = logging.getLogger("test.s4")


# ─── S4-3 ─────────────────────────────────────────────────────────────────


def test_negative_cluster_numbered_past_10000_is_tested(real_scipy):
    from tit.stats.engine import _identify_significant_clusters, label_signed

    shape = (306, 250, 1)
    t = np.zeros(shape)
    for x in range(0, 300, 3):
        for y in range(0, 250, 2):
            t[x : x + 2, y, 0] = 2.5  # 100 * 125 = 12,500 two-voxel positive clusters
    t[302:306, :, 0] = -6.0  # one negative cluster, 1,000 voxels, |mass| 6,000
    labels, n = label_signed(t != 0, t, "two-sided")
    assert n == 12_501
    neg_id = int(labels[303, 10, 0])
    assert neg_id == 12_501

    null = np.full(199, 100.0)  # every permutation's max |mass| is 100
    sig_mask, sig, observed = _identify_significant_clusters(
        labels, n, t, null, "mass", 0.05, "two-sided", _LOG
    )
    (neg,) = [c for c in sig if c["id"] == neg_id]
    assert neg["size"] == 1000
    assert neg["stat_value"] == pytest.approx(-6000.0)
    assert neg["p_value"] == pytest.approx(1 / 200)
    assert sig_mask[302:306].all()
    # It is the most extreme cluster, so it heads the observed list.
    assert observed[0]["id"] == neg_id


def test_top_clusters_are_ordered_by_statistic_not_label(real_scipy):
    from tit.stats.engine import _identify_significant_clusters, label_signed

    # 12 positive two-voxel clusters along x; cluster k (label k) has t = k, so mass = 2k,
    # except the first, which is made the most extreme.
    t = np.zeros((40, 1, 1))
    for k in range(1, 13):
        t[3 * k : 3 * k + 2, 0, 0] = float(k)
    t[3:5, 0, 0] = 50.0
    labels, n = label_signed(t != 0, t, "two-sided")
    assert n == 12
    masses = {int(labels[3 * k, 0, 0]): 2.0 * t[3 * k, 0, 0] for k in range(1, 13)}
    expected = sorted(masses, key=lambda cid: -masses[cid])[:10]

    _, _, observed = _identify_significant_clusters(
        labels, n, t, np.zeros(9), "mass", 0.05, "two-sided", _LOG
    )
    assert [c["id"] for c in observed] == expected


# ─── S4-5 ─────────────────────────────────────────────────────────────────


def _summary(tmp_path, cfg, resp, non, sig_mask, **kw):
    from tit.stats.reporting import generate_summary

    out = tmp_path / "summary.txt"
    generate_summary(cfg, resp, non, sig_mask, 5.0, [], {}, str(out), **kw)
    return out.read_text()


def _two_sign_volumes(n1=3, n2=3):
    resp = np.full((4, 1, 1, n1), 1.0)
    non = np.full((4, 1, 1, n2), 1.0)
    resp[0, 0, 0] = np.linspace(5.0, 6.0, n1)  # responders > non
    non[0, 0, 0] = np.linspace(1.0, 1.5, n2)
    resp[1, 0, 0] = np.linspace(2.0, 2.2, n1)  # responders > non
    non[1, 0, 0] = np.linspace(0.5, 0.9, n2)
    resp[2, 0, 0] = np.linspace(1.0, 1.1, n1)  # responders < non
    non[2, 0, 0] = np.linspace(7.0, 9.0, n2)
    sig = np.zeros((4, 1, 1), int)
    sig[:3] = 1
    return resp, non, sig


def test_summary_states_hypothesis_statistic_connectivity_rule_and_seed(tmp_path):
    from tit.stats.config import CorrelationConfig, GroupComparisonConfig

    cfg = _config(alternative="greater")
    resp, non, sig = _two_sign_volumes()
    text = _summary(tmp_path, cfg, resp, non, sig, seed=1234)

    assert "Alternative hypothesis: greater (Responders > Non-Responders)" in text
    assert "Welch's t" in text
    assert "6-connected" in text
    assert "every subject" in text
    assert "Random seed: 1234" in text
    # The values are field magnitudes, labelled as the correlation's field axis is.
    assert (
        cfg.value_metric
        == CorrelationConfig.__dataclass_fields__["field_metric"].default
    )
    assert "Current Intensity" not in text
    assert GroupComparisonConfig.__dataclass_fields__["value_metric"].default != (
        "Current Intensity"
    )


def test_summary_mean_in_significant_voxels_is_per_sign(tmp_path):
    cfg = _config()
    resp, non, sig = _two_sign_volumes()
    text = _summary(tmp_path, cfg, resp, non, sig, seed=1)

    def block(header_fragment):
        lines = text.splitlines()
        (i,) = [k for k, line in enumerate(lines) if header_fragment in line]
        return "\n".join(lines[i : i + 4])

    pos = block("Responders > Non-Responders, 2 voxels")
    neg = block("Responders < Non-Responders, 1 voxel")
    for sel, section in (([0, 1], pos), ([2], neg)):
        g1 = float(np.mean(resp[sel]))
        g2 = float(np.mean(non[sel]))
        assert f"Responders: {g1:.4f}" in section
        assert f"Non-Responders: {g2:.4f}" in section
        assert f"{g1 - g2:.4f}" in section


def test_summary_names_pooled_t_for_a_one_subject_group(tmp_path):
    """Welch's t is undefined with a group of one, so the run keeps (and says) pooled t."""
    from tit.stats.config import GroupComparisonConfig

    subjects = [GroupComparisonConfig.Subject(f"r{i}", "T", 1) for i in range(2)] + [
        GroupComparisonConfig.Subject("n0", "T", 0)
    ]
    cfg = GroupComparisonConfig(analysis_name="x", subjects=subjects, n_jobs=1)
    resp, non, sig = _two_sign_volumes(2, 1)
    text = _summary(tmp_path, cfg, resp, non, sig, seed=1)
    assert "Student's t (pooled variance" in text
    assert "Welch's t" in text  # says why it is not Welch


# ─── S4-6 ─────────────────────────────────────────────────────────────────


def test_paired_permutation_log_lists_sign_flips(real_scipy, tmp_path):
    from tit.stats.engine import (
        PermutationEngine,
        _max_cluster_stats,
        label_signed,
        ttest_rel,
        ttest_voxelwise,
    )

    rng = np.random.default_rng(2)
    n = 4
    resp = rng.uniform(1.0, 2.0, size=(6, 6, 6, n))
    non = rng.uniform(1.0, 2.0, size=(6, 6, 6, n))
    resp[1:4, 1:4, 1:4] += 3.0
    p, t, valid = ttest_voxelwise(resp, non, test_type="paired", log=_LOG)
    log_file = tmp_path / "perm.txt"
    engine = PermutationEngine(n_permutations=20, n_jobs=1, seed=3, log=_LOG)
    _, _, _, null, _, _ = engine.correct_groups(
        resp,
        non,
        p_values=p,
        t_statistics=t,
        valid_mask=valid,
        test_type="paired",
        perm_log_file=str(log_file),
        subject_ids_resp=["a", "b", "c", "d"],
        subject_ids_non_resp=["a2", "b2", "c2", "d2"],
    )
    lines = [ln for ln in log_file.read_text().splitlines() if ln.startswith("Perm")]
    assert len(lines) == 20
    for line, null_stat in zip(lines, null):
        flips = np.array(
            [int(s) for s in re.search(r"Sign flips: \[([^\]]*)\]", line)[1].split(",")]
        )
        assert flips.shape == (n,) and set(flips) <= {-1, 1}
        # Re-apply the logged flips by hand: swapping a pair's two values where flip = -1.
        swap = flips < 0
        r, nr = resp.copy(), non.copy()
        r[..., swap], nr[..., swap] = non[..., swap], resp[..., swap]
        tp, pp = ttest_rel(
            np.concatenate([r[valid], nr[valid]], axis=1), n, alternative="two-sided"
        )
        t_vol = np.zeros(valid.shape)
        p_vol = np.ones(valid.shape)
        t_vol[valid], p_vol[valid] = tp, pp
        lab, k = label_signed((p_vol < 0.05) & valid, t_vol, "two-sided")
        assert _max_cluster_stats(lab, k, t_vol, "mass", 0)[0] == pytest.approx(
            null_stat, rel=1e-9
        )


# ─── S4-8 ─────────────────────────────────────────────────────────────────


def _null(seed):
    from tit.stats.engine import PermutationEngine, ttest_voxelwise

    resp, non = _groups()
    p, t, valid = ttest_voxelwise(resp, non, log=_LOG)
    engine = PermutationEngine(n_permutations=20, n_jobs=1, seed=seed, log=_LOG)
    return engine.correct_groups(
        resp, non, p_values=p, t_statistics=t, valid_mask=valid
    )[3]


def test_seed_reproduces_the_null_without_touching_global_state(real_scipy):
    state = np.random.get_state()[1].copy()
    first, again, other = _null(5), _null(5), _null(6)
    np.testing.assert_array_equal(first, again)
    assert not np.array_equal(first, other)
    np.testing.assert_array_equal(np.random.get_state()[1], state)


def test_config_seed_is_validated():
    with pytest.raises(ValueError, match="seed"):
        _config(seed=-1)
    with pytest.raises(ValueError, match="seed"):
        _config(seed=1.5)
    assert _config(seed=7).seed == 7
    assert _config().seed is None


@pytest.mark.parametrize("seed", [None, 42])
def test_run_writes_the_seed_it_used(real_scipy, init_pm, monkeypatch, seed):
    """The summary's seed reproduces the run; with no seed a fresh one is drawn and written."""
    perm = _patch_runner(monkeypatch, _groups(), [])
    used = []
    real_init = perm.PermutationEngine.__init__

    def spy(self, *a, **k):
        used.append(k.get("seed"))
        real_init(self, *a, **k)

    monkeypatch.setattr(perm.PermutationEngine, "__init__", spy)
    result = perm.run_group_comparison(_config(cluster_threshold=0.01, seed=seed))
    text = open(f"{result.output_dir}/analysis_summary.txt").read()
    (written,) = re.findall(r"Random seed: (\d+)", text)
    assert used == [int(written)]
    if seed is not None:
        assert int(written) == seed
