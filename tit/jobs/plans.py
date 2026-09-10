"""Job-group plans: the preprocessing DAG and the generic per-subject group (TODO.md §2.3, ``G1``-``G6``).

Pure data: this module only *describes* the DAG a ``PreprocessConfig`` + subject list would
produce, as a flat list of :class:`tit.jobs.spec.PlannedJob`. It never touches the job registry,
the scheduler, or the filesystem beyond what :func:`tit.config_io.serialize_config` needs (an
active :class:`~tit.paths.PathManager`, for the ``project_dir`` it injects into every stage's
config) -- callers submit the plan themselves (``POST /api/jobs/groups``, owned by B1, resolves
each ``PlannedJob.label``/``after_labels`` to a real job id in topological order), and notebook
users can call this directly to inspect or hand-tune the DAG before submitting it job by job.

See Also
--------
tit.jobs.spec.PlannedJob : The node type this module builds.
tit.pre.structural.run_pipeline : Consumes exactly the flags each stage's config sets.
tit.server.routes.plan : Calls this for ``POST /api/plan/pre``.
"""

from __future__ import annotations

from dataclasses import replace

from tit.config_io import serialize_config
from tit.jobs.spec import PlannedJob
from tit.pre.config import PreprocessConfig

__all__ = ["GROUP_KINDS", "plan_per_subject", "plan_preprocessing"]

#: Job kinds ``POST /api/jobs/groups`` can submit as a per-subject group (R3). ``pre`` expands
#: into the G1-G6/report DAG below; every other kind is one independent job per subject (per
#: ``(subject, config)`` entry, for a page like the Simulator that runs several montages for the
#: same subject), built by :func:`plan_per_subject`.
GROUP_KINDS: tuple[str, ...] = (
    "pre",
    "sim",
    "flex",
    "flex_adaptive",
    "flex_pareto",
    "ex",
    "mex",
)

#: kind -> the :data:`tit.config_io.CONFIG_CLASS_REGISTRY` key its config deserializes as
#: (resolved through :func:`tit.config_io.resolve_config_class`).
#: Deliberately a copy of the same rows in ``tit.server.routes.validate.SIMPLE_KIND_CLASS``
#: rather than an import: :mod:`tit.jobs` must not depend on :mod:`tit.server`. The two are
#: kept honest by ``tests/test_jobs_plans.py::test_group_kind_classes_match_validate``.
_KIND_CONFIG_CLASS: dict[str, str] = {
    "sim": "SimulationConfig",
    "flex": "FlexConfig",
    "flex_adaptive": "FlexConfig",
    "flex_pareto": "FlexConfig",
    "ex": "ExConfig",
    "mex": "MExConfig",
}


def plan_per_subject(
    kind: str,
    subject_configs: list[tuple[str, dict]],
    *,
    tags: list[str] | None = None,
    overwrite: bool = False,
) -> list[PlannedJob]:
    """One independent :class:`PlannedJob` per ``(subject_id, config)`` entry.

    The generic half of ``POST /api/jobs/groups`` (R3): unlike ``pre``, a ``sim``/``flex``/
    ``ex``/``mex`` group has no intra-subject DAG -- every job is submittable at once and the
    scheduler's ``group_cap`` (``JobGroupRequest.parallel_subjects``) is the only thing deciding
    how many actually run together.

    Each entry's config is round-tripped through the kind's config dataclass with
    ``subject_id`` **forced to that entry's subject**, so a generated config can only ever carry
    its own subject id no matter what the caller sent (the gate's config-isolation check).

    Parameters
    ----------
    kind : str
        One of :data:`GROUP_KINDS` other than ``"pre"``.
    subject_configs : list of (str, dict)
        ``(subject_id, serialized config)`` pairs, in submission order. One subject may appear
        more than once (the Simulator's one job per ``(subject, montage)``).
    tags : list of str, optional
        Tags copied onto every planned job.
    overwrite : bool, optional
        Replace existing output instead of skipping it; copied onto every planned job.

    Raises
    ------
    ValueError
        Unknown/unsupported *kind*, or a config that does not deserialize for it.
    """
    if kind not in _KIND_CONFIG_CLASS:
        raise ValueError(
            f"kind {kind!r} cannot be submitted as a per-subject group "
            f"(expected one of {tuple(_KIND_CONFIG_CLASS)})"
        )
    # Lazy: tit.config_io imports tit.opt.config, whose package __init__ pulls in SimNIBS.
    from tit.config_io import (
        deserialize_config,
        resolve_config_class,
        serialize_config,
    )

    cls = resolve_config_class(_KIND_CONFIG_CLASS[kind])
    jobs: list[PlannedJob] = []
    for index, (subject_id, config) in enumerate(subject_configs):
        narrowed = {**config, "subject_id": subject_id}
        resolved = serialize_config(deserialize_config(cls, narrowed))
        if resolved.get("subject_id") != subject_id:  # pragma: no cover - defensive
            raise ValueError(
                f"config for {subject_id!r} resolved to subject_id "
                f"{resolved.get('subject_id')!r}"
            )
        jobs.append(
            PlannedJob(
                label=f"{subject_id}:{kind}:{index}",
                kind=kind,
                config=resolved,
                subject_ids=[subject_id],
                tags=list(tags or []),
                overwrite=overwrite,
            )
        )
    return jobs


