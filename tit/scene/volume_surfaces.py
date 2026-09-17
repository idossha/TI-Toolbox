"""Display-only labeled volume surfaces in the image's world coordinates."""

from __future__ import annotations

import colorsys
import re

import numpy as np


def default_visible(name: str, atlas_name: str = "") -> bool:
    """Recognize subcortical anatomy by LUT names, never cross-atlas integers."""
    normalized = re.sub(r"[^a-z0-9]+", " ", name.lower())
    if any(
        word in normalized
        for word in (
            "ventric",
            "csf",
            "background",
            "unknown",
            "white matter",
            "cortex",
            "choroid",
        )
    ):
        return False
    if atlas_name.startswith(
        ("CIT168", "Morel", "massp2021", "ThalamicNuclei", "hippoAmygLabels")
    ):
        return True
    return any(
        word in normalized
        for word in (
            "hippocamp",
            "thalam",
            "amygdal",
            "brain stem",
            "brainstem",
            "caudate",
            "putamen",
            "pallid",
            "accumbens",
            "hypothalam",
            "substantia",
            "subthalam",
            "red nucleus",
            "ventraldc",
            "ventral dc",
            "hippocampal",
            "pons",
            "medulla",
            "midbrain",
        )
    )


def surfaces(
    image,
    names: dict[int, str],
    selected: list[int],
    *,
    atlas: bool = True,
    atlas_name: str = "",
) -> dict:
    """Extract separately pickable regions; padding closes image-edge regions.

    Geometry is approximate display geometry only. Original mask voxels and
    optimization settings are never modified. The complete affine, including
    shear and reflection, maps marching-cubes coordinates to world millimetres.
    """
    from skimage.measure import marching_cubes
    from tit.atlas.islands import keep_main_components
    from tit.scene.simplify import simplify_to_budget

    if (
        len(image.shape) != 3
        or np.prod(image.shape, dtype=np.float64) > 128 * 1024 * 1024
    ):
        raise ValueError(
            "Surface preview requires a 3D volume below 128 million voxels"
        )
    affine = np.asarray(image.affine, dtype=float)
    if not np.isfinite(affine).all() or abs(np.linalg.det(affine[:3, :3])) < 1e-12:
        raise ValueError("Surface preview has an invalid affine")
    data = image.get_fdata(dtype=np.float32)
    if not np.isfinite(data).all():
        raise ValueError("Surface preview contains non-finite values")
    if atlas and not np.equal(data, np.floor(data)).all():
        raise ValueError("Atlas preview requires integer labels")
    ids = [int(value) for value in np.unique(data) if value != 0]
    if not atlas:
        data = (data > 0).astype(np.uint8)
        ids = [1] if data.any() else []
    chosen = set(selected)
    absent = chosen - set(ids)
    if absent:
        raise ValueError(f"Selected labels absent from the preview: {sorted(absent)}")
    ids = [
        value
        for value in ids
        if not atlas
        or value in chosen
        or default_visible(names.get(value, ""), atlas_name)
    ]
    if any(value < 1 or value > 65535 for value in ids):
        raise ValueError("Surface preview supports label IDs from 1 to 65535")
    if len(ids) > 256:
        raise ValueError("Select at most 256 regions for a surface preview")
    positions, indices, labels, entries = [], [], [], []
    offset = 0
    for value in ids:
        mask = data == value
        if atlas:
            # The same cleanup the search and the analysis apply, so the pane draws
            # exactly the mask that will be optimised and measured (tit/atlas/islands.py).
            mask, _, _ = keep_main_components(
                mask, what=names.get(value, f"label {value}")
            )
        occupied = np.where(mask)
        lower = np.array([axis.min() for axis in occupied])
        upper = np.array([axis.max() + 1 for axis in occupied])
        cropped = mask[tuple(slice(lo, hi) for lo, hi in zip(lower, upper))]
        vertices, faces, _, _ = marching_cubes(np.pad(cropped, 1), level=0.5)
        vertices += lower - 1
        vertices = vertices @ affine[:3, :3].T + affine[:3, 3]
        # Marching cubes' default descent winding points inward. Correct its
        # handedness after the world transform, including reflected affines.
        if np.linalg.det(affine[:3, :3]) > 0:
            faces = faces[:, ::-1]
        simplified = simplify_to_budget(
            vertices, faces, max_triangles=max(400, 120000 // max(1, len(ids)))
        )
        vertices, faces = simplified.vertices, simplified.triangles
        if not len(faces):
            raise ValueError(f"Region {value} is too small for the display surface")
        if len(indices) // 3 + len(faces) > 120000:
            raise ValueError(
                "Surface preview exceeds the triangle budget; select fewer regions"
            )
        positions.extend(vertices.astype(np.float32).ravel().tolist())
        indices.extend((faces + offset).ravel().tolist())
        labels.extend([value] * len(vertices))
        offset += len(vertices)
        name = names.get(value, f"Label {value}")
        color = colorsys.hsv_to_rgb((value * 0.61803398875) % 1, 0.55, 0.85)
        entries.append(
            {
                "id": value,
                "name": name,
                "color": [round(channel * 255) for channel in color],
                "default_visible": not atlas or default_visible(name, atlas_name),
            }
        )
    return {
        "positions": positions,
        "indices": indices,
        "labels": labels,
        "entries": entries,
        "space": "subject-ras",
        "note": "Display surfaces only; the geometry is approximate, but the voxels are the ones search and analysis use, including the detached-island cleanup. Default display filtering does not change the target selection.",
    }
