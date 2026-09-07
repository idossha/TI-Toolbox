"""SCI-01 -- two-sided / left-tailed cluster inference (volume and surface).

Two independent defects in v2.x, both of which make the cluster test wrong:

1. **Touching opposite-sign clusters were merged.**  ``scipy.ndimage.label``
   was called on the bare ``p < threshold`` mask, so a positive and a negative
   supra-threshold blob that share a face became one cluster whose *signed*
   mass is the difference of the two effects -- exactly ``0`` when they are
   symmetric.  Two real effects therefore vanished.

2. **The null was built with ``max()`` of signed masses.**  Under
   ``alternative="less"`` (or two-sided, where the observed value is compared
   as ``|mass|``) the most extreme permutation cluster is the *most negative*
   one; ``max()`` picks the mass closest to zero, so the null distribution was
   far too small and the test wildly anti-conservative.

The reference implementation below is written from scratch in this file (chain
connectivity, MNE ``permutation_cluster_1samp_test`` semantics: sign-restricted
components, signed mass, max-statistic null).  It shares no code with the
engine, and the same reference is used to check the volume and the surface
backend, which must agree.
"""

import itertools

import numpy as np
import pytest

pytestmark = pytest.mark.unit


# ─── independent reference implementation ─────────────────────────────────


def ref_components(mask, t):
    """Sign-homogeneous connected components of a 1-D chain.

    Returns a list of ``(indices, size, signed_mass)``.
    """
    out = []
    run = []
    sign = 0
    for i, m in enumerate(mask):
        s = int(np.sign(t[i])) if m else 0
        if s == 0 or s != sign:
            if run:
                out.append(run)
            run = [i] if s != 0 else []
            sign = s
        else:
            run.append(i)
    if run:
        out.append(run)
    return [(np.array(r), len(r), float(np.sum(t[r]))) for r in out]


def ref_tail_stat(size, mass, cluster_stat, tail):
    if cluster_stat == "size":
        return float(size)
    if tail == 1:
        return float(mass)
    if tail == -1:
        return float(-mass)
    return float(abs(mass))


def ref_max_stat(mask, t, cluster_stat, tail):
    """Max oriented cluster statistic; singletons ignored (engine convention)."""
    stats = [
        ref_tail_stat(size, mass, cluster_stat, tail)
        for _, size, mass in ref_components(mask, t)
        if size > 1
    ]
    return max(stats) if stats else 0.0


def ref_ttest_ind_1d(a, b):
    """Pooled-variance two-sample t and two-sided p, from first principles."""
    from scipy.stats import t as t_dist

    na, nb = a.shape[1], b.shape[1]
    va = a.var(axis=1, ddof=1)
    vb = b.var(axis=1, ddof=1)
    pooled = ((na - 1) * va + (nb - 1) * vb) / (na + nb - 2)
    se = np.sqrt(pooled * (1 / na + 1 / nb))
    tv = (a.mean(axis=1) - b.mean(axis=1)) / se
    pv = 2 * t_dist.sf(np.abs(tv), na + nb - 2)
    return tv, pv


# ─── 1. touching opposite-sign clusters ───────────────────────────────────


def _touching_map():
    """t map with a +3 run and a -3 run that share a face."""
    t = np.zeros((8, 1, 1))
    t[1:4, 0, 0] = 3.0
    t[4:7, 0, 0] = -3.0
    mask = np.zeros((8, 1, 1), dtype=bool)
    mask[1:7, 0, 0] = True
    return t, mask


def test_v2_merged_touching_clusters_into_zero_mass():
    """Reproduces the defect: bare ndimage.label fuses +/- into one mass-0 blob."""
    from scipy.ndimage import label, sum as ndimage_sum

    t, mask = _touching_map()
    labeled, n = label(mask)
    assert n == 1, "v2.x saw a single fused cluster"
    mass = float(ndimage_sum(t, labeled, index=1))
    assert mass == pytest.approx(0.0), "…whose signed mass cancels to zero"


def test_label_signed_separates_touching_opposite_sign_clusters():
    from tit.stats.engine import label_signed

    t, mask = _touching_map()
    labeled, n = label_signed(mask, t, "two-sided")
    assert n == 2

    masses = sorted(float(t[labeled == cid].sum()) for cid in (1, 2))
    assert masses == pytest.approx([-9.0, 9.0])

    ref = [m for _, size, m in ref_components(mask[:, 0, 0], t[:, 0, 0]) if size > 1]
    assert sorted(ref) == pytest.approx(masses)


@pytest.mark.parametrize(
    "alternative,expected_n", [("greater", 1), ("less", 1), ("two-sided", 2)]
)
def test_label_signed_one_sided_keeps_only_its_sign(alternative, expected_n):
    from tit.stats.engine import label_signed

    t, mask = _touching_map()
    _, n = label_signed(mask, t, alternative)
    assert n == expected_n


# ─── 2. oriented extreme ──────────────────────────────────────────────────


