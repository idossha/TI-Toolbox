"""Host tests for ``tit.server.routes.system`` — the payload the System page reads.

The System page (pinned above Settings) and the jobs rail's Host tab are two
views of *one* snapshot, so the fields added on 2026-09-07 (per-core CPU, swap,
the Docker root disk, load average, uptime, the server's own process, kernels,
Docker siblings) are asserted here rather than in a page test: if the snapshot
stops carrying them, both surfaces go blank at once.

The other half of what these tests are for is **degradation**. Every one of the
new fields is optional because the host may not be able to answer it, and the
rule is that an unanswerable field is omitted, never an exception that takes the
whole snapshot with it — a monitor that dies when the Docker daemon is wedged is
worse than one that says "no siblings".
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("psutil")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.routes import system as system_routes  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-abc123"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    get_path_manager(str(tmp_path))
    (tmp_path / "dataset_description.json").write_text("{}")
    settings = ServerSettings(project_dir=str(tmp_path), token=TOKEN)
    with TestClient(create_app(settings), base_url=BASE) as c:
        yield c


@pytest.fixture(autouse=True)
def _no_docker_cache() -> None:
    """The 5 s Docker TTL is module state; a test must never inherit another's answer."""
    from tit.server.schemas import DockerHealth

    system_routes._docker_cache = (0.0, DockerHealth())


# ---------------------------------------------------------------- the payload


def test_snapshot_carries_the_system_page_fields(client: TestClient) -> None:
    body = client.get("/api/system", headers=BEARER).json()

    # v0 fields the Host tab already read.
    assert set(body["mem"]) >= {"total", "available", "used", "percent"}
    assert body["cpu_count"] >= 1

    # Added 2026-09-07. Per-core is per *core*: one figure each, and the count
    # has to agree with `cpu_count`, or the System page's core grid is a lie.
    assert len(body["cpu_per_core"]) == body["cpu_count"]
    assert all(0.0 <= v <= 100.0 for v in body["cpu_per_core"])

    assert body["uptime_s"] > 0.0
    assert set(body["swap"]) == {"total", "used", "free", "percent"}
    assert body["kernels"] == 0  # none started in this process
    assert isinstance(body["containers"], list)

    own = body["own"]
    assert own["pid"] == os.getpid()
    assert own["rss"] > 0
    # The server's own process is reported ONCE, as `own`. It must never also
    # appear in `processes` — a monitor that counted itself as toolbox work
    # would attribute its own polling to whatever job is running.
    assert all(p["pid"] != os.getpid() for p in body["processes"])


def test_disk_says_which_filesystem_it_measured(
    client: TestClient, tmp_path: Path
) -> None:
    """`DiskInfo.path` exists so a figure can be labelled, not guessed at."""
    body = client.get("/api/system", headers=BEARER).json()
    assert body["disk"]["path"] in (str(tmp_path), "/")
    assert body["disk"]["total"] > 0
    docker = body["disk_docker"]
    # Present only where the Docker root is visible from here; when it is, it is
    # a real reading of a real mount point.
    assert docker is None or docker["path"] in system_routes.DOCKER_ROOT_CANDIDATES


def test_load_average_is_the_three_windows_or_nothing() -> None:
    load = system_routes.load_average()
    assert load == [] or len(load) == 3


# ------------------------------------------------------- degradation, not death


def test_project_disk_falls_back_when_the_project_dir_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable project volume must not blank the whole snapshot."""
    monkeypatch.setattr(
        system_routes, "_disk", lambda path: None if path != "/" else _fake_disk("/")
    )
    assert system_routes.project_disk().path == "/"


def _fake_disk(path: str):
    from tit.server.schemas import DiskInfo

    return DiskInfo(total=1, free=1, percent=0.0, path=path)


def test_docker_health_reports_a_wedged_daemon_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A monitoring page that dies because Docker is down has failed at its one job."""

    def boom(*_args, **_kwargs):
        raise OSError("socket is wedged")

    monkeypatch.setattr("tit.jobs.docker_engine.discover", boom)
    health = system_routes.docker_health()
    assert health.reachable is False
    assert "wedged" in health.error
    assert health.containers == []
    assert system_routes.docker_siblings() == []


