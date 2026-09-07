"""Wall-clock estimates for one job -- ``PlanCost.eta_minutes``.

Why this exists
---------------
The UI used to state a job's duration as a constant typed into a button ("Generate (~40 min)")
or as a per-kind row in the renderer's step table.  Both are wrong the moment anything about the
job changes: a leadfield for a 19-electrode cap and one for a 256-electrode cap differ by more
than an order of magnitude (one FEM solve per electrode), and the same job on a native x86 host
and under Rosetta/QEMU emulation differs by another factor of three.

The model
---------
Every estimate has the same shape::

    minutes = (fixed + per_unit * units) * mesh_scale * system.factor / parallel

* ``units`` is what actually drives the run: electrodes in the cap (leadfield), electrode pairs
  (simulation), candidate evaluations (ex/mEx), multistart runs x iterations (flex), stages
  (pre-processing).
* ``mesh_scale`` is the subject's head mesh measured against ernie's, using the ``.msh`` file
  size as a cheap proxy for the element count (a stat() call, not a parse), clamped so a missing
  or unusual mesh cannot produce an absurd number.
* ``system.factor`` folds in the two machine facts that matter: how many cores the container has,
  and whether it is running emulated (an amd64 image under Rosetta on Apple Silicon, which is
  where every constant below was measured).

Calibration
-----------
The constants are the *native* (non-emulated, 12-core) numbers implied by real runs on this
project's ernie subject, all measured under emulation and therefore divided by
:data:`EMULATION_FACTOR`:

===============  ====================================================  =====================
Kind             Measured run (emulated, ernie mesh ~184 MB)           Implied constants
===============  ====================================================  =====================
leadfield        76-electrode ``EEG10-10_UI_Jurak_2007``: 16:27:26 ->  fixed 2.0 min,
                 16:50:27 = 23.0 min (76 electrode placements at       0.276 min/electrode
                 ~8.2 s, 75 FEM solves at ~6.2 s + ~2.2 s overhead)
sim              one TI montage (2 pairs): 00:50:33 -> 00:56:10 =      0.8 + 1.7/pair + 1.4
                 5.6 min (2 solves at ~5.8 s; meshing the pads and
                 the post-processing dominate)
ex               ``docs_ex_large``, 16 807 combinations: ~14 min       2.0 min + 7.1e-4/eval
flex             ``VAL_rthal_flex_focality``, n_multistart=2: ~25 min  1.0 + 12.0/multistart
                                                                       at the default budget
pre              the per-stage figures the renderer's step table       charm 15, FastSurfer 30,
                 carried (measured on the same machine)                QSIPrep 40, ...
===============  ====================================================  =====================

So on the machine they were measured on (12 cores, emulated -> factor 3.0) the model reproduces
those wall clocks, and it extrapolates rather than guesses everywhere else: the same subject's
256-electrode cap comes out near 70 min, not the 40 min the button used to claim.

Every number here is an estimate and the UI must label it as one.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, asdict
from functools import lru_cache
from typing import Any

# --------------------------------------------------------------------------- system

#: How much slower the amd64 image is under Rosetta/QEMU than on a native host.  Measured
#: order-of-magnitude, not a benchmark: SimNIBS' FEM solves run ~3x slower emulated.
EMULATION_FACTOR = 3.0
#: Core count the constants were calibrated on.
REFERENCE_CPUS = 12
#: The subject mesh the constants were calibrated on (``ernie.msh``), in bytes.
REFERENCE_MESH_BYTES = 184_000_000


@dataclass(frozen=True)
class SystemProfile:
    """The machine facts an estimate depends on."""

    cpus: int
    emulated: bool
    #: Multiplier applied to every native constant on this machine.
    factor: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cpuinfo() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            return fh.read(8192)
    except OSError:
        return ""


def _is_emulated(machine: str, cpuinfo: str) -> bool:
    """True when an x86_64 image is being translated (Rosetta on Apple Silicon, QEMU).

    Two independent tells, either is enough:

    * the vendor string is a translator's (``VirtualApple`` is Rosetta, ``QEMU``/``TCG`` is
      qemu-user / TCG);
    * the flag list has no ``avx`` -- no real x86_64 CPU that can run this image lacks AVX, but
      Rosetta does not implement it.
    """
    if machine.lower() not in ("x86_64", "amd64"):
        return False
    lowered = cpuinfo.lower()
    if any(tag in lowered for tag in ("virtualapple", "qemu", "tcg cpu")):
        return True
    if "flags" in lowered and " avx " not in lowered.replace("\n", " "):
        return True
    return False


def _cpu_factor(cpus: int) -> float:
    """Cores help, sub-linearly (the FEM solve is only partly parallel). Clamped both ways."""
    if cpus <= 0:
        return 1.0
    return min(2.0, max(0.7, (REFERENCE_CPUS / cpus) ** 0.5))


@lru_cache(maxsize=1)
def detect_system() -> SystemProfile:
    """This machine's :class:`SystemProfile` (cached -- it cannot change under us)."""
    cpus = os.cpu_count() or 1
    emulated = _is_emulated(platform.machine(), _cpuinfo())
    factor = _cpu_factor(cpus) * (EMULATION_FACTOR if emulated else 1.0)
    return SystemProfile(cpus=cpus, emulated=emulated, factor=round(factor, 3))


