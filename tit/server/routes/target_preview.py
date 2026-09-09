"""Subject-space target preview; generated cache only, no job or saved scene."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from tit import catalog
from tit.paths import get_path_manager
from tit.scene import build, cache

router = APIRouter()


class PreviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MaskTarget(PreviewModel):
    kind: Literal["mask"]
    path: str
    space: Literal["subject", "mni"]


class AtlasTarget(PreviewModel):
    kind: Literal["subcortical"]
    atlas: str
    space: Literal["subject", "mni"]
    labels: list[int] = Field(min_length=1, max_length=10000)


class PreviewSphere(PreviewModel):
    center: tuple[float, float, float]
    radius: float = Field(gt=0, le=500)


class SphereTarget(PreviewModel):
    kind: Literal["spherical"]
    space: Literal["subject", "mni"]
    spheres: list[PreviewSphere] = Field(min_length=1, max_length=100)


class SavedTarget(PreviewModel):
    kind: Literal["saved"]
    names: list[str] = Field(min_length=1, max_length=100)
    radius: float = Field(gt=0, le=500)
    space: Literal["subject", "mni"]


class TargetPreviewRequest(PreviewModel):
    subject: str
    roi: Annotated[
        MaskTarget | AtlasTarget | SphereTarget | SavedTarget,
        Field(discriminator="kind"),
    ]


def _input(pm, path):
    resolved = build.source_path(pm, path)
    if resolved is None:
        raise HTTPException(403, "Preview input resolves outside the project")
    if not resolved.is_file():
        raise HTTPException(
            404, f"Target preview unavailable: missing {Path(path).name}"
        )
    return resolved


def _atlas(pm, subject, roi):
    from tit.atlas.constants import MNI_ATLAS_FILES, mni_resources_dir
    from tit.atlas.voxel import VoxelAtlasManager
    from tit.server.routes.files import _resolve_jailed

    if roi.space == "mni":
        root = Path(mni_resources_dir())
        if roi.atlas not in MNI_ATLAS_FILES:
            raise HTTPException(404, "Target preview unavailable: unknown MNI atlas")
        return _resolve_jailed(str(root / roi.atlas), [root])
    manager = VoxelAtlasManager(
        fastsurfer_mri_dir=pm.fastsurfer_mri(subject),
        freesurfer_mri_dir=pm.freesurfer_mri(subject),
        seg_dir=pm.segmentation(subject),
        masks_dir=pm.masks(subject),
    )
    # Check discovery directories before listing to avoid following escaped links.
    for directory in (
        manager.fastsurfer_mri_dir,
        manager.freesurfer_mri_dir,
        manager.seg_dir,
        manager.masks_dir,
    ):
        if build.source_path(pm, directory) is None:
            raise HTTPException(403, "Atlas directory resolves outside the project")
    path = dict(manager.list_atlases()).get(roi.atlas)
    if path is None:
        raise HTTPException(
            404, "Target preview unavailable: atlas missing for this subject"
        )
    return _input(pm, path)


@router.post(
    "/api/scene/target-preview",
    summary="Read-only subject-space target volume preview",
    responses={409: {"description": "No project directory is bound"}},
)
def target_preview(body: TargetPreviewRequest) -> dict:
    pm = get_path_manager()
    if not pm.project_dir:
        raise HTTPException(409, "No project directory is bound")
    if not catalog.is_safe_name(
        body.subject
    ) or body.subject not in catalog.subject_ids(pm):
        raise HTTPException(404, "Target preview unavailable: unknown subject")
    anatomy = _input(pm, pm.t1(body.subject))
    m2m = build.source_path(pm, pm.m2m(body.subject))
    roi = body.roi
    source = None
    if roi.kind == "mask":
        source = _input(pm, roi.path)
    elif roi.kind == "subcortical":
        source = _atlas(pm, body.subject, roi)
    inputs = [anatomy] + ([source] if source else [])
    if roi.kind == "saved":
        from tit.opt.ex.roi import read_roi_center

        spheres = []
        for name in roi.names:
            if not catalog.is_safe_name(name.removesuffix(".csv")):
                raise HTTPException(422, "Invalid saved ROI name")
            filename = name if name.endswith(".csv") else name + ".csv"
            path = _input(pm, Path(pm.rois(body.subject)) / filename)
            inputs.append(path)
            try:
                spheres.append(
                    PreviewSphere(center=read_roi_center(str(path)), radius=roi.radius)
                )
            except ValueError as exc:
                raise HTTPException(422, f"Target preview unavailable: {exc}") from exc
        roi = SphereTarget(kind="spherical", space=roi.space, spheres=spheres)
    if roi.space == "mni":
        # Both transform directions are used by SimNIBS nonlinear image/point mapping.
        transform_dir = build.source_path(pm, Path(m2m) / "toMNI")
        if transform_dir is None or not transform_dir.is_dir():
            raise HTTPException(
                404, "Target preview unavailable: subject MNI registration is missing"
            )
        transforms = [
            _input(pm, path) for path in transform_dir.rglob("*") if path.is_file()
        ]
        if not transforms:
            raise HTTPException(
                404, "Target preview unavailable: subject MNI registration is missing"
            )
        inputs.extend(sorted(transforms))
    fingerprint = [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in inputs]
    key = hashlib.sha256(
        json.dumps(
            ["target-preview-v1", body.model_dump(), fingerprint], sort_keys=True
        ).encode()
    ).hexdigest()[:24]
    try:
        directory = cache.cache_dir(pm.project_dir, body.subject)
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"target-{key}.nii"
        if build.source_path(pm, destination) is None:
            raise PermissionError("Target preview cache escapes project")
        with cache.subject_lock(pm.project_dir, body.subject):
            if not destination.is_file():
                import nibabel as nib
                from tit.scene.target_preview import target_image

                result = target_image(anatomy, roi, m2m, directory, source)
                with tempfile.NamedTemporaryFile(
                    dir=directory, suffix=".nii", delete=False
                ) as handle:
                    temporary = Path(handle.name)
                try:
                    nib.save(result, str(temporary))
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
        from tit.viewspec import to_tetravox_viewspec

        scene = to_tetravox_viewspec(
            {
                "layers": [
                    {"path": str(anatomy), "colormap": "grayscale", "opacity": 1.0},
                    {"path": str(destination), "colormap": "heat", "opacity": 0.65},
                ]
            }
        )
        target = scene["layers"][1]
        target.update(
            interpolation="nearest",
            showIn3D=True,
            scale={"kind": "linear", "lo": 0, "hi": 1},
            threshold={
                "lo": 0.5,
                "hi": None,
                "mode": "hide",
                "symmetric": False,
                "softEdge": 0,
            },
        )
        for layer in scene["layers"]:
            layer.update(pickable=False, showColorbar=False)
        return {
            "scene": scene,
            "note": "Target extent in subject space; analysis/search applies its tissue and mesh settings.",
        }
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, OSError, ImportError, RuntimeError) as exc:
        raise HTTPException(422, f"Target preview unavailable: {exc}") from exc
