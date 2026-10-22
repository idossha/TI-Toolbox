"""Every EEG-net CSV reader in TI-Toolbox returns the same electrodes for the same file.

What this pins (2026-10-22, package p07, task net-csv-reader-contract):

Seven host-runnable functions read ``m2m_<id>/eeg_positions/<net>.csv``: the catalog's net
pickers, job preflight, the simulation's coordinate resolution, the electrode overlay, the
ex-search bucket reader, the scene's parser (viewer) and the flex mapper. The agreed rule:
``Electrode,x,y,z,label`` rows are the stimulation electrodes; ``ReferenceElectrode`` (Cz)
and ``Fiducial`` rows are not; a row with fewer than five cells (a blank line) is skipped.
Each reader must return exactly the fixture's Electrode labels, with its coordinates.

The fixtures are hand-written below in charm's format (``\\r\\n`` line ends, as the files
SimNIBS writes end): a numeric label like easycap's ``46``, a label with a space, a
reference and three fiducials; the same rows with blank lines; a fiducial-only file (every
subject's ``Fiducials.csv``); and a ``Label,X,Y,Z`` table, which is not a net. The expected
labels and coordinates are the fixture text, nothing else.

``tit.opt.ex.buckets._read_eeg_positions`` also reads the 2-D template tables in
``resources/amv`` (``electrode_name,x,y``), so it reads a ``Label,X,Y,Z`` file as such a
table; every other reader finds no electrodes in it. That difference is pinned here on
purpose: no picker lists such a file as a net (it has no Electrode rows).

Real-data leg: with ``TIT_DATASET_000`` set, every ``eeg_positions/*.csv`` of every Dataset
000 subject goes through every reader, and each must return as many electrodes as the file
has lines starting ``Electrode,`` with identical labels and coordinates. SimNIBS's own reader
and the flex skin picture (real scipy) are compared in
``tests/numerical/test_net_csv_readers_real.py``.

Reproduce::

    .venv/bin/python -m pytest tests/test_net_csv_readers.py -q
    TIT_DATASET_000=/Users/idohaber/datasets/000 .venv/bin/python -m pytest tests/test_net_csv_readers.py -q
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import pytest

from tit.catalog import _read_cap_electrode_labels
from tit.jobs.preflight import _eeg_labels
from tit.opt.ex.buckets import _read_eeg_positions
from tit.scene.build import parse_electrode_csv
from tit.sim.utils import _load_eeg_position_csv
from tit.tools.electrode_overlay import _load_eeg_positions
from tit.tools.map_electrodes import read_csv_positions

ELECTRODES = {
    "Fp1": (-26.5, 113.1, 19.3),
    "46": (40.25, -20.0, 85.5),
    "Left Mastoid": (-70.0, -30.0, -40.0),
    "E001": (72.3, 72.9, 1.8),
}
CHARM = (
    "".join(
        f"Electrode,{x},{y},{z},{name}\r\n" for name, (x, y, z) in ELECTRODES.items()
    )
    + "ReferenceElectrode,2.79,27.3,97.4,Cz\r\n"
    + "Fiducial,2.4,113.8,-11.9,Nz\r\n"
    + "Fiducial,-80.5,-15.0,-50.0,LPA\r\n"
    + "Fiducial,80.5,-15.0,-50.0,RPA\r\n"
)
BLANK_LINES = CHARM.replace("Electrode,40.25", "\r\nElectrode,40.25") + "\r\n\r\n"
FIDUCIALS_ONLY = "Fiducial,2.4,113.8,-11.9,Nz\r\nFiducial,-80.5,-15.0,-50.0,LPA\r\n"
LABEL_XYZ = "Label,X,Y,Z\nFz,0.0,60.0,70.0\nCz,0.0,0.0,95.0\n"

#: reader name -> function(path) -> {label: (x, y, z) or None when it reads no coordinates}
Reader = Callable[[Path], dict]


def _labels_only(labels) -> dict:
    return {label: None for label in labels}


def _xyz(mapping: dict) -> dict:
    return {k: tuple(float(v) for v in xyz) for k, xyz in mapping.items()}


READERS: dict[str, Reader] = {
    "catalog": lambda p: _labels_only(_read_cap_electrode_labels(str(p))),
    "preflight": lambda p: _labels_only(_eeg_labels(p)),
    "sim.utils": lambda p: _xyz(_load_eeg_position_csv(str(p))),
    "electrode_overlay": lambda p: _xyz(_load_eeg_positions(p.parent, p.name)),
    "ex.buckets": lambda p: _xyz(_read_eeg_positions(p)),
    "scene": lambda p: {
        e["name"]: tuple(e["world"])
        for e in parse_electrode_csv(p.read_text())["electrodes"]
    },
    "map_electrodes": lambda p: (
        lambda pos_labels: {
            label: tuple(float(v) for v in xyz)
            for xyz, label in zip(pos_labels[0], pos_labels[1])
        }
    )(read_csv_positions(str(p))),
}


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode())
    return path


def _assert_reads(reader: Reader, path: Path, expected: dict) -> None:
    got = reader(path)
    assert set(got) == set(expected)
    for label, xyz in got.items():
        if xyz is not None:
            assert xyz == pytest.approx(expected[label], abs=1e-9), label


@pytest.mark.parametrize("reader", READERS, ids=list(READERS))
@pytest.mark.parametrize(
    "text", [CHARM, BLANK_LINES], ids=["charm-format", "with-blank-lines"]
)
def test_every_reader_returns_the_electrode_rows(
    tmp_path: Path, reader: str, text: str
) -> None:
    _assert_reads(READERS[reader], _write(tmp_path, "net.csv", text), ELECTRODES)


@pytest.mark.parametrize("reader", READERS, ids=list(READERS))
def test_a_fiducial_file_has_no_electrodes_in_any_reader(
    tmp_path: Path, reader: str
) -> None:
    _assert_reads(
        READERS[reader], _write(tmp_path, "Fiducials.csv", FIDUCIALS_ONLY), {}
    )


@pytest.mark.parametrize("reader", sorted(set(READERS) - {"ex.buckets"}))
def test_a_label_xyz_table_is_not_a_net(tmp_path: Path, reader: str) -> None:
    _assert_reads(READERS[reader], _write(tmp_path, "table.csv", LABEL_XYZ), {})


def test_the_bucket_reader_reads_a_label_table_as_a_template(tmp_path: Path) -> None:
    got = READERS["ex.buckets"](_write(tmp_path, "table.csv", LABEL_XYZ))
    assert got == {"Fz": (0.0, 60.0, 70.0), "Cz": (0.0, 0.0, 95.0)}


# ── Dataset 000 (read-only) ──────────────────────────────────────────────────

_ROOT = os.environ.get("TIT_DATASET_000", "")


def _dataset_nets() -> list[Path]:
    base = Path(_ROOT) / "derivatives" / "SimNIBS"
    return sorted(base.glob("sub-*/m2m_*/eeg_positions/*.csv"))


@pytest.mark.skipif(
    not _ROOT or not Path(_ROOT).is_dir(),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)
def test_every_dataset_net_reads_the_same_in_every_reader() -> None:
    nets = _dataset_nets()
    assert nets, f"has nets to check under {_ROOT}"
    before = {p: p.stat().st_mtime_ns for p in nets}
    for path in nets:
        lines = path.read_text().splitlines()
        # Independent count: lines charm wrote as Electrode rows.
        n_rows = sum(line.startswith("Electrode,") for line in lines)
        results = {name: reader(path) for name, reader in READERS.items()}
        first = results["sim.utils"]
        assert len(first) == n_rows, (path, len(first), n_rows)
        for name, got in results.items():
            assert set(got) == set(first), (path, name)
            for label, xyz in got.items():
                if xyz is not None:
                    assert xyz == pytest.approx(first[label], abs=1e-9), (
                        path,
                        name,
                        label,
                    )
    assert {p: p.stat().st_mtime_ns for p in nets} == before, "the dataset was written"
