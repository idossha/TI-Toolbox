#!/usr/bin/env python3
"""Visualize SimNIBS TES flex valid-skin masks across margin values."""

from __future__ import annotations

import argparse
import copy
import csv
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nibabel
import numpy as np
from scipy.spatial import cKDTree

from simnibs.mesh_tools import mesh_io
from simnibs.utils.file_finder import Templates
from simnibs.utils.transformations import (
    create_new_connectivity_list_point_mask,
    subject2mni_coords,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--m2m", required=True, help="Path to m2m subject folder")
    parser.add_argument(
        "--margins",
        default="-20,-10,-5,0,5,10,20",
        help="Comma-separated skin-region margins in mm",
    )
    parser.add_argument(
        "--out-dir",
        default="tmp/skin_region_margin",
        help="Directory for PNG and CSV outputs",
    )
    parser.add_argument(
        "--landmark-guards",
        action="store_true",
        help="Exclude ears and inferred orbital regions using scalp fiducial landmarks",
    )
    parser.add_argument(
        "--ear-guard-radius",
        type=float,
        default=28.0,
        help="Radius in mm to exclude around LPA/RPA when landmark guards are enabled",
    )
    parser.add_argument(
        "--eye-guard-radius",
        type=float,
        default=18.0,
        help="End-cap radius in mm for the connected inferred orbital exclusion zone",
    )
    parser.add_argument(
        "--eye-guard-height",
        type=float,
        default=18.0,
        help="Superior-inferior radius in mm for inferred orbital exclusion zones",
    )
    return parser.parse_args()


def skin_mask_from_mni_volume(skin_surface, mesh, fn_electrode_mask: str) -> np.ndarray:
    nodes_all = skin_surface.nodes.node_coord.copy()
    mask_img = nibabel.load(fn_electrode_mask)
    mask_img_data = mask_img.get_fdata()

    skin_nodes_mni_ras = subject2mni_coords(
        coordinates=nodes_all,
        m2m_folder=os.path.split(mesh.fn)[0],
        transformation_type="nonl",
    )
    skin_nodes_mni_voxel = (
        np.floor(
            np.linalg.inv(mask_img.affine)
            @ np.hstack(
                (
                    skin_nodes_mni_ras,
                    np.ones(skin_nodes_mni_ras.shape[0])[:, np.newaxis],
                )
            ).transpose()
        )[:3, :]
        .transpose()
        .astype(int)
    )
    skin_nodes_mni_voxel[skin_nodes_mni_voxel[:, 0] >= mask_img.shape[0], 0] = (
        mask_img.shape[0] - 1
    )
    skin_nodes_mni_voxel[skin_nodes_mni_voxel[:, 1] >= mask_img.shape[1], 1] = (
        mask_img.shape[1] - 1
    )
    skin_nodes_mni_voxel[skin_nodes_mni_voxel[:, 2] >= mask_img.shape[2], 2] = (
        mask_img.shape[2] - 1
    )

    mask_valid_nodes = mask_img_data[
        skin_nodes_mni_voxel[:, 0],
        skin_nodes_mni_voxel[:, 1],
        skin_nodes_mni_voxel[:, 2],
    ].astype(bool)
    mask_valid_nodes[(skin_nodes_mni_voxel < 0).any(axis=1)] = False
    return mask_valid_nodes


def largest_component_mask(points: np.ndarray, con: np.ndarray, mask: np.ndarray) -> np.ndarray:
    nodes_valid, con_valid = create_new_connectivity_list_point_mask(
        points=points,
        con=con,
        point_mask=mask,
    )
    if con_valid.size == 0 or nodes_valid.size == 0:
        return np.zeros(points.shape[0], dtype=bool)

    tri_domain = np.ones(con_valid.shape[0], dtype=int) * -1
    point_domain = np.ones(nodes_valid.shape[0], dtype=int) * -1
    domain = 0

    while (tri_domain == -1).any():
        nodes_idx_of_domain = np.array([])
        tri_idx_of_domain = np.where(tri_domain == -1)[0][0]
        n_current = -1
        n_last = 0
        while n_last != n_current:
            n_last = copy.deepcopy(n_current)
            nodes_idx_of_domain = np.unique(
                np.append(nodes_idx_of_domain, con_valid[tri_idx_of_domain, :])
            ).astype(int)
            tri_idx_of_domain = np.isin(con_valid, nodes_idx_of_domain).any(axis=1)
            n_current = np.sum(tri_idx_of_domain)
        tri_domain[tri_idx_of_domain] = domain
        point_domain[nodes_idx_of_domain] = domain
        domain += 1

    domain_idx_main = np.argmax([np.sum(point_domain == d) for d in range(domain)])
    nodes_final, _ = create_new_connectivity_list_point_mask(
        points=nodes_valid,
        con=con_valid,
        point_mask=point_domain == domain_idx_main,
    )

    tree = cKDTree(points)
    _, indices = tree.query(nodes_final, k=1)
    final_mask = np.zeros(points.shape[0], dtype=bool)
    final_mask[indices] = True
    return final_mask


def boundary_nodes(con: np.ndarray, mask: np.ndarray, side: bool) -> np.ndarray:
    edges = np.vstack((con[:, [0, 1]], con[:, [1, 2]], con[:, [2, 0]]))
    crosses = mask[edges[:, 0]] != mask[edges[:, 1]]
    edge_nodes = np.unique(edges[crosses])
    return edge_nodes[mask[edge_nodes] == side]


def apply_margin(points: np.ndarray, con: np.ndarray, base_mask: np.ndarray, margin: float) -> np.ndarray:
    if margin == 0:
        return base_mask.copy()

    next_mask = base_mask.copy()
    if margin > 0:
        seeds = points[boundary_nodes(con, base_mask, side=True)]
        candidates = np.where(~base_mask)[0]
        if seeds.size and candidates.size:
            dist, _ = cKDTree(seeds).query(points[candidates], k=1)
            next_mask[candidates[dist <= margin]] = True
    else:
        seeds = points[boundary_nodes(con, base_mask, side=False)]
        candidates = np.where(base_mask)[0]
        if seeds.size and candidates.size:
            dist, _ = cKDTree(seeds).query(points[candidates], k=1)
            next_mask[candidates[dist <= abs(margin)]] = False

    return largest_component_mask(points, con, next_mask)


def read_fiducials(m2m: Path) -> dict[str, np.ndarray]:
    fiducials_path = m2m / "eeg_positions" / "Fiducials.csv"
    fiducials: dict[str, np.ndarray] = {}
    with open(fiducials_path, newline="") as f:
        for row in csv.reader(f):
            if len(row) >= 5 and row[0] == "Fiducial":
                fiducials[row[4]] = np.array(row[1:4], dtype=float)
    missing = {"Nz", "LPA", "RPA"} - set(fiducials)
    if missing:
        raise ValueError(f"{fiducials_path} is missing fiducials: {sorted(missing)}")
    return fiducials


def fiducial_frame(fiducials: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    origin = 0.5 * (fiducials["LPA"] + fiducials["RPA"])
    x_axis = fiducials["RPA"] - fiducials["LPA"]
    x_axis /= np.linalg.norm(x_axis)

    y_axis = fiducials["Nz"] - origin
    y_axis -= np.dot(y_axis, x_axis) * x_axis
    y_axis /= np.linalg.norm(y_axis)

    z_axis = np.cross(x_axis, y_axis)
    z_axis /= np.linalg.norm(z_axis)
    if z_axis[2] < 0:
        z_axis *= -1
    return origin, x_axis, y_axis, z_axis


def local_coords(
    points: np.ndarray,
    origin: np.ndarray,
    x_axis: np.ndarray,
    y_axis: np.ndarray,
    z_axis: np.ndarray,
) -> np.ndarray:
    centered = points - origin
    return np.column_stack(
        (
            centered @ x_axis,
            centered @ y_axis,
            centered @ z_axis,
        )
    )


def landmark_guard_mask(
    points: np.ndarray,
    fiducials: dict[str, np.ndarray],
    ear_radius: float,
    eye_radius: float,
    eye_height: float,
) -> np.ndarray:
    origin, x_axis, y_axis, z_axis = fiducial_frame(fiducials)
    coords = local_coords(points, origin, x_axis, y_axis, z_axis)
    landmarks = {
        name: local_coords(pos[None, :], origin, x_axis, y_axis, z_axis)[0]
        for name, pos in fiducials.items()
    }
    width = np.linalg.norm(fiducials["RPA"] - fiducials["LPA"])
    nz = landmarks["Nz"]

    guard = np.zeros(points.shape[0], dtype=bool)
    ear_offset = -3.0 * y_axis - 8.0 * z_axis
    for name in ("LPA", "RPA"):
        center = local_coords(
            (fiducials[name] + ear_offset)[None, :],
            origin,
            x_axis,
            y_axis,
            z_axis,
        )[0]
        radius_x = ear_radius
        radius_y = np.where(coords[:, 1] >= center[1], 0.8 * ear_radius, ear_radius)
        radius_z = 1.1 * ear_radius
        ear_distance = (
            ((coords[:, 0] - center[0]) / radius_x) ** 2
            + ((coords[:, 1] - center[1]) / radius_y) ** 2
            + ((coords[:, 2] - center[2]) / radius_z) ** 2
        )
        guard |= ear_distance <= 1.0

    eye_y = nz[1] - 0.10 * width
    eye_z = nz[2] - 0.06 * width
    anterior_radius = 0.16 * width
    eye_half_span = 0.23 * width
    horizontal = (np.maximum(np.abs(coords[:, 0]) - eye_half_span, 0.0) / eye_radius) ** 2
    anterior = ((coords[:, 1] - eye_y) / anterior_radius) ** 2
    vertical = ((coords[:, 2] - eye_z) / eye_height) ** 2
    guard |= horizontal + anterior + vertical <= 1.0

    return guard


def plot_masks(
    points: np.ndarray,
    masks: list[tuple[str, np.ndarray]],
    out_png: Path,
    guard_mask: np.ndarray | None = None,
    guard_boundary_mask: np.ndarray | None = None,
    plot_points: np.ndarray | None = None,
) -> None:
    if plot_points is None:
        plot_points = points
    view_specs = [
        ("top x/y", 0, 1, plot_points[:, 0] == plot_points[:, 0], False),
        ("front x/z", 0, 2, plot_points[:, 1] >= 0, False),
        ("right y/z", 1, 2, plot_points[:, 0] >= 0, False),
        ("left y/z", 1, 2, plot_points[:, 0] <= 0, True),
    ]
    fig, axes = plt.subplots(len(masks), len(view_specs), figsize=(18, 2.4 * len(masks)))
    if len(masks) == 1:
        axes = np.array([axes])

    for row, (label, mask) in enumerate(masks):
        for col, (view_name, x_idx, y_idx, view_filter, invert_x) in enumerate(view_specs):
            ax = axes[row, col]
            display_invalid_mask = ~mask
            display_valid_mask = mask
            if guard_mask is not None:
                display_invalid_mask = display_invalid_mask | guard_mask
                display_valid_mask = display_valid_mask & ~guard_mask
            invalid = display_invalid_mask & view_filter
            valid = display_valid_mask & view_filter
            invalid_style = {
                "s": 0.25,
                "c": "#c7c7c7",
                "alpha": 0.25,
                "rasterized": True,
            }
            if view_name == "top x/y":
                ax.scatter(
                    plot_points[invalid, x_idx],
                    plot_points[invalid, y_idx],
                    **invalid_style,
                )
                ax.scatter(
                    plot_points[valid, x_idx],
                    plot_points[valid, y_idx],
                    s=0.35,
                    c="#187a2f",
                    alpha=0.75,
                    rasterized=True,
                )
            else:
                ax.scatter(
                    plot_points[valid, x_idx],
                    plot_points[valid, y_idx],
                    s=0.35,
                    c="#187a2f",
                    alpha=0.75,
                    rasterized=True,
                )
                ax.scatter(
                    plot_points[invalid, x_idx],
                    plot_points[invalid, y_idx],
                    **invalid_style,
                )
            if guard_mask is not None:
                guarded = guard_mask & view_filter
                ax.scatter(
                    plot_points[guarded, x_idx],
                    plot_points[guarded, y_idx],
                    **invalid_style,
                )
            if guard_boundary_mask is not None:
                guarded_boundary = guard_boundary_mask & view_filter
                ax.scatter(
                    plot_points[guarded_boundary, x_idx],
                    plot_points[guarded_boundary, y_idx],
                    s=1.3,
                    c="#7f1010",
                    alpha=0.8,
                    rasterized=True,
                )
            ax.set_aspect("equal")
            if invert_x:
                ax.invert_xaxis()
            ax.axis("off")
            pct = 100.0 * np.count_nonzero(mask) / len(mask)
            ax.set_title(f"{label} ({pct:.1f}% valid), {view_name}")

    fig.tight_layout()
    fig.savefig(out_png, dpi=220)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    margins = [float(item.strip()) for item in args.margins.split(",") if item.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    m2m = Path(args.m2m)
    mesh_path = m2m / f"{m2m.name.removeprefix('m2m_')}.msh"
    if not mesh_path.exists():
        candidates = list(m2m.glob("*.msh"))
        if not candidates:
            raise FileNotFoundError(f"No .msh file found under {m2m}")
        mesh_path = candidates[0]

    mesh = mesh_io.read_msh(str(mesh_path))
    mesh.fn = str(mesh_path)
    mesh_relabel = mesh.relabel_internal_air()
    skin_surface = mesh_relabel.crop_mesh(tags=1005)
    points = skin_surface.nodes.node_coord.copy()
    con = skin_surface.elm.node_number_list[:, :3] - 1
    electrode_mask = Templates().mni_volume_upper_head_mask

    raw_mask = skin_mask_from_mni_volume(skin_surface, mesh_relabel, electrode_mask)
    base_mask = largest_component_mask(points, con, raw_mask)
    margin_masks = [(margin, apply_margin(points, con, base_mask, margin)) for margin in margins]

    guard_mask = None
    guard_boundary_mask = None
    fiducials = None
    plot_points = points
    if args.landmark_guards:
        fiducials = read_fiducials(m2m)
        guard_mask = landmark_guard_mask(
            points,
            fiducials,
            ear_radius=args.ear_guard_radius,
            eye_radius=args.eye_guard_radius,
            eye_height=args.eye_guard_height,
        )
        guard_boundary_mask = np.zeros(points.shape[0], dtype=bool)
        guard_boundary_mask[boundary_nodes(con, guard_mask, side=True)] = True
        plot_points = local_coords(points, *fiducial_frame(fiducials))
    masks = []
    for margin, mask in margin_masks:
        if guard_mask is not None and margin > 0:
            mask = largest_component_mask(points, con, mask & ~guard_mask)
        masks.append((f"{margin:+g} mm", mask))

    suffix = "_landmark_guarded" if args.landmark_guards else ""
    out_png = out_dir / f"valid_skin_region_margin_comparison{suffix}.png"
    plot_masks(
        points,
        masks,
        out_png,
        guard_mask=guard_mask,
        guard_boundary_mask=guard_boundary_mask,
        plot_points=plot_points,
    )

    out_csv = out_dir / f"valid_skin_region_margin_counts{suffix}.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["margin_mm", "valid_nodes", "total_nodes", "valid_percent", "guarded_nodes"]
        )
        guarded_nodes = int(np.count_nonzero(guard_mask)) if guard_mask is not None else 0
        for (margin, _), (_, mask) in zip(margin_masks, masks):
            writer.writerow(
                [
                    margin,
                    int(np.count_nonzero(mask)),
                    len(mask),
                    100.0 * np.count_nonzero(mask) / len(mask),
                    guarded_nodes,
                ]
            )

    print(out_png)
    print(out_csv)


if __name__ == "__main__":
    main()
