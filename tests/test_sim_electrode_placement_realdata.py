"""SimNIBS placed every electrode of every Dataset 000 simulation where its config asked, with the current it asked.

Pins (2026-10-22, package p25). For each ``derivatives/SimNIBS/sub-*/Simulations/*`` with a
``documentation/config.json``, the requested electrode centres are read from what the montage names
-- the subject's ``m2m_<id>/eeg_positions/<eeg_net>`` row for a cap label, the coordinate itself
for a flex-free / free-hand (XYZ) montage -- and compared with what SimNIBS itself wrote:
``high_Frequency/mesh/<id>_TDCS_<k>_el_currents.geo``, whose ``electrode_currents`` view holds one
``ST`` triangle per electrode surface element carrying that electrode's current in amperes
(``+I`` on the pair's first electrode, ``-I`` on its second; the ``scalp`` view after it carries 0
on about 66k triangles and is not read). Asserted per pair k:

* exactly two current values ``+I`` and ``-I``, with ``I * 1000`` equal to ``intensities[k]`` (mA):
  the current that ran is the one the config records;
* each electrode has at least 10 triangles and its centroid lies ``gel - 2`` to ``gel + 4`` mm from
  its requested centre (measured 3.8-4.1 mm on all 6 simulations with 4 mm gel: the surface sits
  on the gel, above the skin point). A cap read in the wrong frame or a flex position in another
  space moves an electrode by centimetres;
* the toolbox's own record (``electrode_coordinates``) is the requested centre, in pair order;
* the two electrodes of a pair are distinct and every two requested centres are > 5 mm apart.

A synthetic ``.geo`` with one electrode moved 40 mm (built in ``tmp_path``) is seen failing first,
so the check is not vacuous. Where the numbers come from: SimNIBS's ``.geo`` output and the cap
CSVs charm wrote, read here with ``re`` and ``csv``; nothing from ``tit`` is called.

Real-data, gated: ``export TIT_DATASET_000=/Users/idohaber/datasets/000`` (read-only; an mtime
listing of every file read is compared before and after). Skips with the reason when unset. Host
only: text, JSON and CSV.
``TIT_DATASET_000=... .venv/bin/python -m pytest tests/test_sim_electrode_placement_realdata.py -q``
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
from pathlib import Path

import pytest

ROOT = os.environ.get("TIT_DATASET_000", "")
_HAVE = bool(ROOT) and Path(ROOT, "derivatives", "SimNIBS").is_dir()
_REASON = (
    "skipping: TIT_DATASET_000 is unset or has no derivatives/SimNIBS "
    "(export TIT_DATASET_000=/path/to/Dataset000, read-only)"
)

#: The electrode surface SimNIBS reports sits on the gel layer; its centroid is about one gel
#: thickness from the requested skin point (3.8-4.1 mm with 4 mm gel on Dataset 000).
BELOW_GEL_MM = 2.0
ABOVE_GEL_MM = 4.0
#: An 8 mm electrode is meshed with 25-39 surface triangles on Dataset 000.
MIN_TRIANGLES = 10
#: Two requested electrodes closer than this would overlap any electrode the app offers.
MIN_SEPARATION_MM = 5.0

_ST = re.compile(r"ST\(([^)]*)\)\{([^}]*)\}")


def electrode_triangles(geo_text: str) -> dict[float, list[list[float]]]:
    """``{current (A): [triangle centroid, ...]}`` from the ``electrode_currents`` view only."""
    out: dict[float, list[list[float]]] = {}
    in_view = False
    for line in geo_text.splitlines():
        if line.startswith('View"electrode_currents"'):
            in_view = True
            continue
        if in_view and (line.startswith("};") or line.startswith("View")):
            break
        match = _ST.match(line) if in_view else None
        if match:
            xyz = [float(v) for v in match.group(1).split(",")]
            value = float(match.group(2).split(",")[0])
            centroid = [(xyz[i] + xyz[i + 3] + xyz[i + 6]) / 3 for i in range(3)]
            out.setdefault(value, []).append(centroid)
    return out


def _mean(points: list[list[float]]) -> list[float]:
    return [sum(p[i] for p in points) / len(points) for i in range(3)]


def placement_violations(
    geo_text: str, requested: list[list[float]], current_mA: float, gel_mm: float
) -> list[str]:
    """What is wrong with one pair's placement; empty when SimNIBS put it where asked."""
    tris = electrode_triangles(geo_text)
    plus = [v for v in tris if v > 0]
    minus = [v for v in tris if v < 0]
    if len(plus) != 1 or len(minus) != 1:
        return [f"expected one +I and one -I electrode, got currents {sorted(tris)}"]
    problems = []
    for value in plus + minus:
        if not math.isclose(abs(value) * 1000, current_mA, rel_tol=1e-9):
            problems.append(f"current {value} A, config says {current_mA} mA")
    for value, centre in zip((plus[0], minus[0]), requested):
        points = tris[value]
        if len(points) < MIN_TRIANGLES:
            problems.append(f"{value} A electrode has only {len(points)} triangles")
        offset = math.dist(_mean(points), centre)
        if not gel_mm - BELOW_GEL_MM <= offset <= gel_mm + ABOVE_GEL_MM:
            problems.append(
                f"{value} A electrode centroid is {offset:.1f} mm from its requested "
                f"centre {centre} (gel {gel_mm} mm)"
            )
    return problems


