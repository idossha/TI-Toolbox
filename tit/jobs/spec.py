"""Job data model: ``JobSpec``/``JobStatus`` and the small value types they're built from.

Shapes mirror ``contracts/openapi.yaml`` (``JobKind``, ``JobState``, ``JobProgress``,
``JobError``, ``Artifact``, ``WaitingOn``, ``JobStatus``, ``JobSpec``, ``JobDetail``,
``LockConflict``).  A few fields exist only on the Python side (persisted to
``spec.json``/``status.json`` for the scheduler's own bookkeeping — ``locks``, ``cost``,
``pid``, ``create_time``, ``budget_wait``, ``group_cap``) and are dropped by
:meth:`JobStatus.to_api` / :meth:`JobSpec.to_api` before a response leaves the server, so the wire
shape stays exactly what the contract describes plus one harmless additive field
(``budget_wait``, not ``additionalProperties: false`` in the schema).

``JobKind``'s frozen v1 contract enum (``CONTRACT_JOB_KINDS``) now includes ``tools`` and
``report`` alongside ``project_init`` (``contracts/CHANGES.md``, 2026-08-27 entry, item 1).
``project_init`` maps to ``-m tit.project_init`` and ``report`` to ``-m tit.pre.report`` in
:mod:`tit.jobs.kinds` (ra_14 finding #2; F0, 2026-09-03).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, get_args

# All kinds the internal job model understands (TODO.md §2.3).
JOB_KINDS: tuple[str, ...] = (
    "pre",
    "sim",
    "flex",
    "flex_adaptive",
    "flex_pareto",
    "ex",
    "mex",
    "leadfield",
    "analyzer",
    "stats",
    "source",
    "blender",
    "nifti_average",
    "nilearn",
    "tools",
    "project_init",
    "report",
)

# Kinds present in the frozen wire contract's JobKind enum (contracts/openapi.yaml).
# "project_init" is in the contract but has no runner mapping in tit.jobs.kinds yet.
CONTRACT_JOB_KINDS: frozenset[str] = frozenset(
    {
        "pre",
        "sim",
        "flex",
        "flex_adaptive",
        "flex_pareto",
        "ex",
        "mex",
        "leadfield",
        "analyzer",
        "stats",
        "source",
        "blender",
        "nifti_average",
        "nilearn",
        "project_init",
        "tools",
        "report",
    }
)

# The same set as a type, so a Pydantic model carrying a job kind on the wire declares the
# contract's ``JobKind`` enum instead of a bare ``str`` (a bare ``str`` dumps no enum, and
# `dev/contracts_check.py` then reports the route as untyped against `contracts/openapi.yaml`).
JobKind = Literal[
    "pre",
    "sim",
    "flex",
    "flex_adaptive",
    "flex_pareto",
    "ex",
    "mex",
    "leadfield",
    "analyzer",
    "stats",
    "source",
    "blender",
    "nifti_average",
    "nilearn",
    "project_init",
    "tools",
    "report",
]

# The Literal above and the frozenset are two spellings of one contract enum; drift between them
# would let a model advertise a kind the rest of the server rejects.
assert set(get_args(JobKind)) == CONTRACT_JOB_KINDS, (
    "JobKind and CONTRACT_JOB_KINDS disagree: "
    f"{set(get_args(JobKind)) ^ CONTRACT_JOB_KINDS}"
)

JOB_STATES: tuple[str, ...] = (
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "skipped",
    "lost",
)

TERMINAL_STATES: frozenset[str] = frozenset(
    {"succeeded", "failed", "cancelled", "skipped", "lost"}
)

CREATED_BY_VALUES: tuple[str, ...] = ("gui", "browser", "api", "notebook")

EVENT_TYPES: tuple[str, ...] = (
    "log",
    "stage",
    "progress",
    "marker",
    "artifact",
    "result",
    "exit",
)


def new_job_id() -> str:
    """A short, URL-safe, collision-resistant job id."""
    return uuid.uuid4().hex[:16]


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string (``JobStatus.created_at`` etc.)."""
    return datetime.now(timezone.utc).isoformat()


def _drop_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


