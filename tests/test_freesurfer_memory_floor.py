"""FreeSurfer starts on a Docker VM configured with 16 GB (2026-10-22, package p27).

What this pins: ``run_freesurfer`` refuses below the documented requirement ("FreeSurfer
requires at least 16 GiB of available container memory") but not on the machine that meets
it. The memory the server sees is what Linux reports, not what the user configured: Docker
Desktop's VM kernel keeps part of it, and docs/wiki/troubleshooting.md:125 shows an 8 GB VM
reported as 7.8 GB. The VM sizes below are scaled by that same 7.8/8 ratio, so a 16 GB VM is
seen as ~15.6 GiB -- the case the floor-to-GiB check refused before this fix.

The memory probes are the real ``tit.pre.qsi.utils`` code; only their two inputs (the cgroup
limit and ``/proc/meminfo``'s MemTotal) are replaced. Nothing launches a container: the
runner is a mock and the worker ``argv`` it receives is the evidence.

Reproduce: ``.venv/bin/python -m pytest tests/test_freesurfer_memory_floor.py -q``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from tit.paths import get_path_manager, reset_path_manager
from tit.pre import freesurfer as fs
from tit.pre.qsi import utils as qsi_utils
from tit.pre.utils import PreprocessError

GIB = 1024**3
#: docs/wiki/troubleshooting.md:125: an 8 GB Docker Desktop VM shows 7.8 GB to Linux.
VISIBLE_FRACTION = 7.8 / 8


def _vm_meminfo_bytes(configured_gib: float) -> int:
    """MemTotal (bytes, whole kB like /proc/meminfo) a VM of *configured_gib* reports."""
    return int(configured_gib * GIB * VISIBLE_FRACTION) // 1024 * 1024


@pytest.fixture
def project(tmp_path, monkeypatch):
    reset_path_manager()
    pm = get_path_manager(str(tmp_path))
    anat = Path(pm.bids_anat("001"))
    anat.mkdir(parents=True)
    (anat / "sub-001_T1w.nii.gz").write_bytes(b"t1")
    license = tmp_path / "license.txt"
    license.write_text("fixture")
    monkeypatch.setattr(fs, "resolve_fs_license_path", lambda: license)
    monkeypatch.setenv("LOCAL_PROJECT_DIR", "/host/project")
    monkeypatch.setattr(fs.subprocess, "run", Mock(return_value=Mock(returncode=0)))
    # A fixed CPU budget and no saved preferences, independent of this machine.
    monkeypatch.setattr("tit.cpu.effective_cpus", lambda: 4)
    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 4)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: tmp_path / "prefs.json"
    )
    yield pm
    reset_path_manager()


def _visible_memory(monkeypatch, *, cgroup_bytes=None, meminfo_bytes=None) -> None:
    monkeypatch.setattr(
        qsi_utils, "get_container_resource_limits", lambda: (None, cgroup_bytes)
    )
    monkeypatch.setattr(
        qsi_utils, "_get_total_mem_bytes_from_proc", lambda: meminfo_bytes
    )


def _worker_argv(pm) -> list[str]:
    def finish(argv, **_):
        done = Path(pm.freesurfer_subject("001"))
        for name in (
            "scripts/recon-all.done",
            "mri/norm.mgz",
            "mri/aseg.mgz",
            "mri/wmparc.mgz",
        ):
            (done / name).parent.mkdir(parents=True, exist_ok=True)
            (done / name).write_bytes(b"x")
        return 0

    runner = Mock()
    runner.run.side_effect = finish
    fs.run_freesurfer("001", recon_all=True, runner=runner, logger=Mock())
    runner.run.assert_called_once()
    return runner.run.call_args.args[0]


def test_the_audit_meminfo_of_a_16_gb_vm_is_about_15_6_gib():
    """The audit's MemTotal (16,370,000 kB) and the docs' 7.8/8 ratio describe the same VM."""
    audit = 16_370_000 * 1024
    assert audit / GIB == pytest.approx(15.61, abs=0.01)
    assert _vm_meminfo_bytes(16) / GIB == pytest.approx(15.6, abs=0.01)
    assert int(audit // GIB) == 15  # what get_inherited_dood_resources floors it to


@pytest.mark.parametrize(
    "meminfo", [16_370_000 * 1024, _vm_meminfo_bytes(16)], ids=["audit", "docs-ratio"]
)
def test_a_16_gb_vm_launches_the_worker_with_16g(project, monkeypatch, meminfo):
    _visible_memory(monkeypatch, meminfo_bytes=meminfo)
    argv = _worker_argv(project)
    assert argv[argv.index("--memory") + 1] == "16g"
    assert argv[argv.index("--cpus") + 1] == "4"


def test_a_cgroup_limit_of_exactly_16_gib_is_accepted(project, monkeypatch):
    # A cgroup limit is exact; /proc/meminfo is not consulted when one is set.
    _visible_memory(monkeypatch, cgroup_bytes=17179869184, meminfo_bytes=4 * GIB)
    argv = _worker_argv(project)
    assert argv[argv.index("--memory") + 1] == "16g"


@pytest.mark.parametrize("configured_gib", [15, 12, 8])
def test_a_vm_below_16_gb_is_still_refused(project, monkeypatch, configured_gib):
    _visible_memory(monkeypatch, meminfo_bytes=_vm_meminfo_bytes(configured_gib))
    runner = Mock()
    with pytest.raises(
        PreprocessError,
        match=r"^FreeSurfer requires at least 16 GiB of available container memory\.$",
    ):
        fs.run_freesurfer("001", recon_all=True, runner=runner, logger=Mock())
    runner.run.assert_not_called()
