"""Frozen preliminary-study versus migrated adapters, synthetic inputs only."""

import ast, json, sys, warnings, tempfile, subprocess
from pathlib import Path
from types import SimpleNamespace
from dataclasses import dataclass
import logging
import numpy as np
import pandas as pd
from scipy import stats, sparse
from scipy.sparse.csgraph import connected_components

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tit.stats import graph, effects, associations, robustness

warnings.filterwarnings("ignore")
checkouts = [Path(p).resolve() for p in sys.argv[1:]]
if not checkouts:
    raise SystemExit("at least one study checkout is required")
_snapshot = tempfile.TemporaryDirectory(prefix="tit-study-parity-")
snap = Path(_snapshot.name)
for root in checkouts:
    paths = [
        "src/detect/detect/stats.py",
        "src/source/source/group.py",
        "src/simulation/simulation/stats.py",
        "src/qc/qc/sensitivity.py",
    ]
    global_path = (
        "src/exploratory/field_vs_global"
        if (root / "src/exploratory/field_vs_global").exists()
        else "src/simulation/global_response"
    )
    paths += [
        global_path + "/" + n
        for n in [
            "hfmax_group_moderation.py",
            "field_orientation_global_density_dkatlas.py",
            "hfmax_perparcel_interaction.py",
            "hfmax_sham_jackknife.py",
        ]
    ]
    for rel in paths:
        result = subprocess.run(
            ["git", "-C", str(root), "show", "v1.0-preliminary:" + rel],
            check=True,
            capture_output=True,
            text=True,
        )
        target = snap / root.name / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result.stdout)

CFG = SimpleNamespace(
    n_permutations=31, alpha=0.05, tail=0, seed=42, n_bootstrap=51, ci_alpha=0.05
)
config = SimpleNamespace(UNCORRECTED_P_THRESHOLD=0.05, MIN_CLUSTER_VERTICES=1)


def load(path, names=None):
    tree = ast.parse(Path(path).read_text())
    nodes = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and (
            names is None or n.name in names
        ):
            nodes.append(n)
        elif (
            isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Attribute)
            and isinstance(n.value.value, ast.Name)
            and n.value.value.id.startswith("_")
        ):
            nodes.append(n)
    env = dict(
        np=np,
        pd=pd,
        sparse=sparse,
        stats=stats,
        sp_stats=stats,
        sstats=stats,
        connected_components=connected_components,
        dataclass=dataclass,
        Path=Path,
        ClusterConfig=object,
        logging=logging,
        logger=logging.getLogger("parity"),
        CFG_STATS=CFG,
        config=config,
        _rank=stats.rankdata,
        _ols_coef=lambda X, y: np.linalg.lstsq(X, y, rcond=None)[0],
        _design=lambda d, g, full: np.column_stack(
            [np.ones(len(d)), d, g] + ([d * g] if full else [])
        ),
        _graph=graph,
        _effects=effects,
        _associations=associations,
        _robustness=robustness,
        _mne_cluster_test=graph.mne_cluster_test,
        MODIFIED_Z_OUTLIER=3.5,
        N_PERM=31,
        N_BOOT=51,
        CONTRAST="stim_vs_pre",
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), env)
    return env


def equal(a, b):
    if hasattr(a, "__dataclass_fields__"):
        a = a.__dict__
        b = b.__dict__
    if isinstance(a, dict):
        assert a.keys() == b.keys(), (a.keys(), b.keys())
        for k in a:
            equal(a[k], b[k])
    elif isinstance(a, (tuple, list)):
        assert len(a) == len(b)
        for aa, bb in zip(a, b):
            equal(aa, bb)
    elif isinstance(a, (float, np.floating, int, np.integer, np.ndarray)):
        np.testing.assert_allclose(a, b, rtol=1e-13, atol=1e-13, equal_nan=True)
    else:
        assert a == b, (a, b)


