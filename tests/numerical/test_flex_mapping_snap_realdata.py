"""Every real flex run of Dataset 000, mapped onto every net of its subject, with real SciPy.

What this pins (package p24, audit_flex.md "mapping snap is unbounded and invisible",
2026-10-22): ``resolve_flex_montage(..., "mapped")`` on the real optimised positions and the
real nets gives four distinct labels, pairs that follow the optimiser's
``channel_array_indices``, ``distances`` that are the Euclidean distance from each optimised
position to its net site, a total that is the true minimum, and a catalog ``max_snap_mm``
equal to the largest of those distances -- the number the Simulator warns on.

Expected values, all independent of the code under test:

- net sites are read here with the ``csv`` module from the subject's own net CSV
  (``Electrode,x,y,z,label`` rows, the SimNIBS format), and optimised positions from the
  run's ``electrode_positions.json``;
- distances are recomputed with ``numpy.linalg.norm``;
- the minimum total is found by brute force over each electrode's four nearest sites. That
  set always holds an optimum: if electrode *i* sat on a site outside its four nearest, one
  of those four is free (only three other electrodes), and moving *i* there costs no more.

Nets SimNIBS cannot map onto (``Fiducials.csv``: no ``Electrode`` rows) must be refused by
name. The dataset is read only: runs and nets are copied into ``tmp_path`` and the mtimes of
every file read are compared before and after.

Run (container, real SciPy)::

    docker run --rm --platform linux/amd64 --entrypoint bash -v $PWD:/ti-toolbox -w /ti-toolbox \
      -v /Users/idohaber/datasets/000:/data/000:ro -e TIT_DATASET_000=/data/000 \
      idossha/ti-toolbox:v3.1.1 -lc \
      'simnibs_python -m pytest tests/numerical/test_flex_mapping_snap_realdata.py -q -s'

Measured on 2026-10-22 (printed with ``-s``, not pinned): the largest snaps are tens of mm
on sparse or mis-registered nets, which is why the Simulator warns above 20 mm.
"""

from __future__ import annotations

import csv
import importlib
import itertools
import json
import math
import os
import shutil
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.host_numerical

DATASET = os.environ.get("TIT_DATASET_000", "")
HAVE_DATASET = bool(DATASET) and os.path.isdir(
    os.path.join(DATASET, "derivatives", "SimNIBS")
)


def _runs(root: Path) -> list[tuple[str, str, Path]]:
    """``(subject, run, electrode_positions.json)`` for every flex run that has positions."""
    out = []
    for positions in sorted(
        (root / "derivatives" / "SimNIBS").glob(
            "sub-*/flex-search/*/electrode_positions.json"
        )
    ):
        run_dir = positions.parent
        sid = run_dir.parent.parent.name.removeprefix("sub-")
        out.append((sid, run_dir.name, positions))
    return out


def _net_sites(path: Path) -> dict[str, list[float]] | None:
    """``label -> [x, y, z]`` of the ``Electrode`` rows, or ``None`` when a label repeats."""
    sites: dict[str, list[float]] = {}
    with open(path, newline="") as handle:
        for row in csv.reader(handle):
            if len(row) >= 5 and row[0].strip() == "Electrode":
                label = row[4].strip()
                if label in sites:
                    return None
                sites[label] = [float(v) for v in row[1:4]]
    return sites


def _brute_force_minimum(optimized: np.ndarray, sites: np.ndarray) -> float:
    """Smallest total distance over distinct sites, searching each electrode's 4 nearest."""
    dist = np.linalg.norm(optimized[:, None, :] - sites[None, :, :], axis=2)
    nearest = [np.argsort(row, kind="stable")[: len(optimized)] for row in dist]
    best = math.inf
    for choice in itertools.product(*nearest):
        if len(set(choice)) == len(choice):
            best = min(best, sum(dist[i, j] for i, j in enumerate(choice)))
    return best


def _mtimes(paths) -> dict[str, int]:
    return {str(p): os.stat(p).st_mtime_ns for p in paths}


