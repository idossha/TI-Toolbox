"""The ``/api/caps/*`` routes answer in bounded time and never with a 500 (p14, 2026-10-22).

What this pins:

* ``/api/caps/inspect`` returns within a deadline when the scene's skin
  surface never becomes ready. The route's own contract
  (``tit/server/routes/caps.py``, ``inspect``) is "the table still answers
  spacing; scalp distance is blank". Before p14 ``_skin_nodes`` looped
  ``while found is None`` with no overall deadline: a mesh replaced
  mid-request publishes its surface under a fingerprint the request's
  ``ready()`` never checks, so the request re-asked the scene service forever.
  ``scene_routes._ensure`` is faked here to answer "still building" for ever,
  which is that state.
* A server without SimNIBS (``tit.caps.simnibs_caps_dir`` raises ``CapError``)
  answers 503 with a sentence naming SimNIBS on every caps route that lists
  the image's caps, instead of an unhandled ``ValueError`` (HTTP 500).

The expected spacing is read off the hand-placed coordinates (two electrodes
20 mm apart on the x axis). Fixture: ``tests/test_caps.py::project`` (SimNIBS
faked). Reproduce: ``.venv/bin/python -m pytest tests/test_caps_routes_bounded.py -q``.
"""

from __future__ import annotations

import threading

import pytest

from tests.test_caps import BEARER, CAP, WARPED, project  # noqa: F401 - fixture
from tit import caps
from tit.server.routes import scene as scene_routes

#: How long the test waits for an answer. The fake build never finishes, so a
#: route without a deadline is still waiting when this runs out.
JOIN_S = 5.0


def _in_thread(fn):
    """Run *fn* in a daemon thread; its result, or ``None`` if it is still running."""
    out: dict = {}
    thread = threading.Thread(target=lambda: out.setdefault("r", fn()), daemon=True)
    thread.start()
    thread.join(JOIN_S)
    return None if thread.is_alive() else out["r"]


def test_inspect_answers_spacing_when_the_skin_never_becomes_ready(
    project, monkeypatch  # noqa: F811 - the imported fixture
) -> None:
    (project.positions / "A.csv").write_text(WARPED)
    waits: list[float] = []

    def still_building(pm, subject, unit, work, ready, wait):
        waits.append(wait)
        return None  # what _ensure answers while a build is still running

    monkeypatch.setattr(scene_routes, "_ensure", still_building)
    r = _in_thread(
        lambda: project.client.get(
            "/api/caps/inspect?subject=ernie&net=A.csv", headers=BEARER
        )
    )
    assert r is not None, f"inspect was still waiting after {JOIN_S:g} s"
    assert r.status_code == 200, r.text
    rows = {row["name"]: row for row in r.json()["electrodes"]}
    # Fz (10,0,90) and Cz (-10,0,90): each is the other's nearest, 20 mm apart.
    assert (rows["Fz"]["nn_mm"], rows["Fz"]["nn_name"]) == (20.0, "Cz")
    assert (rows["Cz"]["nn_mm"], rows["Cz"]["nn_name"]) == (20.0, "Fz")
    assert [row["scalp_mm"] for row in rows.values()] == [None, None]
    assert r.json()["summary"]["scalp_max_mm"] is None
    # One bounded wait in total, never longer than the scene service's own cap.
    assert waits and sum(waits) <= scene_routes.MAX_WAIT_S


def test_inspect_still_measures_the_scalp_once_the_skin_is_ready(project) -> None:
    """The deadline does not cost the normal path its scalp distance."""
    (project.positions / "A.csv").write_text(WARPED)
    r = project.client.get("/api/caps/inspect?subject=ernie&net=A.csv", headers=BEARER)
    assert r.status_code == 200, r.text
    rows = {row["name"]: row for row in r.json()["electrodes"]}
    # The fixture's one skin node is (10,0,92): Fz (10,0,90) is 2 mm from it,
    # Cz (-10,0,90) is sqrt(20^2 + 2^2) mm.
    assert rows["Fz"]["scalp_mm"] == 2.0
    assert rows["Cz"]["scalp_mm"] == pytest.approx((20**2 + 2**2) ** 0.5, abs=1e-3)


@pytest.mark.parametrize(
    ("method", "url", "kwargs"),
    [
        ("get", "/api/caps/available?subject=ernie", {}),
        ("post", "/api/caps/warp", {"json": {"subject": "ernie", "caps": ["A.csv"]}}),
        ("post", "/api/caps/upload?name=Mine.csv", {"content": CAP}),
    ],
)
def test_caps_routes_answer_503_without_simnibs(
    project, monkeypatch, method, url, kwargs  # noqa: F811 - the imported fixture
) -> None:
    def no_simnibs():
        # What the real simnibs_caps_dir raises when find_spec("simnibs") is None.
        raise caps.CapError("SimNIBS is not installed")

    monkeypatch.setattr(caps, "simnibs_caps_dir", no_simnibs)
    r = getattr(project.client, method)(url, headers=BEARER, **kwargs)
    assert r.status_code == 503, r.text
    assert "SimNIBS is not installed" in r.json()["detail"]
    assert project.calls == []
