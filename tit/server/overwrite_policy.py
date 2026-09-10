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
    """Reject replacement of existing outputs while project overrides are disabled.

    Use the same filesystem-backed output resolution as the run receipt. Flags alone
    do not imply data loss: a first run remains valid even if its config permits replacement.
    """
    from tit.server.routes.plan import ALL_KINDS, PlanRequest, plan
    from tit.server.routes.settings import _load_project_settings

    allowed = bool(_load_project_settings().get("allow_unsafe_overrides", False))
    if allowed and (kind != "sim" or overwrite):
        return
    # Reports have unique job output paths and no configurable plan. Preprocessing
    # without replace skips or refuses existing stages instead of deleting them.
    if kind not in ALL_KINDS:
        return
    if kind == "pre":
        if not config.get("replace_existing_outputs", False):
            return
        # The receipt's stage directories are coarser than the destructive targets
        # (DTI shares m2m with CHARM). Use the runner's exact deletion inventory.
        from tit.paths import get_path_manager
        from tit.pre.preflight import (
            existing_outputs_for_step,
            selected_preprocessing_steps,
        )

        steps = selected_preprocessing_steps(
            run_freesurfer=bool(config.get("run_freesurfer", False)),
            freesurfer_recon_all=bool(config.get("freesurfer_recon_all", True)),
            freesurfer_subregions=config.get("freesurfer_subregions", []),
            **{
                flag: bool(config.get(flag, False))
                for flag in (
                    "convert_dicom",
                    "create_m2m",
                    "run_fastsurfer",
                    "run_qsiprep",
                    "run_qsirecon",
                    "extract_dti",
                )
            },
        )
        conflicts = [
            str(output.path)
            for sid in subject_ids or config.get("subject_ids", [])
            for step in steps
            for output in existing_outputs_for_step(
                get_path_manager().project_dir, sid, step
            )
        ]
    else:
        receipt = plan(
            kind,
            PlanRequest(config=config, subject_ids=subject_ids, overwrite=overwrite),
        )
        conflicts = [job.output_dir for job in receipt.jobs if job.will_overwrite]
    if conflicts:
        if allowed:
            raise HTTPException(
                status_code=409,
                detail="Simulation outputs already exist. Explicit overwrite confirmation is required: "
                + "; ".join(conflicts),
            )
        raise HTTPException(
            status_code=403,
            detail=(
                "Overwriting existing outputs is disabled for this project. Enable "
                "Allow unsafe overrides in Settings before replacing: "
                + "; ".join(conflicts)
            ),
        )
