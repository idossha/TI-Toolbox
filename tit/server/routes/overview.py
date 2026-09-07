"""``GET /api/catalog/overview`` -- the project Overview page's one aggregate read.

R1 of ``docs/dev/v3-implementation-plan.md``. The page this serves replaced the
Subjects page, and with it a request fan-out that grew with the project: one
``/api/catalog/subjects/{id}`` per subject plus five output lists per subject
plus one analyses list per simulation, capped in the renderer at 25 subjects
(``pages/results/useOutputs.ts``'s ``EAGER_SUBJECT_LIMIT``) so that a larger
project silently showed no counts at all.

Everything here is a thin aggregation over :mod:`tit.catalog` -- discovery
rules (what makes a subject, which run directories count) stay there on top of
:class:`tit.paths.PathManager` and are never re-implemented, here or in TS.

Import cost: module level imports only ``fastapi`` plus this package's own
schemas; :mod:`tit.catalog`, :mod:`tit.paths` and the job manager are imported
inside the handler, so this module stays far under
``dev/route_import_guard.py``'s 400 ms budget and does no filesystem work when
the server boots.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from tit.server.schemas import (
    Overview,
    OverviewCounts,
    OverviewCoverage,
    OverviewReadiness,
    OverviewSubject,
    OverviewTotals,
)

router = APIRouter()

#: Which job kinds would produce which Overview column. A queued/running job of
#: that kind for a subject makes the column ``pending``; the most recent job of
#: that kind having failed, with the artefact still absent, makes it ``failed``.
STAGE_JOB_KINDS: dict[str, tuple[str, ...]] = {
    "raw": ("pre",),
    "fastsurfer": ("pre",),
    "freesurfer": ("pre",),
    "m2m": ("pre",),
    "dwi": ("pre",),
    "ct": ("pre",),
    "leadfield": ("leadfield",),
}

_ACTIVE_STATES = ("queued", "waiting", "running")


def job_states_by_subject(jobs: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """``{subject: {job_kind: "pending" | "failed"}}`` from one job listing.

    ``jobs`` is the manager's own newest-first list, so the first terminal
    state seen for a (subject, kind) pair is the most recent one and later
    (older) entries never overwrite it. An active job always wins over an older
    failure: something is happening right now, which is what the column should
    say.
    """
    # The empty string records "the newest job of this kind here is terminal and
    # was not a failure" -- a succeeded rerun has to *clear* an older failure, not
    # be ignored by it. Dropped from the result below.
    seen: dict[str, dict[str, str]] = {}
    for job in jobs:
        kind = str(job.get("kind", ""))
        state = str(job.get("state", ""))
        value = (
            "pending"
            if state in _ACTIVE_STATES
            else ("failed" if state == "failed" else "")
        )
        for sid in job.get("subject_ids") or []:
            per_kind = seen.setdefault(str(sid), {})
            if kind in per_kind:
                if value == "pending":
                    per_kind[kind] = "pending"
                continue
            per_kind[kind] = value
    return {
        sid: {k: v for k, v in per_kind.items() if v}
        for sid, per_kind in seen.items()
        if any(per_kind.values())
    }


def presence(
    on: bool,
    *,
    partial: bool = False,
    column: str = "",
    job_states: dict[str, str] | None = None,
) -> str:
    """One column's :data:`tit.server.schemas.PresenceState`.

    On disk wins: an artefact that exists is ``present`` (or ``partial``) no
    matter what a job is doing. Only an absent artefact can be ``pending`` or
    ``failed``, which is what makes the four states answer different questions
    rather than three of them meaning "not there".
    """
    if on:
        return "present"
    if partial:
        return "partial"
    for kind in STAGE_JOB_KINDS.get(column, ()):
        state = (job_states or {}).get(kind)
        if state:
            return state
    return "absent"


def _readiness(row: dict[str, Any]) -> list[OverviewReadiness]:
    """The four workflow verbs for one subject, with the requirement that failed.

    Same rules as the page they feed used to compute in TS
    (``pages/subjects/readiness.ts``), moved server-side so the row and the
    project-wide readiness board cannot disagree.
    """
    checks = [
        (
            "preprocess",
            # A sourcedata-only subject belongs here: Pre-processing is the page
            # that runs the DICOM conversion stage.
            row["has_raw"] or row["has_sourcedata"],
            "no raw MRI",
        ),
        ("simulator", row["has_m2m"], "no head model"),
        (
            "optimizer",
            row["has_m2m"] and bool(row["leadfields"]),
            "no leadfield" if row["has_m2m"] else "no head model",
        ),
        ("analyzer", row["n_simulations"] > 0, "no simulations"),
    ]
    return [
        OverviewReadiness(stage=stage, ready=ok, reason=None if ok else reason)
        for stage, ok, reason in checks
    ]


def _counts(pm: Any, catalog: Any, sid: str, simulations: list[str]) -> OverviewCounts:
    """High-level output totals for one subject -- counts only, never a tree."""

    def n(value: Any) -> int:
        return len(value) if isinstance(value, list) else 0

    optimizations = 0
    for runs in (
        _safe(catalog.flex_runs, pm, sid),
        _safe(catalog.ex_runs, pm, sid, "ex"),
        _safe(catalog.ex_runs, pm, sid, "mex"),
    ):
        optimizations += n(runs)
    analyses = 0
    for sim in simulations:
        analyses += n(_safe(catalog.analyses, pm, sid, sim))
    return OverviewCounts(
        simulations=len(simulations), optimizations=optimizations, analyses=analyses
    )


def _safe(fn: Any, *args: Any) -> Any:
    """A broken run directory for one subject must not fail the whole page."""
    try:
        return fn(*args)
    except Exception:  # pragma: no cover - defensive, per-subject isolation
        return None


def build_overview(pm: Any, jobs: list[dict[str, Any]] | None = None) -> Overview:
    """Aggregate every Overview fact for the bound project. Pure over *pm*."""
    from tit import catalog

    by_subject = job_states_by_subject(jobs or [])
    rows: list[OverviewSubject] = []
    for entry in catalog.list_subjects(pm):
        sid = entry["id"]
        detail = _safe(catalog.subject_detail, pm, sid) or dict(entry)
        job_states = by_subject.get(sid, {})
        simulations = list(pm.list_simulations(sid))
        leadfields = list(detail.get("has_leadfields") or [])
        eeg_nets = list(detail.get("eeg_nets") or [])
        has_raw = bool(detail.get("has_raw"))
        has_sourcedata = bool(detail.get("has_sourcedata"))
        base = {
            "has_raw": has_raw,
            "has_sourcedata": has_sourcedata,
            "has_m2m": bool(detail.get("has_m2m")),
            "leadfields": leadfields,
            "n_simulations": len(simulations),
        }
        rows.append(
            OverviewSubject(
                id=sid,
                # Staged-but-not-converted raw data is `partial`, not `absent`:
                # the DICOMs are there, the BIDS directory is not.
                raw=presence(
                    has_raw,
                    partial=not has_raw and has_sourcedata,
                    column="raw",
                    job_states=job_states,
                ),
                fastsurfer=presence(
                    bool(detail.get("has_fastsurfer")),
                    column="fastsurfer",
                    job_states=job_states,
                ),
                freesurfer=presence(
                    bool(detail.get("has_freesurfer")),
                    column="freesurfer",
                    job_states=job_states,
                ),
                m2m=presence(
                    bool(detail.get("has_m2m")), column="m2m", job_states=job_states
                ),
                dwi=presence(
                    bool(detail.get("has_dwi")), column="dwi", job_states=job_states
                ),
                ct=presence(
                    bool(detail.get("has_ct")), column="ct", job_states=job_states
                ),
                # Some nets have a leadfield and some do not: `partial`, because
                # "has a leadfield" is per net, not per subject.
                leadfield=presence(
                    bool(leadfields) and len(leadfields) >= len(eeg_nets),
                    partial=bool(leadfields),
                    column="leadfield",
                    job_states=job_states,
                ),
                eeg_net=presence(bool(eeg_nets)),
                leadfields=leadfields,
                eeg_nets=eeg_nets,
                counts=_counts(pm, catalog, sid, simulations),
                readiness=_readiness(base),
            )
        )

    def have(pick: Any) -> int:
        return sum(1 for r in rows if pick(r))

    on = ("present", "partial")
    total = len(rows)
    return Overview(
        subjects=rows,
        totals=OverviewTotals(
            subjects=total,
            simulations=sum(r.counts.simulations for r in rows),
            optimizations=sum(r.counts.optimizations for r in rows),
            analyses=sum(r.counts.analyses for r in rows),
            coverage=[
                OverviewCoverage(
                    id="raw", have=have(lambda r: r.raw == "present"), total=total
                ),
                OverviewCoverage(
                    id="recon",
                    have=have(
                        lambda r: r.fastsurfer == "present" or r.freesurfer == "present"
                    ),
                    total=total,
                ),
                OverviewCoverage(
                    id="m2m", have=have(lambda r: r.m2m == "present"), total=total
                ),
                OverviewCoverage(
                    id="dwi", have=have(lambda r: r.dwi == "present"), total=total
                ),
                OverviewCoverage(
                    id="leadfield", have=have(lambda r: r.leadfield in on), total=total
                ),
            ],
        ),
    )


@router.get(
    "/api/catalog/overview",
    response_model=Overview,
    summary="Every Overview fact for the whole project, in one bounded request",
)
def overview(request: Request) -> Overview:
    from tit.paths import get_path_manager

    jobs: list[dict[str, Any]] = []
    try:
        from tit.jobs.bootstrap import get_manager

        jobs = get_manager(request.app).list_jobs()
    except Exception:  # pragma: no cover - no scheduler bound: presence only
        jobs = []
    return build_overview(get_path_manager(), jobs)
