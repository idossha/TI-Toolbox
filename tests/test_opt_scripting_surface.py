"""The scripting surface of ``tit.opt`` does what its config says.

Pins (2026-10-31, assessment items A1-2, A1-3, A1-5, A1-6, A1-9, S2-3):

* ``run_flex_search`` honours ``FlexConfig.mode``: an adaptive config runs the mean calibration
  then the focality run with thresholds from the achievable intensity (it used to run one
  fixed-threshold search); the drivers are importable from ``tit.opt``.
* A relative ``FlexConfig.output_folder`` names a run folder under the subject's
  ``flex-search/``, not under the current working directory (the docstring example
  ``"insula_mean"``).
* ROI ``tissues`` and ``hemisphere`` outside their accepted values are refused instead of
  silently resolving to grey matter / an unknown hemisphere.
* The flex, ex and mex runners remove the per-run log file handlers they attached.
* ``ExConfig.total_current``/``roi_radius`` (and ``MExConfig.current_mA``/``roi_radius``) must
  be finite and above 0 (``nan <= 0`` is False); the ex/mex ``AtlasROI`` accepts ``"MNI"`` as
  the flex ``SubcorticalROI`` does.
* ex/mex record the electrode of the leadfield they read (the path under the subject's
  ``leadfields/``), not of ``leadfield_hdf`` resolved against the working directory.

The flex runs use :class:`tests.test_flex_rerun_same_folder.FakeOpt` (objective
``-mean(ROI) x scale``, ``mean(ROI)`` = 0.25 V/m): calibration scale 1.6 gives an achievable
0.4 V/m, so the default adaptive 80/20 % thresholds are 0.08 and 0.32 V/m, written out here.

Reproduce: ``.venv/bin/python -m pytest tests/test_opt_scripting_surface.py -q -p no:cacheprovider``
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from tests.test_flex_rerun_same_folder import (  # noqa: F401  (flex_project is a fixture)
    flex_config,
    flex_project,
)
from tit.opt.config import ExConfig, FlexConfig, MExConfig


@pytest.fixture(autouse=True)
def _no_plot(monkeypatch):
    monkeypatch.setattr("tit.opt.flex.pareto.generate_pareto_plot", lambda *a: None)


# -- A1-2: mode is honoured ------------------------------------------------------------------


def test_run_flex_search_runs_an_adaptive_config_as_adaptive(flex_project):
    from tit.opt import run_flex_search

    pm, scales = flex_project
    scales[:] = [1.6, 100.0]
    folder = Path(pm.flex_search("001")) / "adaptive"
    config = flex_config(str(folder), goal="focality", mode="flex_adaptive")

    result = run_flex_search(config)

    assert result.success
    calibration = json.loads(
        (folder / "mean_calibration" / "flex_meta.json").read_text()
    )
    assert calibration["goal"] == "mean"
    meta = json.loads((folder / "flex_meta.json").read_text())
    assert meta["goal"] == "focality"
    assert meta["thresholds"] == "0.0800,0.3200"


def test_the_drivers_are_exported_from_tit_opt():
    import tit.opt
    from tit.opt.flex import drivers

    assert tit.opt.run_adaptive_focality is drivers.run_adaptive_focality
    assert tit.opt.run_pareto_sweep is drivers.run_pareto_sweep
    assert {"run_adaptive_focality", "run_pareto_sweep"} <= set(tit.opt.__all__)


# -- A1-3: a relative output folder lands under flex-search/ ---------------------------------


def test_a_relative_output_folder_is_a_run_under_flex_search(
    flex_project, tmp_path, monkeypatch
):
    from tit.opt.flex.flex import run_flex_search

    pm, _ = flex_project
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    result = run_flex_search(flex_config("insula_mean"))

    expected = Path(pm.flex_search("001")) / "insula_mean"
    assert Path(result.output_folder) == expected
    assert (expected / "flex_meta.json").is_file()
    assert list(elsewhere.iterdir()) == []


def test_a_relative_output_folder_of_a_driver_is_under_flex_search(
    flex_project, tmp_path, monkeypatch
):
    from tit.opt.flex.drivers import run_adaptive_focality

    pm, scales = flex_project
    scales[:] = [1.6, 100.0]
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    run_adaptive_focality(flex_config("adapt", goal="focality", mode="flex_adaptive"))

    assert (Path(pm.flex_search("001")) / "adapt" / "flex_meta.json").is_file()
    assert list(elsewhere.iterdir()) == []


# -- A1-6: no file handler outlives its run --------------------------------------------------


def test_flex_search_removes_its_file_handlers(flex_project):
    from tit.opt.flex.flex import run_flex_search

    pm, _ = flex_project
    names = ("tit.opt.flex.001", "simnibs")
    before = {n: list(logging.getLogger(n).handlers) for n in names}
    run_flex_search(flex_config(str(Path(pm.flex_search("001")) / "r")))
    assert {n: logging.getLogger(n).handlers for n in names} == before


# -- A1-5: ROI tissues and hemisphere ----------------------------------------------------------


@pytest.mark.parametrize("tissues", ["CSF", "gm+wm", ""])
def test_unknown_roi_tissues_are_refused(tissues):
    with pytest.raises(ValueError, match="tissues"):
        FlexConfig.SphericalROI(x=0, y=0, z=0, volumetric=True, tissues=tissues)
    with pytest.raises(ValueError, match="tissues"):
        FlexConfig.SubcorticalROI(atlas_path="a.nii.gz", label=1, tissues=tissues)


@pytest.mark.parametrize("tissues", ["GM", "WM", "both", "BOTH", "wm"])
def test_accepted_roi_tissues_pass(tissues):
    FlexConfig.SphericalROI(x=0, y=0, z=0, tissues=tissues)
    FlexConfig.SubcorticalROI(atlas_path="a.nii.gz", label=1, tissues=tissues)


@pytest.mark.parametrize("hemisphere", ["left", "LH", ["lh", "both"]])
def test_unknown_hemisphere_is_refused(hemisphere):
    labels = [1, 2] if isinstance(hemisphere, list) else 1
    with pytest.raises(ValueError, match="hemisphere"):
        FlexConfig.AtlasROI(
            atlas_path="lh.a.annot", label=labels, hemisphere=hemisphere
        )


def test_both_hemispheres_in_a_union_pass():
    FlexConfig.AtlasROI(atlas_path="a.annot", label=[1, 2], hemisphere=["lh", "rh"])


# -- A1-9: ex/mex numbers and MNI casing -----------------------------------------------------


def _ex(**kw):
    base = dict(
        subject_id="001",
        leadfield_hdf="lf.hdf5",
        roi_name="r",
        electrodes=ExConfig.PoolElectrodes(electrodes=["A", "B", "C", "D"]),
    )
    return ExConfig(**{**base, **kw})


def _mex(**kw):
    base = dict(
        subject_id="001",
        leadfield_hdf="lf.hdf5",
        roi_name="r",
        electrodes=MExConfig.PoolElectrodes(electrodes=list("ABCDEFGH")),
    )
    return MExConfig(**{**base, **kw})


@pytest.mark.parametrize(
    "change",
    [
        {"total_current": float("nan")},
        {"total_current": float("inf")},
        {"current_step": float("nan")},
        {"roi_radius": -1.0},
        {"roi_radius": 0.0},
        {"roi_radius": float("nan")},
        {"channel_limit": float("nan")},
    ],
)
def test_ex_numbers_must_be_finite_and_positive(change):
    with pytest.raises(ValueError):
        _ex(**change)


@pytest.mark.parametrize(
    "change",
    [
        {"current_mA": float("nan")},
        {"roi_radius": -1.0},
        {"roi_radius": float("nan")},
    ],
)
def test_mex_numbers_must_be_finite_and_positive(change):
    with pytest.raises(ValueError):
        _mex(**change)


@pytest.mark.parametrize("cls", [ExConfig.AtlasROI, MExConfig.AtlasROI])
def test_ex_atlas_space_accepts_any_case(cls):
    assert cls(atlas_path="a.nii.gz", label=1, atlas_space="MNI").atlas_space == "mni"
    with pytest.raises(ValueError):
        cls(atlas_path="a.nii.gz", label=1, atlas_space="talairach")


# -- A1-6 (ex, mex) and S2-3: handlers removed; the leadfield's electrode is recorded ---------


def _ex_run(module: str, config, tmp_path):
    """One ex/mex run with the engine and post-processing stubbed; returns the keyword
    arguments ``process_and_save`` received."""
    from unittest.mock import MagicMock, patch

    pm = MagicMock()
    pm.logs.return_value = str(tmp_path / "logs")
    pm.ex_search_run.return_value = str(tmp_path / "o")
    pm.m_ex_search_run.return_value = str(tmp_path / "o")
    pm.rois.return_value = str(tmp_path / "rois")
    pm.leadfields.return_value = str(tmp_path / "leadfields")
    saved = {}

    def save(results, config, output_dir, logger, **kw):
        saved.update(kw)
        return {"config_json_path": "c.json", "csv_path": "c.csv"}

    mex = "mex" in module
    engine = MagicMock()
    engine.run.return_value = {"m": {}}
    with (
        patch(f"{module}.get_path_manager", return_value=pm),
        patch(f"{module}.process_and_save", side_effect=save),
        patch(f"{module}.refuse_electrodes_off_leadfield"),
        patch(
            f"{module}.{'MExSearchEngine' if mex else 'ExSearchEngine'}",
            return_value=engine,
        ),
        patch(f"{module}._write_report"),
    ):
        runner = __import__(module, fromlist=["x"])
        (runner.run_m_ex_search if mex else runner.run_ex_search)(config)
    return saved


@pytest.mark.parametrize("module", ["tit.opt.ex.ex", "tit.opt.mex.mex"])
def test_ex_searches_remove_their_handlers_and_pass_the_resolved_leadfield(
    module, tmp_path
):
    mex = "mex" in module
    config = (_mex if mex else _ex)(leadfield_hdf="lf.hdf5")
    names = (f"tit.opt.{'m_ex_search' if mex else 'ex_search'}.001", "simnibs")
    before = {n: list(logging.getLogger(n).handlers) for n in names}

    saved = _ex_run(module, config, tmp_path)

    assert {n: logging.getLogger(n).handlers for n in names} == before
    assert saved["leadfield_path"] == str(tmp_path / "leadfields" / "lf.hdf5")


def test_run_config_reads_the_electrode_beside_the_resolved_leadfield(
    tmp_path, monkeypatch
):
    from unittest.mock import MagicMock

    from tit.opt.ex.results import save_run_config
    from tit.opt.leadfield import write_leadfield_sidecar

    hdf5 = tmp_path / "leadfields" / "lf.hdf5"
    hdf5.parent.mkdir()
    hdf5.write_bytes(b"lf")
    electrode = {
        "electrode_shape": "rect",
        "electrode_dimensions": [12.0, 6.0],
        "gel_thickness": 2.5,
        "rubber_thickness": 3.0,
    }
    write_leadfield_sidecar(hdf5, electrode)
    monkeypatch.chdir(tmp_path)  # a bare "lf.hdf5" does not resolve from here
    path = save_run_config(
        _ex(leadfield_hdf="lf.hdf5"),
        1,
        str(tmp_path),
        MagicMock(),
        leadfield_path=str(hdf5),
    )
    assert json.loads(Path(path).read_text())["leadfield_electrode"] == electrode