def _cap_rows(csv_path: Path) -> dict[str, list[float]]:
    with csv_path.open(newline="") as stream:
        return {
            row[4].strip(): [float(v) for v in row[1:4]]
            for row in csv.reader(stream)
            if len(row) >= 5 and row[0].strip() == "Electrode"
        }


def _requested(sim: Path, config: dict) -> list[list[list[float]]]:
    """Per pair, the two requested centres (subject mm), from what the montage names."""
    pairs = config["electrode_pairs"]
    if all(isinstance(e, list) for pair in pairs for e in pair):
        return [[[float(v) for v in e] for e in pair] for pair in pairs]
    sid = sim.parent.parent.name.removeprefix("sub-")
    net = sim.parent.parent / f"m2m_{sid}" / "eeg_positions" / config["eeg_net"]
    rows = _cap_rows(net)
    return [[rows[label] for label in pair] for pair in pairs]


def _simulations() -> list[Path]:
    return sorted(
        p.parent.parent
        for p in Path(ROOT, "derivatives", "SimNIBS").glob(
            "sub-*/Simulations/*/documentation/config.json"
        )
    )


def _mtimes(paths) -> dict[str, int]:
    return {str(p): p.stat().st_mtime_ns for p in paths}


# ── synthetic: the check fails on a moved electrode ──────────────────────


def _synthetic_geo(centres: list[list[float]], current_A: float, gel: float) -> str:
    """Two discs of 16 triangles, ``gel`` mm outward of each centre, carrying ``+I`` and ``-I``,
    followed by a zero-current scalp view (as SimNIBS writes it)."""
    lines = ['View"electrode_currents"{']
    for centre, value in zip(centres, (current_A, -current_A)):
        norm = math.sqrt(sum(v * v for v in centre))
        n = [v / norm for v in centre]
        u = [-n[1], n[0], 0.0] if abs(n[2]) < 0.9 else [0.0, -n[2], n[1]]
        un = math.sqrt(sum(v * v for v in u))
        u = [v / un for v in u]
        w = [
            n[1] * u[2] - n[2] * u[1],
            n[2] * u[0] - n[0] * u[2],
            n[0] * u[1] - n[1] * u[0],
        ]
        mid = [c + gel * k for c, k in zip(centre, n)]
        ring = [
            [m + 4 * (math.cos(t) * a + math.sin(t) * b) for m, a, b in zip(mid, u, w)]
            for t in (2 * math.pi * i / 16 for i in range(16))
        ]
        for i in range(16):
            tri = mid + ring[i] + ring[(i + 1) % 16]
            lines.append(
                "ST("
                + ",".join(f"{v!r}" for v in tri)
                + "){"
                + ",".join([repr(value)] * 3)
                + "};"
            )
    lines += ["};", 'View"scalp"{', "ST(0,0,0,1,0,0,0,1,0){0.0,0.0,0.0};", "};"]
    return "\n".join(lines) + "\n"


