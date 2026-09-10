"""HTTP client for the Level A smoke harness -- stdlib ``urllib`` only.

What this pins
--------------
Nothing on its own; it is the transport every row of :mod:`tests.smoke.matrix` runs over.

Why stdlib only (the failure it prevents)
-----------------------------------------
``dev/smoke.sh`` runs on the *host* Python 3, which has no ``requests`` and no project
virtualenv -- a third-party dependency here would make the harness un-runnable in exactly the
situation it exists for (a maintainer with a container up and nothing else installed).

Why bearer, never the session cookie
------------------------------------
``tit/server/auth.py``: a matching ``Authorization: Bearer`` is exempt from the CSRF origin
check, a cookie is not. A cookie-authenticated ``POST /api/jobs`` from a script has no
``Origin`` header and is refused 403 by design, so the harness would be testing the auth path
rather than the pipeline.

Reproduce
---------
``dev/smoke.sh`` (or ``TIT_SMOKE_SERVER_URL=... TIT_SMOKE_TOKEN=... pytest -m smoke tests/smoke``).

Deliberately elsewhere: config shapes (:mod:`tests.smoke.matrix`), path bookkeeping
(:mod:`tests.smoke.cleanup`), the assertions (:mod:`tests.smoke.test_kinds`).

Written 2026-09-03 (lane S1).
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

#: States a job can never leave.
TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled", "skipped", "lost"})


class SmokeHTTPError(RuntimeError):
    """A non-2xx response, carrying the body so an assertion can quote the server's reason."""

    def __init__(self, method: str, url: str, status: int, body: str) -> None:
        super().__init__(f"{method} {url} -> HTTP {status}: {body[:800]}")
        self.method = method
        self.url = url
        self.status = status
        self.body = body


@dataclass
class Response:
    status: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def json(self) -> Any:
        return json.loads(self.text) if self.text else None


