"""Simulator, flex-search and ex-search reports: structure and rules, not pixels.

Pins (2026-09-28, ARCHITECTURE.md §14):
* each page has its sections, every contents link lands on an element, every image has alt text,
  every figure a caption, statuses are icon + word, and nothing is fetched (doi.org links only);
* no run report shows checks or advisories; the simulator leads with the grey-matter envelope
  (99.9th percentile, median, where its maximum is) and says nothing about an ROI; flex-search embeds the run's
  own target and valid-scalp figures and draws no cap; ex-search draws no cap;
* the page stays under its size budget;
* on every report (DTI QC included) the reference list is exactly what the rendered page cites;
* the pipelines call the report writers, and a report that cannot be written never fails a run.

Inputs are synthetic files in the formats the pipelines write (SimNIBS log and field-summary lines
copied in shape from sub-ernie's outputs, values chosen here). The cap image is stand-in bytes: the
overlay itself is ``tit.tools.montage_visualizer`` (ImageMagick), exercised by the real-data rebuild
``python -m tit.reporting.generators.<simulation|flex_search|ex_search>``, as is the MNI hot-spot
lookup through charm's warp. No pixel goldens.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.test_reporting_dti_qc import FAKE, _images, _parse, _record
from tit.reporting.generators import simulation as sim

CAP = "tit.tools.montage_visualizer.montage_webp"


def _structure(
    html: str, sections: tuple[str, ...], budget: int, require_status: bool = True
) -> None:
    page = _parse(html)
    assert all(s in page.ids for s in sections), [s for s in sections if s not in page.ids]
    assert page.toc and all(h[1:] in page.ids for h in page.toc)
    assert all(alt.strip() for alt in page.imgs)
    assert page.figures == page.captions
    assert all(u.startswith("https://doi.org/") for u in page.urls), page.urls
    assert "url(http" not in html and "@import" not in html
    if require_status:
        assert page.statuses and all(icon and word for _, icon, word in page.statuses)
    assert len(html.encode()) < budget


def _advisory_ids(html: str) -> list[str]:
    return re.findall(r'<span class="name">([^<]+)</span> <span class="role advisory">', html)


# ── simulator ────────────────────────────────────────────────────────────

LOG = """[ simnibs 4.6.0 - 2026-09-23 18:41:22,260 - 3343 ]INFO: Currents (A): [{a}, -{a}]
[ simnibs 4.6.0 - 2026-09-23 18:42:08,578 - 3343 ]INFO: Using anisotropic volume normalized conductivities based on the file: /p/m2m_X/DTI_coregT1_tensor.nii.gz
[ simnibs 4.6.0 - 2026-09-23 18:42:46,851 - 3343 ]INFO: Using solver options: hypre
[ simnibs 4.6.0 - 2026-09-23 18:42:55,381 - 3343 ]INFO: Time to solve:   5.3871 s
[ simnibs 4.6.0 - 2026-09-23 18:42:55,933 - 3343 ]INFO: Estimated current calibration error: 3.4%
[ simnibs 4.6.0 - 2026-09-23 18:43:09,191 - 3343 ]INFO: Currents (A): [{b}, -{a}]
[ simnibs 4.6.0 - 2026-09-23 18:44:30,040 - 3343 ]INFO: Time to solve:   5.1 s
"""

SUMMARY = """X_TDCS_1
============
Gray Matter

Field Percentiles
-----------------
|Field |99.9%        |99.0%        |95.0%        |
|------|-------------|-------------|-------------|
|E     |2.00e-01 V/m |1.00e-01 V/m |5.00e-02 V/m |
|magnE |2.00e-01 V/m |1.00e-01 V/m |5.00e-02 V/m |


X_TDCS_2
============
Gray Matter

