#!/usr/bin/env python3
"""TI-Toolbox job driver: an MCP server that runs pipelines through the running app.

The read-only knowledge server (``server.py``) explains the toolbox; this one *drives* it.
Every job goes through the ``tit.server`` job API of the TI-Toolbox stack the user already has
open, so it shows up live in the desktop app (job list, terminal) and writes exactly the
records, outputs and reports a job started from the app writes. Jobs are tagged
``created_by: "agent"``.

It never sees or stores the user's AI-subscription credentials: it is a local stdio process the
user's own agent (Claude Code, Codex, ...) launches. The only secret it handles is the local
server token, read from the running container (as ``tit launch`` does) and never returned.

Discovery
---------
1. ``TIT_SERVER_URL`` + ``TIT_SERVER_TOKEN`` when both are set (a native runtime, tests);
2. otherwise the running container labelled ``tit.stack=ti-toolbox-v3`` (``docker inspect``:
   ``TIT_SERVER_TOKEN``/``TIT_SERVER_PORT`` from its environment, the host project directory
   from its ``tit.host_project_dir`` label). With several projects open, ``connect`` takes the
   project path to pick one.

Zero third-party dependencies, Python 3.9+, JSON-RPC 2.0 over newline-delimited stdio
(``stdio_loop.py``, shared with ``server.py``).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stdio_loop  # noqa: E402  (this directory, whatever the working directory is)
from stdio_loop import ToolError  # noqa: E402

SERVER_NAME = "ti-toolbox-jobs"
SERVER_VERSION = "0.6.0"

STACK_ID = "ti-toolbox-v3"  # tit/launch.py STACK_ID, desktop/src/shared/compose.ts
LABEL_STACK = "tit.stack"
LABEL_SERVICE = "tit.service"
LABEL_HOST_DIR = "tit.host_project_dir"
DEFAULT_PORT = "8765"
CREATED_BY = "agent"
TERMINAL_STATES = ("succeeded", "failed", "cancelled", "skipped", "lost")
GROUP_KINDS = ("pre", "sim", "flex", "flex_adaptive", "flex_pareto", "ex", "mex")
FLEX_KINDS = ("flex", "flex_adaptive", "flex_pareto")
SUBJECT_ID_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
)  # tit.paths.SUBJECT_ID_RE
SCHEMA_CLASS = {
    "pre": "PreprocessConfig",
    "sim": "SimulationConfig",
    "flex": "FlexConfig",
    "flex_adaptive": "FlexConfig",
    "flex_pareto": "FlexConfig",
    "ex": "ExConfig",
    "mex": "MExConfig",
    "leadfield": "LeadfieldConfig",
    "analyzer": "AnalyzerConfig",
}

NO_STACK = (
    "No running TI-Toolbox found. Open the TI-Toolbox desktop app on your project (or run "
    "`tit launch`), then call connect again. For a native runtime set TIT_SERVER_URL and "
    "TIT_SERVER_TOKEN."
)


# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------

_CONN: Optional[Dict[str, Any]] = None


def _docker_json(*args: str) -> Any:
    if shutil.which("docker") is None:
        raise ToolError(NO_STACK + " (docker was not found on PATH)")
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=30, check=False
    )
    if result.returncode != 0:
        raise ToolError(
            "Docker is not answering (is Docker Desktop running?): "
            + (result.stderr or result.stdout).strip()
        )
    return result.stdout


def _discover(project: Optional[str] = None) -> Dict[str, Any]:
    url, token = os.environ.get("TIT_SERVER_URL"), os.environ.get("TIT_SERVER_TOKEN")
    if url and token:
        return {"origin": url.rstrip("/"), "token": token, "host_project": None}
    ids = _docker_json(
        "ps", "--filter", f"label={LABEL_STACK}={STACK_ID}", "--format", "{{.ID}}"
    ).split()
    if not ids:
        raise ToolError(NO_STACK)
    stacks = []
    for info in json.loads(_docker_json("inspect", *ids)):
        config = info.get("Config") or {}
        labels = config.get("Labels") or {}
        if labels.get(LABEL_SERVICE) not in (None, "", "tit"):
            continue
        env = dict(p.split("=", 1) for p in config.get("Env") or [] if "=" in p)
        if not env.get("TIT_SERVER_TOKEN"):
            continue
        stacks.append(
            {
                "origin": f"http://127.0.0.1:{env.get('TIT_SERVER_PORT', DEFAULT_PORT)}",
                "token": env["TIT_SERVER_TOKEN"],
                "host_project": labels.get(LABEL_HOST_DIR),
            }
        )
    if project:
        want = os.path.realpath(os.path.expanduser(project))
        stacks = [
            s
            for s in stacks
            if s["host_project"] and os.path.realpath(s["host_project"]) == want
        ]
        if not stacks:
            raise ToolError(f"No running TI-Toolbox has {project} open. " + NO_STACK)
    if not stacks:
        raise ToolError(NO_STACK)
    if len(stacks) > 1:
        open_projects = ", ".join(str(s["host_project"]) for s in stacks)
        raise ToolError(
            f"Several TI-Toolbox projects are open ({open_projects}). Call connect with "
            "project=<one of these paths>."
        )
    return stacks[0]


def _conn() -> Dict[str, Any]:
    global _CONN
    if _CONN is None:
        _CONN = _discover()
    return _CONN


def _api(
    method: str,
    path: str,
    body: Any = None,
    *,
    timeout: float = 60.0,
    text: bool = False,
) -> Any:
    conn = _conn()
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(conn["origin"] + path, data=data, method=method)
    request.add_header("Authorization", f"Bearer {conn['token']}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.dumps(json.loads(detail), ensure_ascii=False)
        except ValueError:
            pass
        raise ToolError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ToolError(
            f"TI-Toolbox at {conn['origin']} is unreachable ({exc}). " + NO_STACK
        ) from exc
    if text:
        return raw.decode("utf-8", errors="replace")
    return json.loads(raw) if raw else None


def _q(**params: Any) -> str:
    return "?" + urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None}
    )


def _subject_id(value: Any) -> str:
    if not isinstance(value, str) or not SUBJECT_ID_RE.match(value):
        raise ToolError(
            f"invalid subject id {value!r}: letters, digits, '_' and '-' only, starting with "
            "a letter or digit, without the 'sub-' prefix"
        )
    return value


def _subject_ids(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value:
        raise ToolError("subject_ids must be a non-empty list of subject ids")
    return [_subject_id(v) for v in value]


def _job_summary(status: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "id",
        "kind",
        "state",
        "subject_ids",
        "group_id",
        "progress",
        "waiting_on",
        "error",
    )
    return {k: status.get(k) for k in keys if status.get(k) not in (None, [])}


# --------------------------------------------------------------------------
# connect
# --------------------------------------------------------------------------


def tool_connect(args: Dict[str, Any]) -> Dict[str, Any]:
    global _CONN
    _CONN = _discover(args.get("project"))
    project = _api("GET", "/api/project")
    if not _CONN.get("host_project"):
        _CONN["host_project"] = project.get("host_path")
    subjects = _api("GET", "/api/catalog/subjects").get("subjects", [])
    jobs = _api("GET", "/api/jobs" + _q(limit=200)) or []
    # An app older than proposals has no such setting and no approval step.
    direct = (_api("GET", "/api/settings") or {}).get("agent_auto_submit", True) is True
    return {
        "server": _CONN["origin"],
        "project": {
            "host_path": _CONN["host_project"],
            "container_path": project.get("container_path"),
            "name": project.get("name"),
        },
        "subjects": subjects,
        "active_jobs": [
            _job_summary(j) for j in jobs if j.get("state") not in TERMINAL_STATES
        ],
        "approval_required": not direct,
        "next": (
            "Plan with plan_job before submit_job; jobs appear live in the desktop app."
            if direct
            else "The user approves agent jobs in the app: plan, then propose_pipeline and "
            "watch_proposal. submit_job / simulate_flex_result are refused."
        ),
        "before_proposing": "Check the request names subject(s), target (region or "
        "coordinates), what to run (simulate a given montage / optimise first / both), goal "
        "or intensity, and the electrode net if it matters. Anything consequential missing or "
        "ambiguous: ask ONE question offering a default flow (in one line) or a few quick "
        "questions. Fill low-stakes gaps (run names) yourself.",
    }


# --------------------------------------------------------------------------
# Regions
# --------------------------------------------------------------------------

#: (atlas path, label id) -> region name, from find_regions, so a proposal's card can name its
#: target ("Left-Thalamus") instead of showing label ids only.
_REGION_NAMES: Dict[Tuple[str, Any], str] = {}


def _target_note(roi: Any) -> Optional[str]:
    """The note 'Target: Left-Thalamus, Right-Thalamus' for an ROI find_regions returned."""
    if not isinstance(roi, dict):
        return None
    pairs = zip(roi.get("atlas_path") or [], roi.get("label") or [])
    names = [_REGION_NAMES.get((p, label)) for p, label in pairs]
    if not names or None in names:
        return None
    return "Target: " + ", ".join(dict.fromkeys(names))


def tool_find_regions(args: Dict[str, Any]) -> Dict[str, Any]:
    subject = _subject_id(args.get("subject_id"))
    # The server searches the subject's atlases and builds the ROIs (tit.catalog.find_regions,
    # the same construction as the app's ROI picker).
    found = _api(
        "GET",
        "/api/catalog/regions" + _q(subject=subject, q=str(args.get("query", ""))),
    )
    if not found:
        raise ToolError(
            f"no region of sub-{subject}'s atlases matches {args.get('query')!r}. Atlases exist "
            "only after preprocessing (charm/FastSurfer); try another spelling or ask the user "
            "for coordinates (SphericalROI)."
        )
    for hit in found:  # rois.all is every match, in order
        all_roi = hit["rois"]["all"]
        for path, label, region in zip(
            all_roi["atlas_path"], all_roi["label"], hit["matches"]
        ):
            _REGION_NAMES[(path, label)] = region["name"]
        hit["matches"] = hit["matches"][:60]
    return {
        "subject_id": subject,
        "query": args.get("query"),
        "atlases": found,
        "how_to_use": "Copy one rois.* object verbatim into FlexConfig.roi. 'all' is the union "
        "of every match (both sides, i.e. bilateral); 'left'/'right' are one side. Surface "
        "(AtlasROI) targets cortex, volume (SubcorticalROI) targets deep structures.",
    }


# --------------------------------------------------------------------------
# Schema, plan, submit
# --------------------------------------------------------------------------


def _refs(node: Any, out: set) -> set:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            out.add(ref.split("/")[-1])
        for value in node.values():
            _refs(value, out)
    elif isinstance(node, list):
        for value in node:
            _refs(value, out)
    return out


def tool_get_config_schema(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(args.get("kind", ""))
    name = SCHEMA_CLASS.get(kind, kind)
    doc = _api("GET", "/api/schema") or {}
    defs = doc.get("$defs", {})
    if name not in defs:
        raise ToolError(
            f"unknown kind/config class {kind!r}; kinds: {', '.join(SCHEMA_CLASS)}"
        )
    wanted, todo = {name}, [name]
    while todo:
        for ref in _refs(defs[todo.pop()], set()):
            if ref in defs and ref not in wanted:
                wanted.add(ref)
                todo.append(ref)
    out: Dict[str, Any] = {"class": name, "schema": defs[name]}
    out["$defs"] = {k: defs[k] for k in sorted(wanted - {name})}
    # What the app's pages start with; the server fills these into omitted fields.
    out["app_defaults_filled_in"] = doc.get("x-app-defaults", {}).get(kind, {})
    return out


def _flex_output_folder(kind: str, config: Dict[str, Any], subject: str) -> str:
    """An absolute run folder, as the Optimizer page resolves one before submitting.

    A bare name goes under the subject's flex-search folder; none at all gets a timestamp
    name, so the run's folder is known before the job starts.
    """
    name = str(config.get("output_folder") or "").strip()
    if name.startswith("/"):
        return name
    if "/" in name or "\\" in name or name in (".", ".."):
        raise ToolError(
            "output_folder must be a run name without separators, or absolute"
        )
    probe = _api(
        "POST",
        f"/api/plan/{kind}",
        {
            "config": {**config, "subject_id": subject, "output_folder": None},
            "subject_ids": [subject],
            "created_by": CREATED_BY,
        },
    )
    parent = os.path.dirname(probe["jobs"][0]["output_dir"])
    return f"{parent}/{name or time.strftime('%Y%m%d_%H%M%S') + '_agent'}"


def _prepare(
    kind: str, config: Any, subject_ids: List[str]
) -> List[Tuple[str, Dict[str, Any]]]:
    """One ``(subject, config)`` per job, with the subject's own id filled in (the server fills
    the app's defaults: every request says ``created_by: "agent"``)."""
    if not isinstance(config, dict):
        raise ToolError("config must be an object")
    if kind == "pre":
        return [("", {**config, "subject_ids": subject_ids})]
    entries = []
    for sid in subject_ids:
        entry = {**config, "subject_id": sid}
        if kind in FLEX_KINDS:
            entry["output_folder"] = _flex_output_folder(kind, entry, sid)
        entries.append((sid, entry))
    return entries


