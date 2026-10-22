"""SimNIBS's own cap reader is the oracle for the EEG caps upload validator (p14, 2026-10-22).

What this pins, in the image with the real SimNIBS 4.6:

* ``tit.caps.validate_mni_cap`` accepts a cap only if
  ``simnibs.utils.csv_reader.read_csv_positions`` -- the reader ``warp_coordinates``
  runs on the stored file -- reads the stored text (``tit.caps.normalise_mni_cap``,
  what ``/api/caps/upload`` writes) with exactly the electrodes the file's author
  wrote: the same names in the same order at the same coordinates, as many as the
  validator counted, each one a key of ``_get_eeg_positions`` (the dict a simulation
  resolves labels from).
* Every case the validator refuses or rewrites because of SimNIBS is one SimNIBS
  misreads as uploaded: it raises, drops or renames an electrode, or keys two rows
  under one name.
* Every cap SimNIBS ships (``resources/ElectrodeCaps_MNI``, TI-Toolbox's six caps
  included in the image) passes the validator with SimNIBS's electrode count, except
  ``Fiducials.csv``, which has no electrode and is not a cap.

Where the numbers come from: each corpus case's ``intended`` rows are authored -- what
the person writing the file meant -- and the verdicts are the validator's documented
rules; the SimNIBS side is read by SimNIBS in a subprocess (``tests/conftest.py`` mocks
SimNIBS in this interpreter). The host half (route, normalisation, messages) is
``tests/test_caps.py``.

Reproduce in the image::

    simnibs_python -m pytest tests/numerical/test_caps_validator_vs_simnibs.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

from tit import caps

FZ, CZ, FP = (
    ("Fz", (10.0, 0.0, 80.0)),
    ("Cz", (-10.0, 0.0, 80.0)),
    ("Fp", (0.0, 20.0, 80.0)),
)
CANON = "Electrode,10,0,80,Fz\nElectrode,-10,0,80,Cz\nElectrode,0,20,80,Fp\n"


class Case(NamedTuple):
    text: str
    #: The electrodes the author wrote (Electrode / ReferenceElectrode rows), in order.
    intended: tuple
    accept: bool
    #: Whether SimNIBS misreads the file exactly as uploaded (the reason the
    #: validator refuses or rewrites it). ``None``: not a SimNIBS concern.
    raw_misread: bool | None


CASES = {
    "canonical": Case(CANON, (FZ, CZ, FP), True, False),
    "lowercase-type": Case(
        CANON.replace("Electrode", "electrode"), (FZ, CZ, FP), False, True
    ),
    "leading-space-type": Case(
        CANON.replace("Electrode", " Electrode"), (FZ, CZ, FP), False, True
    ),
    "trailing-blank-line": Case(CANON + "\n", (FZ, CZ, FP), True, True),
    "blank-middle-row": Case(CANON.replace("Fz\n", "Fz\n\n"), (FZ, CZ, FP), True, True),
    "utf8-bom": Case("\ufeff" + CANON, (FZ, CZ, FP), True, True),
    "duplicate-name": Case(
        CANON.replace(",Fp", ",Fz"), (FZ, CZ, ("Fz", FP[1])), False, True
    ),
    "padded-name": Case(CANON.replace(",Cz", ", Cz"), (FZ, CZ, FP), False, True),
    "second-position-no-name": Case(
        "Electrode,10,0,80,1,2,3\n", (("1", FZ[1]),), False, True
    ),
    "crlf": Case(CANON.replace("\n", "\r\n"), (FZ, CZ, FP), True, False),
    "cr-only": Case(CANON.replace("\n", "\r"), (FZ, CZ, FP), True, False),
    "extra-columns": Case(
        CANON.replace("Fz\n", "Fz,frontal,x\n"), (FZ, CZ, FP), True, False
    ),
    "second-position": Case(
        "Electrode,10,0,80,11,0,80,Fz\nElectrode,-10,0,80,-11,0,80,Cz\n",
        (FZ, CZ),
        True,
        False,
    ),
    "quoted-name-with-comma": Case(
        'Electrode,10,0,80,"F,z"\nElectrode,-10,0,80,Cz\n',
        (("F,z", FZ[1]), CZ),
        True,
        False,
    ),
    "unicode-name": Case(
        "Electrode,10,0,80,Fzü\nElectrode,-10,0,80,Cz\n",
        (("Fzü", FZ[1]), CZ),
        True,
        False,
    ),
    "reference-and-fiducial": Case(
        CANON + "ReferenceElectrode,0,-10,95,Ref\nFiducial,0,90,-20,Nz\n",
        (FZ, CZ, FP, ("Ref", (0.0, -10.0, 95.0))),
        True,
        False,
    ),
    # SimNIBS skips a header row itself; the validator refuses it anyway (conservative).
    "header-row": Case("Type,X,Y,Z,Name\n" + CANON, (FZ, CZ, FP), False, None),
    "label-xyz": Case("Label,X,Y,Z\nFz,10,0,80\nCz,-10,0,80\n", (FZ, CZ), False, None),
}

_ELECTRODE = ("Electrode", "ReferenceElectrode")

_SCRIPT = r"""
import json, os, sys, warnings
warnings.simplefilter("ignore")
try:
    import simnibs
    from simnibs.utils import csv_reader
