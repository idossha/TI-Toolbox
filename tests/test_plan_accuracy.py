"""The plan's numbers are the run's numbers.

Two claims, one file:

1. **Agreement** — the CPU count the plan panel shows is the CPU count the solver is handed
   (``OMP_NUM_THREADS``/``TIT_JOB_CPUS`` for the FEM kinds, the worker count for the exhaustive
   searches, SimNIBS' ``cpus`` argument for flex).
2. **Calibration** — each estimate model reproduces the measured run it was calibrated on, as
   recorded in ``docs/dev/BENCHMARKS.md``. The tolerances are wide on purpose: an estimate that
   lands within a quarter of a measured wall clock is doing its job; one that is out by 3x is a
   model that has drifted from its baseline and should fail here rather than mislead a user.
"""

from __future__ import annotations

from typing import Any

import pytest

from tit.cpu import JOB_CPUS_ENV
from tit.jobs.costs import default_cost
from tit.jobs.eta import SystemProfile, eta_minutes
from tit.jobs.runner import runner_env
from tit.opt.ex.parallel import resolve_n_jobs

#: The machine every constant in `tit/jobs/eta.py` was measured on: the maintainer's 12-core
#: Apple Silicon host running the amd64 image under emulation (BENCHMARKS.md preamble).
REFERENCE = SystemProfile(cpus=12, emulated=True, factor=3.0)


def _minutes(kind: str, config: dict[str, Any], **kwargs: Any) -> float:
    minutes = eta_minutes(kind, config, system=REFERENCE, **kwargs)
    assert minutes is not None, f"{kind} has no estimate for this configuration"
    return minutes


def _close(actual: float, measured: float, tol: float = 0.25) -> None:
    assert actual == pytest.approx(measured, rel=tol), (
        f"estimate {actual:.1f} min is more than {tol:.0%} from the measured {measured:.1f} min"
    )


# --------------------------------------------------------------------------- agreement


