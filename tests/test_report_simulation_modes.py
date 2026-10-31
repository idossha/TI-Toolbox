"""The simulation report renders for every montage mode the simulator runs.

Pins (2026-10-22, package p03):

* net, flex_mapped, flex_free and freehand montages, each as TI (2 pairs) and mTI (4 pairs), get a
  report with all four sections. XYZ montages (flex_free, freehand) crashed ``build_html`` with
  ``TypeError: sequence item 0: expected str instance, list found``; ``BaseSimulation._write_report``
  logged it as a warning, so Dataset 000's flex-free simulations (sub-CHN/left_insula_mean,
  sub-101/20260919_131736_879_1) have no report.
* An XYZ electrode is named by its subject-space position rounded to the millimetre, e.g.
  ``(74, -19, 39)``; the page shows no raw coordinate list (``[[``) and no float with more than three
  decimals outside the config.json listing.
* The channel list has one row per pair and the carrier table one row per carrier, carrier i on
  pair i.
* The pipeline (``BaseSimulation._write_report`` -> the real ``create_simulation_report``) writes
  one report for an XYZ montage and logs no warning.

Where the numbers come from: every config.json is written by the real
``tit.sim.utils.create_simulation_config_file`` from a ``Montage``. The flex_free coordinates are
copied from Dataset 000 ``sub-CHN/Simulations/left_insula_mean/documentation/config.json``
(2026-10-08); the free-hand ones are chosen here. Every rounded name below was rounded by hand from
those numbers (no value sits on a .5). The SimNIBS log and field summary are the shapes in
``tests/test_reporting_runs.py``. Pixels and the cap overlay are elsewhere (``CAP`` is stand-in bytes).
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tests.test_reporting_dti_qc import FAKE
from tests.test_reporting_runs import CAP, LOG, SUMMARY, _structure, _with_envelope
from tit.reporting.generators import simulation as sim
from tit.sim.config import Montage, MontageMode, SimulationConfig
from tit.sim.utils import create_simulation_config_file

SECTIONS = ("verdict", "montage", "field", "technical")

# Dataset 000 sub-CHN/left_insula_mean (flex_free), as config.json stores them.
CHN = [
    (
        [73.97953796386719, -18.586177825927734, 38.58809280395508],
        [-69.9033203125, 35.4944953918457, 37.9424934387207],
    ),
    (
        [-68.37862396240234, 39.93581771850586, 52.04630661010742],
        [76.70392608642578, -9.926175117492676, 49.70404052734375],
    ),
]
CHN_NAMES = ["(74, -19, 39) → (-70, 35, 38)", "(-68, 40, 52) → (77, -10, 50)"]
# Two more flex-free pairs for the 4-pair case (values chosen here).
CHN_MTI = CHN + [
    ([10.2, 60.4, 70.3], [-12.8, -95.1, 20.2]),
    ([45.6, 22.2, -10.4], [-45.6, 22.2, -10.4]),
]
CHN_MTI_NAMES = CHN_NAMES + [
    "(10, 60, 70) → (-13, -95, 20)",
    "(46, 22, -10) → (-46, 22, -10)",
]
FREE = [
    ([-60.4, 10.2, 40.6], [60.0, 10.0, 40.0]),
    ([-60.0, -40.3, 40.0], [60.2, -40.0, 39.7]),
]
FREE_NAMES = ["(-60, 10, 41) → (60, 10, 40)", "(-60, -40, 40) → (60, -40, 40)"]
FREE_MTI = FREE + [
    ([0.3, 80.0, 30.0], [0.0, -100.0, 30.0]),
    ([-70.0, -20.0, 0.0], [70.0, -20.0, 0.0]),
]
FREE_MTI_NAMES = FREE_NAMES + [
    "(0, 80, 30) → (0, -100, 30)",
    "(-70, -20, 0) → (70, -20, 0)",
]

NET = [("AF3", "PO10"), ("AF4", "Oz")]
NET_MTI = NET + [("F3", "P4"), ("F4", "P3")]
MAPPED = [("E010", "E011"), ("E012", "E013")]
MAPPED_MTI = MAPPED + [("E020", "E021"), ("E030", "E031")]

def _polar(names: list[str]) -> str:
    """``"a(+) → b(−), c(+) → d(−) and …"``: the first electrode of a channel carries +I in
    tit.sim (``tdcs.currents = [I, -I]``); coordinates keep their arrow."""
    channels = [n.replace(" → ", "(+) → ") + "(−)" for n in names]
    return ", ".join(channels[:-1]) + " and " + channels[-1]


#: (montage mode, pairs, eeg_net, channel text per pair, the lede's montage phrase)
CASES = {
    "net-TI": (
        MontageMode.NET,
        NET,
        "EEG10-10_UI_Jurak_2007.csv",
        ["AF3 → PO10", "AF4 → Oz"],
        "AF3(+)–PO10(−) and AF4(+)–Oz(−)",
    ),
    "net-mTI": (
        MontageMode.NET,
        NET_MTI,
        "EEG10-10_UI_Jurak_2007.csv",
        ["AF3 → PO10", "AF4 → Oz", "F3 → P4", "F4 → P3"],
        "AF3(+)–PO10(−), AF4(+)–Oz(−), F3(+)–P4(−) and F4(+)–P3(−)",
    ),
    "flex_mapped-TI": (
        MontageMode.FLEX_MAPPED,
        MAPPED,
        "GSN-HydroCel-185.csv",
        ["E010 → E011", "E012 → E013"],
        "E010(+)–E011(−) and E012(+)–E013(−)",
    ),
    "flex_mapped-mTI": (
        MontageMode.FLEX_MAPPED,
        MAPPED_MTI,
        "GSN-HydroCel-185.csv",
        ["E010 → E011", "E012 → E013", "E020 → E021", "E030 → E031"],
        "E010(+)–E011(−), E012(+)–E013(−), E020(+)–E021(−) and E030(+)–E031(−)",
    ),
    "flex_free-TI": (
        MontageMode.FLEX_FREE,
        CHN,
        None,
        CHN_NAMES,
        _polar(CHN_NAMES),
    ),
    "flex_free-mTI": (
        MontageMode.FLEX_FREE,
        CHN_MTI,
        None,
        CHN_MTI_NAMES,
        _polar(CHN_MTI_NAMES),
    ),
    "freehand-TI": (
        MontageMode.FREEHAND,
        FREE,
        None,
        FREE_NAMES,
        _polar(FREE_NAMES),
    ),
    "freehand-mTI": (
        MontageMode.FREEHAND,
        FREE_MTI,
        None,
        FREE_MTI_NAMES,
        _polar(FREE_MTI_NAMES),
    ),
}


def summary_text(n: int) -> str:
    """A SimNIBS fields_summary.txt with *n* carriers ``X_TDCS_1`` .. ``X_TDCS_n``."""
    block = SUMMARY.split("\n\n\n")[0]
    return "\n\n\n".join(
        block.replace("X_TDCS_1", f"X_TDCS_{i}") for i in range(1, n + 1)
    )


def write_run(sim_root: Path, montage: Montage, **config_kw) -> Path:
    """A simulation folder as the simulator leaves it before its report: config.json from the real
    writer, a SimNIBS log and one field-summary block per carrier."""
    config_kw.setdefault("intensities", [1.0] * montage.num_pairs)
    cfg = SimulationConfig(subject_id="X", montages=[montage], **config_kw)
    d = sim_root / montage.name
    (d / "documentation").mkdir(parents=True)
    (d / "high_Frequency" / "analysis").mkdir(parents=True)
    create_simulation_config_file(
        cfg, montage, str(d / "documentation"), logging.getLogger("test")
    )
    (d / "documentation" / "simnibs_simulation_20261008-083216.log").write_text(
        LOG.format(a=0.001, b=0.001)
    )
    (d / "high_Frequency" / "analysis" / "fields_summary.txt").write_text(
        summary_text(montage.num_pairs)
    )
    return d


def visible_text(page: str) -> str:
    """What a reader sees, without the verbatim config.json listing, styles and scripts."""
    page = re.sub(r'<pre class="code">.*?</pre>', " ", page, flags=re.S)
    page = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", page, flags=re.S)
    return html_lib.unescape(re.sub(r"<[^>]+>", " ", page))


def carrier_rows(page: str) -> list[list[str]]:
    """Cells of the per-carrier table under Technical details."""
    table = (
        page.split("<summary>Carrier fields", 1)[1]
        .split("<tbody>", 1)[1]
        .split("</tbody>", 1)[0]
    )
    return [
        re.findall(r"<td[^>]*>(.*?)</td>", row)
        for row in re.findall(r"<tr>(.*?)</tr>", table)
    ]


def channel_rows(page: str) -> list[tuple[str, str]]:
    """``(Channel 1 (blue), "E1+ AF3 · E1- PO10, 1 mA")`` rows of the montage section's channel list."""
    montage = page.split('id="montage"', 1)[1].split('id="field"', 1)[0]
    return re.findall(r"<dt>(Channel \d+ \([a-z]+\))</dt><dd>(.*?)</dd>", montage)


