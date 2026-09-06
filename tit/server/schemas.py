"""Response models for the v0 contract (``contracts/openapi.v0.yaml``).

Names match the contract's ``components/schemas`` so ``--dump-openapi`` can
be diffed against it by ``dev/contracts_check.py``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    uptime_s: float


class Version(BaseModel):
    tit_version: str
    server_api: Literal["v0"]
    schema_hash: str = Field(
        description="sha256 of contracts/schema.json (empty until Phase 1)"
    )
    python: str
    simnibs: str | None


class ProtocolRange(BaseModel):
    """The inclusive embed-protocol range this build can host (E1)."""

    min: int
    max: int


class TetravoxEmbedCapability(BaseModel):
    available: bool
    version: str | None = None
    protocol: int | None = None
    source: Literal["override", "installed", "baked"] | None = Field(
        default=None,
        description=(
            "where the active bundle came from: the version baked into the image, "
            "one installed through POST /api/tetravox/install, or a --tetravox-dir "
            "dev override"
        ),
    )
    features: list[str] = Field(
        default_factory=list,
        description=(
            "named capabilities of the active bundle (E1): derived from its protocol, "
            "or taken verbatim from the manifest's own `features` array when it has one, "
            "so a host asks for a name and never for a version number"
        ),
    )
    compatible: bool = Field(
        default=False,
        description="the active bundle's protocol is inside `supported`",
    )
    supported: ProtocolRange = Field(
        description=(
            "the protocol range this build can host (tit.tetravox.protocol). Always "
            "present -- it is a property of this build, not of whatever is installed"
        )
    )


class TetravoxRelease(BaseModel):
    """One embed bundle on disk (active, installed, or the image's floor)."""

    version: str
    protocol: int | None = None
    source: Literal["override", "installed", "baked"]
    path: str
    name: str | None = None
    sha: str | None = None
    features: list[str] = Field(default_factory=list)
    compatible: bool = False
    active: bool = False


class TetravoxState(BaseModel):
    """``GET /api/tetravox`` — everything the Settings page needs in one read."""

    active: TetravoxRelease | None = None
    reason: str = Field(description="one line saying why that bundle is the active one")
    installed: list[TetravoxRelease] = Field(default_factory=list)
    baked: TetravoxRelease | None = None
    supported: ProtocolRange
    install_root: str
    index_url: str = Field(description="where `check for updates` reads from")
    auto_update: bool = Field(
        default=True,
        description=(
            "A3: when true the server checks the release index at startup and every "
            "24 h and installs a newer *compatible* bundle on its own; when false it "
            "still checks and only reports. Persisted in <install root>/policy.json"
        ),
    )


class TetravoxUpdate(BaseModel):
    """One entry of the release index."""

    version: str
    protocol: int | None = None
    url: str
    sha256: str
    notes: str | None = None
    published: str | None = None
    compatible: bool = Field(
        description="protocol inside the supported range: installable by this build"
    )
    installed: bool = Field(description="already present in the install root")


class TetravoxUpdateOutcome(BaseModel):
    """What one pass of the auto-update policy decided (A3).

    ``action`` is the whole vocabulary: ``installed`` (a newer compatible bundle
    is now active), ``available`` (there is one, automatic updates are off),
    ``current``, ``unsupported`` (its protocol is past this build's range -- A1
    says report, never install) and ``failed`` (offline, rate-limited, bad
    digest).  Every one of them is a sentence in ``message``.
    """

    action: Literal["installed", "available", "current", "unsupported", "failed"]
    message: str
    version: str | None = None
    protocol: int | None = None
    at: float | None = Field(default=None, description="unix seconds")


class TetravoxUpdates(BaseModel):
    """``GET /api/tetravox/updates`` — never an error when the network is down.

    ``available`` is false with a readable ``message`` instead, because "you are
    offline" is a state to render, not a failure to retry.
    """

    available: bool
    message: str | None = None
    index_url: str
    releases: list[TetravoxUpdate] = Field(default_factory=list)
    auto_update: bool = Field(
        default=True, description="the persisted policy (A3); see TetravoxState"
    )
    checked_at: float | None = Field(
        default=None,
        description="unix seconds of the check this answer comes from (cached or fresh)",
    )
    from_cache: bool = Field(
        default=False,
        description=(
            "this answer came from the ETag/age cache rather than a request just "
            "made -- GitHub allows 60 unauthenticated requests per hour per IP"
        ),
    )
    last_outcome: TetravoxUpdateOutcome | None = Field(
        default=None,
        description="what the last automatic pass decided, in the words Settings shows",
    )


class Capabilities(BaseModel):
    docker_socket: bool
    bpy: bool
    jupyter: bool = Field(
        description="jupyter importable in this interpreter (contracts/SCHEMA-CHANGES.md, ra_13 3e)"
    )
    tetravox_embed: TetravoxEmbedCapability = Field(
        description="the embedded viewer bundle at /tetravox/, from <embed dir>/manifest.json"
    )
    fastsurfer: bool = Field(
        description="FASTSURFER_HOME (or /opt/fastsurfer) has run_fastsurfer.sh"
    )


# ── viewers (v1): the ViewSpec ───────────────────────────────────────────────
#
# Both routes that hand out a ViewSpec are typed with this model, so the
# generated OpenAPI (and the renderer's generated TypeScript) names it
# instead of describing an anonymous dict.


class ViewPercentile(BaseModel):
    lo: float
    hi: float


class ViewLayer(BaseModel):
    # A client-submitted spec may carry keys the server does not model; keep them.
    model_config = ConfigDict(extra="allow")

    path: str
    kind: Literal["volume", "label"]
    colormap: str
    opacity: float
    visible: bool
    cal_min: float | None = None
    cal_max: float | None = None
    lut: str | None = None
    percentile: ViewPercentile | None = None


class ViewSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    space: Literal["subject", "mni"]
    layers: list[ViewLayer]
    freeview_args: list[str] = Field(
        description="deprecated: exact argv tail for the external Freeview launcher, kept for one release"
    )
    scene: dict[str, Any] | None = Field(
        default=None,
        description=(
            "the Tetravox ViewSpec v2 document (tit.viewspec.to_tetravox_viewspec) the "
            "embedded viewer's Engine.load() accepts directly; the subset this server "
            "emits is hand-schema'd in contracts/tetravox-viewspec-v2.schema.json "
            "(host-facing: also documents the Tetravox-owned engine type, not just this "
            "server's output). Untyped here (Any) because the full engine scene model is "
            "Tetravox-owned and far larger than a Pydantic model is worth mirroring."
        ),
    )


class Project(BaseModel):
    container_path: str
    host_path: str | None = Field(
        default=None,
        description=(
            "the host directory container_path is mounted from, when it can be known: "
            "LOCAL_PROJECT_DIR when set, else this server's own container definition "
            "(bind mount, then the tit.host_project_dir label) -- see tit/server/host_path.py"
        ),
    )
    name: str


class Subject(BaseModel):
    id: str = Field(description="without the sub- prefix")
    has_raw: bool
    has_fastsurfer: bool
    has_freesurfer: bool = Field(
        description="legacy derivatives/freesurfer, still detected read-only"
    )
    has_m2m: bool
    n_simulations: int
    has_sourcedata: bool = Field(
        default=False,
        description=(
            "sourcedata/sub-<id>/ has a raw T1w or T2w series staged (DICOM or "
            "equivalent), whether or not it has been converted yet -- 'not "
            "converted' is has_sourcedata True with has_raw False"
        ),
    )


class SubjectList(BaseModel):
    subjects: list[Subject]


class Simulation(BaseModel):
    # v1 enriches list items with SimulationDetail keys; keep them (pydantic drops extras by default).
    model_config = ConfigDict(extra="allow")

    name: str
    path: str = Field(description="container path")
    has_ti: bool
    has_mti: bool


class SimulationList(BaseModel):
    simulations: list[Simulation]


class MemoryInfo(BaseModel):
    total: int
    available: int
    used: int
    percent: float


class DiskInfo(BaseModel):
    total: int
    free: int
    percent: float


class ProcessInfo(BaseModel):
    pid: int
    name: str
    cmdline: str = ""
    cpu_percent: float
    rss: int
    started: float


class SystemSnapshot(BaseModel):
    ts: float = Field(description="unix seconds")
    cpu_percent: float
    cpu_count: int
    mem: MemoryInfo
    disk: DiskInfo
    processes: list[ProcessInfo] = Field(
        description="toolbox-relevant processes (same keyword filter as system_monitor_tab.py)"
    )


# ── overview (v1): the project Overview page's single aggregate read ─────────
#
# R1 of desktop/IMPLEMENTATION_PLAN.md: the Overview page must answer "what is
# on disk for every subject, and what can run next" in ONE request whose count
# does not grow with the number of subjects, simulations or outputs. The
# per-subject fan-out it replaces silently omitted counts past the renderer's
# 25-subject eager limit.

#: Presence of one artefact for one subject. ``partial`` is a real,
#: distinguishable state (raw data staged under ``sourcedata/`` but never
#: converted; some but not all EEG nets have a leadfield); ``pending`` means a
#: job that would produce it is queued or running right now; ``failed`` means
#: the most recent job that would have produced it failed and it is still
#: absent.
PresenceState = Literal["present", "absent", "partial", "pending", "failed"]


class OverviewCounts(BaseModel):
    """High-level output totals for one subject. Never a detailed tree (Results owns that)."""

    simulations: int
    optimizations: int = Field(description="flex + ex + mEx search runs")
    analyses: int


class OverviewReadiness(BaseModel):
    """Can this subject run one workflow stage, and if not, the requirement that failed."""

    stage: Literal["preprocess", "simulator", "optimizer", "analyzer"]
    ready: bool
    reason: str | None = Field(
        default=None, description="the missing requirement, never a sentence"
    )


class OverviewSubject(BaseModel):
    id: str = Field(description="without the sub- prefix")
    raw: PresenceState
    fastsurfer: PresenceState
    freesurfer: PresenceState
    m2m: PresenceState
    dwi: PresenceState
    ct: PresenceState
    leadfield: PresenceState
    eeg_net: PresenceState
    leadfields: list[str] = Field(
        default_factory=list, description="EEG nets with a precomputed leadfield"
    )
    eeg_nets: list[str] = Field(default_factory=list)
    counts: OverviewCounts
    readiness: list[OverviewReadiness]


class OverviewCoverage(BaseModel):
    """One project-wide coverage tile: how many subjects have this artefact."""

    id: str
    have: int
    total: int


class OverviewTotals(BaseModel):
    subjects: int
    simulations: int
    optimizations: int
    analyses: int
    coverage: list[OverviewCoverage]


class Overview(BaseModel):
    """``GET /api/catalog/overview`` -- everything the Overview page renders."""

    subjects: list[OverviewSubject]
    totals: OverviewTotals
