"""`tit.cpu` — the effective CPU count, against fixture cgroup trees.

Every case writes the files a real container would have (`root` exists for exactly this), so
these assert the parsing, not a mock of it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tit.cpu import JOB_CPUS_ENV, cgroup_cpu_limit, effective_cpus, job_cpus


def _v2(root: Path, cpu_max: str, cpuset: str | None = None) -> Path:
    (root / "cpu.max").write_text(cpu_max + "\n")
    if cpuset is not None:
        (root / "cpuset.cpus.effective").write_text(cpuset + "\n")
    return root


def _v1(root: Path, quota: str, period: str = "100000") -> Path:
    (root / "cpu").mkdir()
    (root / "cpu" / "cpu.cfs_quota_us").write_text(quota + "\n")
    (root / "cpu" / "cpu.cfs_period_us").write_text(period + "\n")
    return root


def test_cgroup_v2_quota_is_the_limit(tmp_path: Path) -> None:
    """`docker run --cpus=4` on a cgroup-v2 host writes `400000 100000`."""
    assert cgroup_cpu_limit(str(_v2(tmp_path, "400000 100000"))) == 4


def test_cgroup_v2_fractional_quota_floors(tmp_path: Path) -> None:
    """`--cpus=2.5` is 2 whole workers, never 3."""
    assert cgroup_cpu_limit(str(_v2(tmp_path, "250000 100000"))) == 2


def test_cgroup_v2_unlimited_is_no_limit(tmp_path: Path) -> None:
    assert cgroup_cpu_limit(str(_v2(tmp_path, "max 100000"))) is None


def test_cgroup_v2_cpuset_counts(tmp_path: Path) -> None:
    """`--cpuset-cpus=0-3,8` pins the container to five CPUs, with no quota set."""
    assert cgroup_cpu_limit(str(_v2(tmp_path, "max 100000", "0-3,8"))) == 5


def test_cgroup_v2_takes_the_smaller_of_quota_and_cpuset(tmp_path: Path) -> None:
    assert cgroup_cpu_limit(str(_v2(tmp_path, "200000 100000", "0-7"))) == 2


def test_cgroup_v1_quota_is_the_limit(tmp_path: Path) -> None:
    assert cgroup_cpu_limit(str(_v1(tmp_path, "300000"))) == 3


def test_cgroup_v1_unlimited_quota_is_no_limit(tmp_path: Path) -> None:
    assert cgroup_cpu_limit(str(_v1(tmp_path, "-1"))) is None


def test_no_cgroup_at_all_is_no_limit(tmp_path: Path) -> None:
    assert cgroup_cpu_limit(str(tmp_path)) is None


def test_effective_cpus_uses_the_cgroup_limit_not_the_host(tmp_path: Path) -> None:
    """The bug this module exists for: 12 host cores, `--cpus=2`, answer 2."""
    root = _v2(tmp_path, "200000 100000")
    assert effective_cpus(str(root)) == 2
    assert effective_cpus(str(root)) < (os.cpu_count() or 1) or (os.cpu_count() or 1) <= 2


def test_effective_cpus_without_a_cgroup_falls_back_to_affinity(tmp_path: Path) -> None:
    usable = effective_cpus(str(tmp_path))
    assert usable >= 1
    assert usable <= (os.cpu_count() or 1)


def test_effective_cpus_is_never_zero(tmp_path: Path) -> None:
    assert effective_cpus(str(_v2(tmp_path, "1000 100000"))) == 1


def test_job_cpus_reads_the_budget_the_runner_exported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(JOB_CPUS_ENV, "3")
    assert job_cpus() == 3
    assert job_cpus(default=9) == 3


def test_job_cpus_falls_back_outside_a_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(JOB_CPUS_ENV, raising=False)
    assert job_cpus(default=7) == 7
    assert job_cpus() == effective_cpus()


def test_job_cpus_ignores_junk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(JOB_CPUS_ENV, "not-a-number")
    assert job_cpus(default=5) == 5
