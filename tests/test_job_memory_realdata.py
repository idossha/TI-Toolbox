"""Every scheduler memory claim covers what the same job really used (Dataset 000).

What this pins
--------------
``tit.jobs.costs.default_cost(kind, config).mem_gb`` is what the scheduler admits a job with;
sim, flex and analyzer are different products and run side by side, so a claim below the real
peak lets the jobs together exceed the container and the kernel kills one. For every
**succeeded** job in ``<dataset>/code/ti-toolbox/jobs`` whose record carries ``rss_peak``, the
claim for that job's own ``spec.json`` (kind + config) must be at least that peak. A succeeded
run is a complete run, so its peak is the job's whole need; a failed or cancelled run stopped
early and under-reports it.

Where the numbers come from: ``status.json`` ``rss_peak`` is the server's own psutil PSS sample
of the job's process tree (``tit.jobs.runner.ResourceSampler``), measured while the job ran --
independent of the cost table. Claims are converted with 1e9 bytes per GB, the smaller of the
two readings of "GB" (the scheduler's budget is read in GiB), so the check is the strict one.
On 2026-10-22 it failed for sim 34ffcc59/b8fa6613/f56383c0 (7.57-8.30 GB against 4 GB) and
flex ad8cf881 (n_multistart 4, 15.19 GB against 6 GB).

The dataset is opened read-only: the test lists the mtimes of every file it reads before and
after, and they must be unchanged.

Reproduce::

    export TIT_DATASET_000=/Users/idohaber/datasets/000
    .venv/bin/python -m pytest tests/test_job_memory_realdata.py -q

Deliberately elsewhere: the model's code-fact properties (sim flat in montages, flex
non-decreasing in restarts) in ``tests/test_job_costs.py``. Written 2026-10-22 (package p41).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tit.jobs.costs import default_cost

DATASET = os.environ.get("TIT_DATASET_000", "")
JOBS = Path(DATASET) / "code" / "ti-toolbox" / "jobs" if DATASET else None

pytestmark = pytest.mark.skipif(
    not DATASET or not (JOBS and JOBS.is_dir()),
    reason=(
        "skipping: set TIT_DATASET_000 to a Dataset 000 copy with code/ti-toolbox/jobs "
        "to check memory claims against measured peaks"
    ),
)


@pytest.fixture(autouse=True)
def _no_user_preferences(tmp_path, monkeypatch):
    # `pre` costs read the user's saved thread preferences; memory does not depend on them.
    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: tmp_path / "preferences.json"
    )


def _mtimes(paths: list[Path]) -> dict[str, int]:
    return {str(p): p.stat().st_mtime_ns for p in paths}


def test_every_succeeded_jobs_memory_claim_covers_its_measured_peak():
    files = sorted(
        p
        for job in JOBS.iterdir()
        if job.is_dir()
        for p in (job / "spec.json", job / "status.json")
        if p.is_file()
    )
    before = _mtimes(files)

    checked: list[str] = []
    short: list[str] = []
    for job in sorted(JOBS.iterdir()):
        spec_file, status_file = job / "spec.json", job / "status.json"
        if not (spec_file.is_file() and status_file.is_file()):
            continue
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
        status = json.loads(status_file.read_text(encoding="utf-8"))
        peak = status.get("rss_peak")
        if status.get("state") != "succeeded" or not peak:
            continue
        claim = default_cost(spec["kind"], spec.get("config") or {}).mem_gb
        checked.append(f"{job.name} {spec['kind']}")
        if claim * 1e9 < peak:
            short.append(
                f"{job.name} {spec['kind']}: claims {claim:g} GB, used {peak / 1e9:.2f} GB"
            )

    assert _mtimes(files) == before, "the dataset's job records changed while reading"
    # Nothing to check would make this pass vacuously; Dataset 000 has sim and flex records.
    kinds_checked = {entry.split()[1] for entry in checked}
    assert {"sim", "flex"} <= kinds_checked, checked
    assert short == []
