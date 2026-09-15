"""Project overwrite permission at HTTP submission boundaries."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def check_overwrite_permission(
    kind: str,
    config: dict[str, Any],
    subject_ids: list[str],
    *,
    overwrite: bool = False,
) -> None:
    """Reject replacement of existing outputs without explicit confirmation.

    Use the same filesystem-backed output resolution as the run receipt. Flags alone
    do not imply data loss: a first run remains valid even if its config permits replacement.
    """
    from tit.server.routes.plan import ALL_KINDS, PlanRequest, plan

    # Reports have unique job output paths and no configurable plan.
    if kind not in ALL_KINDS:
        return
    if kind == "pre":
        # Preprocessing carries its own explicit replace decision in the config
        # (the same "Replace and rerun" choice sim's `overwrite` request flag makes) --
        # skip/refuse existing stages instead of deleting them when it is unset, and treat
        # it as sufficient confirmation, exactly like sim's `overwrite` flag, when it is set.
        return
    if overwrite:
        return
    receipt = plan(
        kind,
        PlanRequest(config=config, subject_ids=subject_ids, overwrite=overwrite),
    )
    conflicts = [job.output_dir for job in receipt.jobs if job.will_overwrite]
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail="Simulation outputs already exist. Explicit overwrite confirmation is required: "
            + "; ".join(conflicts),
        )
