"""``regenerate_plots`` finds the subject's EEG-position CSV from the run folder.

Pins (2026-10-22): ``simnibs_python -m tit.opt.ex.results <run_dir>`` rebuilds a run's electrode
maps and, without ``--eeg-csv``, infers the cap CSV. It used to build the folder from the
``leadfield_hdf`` recorded in ``run_config.json`` (``<leadfield>/../../m2m_<id>/eeg_positions``),
which only works for a host path: Dataset 000's ernie film run records the bare file name
``ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5`` (so the guess became ``./m2m_ernie/...``,
relative to wherever the command ran) and the sub-101 runs record the container path
``/mnt/000/...``. Both raised "Could not infer an EEG-position CSV".

Expected value: the PathManager layout (``tit/paths.py``) -- a run folder is
``sub-<id>/ex-search/<run>`` (``ex_search_run``) or ``sub-<id>/m-ex-search/<run>``
(``m_ex_search_run``) and the subject's caps are ``sub-<id>/m2m_<id>/eeg_positions/<net>.csv``
(``eeg_positions``), so the CSV is ``<run>/../../m2m_<id>/eeg_positions/<net>.csv`` whatever the
recorded leadfield string looks like. The net name is the part after ``_leadfield_``.

Reproduce: ``.venv/bin/python -m pytest tests/test_ex_regenerate_plots.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tit.paths import get_path_manager

NET = "EEG10-10_UI_Jurak_2007"
HEADER = (
    "Montage,Current_Ch1_mA,Current_Ch2_mA,TImax_ROI,TImean_ROI,TImean_GM,Focality,"
    "Composite_Index\n"
)


def _project(tmp_path: Path, kind: str = "ex") -> tuple[Path, Path]:
    """A project with sub-ernie's cap CSV and one ex (or mEx) run; returns (run_dir, cap_csv)."""
    project = tmp_path / "project"
    project.mkdir()
    pm = get_path_manager(str(project))
    eeg_dir = Path(pm.eeg_positions("ernie"))
    eeg_dir.mkdir(parents=True)
    cap = eeg_dir / f"{NET}.csv"
    cap.write_text("Electrode,-50,0,0,Fp1\nElectrode,50,0,0,Fp2\n")
    run_dir = Path(
        pm.ex_search_run("ernie", "film")
        if kind == "ex"
        else pm.m_ex_search_run("ernie", "film")
    )
    run_dir.mkdir(parents=True)
    (run_dir / "final_output.csv").write_text(
        HEADER + "Fp1_TP8 <> Fp2_TP7_I1-1.5mA_I2-0.5mA,1.5,0.5,0.2,0.1,0.09,1.1,0.11\n"
    )
    return run_dir, cap


def _record(run_dir: Path, leadfield_hdf: str) -> None:
    (run_dir / "run_config.json").write_text(
        json.dumps({"subject_id": "ernie", "leadfield_hdf": leadfield_hdf})
    )


def _leadfield_variants(project: Path) -> dict[str, str]:
    name = f"ernie_leadfield_{NET}.hdf5"
    return {
        # Dataset 000 sub-ernie/ex-search/film_thalamus_bilateral_jurak/run_config.json
        "bare file name": name,
        # Dataset 000 sub-101 runs: written inside the container
        "container path": f"/mnt/000/derivatives/SimNIBS/sub-ernie/leadfields/{name}",
        "host path": str(
            project / "derivatives" / "SimNIBS" / "sub-ernie" / "leadfields" / name
        ),
    }


@pytest.mark.parametrize("kind", ["ex", "mex"])
@pytest.mark.parametrize("variant", ["bare file name", "container path", "host path"])
@patch("tit.opt.ex.results.generate_electrode_maps", return_value=["map.png"])
def test_the_cap_csv_is_found_from_the_run_folder(
    maps, variant, kind, tmp_path, monkeypatch
):
    from tit.opt.ex.results import regenerate_plots

    run_dir, cap = _project(tmp_path, kind)
    _record(run_dir, _leadfield_variants(tmp_path / "project")[variant])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)  # the command does not run from sub-ernie

    assert regenerate_plots(run_dir) == ["map.png"]
    records, eeg_csv, out_dir, _ = maps.call_args.args
    expected = run_dir / ".." / ".." / "m2m_ernie" / "eeg_positions" / f"{NET}.csv"
    assert Path(eeg_csv).resolve() == expected.resolve() == cap.resolve()
    assert out_dir == str(run_dir)
    assert records[0]["electrodes"] == ["Fp1", "TP8", "Fp2", "TP7"]


@patch("tit.opt.ex.results.generate_electrode_maps", return_value=[])
def test_a_relative_run_folder_resolves_from_the_working_directory(
    maps, tmp_path, monkeypatch
):
    """``python -m tit.opt.ex.results .`` from inside the run folder."""
    from tit.opt.ex.results import main

    run_dir, cap = _project(tmp_path)
    _record(run_dir, f"ernie_leadfield_{NET}.hdf5")
    monkeypatch.chdir(run_dir)
    main(["."])
    assert Path(maps.call_args.args[1]).resolve() == cap.resolve()


@patch("tit.opt.ex.results.generate_electrode_maps", return_value=[])
def test_a_net_the_subject_has_no_csv_for_still_asks_for_one(maps, tmp_path):
    """Control: the run folder is searched for the recorded net only, not any CSV it holds."""
    from tit.opt.ex.results import regenerate_plots

    run_dir, _ = _project(tmp_path)
    _record(run_dir, "ernie_leadfield_EEG10-20_Okamoto_2004.hdf5")
    with pytest.raises(ValueError, match="Could not infer an EEG-position CSV"):
        regenerate_plots(run_dir)
    maps.assert_not_called()
