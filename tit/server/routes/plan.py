"""``POST /api/plan/{kind}`` -- resolve what running a config would do.

For every kind this route builds the concrete output directory (or directories, for a batch of
subjects/montages) via :class:`~tit.paths.PathManager` -- the UI never recomputes a path
convention itself (design rule R1) -- reports whether it already exists, estimates the job's
resource cost from :mod:`tit.jobs.costs`, and checks for held lock conflicts via
:mod:`tit.jobs.locks` / :mod:`tit.jobs.api` (empty when the job manager, B1, is not wired up yet
in this environment).

``config`` uses the same kind -> dataclass resolution as
:mod:`tit.server.routes.validate` (:func:`~tit.server.routes.validate.cls_for`) -- a body that
fails validation here fails with the same ``ValueError``/``TypeError`` a
``POST /api/validate/{kind}`` call against it would report, just as a 422 instead of a 200
``{ok: false}`` (a plan cannot be computed for a config that does not even deserialize).

Per-kind output-dir resolution
-------------------------------
``sim``
    One :class:`PlanJob` per ``(subject, montage)``. ``config.montages`` applies to every
    subject in the plan; the request body's top-level ``montage_sources`` field
    (``contracts/openapi.v1.yaml``'s ``MontageSources`` -- ``{"flex": [{"subject"?, "run",
    "electrode_type"?, "eeg_net"?}], "freehand": [{"subject"?, "name"} | "name"]}``) is
    resolved via :mod:`tit.sim.montage_sources` into extra montages attached **only** to
    their own subject (flex-search runs and freehand stim-configs are inherently
    subject-scoped resources, unlike a plain ``montage_list.json`` entry). For one release,
    the pre-contract convention of the same data nested under ``config["montage_sources"]``
    (with ``run_name``/``subject_id`` field names) is still read as a fallback when the
    top-level field is absent -- see :func:`_montage_sources_for_request`. Either shape is
    ignored by :func:`~tit.config_io.deserialize_config` when read from ``config`` (not a
    ``SimulationConfig`` field).
``flex`` / ``flex_adaptive`` / ``flex_pareto``
    ``config.output_folder`` when set, else a previewed
    :func:`~tit.opt.flex.utils.generate_run_dirname` name under ``flex-search/<subject>/`` (the
    real run may pick a different timestamp if run later -- flagged as a warning).
``ex`` / ``mex``
    ``config.run_name`` or a timestamp, under ``ex-search`` / ``m-ex-search``.
    ``resolved.search_space`` gives the exact combination count from
    :mod:`tit.opt.ex.logic` / :mod:`tit.opt.mex.logic` (never materializing the search).
``leadfield``
    Existing leadfield lookup via ``LeadfieldGenerator.list_leadfields`` (no SimNIBS import).
``analyzer``
    ``config.output_dir`` when set, else :meth:`PathManager.analysis_output_dir`.
``pre``
    :func:`tit.jobs.plans.plan_preprocessing`'s ``G1``-``G6``/``report`` DAG, flattened to one
    :class:`PlanJob` per *stage* per subject (not one per subject) -- exactly the granularity
    ``POST /api/jobs/groups`` submits. Each stage's ``output_dir`` is a best-effort mapping to
    the directory that stage's flag writes to (see :func:`_pre_stage_output_dir`) -- several
    stages share a directory with other content (e.g. ``G2a`` and ``G6`` both touch
    ``m2m_<subject>/``), so ``exists``/``will_overwrite`` there are coarser than for the
    single-output kinds above. The request's ``parallel_subjects`` (mirrors
    ``JobGroupRequest.parallel_subjects``, not yet in the frozen ``PlanRequest`` schema -- see
    :class:`PlanRequest`) is echoed back clamped to ``resolved.parallel_subjects`` and scales
    the cost estimate, so a plan preview reflects the concurrency the matching group
    submission would actually use.
``source``
    ``forward`` mode: :meth:`PathManager.forward` per subject. ``fsavg_map`` mode:
    :meth:`PathManager.sim_fsaverage` per ``(subject, simulation)`` pair.
``stats``
    Project-level (``PlanJob.subject`` is ``""``): :meth:`PathManager.stats_output` with the
    literal ``analysis_type`` ``tit.stats.permutation`` itself uses (``"group_comparison"`` /
    ``"correlation"``).
``blender``
    Best-effort: only when the config's own ``output_dir`` is already set (blender's exporters
    otherwise resolve it internally, which needs ``bpy``/``trimesh`` -- not importable outside
    the SimNIBS container, and not reproduced here).
``nifti_average`` / ``nilearn``
    One project-level :class:`PlanJob` (``subject=""``, like ``stats``): ``output_dir`` mirrors
    ``tit.stats.nifti_average.main`` / ``tit.plotting.nilearn.__main__.main``'s own formula
    exactly (``derivatives/ti-toolbox/{nifti_average,nilearn_visuals}/<output_name or
    subdir_name>/``). Real validation/planning since the runners lane registered
    ``NiftiAverageConfig``/``NilearnConfig`` in
    :data:`tit.config_io.CONFIG_CLASS_REGISTRY` -- ``NO_SCHEMA_KINDS`` (see
    :mod:`tit.server.routes.validate`) is empty as a result, kept only as an extension point.
"""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tit.paths import PathManager, get_path_manager
from tit.server.routes.validate import ALL_KINDS, KindNotConfigurable, cls_for

