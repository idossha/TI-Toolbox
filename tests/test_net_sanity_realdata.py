"""Every EEG net on every Dataset 000 head is distinct and agrees with the 10-10 net, or the app refuses it.

What this pins (2026-10-22, package p07, task realdata-net-sanity), read-only over
``$TIT_DATASET_000/derivatives/SimNIBS/sub-*/m2m_*/eeg_positions/*.csv``:

* Labels are unique in every net.
* A net is *sound* when (1) no two electrodes (Electrode and ReferenceElectrode rows) are
  closer than 2 mm, except the 10-20 synonyms T3/T7, T4/T8, T5/P7, T6/P8 (Oostenveld &
  Praamstra 2001, Table 1, typed here), and (2) where a second reading of the same sites
  exists on that head, it agrees: a GSN-HydroCel-128/256 sensor and its 10-10 site in the
  subject's ``EEG10-10_UI_Jurak_2007`` through EGI's own table (``tests/data/
  egi_hydrocel_10-10.csv``; bounds median < 20 mm, max < 40 mm, the derivation is in
  ``tests/test_electrode_caps_mni.py``), and BioSemi-64-10-10 vs Jurak on shared labels
  (median < 20 mm).
* The app flags a net exactly when it is not sound: job preflight refuses a simulation on it
  with "Re-apply in EEG caps", and the scene's ``read_net`` (viewer) refuses it.

Both rules are computed here with numpy from the CSV text, independently of ``tit.caps``.
Measured 2026-10-22: sound nets sit 8-14 mm (median) from their 10-10 sites; sub-LA and
sub-CHN still hold GSN-HydroCel-128 and BioSemi-64/128/256 nets warped before 3.1.1 (29-110
collapsed pairs, 125-131 mm off). Those are pinned as flagged rather than skipped; once a
subject is re-applied, its nets become sound and the same rule still holds.

The skin-distance half needs the head mesh and SimNIBS: ``tests/numerical/
test_net_on_scalp_realdata.py``.

Reproduce::

    TIT_DATASET_000=/Users/idohaber/datasets/000 .venv/bin/python -m pytest tests/test_net_sanity_realdata.py -q
"""

from __future__ import annotations

import csv
import os
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

ROOT = os.environ.get("TIT_DATASET_000", "")
pytestmark = pytest.mark.skipif(
    not ROOT or not Path(ROOT).is_dir(),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)

EGI_TABLE = Path(__file__).parent / "data" / "egi_hydrocel_10-10.csv"
ALIASES = {
    frozenset(p) for p in (("T3", "T7"), ("T4", "T8"), ("T5", "P7"), ("T6", "P8"))
}
COLLAPSE_MM = 2.0
JURAK = "EEG10-10_UI_Jurak_2007.csv"


def _read(path: Path) -> tuple[list[str], np.ndarray]:
    with path.open(newline="") as handle:
        rows = [
            r
            for r in csv.reader(handle)
            if r and r[0] in ("Electrode", "ReferenceElectrode")
        ]
    return [r[4] for r in rows], np.array([[float(v) for v in r[1:4]] for r in rows])


def _collapsed(names: list[str], world: np.ndarray) -> list[tuple[str, str]]:
    d = np.linalg.norm(world[:, None, :] - world[None, :, :], axis=-1)
    i, j = np.nonzero(np.triu(d < COLLAPSE_MM, k=1))
    return [
        (names[a], names[b])
        for a, b in zip(i, j)
        if frozenset((names[a], names[b])) not in ALIASES
    ]


def _egi_offsets(net: str, gsn: dict, jurak: dict) -> list[float]:
    with EGI_TABLE.open() as handle:
        rows = [
            r
            for r in csv.DictReader(handle)
            if r["net"] == net and r["first_listing"] == "1"
        ]
    return [
        float(
            np.linalg.norm(
                gsn[f"E{int(r['egi_sensor']):03d}"] - jurak[r["ten_ten_label"]]
            )
        )
        for r in rows
        # Cz is EGI's reference sensor (129 / 257), which the caps do not carry.
        if r["egi_sensor"]
        and r["ten_ten_label"] in jurak
        and f"E{int(r['egi_sensor']):03d}" in gsn
    ]


