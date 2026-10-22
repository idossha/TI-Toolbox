"""The 2-D cap templates draw every electrode of the nets they stand for, and the ex-search
electrode maps never drop the winning montage.

What this pins (2026-10-22, package p13, task template-label-coverage):

``resources/amv/10-10.csv`` and ``resources/amv/GSN-256.csv`` give pixel positions on
``GSN-256.png`` for the nets the montage image, the report cap figure and the ex-search maps
draw. 10-10.csv lacked AFz (Jurak, Cutini, Neuroelectrics) and GSN-256.csv lacked E256, so a
simulation on those electrodes got no montage image, and ``plot_montage_score_map`` silently
skipped every montage that used one: Dataset 000 ``sub-101/ex-search/20260919_160209`` has AFz in
384 of its 480 rows (all of the top five) and its strength map read "Top 96" without AFz.

Where the expected values come from (never from ``tit``):

* net labels: SimNIBS's own caps as packaged for the guide head
  (``tit/scene/guide/nets/<net>.csv.json``) and the shipped MNI caps
  (``resources/ElectrodeCaps_MNI``, Electrode + ReferenceElectrode rows);
* AFz: EGI's 10-10 table (``tests/data/egi_hydrocel_10-10.csv``, first listing for the 256 net:
  sensor 20), so AFz is the pixel of GSN E020; the image itself labels that circle "20 AFz";
* E256: the MNI GSN-HydroCel-256 cap, in which E256 is the mirror of E229 (3.5 mm from
  (-x, y, z)); every MNI mirror pair must mirror on the template about its midline, the x of
  the 10-10 template's Fpz/Cz/Oz;
* Iz, I1 and I2 lie below the template image's drawn sensors (EGI's table has no inion row), so
  a montage that uses them must be drawn on the net's own x/y layout instead.

The ranking tests use hand-written records whose winner is known by construction.

Real-data leg (read-only, skips without it):
``TIT_DATASET_000=/path/to/000 .venv/bin/python -m pytest tests/test_template_label_coverage.py``.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import re
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
AMV = REPO / "resources" / "amv"
GUIDE_NETS = REPO / "tit" / "scene" / "guide" / "nets"
MNI_CAPS = REPO / "resources" / "ElectrodeCaps_MNI"
EGI_TABLE = Path(__file__).parent / "data" / "egi_hydrocel_10-10.csv"

# Below the template's drawn sensors: no GSN-256 circle stands for them (EGI's table has no
# inion row), so a montage on them is drawn on the net's own x/y layout.
OFF_IMAGE = {"Iz", "I1", "I2"}


def _template(name: str) -> dict[str, tuple[int, int]]:
    with (AMV / name).open(newline="") as f:
        return {
            r["electrode_name"]: (int(r["x"]), int(r["y"])) for r in csv.DictReader(f)
        }


def _guide_labels(net: str) -> set[str] | None:
    path = GUIDE_NETS / f"{net}.csv.json"
    if not path.is_file():
        return None
    return {e["name"] for e in json.loads(path.read_text())["electrodes"]}


def _mni_cap(net: str) -> dict[str, np.ndarray] | None:
    path = MNI_CAPS / f"{net}.csv"
    if not path.is_file():
        return None
    with path.open(newline="") as f:
        return {
            r[4]: np.array(r[1:4], float)
            for r in csv.reader(f)
            if r and r[0] in ("Electrode", "ReferenceElectrode")
        }


def _maps() -> dict[str, dict[str, str]]:
    from tit.opt.ex import buckets
    from tit.plotting import ti_metrics
    from tit.tools import montage_visualizer

    return {
        "montage_visualizer": montage_visualizer._COORD_FILES,
        "ti_metrics": ti_metrics._TEMPLATE_COORD_FILES,
        "buckets": buckets._CANONICAL_TEMPLATE_COORD_FILES,
    }


def _stem(key: str) -> str:
    return key.removesuffix(".csv")


def _net_cases() -> list[tuple[str, str, str]]:
    """(map, net stem, template file) for every net a map sends to a template."""
    cases = []
    for map_name, mapping in _maps().items():
        for key, template in mapping.items():
            stem = _stem(key)
            if _guide_labels(stem) is not None or _mni_cap(stem) is not None:
                cases.append((map_name, stem, template))
    return sorted(set(cases))


CASES = _net_cases()


def test_has_nets_to_check():
    stems = {stem for _, stem, _ in CASES}
    assert {
        "GSN-HydroCel-185",
        "GSN-HydroCel-256",
        "EEG10-10_UI_Jurak_2007",
        "EEG10-10_Cutini_2011",
        "EEG10-10_Neuroelectrics",
        "EEG10-20_Okamoto_2004",
    } <= stems


@pytest.mark.parametrize("map_name,net,template", CASES, ids=lambda v: str(v))
def test_template_draws_every_label_of_its_net(map_name, net, template):
    labels = set()
    for source in (_guide_labels(net), _mni_cap(net)):
        labels |= set(source or ())
    assert len(labels) >= 18, net
    missing = labels - set(_template(template))
    assert (
        missing <= OFF_IMAGE
    ), f"{map_name}: {net} -> {template} lacks {sorted(missing)}"


def test_afz_is_egi_sensor_20_of_the_256_net():
    with EGI_TABLE.open() as f:
        (row,) = [
            r
            for r in csv.DictReader(f)
            if r["net"] == "256"
            and r["ten_ten_label"] == "AFz"
            and r["first_listing"] == "1"
        ]
    sensor = f"E{int(row['egi_sensor']):03d}"
    assert sensor == "E020"
    assert _template("10-10.csv")["AFz"] == _template("GSN-256.csv")[sensor]


def test_every_ten_ten_site_sits_on_its_egi_sensor():
    """The whole 10-10 template against EGI's table: each site within 10 px (a sensor circle
    is ~25 px in radius; the template was clicked independently of GSN-256.csv)."""
    gsn = _template("GSN-256.csv")
    with EGI_TABLE.open() as f:
        sensor = {
            r["ten_ten_label"]: f"E{int(r['egi_sensor']):03d}"
            for r in csv.DictReader(f)
            if r["net"] == "256" and r["first_listing"] == "1" and r["egi_sensor"]
        }
    ten_ten = _template("10-10.csv")
    checked = {
        label: math.dist(xy, gsn[sensor[label]])
        for label, xy in ten_ten.items()
        if label in sensor
    }
    assert len(checked) >= 65 and "AFz" in checked
    assert max(checked.values()) <= 10, max(checked.items(), key=lambda kv: kv[1])


def test_gsn_template_mirrors_the_mni_cap_about_its_midline():
    """Every left/right pair of the MNI GSN-HydroCel-256 cap mirrors on the template about the
    template's midline; E256 (the mirror of E229) included."""
    ten_ten = _template("10-10.csv")
    midline = float(np.median([ten_ten[k][0] for k in ("Fpz", "Cz", "Oz")]))
    gsn = _template("GSN-256.csv")
    cap = _mni_cap("GSN-HydroCel-256")
    labels = sorted(cap)
    pairs = set()
    for label in labels:
        if abs(cap[label][0]) <= 15:
            continue
        image = cap[label] * (-1, 1, 1)
        partner = min(labels, key=lambda other: np.linalg.norm(cap[other] - image))
        if np.linalg.norm(cap[partner] - image) < 5:
            pairs.add(tuple(sorted((label, partner))))
    assert ("E229", "E256") in pairs and len(pairs) >= 100
    errors = {
        (a, b): math.dist((2 * midline - gsn[a][0], gsn[a][1]), gsn[b])
        for a, b in pairs
    }
    assert max(errors.values()) <= 10, max(errors.items(), key=lambda kv: kv[1])


