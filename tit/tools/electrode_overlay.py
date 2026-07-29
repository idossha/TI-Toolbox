#!/usr/bin/env simnibs_python
"""Create NIfTI electrode placement overlays from simulation configs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

_MONTAGE_COLOR_RGB = {
    "blue": (0, 0, 255),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "purple": (128, 0, 128),
    "orange": (255, 165, 0),
    "cyan": (0, 255, 255),
    "chocolate": (210, 105, 30),
    "violet": (238, 130, 238),
}

_DEFAULT_MONTAGE_COLORS = [
    "blue",
    "red",
    "green",
    "purple",
    "orange",
    "cyan",
    "chocolate",
    "violet",
]


def _montage_color_names() -> list[str]:
    """Return the color order used by the simulation PNG montage overlay."""
    try:
        from tit.tools.montage_visualizer import _COLORS
    except ImportError:
        return _DEFAULT_MONTAGE_COLORS
    return list(_COLORS)


def _as_xyz(value: Any) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(
            "Electrode overlay requires XYZ coordinate electrodes; "
            f"got {value!r}"
        )
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid XYZ electrode coordinate: {value!r}") from exc


def _load_eeg_positions(
    eeg_positions_dir: str | Path | None, eeg_net: str | None
) -> dict[str, tuple[float, float, float]]:
    if not eeg_positions_dir or not eeg_net:
        return {}

    eeg_path = Path(eeg_positions_dir)
    if eeg_path.is_dir():
        eeg_path = eeg_path / eeg_net
    if not eeg_path.exists():
        return {}

    positions: dict[str, tuple[float, float, float]] = {}
    with eeg_path.open(newline="") as f:
        for row in csv.reader(f):
            if len(row) < 5 or row[0].strip().lower() != "electrode":
                continue
            label = row[4].strip()
            positions[label] = (float(row[1]), float(row[2]), float(row[3]))
    return positions


def _resolve_position(
    value: Any, eeg_positions: dict[str, tuple[float, float, float]]
) -> tuple[float, float, float]:
    if isinstance(value, str):
        if value in eeg_positions:
            return eeg_positions[value]
        raise ValueError(f"Electrode label {value!r} not found in EEG positions")
    return _as_xyz(value)


def _extract_pair_positions(
    pairs: Any, eeg_positions: dict[str, tuple[float, float, float]]
) -> list[list[tuple[float, float, float]]]:
    position_pairs = []
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(
                "Electrode overlay expects each channel to contain exactly "
                f"two electrodes; got {pair!r}"
            )
        position_pairs.append([_resolve_position(pos, eeg_positions) for pos in pair])
    return position_pairs


def _group_flat_positions(
    positions: list[tuple[float, float, float]]
) -> list[list[tuple[float, float, float]]]:
    if len(positions) % 2:
        raise ValueError(
            "Electrode overlay expects an even number of electrode coordinates "
            "so they can be grouped into channels."
        )
    return [positions[idx : idx + 2] for idx in range(0, len(positions), 2)]


def _extract_position_pairs(
    config_data: dict[str, Any],
    montage_name: str | None = None,
    eeg_positions_dir: str | Path | None = None,
) -> list[list[tuple[float, float, float]]]:
    eeg_positions = _load_eeg_positions(
        eeg_positions_dir, config_data.get("eeg_net")
    )

    for key in (
        "electrode_positions",
        "optimized_positions",
        "mapped_positions",
        "electrode_coordinates",
    ):
        if key in config_data:
            return _group_flat_positions([_as_xyz(pos) for pos in config_data[key]])

    if "electrode_pairs" in config_data:
        return _extract_pair_positions(config_data["electrode_pairs"], eeg_positions)

    montages = config_data.get("montages")
    if isinstance(montages, list):
        selected = [
            montage
            for montage in montages
            if montage_name is None or montage.get("name") == montage_name
        ]
        if montage_name and not selected:
            raise ValueError(f"Montage {montage_name!r} not found in config")
        position_pairs: list[list[tuple[float, float, float]]] = []
        for montage in selected:
            montage_eeg_positions = _load_eeg_positions(
                eeg_positions_dir, montage.get("eeg_net") or config_data.get("eeg_net")
            )
            for key in (
                "electrode_positions",
                "optimized_positions",
                "mapped_positions",
                "electrode_coordinates",
            ):
                if key in montage:
                    position_pairs.extend(
                        _group_flat_positions([_as_xyz(pos) for pos in montage[key]])
                    )
            if "electrode_pairs" in montage:
                position_pairs.extend(
                    _extract_pair_positions(
                        montage["electrode_pairs"], montage_eeg_positions
                    )
                )
        if position_pairs:
            return position_pairs

    raise ValueError(
        "No XYZ electrode positions found. Use a saved simulation config with "
        "electrode_pairs containing [x, y, z] coordinates, or a config with "
        "electrode_positions. Label montages require an EEG positions CSV."
    )


def _extract_xyz_positions(
    config_data: dict[str, Any],
    montage_name: str | None = None,
    eeg_positions_dir: str | Path | None = None,
) -> list[tuple[float, float, float]]:
    return [
        position
        for pair in _extract_position_pairs(config_data, montage_name, eeg_positions_dir)
        for position in pair
    ]


def _electrode_geometry(config_data: dict[str, Any]) -> tuple[str, np.ndarray]:
    geometry = config_data.get("electrode_geometry", {})
    shape = geometry.get("shape", config_data.get("electrode_shape", "ellipse"))
    dimensions = geometry.get(
        "dimensions", config_data.get("electrode_dimensions", [8.0, 8.0])
    )
    gel = float(geometry.get("gel_thickness", config_data.get("gel_thickness", 4.0)))
    rubber = float(
        geometry.get("rubber_thickness", config_data.get("rubber_thickness", 2.0))
    )

    dims = np.asarray(dimensions, dtype=float).reshape(-1)
    if dims.size == 1:
        dims = np.repeat(dims, 2)
    if dims.size < 2:
        raise ValueError("electrode dimensions must contain at least one value")
    if np.any(dims[:2] <= 0):
        raise ValueError("electrode dimensions must be positive")
    if gel < 0 or rubber < 0:
        raise ValueError("electrode thickness values must be non-negative")

    depth = gel + rubber
    if depth <= 0:
        depth = min(float(dims[0]), float(dims[1]))
    radii = np.array([dims[0] / 2.0, dims[1] / 2.0, depth / 2.0], dtype=float)
    return str(shape).lower(), radii


def _voxel_to_world(affine: np.ndarray, voxels: np.ndarray) -> np.ndarray:
    hom = np.c_[voxels, np.ones(len(voxels))]
    return (hom @ affine.T)[:, :3]


def _world_to_voxel(affine: np.ndarray, world: np.ndarray) -> np.ndarray:
    inv_affine = np.linalg.inv(affine)
    hom = np.r_[world, 1.0]
    return (inv_affine @ hom)[:3]


def _draw_electrode(
    mask: np.ndarray,
    affine: np.ndarray,
    center_xyz: tuple[float, float, float],
    radii_mm: np.ndarray,
    label_value: int,
    shape: str,
) -> None:
    center = np.asarray(center_xyz, dtype=float)
    voxel_sizes = np.sqrt(np.sum(affine[:3, :3] ** 2, axis=0))
    min_voxel_size = float(np.min(voxel_sizes[voxel_sizes > 0]))
    voxel_radius = int(np.ceil(float(np.max(radii_mm)) / min_voxel_size)) + 2
    center_voxel = _world_to_voxel(affine, center)

    lo = np.maximum(np.floor(center_voxel).astype(int) - voxel_radius, 0)
    hi = np.minimum(np.ceil(center_voxel).astype(int) + voxel_radius + 1, mask.shape)
    if np.any(lo >= hi):
        return

    grids = np.indices(tuple(hi - lo), dtype=float)
    ijk = np.stack([axis.ravel() + lo[idx] for idx, axis in enumerate(grids)], axis=1)
    world = _voxel_to_world(affine, ijk)
    scaled = (world - center) / radii_mm

    if shape in {"rect", "rectangle", "rectangular"}:
        inside = np.all(np.abs(scaled) <= 1.0, axis=1)
    else:
        inside = np.sum(scaled**2, axis=1) <= 1.0

    if not np.any(inside):
        return
    inside_ijk = ijk[inside].astype(int)
    mask[inside_ijk[:, 0], inside_ijk[:, 1], inside_ijk[:, 2]] = label_value


def electrode_overlay_lut_path(output_path: str | Path) -> Path:
    output_path = Path(output_path)
    name = output_path.name
    if name.endswith(".nii.gz"):
        stem = name[:-7]
    else:
        stem = output_path.stem
    return output_path.with_name(f"{stem}.lut")


def write_electrode_overlay_lut(path: str | Path, num_pairs: int) -> str:
    color_names = _montage_color_names()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write("# TI-Toolbox electrode channel LUT\n")
        for idx in range(1, num_pairs + 1):
            color_name = color_names[(idx - 1) % len(color_names)]
            red, green, blue = _MONTAGE_COLOR_RGB.get(color_name, (220, 220, 220))
            f.write(f"{idx} Channel_{idx} {red} {green} {blue} 0\n")
    return str(path)


def create_electrode_overlay_nifti(
    config_path: str | Path,
    reference_nifti: str | Path,
    output_path: str | Path,
    montage_name: str | None = None,
    eeg_positions_dir: str | Path | None = None,
) -> str:
    """Write a label-mask NIfTI showing XYZ electrode placements.

    The saved simulation ``config.json`` provides electrode centers and
    dimensions. The reference NIfTI provides the output grid and affine, so
    the overlay can be opened alongside that image in Freeview or another
    NIfTI viewer. Because SimNIBS configs do not store electrode normals, the
    pad volume is an axis-aligned approximation around each center.
    """
    import nibabel as nib

    config_path = Path(config_path)
    reference_nifti = Path(reference_nifti)
    output_path = Path(output_path)

    with config_path.open() as f:
        config_data = json.load(f)

    position_pairs = _extract_position_pairs(
        config_data, montage_name=montage_name, eeg_positions_dir=eeg_positions_dir
    )
    shape, radii_mm = _electrode_geometry(config_data)

    reference_img = nib.load(str(reference_nifti))
    mask = np.zeros(reference_img.shape[:3], dtype=np.uint16)
    affine = np.asarray(reference_img.affine, dtype=float)

    for pair_idx, pair_positions in enumerate(position_pairs, start=1):
        for center_xyz in pair_positions:
            _draw_electrode(mask, affine, center_xyz, radii_mm, pair_idx, shape)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = reference_img.header.copy()
    if hasattr(header, "set_data_dtype"):
        header.set_data_dtype(np.uint16)
    overlay_img = nib.Nifti1Image(mask, affine, header)
    nib.save(overlay_img, str(output_path))
    write_electrode_overlay_lut(
        electrode_overlay_lut_path(output_path), len(position_pairs)
    )
    return str(output_path)


def simulation_config_has_xyz_electrodes(
    config_path: str | Path,
    montage_name: str | None = None,
    eeg_positions_dir: str | Path | None = None,
) -> bool:
    """Return whether *config_path* contains resolvable electrode coordinates."""
    try:
        with Path(config_path).open() as f:
            config_data = json.load(f)
        _extract_xyz_positions(
            config_data,
            montage_name=montage_name,
            eeg_positions_dir=eeg_positions_dir,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    return True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Create a NIfTI electrode placement overlay from a simulation config."
    )
    parser.add_argument("config", help="Simulation config JSON")
    parser.add_argument("reference", help="Reference NIfTI defining grid and affine")
    parser.add_argument("output", help="Output overlay NIfTI path")
    parser.add_argument(
        "--montage",
        dest="montage_name",
        help="Montage name when using a multi-montage input config",
    )
    parser.add_argument(
        "--eeg-positions-dir",
        help="Directory containing EEG cap CSVs, or a direct EEG positions CSV path",
    )
    args = parser.parse_args(argv)
    create_electrode_overlay_nifti(
        args.config,
        args.reference,
        args.output,
        montage_name=args.montage_name,
        eeg_positions_dir=args.eeg_positions_dir,
    )


if __name__ == "__main__":
    main()