def _problems(path: Path, jurak: dict | None) -> list[str]:
    """Why the net at *path* is not sound; empty when it is."""
    names, world = _read(path)
    out = []
    pairs = _collapsed(names, world)
    if pairs:
        out.append(f"{len(pairs)} pairs < {COLLAPSE_MM} mm (e.g. {pairs[0]})")
    if jurak is None:
        return out
    pos = dict(zip(names, world))
    offsets: list[float] = []
    bounds = (20.0, 40.0)
    if path.name in ("GSN-HydroCel-128.csv", "GSN-HydroCel-256.csv"):
        offsets = _egi_offsets(
            path.name.split("-")[-1].removesuffix(".csv"), pos, jurak
        )
        assert len(offsets) >= 60, (path, len(offsets))
    elif path.name == "BioSemi-64-10-10.csv":
        offsets = [float(np.linalg.norm(pos[k] - jurak[k])) for k in pos if k in jurak]
        assert len(offsets) >= 50, (path, len(offsets))
        bounds = (20.0, np.inf)
    if offsets and (np.median(offsets) >= bounds[0] or max(offsets) >= bounds[1]):
        out.append(
            f"10-10 offset median {np.median(offsets):.0f} mm, max {max(offsets):.0f} mm"
        )
    return out


def _nets() -> dict[Path, list[Path]]:
    base = Path(ROOT) / "derivatives" / "SimNIBS"
    found = {}
    for positions in sorted(base.glob("sub-*/m2m_*/eeg_positions")):
        nets = [p for p in sorted(positions.glob("*.csv")) if _read(p)[0]]
        if nets:
            found[positions] = nets
    return found


def _mtimes(paths) -> dict:
    return {p: p.stat().st_mtime_ns for p in paths}


def test_every_net_labels_each_electrode_once() -> None:
    nets = [p for group in _nets().values() for p in group]
    assert len(nets) >= 20, f"has nets to check: {len(nets)}"
    dupes = {
        str(p): sorted(k for k, v in Counter(_read(p)[0]).items() if v > 1)
        for p in nets
    }
    assert {k: v for k, v in dupes.items() if v} == {}


def test_the_app_refuses_a_net_exactly_when_it_is_not_sound() -> None:
    from tit.jobs.preflight import preflight
    from tit.paths import get_path_manager
    from tit.scene import build

    groups = _nets()
    files = [p for group in groups.values() for p in group]
    before = _mtimes(files)
    pm = get_path_manager(ROOT)
    verdicts: dict[str, tuple[list[str], bool, bool]] = {}
    for positions, nets in groups.items():
        sid = positions.parent.name.removeprefix("m2m_")
        jurak_path = positions / JURAK
        jurak = None
        if jurak_path.is_file() and not _problems(jurak_path, None):
            jurak = dict(zip(*_read(jurak_path)))
        for path in nets:
            names, _ = _read(path)
            montage = {
                "name": "probe",
                "mode": "net",
                "eeg_net": path.name,
                "electrode_pairs": [[names[0], names[-1]]],
            }
            found = preflight("sim", {"subject_id": sid, "montages": [montage]}, ROOT)
            refused = any("Re-apply in EEG caps" in f.how_to_fix for f in found)
            try:
                build.read_net(pm, sid, path.name)
                viewer_refused = False
            except build.SceneUnavailable as exc:
                viewer_refused = "Re-apply in EEG caps" in str(exc)
            verdicts[f"sub-{sid}/{path.name}"] = (
                _problems(path, jurak),
                refused,
                viewer_refused,
            )
    assert _mtimes(files) == before, "the dataset was written"

    sound = [k for k, (problems, _, _) in verdicts.items() if not problems]
    assert len(sound) >= 10, f"has sound nets to compare against: {sound}"
    wrong = {
        k: v for k, v in verdicts.items() if bool(v[0]) != v[1] or bool(v[0]) != v[2]
    }
    assert wrong == {}, "net -> (problems, preflight refused, viewer refused)"
