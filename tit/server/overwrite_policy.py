"""Project overwrite permission at HTTP submission boundaries."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def planned_outputs(
    kind: str,
    config: dict[str, Any],
    subject_ids: list[str],
    *,
    overwrite: bool = False,
) -> list[Any]:
    """The run receipt's jobs (``PlanJob``) for one submission, or ``[]`` for a kind it skips.

    Uses the same filesystem-backed output resolution as the run receipt
    (:func:`tit.server.routes.plan.plan`), which refuses an output outside the project (422).
    """
    from tit.server.routes.plan import ALL_KINDS, PlanRequest, plan

    # Reports have unique job output paths and no configurable plan.
    if kind not in ALL_KINDS:
        return []
    if kind == "pre":
        # Preprocessing carries its own explicit replace decision in the config
        # (the same "Replace and rerun" choice sim's `overwrite` request flag makes) --
        # skip/refuse existing stages instead of deleting them when it is unset, and treat
        # it as sufficient confirmation, exactly like sim's `overwrite` flag, when it is set.
        return []
    receipt = plan(
        kind,
        PlanRequest(config=config, subject_ids=subject_ids, overwrite=overwrite),
    )
    return list(receipt.jobs)


def refuse_unconfirmed_overwrite(
    kind: str, jobs: list[Any], *, overwrite: bool = False
) -> None:
    """Without explicit confirmation, refuse (409) replacing an output that already exists.

    Flags alone do not imply data loss: a first run remains valid even if its config permits
    replacement.
    """
    if overwrite:
        return
    conflicts = [job.output_dir for job in jobs if job.will_overwrite]
    if conflicts:
        raise HTTPException(
            status_code=409,
            # Every kind shares this check, so the sentence names the kind rather than
            # calling an analysis (or a search) a simulation.
            detail=f"Outputs of this {kind} job already exist. Explicit overwrite "
            "confirmation is required: " + "; ".join(conflicts),
        )


def _named_folders(kind: str, config: dict[str, Any], jobs: list[Any]) -> set[str]:
    """The output folders *jobs* plan, or none when the run folder is the runner's to pick (an
    unnamed search previews a timestamp it will not use)."""
    from tit.server.job_outputs import RUN_FOLDER_FIELD

    field = RUN_FOLDER_FIELD.get(kind)
    if field and not config.get(field):
        return set()
    return {job.output_dir for job in jobs if job.output_dir}


def refuse_outputs_of_active_jobs(
    manager: Any, planned: list[tuple[str, dict[str, Any], list[Any]]]
) -> None:
    """HTTP 422 when a ``(kind, config, plan jobs)`` of *planned* writes a folder a queued or
    running job will write.

    The overwrite check reads the disk, where a queued job has written nothing yet, and only
    the simulator honours the overwrite flag, so a second job into one folder (a double-pressed
    Run, a re-pressed search) replaced the first's results. No overwrite answer makes that
    safe, so this is a 422, not the 409 question.
    """
    wanted = set().union(*(_named_folders(k, c, jobs) for k, c, jobs in planned))
    if not wanted:
        return
    for job in manager.list_jobs():
        if job["state"] not in ("queued", "running"):
            continue
        spec = (manager.get_detail(job["id"]) or {}).get("spec") or {}
        try:
            outputs = planned_outputs(spec["kind"], spec["config"], spec["subject_ids"])
        except (HTTPException, ValueError, TypeError, KeyError, OSError):
            continue  # a spec the plan cannot read names no folder
        taken = wanted & _named_folders(spec["kind"], spec["config"], outputs)
        if taken:
            raise HTTPException(
                status_code=422,
                detail=f"The {job['state']} {job['kind']} job {job['id']} will write "
                f"{', '.join(sorted(taken))}. Wait for it to finish (or cancel it), or "
                "choose another name.",
            )


def check_overwrite_permission(
    kind: str,
    config: dict[str, Any],
    subject_ids: list[str],
    *,
    overwrite: bool = False,
    manager: Any = None,
) -> None:
    """Reject outputs outside the project or planned by one of *manager*'s queued or running
    jobs (422) and, without explicit confirmation, the replacement of existing ones (409).
    Without a *manager* there is no queue to consult and only the disk is checked."""
    outputs = planned_outputs(kind, config, subject_ids, overwrite=overwrite)
    if manager is not None:
        refuse_outputs_of_active_jobs(manager, [(kind, config, outputs)])
    refuse_unconfirmed_overwrite(kind, outputs, overwrite=overwrite)
