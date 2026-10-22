"""Per-kind default resource costs (docs/dev/ARCHITECTURE.md §6, job engine), data + one lookup.

A project can override any kind's default in ``settings`` later. A job's config may also carry
its own ``cpus``/``memory_gb`` (QSIPrep-shaped configs do) -- that wins over the table below,
when it is a finite, positive number (anything else is ignored: ``Cost(cpus=nan)`` never fits
a budget, and a negative claim would lower the running total and over-admit).

Memory claims for ``sim`` and the flex kinds are the measured peaks of real runs: the server's
own PSS samples (``status.json`` ``rss_peak``) in Dataset 000, October 2026.

- ``sim``, one montage each (jobs 34ffcc59, b8fa6613, f56383c0): 7.77, 7.57 and 8.30 GB, so
  :data:`SIM_MEM_GB` is 9 -- flat, because ``tit/sim/__main__`` runs a config's montages one
  after another.
- ``flex``: 5.84 GB with one restart (e689f217), 15.19 GB with four (ad8cf881). Each restart
  builds a new SimNIBS optimisation and the earlier ones' memory is not given back, so the peak
  grows with ``n_multistart`` (about 3.1 GB per restart over a 2.7 GB base); the claim is
  :data:`FLEX_BASE_MEM_GB` + :data:`FLEX_MEM_PER_RESTART_GB` per restart, both rounded up.

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

_FLEX_ONE_RESTART = Cost(cpus=2, mem_gb=FLEX_BASE_MEM_GB + FLEX_MEM_PER_RESTART_GB)

# kind -> Cost (flex kinds: one restart; default_cost adds the rest).
DEFAULT_COSTS: dict[str, Cost] = {
    "pre": Cost(cpus=2, mem_gb=6),
    "sim": Cost(cpus=1, mem_gb=SIM_MEM_GB),
    "flex": _FLEX_ONE_RESTART,
    "flex_adaptive": _FLEX_ONE_RESTART,
    "flex_pareto": _FLEX_ONE_RESTART,
    "ex": Cost(cpus=2, mem_gb=6),
    "mex": Cost(cpus=2, mem_gb=6),
    "leadfield": Cost(cpus=2, mem_gb=8),
    "analyzer": Cost(cpus=1, mem_gb=4),
    "stats": Cost(cpus=1, mem_gb=4),
    "source": Cost(cpus=1, mem_gb=4),
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
    ``n_multistart``; ``sim`` memory does not grow with the montage count (see the module
    docstring for both measurements).
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

    if kind in ("ex", "mex", "stats"):
        # These fork one worker per CPU (exhaustive searches; cluster-permutation stats):
        # `n_jobs < 1` means "the whole budget this job is admitted with", so the plan claims the
        # user's global CPU limit, and an explicit `n_jobs` is clamped to it
        # (tit.opt.ex.parallel.resolve_n_jobs does the same at run time).
        limit = cpu_limit()
        n_jobs = _count(config.get("n_jobs"))
        if n_jobs is not None:
            return Cost(cpus=min(n_jobs, limit), mem_gb=base.mem_gb)
        return Cost(cpus=limit, mem_gb=base.mem_gb)

    if cpus is not None or mem is not None:
        return Cost(
            cpus=cpus if cpus is not None else base.cpus,
            mem_gb=mem if mem is not None else base.mem_gb,
        )

    return base
