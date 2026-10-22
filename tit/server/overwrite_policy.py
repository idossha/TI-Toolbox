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


def check_overwrite_permission(
    kind: str,
    config: dict[str, Any],
    subject_ids: list[str],
    *,
    overwrite: bool = False,
) -> None:
    """Reject outputs outside the project (422) and, without explicit confirmation, the
    replacement of existing ones (409)."""
    refuse_unconfirmed_overwrite(
        kind,
        planned_outputs(kind, config, subject_ids, overwrite=overwrite),
        overwrite=overwrite,
    )
