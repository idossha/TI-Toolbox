"""Per-kind default resource costs (docs/dev/ARCHITECTURE.md §6, job engine), data + one lookup.

A project can override any kind's default in ``settings`` later. A job's config may also carry
its own ``cpus``/``memory_gb`` (QSIPrep-shaped configs do) -- that wins over the table below,
when it is a finite, positive number (anything else is ignored: ``Cost(cpus=nan)`` never fits
a budget, and a negative claim would lower the running total and over-admit).

Memory claims for ``sim``, the flex kinds and ``ex``/``mex`` are the measured peaks of real runs:
the server's own PSS samples (``status.json`` ``rss_peak``) in Dataset 000, October-November 2026.

- ``sim``, one montage each (jobs 34ffcc59, b8fa6613, f56383c0): 7.77, 7.57 and 8.30 GB, so
  :data:`SIM_MEM_GB` is 9 -- flat, because ``tit/sim/__main__`` runs a config's montages one
  after another.
- ``flex``: 5.84 GB with one restart (e689f217), 15.19 GB with four (ad8cf881). Each restart
  builds a new SimNIBS optimisation and the earlier ones' memory is not given back, so the peak
  grows with ``n_multistart`` (about 3.1 GB per restart over a 2.7 GB base); the claim is
  :data:`FLEX_BASE_MEM_GB` + :data:`FLEX_MEM_PER_RESTART_GB` per restart, both rounded up.
- ``ex``/``mex``: the job loads its whole leadfield (sub-101's 75-electrode EEG10-10 one is
  3.5 GB of float64) and forks one worker per CPU it is admitted with
  (:mod:`tit.opt.ex.parallel`); each worker adds its own full-mesh field arrays. The same
  256-montage bucket search on that leadfield peaked at 4.79, 4.98, 5.77 and 7.27 GB with 1, 2,
  4 and 8 workers (jobs 2fdca13b, 0f0802f6, 95712f85, 93ae4df0, run 2026-11-03 on a
  copy-on-write clone of Dataset 000; c6401588, the Dataset 000 run that found the old flat 6 GB
  short, 7.30 GB with 8), and one-montage runs, which evaluate in the parent, 4.87 GB (ex) and
  5.18 GB (mEx). For ex the montage count does not matter (results are small rows). The ex
  claim is :data:`EX_BASE_MEM_GB` + :data:`EX_MEM_PER_WORKER_GB` per CPU claimed (about 0.38 GB
  per worker over 4.2 GB, rounded up; the base also covers mEx in one process: 5.18 GB for one
  montage, 4.89 GB for 64, job e26b35b8).
- ``mex`` with forked workers does not follow the worker count: a 16-montage search peaked at
  8.42 GB with 4 workers and 8.47 GB with 8 (jobs 7a154326, 56eed5c6), the 256-montage one at
  12.64 GB with 8 (job 43c13b0b), all on the clone, 2026-11-03. Forked mEx memory grows with
  the candidates evaluated while the same evaluation in one process does not, so it claims
  :data:`MEX_FORKED_MEM_GB` whenever it forks.

``tests/test_job_memory_realdata.py`` checks every claim against those records
(``TIT_DATASET_000``).
"""

from __future__ import annotations

import math
from typing import Any

from tit.cpu import cpu_limit
from tit.jobs.kinds import FLEX_KINDS
from tit.jobs.spec import Cost
from tit.surfer_settings import effective_threads

#: One simulation's memory, whatever the montage count (see the module docstring).
SIM_MEM_GB = 9
#: Flex memory is ``FLEX_BASE_MEM_GB + FLEX_MEM_PER_RESTART_GB * n_multistart``.
FLEX_BASE_MEM_GB = 3
FLEX_MEM_PER_RESTART_GB = 3.5
#: Ex/mEx memory is ``EX_BASE_MEM_GB + EX_MEM_PER_WORKER_GB * cpus`` (one worker per CPU).
# shortcut: the base holds one 75-electrode leadfield (3.5 GB loaded); a denser net's is larger
# (up to ~20 GB on disk), so add the leadfield file's size once such a search is measured.
EX_BASE_MEM_GB = 5
EX_MEM_PER_WORKER_GB = 0.5
#: An mEx search with more than one worker (see the module docstring).
# shortcut: covers forked searches up to the 256 candidates measured; the growth with candidates
# looks like a defect of the forked mEx path, so find it before raising this for larger searches.
MEX_FORKED_MEM_GB = 13

# shortcut: not measured per stage; 13.5 M points load as float64 lists (~1 GB) on top of the
# fields. Measure on a track + assess run before tightening.
TRACT_MEM_GB = 8
TRACT_TRACK_MEM_GB = 16

_FLEX_ONE_RESTART = Cost(cpus=2, mem_gb=FLEX_BASE_MEM_GB + FLEX_MEM_PER_RESTART_GB)

# kind -> Cost (flex kinds: one restart; default_cost adds the rest).
DEFAULT_COSTS: dict[str, Cost] = {
    "pre": Cost(cpus=2, mem_gb=6),
    "sim": Cost(cpus=1, mem_gb=SIM_MEM_GB),
    "flex": _FLEX_ONE_RESTART,
    "flex_adaptive": _FLEX_ONE_RESTART,
    "flex_pareto": _FLEX_ONE_RESTART,
    "ex": Cost(cpus=2, mem_gb=EX_BASE_MEM_GB + 2 * EX_MEM_PER_WORKER_GB),
    "mex": Cost(cpus=2, mem_gb=MEX_FORKED_MEM_GB),
    "leadfield": Cost(cpus=2, mem_gb=8),
    "analyzer": Cost(cpus=1, mem_gb=4),
    "stats": Cost(cpus=1, mem_gb=4),
    "source": Cost(cpus=1, mem_gb=4),
    # network, assess and target stages; a track stage claims more (default_cost).
    "tract": Cost(cpus=1, mem_gb=TRACT_MEM_GB),
    # The 183-electrode montage exceeds 12 GiB with its existing subdivision modifiers.
    "blender": Cost(cpus=1, mem_gb=16),
    "nifti_average": Cost(cpus=1, mem_gb=2),
    "nilearn": Cost(cpus=1, mem_gb=2),
    "tools": Cost(cpus=1, mem_gb=1),
}

