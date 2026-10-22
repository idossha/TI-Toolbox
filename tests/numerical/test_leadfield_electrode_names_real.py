"""A leadfield holds exactly its net's electrodes: the preflight rule and the runner rule agree.

What this pins (2026-10-22, package c1_4, task runner-fail-fast), in the image with real
h5py and SimNIBS, on every Dataset 000 leadfield (``derivatives/SimNIBS/sub-*/leadfields/
*.hdf5``), opened read-only and never loaded:

* The names in the ``tdcs_leadfield`` dataset's ``electrode_names`` attribute, as the
  runner reads them (``tit.opt.ex.ex.leadfield_electrode_names``), are distinct and are
  exactly the ``Electrode`` rows plus the ``ReferenceElectrode`` row of the leadfield's net
  CSV (``eeg_positions/<net>.csv``) as SimNIBS's own CSV reader
  (``simnibs.utils.csv_reader.read_csv_positions``) reads it, and the attribute
  ``reference_electrode`` is that reference row. So the CSV rule job preflight applies
  (``tit.jobs.preflight._leadfield_labels``) and the HDF5 rule the runner applies are the
  same rule; that set is also compared directly.
* Why the reference belongs in it: SimNIBS's ``TI_utils.get_field`` takes the reference as
  the zero-potential pole (``load_leadfield`` maps it to index ``None``), and an unknown label
  is a bare ``KeyError`` -- shown on a zero leadfield of the file's own shape with the index
  ``load_leadfield`` builds from these names.
* ``refuse_electrodes_off_leadfield`` on the real file refuses an off-net label naming the net and
  accepts every label of the net, the reference included (an off-net label: ``X_ON_NO_NET``).
* The files read keep their mtimes (read-only).

The checks run in a subprocess: ``tests/conftest.py`` replaces h5py and SimNIBS with mocks
in this interpreter.

Reproduce in the image::

    simnibs_python -m pytest tests/numerical/test_leadfield_electrode_names_real.py -q
    # with -v /Users/idohaber/datasets/000:/data/000:ro -e TIT_DATASET_000=/data/000
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATASET = os.environ.get("TIT_DATASET_000", "")


def _leadfields() -> list[Path]:
    base = Path(DATASET) / "derivatives" / "SimNIBS"
    return sorted(base.glob("sub-*/leadfields/*.hdf5")) if DATASET else []


pytestmark = pytest.mark.skipif(
    not DATASET or not Path(DATASET).is_dir() or not _leadfields(),
    reason=(
        "skipping: TIT_DATASET_000 is unset or has no derivatives/SimNIBS/sub-*/leadfields/"
        "*.hdf5 (export TIT_DATASET_000=/path/to/Dataset000, read-only)"
    ),
)

_SCRIPT = r"""
import json, sys
from pathlib import Path
try:
    import h5py
    import numpy as np
    from simnibs.utils import TI_utils as TI
    from simnibs.utils.csv_reader import read_csv_positions
except ImportError as exc:
    print(json.dumps({"skip": f"real h5py/SimNIBS not importable here: {exc}"}))
    sys.exit(0)
from tit.jobs.preflight import _leadfield_labels
from tit.opt.ex.ex import leadfield_electrode_names, refuse_electrodes_off_leadfield
from tit.opt.ex.symmetry import net_name_from_leadfield

