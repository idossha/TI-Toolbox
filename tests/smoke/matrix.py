"""The smoke matrix: one row per kind of ``docs/dev/HISTORY.md § 2026-09-03 (pipelines program)`` §3.

What this pins
--------------
For every pipeline the v3 server can run, *which* config the UI would emit, *what behaviour* is
asserted (``accepted`` -> ``started`` -> ``completed``/``cancelled``/``refused``, decision P4),
*how long* it may take, *what it creates* (so decision P6's cleanup deletes exactly that), and
*why that subject* on Dataset 000.

Where the configs come from
---------------------------
Not invented: every row mirrors either one of the maintainer's own succeeded job specs
(``/Users/idohaber/datasets/000/code/ti-toolbox/jobs/<id>/spec.json`` -- ``35ea5755…`` for sim,
``d0036f3c…`` for pre, ``02a18de1…`` for analyzer), a saved run config the pipeline itself wrote
(``ex-search/docs_ex_symmetric/run_config.json``, ``m-ex-search/docs_mex_symmetric/
run_config.json``, ``Simulations/L_Insula/documentation/config.json``) or the field list of the
matching dataclass in ``contracts/schema.json`` (generated from
``tit.config_io.CONFIG_CLASS_REGISTRY``). A hand-invented config would test the harness's idea
of the contract, not the product's.

The failure this file exists to prevent
---------------------------------------
The two pipelines that failed for the maintainer on 2026-09-03 (``flex``: the UI emits
``atlas_path: string[]`` and the runner assumed a scalar; ``report``: a kind
``tit/jobs/plans.py`` plans and ``tit/jobs/kinds.py`` could not run) both fail within seconds of
submission. Nothing was running them.

Budgets are wall-clock on this machine (Apple silicon, amd64 SimNIBS under emulation); they are
ceilings for a *test*, not performance claims.

Deliberately elsewhere: transport (:mod:`tests.smoke.client`), path bookkeeping
(:mod:`tests.smoke.cleanup`), the assertions and the pytest options
(:mod:`tests.smoke.test_kinds`, :mod:`tests.smoke.conftest`).

Written 2026-09-03 (lane S1).
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from typing import Any, Callable

# ---------------------------------------------------------------------------------------------
# Behaviours (decision P4)
# ---------------------------------------------------------------------------------------------

#: Runs to `succeeded` inside the row's budget; every artifact it reports must exist on disk and
#: the matching catalog route must list the output.
COMPLETED = "completed"
#: Reaches `running` with its own banner, then is cancelled; must reach `cancelled` in <= 15 s
#: with no runner pid left. For the FEM-class kinds that would take 15+ minutes (decision P7).
STARTED_THEN_CANCEL = "started_then_cancel"
#: Accepted by validate/plan/submit, then refused by the runner for a *data* reason, as a
#: human-readable job error -- no Python traceback in `error.message`.
REFUSED = "refused"

BEHAVIOURS = (COMPLETED, STARTED_THEN_CANCEL, REFUSED)

#: Budget for the `accepted` leg of every row (validate + plan + submit), decision P4.
ACCEPT_BUDGET_S = 10.0
#: Budget for reaching `running` + a banner, decision P4.
START_BUDGET_S = 120.0
#: Budget for a cancel to reach `cancelled`, decision P4.
CANCEL_BUDGET_S = 15.0


@dataclass
class Ctx:
    """Everything a row needs to build a namespaced, cleanable config."""

    run_id: str
    #: the project directory *as the server sees it* (``GET /api/project`` -> container_path)
    root: str = "/mnt/000"

    def name(self, suffix: str) -> str:
        """A run/output name nobody else owns: ``smoke-<runid>-<suffix>`` (decision P6)."""
        return f"smoke-{self.run_id}-{suffix}"

    def p(self, *parts: str) -> str:
        return posixpath.join(self.root, *parts)

    def simnibs(self, subject: str, *parts: str) -> str:
        return self.p("derivatives", "SimNIBS", f"sub-{subject}", *parts)

    def ti_toolbox(self, *parts: str) -> str:
        return self.p("derivatives", "ti-toolbox", *parts)


@dataclass
class Submission:
    """One POST the harness will make."""

    kind: str
    config: dict[str, Any]
    subject_ids: list[str]
    tags: list[str] = field(default_factory=list)
    #: True -> ``POST /api/jobs/groups`` (preprocessing DAG) instead of ``POST /api/jobs``
    group: bool = False
    parallel_subjects: int = 1
    #: extra top-level keys for ``POST /api/plan/{kind}`` (e.g. ``montage_sources``)
    plan_extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Row:
    """One line of §3's fixture matrix."""

    id: str
    #: the ``PipelineKind`` used for ``/api/validate`` and ``/api/plan``
    kind: str
    behaviour: str
    subject: str
    why_subject: str
    build: Callable[[Ctx], Submission]
    budget_s: float
    #: Any one of these regexes matching a log line or an event's stage/message proves the
    #: runner itself started. Every pattern here was read off a real run on the dev container
    #: (2026-09-03) -- either the runner's first `stage` event or its first stdout line -- not
    #: guessed: a loose pattern like ``[Ff]lex`` also matches the config path echoed at
    #: startup, which would call a job "started" before the runner did anything.
    banner: tuple[str, ...] = ()
    #: why this row has no banner to match (a silent one-shot script); required when banner is
    #: empty and the row is not REFUSED, so "no banner" is never an oversight
    no_banner_reason: str = ""
    #: False for kinds outside ``PipelineKind`` (``tools``, ``project_init``): validate/plan 404
    plannable: bool = True
    #: container paths this row may create; claimed (with pre-existence) before submitting
    creates: Callable[[Ctx], list[str]] = lambda ctx: []
    #: container paths that must exist after a COMPLETED row, on top of the job's own artifacts
    expect_files: Callable[[Ctx], list[str]] = lambda ctx: []
    #: (client, ctx) -> (ok, evidence); the catalog route that must list the new output
    catalog: Callable[..., tuple[bool, str]] | None = None
    #: for REFUSED rows: one of these must appear in the runner's own output
    refusal: tuple[str, ...] = ()
    #: for group submissions: pick the job of the group this row is about, by tag
    group_tag: str | None = None
    #: ``(config, ctx, row) -> None``, mutating ``config`` in place: rewrites the field(s) of a
    #: *replayed UI payload* that name a fixed output (an ``analysis_name``, an ``output_name``,
    #: a montage ``name``, an ``output_dir`` a runner would otherwise derive deterministically
    #: from the rest of the config) to this session's own ``smoke-<runid>`` tag. Applied only to
    #: payload sources (:func:`tests.smoke.test_kinds.load_submission`) -- a builtin config is
    #: already namespaced by :meth:`Ctx.name`. None for a kind with nothing to rewrite (its
    #: payload either has no such field, or the field it has is already fresh every run -- see
    #: the per-kind functions above each affected row for exactly which field and why).
    payload_rename: Callable[[dict[str, Any], Ctx, "Row"], None] | None = None
    notes: str = ""

    @property
    def heavy(self) -> bool:
        """FEM-class or otherwise exclusive: never run two of these at once (decision P7)."""
        return self.kind in {"sim", "flex", "leadfield", "source", "blender"} or (
            self.group_tag in {"G2a", "G2b"}
        )


