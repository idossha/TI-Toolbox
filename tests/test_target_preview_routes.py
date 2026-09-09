"""2026-09-09: preview request bounds and project jail; geometry is in numerical/."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from tit.server.routes import target_preview as route


@pytest.mark.parametrize("radius", [0, -1, float("nan"), float("inf")])
def test_reject_invalid_sphere_radius(radius):
    with pytest.raises(ValidationError):
        route.TargetPreviewRequest.model_validate(
            {
                "subject": "ernie",
                "roi": {
                    "kind": "spherical",
                    "space": "subject",
                    "spheres": [{"center": [0, 0, 0], "radius": radius}],
                },
            }
        )


def test_source_symlink_cannot_escape(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "outside.nii"
    external.write_bytes(b"private")
    link = project / "mask.nii"
    link.symlink_to(external)
    with pytest.raises(HTTPException) as caught:
        route._input(SimpleNamespace(project_dir=str(project)), link)
    assert caught.value.status_code == 403


def test_missing_anatomy_does_not_substitute_guide(tmp_path, monkeypatch):
    pm = SimpleNamespace(project_dir=str(tmp_path), t1=lambda sid: tmp_path / "T1.nii")
    monkeypatch.setattr(route, "get_path_manager", lambda: pm)
    monkeypatch.setattr(route.catalog, "subject_ids", lambda pm: ["ernie"])
    body = route.TargetPreviewRequest.model_validate(
        {
            "subject": "ernie",
            "roi": {"kind": "mask", "path": "/missing", "space": "subject"},
        }
    )
    with pytest.raises(HTTPException) as caught:
        route.target_preview(body)
    assert caught.value.status_code == 404
    assert "T1.nii" in caught.value.detail