@pytest.mark.skipif(
    not HAVE_DATASET,
    reason="skipping: TIT_DATASET_000 is unset or not a Dataset 000 copy",
)
def test_every_real_run_maps_onto_every_net_optimally_with_its_snap(tmp_path):
    from tit import catalog
    from tit.paths import get_path_manager
    from tit.sim import montage_sources
    from tit.tools import map_electrodes

    # Bind the real scipy.optimize.linear_sum_assignment (the host suite mocks scipy).
    importlib.reload(map_electrodes)

    root = Path(DATASET)
    runs = _runs(root)
    assert runs, "Dataset 000 has no flex run with electrode_positions.json"
    nets_by_sid = {
        sid: sorted(
            (
                root
                / "derivatives"
                / "SimNIBS"
                / f"sub-{sid}"
                / f"m2m_{sid}"
                / "eeg_positions"
            ).glob("*.csv")
        )
        for sid in {sid for sid, _, _ in runs}
    }
    read = [p for _, _, p in runs] + [p for nets in nets_by_sid.values() for p in nets]
    before = _mtimes(read)

    (tmp_path / "dataset_description.json").write_text("{}")
    pm = get_path_manager(str(tmp_path))
    for sid, run, positions in runs:
        run_dir = Path(pm.flex_search_run(sid, run))
        run_dir.mkdir(parents=True)
        shutil.copy2(positions, run_dir / "electrode_positions.json")
        caps = Path(pm.eeg_positions(sid))
        caps.mkdir(parents=True, exist_ok=True)
        for net in nets_by_sid[sid]:
            shutil.copy2(net, caps / net.name)

    checked = refused = 0
    snaps: list[tuple[str, str, str, float]] = []
    for sid, run, positions in runs:
        source = json.loads(positions.read_text())
        optimized = np.asarray(source["optimized_positions"], dtype=float)
        indices = [tuple(i) for i in source["channel_array_indices"]]
        for net in nets_by_sid[sid]:
            sites = _net_sites(net)
            usable = (
                sites is not None
                and len(sites) >= len(optimized)
                and all(np.isfinite(v).all() for v in sites.values())
            )
            if not usable:
                with pytest.raises(ValueError, match=net.name):
                    montage_sources.resolve_flex_montage(
                        pm, sid, run, "mapped", eeg_net=net.name
                    )
                refused += 1
                continue

            montage = montage_sources.resolve_flex_montage(
                pm, sid, run, "mapped", eeg_net=net.name
            )
            mapping_file = Path(pm.flex_search_run(sid, run)) / (
                f"electrode_mapping_{net.stem}.json"
            )
            data = json.loads(mapping_file.read_text())
            labels = data["mapped_labels"]
            where = f"sub-{sid} {run} -> {net.name}"
            assert len(labels) == len(optimized) == len(set(labels)), where

            # Each mapped electrode is the run's own optimised electrode, in order.
            np.testing.assert_allclose(
                data["optimized_positions"], optimized, atol=1e-9
            )
            assert [tuple(i) for i in data["channel_array_indices"]] == indices, where

            recomputed = [
                float(np.linalg.norm(o - np.asarray(sites[label])))
                for o, label in zip(optimized, labels)
            ]
            assert all(math.isfinite(d) for d in data["distances"]), where
            assert data["distances"] == pytest.approx(recomputed, abs=1e-6), where

            # Pairs follow the channels: channel c is [array 0, array 1].
            by_index = dict(zip(indices, labels))
            channels = sorted({c for c, _ in indices})
            expected_pairs = [[by_index[(c, 0)], by_index[(c, 1)]] for c in channels]
            assert [list(p) for p in montage.electrode_pairs] == expected_pairs, where

            site_xyz = np.asarray(list(sites.values()), dtype=float)
            assert sum(recomputed) == pytest.approx(
                _brute_force_minimum(optimized, site_xyz), rel=1e-9, abs=1e-9
            ), where

            listed = catalog.read_flex_mapping(str(mapping_file))
            assert listed is not None, where
            assert listed["max_snap_mm"] == pytest.approx(max(recomputed), abs=1e-6)
            snaps.append((sid, run, net.name, max(recomputed)))
            checked += 1

    assert checked >= len(runs), (checked, refused)
    assert _mtimes(read) == before, "the test changed a file in Dataset 000"
    for sid, run, net, snap in sorted(snaps, key=lambda s: -s[3])[:10]:
        print(f"max snap {snap:6.1f} mm  sub-{sid} {run} -> {net}")