# --------------------------------------------------------------------------- mesh


def mesh_scale(subject_id: str | None) -> float:
    """The subject's head mesh against ernie's, as a cheap ``stat()`` on ``<sid>.msh``.

    1.0 when the mesh is unknown (the job would create it, or the project is not readable).
    Clamped to [0.4, 3.0]: the proxy is a file size, not an element count, and a stray file
    must not turn an estimate into a fantasy.
    """
    path = _mesh_path(subject_id)
    if not path:
        return 1.0
    try:
        size = os.path.getsize(path)
    except OSError:
        return 1.0
    return min(3.0, max(0.4, size / REFERENCE_MESH_BYTES))


def _mesh_path(subject_id: str | None) -> str | None:
    if not subject_id:
        return None
    try:
        from tit import get_path_manager

        pm = get_path_manager()
    except Exception:  # pragma: no cover - no project configured
        return None
    try:
        return os.path.join(pm.m2m(subject_id), f"{subject_id}.msh")
    except Exception:  # pragma: no cover - defensive
        return None


# --------------------------------------------------------------------------- constants

#: Native minutes that do not depend on the job's size (mesh load, leadfield read, writing out).
FIXED_MIN: dict[str, float] = {
    "leadfield": 2.0 / EMULATION_FACTOR,
    "sim": (0.8 + 1.4) / EMULATION_FACTOR,
    "ex": 2.0 / EMULATION_FACTOR,
    "mex": 2.0 / EMULATION_FACTOR,
    "flex": 1.0 / EMULATION_FACTOR,
    "flex_adaptive": 1.0 / EMULATION_FACTOR,
    "flex_pareto": 1.0 / EMULATION_FACTOR,
    "analyzer": 2.0 / EMULATION_FACTOR,
}
#: Native minutes per unit of the thing that drives the kind (see the module docstring).
PER_UNIT_MIN: dict[str, float] = {
    #: per electrode in the cap: one placement (~8.2 s) plus one FEM solve (~8.4 s), emulated.
    "leadfield": 0.276 / EMULATION_FACTOR,
    #: per electrode pair: meshing the pads dominates the solve itself.
    "sim": 1.7 / EMULATION_FACTOR,
    #: per candidate evaluation of the exhaustive sweep.
    "ex": 7.1e-4 / EMULATION_FACTOR,
    "mex": 7.1e-4 / EMULATION_FACTOR,
    #: per multistart run at the default DE budget (see FLEX_REFERENCE_EVALS).
    "flex": 12.0 / EMULATION_FACTOR,
    "flex_adaptive": 12.0 / EMULATION_FACTOR,
    "flex_pareto": 12.0 / EMULATION_FACTOR,
}
#: An anisotropic (DTI) conductivity model costs more per solve than the isotropic default.
ANISOTROPY_FACTOR = 1.3
#: DE budget the flex constant was measured at: ``population_size x max_iterations``.
FLEX_REFERENCE_EVALS = 30 * 500

#: Native per-stage minutes for pre-processing, keyed by the stage tags ``tit.jobs.plans`` emits.
#: These are the figures the renderer's step table carried, divided by :data:`EMULATION_FACTOR`
#: (they were measured on the same emulated machine), so this model reproduces them here.
PRE_STAGE_MIN: dict[str, float] = {
    "G1": 2.0 / EMULATION_FACTOR,
    "G2a": 45.0 / EMULATION_FACTOR,
    "G2b": 90.0 / EMULATION_FACTOR,
    "G3": 3.0 / EMULATION_FACTOR,
    "G4": 120.0 / EMULATION_FACTOR,
    "G5": 60.0 / EMULATION_FACTOR,
    "G6": 6.0 / EMULATION_FACTOR,
    "report": 1.0 / EMULATION_FACTOR,
}
#: A pre-processing plan whose stages could not be resolved.
PRE_DEFAULT_MIN = sum(PRE_STAGE_MIN[k] for k in ("G2a", "G2b", "G3", "report"))


# --------------------------------------------------------------------------- unit counts


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def electrode_count(subject_id: str | None, eeg_net: str | None) -> int | None:
    """Number of electrodes in *eeg_net* for *subject_id*, from the subject's cap CSV.

    ``None`` when the cap cannot be read -- the caller then has no leadfield estimate to give,
    which is honest, rather than a number invented from a default cap size.
    """
    if not subject_id or not eeg_net:
        return None
    try:
        from tit import get_path_manager
        from tit.catalog import _read_cap_electrode_labels

        pm = get_path_manager()
        name = eeg_net if eeg_net.lower().endswith(".csv") else f"{eeg_net}.csv"
        labels = _read_cap_electrode_labels(os.path.join(pm.eeg_positions(subject_id), name))
    except Exception:
        return None
    return len(labels) or None


