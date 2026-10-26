"""A cancelled ex/mEx search never leaves a run that looks complete.

Pins (2026-10-22): the job runner cancels by SIGTERM-ing the job's process tree, and its contract
(``tit/jobs/runner.py``, PETSc note) is that "the default disposition ends the process immediately
(exit 143, no output)"; the real-container spec ``real/ex.spec.ts`` says "a cancelled ex search writes
no completed run directory". The search used to trap SIGTERM, finish the montage in hand and then
write ``run_config.json`` + ``final_output.csv`` for the montages it had reached, report and exit 0,
so ``tit.catalog.ex_runs`` (which lists any run folder holding ``run_config.json``) showed a few-row
"best" as a finished run.

Each case runs the real ``python -m tit.opt.<ex|mex>`` entry point in a child interpreter (the
signal must end a process, so it cannot be this one) on a five-element fake leadfield. The fake
``simnibs.utils.TI_utils.get_field`` SIGTERMs the runner's main process on its first call for the
second candidate: in-process for ``n_jobs=1``, and from a forked worker to its parent for
``n_jobs=2``. Expected: the child dies of SIGTERM (``returncode == -SIGTERM``) and the run folder
holds neither ``run_config.json`` nor ``final_output.csv``. A control run of the same child with no
signal exits 0 and writes both, with ``n_combinations`` equal to the CSV's row count, so a child
that merely crashed cannot pass the cancel cases.

Reproduce: ``.venv/bin/python -m pytest tests/test_ex_cancel.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import csv
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="skipping: POSIX signals and fork only"
)

# The child: stand-ins for the libraries the host venv lacks (SimNIBS above all), a fake
# TI_utils whose leadfield is five elements, and the real runner's main().
_CHILD = r"""
import importlib.util
import os
import signal
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

kind, calls_path, trigger, config_path = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
MAIN_PID = os.getpid()

missing = {
    r for r in ("matplotlib", "pandas", "h5py") if importlib.util.find_spec(r) is None
} | {"simnibs"}
for name in ("simnibs", "simnibs.utils", "matplotlib", "matplotlib.pyplot", "pandas", "h5py"):
    if name.split(".")[0] in missing:
        sys.modules.setdefault(name, MagicMock())

centres = np.array(
    [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [20.0, 0.0, 0.0], [0.0, 20.0, 0.0]]
)
mesh = SimpleNamespace(
    elements_baricenters=lambda: SimpleNamespace(value=centres),
    elements_volumes_and_areas=lambda: SimpleNamespace(value=np.ones(len(centres))),
    elm=SimpleNamespace(tag1=np.array([2, 2, 2, 2, 1])),
)


def get_field(channel, leadfield, idx):
    # One line per call, appended by whichever process makes it (O_APPEND keeps lines whole).
    with open(calls_path, "a") as f:
        f.write(f"{os.getpid()}\n")
    with open(calls_path) as f:
        n = sum(1 for _ in f)
    if trigger and n >= trigger:
        try:  # exactly one process sends it, however the forked workers interleave
            os.close(os.open(calls_path + ".sent", os.O_CREAT | os.O_EXCL))
        except FileExistsError:
            pass
        else:
            os.kill(MAIN_PID, signal.SIGTERM)
    seed = sum(map(ord, channel[0] + channel[1]))
    return np.full((len(centres), 3), float(seed % 7 + 1)) * channel[2]


ti = types.ModuleType("simnibs.utils.TI_utils")
ti.load_leadfield = lambda path: (np.zeros(1), mesh, None)
ti.get_field = get_field
ti.get_maxTI = lambda e1, e2: np.linalg.norm(e1, axis=1) + np.linalg.norm(e2, axis=1)
sys.modules["simnibs.utils"].TI_utils = ti
sys.modules["simnibs.utils.TI_utils"] = ti

# The summary PNGs need a real matplotlib, which the host venv lacks; they are not under test.
import tit.plotting.ti_metrics as ti_metrics