except Exception as exc:
    print(json.dumps({"unavailable": repr(exc)}))
    sys.exit(0)

def read(path):
    try:
        types, coords, _, names, _, _ = csv_reader.read_csv_positions(path)
        keys = csv_reader._get_eeg_positions(path)
    except Exception as exc:
        return {"error": type(exc).__name__}
    return {"types": types, "names": names, "coords": coords.tolist(), "keys": sorted(map(str, keys))}

shipped = os.path.join(os.path.dirname(simnibs.__file__), "resources", "ElectrodeCaps_MNI")
caps = {n: read(os.path.join(shipped, n)) for n in sorted(os.listdir(shipped)) if n.endswith(".csv")}
print(json.dumps({"files": {p: read(p) for p in sys.argv[1:]}, "shipped": shipped, "caps": caps}))
"""


@pytest.fixture(scope="module")
def simnibs_reads(tmp_path_factory):
    """SimNIBS's reading of every corpus case, raw and as stored, and of its shipped caps."""
    root = tmp_path_factory.mktemp("caps-corpus")
    paths = []
    for name, case in CASES.items():
        raw = root / f"{name}.raw.csv"
        raw.write_bytes(case.text.encode("utf-8"))
        paths.append(str(raw))
        if _verdict(case.text) is not None:  # what the upload route would store
            stored = root / f"{name}.stored.csv"
            stored.write_bytes(caps.normalise_mni_cap(case.text).encode("utf-8"))
            paths.append(str(stored))
    done = subprocess.run(
        [sys.executable, "-c", _SCRIPT, *paths],
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    out = json.loads(done.stdout.strip().splitlines()[-1])
    if "unavailable" in out:
        print(f"skipping: real SimNIBS is unavailable ({out['unavailable']})")
        pytest.skip("real SimNIBS is unavailable; run in the toolbox container")
    return root, out


def _electrodes(read: dict) -> list[tuple[str, tuple[float, ...]]]:
    return [
        (name, tuple(xyz))
        for kind, name, xyz in zip(read["types"], read["names"], read["coords"])
        if kind in _ELECTRODE
    ]


def _verdict(text: str) -> int | None:
    try:
        return caps.validate_mni_cap(text)
    except caps.CapError:
        return None


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_validator_accepts_exactly_the_documented_cases(name: str) -> None:
    case = CASES[name]
    assert (_verdict(case.text) is not None) is case.accept


@pytest.mark.parametrize("name", sorted(CASES))
def test_simnibs_reads_every_cap_the_validator_accepts_as_its_author_wrote_it(
    simnibs_reads, name: str
) -> None:
    root, out = simnibs_reads
    case = CASES[name]
    count = _verdict(case.text)
    stored = out["files"].get(str(root / f"{name}.stored.csv"))
    assert (stored is not None) is (count is not None)
    if count is None:
        return  # refused: nothing reaches SimNIBS
    assert "error" not in stored, stored
    intended = [(n, tuple(map(float, xyz))) for n, xyz in case.intended]
    assert _electrodes(stored) == intended
    assert count == len(intended)
    assert {n for n, _ in intended} <= set(stored["keys"])


@pytest.mark.parametrize("name", sorted(n for n, c in CASES.items() if c.raw_misread))
def test_simnibs_misreads_what_the_validator_refuses_or_rewrites(
    simnibs_reads, name: str
) -> None:
    root, out = simnibs_reads
    case = CASES[name]
    read = out["files"][str(root / f"{name}.raw.csv")]
    if "error" in read:
        return  # SimNIBS raises on the file as uploaded
    got = _electrodes(read)
    intended = [(n, tuple(map(float, xyz))) for n, xyz in case.intended]
    names = [n for n, _ in got]
    assert got != intended or len(set(names)) < len(names), read


@pytest.mark.parametrize(
    "name", sorted(n for n, c in CASES.items() if c.raw_misread is False)
)
def test_simnibs_reads_a_clean_case_as_uploaded(simnibs_reads, name: str) -> None:
    """The corpus' negative control: the misread check above can tell a clean file."""
    root, out = simnibs_reads
    case = CASES[name]
    read = out["files"][str(root / f"{name}.raw.csv")]
    assert "error" not in read, read
    assert _electrodes(read) == [(n, tuple(map(float, x))) for n, x in case.intended]


def test_every_cap_simnibs_ships_passes_the_validator(simnibs_reads) -> None:
    _, out = simnibs_reads
    shipped = Path(out["shipped"])
    assert out["caps"], "has shipped caps to check"
    names = set(out["caps"])
    assert caps.TIT_CAPS <= names, "the image carries TI-Toolbox's caps"
    for name, read in out["caps"].items():
        assert "error" not in read, (name, read)
        count = len(_electrodes(read))
        text = (shipped / name).read_text(encoding="utf-8")
        if count == 0:
            assert name == "Fiducials.csv"
            assert _verdict(text) is None
            assert not caps.has_electrodes(shipped / name)
        else:
            assert _verdict(text) == count, name
            assert caps.has_electrodes(shipped / name)
