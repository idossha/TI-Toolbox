"""Unit tests for :func:`tit.catalog.group_stats_detail` and its log reader.

The fixtures below are verbatim excerpts of two real runs on Dataset 000 --
``derivatives/ti-toolbox/stats/group_comparison/{smoke-ui-52708, results-lane-2v1}`` -- so the
expected values here are read, not invented.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tit import catalog
from tit.paths import PathManager

# The 2-vs-1 run that died in ``ttest_voxelwise`` and left only its log (before the pooled-variance
# fix), now with the ERROR line the wrapper writes.
FAILED_LOG = """\
2026-09-07 17:59:32 | INFO | tit.stats.group_comparison | Analysis: smoke-ui-52708
2026-09-07 17:59:32 | INFO | tit.stats.group_comparison | Config:   test=unpaired  alt=two-sided \
 stat=mass  threshold=0.050  perms=1000  alpha=0.050  jobs=-1
2026-09-07 17:59:33 | INFO | tit.stats.group_comparison | Loaded 2 Responders: ['101', 'MNI152']
2026-09-07 17:59:33 | INFO | tit.stats.group_comparison | Loaded 1 Non-Responders: ['ernie']
2026-09-07 17:59:33 | INFO | tit.stats.group_comparison | Image shape: (182, 218, 182)  (0.4s)
2026-09-07 17:59:33 | WARNING | tit.stats.group_comparison | Excluding 1383362 voxel(s) with zero \
within-group variance (degenerate t: 0 perfectly separated, 1383362 constant)
2026-09-07 17:59:33 | ERROR | tit.stats.group_comparison | Analysis failed: No voxel could be \
tested. Every voxel with data has zero within-group variance.
"""

# The same design after the fix: a complete run, 0 significant clusters.
OK_LOG = """\
2026-09-07 18:10:01 | INFO | tit.stats.group_comparison | Config:   test=unpaired  alt=two-sided \
 stat=mass  threshold=0.050  perms=100  alpha=0.050  jobs=2
