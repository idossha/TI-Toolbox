"""Response models for the wire contract (``contracts/openapi.yaml``).

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
        description="sha256 of contracts/generated/config.schema.json (empty until Phase 1)"
    )
    python: str
    simnibs: str | None


class Capabilities(BaseModel):
    docker_socket: bool
    bpy: bool
    jupyter: bool = Field(
        description="jupyter importable in this interpreter (contracts/CHANGES.md, ra_13 3e)"
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


class ViewerSceneFile(BaseModel):
    """One dataset a scene references, as the Viewer page's preview strip shows it."""

    id: str | None = None
    kind: str | None = Field(default=None, description='"volume" or "mesh"')
    name: str
    path: str = Field(description="the path written into the scene (host-facing)")
    container_path: str | None = Field(
        default=None,
        description=(
            "the same file as this server sees it -- what the client sends back in "
            "`files` when the row is kept, moved or joined by another (VM2)"
        ),
    )
    bytes: int | None = Field(
        default=None,
        description="size on disk, or null when the file could not be stat'ed",
    )


class ViewerOpen(BaseModel):
    """``POST /api/view/open`` -- where the scene file was written, in both path languages.

    V2 (``docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)``).  ``path`` is
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
    scene_path: str = Field(
        description="Container scene path accepted by the native host bridge"
    )
    host_path: str | None = None
    files: list[ViewerSceneFile] = Field(
        default_factory=list,
        description=(
            "one row per dataset the scene references -- the Viewer page's preview "
            "strip, so a person can see what a selection resolves to (and how big it "
            "is) before another application's window opens on top of their work"
        ),
    )
    dry_run: bool = Field(
        default=False,
        description=(
            "true when the request asked for the resolution only: the response is "
            "identical except that nothing was written to disk"
        ),
    )
    scene: dict[str, Any] = Field(
        description=(
            "the ViewSpec v2 document that was written, with every dataset/sidecar path "
            "rewritten from an /api/files/raw URL to the host's own absolute path -- a "
            "desktop Tetravox, or an export, reads files rather than URLs"
        )
    )
    view: dict[str, Any] = Field(
        description="Source ViewSpec before native path localisation"
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
    # Optional breakdown (added 2026-09-07): what the System page's stacked bar needs to say
    # "13 GB of this is reclaimable cache" instead of drawing one undifferentiated block.
    free: int = 0
    cached: int = 0
    buffers: int = 0


class DiskInfo(BaseModel):
    total: int
    free: int
    percent: float
    path: str = Field(
        default="",
        description="The mount point measured. Optional: added 2026-09-07 so the System page can "
        "label which filesystem a figure belongs to (the project volume, the Docker root).",
    )


class SwapInfo(BaseModel):
    """Swap, which the System page reads as a pressure signal rather than a capacity one."""

    total: int
    used: int
    free: int
    percent: float


class ContainerInfo(BaseModel):
    """One Docker container the daemon knows about (our siblings: QSIPrep/QSIRecon)."""

    id: str
    name: str
    image: str
    state: str
    status: str


class SelfProcessInfo(BaseModel):
    """The server's own process — the one the jobs are children of."""

    pid: int
    cpu_percent: float
    rss: int


class ProcessInfo(BaseModel):
    pid: int
    name: str
    cmdline: str = ""
    cpu_percent: float
    rss: int
    started: float
    # Optional, added 2026-09-07 for the htop-style process table.
    ppid: int = 0
    status: str = Field(
        default="", description="psutil status: running, sleeping, zombie, ..."
    )
    mem_percent: float = 0.0
    threads: int = 0
    relevant: bool = Field(
        default=True,
        description="matches the toolbox keyword filter (what the pre-2026-09-07 list held)",
    )
    owner_kind: Literal["job", "kernel", "server"] | None = Field(
        default=None,
        description="what this process belongs to; only an owned process may be stopped from the UI",
    )
    owner_id: str | None = Field(default=None, description="job id or kernel id")
    owner_label: str = Field(
        default="", description="human label for the owner, e.g. 'sim - ernie'"
    )