# ── The three net -> template maps ────────────────────────────────────────────────────


def test_net_template_maps_agree_on_every_shared_net():
    by_stem: dict[str, dict[str, str]] = {}
    for map_name, mapping in _maps().items():
        for key, template in mapping.items():
            by_stem.setdefault(_stem(key), {})[f"{map_name}:{key}"] = template
    shared = {stem: files for stem, files in by_stem.items() if len(files) > 1}
    assert "GSN-HydroCel-185" in shared
    for stem, files in shared.items():
        assert len(set(files.values())) == 1, (stem, files)


def test_supported_nets_ignore_the_csv_suffix():
    from tit.tools.montage_visualizer import is_supported_net

    stems = {_stem(key) for mapping in _maps().values() for key in mapping}
    for stem in stems | {"EEG10-10_UI_Jurak_2007", "GSN-HydroCel-256"}:
        assert is_supported_net(stem) == is_supported_net(f"{stem}.csv"), stem
    assert is_supported_net("EEG10-10_Cutini_2011")
    assert is_supported_net("GSN-HydroCel-256")


def test_gsn_128_never_borrows_the_256_template():
    """EGI numbers the 128 net's sensors differently (E036 is C3 on the 128, F3 is E036 on
    the 256 per tests/data/egi_hydrocel_10-10.csv)."""
    with EGI_TABLE.open() as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if r["first_listing"] == "1" and r["egi_sensor"]
        ]
    c3 = {r["net"]: r["egi_sensor"] for r in rows if r["ten_ten_label"] == "C3"}
    assert c3["128"] != c3["256"]
    for map_name, mapping in _maps().items():
        assert "GSN-HydroCel-128" not in {_stem(key) for key in mapping}, map_name


