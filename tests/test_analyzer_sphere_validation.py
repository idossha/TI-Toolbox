"""A spherical target needs a positive finite radius and a centre of three finite numbers (2026-10-22).

What this pins
    ``AnalyzerConfig.__post_init__`` checked only that center and radius were not ``None``, so
    radius 0 (or -1, NaN, inf) and a 2- or 4-number centre were accepted end to end and ended
    in an empty ROI. Now the config refuses them, ``/api/validate/analyzer`` flags the offending
    field by name (its errors carry a ``path``), ``/api/plan/analyzer`` answers 422 instead of
    planning a job, and the ``Analyzer.analyze_sphere(s)`` Python API refuses the same values.
    The desktop half (``isRoiComplete``) is desktop/tests/unit/roi-sphere-complete.test.ts.

Where the expectations come from
    The spec: a sphere is a centre point in 3-D space and a radius > 0 (physical law: a
    radius-0 sphere contains no volume or area). Values at the boundary (a radius just above 0,
    a centre of zeros) must still be accepted.

Run: .venv/bin/python -m pytest tests/test_analyzer_sphere_validation.py -q -p no:cacheprovider
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit.analyzer.config import AnalyzerConfig

BAD_RADII = [0, 0.0, -1.0, -5, math.nan, math.inf, -math.inf]
BAD_CENTERS = [[0.0, 0.0], [0.0, 0.0, 0.0, 0.0], [0.0, math.nan, 0.0], [math.inf, 0, 0]]


def _config(**overrides) -> AnalyzerConfig:
    data = {
        "mode": "single",
        "subject_id": "001",
        "simulation": "M1",
        "analysis_type": "spherical",
        "center": [0.0, 0.0, 0.0],
        "radius": 10.0,
    }
    data.update(overrides)
    return AnalyzerConfig(**data)


@pytest.mark.parametrize("radius", BAD_RADII)
def test_config_refuses_a_radius_that_is_not_positive_and_finite(radius) -> None:
    with pytest.raises(ValueError, match=r"^radius must be a positive, finite number"):
        _config(radius=radius)


@pytest.mark.parametrize("center", BAD_CENTERS)
def test_config_refuses_a_center_that_is_not_three_finite_numbers(center) -> None:
    with pytest.raises(ValueError, match=r"^center must be three"):
        _config(center=center)


@pytest.mark.parametrize("radius", [1e-6, 0.1, 10, 80.0])
def test_config_accepts_any_positive_finite_radius(radius) -> None:
    assert _config(radius=radius).radius == radius
    assert _config(center=[0, 0, 0], radius=radius).center == [0, 0, 0]


def test_non_spherical_targets_ignore_center_and_radius() -> None:
    cfg = _config(analysis_type="cortical", atlas="DK40", center=None, radius=0)
    assert cfg.radius == 0  # not a sphere: the field is unused


# -- the API routes ----------------------------------------------------------------------------

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
# Same local fallback as tests/test_plan_routes.py: importing the server pulls tit.stats.
for _mod in ("scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-p06"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    pm = get_path_manager(str(tmp_path))
    Path(pm.m2m("001")).mkdir(parents=True)
    (tmp_path / "dataset_description.json").write_text("{}")
    settings = ServerSettings(project_dir=str(tmp_path), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def _wire(**overrides) -> dict:
    data = {
        "mode": "single",
        "subject_id": "001",
        "simulation": "M1",
        "space": "mesh",
        "analysis_type": "spherical",
        "center": [-35.0, 5.0, 5.0],
        "radius": 10.0,
        "coordinate_space": "subject",
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    "overrides, path",
    [
        ({"radius": 0}, "radius"),
        ({"radius": -5}, "radius"),
        ({"center": [1.0, 2.0]}, "center"),
    ],
)
def test_validate_route_flags_the_field(client: TestClient, overrides, path) -> None:
    resp = client.post(
        "/api/validate/analyzer", json={"config": _wire(**overrides)}, headers=BEARER
    )
    body = resp.json()
    assert body["ok"] is False
    assert [e["path"] for e in body["errors"]] == [path]


def test_plan_route_refuses_radius_zero_instead_of_planning_a_job(
    client: TestClient,
) -> None:
    good = client.post("/api/plan/analyzer", json={"config": _wire()}, headers=BEARER)
    assert good.status_code == 200 and len(good.json()["jobs"]) == 1
    resp = client.post(
        "/api/plan/analyzer", json={"config": _wire(radius=0)}, headers=BEARER
    )
    assert resp.status_code == 422
    assert "radius must be a positive" in resp.json()["detail"]


# -- the Python API ----------------------------------------------------------------------------


def _analyzer():
    from tit.analyzer.analyzer import Analyzer

    analyzer = object.__new__(Analyzer)
    analyzer.space = "mesh"
    analyzer._sphere_mesh = MagicMock(side_effect=AssertionError("not reached"))
    return analyzer


@pytest.mark.parametrize("radius", BAD_RADII)
def test_analyze_sphere_refuses_the_radius_before_reading_anything(radius) -> None:
    with pytest.raises(ValueError, match="positive, finite radius"):
        _analyzer().analyze_sphere((0.0, 0.0, 0.0), radius)


@pytest.mark.parametrize("center", BAD_CENTERS)
def test_analyze_sphere_refuses_the_center(center) -> None:
    with pytest.raises(ValueError, match="finite centre"):
        _analyzer().analyze_sphere(tuple(center), 5.0)


def test_analyze_spheres_refuses_any_bad_sphere_in_the_union() -> None:
    with pytest.raises(ValueError, match=r"got \(10, 0, 0, 0\)"):
        _analyzer().analyze_spheres([(0, 0, 0, 5.0), (10, 0, 0, 0)])


# -- the group API: one refusal before any subject or folder -----------------------------------


@pytest.mark.parametrize(
    "target, shown",
    [
        ({"center": (0.0, 0.0, 0.0), "radius": 0}, "(0.0, 0.0, 0.0, 0)"),
        ({"center": (0.0, math.nan, 0.0), "radius": 5.0}, "(0.0, nan, 0.0, 5.0)"),
        ({"spheres": [(0, 0, 0, 5.0), (10, 0, 0, -1)]}, "(10, 0, 0, -1)"),
    ],
)
def test_group_refuses_a_bad_sphere_once_and_blames_no_subject(
    tmp_path: Path, target, shown
) -> None:
    """A sphere is the same for every subject: its refusal must not read "sub-101: ..."."""
    from tit.analyzer import group
    from tit.analyzer.analyzer import Analyzer

    built: list[str] = []

    class _Subject(Analyzer):  # the real sphere checks, no files
        def __init__(self, sid, *args, **kwargs):
            built.append(sid)
            self.space = "mesh"
            self._sphere_mesh = MagicMock(side_effect=AssertionError("not reached"))

    out = tmp_path / "group_out"
    with (
        patch.object(group, "Analyzer", _Subject),
        patch.object(group, "add_file_handler"),
    ):
        with pytest.raises(ValueError) as err:
            group.run_group_analysis(
                ["101", "102"],
                "M1",
                analysis_type="spherical",
                output_dir=str(out),
                **target,
            )
    message = str(err.value)
    assert message.startswith("A sphere needs a finite centre"), message
    assert f"got {shown}" in message
    assert built == []  # refused before the subject loop
    assert not out.exists()  # and before the group folder is made