#: Every ``PreprocessConfig`` step flag. A stage's config is *config* with all of these forced
#: to False except the ones that stage itself runs, so each stage is independently submittable.
_STAGE_FLAGS = (
    "convert_dicom",
    "run_fastsurfer",
    "run_freesurfer",
    "create_m2m",
    "run_tissue_analysis",
    "run_qsiprep",
    "run_qsirecon",
    "extract_dti",
)


def _stage_config(config: PreprocessConfig, subject_id: str, **flags: bool) -> dict:
    """One stage's serialized config: *config* narrowed to one subject and one step."""
    overrides = dict.fromkeys(_STAGE_FLAGS, False)
    overrides.update(flags)
    stage_config = replace(config, subject_ids=[subject_id], **overrides)
    return serialize_config(stage_config)


def plan_preprocessing(
    config: PreprocessConfig, subject_ids: list[str]
) -> list[PlannedJob]:
    """Build the per-subject preprocessing job DAG.

    Stage groups, in dependency order per subject (a stage is only planned when its
    ``PreprocessConfig`` flag is set):

    - ``G1`` = DICOM-to-NIfTI conversion (``convert_dicom``)
    - ``G2a`` = SimNIBS ``charm`` + ``subject_atlas`` (``create_m2m``), after ``G1``
    - ``G2b`` = FastSurfer ``--seg_only`` deep segmentation (``run_fastsurfer``), after
      ``G1`` -- it reads the raw BIDS T1w, so it needs nothing from ``G2a`` and the two
      run in parallel
    - ``G2c`` = optional FreeSurfer recon-all/subregions, after ``G1``
    - ``G3`` = tissue-volume/thickness analysis (``run_tissue_analysis``), after ``G2a``
    - ``G4`` = QSIPrep (``run_qsiprep``), after ``G1``
    - ``G5`` = QSIRecon (``run_qsirecon``), after ``G4``
    - ``G6`` = DTI tensor extraction (``extract_dti``), after ``G5`` and ``G2a``
    A report is **not** a stage and never a job of its own. Every stage job writes its
    own HTML report as a side effect of :func:`tit.pre.structural.run_pipeline`, and the
    job manager folds the group's stages into one consolidated per-subject report as a
    post-success attachment of the last stage job to finish for that subject (see
    :meth:`tit.jobs.manager.JobManager._attach_pre_report`) -- with no job record, no
    plan row, no cost and no ETA line of its own.

    Each stage job's config is *config* with every step flag except its own forced to
    ``False`` and ``subject_ids`` narrowed to the one subject -- consistent with
    :func:`tit.pre.structural.run_pipeline` accepting exactly these flags, and letting
    ``G1``/``G2a``/``G2b``/``G4`` (all four have no unmet dependency once ``G1`` is done, or
    none at all) run in parallel once the scheduler admits them. ``skip_existing_outputs`` /
    ``replace_existing_outputs`` are global policy flags, not stage flags, and are carried
    onto every stage's config unchanged.

    Parameters
    ----------
    config : PreprocessConfig
        The full multi-flag request as built by the UI or a notebook. Its own
        ``subject_ids`` is not read -- see *subject_ids* below.
    subject_ids : list of str
        Subjects to plan for. Kept separate from ``config.subject_ids`` so a caller can
        plan for a batch chosen after the rest of *config* is built (e.g. a group picked
        in the UI).

    Returns
    -------
    list of PlannedJob
        Flattened across every subject, most-upstream stage first. Empty for a subject
        with no step flags set at all (no jobs, no report).

    See Also
    --------
    tit.jobs.spec.PlannedJob : ``label``/``after_labels`` are plan-scoped; the real job
        manager resolves them to job ids at submission time.
    """
    jobs: list[PlannedJob] = []

    for subject_id in subject_ids:
        subject_jobs: list[PlannedJob] = []

        g1 = None
        if config.convert_dicom:
            g1 = PlannedJob(
                label=f"{subject_id}:G1",
                kind="pre",
                config=_stage_config(config, subject_id, convert_dicom=True),
                subject_ids=[subject_id],
                tags=["G1", "dicom"],
            )
            subject_jobs.append(g1)

        g2a = None
        if config.create_m2m:
            g2a = PlannedJob(
                label=f"{subject_id}:G2a",
                kind="pre",
                config=_stage_config(config, subject_id, create_m2m=True),
                subject_ids=[subject_id],
                after_labels=[g1.label] if g1 else [],
                tags=["G2a", "charm"],
            )
            subject_jobs.append(g2a)

        g2b = None
        if config.run_fastsurfer:
            g2b = PlannedJob(
                label=f"{subject_id}:G2b",
                kind="pre",
                config=_stage_config(config, subject_id, run_fastsurfer=True),
                subject_ids=[subject_id],
                after_labels=[g1.label] if g1 else [],
                tags=["G2b", "fastsurfer"],
            )
            subject_jobs.append(g2b)

        if config.run_freesurfer:
            subject_jobs.append(
                PlannedJob(
                    label=f"{subject_id}:G2c",
                    kind="pre",
                    config=_stage_config(config, subject_id, run_freesurfer=True),
                    subject_ids=[subject_id],
                    after_labels=[g1.label] if g1 else [],
                    tags=["G2c", "freesurfer"],
                )
            )

        g3 = None
        if config.run_tissue_analysis:
            g3 = PlannedJob(
                label=f"{subject_id}:G3",
                kind="pre",
                config=_stage_config(config, subject_id, run_tissue_analysis=True),
                subject_ids=[subject_id],
                after_labels=[g2a.label] if g2a else [],
                tags=["G3", "tissue"],
            )
            subject_jobs.append(g3)

        g4 = None
        if config.run_qsiprep:
            g4 = PlannedJob(
                label=f"{subject_id}:G4",
                kind="pre",
                config=_stage_config(config, subject_id, run_qsiprep=True),
                subject_ids=[subject_id],
                after_labels=[g1.label] if g1 else [],
                tags=["G4", "qsiprep"],
            )
            subject_jobs.append(g4)

        g5 = None
        if config.run_qsirecon:
            g5 = PlannedJob(
                label=f"{subject_id}:G5",
                kind="pre",
                config=_stage_config(config, subject_id, run_qsirecon=True),
                subject_ids=[subject_id],
                after_labels=[g4.label] if g4 else [],
                tags=["G5", "qsirecon"],
            )
            subject_jobs.append(g5)

        if config.extract_dti:
            after = [j.label for j in (g5, g2a) if j is not None]
            g6 = PlannedJob(
                label=f"{subject_id}:G6",
                kind="pre",
                config=_stage_config(config, subject_id, extract_dti=True),
                subject_ids=[subject_id],
                after_labels=after,
                tags=["G6", "dti"],
            )
            subject_jobs.append(g6)

        # No trailing report job: the consolidated per-subject report is an attachment
        # the job manager produces after the last stage job for this subject succeeds
        # (JobManager._attach_pre_report), not a job of its own.
        jobs.extend(subject_jobs)

    return jobs