# ---------------------------------------------------------------------------------------------
# Config builders
# ---------------------------------------------------------------------------------------------

#: Mirrors job d0036f3cad7b4be9's config exactly (the maintainer's succeeded `pre` run), minus
#: the step flag each row sets. Every flag is spelled out because `plan_preprocessing` forces
#: all of them False except its own stage's, and an absent key would be a different request
#: shape from the one the UI sends.
def _pre_config(ctx: Ctx, subject: str, **flags: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "project_dir": ctx.root,
        "subject_ids": [subject],
        "convert_dicom": False,
        "create_m2m": False,
        "run_fastsurfer": False,
        "fastsurfer_threads": None,
        "run_tissue_analysis": False,
        "run_qsiprep": False,
        "run_qsirecon": False,
        "qsiprep_config": None,
        "qsi_recon_config": None,
        "extract_dti": False,
        "skip_existing_outputs": False,
        "replace_existing_outputs": False,
    }
    config.update(flags)
    return config


def _pre_submission(ctx: Ctx, subject: str, tag: str, **flags: Any) -> Submission:
    return Submission(
        kind="pre",
        config=_pre_config(ctx, subject, **flags),
        subject_ids=[subject],
        group=True,
        parallel_subjects=1,
        plan_extra={"parallel_subjects": 1},
    )


#: Mirrors job 35ea5755624a44ac's config (succeeded, 16 min under emulation) -- same subject,
#: same net, same electrode geometry; only the montage name is namespaced.
def _sim_submission(ctx: Ctx, pairs: list[list[str]], suffix: str) -> Submission:
    # One intensity per electrode pair. The 2-pair TI case is the default `[1, 1]`; a 4-pair
    # mTI montage needs four (tit/sim/config.py's __post_init__, and
    # tit.sim.utils._validate_simulation_inputs before it) -- job cdf272b6556c43fa died on
    # exactly that, and /api/validate/sim used to answer {"ok": true} for it.
    return Submission(
        kind="sim",
        config={
            "subject_id": "101",
            "montages": [
                {
                    "_type": "Montage",
                    "name": ctx.name(suffix),
                    "mode": "net",
                    "eeg_net": "BioSemi-128-A1.csv",
                    "electrode_pairs": pairs,
                }
            ],
            "conductivity": "scalar",
            "electrode_shape": "ellipse",
            "electrode_dimensions": [8, 8],
            "gel_thickness": 4,
            "intensities": [1] * len(pairs),
            "output_fields": ["TI_max"],
        },
        subject_ids=["101"],
    )


_EX_LEADFIELD = "derivatives/SimNIBS/sub-ernie/leadfields/ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5"

#: The one EEG net every sub-101 fixture uses: the only net with a leadfield on this
#: project, and the net `tests/smoke/payloads/source.json` recorded from the UI.
_SOURCE_NET = "EEG10-10_UI_Jurak_2007"


def _ex_submission(ctx: Ctx) -> Submission:
    return Submission(
        kind="ex",
        config={
            "subject_id": "ernie",
            "leadfield_hdf": ctx.p(_EX_LEADFIELD),
            "roi_name": "L_Insula_MNI.csv",
            "roi_radius": 5.0,
            "electrodes": {
                "_type": "BucketElectrodes",
                "e1_plus": ["F7", "FT7"],
                "e1_minus": ["F8", "FT8"],
                "e2_plus": ["P7", "TP7"],
                "e2_minus": ["P8", "TP8"],
            },
            "total_current": 2.0,
            "current_step": 0.5,
            "run_name": ctx.name("ex"),
        },
        subject_ids=["ernie"],
    )