class SmokeClient:
    """Thin ``tit.server`` client: request, poll, tail.

    Parameters
    ----------
    base_url : str
        e.g. ``http://127.0.0.1:8765`` (trailing slash tolerated).
    token : str
        ``TIT_SERVER_TOKEN`` of the target server.
    timeout : float
        Per-request socket timeout in seconds. Deliberately generous: ``POST /api/plan/ex``
        counts the whole search space, and ``POST /api/jobs/<id>/cancel`` blocks for the
        SIGTERM grace period (``tit.jobs.runner.DEFAULT_GRACE_S`` = 10 s).
    """

    def __init__(self, base_url: str, token: str, timeout: float = 45.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        #: every (method, path, status, seconds) this client performed -- the notes' evidence.
        self.calls: list[tuple[str, str, int, float]] = []

    # -- transport ---------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        params: dict[str, Any] | None = None,
        expect: tuple[int, ...] | None = None,
    ) -> Response:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}
            )
        data = None
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "*/*"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        started = time.monotonic()
        out = Response(0, "")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", "replace")
                out = Response(resp.status, text, dict(resp.headers))
        except urllib.error.HTTPError as exc:  # 4xx/5xx still carry a body worth reading
            text = exc.read().decode("utf-8", "replace")
            out = Response(exc.code, text, dict(exc.headers or {}))
        finally:
            self.calls.append((method, path, out.status, time.monotonic() - started))
        if expect is not None and out.status not in expect:
            raise SmokeHTTPError(method, url, out.status, out.text)
        return out

    def get(self, path: str, params: dict[str, Any] | None = None, expect=(200,)) -> Response:
        return self.request("GET", path, params=params, expect=expect)

    def post(self, path: str, body: Any = None, expect=(200, 201)) -> Response:
        return self.request("POST", path, body=body, expect=expect)

    # -- routes used by the harness ----------------------------------------------------

    def health(self) -> dict:
        return self.get("/api/health").json

    def validate(self, kind: str, config: dict) -> dict:
        return self.post(f"/api/validate/{kind}", {"config": config}, expect=(200,)).json

    def plan(self, kind: str, body: dict) -> dict:
        return self.post(f"/api/plan/{kind}", body, expect=(200,)).json

    def submit(self, body: dict) -> dict:
        return self.post("/api/jobs", body, expect=(201,)).json

    def submit_group(self, body: dict) -> dict:
        return self.post("/api/jobs/groups", body, expect=(201,)).json

    def jobs(self, **params: Any) -> list[dict]:
        return self.get("/api/jobs", params=params).json

    def job(self, job_id: str) -> dict:
        """``{spec, status, artifacts}`` for one job."""
        return self.get(f"/api/jobs/{job_id}").json

    def status(self, job_id: str) -> dict:
        return self.job(job_id)["status"]

    def log(self, job_id: str, tail: int | None = 400) -> str:
        return self.get(f"/api/jobs/{job_id}/log", params={"tail": tail}).text

    def events(self, job_id: str, since: int = 0) -> list[dict]:
        return self.get(f"/api/jobs/{job_id}/events", params={"since": since}).json

    def cancel(self, job_id: str) -> dict:
        return self.post(f"/api/jobs/{job_id}/cancel", expect=(200,)).json

    def system(self) -> dict:
        return self.get("/api/system").json

    def catalog(self, path: str, **params: Any) -> Any:
        return self.get(f"/api/catalog/{path.lstrip('/')}", params=params).json

    def artifact_head(self, container_path: str) -> int:
        """Status of ``GET /api/files/artifact?path=...`` -- the server's own view of a file.

        An independent reader of the artifact list: the host filesystem check in
        :mod:`tests.smoke.cleanup` and this route resolve the same path through different
        code (``os.stat`` on the bind mount vs. the server's jail + allow-list), so a
        disagreement is a real finding rather than one reader agreeing with itself.
        """
        return self.request(
            "GET", "/api/files/artifact", params={"path": container_path}
        ).status

    # -- polling helpers ---------------------------------------------------------------

    def wait_for(
        self,
        job_id: str,
        states: set[str],
        timeout: float,
        poll: float = 1.0,
    ) -> tuple[dict, float]:
        """Poll until the job's state is in *states* (or terminal), or *timeout* elapses.

        Returns ``(status, elapsed_s)``. A terminal state always ends the wait even when it is
        not in *states* -- waiting 120 s for ``running`` on a job that already failed teaches
        nothing and wastes the matrix's budget.
        """
        deadline = time.monotonic() + timeout
        started = time.monotonic()
        status = self.status(job_id)
        while True:
            if status["state"] in states or status["state"] in TERMINAL_STATES:
                return status, time.monotonic() - started
            if time.monotonic() >= deadline:
                return status, time.monotonic() - started
            time.sleep(poll)
            status = self.status(job_id)

    def wait_for_banner(
        self, job_id: str, patterns: list[str], timeout: float, poll: float = 1.0
    ) -> tuple[str | None, str, float]:
        """Poll the log + events until one *pattern* matches.

        Returns ``(matched_pattern_or_None, evidence_line, elapsed_s)``. Events are searched as
        well as the raw log because several runners emit their first stage as a structured
        event before any stdout line appears (``tit.pre``: ``{"type":"stage","stage":
        "preprocessing"}`` at seq 0, before ``Beginning pre-processing``).
        """
        compiled = [(p, re.compile(p)) for p in patterns]
        deadline = time.monotonic() + timeout
        started = time.monotonic()
        while True:
            haystack_lines = self.log(job_id, tail=400).splitlines()
            for event in self.events(job_id):
                text = event.get("msg") or event.get("stage") or ""
                if text:
                    haystack_lines.append(f"[{event.get('type')}] {text}")
            for raw, rx in compiled:
                for line in haystack_lines:
                    if rx.search(line):
                        return raw, line.strip(), time.monotonic() - started
            state = self.status(job_id)["state"]
            if time.monotonic() >= deadline or (
                state in TERMINAL_STATES and state != "running"
            ):
                # One last read after a terminal state: the tailer may still have been
                # flushing when the state flipped.
                if state in TERMINAL_STATES:
                    time.sleep(0.5)
                    final = self.log(job_id, tail=400).splitlines()
                    for raw, rx in compiled:
                        for line in final:
                            if rx.search(line):
                                return raw, line.strip(), time.monotonic() - started
                return None, "\n".join(haystack_lines[-15:]), time.monotonic() - started
            time.sleep(poll)

    def runner_pids_for(self, job_id: str) -> list[dict]:
        """Processes in ``GET /api/system`` whose command line still names *job_id*.

        ``tit.jobs.manager._runner_config_path`` passes ``<project>/code/ti-toolbox/jobs/<id>/
        config.json`` as the runner's argv[3], so the job id is literally in the command line
        of every live runner -- this is how "no runner pid left after cancel" is checked
        without guessing at process names.
        """
        procs = self.system().get("processes") or []
        return [p for p in procs if job_id in (p.get("cmdline") or "")]