class NetIO(BaseModel):
    """Cumulative interface counters since boot; the page shows the delta between snapshots."""

    bytes_sent: int
    bytes_recv: int


class DockerDf(BaseModel):
    """``docker system df`` -- the high-level "is the daemon filling the disk" answer."""

    images_size: int = 0
    images_count: int = 0
    images_reclaimable: int = 0
    containers_size: int = 0
    containers_count: int = 0
    volumes_size: int = 0
    volumes_count: int = 0
    volumes_reclaimable: int = 0
    build_cache_size: int = 0


class DockerImage(BaseModel):
    repo_tag: str
    size: int


class DockerMount(BaseModel):
    source: str
    destination: str
    mode: str = ""


class OwnContainer(BaseModel):
    """This server's own container, as ``docker inspect`` describes it."""

    id: str
    name: str
    image: str
    image_id: str = ""
    state: str = ""
    status: str = ""
    health: str = ""
    started_at: str = ""
    restarts: int = 0
    #: Cores, not the Engine's NanoCpus. ``None`` means "no limit set".
    cpu_limit: float | None = None
    #: Bytes. ``None``/0 means "no limit set" -- the container may use the whole host.
    mem_limit: int | None = None
    mounts: list[DockerMount] = Field(default_factory=list)


class DockerHealth(BaseModel):
    """Everything the System page's Docker panel shows, in one bounded read.

    Polled on its own (slower) TTL than the rest of the snapshot: ``/system/df`` walks the image
    graph and an inspect is a round trip, and neither changes at the 1-2 s cadence the CPU
    figures do.  ``reachable: false`` with an ``error`` is a first-class answer -- the panel then
    says the daemon is unreachable rather than showing zeros that look like a healthy, empty
    daemon.
    """

    reachable: bool = False
    latency_ms: float | None = None
    version: str = ""
    api_version: str = ""
    error: str = ""
    df: DockerDf | None = None
    own: OwnContainer | None = None
    containers: list["ContainerInfo"] = Field(default_factory=list)
    images: list[DockerImage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StorageKind(BaseModel):
    """One class of project output, and what it costs on disk."""

    kind: str
    label: str
    bytes: int
    files: int


class StorageItem(BaseModel):
    """One named thing inside a kind -- "sub-101 - Flex search"."""

    name: str
    kind: str
    bytes: int


class ProjectStorage(BaseModel):
    """``GET /api/system/storage`` -- what the project is using, by kind.

    Separate from :class:`SystemSnapshot` because it is a different *kind* of
    read: the snapshot is a cheap sample taken every second, this is a full walk
    of the project that can take minutes on a large volume and is therefore
    cached on disk and refreshed in the background.  ``scanning`` says a refresh
    is running right now and these are the previous numbers.
    """

    project_dir: str
    total_bytes: int
    total_files: int
    scanned_at: float = Field(description="unix seconds; 0 when never scanned")
    duration_s: float
    scanning: bool = Field(
        default=False,
        description="a background refresh is running; these are the last numbers",
    )
    partial: bool = Field(
        default=False, description="the scan was abandoned before it finished"
    )
    kinds: list[StorageKind] = Field(default_factory=list)
    largest: list[StorageItem] = Field(
        default_factory=list, description="the biggest subject x kind combinations"
    )


class SystemSnapshot(BaseModel):
    ts: float = Field(description="unix seconds")
    cpu_percent: float
    cpu_count: int
    mem: MemoryInfo
    disk: DiskInfo
    processes: list[ProcessInfo] = Field(
        description="the busiest processes, capped at PROCESS_LIMIT; `relevant` flags the ones "
        "matching the toolbox keyword filter that used to be the whole list"
    )

    # ---- added 2026-09-07 for the System page (the full-height system monitor) ----
    #
    # Every field below is OPTIONAL with a default, so a client written against
    # the pre-2026-09-07 snapshot keeps parsing this payload unchanged, and a
    # host that cannot answer one of them (no ``getloadavg`` on the platform, no
    # Docker socket mounted, ``/var/lib/docker`` not visible from inside the
    # container) simply omits it rather than failing the whole snapshot.
    cpu_per_core: list[float] = Field(
        default_factory=list, description="per-core utilisation, same order as psutil"
    )
    load_avg: list[float] = Field(
        default_factory=list,
        description="1/5/15-minute load average; empty where unsupported",
    )
    uptime_s: float = Field(
        default=0.0, description="seconds since boot of the machine we see"
    )
    swap: SwapInfo | None = None
    disk_docker: DiskInfo | None = Field(
        default=None,
        description="the Docker root filesystem, when it is visible from here",
    )
    own: SelfProcessInfo | None = Field(
        default=None,
        description="the server process itself (excluded from `processes`)",
    )
    kernels: int = Field(
        default=0, description="notebook kernels this server currently owns"
    )
    containers: list[ContainerInfo] = Field(
        default_factory=list,
        description="Docker sibling containers (QSIPrep/QSIRecon), if any",
    )
    net: NetIO | None = Field(default=None, description="cumulative interface counters")
    docker: DockerHealth | None = Field(
        default=None,
        description="Docker daemon health, disk usage and our own container",
    )
    process_total: int = Field(
        default=0,
        description="how many processes exist; `processes` is the top N by CPU",
    )


# ── overview (v1): the project Overview page's single aggregate read ─────────
#
# R1 of docs/dev/HISTORY.md § 2026-09-05: the Overview page must answer "what is
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


# --------------------------------------------------------------------------- notebooks & kernels


class NotebookEntry(BaseModel):
    """One notebook as the list shows it."""

    name: str
    size: int
    modified: float
    #: Under ``examples/`` -- the seeded worked example.
    example: bool = False


class NotebookList(BaseModel):
    """``GET /api/notebooks``."""

    dir: str
    notebooks: list[NotebookEntry]


class Notebook(BaseModel):
    """One notebook and its nbformat v4 document, verbatim.

    ``content`` is deliberately an untyped object: the ``.ipynb`` IS the
    document (ARCHITECTURE §7.6), and narrowing it here would be this server
    deciding which keys of a format it does not own are allowed to survive.
    """

    name: str
    content: dict[str, Any]


class NotebookDeleted(BaseModel):
    deleted: str


class Kernel(BaseModel):
    """One running notebook kernel."""

    id: str
    name: str
    displayName: str
    language: str
    cwd: str
    state: Literal["starting", "idle", "busy", "dead"]
    startedAt: float
    lastUsed: float


class KernelList(BaseModel):
    """``GET /api/kernels`` -- what is running, and the limits it runs under."""

    kernels: list[Kernel]
    max: int
    idleTimeoutSeconds: float


class KernelStopped(BaseModel):
    id: str
    state: str


class KernelInterrupted(BaseModel):
    id: str
    interrupted: bool


class ProjectIdentity(BaseModel):
    name: str
    path: str
    created_at: str | None


class StoragePart(BaseModel):
    name: str
    bytes: int


class DerivativeStorage(StoragePart):
    children: list[StoragePart] = Field(default_factory=list)


class SummaryStorage(BaseModel):
    state: Literal["scanning", "ready", "error"]
    total_bytes: int | None
    derivatives: list[DerivativeStorage]
    other_bytes: int | None
    scanned_at: str | None


class ActivityDay(BaseModel):
    date: str
    count: int


class RecentProjectJob(BaseModel):
    id: str
    kind: str
    state: str
    subject_ids: list[str]
    created_at: str


class ProjectActivity(BaseModel):
    days: list[ActivityDay]
    recent: list[RecentProjectJob]
    last_activity_at: str | None
    history_since: str | None


class ProjectSummary(BaseModel):
    identity: ProjectIdentity
    storage: SummaryStorage
    activity: ProjectActivity