def _mex_submission(ctx: Ctx) -> Submission:
    return Submission(
        kind="mex",
        config={
            "subject_id": "ernie",
            "leadfield_hdf": ctx.p(_EX_LEADFIELD),
            "roi_name": "L_Insula_MNI.csv",
            "roi_radius": 5.0,
            "electrodes": {
                "_type": "BucketElectrodes",
                "e1_plus": ["F7"],
                "e1_minus": ["F8"],
                "e2_plus": ["P7"],
                "e2_minus": ["P8"],
                "e3_plus": ["F3"],
                "e3_minus": ["F4"],
                "e4_plus": ["P3"],
                "e4_minus": ["P4"],
            },
            "current_mA": 2.0,
            "run_name": ctx.name("mex"),
        },
        subject_ids=["ernie"],
    )


def _analyzer_submission(
    ctx: Ctx, simulation: str, space: str, suffix: str
) -> Submission:
    return Submission(
        kind="analyzer",
        config={
            "mode": "single",
            "subject_id": "ernie",
            "simulation": simulation,
            "space": space,
            "analysis_type": "spherical",
            "coordinate_space": "subject",
            "center": [-40.0, -10.0, 10.0],
            "radius": 10.0,
            # tit.catalog.analyses only scans Analyses/Mesh and Analyses/Voxel, so an
            # output_dir anywhere else produces results the app can never list (measured:
            # /api/catalog/analyses ignored Analyses/<name> on 2026-09-03).
            "output_dir": ctx.simnibs(
                "ernie", "Simulations", simulation, "Analyses", space.capitalize(), ctx.name(suffix)
            ),
            "visualize": True,
        },
        subject_ids=["ernie"],
    )


_STATS_SUBJECTS = [
    {"subject_id": "101", "simulation_name": "L_Insula"},
    {"subject_id": "ernie", "simulation_name": "L_Insula"},
    {"subject_id": "MNI152", "simulation_name": "L_Insula"},
]


# ---------------------------------------------------------------------------------------------
# Payload rename (decision P6; found by lane HX, 2026-09-04)
# ---------------------------------------------------------------------------------------------
# A payload lane S2 recorded is the exact body one real UI session submitted, including
# whatever name it happened to give the output *at that moment* -- ``stats.json``'s
# ``analysis_name: "smoke-ui-4863"``, ``nifti_average.json``'s ``output_name: "smoke-ui-90719"``.
# Replayed later (this session or a future one), the name is still that literal string, so a
# second replay of the same payload always targets the *first* replay's own output: the plan
# reports it ``exists``, and since a payload is allowed to legitimately name a real run (not a
# harness bug), the row *skips* instead of running (P6 working as designed, on the wrong
# target). Each function below rewrites exactly the field(s) named in its docstring, in place,
# to this session's own ``ctx.name(...)`` tag; wired onto a Row via ``payload_rename`` and
# applied by ``tests.smoke.test_kinds.load_submission`` to every loaded payload before the row
# runs -- so a payload is exercised fresh every session, not just the one that recorded it.


def _rename_analyzer_payload(config: dict[str, Any], ctx: Ctx, row: "Row") -> None:
    """``output_dir``: a recorded payload's is usually ``null`` (no field in the Analyzer page
    writes one), which ``Analyzer._resolve_output_dir`` (``tit/analyzer/analyzer.py``) turns
    into a directory name derived deterministically from subject+simulation+space+center+radius
    -- the same payload always derives the same path, so a second replay finds it and skips.
    Given the same directory shape ``_analyzer_submission`` uses for the builtin row, so cleanup
    and the analyses-catalog check behave identically either way."""
    simulation = config.get("simulation") or "unknown-simulation"
    space = str(config.get("space") or "mesh")
    subject = config.get("subject_id") or row.subject
    config["output_dir"] = ctx.simnibs(
        subject, "Simulations", simulation, "Analyses", space.capitalize(), ctx.name(row.id)
    )


def _rename_stats_payload(config: dict[str, Any], ctx: Ctx, row: "Row") -> None:
    """``analysis_name``: names ``derivatives/ti-toolbox/stats/group_comparison/<name>/`` 1:1
    (``tit/stats``); a literal UI-session tag in the recorded body, not derived from anything a
    replay controls."""
    config["analysis_name"] = ctx.name(row.id)


def _rename_nifti_average_payload(config: dict[str, Any], ctx: Ctx, row: "Row") -> None:
    """``output_name``: names ``derivatives/ti-toolbox/nifti_average/<name>/`` 1:1."""
    config["output_name"] = ctx.name(row.id)


def _rename_nilearn_payload(config: dict[str, Any], ctx: Ctx, row: "Row") -> None:
    """``subdir_name``: names ``derivatives/ti-toolbox/nilearn_visuals/<name>/`` 1:1."""
    config["subdir_name"] = ctx.name(row.id)