def _plan(
    kind: str, entries: List[Tuple[str, Dict[str, Any]]], overwrite: bool
) -> Dict[str, Any]:
    plans, errors, missing = [], [], []
    for sid, config in entries:
        subjects = [sid] if sid else config["subject_ids"]
        check = _api(
            "POST",
            f"/api/validate/{kind}",
            {"config": config, "created_by": CREATED_BY},
        )
        if not check.get("ok"):
            errors.extend(check.get("errors") or [])
            continue
        missing.extend(
            _api(
                "POST",
                "/api/jobs/preflight",
                {
                    "kind": kind,
                    "config": config,
                    "subject_ids": subjects,
                    "created_by": CREATED_BY,
                },
            ).get("missing", [])
        )
        plans.append(
            _api(
                "POST",
                f"/api/plan/{kind}",
                {
                    "config": config,
                    "subject_ids": subjects,
                    "overwrite": overwrite,
                    "created_by": CREATED_BY,
                },
            )
        )
    jobs = [j for p in plans for j in p.get("jobs", [])]
    eta = [p["cost"].get("eta_minutes") for p in plans if p.get("cost")]
    return {
        "ok": not errors and not missing,
        "errors": errors,
        "missing_inputs": missing,
        "jobs": jobs,
        "will_overwrite": [j["output_dir"] for j in jobs if j.get("will_overwrite")],
        "lock_conflicts": [c for p in plans for c in p.get("lock_conflicts", [])],
        "eta_minutes": sum(e for e in eta if e) if any(eta) else None,
        "warnings": [w for p in plans for w in p.get("warnings", [])],
        "resolved": [p.get("resolved") for p in plans if p.get("resolved")],
    }