def test_max_cluster_stats_picks_most_negative_under_left_tail():
    """v2.x max() picked -2 (least extreme); the fix picks -10."""
    from tit.stats.engine import _max_cluster_stats, label_signed

    t = np.zeros((9, 1, 1))
    t[0:5, 0, 0] = -2.0  # mass -10, the extreme cluster
    t[6:8, 0, 0] = -1.0  # mass -2
    mask = t != 0

    labeled, n = label_signed(mask, t, "less")
    stat, size, mass = _max_cluster_stats(labeled, n, t, "mass", tail=-1)
    assert mass == pytest.approx(-10.0)
    assert size == 5
    assert stat == pytest.approx(10.0)
    assert stat == pytest.approx(ref_max_stat(mask[:, 0, 0], t[:, 0, 0], "mass", -1))

    from scipy.ndimage import sum as ndimage_sum

    v2 = float(
        np.max(ndimage_sum(t, labeled, index=np.arange(1, n + 1)))
    )  # the v2.x rule
    assert v2 == pytest.approx(-2.0)


def test_two_sided_extreme_uses_absolute_mass():
    from tit.stats.engine import _max_cluster_stats, label_signed

    t = np.zeros((9, 1, 1))
    t[0:5, 0, 0] = -2.0  # |mass| 10
    t[6:8, 0, 0] = 1.5  # |mass| 3
    mask = t != 0
    labeled, n = label_signed(mask, t, "two-sided")
    stat, _, mass = _max_cluster_stats(labeled, n, t, "mass", tail=0)
    assert stat == pytest.approx(10.0)
    assert mass == pytest.approx(-10.0)


# ─── 3. end-to-end: engine null == exhaustive reference null ──────────────


def _tiny_design(rng):
    """8-voxel chain, 3 vs 3 subjects, with a real negative effect."""
    n_vox, n_a, n_b = 8, 3, 3
    a = rng.normal(0.0, 0.4, size=(n_vox, n_a))
    b = rng.normal(0.0, 0.4, size=(n_vox, n_b))
    a[2:6, :] -= 4.0  # group A much lower in voxels 2..5
    return np.concatenate([a, b], axis=1), n_a, n_b


@pytest.mark.parametrize("alternative", ["two-sided", "less", "greater"])
@pytest.mark.parametrize("cluster_stat", ["mass", "size"])
def test_engine_permutation_null_matches_exhaustive_reference(
    alternative, cluster_stat, monkeypatch
):
    """Drive the engine over *every* relabelling and compare null values.

    ``_run_single_permutation`` draws its relabelling from
    ``np.random.permutation``; stubbing that lets the exhaustive enumeration be
    pushed through the production code path, so the comparison is against the
    real function and not a re-typed copy of it.
    """
    import tit.stats.engine as engine

    rng = np.random.default_rng(20260907)
    data, n_a, n_b = _tiny_design(rng)
    n_total = n_a + n_b
    n_vox = data.shape[0]
    threshold = 0.20

    coords = np.stack(
        [np.arange(n_vox), np.zeros(n_vox, int), np.zeros(n_vox, int)], axis=1
    )
    shape = (n_vox, 1, 1)
    valid_mask = np.ones(shape, dtype=bool)
    tail = engine.tail_from_alternative(alternative)

    orders = [
        np.array(list(c) + [i for i in range(n_total) if i not in c])
        for c in itertools.combinations(range(n_total), n_a)
    ]
    assert len(orders) == 20

    for order in orders:
        monkeypatch.setattr(np.random, "permutation", lambda _n, o=order: o)
        got = engine._run_single_permutation(
            data,
            coords,
            n_a,
            n_total,
            threshold,
            valid_mask,
            shape,
            test_type="unpaired",
            alternative=alternative,
            cluster_stat=cluster_stat,
            seed=None,
        )[0]

        permuted = data[:, order]
        t_ref, p_ref = ref_ttest_ind_1d(permuted[:, :n_a], permuted[:, n_a:])
        if alternative == "greater":
            p_ref = p_ref / 2 * np.where(t_ref > 0, 1, 0) + np.where(
                t_ref > 0, 0, 1 - p_ref / 2
            )
        elif alternative == "less":
            p_ref = p_ref / 2 * np.where(t_ref < 0, 1, 0) + np.where(
                t_ref < 0, 0, 1 - p_ref / 2
            )
        mask_ref = p_ref < threshold
        if alternative == "greater":
            mask_ref &= t_ref > 0
        elif alternative == "less":
            mask_ref &= t_ref < 0
        expected = ref_max_stat(mask_ref, t_ref, cluster_stat, tail)

        assert got == pytest.approx(expected), f"order={order.tolist()}"


def test_surface_and_volume_agree_on_a_chain():
    """The surface backend must give the engine's answer on a chain graph."""
    import tit.stats.engine as engine
    import tit.stats.surface as surface

    n = 12
    t = np.zeros(n)
    t[1:4] = 2.5
    t[4:8] = -3.0
    mask = t != 0

    # Dense chain adjacency: connected_components accepts it directly, and it
    # sidesteps sparse-slicing differences between scipy versions.
    adj = np.zeros((n, n))
    for i in range(n - 1):
        adj[i, i + 1] = adj[i + 1, i] = 1.0

    for alternative in ("two-sided", "less", "greater"):
        tail = engine.tail_from_alternative(alternative)
        labels_s, n_s = surface._label_graph_signed(mask, t, adj, alternative)
        got = surface._max_cluster_stat(labels_s, n_s, t, "mass", tail=tail)

        t3 = t.reshape(n, 1, 1)
        labels_v, n_v = engine.label_signed(mask.reshape(n, 1, 1), t3, alternative)
        want = engine._max_cluster_stats(labels_v, n_v, t3, "mass", tail)[0]

        assert n_s == n_v
        assert got == pytest.approx(want)
        assert got == pytest.approx(ref_max_stat(mask, t, "mass", tail))
