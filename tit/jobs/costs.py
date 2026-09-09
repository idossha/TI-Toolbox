"""Per-kind default resource costs (TODO.md §2.4), data + one lookup function.

Placeholders (documented as such in TODO.md) until the resource-usage spike lands; a project can
override any kind's default in ``settings`` later.  A job's config may also carry its own
``cpus``/``memory_gb`` (QSIPrep-shaped configs do) — that always wins over the table below.
"""

from __future__ import annotations

from typing import Any

from tit.jobs.spec import Cost

# kind -> Cost.
DEFAULT_COSTS: dict[str, Cost] = {
    "pre": Cost(cpus=2, mem_gb=6),
    "sim": Cost(cpus=1, mem_gb=4),
    "flex": Cost(cpus=2, mem_gb=6),
    "flex_adaptive": Cost(cpus=2, mem_gb=6),
    "flex_pareto": Cost(cpus=2, mem_gb=6),
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
    "report": Cost(cpus=1, mem_gb=2),
}

_FALLBACK = Cost(cpus=1, mem_gb=2)


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def default_cost(kind: str, config: dict[str, Any] | None = None) -> Cost:
    """The default :class:`~tit.jobs.spec.Cost` for one job.

    A config carrying its own ``cpus``/``memory_gb`` (or ``mem_gb``) — QSIPrep/QSIRecon-shaped
    configs, and ``FlexConfig.cpus`` for the ``cpus`` half — overrides the table.  ``sim`` scales
    memory by the number of montages in the config (``sim 1 cpu / 4 GB per montage``, run
    sequentially by the runner so cpus stays flat).
    """
    config = config or {}
    base = DEFAULT_COSTS.get(kind, _FALLBACK)
    if kind == "pre" and config.get("run_fastsurfer"):
        # Upstream minimum system memory for segmentation; keep other pre stages unchanged.
        base = Cost(cpus=base.cpus, mem_gb=8)
    if kind == "blender" and config.get("_type") in (
        "VectorConfig",
        "RegionConfig",
        "SubcorticalConfig",
    ):
        # These geometry exports do not launch Blender or evaluate montage subdivision.
        base = Cost(cpus=1, mem_gb=2)
    cpus = _num(config.get("cpus"))
    mem = _num(config.get("memory_gb"))
    if mem is None:
        mem = _num(config.get("mem_gb"))

    if kind == "sim":
        n_montages = _n_montages(config)
        return Cost(cpus=base.cpus, mem_gb=base.mem_gb * max(n_montages, 1))

    if cpus is not None or mem is not None:
        return Cost(
            cpus=cpus if cpus is not None else base.cpus,
            mem_gb=mem if mem is not None else base.mem_gb,
        )

    return base


def _n_montages(config: dict[str, Any]) -> int:
    montages = config.get("montages")
    if isinstance(montages, list) and montages:
        return len(montages)
    return 1
