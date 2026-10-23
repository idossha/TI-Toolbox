"""The one folder a job's results live in (``JobDetail.output_dir``).

The desktop's folder buttons (the run pages' Terminal pane, the Jobs page) open this folder. It
used to be guessed from the job's registered artifacts, which a runner reports only when it
finishes: while a job ran, the button fell back to ``code/ti-toolbox/jobs/<id>/`` (the job's own
bookkeeping record), and a finished simulation or search, whose first artifact is the run folder
itself, opened that folder's parent.

The answer, in order:

1. the folder the runner itself registered, as a ``dir`` artifact (a simulation registers its
   ``Simulations/<montage>`` folder, a flex-search its run folder);
2. the folder ``POST /api/plan/{kind}`` names for the job's own spec
   (:func:`tit.server.routes.plan.plan_jobs`, the resolver the run pages' plan uses), so a job
   that is still running or queued is answered too. A flex, ex or mEx search whose run folder
   the config leaves to the runner (a timestamp the plan can only preview) has no planned
   answer;
3. the directory of the first file the runner registered (a search's ``results.csv``).

``None`` when there is no single folder: a job that registered nothing and plans nothing (a
pre-processing group), a simulation of several montages, a job whose folder does not exist yet
or is outside the project. The caller then falls back to the job's own folder.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import HTTPException

from tit.paths import get_path_manager, is_within

logger = logging.getLogger(__name__)

#: The config field naming an optimisation run's folder. Unset, the plan previews a timestamp
#: and the run picks a fresh one when it starts, so two previews agreeing proves nothing.
RUN_FOLDER_FIELD = {
    "ex": "run_name",
    "mex": "run_name",
    "flex": "output_folder",
    "flex_adaptive": "output_folder",
    "flex_pareto": "output_folder",
}


def _registered_folder(artifacts: list[dict[str, Any]]) -> tuple[bool, str | None]:
    """``(claimed, folder)``: whether the runner registered a ``dir``, and the one it named.

    Two different ``dir`` artifacts (a simulation of two montages) are a claim with no single
    folder: ``claimed`` is True and ``folder`` None, so the caller does not guess one.
    """
    folders = list(
        dict.fromkeys(
            a["path"] for a in artifacts if a.get("kind") == "dir" and a.get("path")
        )
    )
    if not folders:
        return False, None
    return True, folders[0] if len(folders) == 1 else None


def _planned_folder(
    kind: str, config: dict[str, Any], subject_ids: list[str]
) -> str | None:
    """The one folder the plan route names for this spec, else ``None``."""
    from tit.server.routes.plan import PlanRequest, plan_jobs

    run_folder = RUN_FOLDER_FIELD.get(kind)
    if run_folder and not config.get(run_folder):
        return None
    try:
        planned = plan_jobs(
            kind, PlanRequest(config=config, subject_ids=list(subject_ids))
        )
    except (HTTPException, ValueError, TypeError, KeyError, OSError) as exc:
        logger.debug("no planned output folder for a %s job: %s", kind, exc)
        return None
    if planned is None:
        return None
    jobs = planned[0]
    # A group analysis plans each subject's folder and one project-level summary folder
    # (``subject == ""``); the job is the latter. Otherwise every planned job is the job's own.
    own = [job for job in jobs if not job.subject] or jobs
    folders = list(dict.fromkeys(job.output_dir for job in own if job.output_dir))
    if len(folders) != 1:
        return None
    folder = folders[0]
    # A leadfield job plans the file it writes; its folder is the one holding it.
    return os.path.dirname(folder) if os.path.isfile(folder) else folder


def job_output_dir(
    kind: str,
    config: dict[str, Any],
    subject_ids: list[str],
    artifacts: list[dict[str, Any]],
) -> str | None:
    """The folder holding the job's results, or ``None`` (see the module docstring).

    Only a folder that exists inside the project is returned, so a button built on it never
    opens a path outside the project or one a run has not created yet.
    """
    claimed, folder = _registered_folder(artifacts)
    if not claimed:
        folder = _planned_folder(kind, config, subject_ids)
    if not claimed and folder is None:
        first = next((a["path"] for a in artifacts if a.get("path")), None)
        folder = os.path.dirname(first) if first else None
    if not folder:
        return None
    root = get_path_manager().project_dir
    if root and not is_within(root, folder):
        return None
    return folder if os.path.isdir(folder) else None