def _sim_pairs(config: dict[str, Any]) -> int:
    """Electrode pairs the run solves, summed over montages.

    One FEM solve per pair: two for a TI montage, four or more for mTI
    (:attr:`tit.sim.config.Montage.electrode_pairs`).
    """
    total = 0
    for montage in _as_list(config.get("montages")):
        pairs = montage.get("electrode_pairs") if isinstance(montage, dict) else None
        total += len(_as_list(pairs)) or 2
    return total or 2


def _flex_units(config: dict[str, Any]) -> float:
    """Multistart runs, scaled by the DE budget relative to the one the constant was measured at."""
    starts = config.get("n_multistart")
    starts = starts if isinstance(starts, int) and starts > 0 else 1
    pop = config.get("population_size")
    iters = config.get("max_iterations")
    evals = (pop if isinstance(pop, int) and pop > 0 else 30) * (
        iters if isinstance(iters, int) and iters > 0 else 500
    )
    return starts * (evals / FLEX_REFERENCE_EVALS)


def _search_combinations(resolved: dict[str, Any] | None) -> int | None:
    """``n_combinations`` as ``tit.server.routes.plan`` already resolved it for ex/mEx."""
    if not isinstance(resolved, dict):
        return None
    space = resolved.get("search_space")
    if not isinstance(space, dict):
        return None
    n = space.get("n_combinations")
    return n if isinstance(n, int) and n > 0 else None


def _pre_minutes(resolved: dict[str, Any] | None) -> float:
    stages = (resolved or {}).get("stages") if isinstance(resolved, dict) else None
    total = 0.0
    for stage in _as_list(stages):
        tags = _as_list(stage.get("tags")) if isinstance(stage, dict) else []
        total += sum(PRE_STAGE_MIN.get(str(t), 0.0) for t in tags)
    return total or PRE_DEFAULT_MIN


# --------------------------------------------------------------------------- the estimate


def eta_minutes(
    kind: str,
    config: dict[str, Any] | None = None,
    *,
    resolved: dict[str, Any] | None = None,
    subject_id: str | None = None,
    n_jobs: int = 1,
    parallel: int = 1,
    system: SystemProfile | None = None,
) -> float | None:
    """Estimated wall-clock minutes for the whole plan, or ``None`` when it cannot be modelled.

    Parameters
    ----------
    kind : str
        Job kind (``"leadfield"``, ``"sim"``, ``"ex"``, ...).
    config : dict, optional
        The raw request config -- read for the montages, the cap, the DE budget.
    resolved : dict, optional
        The planner's own ``resolved`` block, so ex/mEx reuse the ``n_combinations`` it already
        counted and ``pre`` reuses its stage list rather than re-deriving either.
    subject_id : str, optional
        Whose head mesh and electrode cap to measure. Defaults to ``config["subject_id"]``.
    n_jobs : int
        Jobs in the plan (a batch of subjects/montages runs the same estimate that many times).
    parallel : int
        How many of them run at once.
    system : SystemProfile, optional
        Overrides :func:`detect_system` (tests, and a future "estimate for another machine").

    Returns
    -------
    float or None
        Minutes, rounded to one decimal.  ``None`` for a kind with no model, and for a leadfield
        whose cap cannot be read.
    """
    config = config or {}
    sid = subject_id or (config.get("subject_id") if isinstance(config.get("subject_id"), str) else None)
    sys_profile = system or detect_system()
    scale = mesh_scale(sid)

    if kind == "pre":
        per_job = _pre_minutes(resolved)
        scale = 1.0  # pre-processing BUILDS the mesh; there is nothing to measure yet.
    elif kind == "leadfield":
        n_electrodes = electrode_count(sid, config.get("eeg_net"))
        if n_electrodes is None:
            return None
        per_job = FIXED_MIN["leadfield"] + PER_UNIT_MIN["leadfield"] * n_electrodes
    elif kind == "sim":
        per_job = FIXED_MIN["sim"] + PER_UNIT_MIN["sim"] * _sim_pairs(config)
        # "vn" / "dir" / "mc" are the anisotropic (DTI) conductivity models; "scalar" is the
        # isotropic default (tit.sim.config.SimulationConfig.conductivity).
        if config.get("conductivity") in ("vn", "dir", "mc"):
            per_job *= ANISOTROPY_FACTOR
    elif kind in ("ex", "mex"):
        combos = _search_combinations(resolved)
        if combos is None:
            return None
        per_job = FIXED_MIN[kind] + PER_UNIT_MIN[kind] * combos
    elif kind in ("flex", "flex_adaptive", "flex_pareto"):
        per_job = FIXED_MIN[kind] + PER_UNIT_MIN[kind] * _flex_units(config)
    else:
        return None

    jobs = max(1, n_jobs)
    lanes = min(max(1, parallel), jobs)
    total = per_job * scale * sys_profile.factor * jobs / lanes
    return round(total, 1)