ti_metrics.plot_montage_distributions = lambda **kw: kw["output_file"]
ti_metrics.plot_intensity_vs_focality = lambda **kw: kw["output_file"]

if kind == "mex":
    import tit.opt.mex.engine as mex_engine

    mex_engine.envelope_max = lambda fields: np.linalg.norm(sum(fields), axis=1)
    from tit.opt.mex.__main__ import main
else:
    from tit.opt.ex.__main__ import main

sys.argv = ["runner", config_path]
main()
"""


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    rois = project / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001" / "ROIs"
    rois.mkdir(parents=True)
    (rois / "target.csv").write_text(
        "0,0,0\n"
    )  # element 0's barycentre: a non-empty ROI
    return project


def _config(project: Path, kind: str, n_jobs: int) -> dict:
    letters = ["A", "B", "C", "D", "E", "F", "G", "H"]
    return {
        "project_dir": str(project),
        "subject_id": "001",
        "leadfield_hdf": "001_leadfield_TESTNET.hdf5",
        "roi_name": "target.csv",
        "run_name": "cancel_me",
        "n_jobs": n_jobs,
        "electrodes": {
            "_type": "PoolElectrodes",
            "electrodes": letters[:6] if kind == "ex" else letters,
        },
        **({"current_mA": 1.0} if kind == "mex" else {"total_current": 2.0}),
    }


def _run(tmp_path: Path, kind: str, n_jobs: int, trigger: int):
    project = _project(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(_config(project, kind, n_jobs)))
    calls = tmp_path / "calls.txt"
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "TIT_NO_TELEMETRY": "1",
        "TIT_JOB_CPUS": str(n_jobs),
        "HOME": str(tmp_path),  # no real ~/.config/ti-toolbox settings
    }
    env.pop("TIT_EVENTS_FILE", None)
    env.pop("TIT_JOB_ID", None)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            _CHILD,
            kind,
            str(calls),
            str(trigger),
            str(config_path),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    folder = "ex-search" if kind == "ex" else "m-ex-search"
    run_dir = project / "derivatives" / "SimNIBS" / "sub-001" / folder / "cancel_me"
    n_calls = len(calls.read_text().splitlines()) if calls.exists() else 0
    return proc, run_dir, n_calls


# get_field calls per candidate: two channels for ex, four pairs for mEx. The trigger is the
# first call of the second candidate, so the first candidate has been fully evaluated.
_FIRST_CALL_OF_SECOND = {"ex": 3, "mex": 5}


@pytest.mark.parametrize("kind", ["ex", "mex"])
@pytest.mark.parametrize("n_jobs", [1, 2])
def test_sigterm_mid_search_ends_the_runner_and_writes_no_completed_run(
    tmp_path, kind, n_jobs
):
    proc, run_dir, n_calls = _run(tmp_path, kind, n_jobs, _FIRST_CALL_OF_SECOND[kind])
    assert n_calls >= _FIRST_CALL_OF_SECOND[kind], proc.stdout + proc.stderr
    assert proc.returncode == -signal.SIGTERM, (proc.returncode, proc.stdout[-2000:])
    assert not (run_dir / "run_config.json").exists()
    assert not (run_dir / "final_output.csv").exists()


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_the_same_runner_left_alone_completes_and_writes_its_run(tmp_path, kind):
    """Control: the child harness itself works, so the cancel cases above cannot pass by crashing."""
    proc, run_dir, n_calls = _run(tmp_path, kind, 1, trigger=0)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    run_config = json.loads((run_dir / "run_config.json").read_text())
    with open(run_dir / "final_output.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) > 1
    assert run_config["n_combinations"] == len(rows)
    # Every candidate costs the same number of field gathers; the run evaluated them all.
    per_candidate = _FIRST_CALL_OF_SECOND[kind] - 1
    assert n_calls % per_candidate == 0 and n_calls // per_candidate > 1