_FALLBACK = Cost(cpus=1, mem_gb=2)


def _num(value: Any) -> float | None:
    """*value* as a float when it is a finite number above zero, else ``None`` (no claim)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if math.isfinite(number) and number > 0:
            return number
    return None


def _count(value: Any) -> int | None:
    """*value* as a whole count when it is a finite number of at least one, else ``None``."""
    number = _num(value)
    return int(number) if number is not None and number >= 1 else None


def default_cost(kind: str, config: dict[str, Any] | None = None) -> Cost:
    """The default :class:`~tit.jobs.spec.Cost` for one job.

    A config carrying its own ``cpus``/``memory_gb`` (or ``mem_gb``) — QSIPrep/QSIRecon-shaped
    configs, and ``FlexConfig.cpus`` for the ``cpus`` half — overrides the table when the value
    is a finite number above zero; a CPU claim is at least one CPU. Flex memory grows with
    ``n_multistart``, ex memory with the CPUs (workers) claimed, forked mEx is flat; ``sim`` memory does not grow
    with the montage count (see the module docstring for the measurements).
    """
    config = config or {}
    base = DEFAULT_COSTS.get(kind, _FALLBACK)
    if kind == "pre" and config.get("run_fastsurfer"):
        # Upstream minimum system memory for segmentation; keep other pre stages unchanged.
        base = Cost(
            cpus=effective_threads(
                "fastsurfer", _count(config.get("fastsurfer_threads"))
            ),
            mem_gb=8,
        )
    if kind == "pre" and config.get("run_freesurfer"):
        base = Cost(
            cpus=max(
                base.cpus,
                effective_threads(
                    "freesurfer", _count(config.get("freesurfer_threads"))
                ),
            ),
            mem_gb=16,
        )
    if kind == "pre" and config.get("create_m2m"):
        base = Cost(
            cpus=max(
                base.cpus,
                effective_threads("charm", _count(config.get("charm_threads"))),
            ),
            mem_gb=base.mem_gb,
        )
    if kind == "pre":
        for tool, field in (
            ("qsiprep", "qsiprep_config"),
            ("qsirecon", "qsi_recon_config"),
        ):
            if config.get(f"run_{tool}"):
                resources = config.get(field) or {}
                base = Cost(
                    cpus=max(
                        base.cpus,
                        effective_threads(tool, _count(resources.get("cpus"))),
                    ),
                    mem_gb=max(
                        base.mem_gb, _num(resources.get("memory_gb")) or base.mem_gb
                    ),
                )
    if kind == "blender" and config.get("_type") in (
        "VectorConfig",
        "RegionConfig",
        "SubcorticalConfig",
    ):
        # These geometry exports do not launch Blender or evaluate montage subdivision.
        base = Cost(cpus=1, mem_gb=2)
    if kind in FLEX_KINDS:
        restarts = _count(config.get("n_multistart")) or 1
        base = Cost(
            cpus=base.cpus,
            mem_gb=FLEX_BASE_MEM_GB + FLEX_MEM_PER_RESTART_GB * restarts,
        )
    cpus = _num(config.get("cpus"))
    if cpus is not None:
        cpus = max(cpus, 1.0)
    mem = _num(config.get("memory_gb"))
    if mem is None:
        mem = _num(config.get("mem_gb"))

    if kind == "tract" and "track" in (config.get("stages") or ("track",)):
        # TrackConfig.n_jobs < 1 means the whole budget this job is admitted with.
        track = config.get("track")
        n_jobs = _count(track.get("n_jobs")) if isinstance(track, dict) else None
        limit = cpu_limit()
        return Cost(
            cpus=min(n_jobs, limit) if n_jobs is not None else limit,
            mem_gb=TRACT_TRACK_MEM_GB,
        )

    if kind in ("ex", "mex", "stats"):
        # These fork one worker per CPU (exhaustive searches; cluster-permutation stats):
        # `n_jobs < 1` means "the whole budget this job is admitted with", so the plan claims the
        # user's global CPU limit, and an explicit `n_jobs` is clamped to it
        # (tit.opt.ex.parallel.resolve_n_jobs does the same at run time).
        limit = cpu_limit()
        n_jobs = _count(config.get("n_jobs"))
        workers = min(n_jobs, limit) if n_jobs is not None else limit
        if kind == "stats":
            return Cost(cpus=workers, mem_gb=base.mem_gb)
        # A queued job's claim above the memory budget is clamped to it (JobManager), so a
        # small container still runs the search, alone.
        if kind == "mex" and workers > 1:
            return Cost(cpus=workers, mem_gb=MEX_FORKED_MEM_GB)
        return Cost(
            cpus=workers, mem_gb=EX_BASE_MEM_GB + EX_MEM_PER_WORKER_GB * workers
        )

    if cpus is not None or mem is not None:
        return Cost(
            cpus=cpus if cpus is not None else base.cpus,
            mem_gb=mem if mem is not None else base.mem_gb,
        )

    return base