@dataclass
class Cost:
    """Estimated resource cost of one job, for scheduler admission (§2.4)."""

    cpus: float
    mem_gb: float

    def __add__(self, other: "Cost") -> "Cost":
        return Cost(self.cpus + other.cpus, self.mem_gb + other.mem_gb)

    def fits(self, budget: "Cost") -> bool:
        return self.cpus <= budget.cpus and self.mem_gb <= budget.mem_gb

    def to_dict(self) -> dict[str, float]:
        return {"cpus": self.cpus, "mem_gb": self.mem_gb}


@dataclass
class JobProgress:
    stage: str
    i: int
    n: int
    pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "JobProgress | None":
        if data is None:
            return None
        return cls(stage=data["stage"], i=data["i"], n=data["n"], pct=data["pct"])


@dataclass
class WaitingOn:
    key: str
    job_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WaitingOn":
        return cls(key=data["key"], job_id=data["job_id"])


@dataclass
class JobError:
    type: str
    message: str
    last_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "JobError | None":
        if data is None:
            return None
        return cls(
            type=data["type"],
            message=data["message"],
            last_lines=list(data.get("last_lines", [])),
        )


@dataclass
class Artifact:
    path: str
    kind: str
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Artifact":
        return cls(path=data["path"], kind=data["kind"], label=data.get("label"))


@dataclass
class LockConflict:
    key: str
    held_by: str
    kind: str
    subject: str
    started_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobSpec:
    """The full, persisted job record (``jobs/<id>/spec.json``).

    ``kind``/``config``/``subject_ids``/``after``/``tags``/``overwrite`` are the fields a caller
    may set (the wire ``JobSpec`` in the contract is exactly this subset, minus ``id`` which the
    server assigns); ``locks``/``cost``/``env``/``created_by``/``created_at``/``group_id``/
    ``group_cap`` are computed or defaulted by :mod:`tit.jobs.manager` at submission time and
    never come from the client directly (``group_cap`` mirrors ``JobGroupRequest.parallel_subjects``
    onto every job ``submit_plan`` creates for that group, so :mod:`tit.jobs.scheduler` can enforce
    it without a separate group registry — see :func:`tit.jobs.scheduler.evaluate`).
    """

    id: str
    kind: str
    config: dict[str, Any]
    subject_ids: list[str]
    after: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    locks: list[str] = field(default_factory=list)
    cost: Cost = field(default_factory=lambda: Cost(cpus=1.0, mem_gb=1.0))
    created_by: str = "api"
    created_at: str = field(default_factory=utcnow_iso)
    group_id: str | None = None
    group_cap: int | None = None
    overwrite: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "config": self.config,
            "subject_ids": list(self.subject_ids),
            "after": list(self.after),
            "tags": list(self.tags),
            "env": dict(self.env),
            "locks": list(self.locks),
            "cost": self.cost.to_dict(),
            "created_by": self.created_by,
            "created_at": self.created_at,
            "group_id": self.group_id,
            "group_cap": self.group_cap,
            "overwrite": self.overwrite,
        }

    def to_api(self) -> dict[str, Any]:
        """The contract-shaped ``JobSpec`` (request/response body — no server internals)."""
        out: dict[str, Any] = {
            "kind": self.kind,
            "config": self.config,
            "subject_ids": list(self.subject_ids),
        }
        if self.after:
            out["after"] = list(self.after)
        if self.tags:
            out["tags"] = list(self.tags)
        if self.overwrite:
            out["overwrite"] = self.overwrite
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobSpec":
        cost = data.get("cost") or {"cpus": 1.0, "mem_gb": 1.0}
        return cls(
            id=data["id"],
            kind=data["kind"],
            config=data.get("config", {}),
            subject_ids=list(data.get("subject_ids", [])),
            after=list(data.get("after", [])),
            tags=list(data.get("tags", [])),
            env=dict(data.get("env", {})),
            locks=list(data.get("locks", [])),
            cost=Cost(cpus=cost["cpus"], mem_gb=cost["mem_gb"]),
            created_by=data.get("created_by", "api"),
            created_at=data.get("created_at", utcnow_iso()),
            group_id=data.get("group_id"),
            group_cap=data.get("group_cap"),
            overwrite=bool(data.get("overwrite", False)),
        )