def test_a_pair_placed_where_asked_passes_and_a_moved_electrode_fails():
    centres = [[-30.0, 100.0, 40.0], [50.0, -65.0, -30.0]]
    good = _synthetic_geo(centres, 0.001, gel=4.0)
    assert placement_violations(good, centres, 1.0, 4.0) == []

    moved = _synthetic_geo([[-30.0, 100.0, 80.0], centres[1]], 0.001, gel=4.0)
    problems = placement_violations(moved, centres, 1.0, 4.0)
    assert len(problems) == 1, problems
    offset = re.search(r"^0\.001 A electrode centroid is ([\d.]+) mm", problems[0])
    assert offset and 36 <= float(offset.group(1)) <= 44, problems

    swapped = _synthetic_geo(centres[::-1], 0.001, gel=4.0)
    assert len(placement_violations(swapped, centres, 1.0, 4.0)) == 2

    assert placement_violations(good, centres, 1.5, 4.0) == [
        "current 0.001 A, config says 1.5 mA",
        "current -0.001 A, config says 1.5 mA",
    ]
    assert (
        "one +I and one -I"
        in placement_violations(good.replace("-0.001", "0.001"), centres, 1.0, 4.0)[0]
    )


# ── real data ────────────────────────────────────────────────────────────


@pytest.mark.skipif(not _HAVE, reason=_REASON)
def test_every_dataset_simulation_placed_each_electrode_where_its_config_asked():
    sims = _simulations()
    assert sims, "has no simulations to check"
    read = [
        *[sim / "documentation" / "config.json" for sim in sims],
        *[p for sim in sims for p in sim.glob("high_Frequency/mesh/*_el_currents.geo")],
        *[
            p
            for sim in sims
            for p in sim.parent.parent.glob("m2m_*/eeg_positions/*.csv")
        ],
    ]
    before = _mtimes(read)
    checked = 0
    problems = []
    for sim in sims:
        config_path = sim / "documentation" / "config.json"
        config = json.loads(config_path.read_text())
        sid = sim.parent.parent.name.removeprefix("sub-")
        requested = _requested(sim, config)
        gel = float(config["electrode_geometry"]["gel_thickness"])
        currents = [float(v) for v in config["intensities"]]

        recorded = config["electrode_coordinates"]
        flat = [c for pair in requested for c in pair]
        assert len(recorded) == len(flat), sim
        for got, want in zip(recorded, flat):
            assert math.dist(got, want) <= 1e-6, (sim, got, want)

        for pair in requested:
            assert math.dist(*pair) > MIN_SEPARATION_MM, (sim, pair)
        for i, a in enumerate(flat):
            for b in flat[i + 1 :]:
                assert math.dist(a, b) > MIN_SEPARATION_MM, (sim, a, b)

        for k, pair in enumerate(requested, start=1):
            geo = sim / "high_Frequency" / "mesh" / f"{sid}_TDCS_{k}_el_currents.geo"
            assert geo in read, geo
            for problem in placement_violations(
                geo.read_text(), pair, currents[k - 1], gel
            ):
                problems.append(f"{sim.relative_to(ROOT)} pair {k}: {problem}")
            checked += 1
    assert checked >= 2 * len(sims), "has no electrode pairs to check"
    assert problems == []
    assert _mtimes(read) == before, "a test wrote into the read-only dataset"