# ── Ex-search maps: the winner is always drawn ────────────────────────────────────────


@pytest.fixture
def axes(monkeypatch):
    """One fresh mock Axes per ``plt.subplots`` call (matplotlib is a host mock)."""
    import sys

    import matplotlib.pyplot as plt

    for name in ("matplotlib.image", "matplotlib.patches", "matplotlib.path"):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, MagicMock())
    made: list[MagicMock] = []

    def subplots(*args, **kwargs):
        made.append(MagicMock())
        return MagicMock(), made[-1]

    monkeypatch.setattr(plt, "subplots", subplots)
    return made


def _write_net(path: Path, labels: dict[str, tuple[float, float, float]]) -> str:
    path.write_text(
        "".join(f"Electrode,{x},{y},{z},{name}\n" for name, (x, y, z) in labels.items())
    )
    return str(path)


# A Jurak-named subject net in RAS mm: Iz is on the net but not on the template image.
JURAK_LIKE = {
    "Fz": (0.0, 60.0, 70.0),
    "F3": (-45.0, 55.0, 60.0),
    "F4": (45.0, 55.0, 60.0),
    "C3": (-60.0, -8.0, 70.0),
    "C4": (60.0, -8.0, 70.0),
    "Oz": (0.0, -100.0, 10.0),
    "Iz": (0.0, -105.0, -20.0),
    "AFz": (0.0, 75.0, 40.0),
}


def _title(ax) -> str:
    (call,) = ax.set_title.call_args_list
    return call.args[0]


def _highlighted(ax) -> list[str]:
    return [call.args[2] for call in ax.text.call_args_list]


def test_winner_off_the_template_is_drawn_on_the_net_layout(tmp_path, axes):
    from tit.plotting.ti_metrics import plot_montage_score_map

    net = _write_net(tmp_path / "EEG10-10_UI_Jurak_2007.csv", JURAK_LIKE)
    records = [
        {"electrodes": ["Iz", "Fz", "C3", "C4"], "composite": 0.9},
        {"electrodes": ["F3", "F4", "C3", "C4"], "composite": 0.4},
        {"electrodes": ["Fz", "Oz", "F3", "C4"], "composite": 0.2},
    ]
    out = str(tmp_path / "map.png")
    assert (
        plot_montage_score_map(
            eeg_positions_csv=net, montage_scores=records, output_file=out
        )
        == out
    )
    (ax,) = axes
    assert _highlighted(ax) == ["Iz", "Fz", "C3", "C4"]
    assert _title(ax).startswith("Top 3 ")
    ax.imshow.assert_not_called()  # the template image cannot show Iz
    # Labels sit at the net's own RAS x/y, offset 2 mm (the template's offset is 18 px).
    iz_text = ax.text.call_args_list[0]
    assert iz_text.args[:2] == (JURAK_LIKE["Iz"][0] + 2.0, JURAK_LIKE["Iz"][1] - 2.0)


def test_afz_winner_is_drawn_on_the_template(tmp_path, axes):
    """The audit's repro: a Cutini net whose best montage uses AFz. It read "Top 1" and ringed
    the Fz montage as best."""
    from tit.plotting.ti_metrics import plot_montage_score_map

    labels = {k: v for k, v in JURAK_LIKE.items() if k != "Iz"}
    net = _write_net(tmp_path / "EEG10-10_Cutini_2011.csv", labels)
    records = [
        {"electrodes": ["AFz", "C3", "F3", "F4"], "composite": 1.0},
        {"electrodes": ["Fz", "C3", "F3", "F4"], "composite": 0.5},
    ]
    plot_montage_score_map(
        eeg_positions_csv=net,
        montage_scores=records,
        output_file=str(tmp_path / "m.png"),
    )
    (ax,) = axes
    assert _highlighted(ax) == ["AFz", "C3", "F3", "F4"]
    assert _title(ax).startswith("Top 2 ")
    ax.imshow.assert_called_once()
    afz_text = ax.text.call_args_list[0]
    pixel = _template("10-10.csv")["AFz"]
    assert afz_text.args[0] == pytest.approx(
        pixel[0] + 18
    )  # label offset on the template
    assert afz_text.args[1] == pytest.approx(pixel[1] - 18)


