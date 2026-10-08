"""Agent proposals: a plan an AI agent proposes, the user approves in the app, the server runs.

A proposal is ``<project>/code/ti-toolbox/proposals/<id>.json`` (ARCHITECTURE §6): a title, a
rationale and ordered steps ``{id, kind, config, subject_ids, after, note, overwrite}``. Its
lifecycle is ``pending`` -> ``approved`` | ``rejected``; while pending the user may edit a step
(``edit_step``), and what is approved is what runs. ``proposed_steps`` keeps the agent's version.

**The server queues approved steps itself.** On approval every step with no ``after`` is queued
at once, with ``created_by`` the proposer's and a ``proposal:<id>`` tag; a step with ``after``
is queued by this module the moment every job of every step it names has succeeded, and marked
``skipped`` when one of them did not. Dependent steps are deferred rather than queued up front
with job-level ``after``, because submission refuses a job whose inputs are not on disk yet
(``tit.jobs.preflight``: a flex step after a ``pre`` step has no head model at approval time) and
a ``sim_from_flex`` step has no electrodes until its flex run exists. ``sim_from_flex`` names
either an earlier flex step (``config.flex_step``) or a finished run (``config.flex_run``); its
montage and currents come from :func:`tit.sim.montage_sources.resolve_flex_simulation`, the same
function ``POST /api/sim-from-flex`` serves.

Progress: a watcher thread per job manager follows its status stream and advances approved
proposals whenever a job finishes; every record change is published to ``/ws/jobs`` subscribers
as ``{"type": "proposal", "proposal": ...}``. Step and proposal states are derived from the
step's jobs at read time, never stored.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import queue
import re
import threading
import time
from typing import Any

from fastapi import HTTPException

from tit.jobs.registry import _atomic_write_json, _storage_path
from tit.jobs.spec import (
    CREATED_BY_VALUES,
    JOB_KINDS,
    TERMINAL_STATES,
    new_job_id,
    utcnow_iso,
)
from tit.paths import is_valid_subject_id
from tit.server.app_defaults import with_app_defaults

logger = logging.getLogger(__name__)

SIM_FROM_FLEX = "sim_from_flex"
STEP_KINDS: tuple[str, ...] = (*JOB_KINDS, SIM_FROM_FLEX)
FLEX_KINDS = ("flex", "flex_adaptive", "flex_pareto")
#: Keys of a ``sim_from_flex`` config that are not ``SimulationConfig`` fields.
FLEX_SOURCE_KEYS = ("flex_step", "flex_run", "eeg_net")
FAILED_STATES = frozenset({"failed", "cancelled", "skipped", "lost"})
STEP_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
MAX_STEPS = 20

#: One lock for every proposal read-modify-write and the submissions it triggers, so a route
#: and the watcher can never queue the same step twice.
# ponytail: global lock; per-proposal locks if many agents ever propose at once.
_LOCK = threading.RLock()
_SUBSCRIBERS: list[queue.Queue[dict[str, Any]]] = []
_WATCHED: set[int] = set()


# -- storage ----------------------------------------------------------------------------------


def proposals_root(project_dir: str) -> str:
    return _storage_path(
        project_dir, os.path.join(project_dir, "code", "ti-toolbox", "proposals")
    )


def _path(project_dir: str, proposal_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{16}", proposal_id or ""):
        raise HTTPException(status_code=404, detail=f"unknown proposal: {proposal_id}")
    return _storage_path(
        project_dir, os.path.join(proposals_root(project_dir), f"{proposal_id}.json")
    )


def _load(project_dir: str, proposal_id: str) -> dict[str, Any]:
    try:
        with open(_path(project_dir, proposal_id), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=404, detail=f"unknown proposal: {proposal_id}"
        ) from exc


def _save(project_dir: str, record: dict[str, Any]) -> None:
    record["updated_at"] = utcnow_iso()
    _atomic_write_json(_path(project_dir, record["id"]), record)


def _all(project_dir: str) -> list[dict[str, Any]]:
    # ponytail: proposals are never pruned; a few KB each, add retention if they pile up.
    try:
        names = os.listdir(proposals_root(project_dir))
    except OSError:
        return []
    out = []
    for name in names:
        if name.endswith(".json"):
            with contextlib.suppress(HTTPException):
                out.append(_load(project_dir, name[: -len(".json")]))
    return out


# -- validation -------------------------------------------------------------------------------


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _text(value: Any, name: str, limit: int, required: bool = False) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise _bad(f"{name} must be a{' non-empty' if required else ''} string")
    if len(value) > limit:
        raise _bad(f"{name} is longer than {limit} characters")
    return value.strip()


def _flex_run_name(config: dict[str, Any]) -> str:
    """A flex step's run folder name, assigned now when the agent left it empty, so the step's
    output folder (and a later ``sim_from_flex``'s source) is known before anything runs.
    """
    name = str(config.get("output_folder") or "").strip()
    if not name:
        return time.strftime("%Y%m%d_%H%M%S") + "_agent"
    if not name.startswith("/") and (
        "/" in name or "\\" in name or name in (".", "..")
    ):
        raise _bad("output_folder must be a run name without separators, or absolute")
    return name


def _checked_step(raw: Any, earlier: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise _bad("each step must be an object")
    step_id = raw.get("id")
    if not isinstance(step_id, str) or not STEP_ID_RE.match(step_id):
        raise _bad("step id must be 1-32 letters, digits, '_' or '-'")
    if step_id in earlier:
        raise _bad(f"duplicate step id {step_id!r}")
    kind = raw.get("kind")
    if kind not in STEP_KINDS:
        raise _bad(f"step {step_id}: kind must be one of {list(STEP_KINDS)}")
    config = raw.get("config")
    if not isinstance(config, dict):
        raise _bad(f"step {step_id}: config must be an object")
    subjects = raw.get("subject_ids")
    if not isinstance(subjects, list) or not subjects:
        raise _bad(f"step {step_id}: subject_ids must be a non-empty array")
    for sid in subjects:
        if not is_valid_subject_id(sid):
            raise _bad(f"step {step_id}: invalid subject id {sid!r}")
    after = raw.get("after") or []
    if not isinstance(after, list) or any(a not in earlier for a in after):
        raise _bad(
            f"step {step_id}: after must name earlier steps ({sorted(earlier) or 'none'})"
        )
    # The run pages' defaults under what the agent sent; a sim_from_flex step is a simulation.
    config = with_app_defaults("sim" if kind == SIM_FROM_FLEX else kind, config)
    if kind in FLEX_KINDS:
        config["output_folder"] = _flex_run_name(config)
    if kind == SIM_FROM_FLEX:
        source = config.get("flex_step")
        if bool(source) == bool(config.get("flex_run")):
            raise _bad(
                f"step {step_id}: sim_from_flex needs exactly one of config.flex_step (an "
                "earlier flex step) or config.flex_run (a finished run's name)"
            )
        if source:
            parent = earlier.get(source)
            if parent is None or parent["kind"] not in FLEX_KINDS:
                raise _bad(
                    f"step {step_id}: flex_step {source!r} is not an earlier flex step"
                )
            if set(subjects) - set(parent["subject_ids"]):
                raise _bad(f"step {step_id}: subjects must be among step {source}'s")
            if source not in after:
                after = [*after, source]
    return {
        "id": step_id,
        "kind": kind,
        "config": config,
        "subject_ids": list(subjects),
        "after": list(after),
        "note": _text(raw.get("note"), f"step {step_id}: note", 2000),
        "overwrite": raw.get("overwrite") is True,
        "job_ids": [],
        "error": None,
        "skipped": None,
        "resolved": None,
        "plan": None,
    }


def _checked_steps(raw_steps: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_steps, list) or not raw_steps:
        raise _bad("steps must be a non-empty array")
    if len(raw_steps) > MAX_STEPS:
        raise _bad(f"at most {MAX_STEPS} steps per proposal")
    steps: dict[str, dict[str, Any]] = {}
    for raw in raw_steps:
        step = _checked_step(raw, steps)
        steps[step["id"]] = step
    return list(steps.values())


# -- planning: what the card shows ------------------------------------------------------------


def _pm():
    from tit.paths import get_path_manager

    return get_path_manager()


def _flex_folder(name: str, subject_id: str) -> str:
    return (
        name
        if name.startswith("/")
        else os.path.join(_pm().flex_search(subject_id), name)
    )


def _entries(
    record: dict[str, Any], step: dict[str, Any]
) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
    """``(job kind, [(subject, config)])`` for *step*: ``pre`` is one entry for all subjects,
    a flex step gets each subject's absolute run folder, and a ``sim_from_flex`` step is
    resolved against its flex run now (:class:`ValueError` when that run is not usable).
    """
    kind, config = step["kind"], step["config"]
    if kind == "pre":
        return kind, [("", {**config, "subject_ids": step["subject_ids"]})]
    if kind != SIM_FROM_FLEX:
        entries = []
        for sid in step["subject_ids"]:
            entry = {**config, "subject_id": sid}
            if kind in FLEX_KINDS:
                entry["output_folder"] = _flex_folder(config["output_folder"], sid)
            entries.append((sid, entry))
        return kind, entries

    from tit.sim.montage_sources import resolve_flex_simulation

    base = {k: v for k, v in config.items() if k not in FLEX_SOURCE_KEYS}
    parent = next(
        (s for s in record["steps"] if s["id"] == config.get("flex_step")), None
    )
    entries, resolved = [], {}
    for sid in step["subject_ids"]:
        run = config.get("flex_run")
        if parent is not None:
            run = os.path.basename(_flex_folder(parent["config"]["output_folder"], sid))
        found = resolve_flex_simulation(
            _pm(),
            sid,
            run,
            eeg_net=config.get("eeg_net"),
            intensities=config.get("intensities"),
        )
        resolved[sid] = {k: v for k, v in found.items() if k != "montage"}
        entries.append(
            (
                sid,
                {
                    **base,
                    "subject_id": sid,
                    "montages": [found["montage"]],
                    "intensities": found["intensities"],
                },
            )
        )
    step["resolved"] = resolved
    return "sim", entries


def _plan_step(record: dict[str, Any], step: dict[str, Any], manager: Any) -> None:
    """Fill ``step["plan"]`` from the validate/plan/preflight routes' own functions."""
    from tit.jobs.preflight import preflight
    from tit.server.routes.plan import PlanRequest, plan
    from tit.server.routes.validate import ALL_KINDS, ValidateRequest, validate

    out: dict[str, Any] = {
        "errors": [],
        "missing_inputs": [],
        "outputs": [],
        "will_overwrite": [],
        "eta_minutes": None,
        "warnings": [],
        "deferred": None,
    }
    step["plan"] = out
    if step["kind"] == SIM_FROM_FLEX and step["config"].get("flex_step"):
        source = step["config"]["flex_step"]
        out["deferred"] = (
            f"Electrodes and currents come from step {source}'s flex-search result once it "
            "finishes (the run's mapped net, else its optimised positions)."
        )
        return
    try:
        kind, entries = _entries(record, step)
    except ValueError as exc:
        out["errors"].append(str(exc))
        return
    if kind not in ALL_KINDS:
        return
    eta = 0.0
    for sid, config in entries:
        subjects = [sid] if sid else step["subject_ids"]
        check = validate(kind, ValidateRequest(config=config))
        if not check.ok:
            out["errors"].extend(f"{e.path}: {e.message}" for e in check.errors)
            continue
        if not step[
            "after"
        ]:  # a dependent step's inputs are made by the steps it waits on
            for item in preflight(kind, config, manager.project_dir):
                out["missing_inputs"].append(item.to_dict())
        try:
            result = plan(
                kind,
                PlanRequest(
                    config=config, subject_ids=subjects, overwrite=step["overwrite"]
                ),
            )
        except HTTPException as exc:
            out["errors"].append(str(exc.detail))
            continue
        for job in result.jobs:
            out["outputs"].append(
                {
                    "subject": job.subject,
                    "output_dir": job.output_dir,
                    "exists": job.exists,
                }
            )
            if job.will_overwrite:
                out["will_overwrite"].append(job.output_dir)
        out["warnings"].extend(result.warnings)
        if result.cost.eta_minutes:
            eta += result.cost.eta_minutes
    out["eta_minutes"] = eta or None


# -- derived state ----------------------------------------------------------------------------


def _job_states(step: dict[str, Any], manager: Any) -> list[str]:
    states = []
    for job_id in step["job_ids"]:
        status = manager.get(job_id)
        states.append(status["state"] if status else "lost")
    return states


def _step_state(record: dict[str, Any], step: dict[str, Any], manager: Any) -> str:
    if record["decision"]["state"] != "approved":
        return "proposed"
    if step["error"]:
        return "error"
    if step["skipped"]:
        return "skipped"
    if not step["job_ids"]:
        return "waiting"
    states = _job_states(step, manager)
    if all(s == "succeeded" for s in states):
        return "succeeded"
    if any(s in FAILED_STATES for s in states):
        return "failed"
    return "running" if "running" in states else "queued"


def view(record: dict[str, Any], manager: Any) -> dict[str, Any]:
    """The wire shape (contract ``Proposal``): the record plus derived step/proposal states."""
    out = json.loads(json.dumps(record))
    for step in out["steps"]:
        step["state"] = _step_state(record, step, manager)
    decision = record["decision"]["state"]
    if decision != "approved":
        out["status"] = decision
    else:
        states = [s["state"] for s in out["steps"]]
        if any(s in ("waiting", "queued", "running") for s in states):
            out["status"] = "running"
        elif all(s == "succeeded" for s in states):
            out["status"] = "succeeded"
        else:
            out["status"] = "failed"
    out["edited"] = [
        (s["config"], s["subject_ids"], s["overwrite"]) for s in record["steps"]
    ] != [
        (s["config"], s["subject_ids"], s["overwrite"])
        for s in record["proposed_steps"]
    ]
    return out


# -- pub/sub ----------------------------------------------------------------------------------


def subscribe() -> queue.Queue[dict[str, Any]]:
    q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1000)
    with _LOCK:
        _SUBSCRIBERS.append(q)
    return q