Field Percentiles
-----------------
|Field |99.9%        |99.0%        |95.0%        |
|------|-------------|-------------|-------------|
|E     |3.00e-01 V/m |2.00e-01 V/m |1.00e-01 V/m |
|magnE |3.00e-01 V/m |2.00e-01 V/m |1.00e-01 V/m |
"""


def _sim_dir(tmp_path: Path, mA: float = 1.0) -> Path:
    d = tmp_path / "Simulations" / "M"
    (d / "documentation").mkdir(parents=True)
    (d / "high_Frequency" / "analysis").mkdir(parents=True)
    config = {
        "subject_id": "X", "simulation_name": "M", "simulation_mode": "TI", "eeg_net": "EEG10-10_UI_Jurak_2007.csv",
        "conductivity": "vn", "electrode_pairs": [["AF3", "PO10"], ["AF4", "Oz"]], "is_xyz_montage": False,
        "intensities": [mA, mA], "electrode_geometry": {"shape": "ellipse", "dimensions": [8, 8], "gel_thickness": 4, "rubber_thickness": 2.0},
        "created_at": "2026-09-23T18:41:20",
    }
    (d / "documentation" / "config.json").write_text(json.dumps(config))
    (d / "documentation" / "simnibs_simulation_20260923-184120.log").write_text(LOG.format(a=mA / 1e3, b=mA / 1e3))
    (d / "high_Frequency" / "analysis" / "fields_summary.txt").write_text(SUMMARY)
    return d


def _with_envelope(rec: dict, mni=(-12.4, -80.2, 4.0)) -> dict:
    rec["envelope"] = {"median": 0.17, "p99_9": 0.36, "max": 0.48, "peak_world": [10.0, -60.0, 20.0],
                       "peak_mni": list(mni) if mni else None}
    return rec


def _sim_images() -> dict:
    return {"image": FAKE, "labels": ["sagittal", "coronal", "axial"], "tile": (100, 80), "shape": (100, 248),
            "lo": 0.17, "hi": 0.36, "stops": ["#000", "#fff"], "centred_on": "the grey-matter hot spot (top 0.1 %)"}


class TestSimulation:
    def test_parsers_read_the_simnibs_formats(self, tmp_path):
        carriers = sim.parse_fields_summary(SUMMARY)
        assert [c_["name"] for c_ in carriers] == ["X_TDCS_1", "X_TDCS_2"]
        assert carriers[1]["p99.9"] == 0.3 and carriers[0]["p95.0"] == 0.05
        log = sim.parse_log(LOG.format(a=0.001, b=0.001))
        assert log["tensor"].endswith("DTI_coregT1_tensor.nii.gz") and log["solver"] == "hypre"
        assert log["simnibs"] == "4.6.0" and log["calibration_error_pct"] == [3.4]

    def test_page_structure_and_grey_matter_headline(self, tmp_path):
        rec = _with_envelope(sim.collect(_sim_dir(tmp_path)))
        with patch(CAP, return_value=FAKE):
            html = sim.build_html(rec, _sim_images(), "X")
        _structure(html, ("verdict", "montage", "field", "technical"), sim.SIZE_BUDGET, require_status=False)
        assert '<h2 id="verdict-h">0.360 V/m peak envelope in grey matter</h2>' in html
        assert "median 0.170 V/m; its maximum, 0.480 V/m, is at MNI (-12, -80, 4) mm." in html
        assert "Grey matter maximum" in html and "from the subject's DTI tensor" in html
        assert "ROI" not in html  # the simulator report says nothing about an ROI
        assert not _advisory_ids(html) and 'id="safety"' not in html and "Software checks" not in html
        assert "Electrode current" not in html and 'class="callout' not in html  # no checks, even at 1 mA
        assert "Montage on the EEG cap" in html  # the cap overlay stays

    def test_peak_falls_back_to_subject_space_without_the_warp(self, tmp_path):
        rec = _with_envelope(sim.collect(_sim_dir(tmp_path)), mni=None)
        with patch(CAP, return_value=None):
            html = sim.build_html(rec, None, "X")
        assert "its maximum, 0.480 V/m, is at (10, -60, 20) mm, subject space." in html

    def test_high_current_raises_no_advisory(self, tmp_path):
        with patch(CAP, return_value=None):
            html = sim.build_html(_with_envelope(sim.collect(_sim_dir(tmp_path, mA=5.0))), None, "X")
        assert "5 mA per channel, 10 mA total" in html
        assert 'class="callout' not in html and "Electrode current" not in html

    def test_report_file_and_budget(self, tmp_path):
        d = _sim_dir(tmp_path)
        pm = MagicMock()
        pm.simulation.return_value = str(d)
        pm.m2m.return_value = str(tmp_path / "m2m_X")
        with patch("tit.paths.get_path_manager", return_value=pm), patch(CAP, return_value=FAKE):
            path = sim.create_simulation_report(tmp_path, "X", "M", out_dir=tmp_path / "out")
        assert path.parent == tmp_path / "out" and path.name.startswith("simulation_report_")
        assert path.stat().st_size < sim.SIZE_BUDGET

    def test_simulation_run_writes_a_report_and_survives_its_failure(self):
        from tit.sim.base import BaseSimulation

        run = MagicMock()
        run.pm.project_dir, run.config.subject_id, run.montage.name = "/p", "X", "M"
        with patch("tit.reporting.generators.simulation.create_simulation_report", side_effect=OSError("disk full")) as create:
            BaseSimulation._write_report(run)
        create.assert_called_once_with("/p", "X", "M")
        assert "disk full" in run.logger.warning.call_args[0][0]


class TestShared:
    def test_the_optimisers_have_no_advisories(self):
        from tit.reporting.qc_rules import RULES

        assert "sim" not in RULES  # the simulator report has no checks
        assert not any(r["role"] == "advisory" for r in RULES["opt"].values())


# ── flex-search ──────────────────────────────────────────────────────────

CANDIDATES = (
    "candidate_id,evaluation,objective,roi_mean,roi_p99_9,non_roi_mean,non_roi_p95,target_background_ratio,current_ch1_mA,current_ch2_mA,geometry_file\n"
    "r:1,1,-1.15,0.12,0.21,0.10,0.17,1.15,1.1,0.9,g.jsonl\n"
    "r:9,9,-1.8,0.04,0.08,0.022,0.034,1.8,0.7,1.3,g.jsonl\n"
)


def _flex_dir(tmp_path: Path, values=(-1.8,), goal="focality_tf", success=True) -> Path:
    d = tmp_path / "run"
    meta = {
        "created": "2026-09-19T14:51:52", "subject_id": "X", "goal": goal, "postproc": "max_TI", "current_mA": 1,
        "electrode": {"shape": "ellipse", "dimensions": [8, 8], "gel_thickness": 4}, "non_roi_method": "everything_else",
        "intensity_weight": 0.0, "optimize_current_ratio": True, "current_split": [0.7, 1.3], "n_multistart": len(values),
        "min_electrode_distance": 5,
        "result": {"success": success, "best_value": min(values), "best_run_index": 0 if success else -1, "all_values": list(values)},
    }
    for i, _ in enumerate(values):
        h = d / "candidate_history" / f"{i:02d}"
        h.mkdir(parents=True)
        (h / "candidates.csv").write_text(CANDIDATES)
        (h / "candidate_manifest.json").write_text(json.dumps({
            "accepted_candidate_id": "r:9", "evaluations": 3536, "valid_candidates": 1447,
            "metric_definitions": {"roi_mean": "unweighted mean of target samples, V/m"},
            "optimizer_termination": {"global": {"evaluations": 3536, "iterations": 33}}, "config": {"anisotropy_type": "scalar"}}))
    (d / "flex_meta.json").write_text(json.dumps(meta))
    (d / "electrode_positions.json").write_text(json.dumps({
        "optimized_positions": [[82, -6, 5], [81, 31, 21], [-77, 27, 18], [-78, 5, 8]],
        "channel_array_indices": [[0, 0], [0, 1], [1, 0], [1, 1]]}))
    (d / "final_sim_0").mkdir()
    (d / "final_sim_0" / "fields_summary.txt").write_text(SUMMARY.split("\n\n\n")[0])
    (d / "roi.tetravox.json").write_text(json.dumps({"meta": {
        "roi": "", "source": None, "label": None, "volume_mm3": 17426.0, "centroid_ras": [0.8, 9.1, 17.6],
        "gm_overlap": 0.757, "spheres": [{"centre_ras": [1, 9, 18], "radius_mm": 5.0}]}}))
    from PIL import Image

    Image.new("RGBA", (174, 42), (0, 128, 0, 255)).save(d / "roi.png")
    Image.new("RGBA", (447, 297), (200, 200, 200, 255)).save(d / "valid_skin_region.png")
    return d


def _flex_rec(tmp_path, **kw) -> dict:
    from tit.reporting.generators import flex_search as flex

    return flex.collect(_flex_dir(tmp_path, **kw))


class TestFlexSearch:
    def test_page_structure_advisories_and_plain_score(self, tmp_path):
        from tit.reporting.generators import flex_search as flex

        with patch(CAP, return_value=FAKE):
            html = flex.build_html(_flex_rec(tmp_path), "X")
        _structure(
            html,
            ("verdict", "target", "montage", "runs", "technical"),
            flex.SIZE_BUDGET,
            require_status=False,
        )
        assert not _advisory_ids(html)
        assert '<h2 id="verdict-h">Best montage: target mean 1.80× the background mean</h2>' in html
        assert "0.7 / 1.3 mA per channel, 2 mA total" in html  # the searched split, not 1 mA per channel
        assert html.count('<img src="data:image/webp') == 2  # the run's roi.png and valid_skin_region.png
        assert "The target on the subject's T1" in html and "Where electrodes could go" in html
        assert "Nearest cap electrode" not in html and "Montage on the EEG cap" not in html
        assert "sphere at (1, 9, 18) mm" in html  # the ROI is named, not "Target ROI"

    @pytest.mark.parametrize("goal,words", [("mean", "mean target field 1.800 V/m"), ("max", "peak target field 1.800 V/m")])
    def test_goal_is_explained_in_words(self, tmp_path, goal, words):
        from tit.reporting.generators import flex_search as flex

        with patch(CAP, return_value=None):
            html = flex.build_html(_flex_rec(tmp_path, goal=goal), "X")
        assert f'<h2 id="verdict-h">Best montage: {words}</h2>' in html

    def test_failed_run_still_reports(self, tmp_path):
        from tit.reporting.generators import flex_search as flex

        with patch(CAP, return_value=None):
            html = flex.build_html(_flex_rec(tmp_path, values=(1e300,), success=False), "X")
        assert '<h2 id="verdict-h">No valid montage found</h2>' in html

    def test_flex_run_writes_a_report_and_survives_its_failure(self):
        from tit.opt.flex import flex as flex_run

        logger = MagicMock()
        with patch("tit.reporting.generators.flex_search.create_flex_search_report", side_effect=ValueError("bad")) as create, \
                patch("tit.opt.flex.flex.get_path_manager", return_value=MagicMock(project_dir="/p")):
            flex_run._write_report(MagicMock(subject_id="X"), "/p/run", logger)
        create.assert_called_once_with("/p", "X", "/p/run")
        assert "bad" in logger.warning.call_args[0][0]


# ── ex-search ────────────────────────────────────────────────────────────

LEADFIELD_LOG = """[ simnibs 4.6.0 - 2026-09-23 17:38:24,694 - 936 ]INFO: Running simulations
[ simnibs 4.6.0 - 2026-09-23 17:38:37,711 - 936 ]INFO: Placing Electrode:
definition: plane
shape: ellipse
centre: Fp1
dimensions: [10, 10]
thickness:[4]
"""


def _ex_dir(tmp_path: Path, n: int = 40, mA=(1.0, 1.0)) -> Path:
    import random

    d = tmp_path / "ex"
    d.mkdir()
    (d / "run_config.json").write_text(json.dumps({
        "subject_id": "X", "roi_name": "thal.csv", "roi_radius": 3.0, "leadfield_hdf": "X_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
        "electrode_mode": "bucket", "electrodes": {"e1_plus": ["AF3", "F3"], "e1_minus": ["PO10"], "e2_plus": ["AF4"], "e2_minus": ["Oz"]},
        "n_combinations": n, "total_current_mA": 2.0, "current_step_mA": 0.5, "channel_limit_mA": 1.5}))
    rng = random.Random(0)
    lines = ["Montage,Current_Ch1_mA,Current_Ch2_mA,TImax_ROI,TImean_ROI,TImean_GM,Focality,Composite_Index"]
    for i in range(n):
        mean, foc = rng.uniform(0.05, 0.2), rng.uniform(0.9, 1.2)
        lines.append(f"AF3_PO10 <> AF4_O{i}_I1-{mA[0]}mA_I2-{mA[1]}mA,{mA[0]},{mA[1]},{2 * mean:.4f},{mean:.4f},{mean / foc:.4f},{foc:.4f},{mean * foc:.4f}")
    lines.append(f"F3_PO10 <> AF4_Oz_I1-{mA[0]}mA_I2-{mA[1]}mA,{mA[0]},{mA[1]},0.5,0.3,0.2,1.5,0.45")  # the known winner
    (d / "final_output.csv").write_text("\n".join(lines) + "\n")
    return d


def _ex_rec(tmp_path, **kw) -> dict:
    from tit.reporting.generators import ex_search as ex

    lf = tmp_path / "lf"
    lf.mkdir()
    (lf / "simnibs_simulation_20260923-173824.log").write_text(LEADFIELD_LOG)
    return ex.collect(_ex_dir(tmp_path, **kw), lf)


class TestExSearch:
    def test_results_are_ranked_by_composite_and_parsed(self, tmp_path):
        rows = _ex_rec(tmp_path)["rows"]
        assert rows[0]["pairs"] == [["F3", "PO10"], ["AF4", "Oz"]] and rows[0]["Composite_Index"] == 0.45
        assert [r["Composite_Index"] for r in rows] == sorted((r["Composite_Index"] for r in rows), reverse=True)

    def test_leadfield_geometry_comes_from_its_log(self, tmp_path):
        from tit.reporting.generators import ex_search as ex

        lf = ex.leadfield_facts(LEADFIELD_LOG)
        assert (lf["shape"], lf["dimensions"], lf["thickness"], lf["tensor"]) == ("ellipse", "10, 10", "4", None)

    def test_page_structure_no_checks_table_and_chart(self, tmp_path):
        from tit.reporting.generators import ex_search as ex

        with patch(CAP, return_value=FAKE):
            html = ex.build_html(_ex_rec(tmp_path, mA=(4.5, 0.5)), "X")
        _structure(
            html,
            ("verdict", "winner", "results", "target", "technical"),
            ex.SIZE_BUDGET,
            require_status=False,
        )
        assert not _advisory_ids(html) and 'class="tbl gate"' not in html  # no checks, even at 4.5 mA
        assert 'class="callout' not in html and "Electrode current" not in html
        assert '<h2 id="verdict-h">F3–PO10 ‖ AF4–Oz leads 41 montages</h2>' in html
        table = html.split('sortable">')[1].split("</table>")[0]
        assert table.count("<tr>") == ex.TOP_N + 1  # header + top 25
        assert html.count('fill="none" stroke="var(--s2)"') == ex.TOP_N - 1  # rings for 2..25
        assert "ellipse 10×10 mm, gel 4 mm" in html and "4.5 / 0.5 mA per channel, 5 mA total" in html
        assert "Montage on the EEG cap" not in html and "<img" not in html  # no cap overlay
        assert "F3 → PO10, 4.5 mA" in html and "AF4 → Oz, 0.5 mA" in html  # the winner's electrodes

    def test_a_full_size_search_stays_under_budget(self, tmp_path):
        from tit.reporting.generators import ex_search as ex

        with patch(CAP, return_value=FAKE):
            html = ex.build_html(_ex_rec(tmp_path, n=48_000), "X")
        assert len(html.encode()) < ex.SIZE_BUDGET

    def test_ex_search_writes_a_report_and_survives_its_failure(self):
        from tit.opt.ex import ex as ex_run

        logger = MagicMock()
        with patch("tit.reporting.generators.ex_search.create_ex_search_report", side_effect=OSError("gone")) as create, \
                patch("tit.opt.ex.ex.get_path_manager", return_value=MagicMock(project_dir="/p")):
            ex_run._write_report("X", "/p/run", logger)
        create.assert_called_once_with("/p", "X", "/p/run")
        assert "gone" in logger.warning.call_args[0][0]


# ── every report: the reference list is exactly what the page cites ──────


def _report_html(kind: str, tmp_path: Path) -> str:
    from tit.reporting.generators import dti_qc, ex_search, flex_search

    with patch(CAP, return_value=FAKE):
        if kind == "dti_qc":
            return dti_qc.build_html(_record(), _images(), "X")
        if kind == "simulation":
            return sim.build_html(_with_envelope(sim.collect(_sim_dir(tmp_path))), _sim_images(), "X")
        if kind == "flex_search":
            return flex_search.build_html(_flex_rec(tmp_path), "X")
        return ex_search.build_html(_ex_rec(tmp_path), "X")


@pytest.mark.parametrize("kind", ["dti_qc", "simulation", "flex_search", "ex_search"])
def test_references_are_exactly_what_the_page_cites(tmp_path, kind):
    """Both ways, from the generator's real output: every listed reference is cited by something
    rendered on the page, and every citation rendered on the page is listed."""
    html = _report_html(kind, tmp_path)
    cited = set(re.findall(r'<a class="cite" href="#ref-([^"]+)"', html))
    listed = set(re.findall(r'<li id="ref-([^"]+)"', html))
    assert cited, "the page cites nothing, so there is nothing to check"
    assert listed - cited == set(), f"listed but not cited on the page: {listed - cited}"
    assert cited - listed == set(), f"cited on the page but not listed: {cited - listed}"