def test_heatmap_counts_a_winner_off_the_template(tmp_path, axes):
    from tit.plotting.ti_metrics import plot_electrode_score_heatmap

    net = _write_net(tmp_path / "EEG10-10_UI_Jurak_2007.csv", JURAK_LIKE)
    records = [
        {"electrodes": ["Iz", "Fz", "C3", "C4"], "composite": 0.9},
        {"electrodes": ["F3", "F4", "C3", "C4"], "composite": 0.4},
    ]
    plot_electrode_score_heatmap(
        eeg_positions_csv=net,
        montage_scores=records,
        output_file=str(tmp_path / "h.png"),
    )
    (ax,) = axes
    scatter = [c for c in ax.scatter.call_args_list if "c" in c.kwargs][0]
    sums = dict(zip(zip(scatter.args[0], scatter.args[1]), scatter.kwargs["c"]))
    assert sums[JURAK_LIKE["Iz"][:2]] == pytest.approx(0.9)
    assert sums[JURAK_LIKE["C3"][:2]] == pytest.approx(0.9 + 0.4)
    assert "Top 2 Montages" in _title(ax)


def test_montages_no_layout_can_draw_are_counted_in_a_warning(tmp_path, axes):
    from tit.plotting.ti_metrics import plot_montage_score_map

    net = _write_net(tmp_path / "EEG10-10_UI_Jurak_2007.csv", JURAK_LIKE)
    records = [
        {"electrodes": ["Fz", "NOPE", "C3", "C4"], "composite": 0.9},
        {"electrodes": ["F3", "F4", "C3", "C4"], "composite": 0.4},
    ]
    # The "tit" logger does not propagate once setup_logging ran, so listen on the module's own.
    seen: list[logging.LogRecord] = []
    handler = logging.Handler(logging.WARNING)
    handler.emit = seen.append
    module_logger = logging.getLogger("tit.plotting.ti_metrics")
    module_logger.addHandler(handler)
    try:
        plot_montage_score_map(
            eeg_positions_csv=net,
            montage_scores=records,
            output_file=str(tmp_path / "m.png"),
        )
    finally:
        module_logger.removeHandler(handler)
    (ax,) = axes
    assert _highlighted(ax) == ["F3", "F4", "C3", "C4"]
    warned = [r.getMessage() for r in seen if r.levelno >= logging.WARNING]
    assert len(warned) == 1 and re.search(r"\b1 of 2 montages\b", warned[0]), warned


# ── Dataset 000 (read-only) ──────────────────────────────────────────────────────────

_DATASET = Path(os.environ.get("TIT_DATASET_000", "/nonexistent"))
_RUN = (
    _DATASET / "derivatives" / "SimNIBS" / "sub-101" / "ex-search" / "20260919_160209"
)
_NET = (
    _DATASET
    / "derivatives"
    / "SimNIBS"
    / "sub-101"
    / "m2m_101"
    / "eeg_positions"
    / "EEG10-10_UI_Jurak_2007.csv"
)


@pytest.mark.skipif(
    not (_RUN / "final_output.csv").is_file() or not _NET.is_file(),
    reason="skipping: TIT_DATASET_000 unset or lacks sub-101/ex-search/20260919_160209",
)
def test_sub101_afz_run_maps_its_best_montage(tmp_path, axes):
    from tit.opt.ex.results import MONTAGE_MAP_TOP_N, regenerate_plots

    read = [_RUN / "final_output.csv", _RUN / "run_config.json", _NET]
    before = {p: p.stat().st_mtime_ns for p in read}
    run = tmp_path / "run"
    run.mkdir()
    shutil.copy(_RUN / "final_output.csv", run / "final_output.csv")

    # Independent reading of the CSV: row count, AFz share, the best rows by each metric.
    with (run / "final_output.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 480
    assert sum("AFz" in r["Montage"] for r in rows) == 384

    def electrodes(row) -> frozenset[str]:
        # "AF7_AFz <> CP6_P10_I1-1.6mA_I2-0.4mA": two pairs, then the channel currents.
        core = re.sub(r"_I1-.*$", "", row["Montage"])
        return frozenset(
            label for pair in core.split(" <> ") for label in pair.split("_")
        )

    def best_montage(column: str) -> frozenset[str]:
        top = max(float(r[column]) for r in rows)
        # This run predates one-row-per-physical-montage: ties are one montage, reordered.
        (labels,) = {electrodes(r) for r in rows if float(r[column]) == top}
        return labels

    best_strength = best_montage("TImean_ROI")
    assert "AFz" in best_strength and len(best_strength) == 4

    regenerate_plots(run, eeg_csv=_NET)
    heatmap, strength, focality = axes
    n = min(MONTAGE_MAP_TOP_N, len(rows))
    assert _title(strength) == (
        f"Top {n} Ex-Search Montages by ROI Strength (EEG10-10_UI_Jurak_2007.csv)"
    )
    assert _title(focality).startswith(f"Top {n} Ex-Search Montages by Focality")
    assert set(_highlighted(strength)) == best_strength
    assert set(_highlighted(focality)) == best_montage("Focality")
    # Every figure draws on the template now that it has AFz.
    for ax in axes:
        ax.imshow.assert_called_once()
    assert {p: p.stat().st_mtime_ns for p in read} == before