def test_docker_health_is_ttl_cached_so_a_1s_poll_is_not_a_1s_docker_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def counting_discover(*_args, **_kwargs):
        calls["n"] += 1
        raise OSError("no daemon here")

    monkeypatch.setattr("tit.jobs.docker_engine.discover", counting_discover)
    system_routes.docker_health(now=1000.0)
    system_routes.docker_health(now=1000.0 + system_routes.DOCKER_TTL_S / 2)
    assert calls["n"] == 1, "second call inside the TTL must be served from cache"
    system_routes.docker_health(now=1000.0 + system_routes.DOCKER_TTL_S + 1)
    assert calls["n"] == 2, "a call past the TTL re-reads the daemon"


def test_docker_df_sums_the_engine_rows_the_way_docker_system_df_does() -> None:
    """The Engine returns rows; `docker system df` prints totals. This is that arithmetic."""
    df = system_routes._df(
        {
            "Images": [
                {"Size": 100, "Containers": 1},
                {"Size": 250, "Containers": 0},  # unused -> reclaimable
            ],
            "Containers": [{"SizeRw": 7}, {"SizeRw": 3}],
            "Volumes": [
                {"UsageData": {"Size": 40, "RefCount": 1}},
                {"UsageData": {"Size": 60, "RefCount": 0}},  # dangling -> reclaimable
            ],
            "BuildCache": [{"Size": 11}, {"Size": 9}],
        }
    )
    assert (df.images_size, df.images_count, df.images_reclaimable) == (350, 2, 250)
    assert (df.containers_size, df.containers_count) == (10, 2)
    assert (df.volumes_size, df.volumes_count, df.volumes_reclaimable) == (100, 2, 60)
    assert df.build_cache_size == 20


def test_docker_warnings_name_only_things_a_person_can_act_on() -> None:
    from tit.server.schemas import DockerDf, DockerHealth, OwnContainer

    quiet = DockerHealth(df=DockerDf(images_reclaimable=1024**3))
    assert system_routes.docker_warnings(quiet) == []

    loud = DockerHealth(
        df=DockerDf(images_reclaimable=40 * 1024**3),
        own=OwnContainer(id="a", name="tit", image="i", restarts=2),
    )
    text = " | ".join(system_routes.docker_warnings(loud))
    assert "prune" in text
    assert "restarted 2" in text


def test_process_list_is_the_busiest_processes_not_only_the_keyword_matches() -> None:
    """The pre-2026-09-07 list hid whatever was actually using the CPU unless it was on a
    keyword list. `relevant` keeps that information without keeping that behaviour."""
    rows, total = system_routes.process_list()
    assert total >= len(rows)
    assert len(rows) <= system_routes.PROCESS_LIMIT
    # Sorted by CPU, descending.
    assert [r.cpu_percent for r in rows] == sorted(
        (r.cpu_percent for r in rows), reverse=True
    )
    # And `relevant_processes()` -- what the terminate allowlist is defined in terms of -- is
    # still exactly the keyword-matched subset.
    assert all(p.relevant for p in system_routes.relevant_processes())


def test_a_snapshot_never_starts_the_job_subsystem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Opening a monitoring page must not be the thing that boots the job manager."""
    from tit.jobs import bootstrap

    def fail(*_args, **_kwargs):
        raise AssertionError("snapshot called get_manager()")

    monkeypatch.setattr(bootstrap, "get_manager", fail)
    monkeypatch.setattr(bootstrap, "_manager", None)
    assert system_routes.job_pid_owners() == {}


def test_kernel_count_survives_a_registry_that_cannot_be_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "tit.server.kernels.get_kernel_registry",
        lambda: (_ for _ in ()).throw(RuntimeError("no jupyter_client")),
    )
    assert system_routes.kernel_count() == 0