router = APIRouter()

# NOTE: tit.config_io is imported lazily inside plan() below, not at module level -- see the
# matching note in tit.server.routes.validate. tit.paths has no SimNIBS dependency (verified),
# so it stays a normal top-level import.


# ---------------------------------------------------------------------------
# Wire shapes (contracts/openapi.v1.yaml: PlanJob, LockConflict, PlanCost, PlanResolved, PlanResult)
# ---------------------------------------------------------------------------


class PlanRequest(BaseModel):
    config: dict[str, Any]
    subject_ids: list[str] | None = None
    overwrite: bool = False
    #: contracts/openapi.v1.yaml's MontageSources -- kind=sim only. Top-level field, per the
    #: frozen contract (``{flex: [{subject?, run, electrode_type?, eeg_net?}], freehand:
    #: [{subject?, name}]}``). ``_plan_sim`` also accepts the pre-contract convention of the
    #: same data nested under ``config["montage_sources"]`` (with ``run_name``/``subject_id``
    #: field names) for one release, preferring this field when both are present -- see
    #: _montage_sources_for_request.
    montage_sources: dict[str, Any] | None = None
    #: kind=pre only, mirrors JobGroupRequest.parallel_subjects (contracts/openapi.v1.yaml) so
    #: a plan preview can reflect the same concurrency the matching ``POST /api/jobs/groups``
    #: call would use -- not yet part of the frozen PlanRequest schema (flagged for F1a to add
    #: alongside montage_sources); ``_plan_pre`` folds it into ``resolved.parallel_subjects``
    #: and the cost estimate scales with ``min(parallel_subjects, n_subjects)``.
    parallel_subjects: int | None = None


class PlanJob(BaseModel):
    kind: str
    subject: str
    output_dir: str
    exists: bool
    will_overwrite: bool


class LockConflict(BaseModel):
    key: str
    held_by: str
    kind: str
    subject: str
    started_at: str


class PlanSystem(BaseModel):
    """The machine an ``eta_minutes`` was computed for (:mod:`tit.jobs.eta`)."""

    cpus: int
    emulated: bool
    factor: float


class PlanCost(BaseModel):
    cpus: float
    mem_gb: float
    #: Estimated wall-clock minutes for the whole plan on THIS machine, or ``None`` when the
    #: kind has no model (or a leadfield whose cap CSV cannot be read). An estimate: the UI
    #: must label it as one. See :func:`tit.jobs.eta.eta_minutes`.
    eta_minutes: float | None = None
    system: PlanSystem | None = None