def _rename_sim_payload(config: dict[str, Any], ctx: Ctx, row: "Row") -> None:
    """``montages[*].name``: SimNIBS refuses to reuse a montage's own output directory
    ("Found already existing simulation results in directory", job caad925a2e9c4142), and a
    recorded payload's montage name is the literal timestamp the UI session happened to use
    (e.g. ``"smoke-ui-71595-ti"``), not re-derived on replay. One row's payload holds exactly
    one montage today; indexed regardless, so a future multi-montage payload stays collision-free
    too."""
    for i, montage in enumerate(config.get("montages") or []):
        if isinstance(montage, dict) and montage.get("name"):
            montage["name"] = ctx.name(f"{row.id}-{i}")


# flex's ``output_folder`` is deliberately not rewritten here: when the payload leaves it
# ``null`` (as recorded), ``tit/opt/flex/flex.py::_run_flex_search_inner`` calls
# ``generate_run_dirname`` itself and gets a fresh, timestamped directory on every run -- the
# same self-namespacing a builtin row gets from ``Ctx.name``, already applied by the runner, not
# something this harness needs to redo. ``source``'s forward/ directory has no name-bearing
# field at all (one fixed path per subject, per S2's own notes) -- nothing to rewrite it to.


# ---------------------------------------------------------------------------------------------
# Catalog checks -- the second reader for a COMPLETED row (the server's own discovery rules)
# ---------------------------------------------------------------------------------------------


def _catalog_subject_listed(subject: str):
    def check(client, ctx: Ctx) -> tuple[bool, str]:
        ids = [s.get("id") or s.get("subject_id") for s in client.catalog("subjects")["subjects"]]
        return subject in ids, f"/api/catalog/subjects -> {sorted(str(i) for i in ids)}"

    return check


def _catalog_run_listed(path: str, key: str, name_of: Callable[[Ctx], str], **params: Any):
    def check(client, ctx: Ctx) -> tuple[bool, str]:
        wanted = name_of(ctx)
        items = client.catalog(path, **params)
        names = [i.get(key) for i in items] if isinstance(items, list) else []
        return wanted in names, f"/api/catalog/{path} -> {names}"

    return check


def _catalog_analyses(simulation: str, name_of: Callable[[Ctx], str]):
    def check(client, ctx: Ctx) -> tuple[bool, str]:
        wanted = name_of(ctx)
        items = client.catalog("analyses", subject="ernie", simulation=simulation)
        names = [i.get("name") for i in items]
        return wanted in names, f"/api/catalog/analyses({simulation}) -> {names}"

    return check


def _catalog_group_has(section: str, name_of: Callable[[Ctx], str]):
    def check(client, ctx: Ctx) -> tuple[bool, str]:
        wanted = name_of(ctx)
        group = client.catalog("group")
        blob = repr(group.get(section, group))
        return wanted in blob, f"/api/catalog/group[{section}] contains {wanted!r}: {wanted in blob}"

    return check


# ---------------------------------------------------------------------------------------------
# The matrix
# ---------------------------------------------------------------------------------------------