def unsubscribe(q: queue.Queue[dict[str, Any]]) -> None:
    with _LOCK:
        if q in _SUBSCRIBERS:
            _SUBSCRIBERS.remove(q)


def _publish(record: dict[str, Any], manager: Any) -> dict[str, Any]:
    payload = view(record, manager)
    with _LOCK:
        subs = list(_SUBSCRIBERS)
    for q in subs:
        with contextlib.suppress(
            queue.Full
        ):  # a slow socket misses a message, never blocks
            q.put_nowait(payload)
    return payload


# -- lifecycle --------------------------------------------------------------------------------


def create(manager: Any, body: dict[str, Any]) -> dict[str, Any]:
    created_by = body.get("created_by", "agent")
    if created_by not in CREATED_BY_VALUES:
        raise _bad(f"created_by must be one of {list(CREATED_BY_VALUES)}")
    steps = _checked_steps(body.get("steps"))
    record: dict[str, Any] = {
        "id": new_job_id(),
        "title": _text(body.get("title"), "title", 200, required=True),
        "rationale": _text(body.get("rationale"), "rationale", 4000),
        "created_by": created_by,
        "client": _text(body.get("client"), "client", 60) or None,
        "created_at": utcnow_iso(),
        "decision": {"state": "pending", "at": None, "note": None},
        "steps": steps,
        "proposed_steps": [
            {
                k: s[k]
                for k in ("id", "kind", "config", "subject_ids", "after", "overwrite")
            }
            for s in steps
        ],
    }
    for step in steps:
        _plan_step(record, step, manager)
    if (
        body.get("dry_run") is True
    ):  # the agent checks its plan before showing it to the user
        return {**view(record, manager), "status": "draft"}
    with _LOCK:
        _save(manager.project_dir, record)
        return _publish(record, manager)


