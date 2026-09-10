"""One parametrized test per row of :mod:`tests.smoke.matrix` (decisions P4-P8).

What this pins
--------------
The three-legged behaviour contract of §3, for every kind:

``accepted``   ``POST /api/validate/{kind}`` ok, ``POST /api/plan/{kind}`` >= 1 job and no lock
               conflicts, ``POST /api/jobs`` (or ``/api/jobs/groups`` for ``pre``) 201 -- all
               inside 10 s.
``started``    the job reaches ``running`` within 120 s and its log or events carry the runner's
               own banner / first stage event.
``completed``  succeeded inside the row's budget; every artifact the job reports exists on disk
               *and* the server's own ``/api/files/artifact`` agrees; the matching catalog route
               lists the new output.
``cancelled``  for the long kinds: cancel reaches ``cancelled`` in <= 15 s with no runner pid
               left in ``GET /api/system``.
``refused``    for a row that cannot run on this data: the job fails with a human-readable
               message and no Python traceback in ``error.message``.

Where the numbers come from
---------------------------
Budgets and the accept/start/cancel ceilings are §3's, restated in :mod:`tests.smoke.matrix`.
Artifact existence is read twice by two different readers -- the host filesystem through the
bind mount, and the server's own jailed file route -- so neither reader is checked against
itself.

How to reproduce
----------------
``dev/smoke.sh``  (or ``TIT_SMOKE_SERVER_URL=… TIT_SMOKE_TOKEN=… TIT_SMOKE_PROJECT_HOST=… \\
python3 -m pytest -m smoke tests/smoke -p no:cacheprovider``).

Deliberately elsewhere: the configs (:mod:`tests.smoke.matrix`), HTTP (
:mod:`tests.smoke.client`), path bookkeeping (:mod:`tests.smoke.cleanup`).

Written 2026-09-03 (lane S1).
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import pytest

from tests.smoke.cleanup import Manifest
from tests.smoke.client import SmokeClient, SmokeHTTPError
from tests.smoke.matrix import (
    ACCEPT_BUDGET_S,
    CANCEL_BUDGET_S,
    COMPLETED,
    REFUSED,
    ROWS,
    START_BUDGET_S,
    STARTED_THEN_CANCEL,
    Ctx,
    Row,
    Submission,
    rows_for,
)

PAYLOAD_DIR = os.path.join(os.path.dirname(__file__), "payloads")

#: Markers of a Python traceback leaking into a user-facing message (the readability contract).
_TRACEBACK_MARKERS = (
    "Traceback (most recent call last)",
    'File "',
    "  ^^^^",
)


# ---------------------------------------------------------------------------------------------
# Payload loading: lane S2's recorded UI body wins over the hand-built config (decision P5)
# ---------------------------------------------------------------------------------------------


def payload_path_for(row: Row) -> str | None:
    """``payloads/<row id>.json`` (or its hyphenated spelling), else ``payloads/<kind>.json``.

    The kind-level fallback is deliberately narrow. Several rows can share a kind and differ in
    exactly the thing the payload fixes (``sim_ti``/``sim_mti``; the six ``pre`` stages), so a
    single ``sim.json`` replayed by both sim rows submits the same montage name twice and the
    second job dies on SimNIBS's own "Found already existing simulation results in directory"
    (measured 2026-09-03, job caad925a2e9c4142); a single ``pre.json`` recorded from one page
    encodes one stage combination, and every other ``pre`` row then looks for a stage tag the
    group does not contain. So the fallback applies only to the first row of its kind, and never
    to a row that selects a job by tag.
    """
    exact = [f"{row.id}.json", f"{row.id.replace('_', '-')}.json"]
    first_of_kind = next(r for r in ROWS if r.kind == row.kind).id == row.id
    if first_of_kind and row.group_tag is None:
        exact.append(f"{row.kind}.json")
    for name in exact:
        candidate = os.path.join(PAYLOAD_DIR, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def submission_from_payload(row: Row, raw: dict[str, Any]) -> Submission:
    """Rebuild a :class:`Submission` from a recorded request body or a bare config.

    A recorded body is whatever the renderer POSTed: ``{"kind","config","subject_ids", …}`` for
    ``/api/jobs``, plus ``parallel_subjects`` for ``/api/jobs/groups``. A file holding only the
    config object is accepted too (that is all a page needs to record for the simple kinds).
    """
    if "config" in raw and isinstance(raw["config"], dict):
        config = raw["config"]
        subject_ids = list(raw.get("subject_ids") or [])
        group = "parallel_subjects" in raw or raw.get("kind") == "pre"
        return Submission(
            kind=raw.get("kind", row.kind),
            config=config,
            subject_ids=subject_ids,
            tags=list(raw.get("tags") or []),
            group=bool(group),
            parallel_subjects=int(raw.get("parallel_subjects") or 1),
            plan_extra={
                k: raw[k] for k in ("montage_sources", "parallel_subjects") if k in raw
            },
        )
    return Submission(kind=row.kind, config=raw, subject_ids=[])


def load_submission(row: Row, ctx: Ctx) -> tuple[Submission, str, str]:
    """``(submission, source, origin)`` -- ``source`` is ``payload`` or ``builtin``.

    ``row.payload_rename``, when set, is applied here -- and only here, to a payload -- before
    the config is used for anything: rewrites the field(s) that name a fixed output (an
    ``analysis_name``, a montage ``name``, ...) to this session's own ``smoke-<runid>`` tag, so
    a payload recorded once can be replayed in any future session without the second replay
    finding the first replay's own output and skipping (decision P6, HX finding 2026-09-04). See
    the functions above each affected row in ``tests/smoke/matrix.py`` for exactly which field.
    """
    path = payload_path_for(row)
    if path:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        if row.payload_rename is not None:
            target = raw["config"] if "config" in raw and isinstance(raw["config"], dict) else raw
            row.payload_rename(target, ctx, row)
        return submission_from_payload(row, raw), "payload", os.path.basename(path)
    return row.build(ctx), "builtin", "tests/smoke/matrix.py"


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------


def _first_traceback_line(status: dict) -> str:
    lines = (status.get("error") or {}).get("last_lines") or []
    for line in lines:
        if line.strip().startswith(("Traceback", "  File ")):
            return line.strip()
    return (lines[-1].strip() if lines else "") or (status.get("error") or {}).get(
        "message", ""
    )


def _error_summary(status: dict) -> str:
    err = status.get("error") or {}
    tail = (err.get("last_lines") or [])[-1:]
    return f"{err.get('type', '')}: {err.get('message', '')} | {tail}"[:400]


def _submit(client: SmokeClient, sub: Submission) -> list[dict]:
    """Submit and return every job created (one for /api/jobs, the DAG for a group)."""
    if sub.group:
        body = {
            "kind": "pre",
            "config": sub.config,
            "subject_ids": sub.subject_ids,
            "parallel_subjects": sub.parallel_subjects,
        }
        return client.submit_group(body)["jobs"]
    body = {
        "kind": sub.kind,
        "config": sub.config,
        "subject_ids": sub.subject_ids,
        "tags": sub.tags,
    }
    return [client.submit(body)]


class _MissingGroupTag(AssertionError):
    """The submitted group has no job with this row's stage tag."""


