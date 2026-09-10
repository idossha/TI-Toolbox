"""Gate + fixtures for the Level A smoke harness (decision P5).

What this pins
--------------
The harness never runs by accident. It talks to a *live* server against the maintainer's own
dataset, so it is gated on ``TIT_SMOKE_SERVER_URL`` **and** ``TIT_SMOKE_TOKEN``: with either
unset every server-touching test skips, printing why. ``pytest.ini`` additionally deselects the
``smoke`` marker by default, so the host suite stays at its ~35 s with zero smoke tests run.

Why two mechanisms and not one (the failure it prevents)
--------------------------------------------------------
The marker deselect is a *policy* (fast default suite) and can be overridden with one flag;
the env gate is a *safety property* (never write to a real dataset unless someone named a
server) and cannot. Someone running ``pytest -m smoke`` on a laptop with no container must get
skips with a reason, not a wall of connection errors -- and a run against the wrong server must
be impossible to trigger by flag alone.

Options
-------
``--smoke-kinds a,b``  run only those rows (row id, or a kind name -> every row of that kind)
``--smoke-keep``       do not delete anything the run created (inspect it on disk)
``--smoke-full``       run the long kinds to completion instead of started-then-cancel

Environment
-----------
``TIT_SMOKE_SERVER_URL``   e.g. http://127.0.0.1:8765          (required)
``TIT_SMOKE_TOKEN``        the server's TIT_SERVER_TOKEN       (required)
``TIT_SMOKE_PROJECT_HOST`` host directory bound at the project's container path (required for
                           the on-disk artifact check; ``dev/smoke.sh`` reads it from the
                           container's ``tit.host_project_dir`` label)
``TIT_SMOKE_RUN_ID``       override the generated run id (namespacing, decision P6)

Written 2026-09-03 (lane S1).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pytest

from tests.smoke.cleanup import Manifest
from tests.smoke.client import SmokeClient
from tests.smoke.matrix import Ctx

ENV_URL = "TIT_SMOKE_SERVER_URL"
ENV_TOKEN = "TIT_SMOKE_TOKEN"
ENV_HOST_DIR = "TIT_SMOKE_PROJECT_HOST"
ENV_RUN_ID = "TIT_SMOKE_RUN_ID"

ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "artifacts")


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("smoke", "TI-Toolbox pipeline smoke harness")
    group.addoption(
        "--smoke-kinds",
        action="store",
        default="",
        help="Comma-separated row ids or kinds to run (default: the whole matrix).",
    )
    group.addoption(
        "--smoke-keep",
        action="store_true",
        default=False,
        help="Keep everything the run created (no cleanup), for inspection.",
    )
    group.addoption(
        "--smoke-full",
        action="store_true",
        default=False,
        help="Run started-then-cancel rows to completion instead of cancelling them.",
    )


def _gate_reason() -> str | None:
    """Why the harness cannot run here, or None."""
    missing = [name for name in (ENV_URL, ENV_TOKEN) if not os.environ.get(name)]
    if missing:
        return (
            f"skipping: pipeline smoke harness needs {' and '.join(missing)} "
            "(run dev/smoke.sh, which discovers the dev container and sets them)"
        )
    return None


@pytest.fixture(scope="session")
def smoke_gate() -> None:
    """Skip, with a printed reason, unless a target server was named."""
    reason = _gate_reason()
    if reason:
        print(reason)
        pytest.skip(reason, allow_module_level=False)


@pytest.fixture(scope="session")
def smoke_client(smoke_gate: None) -> SmokeClient:
    client = SmokeClient(os.environ[ENV_URL], os.environ[ENV_TOKEN])
    health = client.health()
    assert health.get("status") == "ok", f"server not healthy: {health}"
    return client


@pytest.fixture(scope="session")
def smoke_ctx(smoke_client: SmokeClient) -> Ctx:
    run_id = os.environ.get(ENV_RUN_ID) or time.strftime("%H%M%S", time.localtime())
    project = smoke_client.get("/api/project").json
    return Ctx(run_id=run_id, root=project["container_path"])


@pytest.fixture(scope="session")
def smoke_manifest(request: pytest.FixtureRequest, smoke_ctx: Ctx):
    """One manifest for the whole session; written out and (unless --smoke-keep) emptied."""
    host_root = os.environ.get(ENV_HOST_DIR, "")
    if not host_root:
        pytest.skip(
            f"skipping: {ENV_HOST_DIR} is unset, so no on-disk artifact check or cleanup "
            "is possible (dev/smoke.sh reads it from the container's tit.host_project_dir label)"
        )
    manifest = Manifest(
        container_root=smoke_ctx.root,
        host_root=host_root,
        keep=bool(request.config.getoption("--smoke-keep")),
    )
    yield manifest
    removed = manifest.remove_created()
    path = os.path.join(
        ARTIFACT_DIR,
        f"manifest-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{smoke_ctx.run_id}.json",
    )
    manifest.write(path)
    kept = [c for c in manifest.claims if c.pre_existed]
    print(
        f"\nsmoke cleanup: removed {len(removed)} created path(s); "
        f"{len(kept)} pre-existing path(s) left alone; manifest {path}"
    )


@pytest.fixture(scope="session")
def smoke_results(smoke_ctx: Ctx) -> list[dict]:
    """Collected per-row results.

    Written to ``tests/smoke/artifacts/results-<utc>-<runid>.md`` as well as printed: pytest
    swallows a teardown ``print`` unless ``-s`` is passed, and the results table *is* the
    deliverable (decision P8) -- a table that only exists when the run happens to fail is no
    table at all.
    """
    rows: list[dict] = []
    yield rows
    if not rows:
        return
    header = (
        "| kind (row) | subject | behaviour | source | result | wall s | evidence |\n"
        "|---|---|---|---|---|---|---|"
    )
    lines = [
        "| {row} | {subject} | {behaviour} | {source} | {result} | {wall:.1f} | {evidence} |".format(**r)
        for r in rows
    ]
    table = header + "\n" + "\n".join(lines) + "\n"
    path = os.path.join(
        ARTIFACT_DIR,
        f"results-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{smoke_ctx.run_id}.md",
    )
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(table)
    print("\n\n" + table + f"\nresults table: {path}\n")
