"""Simulator, flex-search and ex-search reports: structure and rules, not pixels.

Pins (2026-09-28, ARCHITECTURE.md §14):
* each page has its sections, every contents link lands on an element, every image has alt text,
  every figure a caption, statuses are icon + word, and nothing is fetched (doi.org links only);
* the advisories shown are exactly the ``RULES`` advisories for that report, with the rule's label,
  role and citations; current checks are advisories (never blocking) and state the total current;
* a failed software check is named in the verdict; the page stays under its size budget;
* the pipelines call the report writers, and a report that cannot be written never fails a run.

Inputs are synthetic files in the formats the pipelines write (SimNIBS log and field-summary lines
copied in shape from sub-ernie's outputs, values chosen here). The cap image is stand-in bytes: the
overlay itself is ``tit.tools.montage_visualizer`` (ImageMagick), exercised by the real-data rebuild
``python -m tit.reporting.generators.<simulation|flex_search|ex_search>``. No pixel goldens.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.test_reporting_dti_qc import FAKE, _parse
from tit.reporting.generators import common
from tit.reporting.generators import simulation as sim
from tit.reporting.qc_rules import RULES

CAP = "tit.tools.montage_visualizer.montage_webp"


def _structure(html: str, sections: tuple[str, ...], budget: int) -> None:
    page = _parse(html)
    assert all(s in page.ids for s in sections), [s for s in sections if s not in page.ids]
    assert page.toc and all(h[1:] in page.ids for h in page.toc)
    assert all(alt.strip() for alt in page.imgs)
    assert page.figures == page.captions
    assert all(u.startswith("https://doi.org/") for u in page.urls), page.urls
    assert "url(http" not in html and "@import" not in html
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


def _sim_dir(tmp_path: Path, mA: float = 1.0, imbalance: float = 0.0) -> Path:
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
    (d / "documentation" / "simnibs_simulation_20260923-184120.log").write_text(LOG.format(a=mA / 1e3, b=mA / 1e3 + imbalance))
    (d / "high_Frequency" / "analysis" / "fields_summary.txt").write_text(SUMMARY)
    return d


def _with_roi(rec: dict) -> dict:
    rec["envelope"] = {"median": 0.17, "p99_9": 0.36, "max": 0.48}
    rec["roi"] = {"name": "thalamus", "space": "voxel", "type": "mask", "mean": 0.2, "max": 0.4, "focality": 1.1,
                  "gm_mean": 0.18, "n": 100.0, "mask": None, "folder": "thalamus"}
    return rec


class TestSimulation:
    def test_parsers_read_the_simnibs_formats(self, tmp_path):
        carriers = sim.parse_fields_summary(SUMMARY)
        assert [c_["name"] for c_ in carriers] == ["X_TDCS_1", "X_TDCS_2"]
        assert carriers[1]["p99.9"] == 0.3 and carriers[0]["p95.0"] == 0.05
        log = sim.parse_log(LOG.format(a=0.001, b=0.001))
        assert log["currents_A"] == [[0.001, -0.001], [0.001, -0.001]]
        assert log["tensor"].endswith("DTI_coregT1_tensor.nii.gz") and log["n_solved"] == 2
        assert log["simnibs"] == "4.6.0" and log["calibration_error_pct"] == [3.4]

    def test_page_structure_and_advisories(self, tmp_path):
        rec = _with_roi(sim.collect(_sim_dir(tmp_path)))
        with patch(CAP, return_value=FAKE):
            html = sim.build_html(rec, None, "X")
        _structure(html, ("verdict", "montage", "field", "safety", "technical"), sim.SIZE_BUDGET)
        advisory = {k for k, r in RULES["sim"].items() if r["role"] == "advisory"}
        assert set(_advisory_ids(html)) == {RULES["sim"][k]["label"] for k in advisory}
        assert "1 mA per electrode (2 mA total)" in html
        assert "per channel or to the total" in html  # the unverified Cassarà reading is stated
        assert '<h2 id="verdict-h">0.200 V/m mean envelope in the ROI</h2>' in html
        assert "<b>below</b> the published range" in html  # 0.2 < 0.24 V/m at 2 mA total
        assert "from the subject's DTI tensor" in html

    def test_brain_current_density_is_the_stated_estimate(self, tmp_path):
        from tit.constants import CONDUCTIVITY_GRAY_MATTER

        rows = {r.id: r for r in sim.checks(sim.collect(_sim_dir(tmp_path)))}
        assert rows["brain_peak_J"].shown == f"≈ {CONDUCTIVITY_GRAY_MATTER * (0.2 + 0.3):.2g} A/m² (estimate)"
        assert rows["brain_peak_J"].status == "pass" and rows["brain_peak_J"].role == "advisory"

    def test_high_current_warns_and_never_blocks(self, tmp_path):
        rows = sim.checks(sim.collect(_sim_dir(tmp_path, mA=5.0)))
        current = next(r for r in rows if r.id == "electrode_peak_current")
        assert current.status == "warn" and not current.blocking
        with patch(CAP, return_value=None):
            html = sim.build_html(_with_roi(sim.collect(_sim_dir(tmp_path / "b", mA=5.0))), None, "X")
        assert "Electrode current: 5 mA per electrode (10 mA total) (rule &lt; 4 mA)." in html
        assert 'class="callout warn"' in html

    def test_unbalanced_currents_fail_the_software_check(self, tmp_path):
        with patch(CAP, return_value=None):
            html = sim.build_html(sim.collect(_sim_dir(tmp_path, imbalance=1e-4)), None, "X")
        assert "Software check failed: Current conservation" in html
        assert '<details class="raw" open><summary>Software checks' in html

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
    def test_current_check_names_per_electrode_and_total(self):
        row = common.current_check("opt", [1.5, 0.5])
        assert row.shown == "1.5 mA per electrode (2 mA total)" and row.status == "pass"
        assert row.role == "advisory" and list(row.cite) == RULES["opt"]["electrode_peak_current"]["cite"]

    def test_target_range_numbers_match_the_cited_text(self):
        r = RULES["sim"]["roi_envelope_V_per_m"]
        lo, hi = r["range"]
        assert r["value"].startswith(f"{lo}–{hi} V/m at {r['at_mA_total']:g} mA total")

    @pytest.mark.parametrize("section", ["sim", "opt"])
    def test_current_checks_are_advisories(self, section):
        assert RULES[section]["electrode_peak_current"]["role"] == "advisory"