def _pick_job(jobs: list[dict], client: SmokeClient, row: Row) -> dict:
    """The job of a submission this row is about (a group submits several)."""
    if row.group_tag is None or len(jobs) == 1:
        return jobs[0]
    for job in jobs:
        spec = client.job(job["id"])["spec"]
        if row.group_tag in (spec.get("tags") or []):
            return job
    raise _MissingGroupTag(
        f"no job tagged {row.group_tag!r} in the submitted group "
        f"({[client.job(j['id'])['spec'].get('tags') for j in jobs]})"
    )


def _wait_no_heavy_job(client: SmokeClient, timeout: float = 900.0) -> None:
    """Block until no other job is running/queued (decision P7 -- one heavy job at a time).

    Other lanes submit to the same server; two emulated FEM solves fight for the same cores
    until both time out, which looks like a harness failure and is not one.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        busy = [j for j in client.jobs(limit=50) if j["state"] in ("running", "queued")]
        if not busy:
            return
        time.sleep(3.0)
    pytest.skip(
        "skipping: another job has been running/queued on the shared dev container for "
        f"{timeout:.0f} s; refusing to start a second heavy job (decision P7)"
    )


def _cancel_leftovers(client: SmokeClient, jobs: list[dict]) -> None:
    for job in jobs:
        try:
            state = client.status(job["id"])["state"]
            if state in ("queued", "running"):
                client.cancel(job["id"])
        except (SmokeHTTPError, OSError):
            pass


# ---------------------------------------------------------------------------------------------
# the test
# ---------------------------------------------------------------------------------------------


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "row" in metafunc.fixturenames:
        selected = rows_for(
            [k for k in metafunc.config.getoption("--smoke-kinds").split(",") if k]
        )
        metafunc.parametrize("row", selected, ids=[r.id for r in selected])


@pytest.mark.smoke
def test_kind(
    row: Row,
    smoke_client: SmokeClient,
    smoke_ctx: Ctx,
    smoke_manifest: Manifest,
    smoke_results: list[dict],
    request: pytest.FixtureRequest,
) -> None:
    client, ctx = smoke_client, smoke_ctx
    full = bool(request.config.getoption("--smoke-full"))
    behaviour = row.behaviour
    if full and behaviour == STARTED_THEN_CANCEL:
        behaviour = COMPLETED
    submission, source, origin = load_submission(row, ctx)
    record: dict[str, Any] = {
        "row": f"{row.kind} ({row.id})",
        "subject": row.subject,
        "behaviour": behaviour,
        "source": f"{source}: {origin}",
        "result": "not run",
        "wall": 0.0,
        "evidence": "",
    }
    smoke_results.append(record)
    started_at = time.monotonic()
    jobs: list[dict] = []
    planned_dirs: list[str] = []
    # A little slack for host/container clock skew when deciding "this run wrote that file".
    job_started_epoch = time.time() - 5.0

    try:
        # ---- accepted -------------------------------------------------------------------
        accept_t0 = time.monotonic()
        for path in row.creates(ctx):
            smoke_manifest.claim(row.id, path)
        if row.plannable:
            result = client.validate(submission.kind, submission.config)
            assert result["ok"], (
                f"{row.id}: POST /api/validate/{submission.kind} rejected the config: "
                f"{result['errors']}"
            )
            plan_body: dict[str, Any] = {
                "config": submission.config,
                "subject_ids": submission.subject_ids,
            }
            plan_body.update(submission.plan_extra)
            plan = client.plan(submission.kind, plan_body)
            assert plan["jobs"], f"{row.id}: plan returned no jobs ({plan['warnings']})"
            # Claim what *this submission* will write, not only what the built-in config would:
            # a recorded UI payload names its own output (S2's analyzer payload has
            # output_dir=null, so the runner derives Analyses/Mesh/sphere_x…), and without
            # this the run would be left on disk after the session.
            planned_dirs = [j["output_dir"] for j in plan["jobs"] if j["output_dir"]]
            for planned_dir in planned_dirs:
                smoke_manifest.claim(row.id, planned_dir)
            assert not plan["lock_conflicts"], (
                f"{row.id}: plan reports lock conflicts, another job holds this output: "
                f"{plan['lock_conflicts']}"
            )
            # P6: never overwrite a pre-existing output. A builtin config is namespaced
            # smoke-<runid>, so an existing output means the namespacing is broken; a recorded
            # UI payload may legitimately name a real run, which is a skip, not a failure.
            #
            # Only the row's *own* claimed outputs can be judged for `pre`: that plan is one
            # job per stage, and "several stages share a directory with other content" (see
            # tit/server/routes/plan.py's docstring) -- derivatives/ti-toolbox/reports and
            # m2m_<subject>/ exist for every project, so `exists` there says nothing about
            # this row.
            owned = set(row.creates(ctx))
            existing = [j["output_dir"] for j in plan["jobs"] if j["exists"]]
            judgeable = (
                [d for d in existing if d in owned]
                if (owned or submission.kind == "pre")
                else existing
            )
            if judgeable and source == "payload":
                pytest.skip(
                    f"skipping: recorded payload {origin} targets existing output(s) "
                    f"{judgeable}; refusing to overwrite (decision P6)"
                )
            assert not judgeable, (
                f"{row.id}: the harness's own config targets existing output(s) {judgeable}; "
                "smoke outputs must be namespaced (decision P6)"
            )
        else:
            with pytest.raises(SmokeHTTPError) as excinfo:
                client.validate(submission.kind, submission.config)
            assert excinfo.value.status == 404, (
                f"{row.id}: kind {submission.kind!r} is outside PipelineKind, so "
                f"/api/validate must 404; got {excinfo.value.status}"
            )

        # Stop the clock before the politeness wait: `_wait_no_heavy_job` blocks on *another
        # lane's* job finishing on the shared container, which has nothing to do with how long
        # this server takes to accept a submission (measured 2026-09-03: a 42.2 s "accepted
        # leg" that was 41 s of waiting for someone else's analyzer job).
        accept_s = time.monotonic() - accept_t0
        if row.heavy or behaviour == COMPLETED:
            _wait_no_heavy_job(client)

        submit_t0 = time.monotonic()
        jobs = _submit(client, submission)
        accept_s += time.monotonic() - submit_t0
        assert accept_s <= ACCEPT_BUDGET_S, (
            f"{row.id}: accepted leg took {accept_s:.1f}s, budget {ACCEPT_BUDGET_S}s"
        )
        try:
            job = _pick_job(jobs, client, row)
        except _MissingGroupTag as exc:
            if source == "payload":
                # A recorded payload for one stage cannot exercise another stage's row.
                pytest.skip(f"skipping: {origin} {exc}")
            raise AssertionError(f"{row.id}: {exc}") from exc
        job_id = job["id"]
        record["evidence"] = f"job {job_id}"

        # ---- started --------------------------------------------------------------------
        status, to_running = client.wait_for(job_id, {"running"}, START_BUDGET_S)
        assert status["started_at"] or status["state"] != "queued", (
            f"{row.id}: job {job_id} never left `queued` in {START_BUDGET_S}s "
            f"(waiting_on={status['waiting_on']})"
        )
        assert status["state"] != "queued", (
            f"{row.id}: job {job_id} still queued after {to_running:.1f}s: "
            f"waiting_on={status['waiting_on']}"
        )

        if behaviour != REFUSED and row.banner:
            pattern, evidence, banner_s = client.wait_for_banner(
                job_id, list(row.banner), START_BUDGET_S
            )
            assert pattern is not None, (
                f"{row.id}: job {job_id} produced no banner matching {row.banner} within "
                f"{START_BUDGET_S}s. Last output:\n{evidence}"
            )
            record["evidence"] = f"job {job_id}; banner {pattern!r} at {banner_s:.1f}s"

        # ---- the row's own behaviour ----------------------------------------------------
        if behaviour == STARTED_THEN_CANCEL:
            client.cancel(job_id)
            status, cancel_s = client.wait_for(job_id, {"cancelled"}, CANCEL_BUDGET_S, poll=0.5)
            assert status["state"] == "cancelled", (
                f"{row.id}: cancel left job {job_id} in {status['state']!r} after "
                f"{cancel_s:.1f}s: {_error_summary(status)}"
            )
            assert cancel_s <= CANCEL_BUDGET_S, (
                f"{row.id}: cancel took {cancel_s:.1f}s, budget {CANCEL_BUDGET_S}s"
            )
            leftover = client.runner_pids_for(job_id)
            assert not leftover, (
                f"{row.id}: runner process(es) still alive after cancel: "
                f"{[p.get('cmdline') for p in leftover]}"
            )
            record["result"] = f"cancelled in {cancel_s:.1f}s, no runner pid"

        elif behaviour == REFUSED:
            status, wall = client.wait_for(job_id, {"failed"}, row.budget_s)
            assert status["state"] == "failed", (
                f"{row.id}: expected a readable refusal, got state {status['state']!r} "
                f"after {wall:.1f}s"
            )
            message = (status.get("error") or {}).get("message", "")
            assert not any(m in message for m in _TRACEBACK_MARKERS), (
                f"{row.id}: error.message leaks a Python traceback: {message!r}"
            )
            body = "\n".join((status.get("error") or {}).get("last_lines") or [])
            body += "\n" + client.log(job_id, tail=200)
            matched = [p for p in row.refusal if re.search(p, body)]
            assert matched, (
                f"{row.id}: no readable refusal matching {row.refusal} in the job's output. "
                f"Tail:\n{body[-1200:]}"
            )
            assert "Traceback (most recent call last)" not in body, (
                f"{row.id}: the refusal is a raw traceback, not a message:\n{body[-1200:]}"
            )
            record["result"] = f"refused readably in {wall:.1f}s ({matched[0]})"

        else:  # COMPLETED
            status, wall = client.wait_for(job_id, {"succeeded"}, row.budget_s, poll=2.0)
            if row.id == "stats_group" and status["state"] == "failed":
                # §3 allows a readable refusal here (2-vs-1 unpaired design).
                message = (status.get("error") or {}).get("message", "")
                assert not any(m in message for m in _TRACEBACK_MARKERS), (
                    f"{row.id}: error.message leaks a Python traceback: {message!r}"
                )
                record["result"] = f"readable refusal in {wall:.1f}s: {_error_summary(status)}"
                return
            assert status["state"] == "succeeded", (
                f"{row.id}: job {job_id} ended {status['state']!r} after {wall:.1f}s "
                f"(budget {row.budget_s}s). {_error_summary(status)} "
                f"first traceback line: {_first_traceback_line(status)!r}"
            )
            detail = client.job(job_id)
            artifacts = [a["path"] for a in detail["artifacts"]]
            # `expect_files` describes the *built-in* config's output paths; a recorded UI
            # payload writes wherever its own config says, so only the job's reported
            # artifacts can be checked for it.
            expected = [] if source == "payload" else row.expect_files(ctx)
            missing_host = [
                p
                for p in artifacts + expected
                if not os.path.exists(smoke_manifest.host_path(p))
            ]
            assert not missing_host, (
                f"{row.id}: job reports artifacts that are not on disk: {missing_host}"
            )
            # Second reader: the server's own jailed file route, for the extensions it serves.
            servable = [
                p for p in artifacts if os.path.splitext(p)[1].lower()
                in {".pdf", ".png", ".csv", ".json", ".txt", ".html"}
            ]
            unserved = [p for p in servable if client.artifact_head(p) != 200]
            assert not unserved, (
                f"{row.id}: /api/files/artifact cannot serve reported artifact(s) {unserved} "
                "(the host filesystem sees them, the server does not)"
            )
            # For a payload run the row's own `creates` paths are never written; the plan's
            # output_dir is where that submission actually put things.
            own_paths = planned_dirs if source == "payload" else row.creates(ctx)
            created = [
                p
                for p in own_paths
                if not smoke_manifest.claim(row.id, p).pre_existed
            ]
            gone = [p for p in created if not os.path.exists(smoke_manifest.host_path(p))]
            assert not gone, (
                f"{row.id}: job succeeded but claimed output path(s) {gone} do not exist"
            )
            # Non-emptiness is only *evidence of work* where there is no other evidence. A row
            # that named artifact files, or whose job reported artifacts, has already proved
            # more than "the directory is not empty"; and some claimed paths are scaffolding a
            # stage creates on the way (pre_dicom's derivatives/SimNIBS/sub-102 is an empty
            # subject folder by design, measured 2026-09-03).
            if not artifacts and not expected:
                empty = [
                    p
                    for p in created
                    if os.path.isdir(smoke_manifest.host_path(p))
                    and not os.listdir(smoke_manifest.host_path(p))
                ]
                assert not empty, (
                    f"{row.id}: job succeeded but its only evidence, output path(s) {empty}, "
                    "are empty"
                )
            if row.catalog is not None and source != "payload":
                # The catalog check looks for the harness's own smoke-<runid> name; a payload
                # names its own output, so the check would be asking the wrong question.
                ok, evidence = row.catalog(client, ctx)
                assert ok, f"{row.id}: catalog does not list the new output -- {evidence}"
                record["evidence"] += "; catalog ok"
            elif row.catalog is not None:
                record["evidence"] += "; catalog check skipped (payload names its own output)"
            record["result"] = (
                f"succeeded in {wall:.1f}s, {len(artifacts)} artifact(s)"
            )
    finally:
        record["wall"] = time.monotonic() - started_at
        if jobs:
            _cancel_leftovers(client, jobs)
            # Claim every file *any* job of this submission produced into a shared,
            # pre-existing directory. Not just the row's own job: a `pre` group's G1 stage
            # writes its own preprocessing report beside the trailing report job's, and only
            # the latter was cleaned up before this loop existed (measured 2026-09-03: one
            # stray pre_processing_report_*.html per run in reports/sub-102).
            for other in jobs:
                try:
                    for artifact in client.job(other["id"])["artifacts"]:
                        smoke_manifest.claim_produced(
                            row.id, artifact["path"], job_started_epoch
                        )
                except (SmokeHTTPError, OSError, KeyError):
                    pass
        if record["result"] == "not run":
            record["result"] = "FAILED"