2026-09-07 18:10:02 | INFO | tit.stats.group_comparison | Loaded 2 Responders: ['101', 'MNI152']
2026-09-07 18:10:02 | INFO | tit.stats.group_comparison | Loaded 1 Non-Responders: ['ernie']
2026-09-07 18:10:02 | INFO | tit.stats.group_comparison | Image shape: (182, 218, 182)  (0.4s)
2026-09-07 18:10:02 | INFO | tit.stats.group_comparison | Min p=2.06e-08 over 1282385 testable \
voxel(s), p<0.05: 49077  (0.4s)
2026-09-07 18:10:02 | INFO | tit.stats.group_comparison | Clusters at p<0.050 (uncorrected, \
sign-separated): 26086
2026-09-07 18:10:21 | INFO | tit.stats.group_comparison | Threshold (p<0.050): 30972312.56 mass \
units  (null min=3119326.40, mean=13675110.32, max=30972312.56)
2026-09-07 18:10:21 | INFO | tit.stats.group_comparison |   Cluster 12: mass=24346.53, size=35, \
p=1.0000 (ns)
2026-09-07 18:10:21 | INFO | tit.stats.group_comparison | Significant: 0 clusters, 0 voxels
2026-09-07 18:10:25 | INFO | tit.stats.group_comparison | COMPLETE in 23.3s
"""


@pytest.fixture()
def pm(tmp_path: Path) -> PathManager:
    return PathManager(project_dir=str(tmp_path))


def _write_run(pm: PathManager, name: str, log: str, files: list[str]) -> str:
    run_dir = pm.ensure(pm.stats_output("group_comparison", name))
    with open(os.path.join(run_dir, "group_comparison_analysis_20260907_181001.log"), "w") as f:
        f.write(log)
    for filename in files:
        with open(os.path.join(run_dir, filename), "wb") as f:
            f.write(b"x")
    return run_dir


# ── the log reader ───────────────────────────────────────────────────────────


def test_parse_log_reads_the_config_line() -> None:
    parsed = catalog._parse_stats_log(OK_LOG)
    assert parsed["config"] == [
        {"label": "Test", "value": "unpaired"},
        {"label": "Alternative", "value": "two-sided"},
        {"label": "Cluster statistic", "value": "mass"},
        {"label": "Cluster-forming p", "value": "0.050"},
        {"label": "Permutations", "value": "100"},
        {"label": "Cluster alpha", "value": "0.050"},
        {"label": "Parallel jobs", "value": "2"},
    ]


def test_parse_log_reads_the_groups_and_their_subjects() -> None:
    parsed = catalog._parse_stats_log(OK_LOG)
    assert parsed["groups"] == [
        {"name": "Responders", "n": 2, "subjects": ["101", "MNI152"]},
        {"name": "Non-Responders", "n": 1, "subjects": ["ernie"]},
    ]
    assert parsed["image_shape"] == "(182, 218, 182)"


def test_parse_log_reads_the_outcome_numbers() -> None:
    results = {r["label"]: r["value"] for r in catalog._parse_stats_log(OK_LOG)["results"]}
    assert results["Smallest uncorrected p"] == "2.06e-08"
    assert results["Testable voxels"] == "1282385"
    assert results["Voxels at p < 0.05"] == "49077"
    assert results["Candidate clusters"] == "26086"
    assert results["Cluster threshold"] == "30972312.56"
    assert results["Significant clusters"] == "0"
    assert results["Significant voxels"] == "0"


def test_parse_log_reads_the_cluster_lines() -> None:
    clusters = catalog._parse_stats_log(OK_LOG)["clusters"]
    assert clusters["columns"] == ["Cluster", "mass", "Size (voxels)", "p", "Verdict"]
    assert clusters["rows"] == [[12, 24346.53, 35, 1.0, "ns"]]


def test_parse_log_keeps_the_error_line() -> None:
    parsed = catalog._parse_stats_log(FAILED_LOG)
    assert parsed["error"] is not None
    assert "No voxel could be tested" in parsed["error"]
    assert parsed["clusters"] is None


# ── the directory reader ─────────────────────────────────────────────────────


def test_detail_is_none_for_an_unknown_run(pm: PathManager) -> None:
    assert catalog.group_stats_detail(pm, "group_comparison", "nope") is None


def test_detail_rejects_a_traversing_name(pm: PathManager) -> None:
    _write_run(pm, "run", OK_LOG, [])
    assert catalog.group_stats_detail(pm, "group_comparison", "../run") is None


def test_detail_of_a_complete_run(pm: PathManager) -> None:
    _write_run(
        pm,
        "good",
        OK_LOG,
        [
            "analysis_summary.txt",
            "pvalues_map.nii.gz",
            "average_responders.nii.gz",
            "permutation_null_distribution.pdf",
        ],
    )
    detail = catalog.group_stats_detail(pm, "group_comparison", "good")
    assert detail is not None
    assert detail["status"] == "ok"
    assert detail["reason"] is None
    assert detail["clusters"]["rows"] == [[12, 24346.53, 35, 1.0, "ns"]]
    # Ordered by the label table, not alphabetically, and each file named rather than filename-cased.
    labels = [a["label"] for a in detail["artifacts"]]
    assert labels[:4] == [
        "Group 1 average field",
        "p-value map (−log10 p)",
        "Permutation null distribution",
        "Analysis summary",
    ]
    kinds = {os.path.basename(a["path"]): a["kind"] for a in detail["artifacts"]}
    assert kinds["pvalues_map.nii.gz"] == "nifti"
    assert kinds["permutation_null_distribution.pdf"] == "pdf"
    assert kinds["group_comparison_analysis_20260907_181001.log"] == "log"


def test_detail_of_a_run_that_wrote_only_its_log(pm: PathManager) -> None:
    """The state in the maintainer's screenshot: the pane must be able to say why."""
    _write_run(pm, "bare", FAILED_LOG, [])
    detail = catalog.group_stats_detail(pm, "group_comparison", "bare")
    assert detail is not None
    assert detail["status"] == "empty"
    assert "No voxel could be tested" in detail["reason"]
    assert [a["kind"] for a in detail["artifacts"]] == ["log"]


def test_detail_prefers_a_clusters_csv_over_the_log(pm: PathManager) -> None:
    """The fsaverage surface path writes ``significant_clusters.csv``; the MNI path does not."""
    run_dir = _write_run(pm, "surface", FAILED_LOG, [])
    with open(os.path.join(run_dir, "significant_clusters.csv"), "w") as f:
        f.write("id,size,stat_value,p_value\n7,42,3.5,0.01\n")
    detail = catalog.group_stats_detail(pm, "group_comparison", "surface")
    assert detail["clusters"]["columns"] == ["id", "size", "stat_value", "p_value"]
    assert detail["clusters"]["rows"] == [["7", "42", "3.5", "0.01"]]
    assert detail["status"] == "ok"
