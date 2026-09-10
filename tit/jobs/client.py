"""Notebook client for ``tit.jobs`` (TODO.md §2.3): submit into the *same* queue the desktop
app uses, over the local server's HTTP API — so a notebook and the GUI never race on the same
resource without the scheduler knowing about both.

Talks to ``tit.server`` over plain HTTP (stdlib ``urllib``, no new dependency); defaults come
from the same environment variables the server itself uses (``TIT_SERVER_URL``,
``TIT_SERVER_TOKEN``) so a notebook started alongside ``NOTEBOOK`` in-container needs no extra
configuration.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
ENV_BASE_URL = "TIT_SERVER_URL"
ENV_TOKEN = "TIT_SERVER_TOKEN"
TERMINAL_STATES = ("succeeded", "failed", "cancelled", "skipped", "lost")


class JobClientError(RuntimeError):
    """An HTTP call to ``tit.server`` failed (non-2xx, or the server is unreachable)."""


def _base_url(base_url: str | None) -> str:
    return (base_url or os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")


def _request(
    method: str,
    path: str,
    *,
    base_url: str | None = None,
    token: str | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> Any:
    url = f"{_base_url(base_url)}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    resolved_token = token or os.environ.get(ENV_TOKEN)
    if resolved_token:
        request.add_header("Authorization", f"Bearer {resolved_token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise JobClientError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise JobClientError(f"{method} {path} -> unreachable: {exc.reason}") from exc
    return json.loads(raw) if raw else None


def submit(
    kind: str,
    config: dict[str, Any],
    subject_ids: list[str],
    *,
    after: list[str] | None = None,
    tags: list[str] | None = None,
    overwrite: bool = False,
    base_url: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """``POST /api/jobs``; returns the ``JobStatus`` dict."""
    body: dict[str, Any] = {"kind": kind, "config": config, "subject_ids": subject_ids}
    if after:
        body["after"] = after
    if tags:
        body["tags"] = tags
    if overwrite:
        body["overwrite"] = overwrite
    return _request("POST", "/api/jobs", base_url=base_url, token=token, body=body)


def get(
    job_id: str, *, base_url: str | None = None, token: str | None = None
) -> dict[str, Any]:
    """``GET /api/jobs/{id}``; returns the ``JobDetail`` dict (``spec``/``status``/``artifacts``)."""
    return _request("GET", f"/api/jobs/{job_id}", base_url=base_url, token=token)


def cancel(
    job_id: str, *, base_url: str | None = None, token: str | None = None
) -> dict[str, Any]:
    return _request(
        "POST", f"/api/jobs/{job_id}/cancel", base_url=base_url, token=token
    )


def watch(
    job_id: str,
    *,
    base_url: str | None = None,
    token: str | None = None,
    poll_interval: float = 1.0,
    print_events: bool = True,
) -> dict[str, Any]:
    """Poll ``/api/jobs/{id}/events`` until *job_id* reaches a terminal state.

    Prints ``log``/``stage`` events as they arrive when *print_events* is true (the notebook
    equivalent of watching the Jobs panel). Returns the final ``JobStatus`` dict.
    """
    since = 0
    while True:
        events = (
            _request(
                "GET",
                f"/api/jobs/{job_id}/events?since={since}",
                base_url=base_url,
                token=token,
            )
            or []
        )
        for event in events:
            since = max(since, event.get("seq", since) + 1)
            if not print_events:
                continue
            if event.get("type") == "log":
                print(f"[{event.get('level', 'info')}] {event.get('msg', '')}")
            elif event.get("type") == "stage":
                print(f"-- stage: {event.get('stage')}")
        detail = get(job_id, base_url=base_url, token=token)
        status = detail.get("status", detail)
        if status["state"] in TERMINAL_STATES:
            return status
        time.sleep(poll_interval)


def run_from_json(
    spec_path: str,
    *,
    base_url: str | None = None,
    token: str | None = None,
    poll_interval: float = 1.0,
    print_events: bool = True,
) -> dict[str, Any]:
    """Read a ``spec.json`` (``{kind, config, subject_ids, after?, tags?, overwrite?}``), submit
    it, and block until it finishes. Returns the final ``JobStatus`` dict.
    """
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    status = submit(
        spec["kind"],
        spec.get("config", {}),
        spec.get("subject_ids", []),
        after=spec.get("after"),
        tags=spec.get("tags"),
        overwrite=spec.get("overwrite", False),
        base_url=base_url,
        token=token,
    )
    return watch(
        status["id"],
        base_url=base_url,
        token=token,
        poll_interval=poll_interval,
        print_events=print_events,
    )
