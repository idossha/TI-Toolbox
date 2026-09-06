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


class Capabilities(BaseModel):
    docker_socket: bool
    bpy: bool
    jupyter: bool = Field(
        description="jupyter importable in this interpreter (contracts/SCHEMA-CHANGES.md, ra_13 3e)"
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


class ViewerOpen(BaseModel):
    """``POST /api/view/open`` -- where the scene file was written, in both path languages.

    V2 (``dev/notes/v3-native-panes-external-viewer-plan.md``).  ``path`` is
    inside this container; ``host_path`` is the same file as the *host* sees
    it, and is what the Electron shell hands to the Tetravox desktop app.
    ``host_path`` is ``None`` when this server cannot know its project's host
    root (:mod:`tit.server.host_path`) -- the app then offers the scene as a
    download instead of a launch.
    """

    name: str = Field(description="the file's basename, ending in .tetravox.json")
    path: str = Field(
        description="absolute container path, under <project>/code/ti-toolbox/viewer/"
    )
    host_path: str | None = None
    scene: dict[str, Any] = Field(
        description=(
            "the ViewSpec v2 document that was written, with every dataset/sidecar path "
            "rewritten from an /api/files/raw URL to the host's own absolute path -- the "
            "desktop app reads files, not URLs"
        )
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