class PlanResult(BaseModel):
    jobs: list[PlanJob]
    lock_conflicts: list[LockConflict]
    cost: PlanCost
    warnings: list[str]
    resolved: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Cost / lock helpers (both tolerate B1's pieces not being wired up yet)
# ---------------------------------------------------------------------------


def _plan_cost(
    kind: str,
    raw_config: dict[str, Any],
    *,
    resolved: dict[str, Any] | None = None,
    jobs: list[PlanJob] | None = None,
    parallel: int = 1,
) -> PlanCost:
    """One representative job's resource cost for *kind* plus the plan's ETA.

    ``cpus``/``mem_gb`` are per job (not summed across a multi-job plan -- see this module's
    docstring); ``eta_minutes`` is the opposite, the wall clock of the WHOLE plan, because that
    is the number a user reads before pressing Run.
    """
    try:
        from tit.jobs.costs import default_cost
    except ImportError:
        return PlanCost(cpus=1.0, mem_gb=2.0)
    cost = default_cost(kind, raw_config)
    eta, system = _plan_eta(kind, raw_config, resolved=resolved, jobs=jobs, parallel=parallel)
    return PlanCost(cpus=cost.cpus, mem_gb=cost.mem_gb, eta_minutes=eta, system=system)


def _plan_eta(
    kind: str,
    raw_config: dict[str, Any],
    *,
    resolved: dict[str, Any] | None,
    jobs: list[PlanJob] | None,
    parallel: int,
) -> tuple[float | None, PlanSystem | None]:
    """``(eta_minutes, system)`` for the plan; ``(None, system)`` when the kind has no model."""
    try:
        from tit.jobs import eta as eta_model
    except ImportError:  # pragma: no cover - tit.jobs is always importable in-tree
        return None, None
    profile = eta_model.detect_system()
    system = PlanSystem(cpus=profile.cpus, emulated=profile.emulated, factor=profile.factor)
    job_list = jobs or []
    if kind == "pre":
        # `_plan_pre`'s `resolved["stages"]` already has one entry per (subject, stage), so the
        # stage sum IS the whole plan; only the subject concurrency divides it.
        n_jobs, lanes = 1, max(1, parallel)
    else:
        n_jobs, lanes = max(1, len(job_list)), max(1, parallel)
    subject = job_list[0].subject if job_list else None
    minutes = eta_model.eta_minutes(
        kind,
        raw_config,
        resolved=resolved,
        subject_id=subject,
        n_jobs=n_jobs,
        parallel=lanes,
        system=profile,
    )
    return minutes, system


def _plan_lock_conflicts(
    kind: str, subject_ids: list[str], raw_config: dict[str, Any]
) -> list[LockConflict]:
    try:
        from tit.jobs import api as jobs_api
        from tit.jobs import locks
    except ImportError:
        return []
    try:
        keys = [
            request.key for request in locks.keys_for(kind, subject_ids, raw_config)
        ]
        raw = jobs_api.lock_conflicts(keys)
    except (NotImplementedError, RuntimeError):
        return []
    return [LockConflict(**item) for item in raw]


# ---------------------------------------------------------------------------
# Per-kind planners: each returns (jobs, resolved)
# ---------------------------------------------------------------------------


def _dir_exists(path: str | None) -> bool:
    return bool(path) and os.path.isdir(path)


def _serialize_montage(montage: Any) -> dict[str, Any]:
    return {
        "name": montage.name,
        "mode": montage.mode.value,
        "electrode_pairs": [list(pair) for pair in montage.electrode_pairs],
        "eeg_net": montage.eeg_net,
        "display_name": montage.display_name,
    }


def _montage_sources_for_request(
    request_field: dict[str, Any] | None, raw_config: dict[str, Any]
) -> dict[str, Any]:
    """Resolve the ``MontageSources`` body for kind=sim, new field first.

    ``PlanRequest.montage_sources`` (contracts/openapi.v1.yaml) is the frozen wire shape;
    ``raw_config["montage_sources"]`` was this route's own pre-contract convention (see the
    module docstring's ``sim`` section) and is read as a fallback for one release so existing
    callers keep working while they move to the top-level field. The top-level field wins
    whenever both are present -- no silent merge of two sources for the same kind.
    """
    if request_field:
        return request_field
    return raw_config.get("montage_sources") or {}


def _spec_get(spec: dict[str, Any], *names: str) -> Any:
    """First present key in *spec* from *names*, e.g. the contract's ``run`` vs. the old ``run_name``."""
    for name in names:
        if spec.get(name) is not None:
            return spec[name]
    return None


def _plan_sim(
    kind: str,
    pm: PathManager,
    config: Any,
    raw_config: dict[str, Any],
    subject_ids: list[str],
    warnings: list[str],
    montage_sources_field: dict[str, Any] | None = None,
) -> tuple[list[PlanJob], dict[str, Any]]:
    from tit.sim import montage_sources

    source_montages: dict[str, list[Any]] = {}
    sources = _montage_sources_for_request(montage_sources_field, raw_config)

    for spec in sources.get("flex", []) or []:
        if not isinstance(spec, dict):
            warnings.append(f"flex montage source {spec!r} must be an object")
            continue
        sid = _spec_get(spec, "subject", "subject_id") or config.subject_id
        run_name = _spec_get(spec, "run", "run_name")
        if not sid or not run_name:
            warnings.append(f"flex montage source {spec!r} needs subject and run")
            continue
        try:
            montage = montage_sources.resolve_flex_montage(
                pm,
                sid,
                run_name,
                spec.get("electrode_type", "mapped"),
                eeg_net=spec.get("eeg_net"),
                run_id=spec.get("run_id"),
                display_name=spec.get("display_name"),
            )
        except ValueError as exc:
            warnings.append(f"flex montage source {spec!r}: {exc}")
            continue
        source_montages.setdefault(sid, []).append(montage)

    for spec in sources.get("freehand", []) or []:
        if isinstance(spec, dict):
            sid = _spec_get(spec, "subject", "subject_id") or config.subject_id
            name = spec.get("name")
        else:
            sid, name = config.subject_id, spec
        if not sid or not name:
            warnings.append(f"freehand montage source {spec!r} needs subject and name")
            continue
        try:
            montage = montage_sources.resolve_freehand_montage(pm, sid, name)
        except ValueError as exc:
            warnings.append(f"freehand montage source {name!r}: {exc}")
            continue
        source_montages.setdefault(sid, []).append(montage)

    subjects = list(subject_ids)
    if not subjects and config.subject_id:
        subjects = [config.subject_id]
    for sid in source_montages:
        if sid not in subjects:
            subjects.append(sid)

    if not subjects:
        warnings.append(
            "no subjects to plan for (subject_ids empty and config.subject_id unset)"
        )

    resolved_montages = [_serialize_montage(m) for m in config.montages]
    for montages in source_montages.values():
        resolved_montages.extend(_serialize_montage(m) for m in montages)

    jobs: list[PlanJob] = []
    for sid in subjects:
        montages = list(config.montages) + source_montages.get(sid, [])
        if not montages:
            warnings.append(f"{sid}: no montages resolved")
        for montage in montages:
            output_dir = pm.simulation(sid, montage.name)
            exists = _dir_exists(output_dir) and bool(os.listdir(output_dir))
            jobs.append(
                PlanJob(
                    kind=kind,
                    subject=sid,
                    output_dir=output_dir,
                    exists=exists,
                    will_overwrite=exists,
                )
            )

    return jobs, {"montages": resolved_montages}


def _plan_flex(
    kind: str, pm: PathManager, config: Any, subject_ids: list[str], warnings: list[str]
) -> tuple[list[PlanJob], None]:
    from tit.opt.flex.utils import generate_run_dirname

    subjects = subject_ids or ([config.subject_id] if config.subject_id else [])
    jobs: list[PlanJob] = []
    for sid in subjects:
        if config.output_folder:
            output_dir = config.output_folder
            exists = _dir_exists(output_dir)
        else:
            flex_root = pm.flex_search(sid)
            dirname = generate_run_dirname(flex_root)
            output_dir = os.path.join(flex_root, dirname)
            exists = False
            warnings.append(
                f"{sid}: output_folder not set; the previewed run name may differ from "
                "the one the run actually picks (both are the current timestamp, "
                "resolved a second apart)"
            )
        jobs.append(
            PlanJob(
                kind=kind,
                subject=sid,
                output_dir=output_dir,
                exists=exists,
                will_overwrite=exists,
            )
        )
    return jobs, None


def _plan_ex(
    kind: str, pm: PathManager, config: Any, subject_ids: list[str], warnings: list[str]
) -> tuple[list[PlanJob], dict[str, Any]]:
    from tit.opt.config import ExConfig
    from tit.opt.ex.logic import count_combinations, generate_current_ratios

    subjects = subject_ids or ([config.subject_id] if config.subject_id else [])
    jobs: list[PlanJob] = []
    for sid in subjects:
        run_name = config.run_name or time.strftime("%Y%m%d_%H%M%S")
        output_dir = pm.ex_search_run(sid, run_name)
        exists = _dir_exists(output_dir)
        jobs.append(
            PlanJob(
                kind=kind,
                subject=sid,
                output_dir=output_dir,
                exists=exists,
                will_overwrite=exists,
            )
        )

    if isinstance(config.electrodes, ExConfig.PoolElectrodes):
        pool = config.electrodes.electrodes
        e1p = e1m = e2p = e2m = pool
        all_combinations = True
    else:
        e1p = config.electrodes.e1_plus
        e1m = config.electrodes.e1_minus
        e2p = config.electrodes.e2_plus
        e2m = config.electrodes.e2_minus
        all_combinations = False

    ratios = generate_current_ratios(
        config.total_current,
        config.current_step,
        config.channel_limit or config.total_current - config.current_step,
    )
    n_combinations = count_combinations(e1p, e1m, e2p, e2m, ratios, all_combinations)
    return jobs, {
        "search_space": {
            "n_combinations": n_combinations,
            "n_current_ratios": len(ratios),
        }
    }


def _plan_mex(
    kind: str, pm: PathManager, config: Any, subject_ids: list[str], warnings: list[str]
) -> tuple[list[PlanJob], dict[str, Any]]:
    from tit.opt.config import MExConfig
    from tit.opt.mex.logic import count_multipolar_combinations

    subjects = subject_ids or ([config.subject_id] if config.subject_id else [])
    jobs: list[PlanJob] = []
    for sid in subjects:
        run_name = config.run_name or time.strftime("%Y%m%d_%H%M%S")
        output_dir = pm.m_ex_search_run(sid, run_name)
        exists = _dir_exists(output_dir)
        jobs.append(
            PlanJob(
                kind=kind,
                subject=sid,
                output_dir=output_dir,
                exists=exists,
                will_overwrite=exists,
            )
        )

    if isinstance(config.electrodes, MExConfig.PoolElectrodes):
        buckets_or_pool: Any = config.electrodes.electrodes
        all_combinations = True
    else:
        e = config.electrodes
        buckets_or_pool = {
            "e1_plus": e.e1_plus,
            "e1_minus": e.e1_minus,
            "e2_plus": e.e2_plus,
            "e2_minus": e.e2_minus,
            "e3_plus": e.e3_plus,
            "e3_minus": e.e3_minus,
            "e4_plus": e.e4_plus,
            "e4_minus": e.e4_minus,
        }
        all_combinations = False
        if config.symmetric_bucket:
            warnings.append(
                "search-space count ignores symmetric_bucket (an exact count needs the "
                "EEG-position CSV read by build_electrode_mirror_map); this is an upper bound"
            )

    n_combinations = count_multipolar_combinations(
        buckets_or_pool, all_combinations=all_combinations, channels=config.channels
    )
    return jobs, {"search_space": {"n_combinations": n_combinations}}


def _plan_leadfield(
    kind: str, pm: PathManager, config: Any, subject_ids: list[str], warnings: list[str]
) -> tuple[list[PlanJob], None]:
    from tit.opt.leadfield import LeadfieldGenerator

    subjects = subject_ids or [config.subject_id]
    jobs: list[PlanJob] = []
    for sid in subjects:
        generator = LeadfieldGenerator(sid, electrode_cap=config.eeg_net)
        existing = {net: path for net, path, _ in generator.list_leadfields(sid)}
        exists = config.eeg_net in existing
        output_dir = existing.get(
            config.eeg_net, os.path.join(pm.leadfields(sid), f"{config.eeg_net}.hdf5")
        )
        jobs.append(
            PlanJob(
                kind=kind,
                subject=sid,
                output_dir=output_dir,
                exists=exists,
                will_overwrite=exists and config.overwrite,
            )
        )
    if config.tissues != [1, 2]:
        warnings.append(
            "LeadfieldGenerator.generate(tissues=...) currently discards its argument and "
            "always uses [1, 2] -- see tit/opt/leadfield_config.py's Notes"
        )
    return jobs, None


def _plan_analyzer(
    kind: str, pm: PathManager, config: Any, subject_ids: list[str], warnings: list[str]
) -> tuple[list[PlanJob], None]:
    from tit.analyzer.config import AnalysisMode, AnalysisType

    if subject_ids:
        subjects = subject_ids
    elif config.mode == AnalysisMode.GROUP:
        subjects = list(config.subject_ids)
    else:
        subjects = [config.subject_id] if config.subject_id else []

    jobs: list[PlanJob] = []
    for sid in subjects:
        if config.output_dir:
            output_dir = config.output_dir
        else:
            try:
                if config.analysis_type == AnalysisType.SPHERICAL:
                    output_dir = pm.analysis_output_dir(
                        sid=sid,
                        sim=config.simulation,
                        space=config.space.value,
                        analysis_type="spherical",
                        coordinates=config.center,
                        radius=config.radius,
                        coordinate_space=config.coordinate_space.value,
                    )
                else:
                    region = config.region
                    region_str = (
                        ", ".join(region)
                        if isinstance(region, list)
                        else (region or "")
                    )
                    output_dir = pm.analysis_output_dir(
                        sid=sid,
                        sim=config.simulation,
                        space=config.space.value,
                        analysis_type="cortical",
                        whole_head=not region_str,
                        region=region_str or None,
                        atlas_name=config.atlas,
                    )
            except ValueError as exc:
                warnings.append(f"{sid}: {exc}")
                continue
        exists = _dir_exists(output_dir)
        jobs.append(
            PlanJob(
                kind=kind,
                subject=sid,
                output_dir=output_dir,
                exists=exists,
                will_overwrite=exists,
            )
        )

    if config.analysis_type == AnalysisType.SUBCORTICAL:
        warnings.append(
            "analysis_type='subcortical' is accepted by AnalyzerConfig but "
            "tit.analyzer.__main__ does not dispatch it yet (silent no-op today) -- see "
            "tit/analyzer/config.py's Notes"
        )
    return jobs, None


#: Best-effort stage -> output-dir mapping for the `pre` DAG (see module docstring's `pre`
#: section for the caveat: several stages share a directory with other content).
def _pre_stage_output_dir(pm: PathManager, sid: str, stage: str) -> str:
    return {
        "G1": pm.bids_anat(sid),
        "G2a": pm.m2m(sid),
        "G2b": pm.fastsurfer_subject(sid),
        "G3": pm.tissue_analysis_output(sid),
        "G4": pm.qsiprep_subject(sid),
        "G5": pm.qsirecon_subject(sid),
        "G6": pm.m2m(sid),
        "report": pm.reports(),
    }.get(stage, "")


def _plan_pre(
    pm: PathManager,
    config: Any,
    subject_ids: list[str],
    warnings: list[str],
    parallel_subjects: int | None = None,
) -> tuple[list[PlanJob], dict[str, Any]]:
    from tit.jobs.plans import plan_preprocessing

    subjects = subject_ids or list(config.subject_ids)
    effective_parallel = max(1, parallel_subjects or 1)
    if not subjects:
        warnings.append(
            "no subject_ids given and config.subject_ids is empty; nothing planned"
        )
        return [], {"stages": [], "parallel_subjects": effective_parallel}

    if effective_parallel > len(subjects):
        warnings.append(
            f"parallel_subjects={effective_parallel} exceeds the {len(subjects)} "
            "planned subject(s); at most one subject-DAG per subject can run at once"
        )

    planned = plan_preprocessing(config, subjects)
    jobs: list[PlanJob] = []
    stages: list[dict[str, Any]] = []
    for planned_job in planned:
        sid = planned_job.subject_ids[0] if planned_job.subject_ids else ""
        stage = planned_job.tags[0] if planned_job.tags else planned_job.kind
        output_dir = _pre_stage_output_dir(pm, sid, stage) if sid else ""
        exists = _dir_exists(output_dir)
        will_overwrite = exists and not config.skip_existing_outputs
        jobs.append(
            PlanJob(
                kind=planned_job.kind,
                subject=sid,
                output_dir=output_dir,
                exists=exists,
                will_overwrite=will_overwrite,
            )
        )
        stages.append(
            {
                "label": planned_job.label,
                "kind": planned_job.kind,
                "subject": sid,
                "after": planned_job.after_labels,
                "tags": planned_job.tags,
            }
        )
    return jobs, {
        "stages": stages,
        "parallel_subjects": min(effective_parallel, len(subjects)),
    }


def _plan_source(
    kind: str, pm: PathManager, config: Any, subject_ids: list[str], warnings: list[str]
) -> tuple[list[PlanJob], None]:
    from tit.source.config import SourceMode

    jobs: list[PlanJob] = []
    if config.mode == SourceMode.FORWARD:
        subjects = subject_ids or list(config.subject_ids)
        for sid in subjects:
            output_dir = pm.forward(sid)
            exists = _dir_exists(output_dir)
            jobs.append(
                PlanJob(
                    kind=kind,
                    subject=sid,
                    output_dir=output_dir,
                    exists=exists,
                    will_overwrite=exists and config.forward.overwrite,
                )
            )
    else:
        for pair in config.pairs:
            output_dir = pm.sim_fsaverage(pair.subject_id, pair.simulation)
            exists = _dir_exists(output_dir)
            jobs.append(
                PlanJob(
                    kind=kind,
                    subject=pair.subject_id,
                    output_dir=output_dir,
                    exists=exists,
                    will_overwrite=exists,
                )
            )
    return jobs, None


def _plan_nifti_average(
    kind: str, pm: PathManager, config: Any
) -> tuple[list[PlanJob], None]:
    """Mirrors ``tit.stats.nifti_average.main``'s own ``output_dir`` formula exactly."""
    from tit import constants as const

    output_dir = os.path.join(
        pm.project_dir,
        const.DIR_DERIVATIVES,
        const.DIR_TI_TOOLBOX,
        "nifti_average",
        config.output_name,
    )
    exists = _dir_exists(output_dir)
    return [
        PlanJob(
            kind=kind,
            subject="",
            output_dir=output_dir,
            exists=exists,
            will_overwrite=exists,
        )
    ], None


def _plan_nilearn(
    kind: str, pm: PathManager, config: Any
) -> tuple[list[PlanJob], None]:
    """Mirrors ``tit.plotting.nilearn.__main__.main``'s own ``output_dir`` formula exactly."""
    from tit import constants as const

    output_dir = os.path.join(
        pm.project_dir,
        const.DIR_DERIVATIVES,
        const.DIR_TI_TOOLBOX,
        "nilearn_visuals",
        config.subdir_name,
    )
    exists = _dir_exists(output_dir)
    return [
        PlanJob(
            kind=kind,
            subject="",
            output_dir=output_dir,
            exists=exists,
            will_overwrite=exists,
        )
    ], None


def _plan_stats(kind: str, pm: PathManager, config: Any) -> tuple[list[PlanJob], None]:
    from tit.stats.config import GroupComparisonConfig

    analysis_type = (
        "group_comparison"
        if isinstance(config, GroupComparisonConfig)
        else "correlation"
    )
    output_dir = pm.stats_output(analysis_type, config.analysis_name)
    exists = _dir_exists(output_dir)
    return [
        PlanJob(
            kind=kind,
            subject="",
            output_dir=output_dir,
            exists=exists,
            will_overwrite=exists,
        )
    ], None


def _plan_blender(
    kind: str, config: Any, warnings: list[str]
) -> tuple[list[PlanJob], None]:
    output_dir = getattr(config, "output_dir", None) or ""
    if not output_dir:
        warnings.append(
            "blender output_dir not set on the config; tit.blender resolves it internally "
            "at run time (needs bpy/trimesh, not importable outside the SimNIBS container) "
            "so it cannot be previewed here"
        )
    exists = _dir_exists(output_dir)
    return [
        PlanJob(
            kind=kind,
            subject=config.subject_id,
            output_dir=output_dir,
            exists=exists,
            will_overwrite=exists,
        )
    ], None


@router.post(
    "/api/plan/{kind}",
    response_model=PlanResult,
    summary="Resolve what running this config would do (outputs, overwrite conflicts, "
    "lock waits, cost)",
)
def plan(kind: str, body: PlanRequest) -> PlanResult:
    from tit.config_io import deserialize_config

    if kind not in ALL_KINDS:
        raise HTTPException(status_code=404, detail=f"unknown kind: {kind}")

    warnings: list[str] = []

    try:
        cls = cls_for(kind, body.config)
    except KindNotConfigurable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if cls is None:
        warnings.append(
            f"kind={kind!r} has no config schema yet; nothing can be planned"
        )
        return PlanResult(
            jobs=[],
            lock_conflicts=[],
            cost=PlanCost(cpus=0.0, mem_gb=0.0, eta_minutes=None),
            warnings=warnings,
            resolved=None,
        )

    config_dict = body.config
    if kind == "pre":
        from tit.pre.config import migrate_legacy_keys

        config_dict = migrate_legacy_keys(config_dict, warnings=warnings)

    try:
        config = deserialize_config(cls, config_dict)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    pm = get_path_manager()
    subject_ids = list(body.subject_ids or [])

    if kind == "pre":
        jobs, resolved = _plan_pre(
            pm, config, subject_ids, warnings, parallel_subjects=body.parallel_subjects
        )
    elif kind == "sim":
        jobs, resolved = _plan_sim(
            kind,
            pm,
            config,
            body.config,
            subject_ids,
            warnings,
            montage_sources_field=body.montage_sources,
        )
    elif kind in ("flex", "flex_adaptive", "flex_pareto"):
        jobs, resolved = _plan_flex(kind, pm, config, subject_ids, warnings)
    elif kind == "ex":
        jobs, resolved = _plan_ex(kind, pm, config, subject_ids, warnings)
    elif kind == "mex":
        jobs, resolved = _plan_mex(kind, pm, config, subject_ids, warnings)
    elif kind == "leadfield":
        jobs, resolved = _plan_leadfield(kind, pm, config, subject_ids, warnings)
    elif kind == "analyzer":
        jobs, resolved = _plan_analyzer(kind, pm, config, subject_ids, warnings)
    elif kind == "source":
        jobs, resolved = _plan_source(kind, pm, config, subject_ids, warnings)
    elif kind == "stats":
        jobs, resolved = _plan_stats(kind, pm, config)
    elif kind == "blender":
        jobs, resolved = _plan_blender(kind, config, warnings)
    elif kind == "nifti_average":
        jobs, resolved = _plan_nifti_average(kind, pm, config)
    elif kind == "nilearn":
        jobs, resolved = _plan_nilearn(kind, pm, config)
    else:  # pragma: no cover - ALL_KINDS/NO_SCHEMA_KINDS covers everything else
        jobs, resolved = [], None

    parallel = 1
    if kind == "pre" and resolved is not None:
        parallel = resolved.get("parallel_subjects", 1)
    cost = _plan_cost(
        kind, body.config, resolved=resolved, jobs=jobs, parallel=parallel
    )
    if kind == "pre" and resolved is not None:
        # A `pre` plan is N per-subject DAGs; resolved["parallel_subjects"] (see _plan_pre)
        # is how many of them the matching `POST /api/jobs/groups` call would run at once,
        # so the previewed cost -- one representative stage's cost times that concurrency --
        # matches what the group would actually consume, not just one lone stage's footprint.
        concurrency = resolved.get("parallel_subjects", 1)
        cost = PlanCost(
            cpus=cost.cpus * concurrency,
            mem_gb=cost.mem_gb * concurrency,
            eta_minutes=cost.eta_minutes,
            system=cost.system,
        )
    lock_conflicts = _plan_lock_conflicts(
        kind, subject_ids or [j.subject for j in jobs if j.subject], body.config
    )

    return PlanResult(
        jobs=jobs,
        lock_conflicts=lock_conflicts,
        cost=cost,
        warnings=warnings,
        resolved=resolved,
    )
