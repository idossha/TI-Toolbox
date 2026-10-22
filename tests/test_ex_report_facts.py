"""The ex-search report states the run's own channel limit, leadfield geometry and target.

Pins (2026-10-22), each a false statement the page used to make:

* Channel limit. ``channel_limit=None`` (the Python default, and a cleared desktop field) means
  ``total - step`` (``ExConfig`` docstring; ``ex.py`` passes that to ``generate_current_ratios``).
  The dose record printed ``fmt(channel_limit_mA or 0)``: "at most 0 mA per channel". With total
  2 mA in 0.2 mA steps the largest channel current is 2.0 - 0.2 = 1.8 mA (hand arithmetic: the
  other channel keeps at least one step).
* Leadfield log. Electrode geometry and conductivity came from the newest
  ``leadfields/simnibs_simulation_*.log``, whatever net it was for. Dataset 000 sub-101 has the
  Jul-29 EEG10-10 log that built the runs' leadfield, later GSN-185/BioSemi-128 attempts, and
  header-only aborted logs; the newest is BioSemi. The page must use the log whose "EEG Cap:" line
  names the run's net (preferring the one that names the run's HDF5), never another net's, and
  must not print "?" or claim a conductivity model the log does not state ("Using isotropic
  conductivities" / "Using anisotropic ... based on the file:" are SimNIBS's own lines, copied
  from sub-101's and sub-ernie's real logs).
* Target. ``run_config.json`` did not record ``roi_names``/``roi_atlas``/``roi_coordinate_space``,
  so a combined, MNI or atlas target without a ROI plate was described as "sphere of 3 mm around
  the centre in L-Insula+R-Insula.csv". ``save_run_config`` now records them and the page reads
  them; an older run that lacks them is not called a sphere.

Expected strings come from the fixture text written here (log lines, file names, config values).

Reproduce: ``.venv/bin/python -m pytest tests/test_ex_report_facts.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_HEADER = "Montage,Current_Ch1_mA,Current_Ch2_mA,TImax_ROI,TImean_ROI,TImean_GM,Focality,Composite_Index"
_HDF = "101_leadfield_EEG10-10_UI_Jurak_2007.hdf5"
_STAMP = "[ simnibs 4.6.0 - 2026-07-29 19:43:43,469 - 1 ]INFO: "


def _log(cap: str | None, shape="ellipse", dims="10, 10", gel="4", cond=None, hdf=None):
    lines = [
        f"{_STAMP}Running simulations in the directory: /mnt/000/sub-101/leadfields",
        f"{_STAMP}Head Mesh:          /mnt/000/sub-101/m2m_101/101.msh",
    ]
    if cap:
        lines.append(f"{_STAMP}EEG Cap: /mnt/000/sub-101/m2m_101/eeg_positions/{cap}")
    if shape:
        lines += [
            f"{_STAMP}Placing Electrode:",
            "definition: plane",
            f"shape: {shape}",
            "centre: [ -5.2377 -20.1594  58.0596]",
            f"dimensions: [{dims}]",
            f"thickness:[{gel}]",
            "channelnr: 1",
        ]
    if cond == "aniso":
        lines.append(
            f"{_STAMP}Using anisotropic volume normalized conductivities based on the file: "
            "/mnt/000/sub-101/m2m_101/DTI_coregT1_tensor.nii.gz"
        )
    elif cond == "iso":
        lines.append(f"{_STAMP}Using isotropic conductivities")
    if hdf:
        lines += [
            f"{_STAMP}Final HDF5 file:",
            f"{_STAMP}/mnt/000/sub-101/leadfields/{hdf}",
        ]
    return "\n".join(lines) + "\n"


_ABORTED = _log(None, shape=None)  # header lines only, like 20260904-035530.log


def _run(tmp_path: Path, **cfg_over) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    cfg = {
        "subject_id": "101",
        "roi_name": "thal.csv",
        "roi_radius": 3.0,
        "leadfield_hdf": f"/mnt/000/derivatives/SimNIBS/sub-101/leadfields/{_HDF}",
        "electrode_mode": "pool",
        "electrodes": {"electrodes": ["AF7", "AFz", "CP6", "P10"]},
        "total_current_mA": 2.0,
        "current_step_mA": 0.5,
        "channel_limit_mA": 1.5,
        **cfg_over,
    }
    (run / "run_config.json").write_text(json.dumps(cfg))
    (run / "final_output.csv").write_text(
        f"{_HEADER}\n"
        "AF7_AFz <> CP6_P10_I1-1.2mA_I2-0.8mA,1.2,0.8,0.19,0.07,0.07,0.99,0.069\n"
        "AF7_CP6 <> AFz_P10_I1-1.0mA_I2-1.0mA,1.0,1.0,0.1,0.05,0.07,0.7,0.035\n"
    )
    return run


def _leadfields(tmp_path: Path, logs: dict[str, str]) -> Path:
    lf = tmp_path / "leadfields"
    lf.mkdir()
    for stamp, text in logs.items():
        (lf / f"simnibs_simulation_{stamp}.log").write_text(text)
    return lf


def _html(run: Path, lf: Path | None = None) -> str:
    from tit.reporting.generators import ex_search

    with patch("tit.tools.montage_visualizer.montage_webp", return_value=None):
        return ex_search.build_html(ex_search.collect(run, lf), "101")


def _section(html: str, sid: str) -> str:
    return html.split(f'id="{sid}"', 1)[1].split("</section>", 1)[0]


def _text(fragment: str) -> str:
    return re.sub(r"<[^>]+>", " ", fragment)


# ── channel limit ───────────────────────────────────────────────────────


def test_an_unset_channel_limit_is_reported_as_total_minus_step(tmp_path):
    run = _run(
        tmp_path, total_current_mA=2.0, current_step_mA=0.2, channel_limit_mA=None
    )
    winner = _text(_section(_html(run), "winner"))
    assert "2 mA total in 0.2 mA steps, at most 1.8 mA per channel" in winner
    assert "at most 0 mA" not in winner


def test_a_set_channel_limit_is_reported_as_set(tmp_path):
    run = _run(tmp_path, channel_limit_mA=1.5)
    assert "at most 1.5 mA per channel" in _text(_section(_html(run), "winner"))


# ── leadfield log ───────────────────────────────────────────────────────


def test_geometry_and_conductivity_come_from_the_log_of_the_runs_net(tmp_path):
    lf = _leadfields(
        tmp_path,
        {
            "20260729-194343": _log(
                "EEG10-10_UI_Jurak_2007.csv", cond="aniso", hdf=_HDF
            ),
            "20260911-002821": _log(
                "BioSemi-128-A1.csv", shape="rect", dims="20, 20", gel="2", cond="iso"
            ),
            "20260912-000000": _ABORTED,  # newest of all
        },
    )
    html = _html(_run(tmp_path), lf)
    winner = _text(_section(html, "winner"))
    assert "ellipse 10×10 mm, gel 4 mm" in winner
    assert "anisotropic" in winner
    assert "rect" not in winner and "20×20" not in winner
    assert not re.search(r"\bisotropic\b", winner)


def test_a_newer_attempt_for_the_same_net_does_not_displace_the_log_that_built_the_hdf5(
    tmp_path,
):
    lf = _leadfields(
        tmp_path,
        {
            "20260729-194343": _log("EEG10-10_UI_Jurak_2007.csv", cond="iso", hdf=_HDF),
            # A later attempt for the same net that placed electrodes and then died.
            "20260903-000000": _log(
                "EEG10-10_UI_Jurak_2007.csv", shape="rect", dims="20, 20", gel="2"
            ),
        },
    )
    winner = _text(_section(_html(_run(tmp_path), lf), "winner"))
    assert "ellipse 10×10 mm, gel 4 mm" in winner
    assert re.search(r"\bisotropic\b", winner)


def test_only_other_nets_and_aborted_logs_mean_not_recorded_and_no_guesses(tmp_path):
    lf = _leadfields(
        tmp_path,
        {
            "20260911-002821": _log("BioSemi-128-A1.csv", shape="rect", cond="iso"),
            "20260912-000000": _ABORTED,
        },
    )
    html = _html(_run(tmp_path), lf)
    winner = _text(_section(html, "winner"))
    assert "as in the leadfield (not recorded)" in winner
    assert "?" not in winner
    assert "isotropic" not in winner  # neither model is claimed without the log line
    assert "isotropic" not in _text(_section(html, "technical"))


def test_a_log_without_a_conductivity_line_claims_no_model(tmp_path):
    lf = _leadfields(
        tmp_path, {"20260729-194343": _log("EEG10-10_UI_Jurak_2007.csv", cond=None)}
    )
    html = _html(_run(tmp_path), lf)
    assert "ellipse 10×10 mm, gel 4 mm" in _text(_section(html, "winner"))
    assert "isotropic" not in _text(html.split("<body", 1)[1].split("<script", 1)[0])


# ── target ──────────────────────────────────────────────────────────────


def _cfg(**kw):
    from tit.opt.config import ExConfig

    return ExConfig(
        subject_id="101",
        leadfield_hdf=_HDF,
        electrodes=ExConfig.PoolElectrodes(electrodes=["AF7", "AFz", "CP6", "P10"]),
        **kw,
    )


def test_save_run_config_records_the_roi_definition(tmp_path):
    from tit.opt.ex.results import save_run_config

    config = _cfg(
        roi_name="L-Insula+R-Insula",
        roi_names=["L-Insula", "R-Insula"],
        roi_atlas=[
            {"atlas_path": "/p/m2m_101/segmentation/labeling.nii.gz", "label": 10},
            {"atlas_path": "/p/MNI_mask.nii.gz", "label": None, "atlas_space": "mni"},
        ],
        roi_coordinate_space="mni",
    )
    saved = json.loads(
        Path(save_run_config(config, 2, str(tmp_path), MagicMock())).read_text()
    )
    assert saved["roi_names"] == ["L-Insula.csv", "R-Insula.csv"]
    assert saved["roi_coordinate_space"] == "mni"
    assert saved["roi_atlas"] == [
        {
            "atlas_path": "/p/m2m_101/segmentation/labeling.nii.gz",
            "label": 10,
            "atlas_space": "subject",
        },
        {"atlas_path": "/p/MNI_mask.nii.gz", "label": None, "atlas_space": "mni"},
    ]


def test_save_run_config_records_a_single_sphere_target_as_such(tmp_path):
    from tit.opt.ex.results import save_run_config

    saved = json.loads(
        Path(
            save_run_config(_cfg(roi_name="thal"), 2, str(tmp_path), MagicMock())
        ).read_text()
    )
    assert (saved["roi_names"], saved["roi_atlas"], saved["roi_coordinate_space"]) == (
        None,
        None,
        "subject",
    )


def _target(html: str) -> str:
    return _text(_section(html, "target"))


def test_a_combined_sphere_target_names_each_roi_file(tmp_path):
    run = _run(
        tmp_path,
        roi_name="L-Insula+R-Insula.csv",
        roi_names=["L-Insula.csv", "R-Insula.csv"],
        roi_atlas=None,
        roi_coordinate_space="subject",
    )
    target = _target(_html(run))
    assert "L-Insula.csv" in target and "R-Insula.csv" in target
    assert "L-Insula+R-Insula.csv" not in target
    assert "3 mm" in target and "MNI" not in target


def test_an_mni_sphere_target_says_mni(tmp_path):
    run = _run(
        tmp_path,
        roi_name="L-Insula.csv",
        roi_names=None,
        roi_atlas=None,
        roi_coordinate_space="mni",
    )
    target = _target(_html(run))
    assert "MNI" in target and "L-Insula.csv" in target


def test_an_atlas_only_target_is_not_called_a_sphere(tmp_path):
    run = _run(
        tmp_path,
        roi_name="labeling.nii.gz_1region.csv",
        roi_names=[],
        roi_atlas=[
            {
                "atlas_path": "/p/m2m_101/segmentation/labeling.nii.gz",
                "label": 10,
                "atlas_space": "subject",
            }
        ],
        roi_coordinate_space="subject",
    )
    html = _html(run)
    target = _target(html)
    assert "label 10" in target and "labeling.nii.gz" in target
    assert "sphere" not in html and "labeling.nii.gz_1region.csv" not in target


def test_an_older_run_without_the_roi_definition_is_not_called_a_sphere(tmp_path):
    # sub-101/ex-search/20260914_112857: an atlas run whose run_config lacks the ROI fields.
    run = _run(tmp_path, roi_name="labeling.nii.gz_1region.csv", roi_radius=3)
    html = _html(run)
    assert "sphere" not in html
    assert "labeling.nii.gz_1region.csv" in _target(html)
    assert "not recorded" in _target(html)


def test_a_roi_plate_still_wins_over_the_recorded_definition(tmp_path):
    run = _run(tmp_path, roi_names=["A.csv", "B.csv"], roi_coordinate_space="subject")
    (run / "roi.tetravox.json").write_text(
        json.dumps({"meta": {"roi": "Left insula", "space": "subject"}})
    )
    target = _target(_html(run))
    assert "Left insula" in target and "A.csv" not in target