@dataclass
class PlannedJob:
    """One node of a not-yet-submitted job DAG (``tit.jobs.plans.plan_preprocessing``).

    ``label`` is a plan-scoped identifier (e.g. ``"charm"``, ``"dicom"``) used only to express
    edges before real job ids exist; :meth:`tit.jobs.manager.JobManager.submit_plan` resolves
    ``after_labels`` to real job ids in topological order and assigns each a real id.
    """

    label: str
    kind: str
    config: dict[str, Any]
    subject_ids: list[str]
    after_labels: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    #: Replace this job's existing output instead of skipping it (``JobSpec.overwrite``). Set by
    #: ``POST /api/jobs/groups`` from ``JobGroupRequest.overwrite`` for the generic per-subject
    #: kinds; ``pre`` carries the same policy inside its own config's skip/replace flags instead.
    overwrite: bool = False


@dataclass
class JobStatus:
    id: str
    kind: str
    state: str
    subject_ids: list[str]
    created_at: str
    group_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    progress: JobProgress | None = None
    liveness: str | None = None  # "active" | "stalled" | None
    waiting_on: list[WaitingOn] = field(default_factory=list)
    exit_code: int | None = None
    error: JobError | None = None
    artifacts: list[Artifact] = field(default_factory=list)
    cpu_percent: float | None = None
    rss: int | None = None
    # Internal-only (persisted to status.json, stripped by to_api()):
    pid: int | None = None
    create_time: float | None = None
    budget_wait: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Full persisted shape (``status.json``), internal fields included."""
        d = self.to_api()
        d["pid"] = self.pid
        d["create_time"] = self.create_time
        d["budget_wait"] = self.budget_wait
        return d

    def to_api(self, project_dir: str | None = None) -> dict[str, Any]:
        """Contract-shaped ``JobStatus`` for API responses.

        ``log_path`` (ra_13 finding #6) is derived from *project_dir* on the fly via the same
        convention :mod:`tit.jobs.registry` uses for the file itself, rather than persisted --
        it's the same deterministic string every time for a given ``(project_dir, id)`` pair, so
        there is nothing to store. ``None`` when *project_dir* isn't supplied (e.g. a bare
        ``JobStatus`` built in a test with no registry behind it).
        """
        from tit.jobs.registry import stdout_path  # local: registry imports this module

        return {
            "id": self.id,
            "kind": self.kind,
            "state": self.state,
            "subject_ids": list(self.subject_ids),
            "group_id": self.group_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress": self.progress.to_dict() if self.progress else None,
            "liveness": self.liveness,
            "waiting_on": [w.to_dict() for w in self.waiting_on],
            "exit_code": self.exit_code,
            "error": self.error.to_dict() if self.error else None,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "cpu_percent": self.cpu_percent,
            "rss": self.rss,
            "log_path": stdout_path(project_dir, self.id) if project_dir else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobStatus":
        return cls(
            id=data["id"],
            kind=data["kind"],
            state=data["state"],
            subject_ids=list(data.get("subject_ids", [])),
            group_id=data.get("group_id"),
            created_at=data["created_at"],
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            progress=JobProgress.from_dict(data.get("progress")),
            liveness=data.get("liveness"),
            waiting_on=[WaitingOn.from_dict(w) for w in data.get("waiting_on", [])],
            exit_code=data.get("exit_code"),
            error=JobError.from_dict(data.get("error")),
            artifacts=[Artifact.from_dict(a) for a in data.get("artifacts", [])],
            cpu_percent=data.get("cpu_percent"),
            rss=data.get("rss"),
            pid=data.get("pid"),
            create_time=data.get("create_time"),
            budget_wait=data.get("budget_wait"),
        )

    @classmethod
    def queued(cls, spec: JobSpec) -> "JobStatus":
        return cls(
            id=spec.id,
            kind=spec.kind,
            state="queued",
            subject_ids=list(spec.subject_ids),
            group_id=spec.group_id,
            created_at=spec.created_at,
        )