OFF_NET = "X_ON_NO_NET"  # no SimNIBS or TI-Toolbox net has this label
out = []
for path in sys.argv[1:]:
    path = Path(path)
    sid = path.parent.parent.name.removeprefix("sub-")
    net = net_name_from_leadfield(path)
    csv_path = path.parent.parent / f"m2m_{sid}" / "eeg_positions" / f"{net}.csv"
    types, _, _, labels, _, _ = read_csv_positions(str(csv_path))
    names = leadfield_electrode_names(str(path))
    with h5py.File(path, "r") as handle:
        lf = handle["mesh_leadfield"]["leadfields"]["tdcs_leadfield"]
        reference = lf.attrs["reference_electrode"]
        reference = reference.decode() if isinstance(reference, bytes) else str(reference)
        n_rows = int(lf.shape[0])
    # load_leadfield's index, from the same names: the reference maps to None.
    idx = {n: i for i, n in enumerate([n for n in names if n != reference])}
    idx[reference] = None
    zero = np.zeros((n_rows, 1, 3))
    other = next(n for n in names if n != reference)
    try:
        TI.get_field([OFF_NET, other, 1.0], zero, idx)
        unknown_error = None
    except Exception as exc:
        unknown_error = f"{type(exc).__name__}: {exc}"
    ref_field = TI.get_field([reference, other, 1.0], zero, idx)
    try:
        refuse_electrodes_off_leadfield("ex-search", [OFF_NET, reference], str(path))
        refusal = None
    except ValueError as exc:
        refusal = str(exc)
    try:
        refuse_electrodes_off_leadfield("ex-search", list(names), str(path))
        all_accepted = True
    except ValueError:
        all_accepted = False
    out.append({
        "leadfield": str(path),
        "net": net,
        "csv": str(csv_path),
        "names": names,
        "reference_attr": reference,
        "n_rows": n_rows,
        "csv_electrodes": [l for t, l in zip(types, labels) if t == "Electrode"],
        "csv_references": [l for t, l in zip(types, labels) if t == "ReferenceElectrode"],
        "preflight_labels": sorted(_leadfield_labels(csv_path)),
        "unknown_error": unknown_error,
        "reference_field_shape": list(ref_field.shape),
        "refusal": refusal,
        "all_accepted": all_accepted,
    })
print(json.dumps({"leadfields": out}))
"""


def _mtimes(paths: list[Path]) -> dict[str, int]:
    return {str(p): p.stat().st_mtime_ns for p in paths}


@pytest.fixture(scope="module")
def checked() -> dict:
    leadfields = _leadfields()
    nets = sorted(
        Path(DATASET).glob("derivatives/SimNIBS/sub-*/m2m_*/eeg_positions/*.csv")
    )
    before = _mtimes(leadfields + nets)
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT, *map(str, leadfields)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr[-4000:]
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    if "skip" in result:
        pytest.skip(f"skipping: {result['skip']}")
    assert _mtimes(leadfields + nets) == before, "a Dataset 000 file was modified"
    assert len(result["leadfields"]) == len(leadfields) >= 1
    return result


def test_leadfield_names_are_the_net_electrodes_plus_its_reference(checked) -> None:
    for lf in checked["leadfields"]:
        names = lf["names"]
        assert len(names) == len(set(names)), lf["leadfield"]
        assert len(lf["csv_references"]) == 1, lf["csv"]
        assert set(names) == set(lf["csv_electrodes"]) | set(lf["csv_references"])
        assert lf["reference_attr"] == lf["csv_references"][0]
        # The field rows exclude the reference (SimNIBS: N_elec - 1 rows).
        assert lf["n_rows"] == len(names) - 1


def test_preflight_csv_rule_equals_the_leadfield_names(checked) -> None:
    for lf in checked["leadfields"]:
        assert lf["preflight_labels"] == sorted(lf["names"]), lf["leadfield"]


def test_simnibs_takes_the_reference_and_fails_an_unknown_label_late(checked) -> None:
    for lf in checked["leadfields"]:
        assert lf["reference_field_shape"] == [1, 3]
        # What a run died of before the runner check: a bare KeyError, after the load.
        assert lf["unknown_error"] == "KeyError: 'X_ON_NO_NET'", lf["unknown_error"]


def test_runner_check_refuses_off_net_labels_on_the_real_file(checked) -> None:
    for lf in checked["leadfields"]:
        assert lf["refusal"] is not None
        assert lf["refusal"].startswith(
            f"ex-search electrodes not in the leadfield of {lf['net']}: X_ON_NO_NET."
        ), lf["refusal"]
        assert lf["all_accepted"] is True