def by_role(names: list[str]) -> list[str]:
    """``"AF3 → PO10"`` (plus electrode first) as the reports name channel k: ``"Ek+ AF3 · Ek- PO10"``."""
    return [
        "E{0}+ {1} · E{0}- {2}".format(k, *name.split(" → "))
        for k, name in enumerate(names, start=1)
    ]


@pytest.mark.parametrize("case", list(CASES))
def test_every_montage_mode_reports(tmp_path, case):
    mode, pairs, net, names, phrase = CASES[case]
    montage = Montage(name="M", mode=mode, electrode_pairs=pairs, eeg_net=net)
    rec = _with_envelope(sim.collect(write_run(tmp_path, montage)))
    with patch(CAP, return_value=FAKE):
        page = sim.build_html(rec, None, "X")

    _structure(page, SECTIONS, sim.SIZE_BUDGET, require_status=False)
    kind = (
        "Multichannel temporal interference"
        if len(pairs) == 4
        else "Temporal interference"
    )
    assert f"{kind} with {phrase} at 1 mA per channel ({len(pairs)} mA total)" in page
    # one channel row per pair, each naming its own electrodes and current
    assert [dt for dt, _ in channel_rows(page)][:2] == [
        "Channel 1 (blue)",
        "Channel 2 (red)",
    ]
    assert [dd for _, dd in channel_rows(page)] == [
        f"{n}, 1 mA" for n in by_role(names)
    ]
    # one carrier row per carrier, carrier i on pair i
    assert [(r[0], r[1]) for r in carrier_rows(page)] == [
        (f"X_TDCS_{i}", n) for i, n in enumerate(by_role(names), start=1)
    ]