def list_views(
    manager: Any, status: str | None = None, include_dismissed: bool = False
) -> list[dict[str, Any]]:
    ensure_watcher(manager)
    with _LOCK:
        records = _all(manager.project_dir)
    views = [view(r, manager) for r in records]
    views.sort(key=lambda v: v["created_at"], reverse=True)
    return [
        v
        for v in views
        if (status is None or v["status"] == status)
        and (include_dismissed or not v.get("dismissed_at"))
    ]


def get_view(manager: Any, proposal_id: str) -> dict[str, Any]:
    return view(_load(manager.project_dir, proposal_id), manager)


def _pending(manager: Any, proposal_id: str) -> dict[str, Any]:
    record = _load(manager.project_dir, proposal_id)
    if record["decision"]["state"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"proposal {proposal_id} is already {record['decision']['state']}",
        )
    return record


def _apply_edit(record: dict[str, Any], edit: Any, manager: Any) -> None:
    """Replace a pending step's config / subjects / overwrite with the user's, then re-plan."""
    if not isinstance(edit, dict):
        raise _bad("each edit must be an object with the step id")
    index = next(
        (i for i, s in enumerate(record["steps"]) if s["id"] == edit.get("id")), None
    )
    if index is None:
        raise _bad(f"no step {edit.get('id')!r} in this proposal")
    current = record["steps"][index]
    raw = {
        **{
            k: current[k]
            for k in ("id", "kind", "config", "subject_ids", "after", "note")
        },
        "overwrite": current["overwrite"],
    }
    raw.update(
        {k: edit[k] for k in ("config", "subject_ids", "overwrite") if k in edit}
    )
    earlier = {s["id"]: s for s in record["steps"][:index]}
    step = _checked_step(raw, earlier)
    record["steps"][index] = step
    _plan_step(record, step, manager)