def tool_plan_job(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(args.get("kind", ""))
    entries = _prepare(kind, args.get("config"), _subject_ids(args.get("subject_ids")))
    result = _plan(kind, entries, bool(args.get("overwrite", False)))
    if result["will_overwrite"] and not args.get("overwrite"):
        result["next"] = (
            "Existing output would be replaced: ask the user, then submit with overwrite=true, "
            "or change the run name."
        )
    return result


def _submit(
    kind: str,
    entries: List[Tuple[str, Dict[str, Any]]],
    subject_ids: List[str],
    overwrite: bool,
    after: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if (
        kind in GROUP_KINDS and not after
    ):  # what every run page sends (pages/_shared/run)
        body: Dict[str, Any] = {
            "kind": kind,
            "config": entries[0][1],
            "subject_ids": subject_ids,
            "created_by": CREATED_BY,
        }
        if kind != "pre":
            body["subject_configs"] = [
                {"subject_id": s, "config": c} for s, c in entries
            ]
        if len(entries) > 1 and kind != "pre":
            body["tags"] = [f"{kind}-batch"]
        if overwrite:
            body["overwrite"] = True
        result = _api("POST", "/api/jobs/groups", body)
        jobs = result.get("jobs", [])
        group = result.get("group_id")
    else:
        jobs, group = [], None
        for sid, config in entries:
            body = {
                "kind": kind,
                "config": config,
                "subject_ids": [sid] if sid else subject_ids,
                "created_by": CREATED_BY,
            }
            if after:
                body["after"] = after
            if overwrite:
                body["overwrite"] = True
            jobs.append(_api("POST", "/api/jobs", body))
    out: Dict[str, Any] = {
        "group_id": group,
        "jobs": [_job_summary(j) for j in jobs],
        "job_ids": [j["id"] for j in jobs],
        "next": "wait_for_job(job_ids=...) -- call again while any job is still running.",
    }
    if kind in FLEX_KINDS:
        out["output_folders"] = {s: c["output_folder"] for s, c in entries}
    return out


def tool_submit_job(args: Dict[str, Any]) -> Dict[str, Any]:
    kind = str(args.get("kind", ""))
    subject_ids = _subject_ids(args.get("subject_ids"))
    after = args.get("after") or None
    if after is not None and not (
        isinstance(after, list) and all(isinstance(a, str) for a in after)
    ):
        raise ToolError("after must be a list of job ids")
    if after and kind == "pre":
        raise ToolError("kind='pre' cannot wait on other jobs; submit it on its own")
    entries = _prepare(kind, args.get("config"), subject_ids)
    return _submit(
        kind, entries, subject_ids, bool(args.get("overwrite", False)), after
    )


# --------------------------------------------------------------------------
# wait / cancel
# --------------------------------------------------------------------------


def _finished(job_id: str, status: Dict[str, Any]) -> Dict[str, Any]:
    out = _job_summary(status)
    failed = status.get("state") != "succeeded"
    quoted = urllib.parse.quote(job_id, safe="")
    log = _api(
        "GET", f"/api/jobs/{quoted}/log" + _q(tail=40 if failed else 10), text=True
    )
    out["log_tail"] = log.splitlines()[-(40 if failed else 10) :]
    outputs = _api("GET", f"/api/jobs/{quoted}/artifacts") or {}
    files = outputs.get("files") or []
    out["output_folder"] = outputs.get("folder")
    out["output_files"] = [
        {"label": f.get("label"), "kind": f.get("kind"), "path": f.get("path")}
        for f in files[:40]
    ]
    if len(files) > 40:
        out["output_files_truncated"] = len(files)
    return out


#: The longest a wait blocks: under Claude Code's 30-minute idle limit for stdio servers even
#: when the client sends no progress token (code.claude.com/docs/en/mcp, "Timeout configuration").
MAX_WAIT_S = 1500.0
#: A client without background tool calls (Codex: 60 s per-tool timeout, calls run in the turn)
#: gets a short wait, so the turn ends and the user can ask for "status" later.
SHORT_WAIT_S = 45.0


def _backgrounds_waits() -> bool:
    """Claude Code moves a long MCP call to a background task and wakes the agent when it
    returns (automatic backgrounding, 120 s by default, CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS).
    """
    return str(_CLIENT or "").lower() == "claude-code"


def _wait_budget(args: Dict[str, Any]) -> float:
    default = MAX_WAIT_S if _backgrounds_waits() else SHORT_WAIT_S
    return min(max(float(args.get("timeout_s", default)), 0.0), MAX_WAIT_S)


def _poll(check: Callable[[], Any], timeout: float) -> Any:
    """Call ``check`` until it returns something truthy, the budget ends or the call is
    cancelled; returns its last value."""
    poll = float(os.environ.get("TIT_AGENT_POLL_S", "3"))
    deadline = time.monotonic() + timeout
    while True:
        value = check()
        left = deadline - time.monotonic()
        if value or left <= 0 or stdio_loop.pause(min(poll, left)):
            return value


def _job_status(job_id: str) -> Dict[str, Any]:
    return _api("GET", f"/api/jobs/{urllib.parse.quote(job_id, safe='')}")["status"]


def _job_line(status: Dict[str, Any]) -> str:
    pct = (status.get("progress") or {}).get("pct")
    return f"{status.get('kind')} {status.get('state')}" + (
        f" {pct:.0f}%" if isinstance(pct, (int, float)) and pct else ""
    )


def tool_wait_for_job(args: Dict[str, Any]) -> Dict[str, Any]:
    ids = args.get("job_ids") or args.get("job_id")
    ids = [ids] if isinstance(ids, str) else ids
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
        raise ToolError("job_ids must be a non-empty list of job ids")
    statuses: Dict[str, Dict[str, Any]] = {}

    def check() -> bool:
        statuses.update({i: _job_status(i) for i in ids})
        stdio_loop.progress("; ".join(_job_line(s) for s in statuses.values()))
        return all(s.get("state") in TERMINAL_STATES for s in statuses.values())

    done = _poll(check, _wait_budget(args))
    return {
        "done": done,
        "jobs": [
            _finished(i, s) if s.get("state") in TERMINAL_STATES else _job_summary(s)
            for i, s in statuses.items()
        ],
        "next": (
            "All finished. Report states and output paths to the user."
            if done
            else "Still running: call wait_for_job again."
        ),
    }


def tool_cancel_job(args: Dict[str, Any]) -> Dict[str, Any]:
    job_id = str(args.get("job_id", ""))
    if not job_id:
        raise ToolError("job_id is required")
    return _job_summary(
        _api("POST", f"/api/jobs/{urllib.parse.quote(job_id, safe='')}/cancel")
    )


# --------------------------------------------------------------------------
# flex result -> simulation (what Simulator > flex row does, in one call)
# --------------------------------------------------------------------------


def tool_simulate_flex_result(args: Dict[str, Any]) -> Dict[str, Any]:
    subject = _subject_id(args.get("subject_id"))
    # The server owns the run -> montage resolution (tit.sim.montage_sources
    # .resolve_flex_simulation), the same one an approved proposal's sim_from_flex step uses.
    found = _api(
        "GET",
        "/api/sim-from-flex"
        + _q(
            subject=subject, flex_run=args.get("flex_run"), eeg_net=args.get("eeg_net")
        ),
    )
    intensities = args.get("intensities") or found["intensities"]
    config = {
        **(args.get("overrides") or {}),
        "montages": [found["montage"]],
        "intensities": intensities,
    }
    entries = _prepare("sim", config, [subject])
    overwrite = bool(args.get("overwrite", False))
    plan = _plan("sim", entries, overwrite)
    out: Dict[str, Any] = {
        "flex_run": found["flex_run"],
        "placement": found["placement"],
        "intensities_mA": intensities,
        "intensities_from": (
            "given" if args.get("intensities") else found["intensities_from"]
        ),
        "plan": plan,
    }
    if not plan["ok"]:
        out["submitted"] = False
        return out
    if plan["will_overwrite"] and not overwrite:
        out["submitted"] = False
        out["next"] = (
            "A simulation of this run exists: ask the user, then repeat with overwrite=true."
        )
        return out
    if args.get("dry_run"):
        out["submitted"] = False
        return out
    out.update(_submit("sim", entries, [subject], overwrite))
    out["submitted"] = True
    return out


# --------------------------------------------------------------------------
# Proposals: the agent proposes, the user approves in the app, the app queues
# --------------------------------------------------------------------------

#: initialize's clientInfo.name -> the name the approval card shows.
CLIENT_LABELS = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "codex-mcp-client": "Codex",
}
_CLIENT: Optional[str] = None


def _step_for_proposal(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ToolError("each step must be an object")
    kind = str(raw.get("kind", ""))
    config = raw.get("config") or {}
    if not isinstance(config, dict):
        raise ToolError(f"step {raw.get('id')}: config must be an object")
    config = {
        k: v for k, v in config.items() if k != "subject_ids"
    }  # the step's decide
    note = raw.get("note") or (
        _target_note(config.get("roi")) if kind in FLEX_KINDS else None
    )
    return {
        **{k: raw[k] for k in ("id", "overwrite", "after") if k in raw},
        **({"note": note} if note else {}),
        "kind": kind,
        "config": config,
        "subject_ids": _subject_ids(raw.get("subject_ids")),
    }


def _step_summary(step: Dict[str, Any]) -> Dict[str, Any]:
    plan = step.get("plan") or {}
    out = {
        "id": step["id"],
        "kind": step["kind"],
        "subject_ids": step["subject_ids"],
        "state": step.get("state"),
        "job_ids": step.get("job_ids") or [],
    }
    for key in (
        "errors",
        "missing_inputs",
        "will_overwrite",
        "deferred",
        "eta_minutes",
    ):
        if plan.get(key):
            out[key] = plan[key]
    outputs = [o["output_dir"] for o in plan.get("outputs") or []]
    if outputs:
        out["output_dirs"] = outputs
    for key in ("error", "skipped", "resolved"):
        if step.get(key):
            out[key] = step[key]
    return out


def tool_propose_pipeline(args: Dict[str, Any]) -> Dict[str, Any]:
    raw_steps = args.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ToolError("steps must be a non-empty list")
    body: Dict[str, Any] = {
        "title": args.get("title"),
        "rationale": args.get("rationale") or "",
        "steps": [_step_for_proposal(s) for s in raw_steps],
        "created_by": CREATED_BY,
        "client": CLIENT_LABELS.get(str(_CLIENT or "").lower(), _CLIENT),
    }
    draft = _api("POST", "/api/proposals", {**body, "dry_run": True})
    steps = [_step_summary(s) for s in draft["steps"]]
    blocking = [s for s in steps if s.get("errors") or s.get("missing_inputs")]
    if blocking:
        return {
            "proposed": False,
            "steps": steps,
            "next": "Nothing was shown to the user. Fix the errors / missing inputs above "
            "(run a 'pre' step first for missing head models) and call propose_pipeline again.",
        }
    created = _api("POST", "/api/proposals", body)
    out: Dict[str, Any] = {
        "proposed": True,
        "proposal_id": created["id"],
        "status": created["status"],
        "steps": [_step_summary(s) for s in created["steps"]],
        "next": "Write ONE line to the user: the plan is waiting for their approval on the "
        "TI-Toolbox Jobs page and you will pick it up from there. Then call "
        "watch_proposal(proposal_id) as the last thing in this turn"
        + (
            "; it runs in the background, so end your turn as soon as it is moved there."
            if _backgrounds_waits()
            else " (it returns within a minute); if it is still pending, end your turn and "
            "tell the user to say 'status' anytime."
        )
        + " Do not submit these jobs yourself.",
    }
    if any(s.get("will_overwrite") for s in steps):
        out["note"] = (
            "Some steps would replace existing output: approval needs the user to allow "
            "replacing on the card (or edit the run name)."
        )
    return out


def _quoted(proposal_id: Any) -> str:
    if not isinstance(proposal_id, str) or not proposal_id:
        raise ToolError("proposal_id is required")
    return urllib.parse.quote(proposal_id, safe="")


#: Proposal statuses after which nothing else happens, and step states that are final.
PROPOSAL_DONE = ("succeeded", "failed", "rejected")
STEP_DONE = ("succeeded", "failed", "skipped", "error")
#: proposal id -> what watch_proposal already reported ("decision", step ids), so each call
#: returns on the *next* change. ponytail: in this process only; a restarted server reports the
#: current decision and finished steps once more, which is harmless.
_REPORTED: Dict[str, set] = {}
_REPORTED_LOCK = threading.Lock()


def _new_events(proposal: Dict[str, Any], mark: bool) -> List[Tuple[str, Any]]:
    """("decision", state) and ("step", step) not reported yet; marked reported when ``mark``."""
    with _REPORTED_LOCK:
        seen = _REPORTED.setdefault(proposal["id"], set())
        events: List[Tuple[str, Any]] = []
        if proposal["decision"]["state"] != "pending" and "decision" not in seen:
            events.append(("decision", proposal["decision"]["state"]))
        events += [
            ("step", s)
            for s in proposal["steps"]
            if s.get("state") in STEP_DONE and s["id"] not in seen
        ]
        if mark:
            seen.update(
                "decision" if kind == "decision" else s["id"] for kind, s in events
            )
        return events


def _approved_steps(proposal: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Each step's summary, with the config that will run where the user edited it."""
    proposed = {s["id"]: s for s in proposal.get("proposed_steps") or []}
    out = []
    for step in proposal["steps"]:
        summary = _step_summary(step)
        original = proposed.get(step["id"]) or {}
        if (step["config"], step["subject_ids"], step.get("overwrite")) != (
            original.get("config"),
            original.get("subject_ids"),
            original.get("overwrite"),
        ):
            summary["edited"] = True
            summary["approved_config"] = step["config"]
        out.append(summary)
    return out


def _watch_next(status: str, changed: bool) -> str:
    again = (
        "call watch_proposal again as the last thing in your turn (it runs in the background) "
        "and end the turn"
        if _backgrounds_waits()
        else "end your turn and tell the user to say 'status' anytime; then call "
        "watch_proposal(proposal_id, timeout_s=0)"
    )
    if status == "rejected":
        return (
            "The user rejected the plan. Tell them, quote their note, and ask what to change; "
            "never propose the same plan again unchanged. Stop watching."
        )
    if status in PROPOSAL_DONE:
        return (
            "All steps are finished. Give the final summary: each step's state, output folder, "
            "report (*.html) and the key numbers in its log_tail; for a failure quote error and "
            "log_tail. Stop watching."
        )
    if not changed:
        return "Nothing changed yet. Say nothing to the user; " + again + "."
    return (
        "Report only what changed, in two or three lines (approved / the user's edits / the "
        "finished step's output folder, report path and key numbers), then "
        + again
        + "."
    )


def tool_watch_proposal(args: Dict[str, Any]) -> Dict[str, Any]:
    path = f"/api/proposals/{_quoted(args.get('proposal_id'))}"
    latest: Dict[str, Any] = {}

    def check() -> bool:
        latest.update(_api("GET", path))
        running = [s["id"] + " " + s["state"] for s in latest["steps"]]
        stdio_loop.progress(f"{latest['status']}: " + ", ".join(running))
        return bool(_new_events(latest, mark=False))

    _poll(check, _wait_budget(args))
    proposal = latest
    events = _new_events(proposal, mark=True)
    decision = proposal["decision"]
    out: Dict[str, Any] = {
        "proposal_id": proposal["id"],
        "title": proposal.get("title"),
        "status": proposal["status"],
        "decision": decision["state"],
        "changed": bool(events),
        "done": proposal["status"] in PROPOSAL_DONE,
        "events": [
            ev if kind == "decision" else f"step {ev['id']} {ev['state']}"
            for kind, ev in events
        ],
    }
    if decision.get("note"):
        out["note"] = decision["note"]
    if ("decision", "approved") in events:
        out["edited_by_user"] = bool(proposal.get("edited"))
        out["steps"] = _approved_steps(proposal)
    else:
        out["steps"] = [_step_summary(s) for s in proposal["steps"]]
    finished = []
    for kind, step in events:
        if kind == "step":
            jobs = [_finished(j, _job_status(j)) for j in step.get("job_ids") or []]
            finished.append({"step": step["id"], "state": step["state"], "jobs": jobs})
    if finished:
        out["finished"] = finished
    out["next"] = _watch_next(proposal["status"], bool(events))
    return out


def tool_get_proposal(args: Dict[str, Any]) -> Dict[str, Any]:
    proposal = _api("GET", f"/api/proposals/{_quoted(args.get('proposal_id'))}")
    return {
        "proposal_id": proposal["id"],
        "title": proposal["title"],
        "status": proposal["status"],
        "decision": proposal["decision"],
        "steps": [_step_summary(s) for s in proposal["steps"]],
    }


# --------------------------------------------------------------------------
# Tool registry
# --------------------------------------------------------------------------


def _schema(props: Dict[str, Any], required: Tuple[str, ...] = ()) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": list(required),
        "additionalProperties": False,
    }


def _hints(
    read_only: bool, destructive: bool = False, idempotent: bool = False
) -> Dict[str, Any]:
    hints: Dict[str, Any] = {"readOnlyHint": read_only, "openWorldHint": False}
    if not read_only:
        hints.update(destructiveHint=destructive, idempotentHint=idempotent)
    return hints


_STR = {"type": "string"}
_SUBJECTS = {
    "type": "array",
    "items": {"type": "string"},
    "description": "ids without 'sub-'",
}
_KIND = {
    "type": "string",
    "description": "pre, sim, flex, flex_adaptive, flex_pareto, ex, mex, leadfield, analyzer, ...",
}

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "connect",
        "description": "Call first. Finds the TI-Toolbox the user has open and returns its "
        "project folder, every subject with what it has (has_raw, has_sourcedata, has_m2m, ...) "
        "and the jobs queued or running. Pass project=<host path> only when several projects "
        "are open.",
        "inputSchema": _schema({"project": _STR}),
        "annotations": _hints(True),
        "handler": tool_connect,
    },
    {
        "name": "find_regions",
        "description": "Search one subject's atlases for a structure (e.g. 'thalamus', "
        "'precentral') and return ready-to-use FlexConfig ROI objects: rois.all (bilateral "
        "union), rois.left, rois.right. Never invent atlas paths or label ids -- use these.",
        "inputSchema": _schema(
            {"subject_id": _STR, "query": _STR}, ("subject_id", "query")
        ),
        "annotations": _hints(True),
        "handler": tool_find_regions,
    },
    {
        "name": "get_config_schema",
        "description": "JSON schema of one job kind's config (with referenced definitions) and "
        "the app defaults this server fills in for omitted fields.",
        "inputSchema": _schema({"kind": _KIND}, ("kind",)),
        "annotations": _hints(True),
        "handler": tool_get_config_schema,
    },
    {
        "name": "plan_job",
        "description": "Validate a config and show what submitting it would do: errors, missing "
        "inputs, output folders, which existing outputs would be replaced, lock waits and ETA. "
        "Always call before submit_job. Same arguments as submit_job.",
        "inputSchema": _schema(
            {
                "kind": _KIND,
                "config": {"type": "object"},
                "subject_ids": _SUBJECTS,
                "overwrite": {"type": "boolean"},
            },
            ("kind", "config", "subject_ids"),
        ),
        "annotations": _hints(True),
        "handler": tool_plan_job,
    },
    {
        "name": "submit_job",
        "description": "Queue a job directly, without the user's approval. Only works when the "
        "user turned on 'Agent may submit without approval' in the app (connect reports "
        "approval_required=false); otherwise the app refuses it (HTTP 403) and you must use "
        "propose_pipeline. One job per subject; kind='pre' queues the full preprocessing stage "
        "graph. Omitted fields take the app's defaults; subject_id is filled per subject. "
        "overwrite=true replaces existing output -- only after the user agreed. after=[job ids] "
        "waits for other jobs.",
        "inputSchema": _schema(
            {
                "kind": _KIND,
                "config": {"type": "object"},
                "subject_ids": _SUBJECTS,
                "overwrite": {"type": "boolean"},
                "after": {"type": "array", "items": _STR},
            },
            ("kind", "config", "subject_ids"),
        ),
        "annotations": _hints(False, destructive=True),
        "handler": tool_submit_job,
    },
    {
        "name": "wait_for_job",
        "description": "Wait for jobs to finish (direct mode; for a proposal use watch_proposal). "
        "Returns each job's state; finished jobs also get their log tail, output folder and "
        "files. Waits up to timeout_s (max 1500; default 1500 in Claude Code, which runs it in "
        "the background and wakes you when it returns -- end your turn meanwhile; 45 elsewhere). "
        "Call again while done=false.",
        "inputSchema": _schema(
            {
                "job_ids": {"type": "array", "items": _STR},
                "timeout_s": {"type": "number"},
            },
            ("job_ids",),
        ),
        "annotations": _hints(True),
        "handler": tool_wait_for_job,
    },
    {
        "name": "cancel_job",
        "description": "Cancel a queued or running job (stops its processes).",
        "inputSchema": _schema({"job_id": _STR}, ("job_id",)),
        "annotations": _hints(False, destructive=True, idempotent=True),
        "handler": tool_cancel_job,
    },
    {
        "name": "simulate_flex_result",
        "description": "Simulate a finished flex-search run's electrodes, as the Simulator does "
        "for a flex row: picks the run (default: newest), the placement (eeg_net, else the "
        "first mapped net, else the optimised XYZ), the run's own currents, plans, and submits "
        "unless it would overwrite (then asks for overwrite=true). overrides merges extra "
        "SimulationConfig fields. Submitting needs approval_required=false; otherwise use "
        "dry_run=true to preview and propose a sim_from_flex step with config.flex_run.",
        "inputSchema": _schema(
            {
                "subject_id": _STR,
                "flex_run": _STR,
                "eeg_net": _STR,
                "intensities": {"type": "array", "items": {"type": "number"}},
                "overrides": {"type": "object"},
                "overwrite": {"type": "boolean"},
                "dry_run": {"type": "boolean"},
            },
            ("subject_id",),
        ),
        "annotations": _hints(False, destructive=True),
        "handler": tool_simulate_flex_result,
    },
    {
        "name": "propose_pipeline",
        "description": "Propose a plan for the user to approve in the app (a card on its Jobs "
        "page). steps run in order: each {id, kind, config, subject_ids, after?: [earlier step "
        "ids], note?, overwrite?}. kind is a job kind or 'sim_from_flex' (config.flex_step = an "
        "earlier flex step's id, or config.flex_run = a finished run's name; optional eeg_net, "
        "intensities and SimulationConfig fields). Omitted fields take the app's defaults; a "
        "flex step without output_folder gets a timestamped run name. The server validates and "
        "plans every step first; with errors nothing is shown to the user. After approval the "
        "app queues the steps itself -- a step starts when every step in its after succeeded. "
        "Before proposing, the request must name the subject(s), the target, what to run "
        "(simulate a given montage, optimise, or both) and the goal; if any of these is "
        "missing or ambiguous, ask the user first instead of guessing. Then watch_proposal.",
        "inputSchema": _schema(
            {
                "title": _STR,
                "rationale": {
                    "type": "string",
                    "description": "why this plan, in the user's terms",
                },
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": _STR,
                            "kind": _KIND,
                            "config": {"type": "object"},
                            "subject_ids": _SUBJECTS,
                            "after": {"type": "array", "items": _STR},
                            "note": _STR,
                            "overwrite": {"type": "boolean"},
                        },
                        "required": ["id", "kind", "config", "subject_ids"],
                    },
                },
            },
            ("title", "rationale", "steps"),
        ),
        "annotations": _hints(False, destructive=False),
        "handler": tool_propose_pipeline,
    },
    {
        "name": "watch_proposal",
        "description": "Follow a proposal until its NEXT change: the user approves or rejects "
        "it, a step finishes, or everything is done. Returns changed, events, every step's "
        "state, finished steps' output folders / files / log tails, and next. Call it as the "
        "last thing in your turn, right after one line telling the user what you are waiting "
        "for. Claude Code runs it in the background (default timeout_s 1500) and wakes you "
        "with its result: end your turn, never sit waiting. Other clients: it returns within "
        "45 s; end the turn and, when the user asks for status, call it with timeout_s=0. "
        "Keep one watch per proposal.",
        "inputSchema": _schema(
            {"proposal_id": _STR, "timeout_s": {"type": "number"}}, ("proposal_id",)
        ),
        "annotations": _hints(True),
        "handler": tool_watch_proposal,
    },
    {
        "name": "get_proposal",
        "description": "A proposal's status and each step's state (proposed, waiting, queued, "
        "running, succeeded, failed, skipped, error) with its job ids. Returns at once.",
        "inputSchema": _schema({"proposal_id": _STR}, ("proposal_id",)),
        "annotations": _hints(True),
        "handler": tool_get_proposal,
    },
]


def _on_initialize(params: Dict[str, Any]) -> None:
    global _CLIENT
    _CLIENT = (params.get("clientInfo") or {}).get("name") or None


handle = stdio_loop.handler(
    SERVER_NAME,
    SERVER_VERSION,
    "Runs TI-Toolbox jobs through the app the user has open; every job appears live in its "
    "job list. Call connect first: unless it says approval_required is false, jobs need the "
    "user's approval -- propose the whole pipeline with propose_pipeline, then watch_proposal "
    "as the last call of the turn (it runs in the background and returns on the next change; "
    "never keep the user waiting on it). If the request leaves the subject, target, what to "
    "run or the goal open, ask before proposing. Raw scans: copy them yourself into "
    "<connect's project.host_path>/sourcedata/sub-<id>/<T1w|T2w|ct|dwi>/ (never move or "
    "overwrite), then propose a pre step. Targets: find_regions, never invented atlas paths or labels. Plan before "
    "proposing or submitting; never resubmit a rejected plan unchanged.",
    TOOLS,
    on_initialize=_on_initialize,
)


if __name__ == "__main__":
    stdio_loop.serve(handle)
