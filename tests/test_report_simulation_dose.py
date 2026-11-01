"""config.json and the simulation report state the currents and conductivities that ran.

Pins (2026-10-22, package p03):

* config.json records the montage's own currents: SimNIBS reads ``intensities[0:2]`` for a TI
  montage (``TISimulation._build_session``) and ``intensities[0:num_pairs]`` for mTI
  (``mTISimulation``); ``SimulationConfig`` accepts a longer list (one list serves a mixed TI + mTI
  config). It used to record the whole list, and the report then counted every value as a channel.
* The report reads only one current per pair, also from a config.json written before the fix, and
  its total is the sum of the channel amplitudes ``|I|`` (a negative current is a polarity, not a
  negative dose).
* config.json records the tissue-conductivity overrides the run applied
  (``SimulationConfig.tissue_conductivities``, applied by
  ``BaseSimulation._apply_tissue_conductivities`` -- pinned by
  ``tests/test_sim_scripting_surface.py``), and the report names them instead of claiming
  SimNIBS standard values.

Expected values are worked out by hand from the inputs written in each test: [1, 2] mA is
"1 / 2 mA per channel", 3 mA total; [1, -2] mA is 3 mA total; tissue 2 at 0.4 S/m is
"tissue 2 = 0.4 S/m".
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.test_report_simulation_modes import NET, NET_MTI, write_run
from tests.test_reporting_runs import CAP, _sim_dir, _with_envelope
from tit.reporting.generators import simulation as sim
from tit.sim.config import Montage, MontageMode, SimulationConfig
from tit.sim.utils import create_simulation_config_file

NET_FILE = "EEG10-10_UI_Jurak_2007.csv"


@pytest.fixture
def no_tissue_overrides(monkeypatch):
    """No TISSUE_COND_<n> in the environment, whatever the developer's shell holds."""
    for key in [k for k in os.environ if k.startswith("TISSUE_COND_")]:
        monkeypatch.delenv(key)


def _ti(name="ti"):
    return Montage(
        name=name, mode=MontageMode.NET, electrode_pairs=NET, eeg_net=NET_FILE
    )


def _mti(name="mti"):
    return Montage(
        name=name, mode=MontageMode.NET, electrode_pairs=NET_MTI, eeg_net=NET_FILE
    )


def _written(tmp_path: Path, cfg: SimulationConfig, montage: Montage) -> dict:
    doc = tmp_path / montage.name
    doc.mkdir()
    create_simulation_config_file(cfg, montage, str(doc), logging.getLogger("test"))
    return json.loads((doc / "config.json").read_text())


def _report(sim_dir: Path) -> str:
    with patch(CAP, return_value=None):
        return sim.build_html(_with_envelope(sim.collect(sim_dir)), None, "X")


def _old_config(tmp_path: Path, **changes) -> Path:
    """A simulation folder whose config.json was written before the fix (v3.1.1 shape)."""
    d = _sim_dir(tmp_path)
    path = d / "documentation" / "config.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), **changes}))
    return d


# ── config.json ──────────────────────────────────────────────────────────


def test_config_json_records_each_montages_own_currents(tmp_path, no_tissue_overrides):
    cfg = SimulationConfig(
        subject_id="X", montages=[_ti(), _mti()], intensities=[1.0, 2.0, 3.0, 4.0]
    )
    assert _written(tmp_path, cfg, _ti())["intensities"] == [1.0, 2.0]
    assert _written(tmp_path, cfg, _mti())["intensities"] == [1.0, 2.0, 3.0, 4.0]


def test_config_json_records_the_tissue_overrides_that_ran(
    tmp_path, no_tissue_overrides
):
    # BaseSimulation._apply_tissue_conductivities applies the config's overrides to each channel.
    cfg = SimulationConfig(
        subject_id="X", montages=[_ti()], tissue_conductivities={2: 0.4, 10: 0.16}
    )
    assert _written(tmp_path, cfg, _ti())["tissue_conductivities"] == {
        "2": 0.4,
        "10": 0.16,
    }


def test_config_json_ignores_a_tissue_variable_left_in_the_environment(
    tmp_path, monkeypatch, no_tissue_overrides
):
    # The removed side channel: an exported TISSUE_COND_3 no longer changes the run.
    monkeypatch.setenv("TISSUE_COND_3", "1.654")
    cfg = SimulationConfig(subject_id="X", montages=[_ti()])
    assert _written(tmp_path, cfg, _ti())["tissue_conductivities"] == {}


def test_config_json_records_no_overrides_when_none_ran(tmp_path, no_tissue_overrides):
    cfg = SimulationConfig(subject_id="X", montages=[_ti()])
    assert _written(tmp_path, cfg, _ti())["tissue_conductivities"] == {}


# ── the report ───────────────────────────────────────────────────────────


def test_report_of_a_ti_montage_in_a_mixed_config_counts_its_two_channels(
    tmp_path, no_tissue_overrides
):
    d = write_run(tmp_path, _ti("M"), intensities=[1.0, 2.0, 3.0, 4.0])
    page = _report(d)
    assert "at 1 / 2 mA per channel (3 mA total)" in page
    assert "2 channels × 1 / 2 mA" in page
    assert "<dt>Total current</dt><dd>3 mA</dd>" in page  # masthead
    assert "10 mA" not in page and "4 channels" not in page


@pytest.mark.parametrize(
    "intensities,per_channel,total,channels",
    [
        (
            [1, 1, 1, 1],
            "1",
            "2",
            "2 channels × 1 mA",
        ),  # v3.1.1 recorded every configured value
        ([1, 2, 3], "1 / 2", "3", "2 channels × 1 / 2 mA"),
        ([1.0, -2.0], "1 / -2", "3", "2 channels × 1 / -2 mA"),  # |1| + |-2|
    ],
)
def test_report_counts_one_current_per_pair_and_sums_amplitudes(
    tmp_path, intensities, per_channel, total, channels
):
    page = _report(_old_config(tmp_path, intensities=intensities))
    assert f"at {per_channel} mA per channel ({total} mA total)" in page
    assert channels in page
    assert f"<dt>Total current</dt><dd>{total} mA</dd>" in page
    assert f"{per_channel} mA per channel, {total} mA total" in page  # the Dose listing


@pytest.mark.parametrize("cond", ["scalar", "vn"])
def test_report_names_the_tissue_overrides(tmp_path, cond):
    page = _report(
        _old_config(
            tmp_path, conductivity=cond, tissue_conductivities={"2": 0.4, "10": 0.16}
        )
    )
    overrides = "tissue 2 = 0.4 S/m, tissue 10 = 0.16 S/m"  # by tissue number, not as strings sort
    lede = page.split('<p class="lede">', 1)[1].split("</p>", 1)[0]
    methods = page.split('id="methods-text">', 1)[1].split("</div>", 1)[0]
    assert overrides in lede and overrides in methods
    assert "Tissue conductivities were isotropic SimNIBS standard values." not in page
    if cond == "scalar":
        assert f"isotropic SimNIBS standard values except {overrides}." in methods


def test_report_without_overrides_still_says_standard_values(tmp_path):
    page = _report(_old_config(tmp_path, conductivity="scalar"))
    assert "Tissue conductivities were isotropic SimNIBS standard values." in page
    assert "S/m" not in page.split('id="verdict"', 1)[1].split('id="montage"', 1)[0]