rng = np.random.default_rng(19)
a = rng.normal(size=(8, 4)) + 0.7
b = rng.normal(size=(5, 4))
a[0, 1] = np.nan
a[1, 1] = 0
adj = sparse.diags([np.ones(3), np.ones(3)], [-1, 1], shape=(4, 4)).tocsr()
results = []
for root in checkouts:
    repo = root.name
    path = "src/detect/detect/stats.py"
    old, new = load(snap / repo / path), load(root / path)
    for env in [old, new]:
        env["_adjacency"] = lambda ch: (adj, list(range(4)))
    for name, args in [
        ("run_within_group_topo_test", (a, list("abcd"), CFG)),
        ("run_between_group_topo_test", (a, b, list("abcd"), CFG)),
    ]:
        equal(old[name](*args), new[name](*args))
        results.append(repo + ":" + name)
    for name, args in [
        ("_boot_within", (np.array([0.0, 1.0, -2.0, 4.0, np.nan]), 51)),
        ("_boot_between", (np.array([1.0, 2.0, 5.0]), np.array([0.0, 3.0, 8.0]), 51)),
    ]:
        equal(
            old[name](*args, np.random.default_rng(4)),
            new[name](*args, np.random.default_rng(4)),
        )
        results.append(repo + ":" + name)
    path = "src/source/source/group.py"
    ns = {
        "_sig_mask_from_clusters",
        "_sig_cluster_labels",
        "cluster_perm_1samp",
        "cluster_perm_between",
        "_rb_within",
        "_rb_between",
        "_boot_within",
        "_boot_between",
        "_percentile_ci",
    }
    old, new = load(snap / repo / path, ns), load(root / path, ns)
    # n_jobs=-1 is the same study convention; force MNE joblib to one process externally.
    clean = np.nan_to_num(a)
    for name, args in [
        ("cluster_perm_1samp", (clean, adj)),
        ("cluster_perm_between", (clean, b, adj)),
    ]:
        equal(old[name](*args), new[name](*args))
        results.append(repo + ":" + name)
    path = "src/simulation/simulation/stats.py"
    old, new = load(snap / repo / path), load(root / path)
    for name, args in [
        ("pearson_vectorized", (a, clean)),
        ("spearman_vectorized", (a, clean)),
    ]:
        equal(old[name](*args), new[name](*args))
        results.append(repo + ":" + name)
    equal(
        old["permutation_max_cluster_masses"](
            a, clean, adj, n_permutations=31, rng=np.random.default_rng(9)
        ),
        new["permutation_max_cluster_masses"](
            a, clean, adj, n_permutations=31, rng=np.random.default_rng(9)
        ),
    )
    results.append(repo + ":field_null")
    kwargs = dict(statistic="spearman", n_bootstrap=51, ci_alpha=0.05)
    equal(
        old["bootstrap_cluster_mean_r_ci"](
            a, clean, rng=np.random.default_rng(3), **kwargs
        ),
        new["bootstrap_cluster_mean_r_ci"](
            a, clean, rng=np.random.default_rng(3), **kwargs
        ),
    )
    results.append(repo + ":field_bootstrap")
    path = "src/qc/qc/sensitivity.py"
    old, new = load(snap / repo / path), load(root / path)
    for name, args in [
        ("loso_subject_effects", (np.array([0.0, 1.0, 2.0, 3.0, 8.0]), list("abcde"))),
        ("modified_zscores", (np.array([1.0, 1.0, 1.0, 9.0]),)),
    ]:
        equal(old[name](*args), new[name](*args))
        results.append(repo + ":" + name)
    gp = (
        "src/exploratory/field_vs_global"
        if (root / "src/exploratory/field_vs_global").exists()
        else "src/simulation/global_response"
    )
    path = gp + "/hfmax_group_moderation.py"
    names = {"_ols_coef", "_rank", "_design", "moderation"}
    old, new = load(snap / repo / path, names), load(root / path, names)
    da = pd.DataFrame(
        {"hf_max@roi": rng.normal(size=9), "density__stim_vs_pre": rng.normal(size=9)}
    )
    db = pd.DataFrame(
        {"hf_max@roi": rng.normal(size=7), "density__stim_vs_pre": rng.normal(size=7)}
    )
    equal(
        old["moderation"]("roi", da, db, np.random.default_rng(2)),
        new["moderation"]("roi", da, db, np.random.default_rng(2)),
    )
    results.append(repo + ":rank_moderation_full")
    path = gp + "/field_orientation_global_density_dkatlas.py"
    names = {"_residualize", "_rank", "_partial_r", "_partial_p", "_bh_fdr"}
    old, new = load(snap / repo / path, names), load(root / path, names)
    vals = stats.rankdata(rng.normal(size=(20, 4)), axis=0)
    equal(
        old["_partial_r"](vals[:, 0], vals[:, 1], vals[:, 2:]),
        new["_partial_r"](vals[:, 0], vals[:, 1], vals[:, 2:]),
    )
    results.append(repo + ":partial_ranked")
    equal(
        old["_bh_fdr"](np.array([0.01, 0.04, np.nan, 0.2])),
        new["_bh_fdr"](np.array([0.01, 0.04, np.nan, 0.2])),
    )
    results.append(repo + ":bh_fdr")
    # Supporting interaction / jackknife use the same residual permutations.
    for fn, symbol in [
        ("hfmax_perparcel_interaction.py", "_interaction"),
        ("hfmax_sham_jackknife.py", "moderation_fit"),
    ]:
        path = gp + "/" + fn
        names = {"_rank", "_design", "_ols_coef", symbol, "_bh_fdr"}
        old, new = load(snap / repo / path, names), load(root / path, names)
        inputs = (
            rng.normal(size=9),
            rng.normal(size=9),
            rng.normal(size=7),
            rng.normal(size=7),
        )
        equal(
            old[symbol](*inputs, np.random.default_rng(77)),
            new[symbol](*inputs, np.random.default_rng(77)),
        )
        results.append(repo + ":" + symbol)
        if fn == "hfmax_perparcel_interaction.py":
            equal(
                old["_bh_fdr"](np.array([0.01, 0.04, np.nan, 0.2])),
                new["_bh_fdr"](np.array([0.01, 0.04, np.nan, 0.2])),
            )
            results.append(repo + ":bh_propagate")
report = {"passed": len(results), "checks": results, "dataset_rerun": False}
print(json.dumps(report, indent=2))