def edit_step(
    manager: Any, proposal_id: str, step_id: str, edit: dict[str, Any]
) -> dict[str, Any]:
    with _LOCK:
        record = _pending(manager, proposal_id)
        _apply_edit(record, {**edit, "id": step_id}, manager)
        _save(manager.project_dir, record)
        return _publish(record, manager)


def _blockers(record: dict[str, Any]) -> list[str]:
    problems = []
    for step in record["steps"]:
        plan = step["plan"] or {}
        for error in plan.get("errors", []):
            problems.append(f"step {step['id']}: {error}")
        for item in plan.get("missing_inputs", []):
            problems.append(f"step {step['id']}: missing {item.get('what')}")
        if plan.get("will_overwrite") and not step["overwrite"]:
            problems.append(
                f"step {step['id']} would replace existing output "
                f"({', '.join(plan['will_overwrite'])}); allow replacing or rename the run"
            )
    return problems


def approve(
    manager: Any,
    proposal_id: str,
    edits: list[Any] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Approve (after applying *edits*), then queue every step that waits on nothing.

    Every step is re-planned first, so the check runs against the project as it is now; an
    error, a missing input of a step that waits on nothing, or an output the step would replace
    without ``overwrite`` refuses the approval (409) and nothing is queued.
    """
    with _LOCK:
        record = _pending(manager, proposal_id)
        for edit in edits or []:
            _apply_edit(record, edit, manager)
        for step in record["steps"]:
            _plan_step(record, step, manager)
        problems = _blockers(record)
        if problems:
            _save(manager.project_dir, record)
            _publish(record, manager)
            raise HTTPException(status_code=409, detail="; ".join(problems))
        record["decision"] = {
            "state": "approved",
            "at": utcnow_iso(),
            "note": _text(note, "note", 2000) or None,
        }
        _save(manager.project_dir, record)
        ensure_watcher(manager)
        _advance(record, manager)
        return _publish(record, manager)


def reject(manager: Any, proposal_id: str, note: str | None = None) -> dict[str, Any]:
    with _LOCK:
        record = _pending(manager, proposal_id)
        record["decision"] = {
            "state": "rejected",
            "at": utcnow_iso(),
            "note": _text(note, "note", 2000) or None,
        }
        _save(manager.project_dir, record)
        return _publish(record, manager)


def dismiss(manager: Any, proposal_id: str) -> dict[str, Any]:
    """Hide a finished proposal (done, rejected or failed) from the default list."""
    with _LOCK:
        record = _load(manager.project_dir, proposal_id)
        status = view(record, manager)["status"]
        if status not in ("succeeded", "rejected", "failed"):
            raise HTTPException(
                status_code=409,
                detail=f"proposal {proposal_id} is {status}; only a finished plan can be dismissed",
            )
        record["dismissed_at"] = utcnow_iso()
        _save(manager.project_dir, record)
        return _publish(record, manager)


def _dependants(record: dict[str, Any], step_id: str) -> list[dict[str, Any]]:
    found, frontier = [], {step_id}
    for step in record["steps"]:
        if frontier & set(step["after"]):
            found.append(step)
            frontier.add(step["id"])
    return found


def run_step(manager: Any, proposal_id: str, step_id: str) -> dict[str, Any]:
    """Queue one approved step now -- a retry after it failed, errored or was skipped. Steps
    that were skipped because of it wait for it again."""
    with _LOCK:
        record = _load(manager.project_dir, proposal_id)
        if record["decision"]["state"] != "approved":
            raise HTTPException(status_code=409, detail="approve the proposal first")
        step = next((s for s in record["steps"] if s["id"] == step_id), None)
        if step is None:
            raise HTTPException(status_code=404, detail=f"no step {step_id!r}")
        state = _step_state(record, step, manager)
        if state in ("queued", "running", "succeeded"):
            raise HTTPException(status_code=409, detail=f"step {step_id} is {state}")
        by_id = {s["id"]: s for s in record["steps"]}
        unmet = [
            a
            for a in step["after"]
            if _step_state(record, by_id[a], manager) != "succeeded"
        ]
        if unmet:
            raise HTTPException(
                status_code=409, detail=f"step {step_id} waits on {', '.join(unmet)}"
            )
        for later in [step, *_dependants(record, step_id)]:
            later.update(job_ids=[], error=None, skipped=None)
        record.pop("dismissed_at", None)  # running again: it is not finished any more
        _submit(record, step, manager)
        _save(manager.project_dir, record)
        _advance(record, manager)
        return _publish(record, manager)


# -- queuing ----------------------------------------------------------------------------------


def _submit(record: dict[str, Any], step: dict[str, Any], manager: Any) -> None:
    from tit.server.routes.jobs import InputsMissing, plan_submission

    try:
        kind, entries = _entries(record, step)
        planned = plan_submission(
            manager,
            kind,
            entries[0][1],
            step["subject_ids"],
            subject_configs=(
                None
                if kind == "pre"
                else [{"subject_id": s, "config": c} for s, c in entries]
            ),
            tags=[f"proposal:{record['id']}"],
            overwrite=step["overwrite"],
        )
        result = manager.submit_plan(planned, created_by=record["created_by"])
    except ValueError as exc:
        step["error"] = str(exc)
    except InputsMissing as exc:
        step["error"] = "missing inputs: " + "; ".join(m["what"] for m in exc.missing)
    except HTTPException as exc:
        step["error"] = str(exc.detail)
    else:
        step["job_ids"] = [job["id"] for job in result["jobs"]]
        if not step["job_ids"]:
            step["error"] = "nothing to run for these subjects"


def _advance(record: dict[str, Any], manager: Any) -> bool:
    """Queue every waiting step whose prerequisites all succeeded; skip those with one that
    did not. Caller holds ``_LOCK``. Returns whether the record changed (and was saved).
    """
    if record["decision"]["state"] != "approved":
        return False
    changed = False
    by_id = {s["id"]: s for s in record["steps"]}
    for step in record[
        "steps"
    ]:  # steps only wait on earlier steps: one pass settles them
        if _step_state(record, step, manager) != "waiting":
            continue
        before = [_step_state(record, by_id[a], manager) for a in step["after"]]
        if any(s in ("failed", "error", "skipped") for s in before):
            failed = [a for a, s in zip(step["after"], before) if s != "succeeded"]
            step["skipped"] = f"step {', '.join(failed)} did not succeed"
            changed = True
        elif all(s == "succeeded" for s in before):
            _submit(record, step, manager)
            changed = True
    if changed:
        _save(manager.project_dir, record)
    return changed


def advance_all(manager: Any, finished_job: str | None = None) -> None:
    """Advance every approved proposal; publish those that changed or own *finished_job*."""
    with _LOCK:
        for record in _all(manager.project_dir):
            changed = _advance(record, manager)
            owns = finished_job is not None and any(
                finished_job in s["job_ids"] for s in record["steps"]
            )
            if changed or owns:
                _publish(record, manager)


def ensure_watcher(manager: Any) -> None:
    """Start (once per job manager) the thread that advances proposals as jobs finish."""
    with _LOCK:
        if id(manager) in _WATCHED:
            return
        _WATCHED.add(id(manager))
    q = manager.subscribe_status()

    def watch() -> None:
        try:
            advance_all(manager)  # whatever finished while nobody was watching
            while getattr(manager, "_started", True):
                try:
                    job = q.get(timeout=1.0)
                except queue.Empty:
                    continue
                if job.get("state") in TERMINAL_STATES:
                    try:
                        advance_all(manager, job.get("id"))
                    except Exception:  # noqa: BLE001 - never kill the watcher
                        logger.exception(
                            "proposals: advancing after %s failed", job.get("id")
                        )
        finally:
            manager.unsubscribe_status(q)
            with _LOCK:
                _WATCHED.discard(id(manager))

    threading.Thread(target=watch, name="tit-proposals", daemon=True).start()