def test_runner_exports_the_admitted_cpu_budget() -> None:
    """The child gets the plan's CPU count under every name a solver might read."""
    env = runner_env(
        "job-1",
        events_file="events.jsonl",
        interface="cli",
        base_env={"PATH": "/usr/bin"},
        cpus=3,
    )
    assert env["OMP_NUM_THREADS"] == "3"
    assert env["MKL_NUM_THREADS"] == "3"
    assert env["NUMBA_NUM_THREADS"] == "3"
    assert env[JOB_CPUS_ENV] == "3"


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_exhaustive_search_forks_exactly_what_the_plan_showed(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`n_jobs=-1` (the UI default) used to fork `os.cpu_count()-1` workers behind a 2-CPU plan."""
    planned = default_cost(kind, {"n_jobs": -1}).cpus
    monkeypatch.setenv(JOB_CPUS_ENV, str(int(planned)))
    assert resolve_n_jobs(-1) == planned


@pytest.mark.parametrize("kind", ["ex", "mex"])
def test_an_explicit_n_jobs_is_what_the_plan_shows(kind: str) -> None:
    assert default_cost(kind, {"n_jobs": 4}).cpus == 4


def test_flex_cpus_in_the_config_is_what_the_plan_shows() -> None:
    assert default_cost("flex", {"cpus": 6}).cpus == 6


def test_sim_cost_is_one_cpu_per_montage_run_serially() -> None:
    """The runner runs a sim's montages one after another, so CPUs stay flat and memory scales."""
    one = default_cost("sim", {"montages": [{}]})
    three = default_cost("sim", {"montages": [{}, {}, {}]})
    assert one.cpus == three.cpus == 1
    assert three.mem_gb == 3 * one.mem_gb


# --------------------------------------------------------------------------- calibration
#
# Each case names the measured run in docs/dev/BENCHMARKS.md (or the maintainer's ernie runs
# tabulated in tit/jobs/eta.py's docstring) that the model's constants come from.


def test_sim_matches_the_measured_two_carrier_session() -> None:
    """BENCHMARKS 2026-09-13: two serial remeshed carrier solves + cortical mapping, 366.46 s."""
    minutes = _minutes("sim", {"montages": [{"electrode_pairs": [[1, 2], [3, 4]]}]})
    _close(minutes, 366.46 / 60.0)


def test_sim_anisotropic_costs_more_than_scalar() -> None:
    scalar = _minutes("sim", {"montages": [{}], "conductivity": "scalar"})
    tensor = _minutes("sim", {"montages": [{}], "conductivity": "vn"})
    assert tensor > scalar


def test_flex_matches_the_measured_two_multistart_run() -> None:
    """eta.py's calibration table: `VAL_rthal_flex_focality`, n_multistart=2, about 25 min."""
    _close(_minutes("flex", {"n_multistart": 2}), 25.0)


def test_flex_scales_with_the_de_budget() -> None:
    """Doubling the evaluations doubles the search, which is nearly the whole run."""
    base = _minutes("flex", {"n_multistart": 1})
    doubled = _minutes(
        "flex", {"n_multistart": 1, "population_size": 30, "max_iterations": 1000}
    )
    assert doubled > 1.8 * (base - 1.0)


def test_ex_matches_the_measured_large_sweep() -> None:
    """eta.py's calibration table: `docs_ex_large`, 16,807 combinations, about 14 min."""
    resolved = {"search_space": {"n_combinations": 16_807}}
    _close(_minutes("ex", {}, resolved=resolved), 14.0)


def test_leadfield_matches_the_measured_76_electrode_run() -> None:
    """eta.py's calibration table: EEG10-10_UI_Jurak_2007, 76 electrodes, 23.0 min.

    The cap is read off the project, so this drives the model directly rather than through a
    fixture subject: the count is the only input.
    """
    from tit.jobs import eta as eta_model

    minutes = eta_model.FIXED_MIN["leadfield"] + eta_model.PER_UNIT_MIN["leadfield"] * 76
    _close(minutes * REFERENCE.factor, 23.0)


def test_pre_stage_sum_matches_the_step_table() -> None:
    """charm + FastSurfer + tissue on one subject, the figures the step table carries."""
    resolved = {
        "stages": [
            {"subject": "ernie", "tags": ["G2a"]},
            {"subject": "ernie", "tags": ["G2b"]},
            {"subject": "ernie", "tags": ["G3"]},
        ]
    }
    _close(_minutes("pre", {}, resolved=resolved), 45 + 90 + 3 + 1, tol=0.05)


def test_freesurfer_has_no_estimate() -> None:
    """No measured FreeSurfer baseline exists, so the plan says nothing rather than guessing."""
    assert eta_minutes("pre", {"run_freesurfer": True}, system=REFERENCE) is None


def test_kinds_without_a_model_say_so() -> None:
    for kind in ("analyzer", "stats", "blender", "nilearn"):
        assert eta_minutes(kind, {}, system=REFERENCE) is None


def test_leadfield_without_a_readable_cap_says_nothing() -> None:
    assert eta_minutes("leadfield", {"eeg_net": None}, system=REFERENCE) is None


# --------------------------------------------------------------------------- parallelism math


def test_parallel_lanes_divide_the_wall_clock_but_never_below_one_job() -> None:
    config = {"montages": [{}]}
    serial = _minutes("sim", config, n_jobs=4, parallel=1)
    two = _minutes("sim", config, n_jobs=4, parallel=2)
    over = _minutes("sim", config, n_jobs=4, parallel=99)
    one = _minutes("sim", config, n_jobs=1, parallel=1)
    assert two == pytest.approx(serial / 2)
    # More lanes than jobs cannot beat running every job at once.
    assert over == pytest.approx(one)


def test_a_faster_machine_shortens_the_estimate() -> None:
    config = {"montages": [{}]}
    native = SystemProfile(cpus=12, emulated=False, factor=1.0)
    assert _minutes("sim", config) > eta_minutes("sim", config, system=native)