ROWS: tuple[Row, ...] = (
    Row(
        id="pre_dicom",
        kind="pre",
        behaviour=COMPLETED,
        subject="102",
        why_subject="sub-102 is the only subject with sourcedata DICOMs and no BIDS directory, "
        "so this row creates the subject instead of overwriting one (P6).",
        build=lambda ctx: _pre_submission(ctx, "102", "G1", convert_dicom=True),
        group_tag="G1",
        budget_s=300.0,
        banner=(r"Beginning pre-processing for subject: 102", r"^DICOM conversion$"),
        # `tit.pre.structural.ensure_subject_dirs` scaffolds derivatives/SimNIBS/sub-102 as
        # part of this stage, so pre_dicom -- not pre_charm -- is the row that creates it.
        # Claiming it here (before it exists) is what lets cleanup remove it: `Manifest.claim`
        # is idempotent per path and the *first* claim's pre-existence is the one that counts,
        # so a later row claiming the same path cannot mistake this run's own output for the
        # maintainer's (measured 2026-09-03: it was left behind exactly that way).
        creates=lambda ctx: [
            ctx.p("sub-102"),
            ctx.simnibs("102"),
            ctx.ti_toolbox("reports", "sub-102"),
        ],
        expect_files=lambda ctx: [ctx.p("sub-102", "anat", "sub-102_T1w.nii.gz")],
        catalog=_catalog_subject_listed("102"),
        notes="Group route: the DAG is G1 + the trailing `report` job (see pre_report).",
    ),
    Row(
        id="pre_charm",
        kind="pre",
        behaviour=STARTED_THEN_CANCEL,
        subject="102",
        why_subject="sub-102 has no m2m yet; charm on 101/ernie/MNI152 would overwrite the "
        "head models everything else in the matrix reads.",
        build=lambda ctx: _pre_submission(ctx, "102", "G2a", create_m2m=True),
        group_tag="G2a",
        budget_s=START_BUDGET_S,
        banner=(r"Running SimNIBS charm", r"^SimNIBS charm$"),
        creates=lambda ctx: [ctx.simnibs("102")],
        notes="charm is hours under emulation; started -> cancel is the whole assertion (P4).",
    ),
    Row(
        id="pre_fastsurfer",
        kind="pre",
        behaviour=STARTED_THEN_CANCEL,
        subject="102",
        why_subject="Reads the raw BIDS T1w pre_dicom just created; no other subject lacks a "
        "FastSurfer output to create.",
        build=lambda ctx: _pre_submission(ctx, "102", "G2b", run_fastsurfer=True),
        group_tag="G2b",
        budget_s=START_BUDGET_S,
        banner=(r"^FastSurfer", r"FastSurfer segmentation"),
        creates=lambda ctx: [ctx.p("derivatives", "fastsurfer", "sub-102")],
    ),
    Row(
        id="pre_tissue",
        kind="pre",
        behaviour=COMPLETED,
        subject="MNI152",
        why_subject="MNI152 has m2m_MNI152/segmentation/labeling.nii.gz (the only input tissue "
        "analysis needs) and is the one subject with no tissue_analysis output yet -- 101 and "
        "ernie already have one and would be overwritten (P6). Read-only on m2m_MNI152.",
        build=lambda ctx: _pre_submission(ctx, "MNI152", "G3", run_tissue_analysis=True),
        group_tag="G3",
        budget_s=600.0,
        banner=(r"^Tissue analysis$", r"Tissue analysis: Started"),
        creates=lambda ctx: [ctx.ti_toolbox("tissue_analysis", "sub-MNI152")],
        expect_files=lambda ctx: [
            ctx.ti_toolbox("tissue_analysis", "sub-MNI152", "bone_analysis", "bone_analysis.txt")
        ],
    ),
    Row(
        id="pre_qsiprep",
        kind="pre",
        behaviour=REFUSED,
        subject="101",
        why_subject="Dataset 000 has no DWI for any subject; 101 is the subject whose BIDS tree "
        "is otherwise complete, so the only thing that can fail is the DWI preflight.",
        build=lambda ctx: _pre_submission(ctx, "101", "G4", run_qsiprep=True),
        group_tag="G4",
        budget_s=120.0,
        refusal=(r"requires BIDS DWI data", r"[Nn]o DWI", r"Preprocessing failed"),
        notes="§3 row 'accepted-then-refused readable': the QSIPrep image is never pulled.",
    ),
    Row(
        id="pre_report",
        kind="pre",
        behaviour=COMPLETED,
        subject="102",
        why_subject="The trailing `report` job of any pre group; ridden on the cheapest one "
        "(sub-102 DICOM conversion, 12 s measured) so the row costs a report, not a pipeline. "
        "`replace_existing_outputs` is set so re-converting after pre_dicom in the same "
        "session is well-defined rather than a race with that row's output.",
        build=lambda ctx: _pre_submission(
            ctx, "102", "report", convert_dicom=True, replace_existing_outputs=True
        ),
        group_tag="report",
        budget_s=180.0,
        banner=(r"^report$", r"Report generated: "),
        # The report lands in derivatives/ti-toolbox/reports/sub-102/, a directory that
        # pre-exists and holds the maintainer's own reports; the file itself is claimed from
        # the job's reported artifacts (Manifest.claim_produced), never the directory.
        creates=lambda ctx: [ctx.p("sub-102"), ctx.simnibs("102")],
        notes="Was broken (F0 fixed it): tit/jobs/plans.py planned a kind tit/jobs/kinds.py "
        "could not run -- 'unknown job kind: report'.",
    ),
    Row(
        id="sim_ti",
        kind="sim",
        behaviour=STARTED_THEN_CANCEL,
        subject="101",
        why_subject="Exactly the maintainer's own succeeded run (job 35ea5755624a44ac): "
        "sub-101, BioSemi-128-A1, A1/A2 + A4/A3.",
        build=lambda ctx: _sim_submission(ctx, [["A1", "A2"], ["A4", "A3"]], "ti"),
        budget_s=START_BUDGET_S,
        banner=(r"TI: smoke-", r"SimNIBS simulation: Started"),
        creates=lambda ctx: [ctx.simnibs("101", "Simulations", ctx.name("ti"))],
        payload_rename=_rename_sim_payload,
        notes="16 min to completion under emulation (measured, job 35ea5755); --smoke-full runs it.",
    ),
    Row(
        id="sim_mti",
        kind="sim",
        behaviour=STARTED_THEN_CANCEL,
        subject="101",
        why_subject="Same subject/net as sim_ti; four electrode pairs is what makes "
        "Montage.simulation_mode report mTI (tit/sim/config.py).",
        build=lambda ctx: _sim_submission(
            ctx, [["A1", "A2"], ["A4", "A3"], ["B1", "B2"], ["B4", "B3"]], "mti"
        ),
        budget_s=START_BUDGET_S,
        banner=(r"mTI: smoke-", r"TI: smoke-", r"SimNIBS simulation: Started"),
        creates=lambda ctx: [ctx.simnibs("101", "Simulations", ctx.name("mti"))],
        payload_rename=_rename_sim_payload,
    ),
    Row(
        id="flex",
        kind="flex",
        behaviour=STARTED_THEN_CANCEL,
        subject="101",
        why_subject="Byte-for-byte the ROI shape of the maintainer's failed job "
        "c45cb53b0e864d02 (three DK40 labels as a list -- the ROI-union form the UI emits).",
        build=lambda ctx: Submission(
            kind="flex",
            config={
                "subject_id": "101",
                "goal": "mean",
                "postproc": "max_TI",
                "current_mA": 1,
                "electrode": {"shape": "ellipse", "dimensions": [8, 8], "gel_thickness": 4},
                "roi": {
                    "_type": "AtlasROI",
                    "atlas_path": [
                        ctx.simnibs("101", "m2m_101", "segmentation", "lh.101_DK40.annot"),
                        ctx.simnibs("101", "m2m_101", "segmentation", "lh.101_DK40.annot"),
                        ctx.simnibs("101", "m2m_101", "segmentation", "lh.101_DK40.annot"),
                    ],
                    "hemisphere": ["lh", "lh", "lh"],
                    "label": [4, 7, 10],
                },
                "anisotropy_type": "scalar",
                "n_multistart": 1,
                "max_iterations": 500,
                "population_size": 13,
                "mutation": "0.01,0.5",
                "recombination": 0.7,
                "tolerance": 0.1,
                "optimize_current_ratio": True,
                "min_electrode_distance": 5,
                "output_folder": ctx.simnibs("101", "flex-search", ctx.name("flex")),
            },
            subject_ids=["101"],
        ),
        budget_s=START_BUDGET_S,
        banner=(r"^flex_search$", r"Setting up headmodel"),
        creates=lambda ctx: [ctx.simnibs("101", "flex-search", ctx.name("flex"))],
        notes="Known broken (F0): TypeError expected str ... not list in _validate_roi_input.",
    ),
    Row(
        id="leadfield",
        kind="leadfield",
        behaviour=STARTED_THEN_CANCEL,
        subject="101",
        why_subject="sub-101 has a leadfield for EEG10-10_UI_Jurak_2007 only, so "
        "GSN-HydroCel-185 is a net with nothing to overwrite (P6).",
        build=lambda ctx: Submission(
            kind="leadfield",
            config={
                "subject_id": "101",
                "eeg_net": "GSN-HydroCel-185",
                "overwrite": False,
            },
            subject_ids=["101"],
        ),
        budget_s=START_BUDGET_S,
        banner=(r"Generating leadfield for ", r"Running simulations in the directory"),
        creates=lambda ctx: [
            ctx.simnibs("101", "leadfields", "101_leadfield_GSN-HydroCel-185.hdf5"),
            ctx.simnibs("101", "leadfields", "101_electrodes_GSN-HydroCel-185.msh"),
        ],
    ),
    Row(
        id="ex",
        kind="ex",
        behaviour=COMPLETED,
        subject="ernie",
        why_subject="The only subject with a precomputed leadfield and a saved ROI CSV "
        "(m2m_ernie/ROIs/L_Insula_MNI.csv); the run config mirrors ex-search/"
        "docs_ex_symmetric/run_config.json with 2 electrodes per bucket instead of 7.",
        build=_ex_submission,
        budget_s=900.0,
        banner=(r"^ex_search$", r"TI Exhaustive Search"),
        creates=lambda ctx: [ctx.simnibs("ernie", "ex-search", ctx.name("ex"))],
        expect_files=lambda ctx: [
            ctx.simnibs("ernie", "ex-search", ctx.name("ex"), "final_output.csv")
        ],
        # `run_name`, not `name`: tit.catalog.ex_runs keys the entry that way (verified
        # against /api/catalog/ex-runs on the dev container, 2026-09-03).
        catalog=_catalog_run_listed(
            "ex-runs", "run_name", lambda ctx: ctx.name("ex"), subject="ernie", kind="ex"
        ),
    ),
    Row(
        id="mex",
        kind="mex",
        behaviour=COMPLETED,
        subject="ernie",
        why_subject="Same leadfield/ROI as `ex`; mirrors m-ex-search/docs_mex_symmetric/"
        "run_config.json with one electrode per bucket (the smallest legal multipolar search).",
        build=_mex_submission,
        budget_s=900.0,
        banner=(r"^mex_search$", r"Multipolar Exhaustive Sea"),
        creates=lambda ctx: [ctx.simnibs("ernie", "m-ex-search", ctx.name("mex"))],
        expect_files=lambda ctx: [
            ctx.simnibs("ernie", "m-ex-search", ctx.name("mex"), "final_output.csv")
        ],
        catalog=_catalog_run_listed(
            "ex-runs", "run_name", lambda ctx: ctx.name("mex"), subject="ernie", kind="mex"
        ),
    ),
    Row(
        id="analyzer_mesh",
        kind="analyzer",
        behaviour=COMPLETED,
        subject="ernie",
        why_subject="Simulation `Thalamus` is the ernie run with a full TI mesh + surfaces "
        "tree; the sphere is the maintainer's own succeeded analyzer job (02a18de1d3d047e3).",
        build=lambda ctx: _analyzer_submission(ctx, "Thalamus", "mesh", "mesh"),
        budget_s=600.0,
        banner=(r"Starting single analysis", r"Analyzer initialised"),
        creates=lambda ctx: [
            ctx.simnibs("ernie", "Simulations", "Thalamus", "Analyses", "Mesh", ctx.name("mesh"))
        ],
        expect_files=lambda ctx: [
            ctx.simnibs(
                "ernie", "Simulations", "Thalamus", "Analyses", "Mesh", ctx.name("mesh"),
                "analysis.json",
            )
        ],
        catalog=_catalog_analyses("Thalamus", lambda ctx: ctx.name("mesh")),
        payload_rename=_rename_analyzer_payload,
    ),
    Row(
        id="analyzer_voxel",
        kind="analyzer",
        behaviour=COMPLETED,
        subject="ernie",
        why_subject="Simulation `L_Insula` is the ernie run with subject-space NIfTIs "
        "(TI/niftis/L_Insula_TI_subject_TI_max.nii.gz), which is what voxel space reads.",
        build=lambda ctx: _analyzer_submission(ctx, "L_Insula", "voxel", "voxel"),
        budget_s=600.0,
        banner=(r"Starting single analysis", r"Analyzer initialised"),
        creates=lambda ctx: [
            ctx.simnibs("ernie", "Simulations", "L_Insula", "Analyses", "Voxel", ctx.name("voxel"))
        ],
        expect_files=lambda ctx: [
            ctx.simnibs(
                "ernie", "Simulations", "L_Insula", "Analyses", "Voxel", ctx.name("voxel"),
                "analysis.json",
            )
        ],
        catalog=_catalog_analyses("L_Insula", lambda ctx: ctx.name("voxel")),
        payload_rename=_rename_analyzer_payload,
    ),
    Row(
        id="source",
        kind="source",
        behaviour=STARTED_THEN_CANCEL,
        subject="101",
        why_subject="sub-101 has no forward/ directory; ernie's already exists and a completed "
        "run would overwrite it (P6). mne is importable in the image (checked), so this row "
        "asserts the pipeline starts rather than a refusal.",
        notes="Default run cancels at the banner: the point-electrode FEM leadfield alone is "
        "~10 min on this emulated container (75 solves for this net). `--smoke-full` promotes "
        "the row to COMPLETED and checks the three MNE files in expect_files -- measured "
        "2026-09-04 (lane FX4): succeeded in 611.1 s, 3 artifacts, job 300d9dd6f6e94ac5. Note "
        "the output directory is fixed (no run-name field), so under P6 this row runs once "
        "per project until forward/ is removed.",
        build=lambda ctx: Submission(
            kind="source",
            config={
                "mode": "forward",
                "subject_ids": ["101"],
                "forward": {
                    "eeg_net": "EEG10-10_UI_Jurak_2007",
                    "fsaverage_spacing": 5,
                    "cpus": 1,
                    "overwrite": False,
                },
            },
            subject_ids=["101"],
        ),
        # Only read on the COMPLETED / REFUSED legs, so this is inert for the default
        # started-then-cancel run and is the ceiling for `--smoke-full`.
        budget_s=2700.0,
        banner=(r"Starting source forward pipeline", r"Forward: 1 subject"),
        creates=lambda ctx: [ctx.simnibs("101", "forward")],
        # The three files an MNE source reconstruction needs; the fsaverage projection is
        # the -morph.h5 (a SourceMorph onto fsaverage5). Names are prepare_forward()'s own
        # `sub-<id>_net-<net>` stem, not a guess.
        expect_files=lambda ctx: [
            ctx.simnibs("101", "forward", f"sub-101_net-{_SOURCE_NET}{suffix}")
            for suffix in ("-fwd.fif", "-src.fif", "-morph.h5")
        ],
    ),
    Row(
        id="nifti_average",
        kind="nifti_average",
        behaviour=COMPLETED,
        subject="101,ernie,MNI152",
        why_subject="All three subjects have Simulations/L_Insula/TI/niftis/"
        "*_MNI_MNI_TI_max.nii.gz, the MNI-space input this kind averages.",
        build=lambda ctx: Submission(
            kind="nifti_average",
            config={
                "output_name": ctx.name("avg"),
                "space": "mni",
                "subjects": [dict(s, group="Group1") for s in _STATS_SUBJECTS],
            },
            subject_ids=[],
        ),
        budget_s=600.0,
        banner=(r"^nifti_average$", r"Loading 3 subject/simulation NIfTIs"),
        creates=lambda ctx: [
            ctx.ti_toolbox("nifti_average", ctx.name("avg")),
            # The per-kind parent too: on a project that has never run this kind the runner
            # creates it, and removing only the run directory strands an empty one (measured
            # 2026-09-03). Claimed second, so a parent that already existed is left alone.
            ctx.ti_toolbox("nifti_average"),
        ],
        payload_rename=_rename_nifti_average_payload,
    ),
    Row(
        id="stats_group",
        kind="stats",
        behaviour=COMPLETED,
        subject="101,ernie,MNI152",
        why_subject="The same three MNI-space L_Insula runs; two responders vs one "
        "non-responder is the largest unpaired design Dataset 000 can express.",
        build=lambda ctx: Submission(
            kind="stats",
            config={
                "_type": "GroupComparisonConfig",
                "analysis_name": ctx.name("stats"),
                "subjects": [
                    dict(_STATS_SUBJECTS[0], response=1),
                    dict(_STATS_SUBJECTS[1], response=1),
                    dict(_STATS_SUBJECTS[2], response=0),
                ],
                "test_type": "unpaired",
                "space": "mni",
                "n_permutations": 50,
                "n_jobs": 1,
            },
            subject_ids=[],
        ),
        budget_s=600.0,
        banner=(r"^group_comparison$", r"CLUSTER-BASED PERMUTATION TESTING"),
        creates=lambda ctx: [
            ctx.ti_toolbox("stats", "group_comparison", ctx.name("stats")),
            ctx.ti_toolbox("stats", "group_comparison"),
            ctx.ti_toolbox("stats"),
        ],
        payload_rename=_rename_stats_payload,
        notes="§3 allows a readable refusal here (a 2-vs-1 design may be rejected); the test "
        "accepts either, and the table records which happened.",
    ),
    Row(
        id="nilearn",
        kind="nilearn",
        behaviour=COMPLETED,
        subject="ernie",
        why_subject="One MNI-space L_Insula NIfTI is all this kind plots; ernie's is the one "
        "the documentation figures use.",
        build=lambda ctx: Submission(
            kind="nilearn",
            config={
                "subject_simulation_pairs": [
                    {"subject_id": "ernie", "simulation_name": "L_Insula"}
                ],
                "subdir_name": ctx.name("nilearn"),
                # Percentile, not the 0.3 V/m default: ernie's MNI-space L_Insula TI_max peaks
                # at 0.138 V/m (measured), so the default absolute cutoff is above every voxel
                # and the run dies with "minvalue must be less than or equal to maxvalue"
                # (job 287e3e0c2eb94134). A percentile is data-driven and cannot do that.
                "use_percentiles": True,
                "min_cutoff": 95.0,
            },
            subject_ids=[],
        ),
        budget_s=300.0,
        banner=(r"^nilearn_visuals$", r"Loading 1 subject/simulation NIfTIs"),
        creates=lambda ctx: [
            ctx.ti_toolbox("nilearn_visuals", ctx.name("nilearn")),
            ctx.ti_toolbox("nilearn_visuals"),
        ],
        payload_rename=_rename_nilearn_payload,
    ),
    Row(
        id="blender",
        kind="blender",
        behaviour=COMPLETED,
        subject="ernie",
        why_subject="`docs_example` is an ernie simulation with a montage the blender exporter "
        "can read. §3 assumed bpy under emulation would need started-then-cancel; measured, the "
        "montage export finishes in ~110 s (job d397adbe7bf24501), so cancelling it is a race "
        "against its own success -- this row runs it to completion instead.",
        build=lambda ctx: Submission(
            kind="blender",
            config={
                "_type": "MontageConfig",
                "subject_id": "ernie",
                "simulation_name": "docs_example",
                "output_dir": ctx.ti_toolbox("visual_exports", ctx.name("blender")),
            },
            subject_ids=["ernie"],
        ),
        budget_s=300.0,
        banner=(r"^MontageConfig$", r"Starting electrode placement for subject ernie"),
        creates=lambda ctx: [ctx.ti_toolbox("visual_exports", ctx.name("blender"))],
    ),
    Row(
        id="tools_electrode_overlay",
        kind="tools",
        behaviour=COMPLETED,
        subject="ernie",
        why_subject="Simulations/L_Insula/documentation/config.json is a real saved sim config "
        "with label electrode pairs, and m2m_ernie/eeg_positions holds the net CSV it needs.",
        plannable=False,
        build=lambda ctx: Submission(
            kind="tools",
            config={
                "module": "tit.tools.electrode_overlay",
                "args": [
                    ctx.simnibs(
                        "ernie", "Simulations", "L_Insula", "documentation", "config.json"
                    ),
                    ctx.simnibs(
                        "ernie",
                        "Simulations",
                        "L_Insula",
                        "TI",
                        "niftis",
                        "grey_L_Insula_TI_subject_TI_max.nii.gz",
                    ),
                    ctx.ti_toolbox("visual_exports", ctx.name("overlay"), "overlay.nii"),
                    "--eeg-positions-dir",
                    ctx.simnibs("ernie", "m2m_ernie", "eeg_positions"),
                ],
            },
            subject_ids=[],
        ),
        budget_s=300.0,
        no_banner_reason="tit.tools.electrode_overlay is a silent one-shot script: it writes "
        "the NIfTI and exits 0 with an empty stdout (measured, job cc95facbadf84dee).",
        creates=lambda ctx: [ctx.ti_toolbox("visual_exports", ctx.name("overlay"))],
        expect_files=lambda ctx: [
            ctx.ti_toolbox("visual_exports", ctx.name("overlay"), "overlay.nii")
        ],
        notes="`tools` is outside PipelineKind, so /api/validate and /api/plan 404 by design.",
    ),
    Row(
        id="project_init",
        kind="project_init",
        behaviour=COMPLETED,
        subject="(project)",
        why_subject="Project-level and idempotent: it scaffolds the BIDS skeleton Dataset 000 "
        "already has, so a green run creates nothing new.",
        plannable=False,
        build=lambda ctx: Submission(
            kind="project_init",
            config={"example_data": False},
            subject_ids=[],
        ),
        budget_s=60.0,
        banner=(r"Project initialization: Started", r"Project structure ready"),
        notes="Known broken before this program: tit.project_init is a package with no "
        "__main__ (job 5d0c6180a8004f49).",
    ),
)


def rows_for(ids: list[str] | None) -> list[Row]:
    """Rows named by *ids* (row id, or a kind that selects every row of that kind)."""
    if not ids:
        return list(ROWS)
    wanted = {i.strip() for i in ids if i.strip()}
    picked = [r for r in ROWS if r.id in wanted or r.kind in wanted]
    unknown = wanted - {r.id for r in ROWS} - {r.kind for r in ROWS}
    if unknown:
        raise SystemExit(
            f"unknown smoke kind(s): {sorted(unknown)}; "
            f"known rows: {sorted(r.id for r in ROWS)}"
        )
    return picked