@pytest.mark.parametrize(
    "case", ["flex_free-TI", "flex_free-mTI", "freehand-TI", "freehand-mTI"]
)
def test_xyz_montages_show_rounded_millimetres_not_raw_lists(tmp_path, case):
    mode, pairs, _, names, _ = CASES[case]
    montage = Montage(name="M", mode=mode, electrode_pairs=pairs)
    rec = _with_envelope(sim.collect(write_run(tmp_path, montage)))
    with patch(CAP, return_value=FAKE):
        page = sim.build_html(rec, None, "X")

    text = visible_text(page)
    assert "[[" not in text and "[7" not in text and "[-" not in text
    # a number with 4+ decimals that is not inside a DOI or a dotted name
    assert not re.findall(r"(?<![\w./:])-?\d+\.\d{4,}", text)
    assert "73.98" not in text and "-18.59" not in text
    assert "Montage on the EEG cap" not in page  # no cap: an XYZ montage has no net
    montage_sec = page.split('id="montage"', 1)[1].split('id="field"', 1)[0]
    assert (
        "<dt>EEG net</dt><dd>none: electrodes placed at subject-space coordinates (mm)</dd>"
        in montage_sec
    )
    # the config.json listing keeps the coordinates exactly as run
    assert json.dumps(pairs[0][0][0]) in page


def test_the_simulation_pipeline_writes_a_report_for_an_xyz_montage(tmp_path):
    """BaseSimulation._write_report with the real create_simulation_report on a project holding the
    sub-CHN flex-free config: one report file, no warning."""
    from tit.paths import get_path_manager
    from tit.sim.base import BaseSimulation

    project = tmp_path / "project"
    project.mkdir()
    pm = get_path_manager(str(project))
    montage = Montage(
        name="left_insula_mean", mode=MontageMode.FLEX_FREE, electrode_pairs=CHN
    )
    d = write_run(Path(pm.simulations("X")), montage)
    assert str(d) == pm.simulation("X", "left_insula_mean")
    nifti_dir = d / "TI" / "niftis"
    nifti_dir.mkdir(parents=True)
    grey = nifti_dir / "grey_left_insula_mean_TI_subject_TI_max.nii.gz"
    grey.touch()
    gm = np.zeros((4, 4, 4), np.float32)
    gm[1, 2, 3] = 0.7
    images = {grey.name: SimpleNamespace(dataobj=gm, affine=np.eye(4))}

    def load(path):
        # The m2m folder holds no T1: the figure is skipped, the report is not.
        try:
            return images[Path(path).name]
        except KeyError:
            raise FileNotFoundError(path) from None

    run = MagicMock()
    run.pm.project_dir, run.config.subject_id, run.montage.name = (
        str(project),
        "X",
        montage.name,
    )
    with patch("nibabel.load", side_effect=load):
        BaseSimulation._write_report(run)

    run.logger.warning.assert_not_called()
    reports = sorted(
        (project / "derivatives" / "ti-toolbox" / "reports" / "sub-X").glob(
            "simulation_report_*.html"
        )
    )
    assert len(reports) == 1
    page = reports[0].read_text()
    assert f"Temporal interference with {_polar(CHN_NAMES)}" in page
    assert "its hot spot (top 0.1 %) is at (1, 2, 3) mm, subject space." in page
