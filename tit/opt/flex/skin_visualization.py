"""Valid-skin-region visualization for flex-search outputs."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nibabel
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from tit.opt.config import FlexConfig


def create_valid_skin_region_visualization(
    config: FlexConfig,
    output_folder: str,
    logger,
) -> None:
    """Write valid-skin-region PNG/PDF files for a flex-search run."""
    try:
        from simnibs.mesh_tools import mesh_io
        from simnibs.utils.file_finder import Templates
        from simnibs.utils.transformations import (
            create_new_connectivity_list_point_mask,
            subject2mni_coords,
        )
        from tit.paths import get_path_manager
    except ImportError as exc:
        logger.warning(f"Could not import SimNIBS skin visualization dependencies: {exc}")
        return

    pm = get_path_manager()
    m2m = Path(pm.m2m(config.subject_id))
    mesh_path = m2m / f"{m2m.name.removeprefix('m2m_')}.msh"
    if not mesh_path.exists():
        candidates = list(m2m.glob("*.msh"))
        if not candidates:
            logger.warning(f"Could not create skin visualization: no .msh under {m2m}")
            return
        mesh_path = candidates[0]

    try:
        mesh = mesh_io.read_msh(str(mesh_path))
        mesh.fn = str(mesh_path)
        mesh_relabel = mesh.relabel_internal_air()
        skin_surface = mesh_relabel.crop_mesh(tags=1005)
        points = skin_surface.nodes.node_coord.copy()
        con = skin_surface.elm.node_number_list[:, :3] - 1

        raw_mask = _skin_mask_from_mni_volume(
            skin_surface,
            mesh_relabel,
            Templates().mni_volume_upper_head_mask,
            subject2mni_coords,
        )
        mask = _largest_component_mask(
            points,
            con,
            raw_mask,
            create_new_connectivity_list_point_mask,
        )
        if config.skin_region_margin_mm:
            mask = _apply_margin(
                points,
                con,
                mask,
                float(config.skin_region_margin_mm),
                create_new_connectivity_list_point_mask,
            )

        guard_mask = None
        guard_boundary_mask = None
        plot_points = points
        fiducial_frame = None
        if config.avoid_landmark_regions and config.skin_region_margin_mm > 0:
            fiducials = _read_fiducials(m2m)
            fiducial_frame = _make_fiducial_frame(fiducials)
            guard_mask = _landmark_guard_mask(points, fiducials, fiducial_frame)
            mask = _largest_component_mask(
                points,
                con,
                mask & ~guard_mask,
                create_new_connectivity_list_point_mask,
            )
            guard_boundary_mask = np.zeros(points.shape[0], dtype=bool)
            guard_boundary_mask[_boundary_nodes(con, guard_mask, side=True)] = True
            plot_points = _local_coords(points, *fiducial_frame)

        electrodes = _load_electrodes(
            config.skin_visualization_net,
            points,
            plot_points,
            mask,
            fiducial_frame,
            logger,
        )

        vis_dir = Path(output_folder) / "skin_visualization"
        vis_dir.mkdir(parents=True, exist_ok=True)
        _plot_skin_region(
            plot_points=plot_points,
            mask=mask,
            out_png=vis_dir / "skin_surface_2d.png",
            out_pdf=vis_dir / "skin_surface_2d.pdf",
            guard_mask=guard_mask,
            guard_boundary_mask=guard_boundary_mask,
            electrodes=electrodes,
        )
        logger.info(f"Valid skin region visualization saved to: {vis_dir}")
    except Exception as exc:
        logger.warning(f"Could not create valid skin region visualization: {exc}")


def _skin_mask_from_mni_volume(skin_surface, mesh, fn_electrode_mask, transform_fn):
    nodes_all = skin_surface.nodes.node_coord.copy()
    mask_img = nibabel.load(fn_electrode_mask)
    mask_img_data = mask_img.get_fdata()

    skin_nodes_mni_ras = transform_fn(
        coordinates=nodes_all,
        m2m_folder=os.path.split(mesh.fn)[0],
        transformation_type="nonl",
    )
    skin_nodes_mni_voxel = (
        np.floor(
            np.linalg.inv(mask_img.affine)
            @ np.hstack(
                (skin_nodes_mni_ras, np.ones((skin_nodes_mni_ras.shape[0], 1)))
            ).T
        )[:3, :]
        .T.astype(int)
    )
    for axis in range(3):
        skin_nodes_mni_voxel[
            skin_nodes_mni_voxel[:, axis] >= mask_img.shape[axis], axis
        ] = (mask_img.shape[axis] - 1)

    mask_valid_nodes = mask_img_data[
        skin_nodes_mni_voxel[:, 0],
        skin_nodes_mni_voxel[:, 1],
        skin_nodes_mni_voxel[:, 2],
    ].astype(bool)
    mask_valid_nodes[(skin_nodes_mni_voxel < 0).any(axis=1)] = False
    return mask_valid_nodes


def _largest_component_mask(points, con, mask, filter_fn):
    nodes_valid, con_valid = filter_fn(points=points, con=con, point_mask=mask)
    if con_valid.size == 0 or nodes_valid.size == 0:
        return np.zeros(points.shape[0], dtype=bool)

    tri_domain = np.ones(con_valid.shape[0], dtype=int) * -1
    point_domain = np.ones(nodes_valid.shape[0], dtype=int) * -1
    domain = 0
    while (tri_domain == -1).any():
        nodes_idx = np.array([])
        tri_idx = np.where(tri_domain == -1)[0][0]
        n_current = -1
        n_last = 0
        while n_last != n_current:
            n_last = n_current
            nodes_idx = np.unique(np.append(nodes_idx, con_valid[tri_idx, :])).astype(
                int
            )
            tri_idx = np.isin(con_valid, nodes_idx).any(axis=1)
            n_current = np.sum(tri_idx)
        tri_domain[tri_idx] = domain
        point_domain[nodes_idx] = domain
        domain += 1

    main_domain = np.argmax([np.sum(point_domain == d) for d in range(domain)])
    nodes_final, _ = filter_fn(
        points=nodes_valid,
        con=con_valid,
        point_mask=point_domain == main_domain,
    )
    _, indices = cKDTree(points).query(nodes_final, k=1)
    final_mask = np.zeros(points.shape[0], dtype=bool)
    final_mask[indices] = True
    return final_mask


def _boundary_nodes(con, mask, side):
    edges = np.vstack((con[:, [0, 1]], con[:, [1, 2]], con[:, [2, 0]]))
    crosses = mask[edges[:, 0]] != mask[edges[:, 1]]
    edge_nodes = np.unique(edges[crosses])
    return edge_nodes[mask[edge_nodes] == side]


def _apply_margin(points, con, base_mask, margin, filter_fn):
    next_mask = base_mask.copy()
    if margin > 0:
        seeds = points[_boundary_nodes(con, base_mask, side=True)]
        candidates = np.where(~base_mask)[0]
        if seeds.size and candidates.size:
            dist, _ = cKDTree(seeds).query(points[candidates], k=1)
            next_mask[candidates[dist <= margin]] = True
    else:
        seeds = points[_boundary_nodes(con, base_mask, side=False)]
        candidates = np.where(base_mask)[0]
        if seeds.size and candidates.size:
            dist, _ = cKDTree(seeds).query(points[candidates], k=1)
            next_mask[candidates[dist <= abs(margin)]] = False
    return _largest_component_mask(points, con, next_mask, filter_fn)


def _read_fiducials(m2m):
    fiducials_path = m2m / "eeg_positions" / "Fiducials.csv"
    fiducials = {}
    with open(fiducials_path, newline="") as f:
        for row in csv.reader(f):
            if len(row) >= 5 and row[0] == "Fiducial":
                fiducials[row[4]] = np.array(row[1:4], dtype=float)
    missing = {"Nz", "LPA", "RPA"} - set(fiducials)
    if missing:
        raise ValueError(f"{fiducials_path} is missing fiducials: {sorted(missing)}")
    return fiducials


def _make_fiducial_frame(fiducials):
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


def _local_coords(points, origin, x_axis, y_axis, z_axis):
    centered = points - origin
    return np.column_stack((centered @ x_axis, centered @ y_axis, centered @ z_axis))


def _landmark_guard_mask(points, fiducials, frame):
    origin, x_axis, y_axis, z_axis = frame
    coords = _local_coords(points, origin, x_axis, y_axis, z_axis)
    landmarks = {
        name: _local_coords(pos[None, :], origin, x_axis, y_axis, z_axis)[0]
        for name, pos in fiducials.items()
    }
    width = np.linalg.norm(fiducials["RPA"] - fiducials["LPA"])
    nz = landmarks["Nz"]
    guard = np.zeros(points.shape[0], dtype=bool)

    ear_radius = 28.0
    ear_offset = -3.0 * y_axis - 8.0 * z_axis
    for name in ("LPA", "RPA"):
        center = _local_coords(
            (fiducials[name] + ear_offset)[None, :],
            origin,
            x_axis,
            y_axis,
            z_axis,
        )[0]
        radius_y = np.where(coords[:, 1] >= center[1], 0.8 * ear_radius, ear_radius)
        ear_distance = (
            ((coords[:, 0] - center[0]) / ear_radius) ** 2
            + ((coords[:, 1] - center[1]) / radius_y) ** 2
            + ((coords[:, 2] - center[2]) / (1.1 * ear_radius)) ** 2
        )
        guard |= ear_distance <= 1.0

    eye_y = nz[1] - 0.10 * width
    eye_z = nz[2] - 0.06 * width
    horizontal = (np.maximum(np.abs(coords[:, 0]) - 0.23 * width, 0.0) / 18.0) ** 2
    anterior = ((coords[:, 1] - eye_y) / (0.16 * width)) ** 2
    vertical = ((coords[:, 2] - eye_z) / 18.0) ** 2
    guard |= horizontal + anterior + vertical <= 1.0
    return guard


def _load_electrodes(net_csv, points, plot_points, mask, frame, logger):
    if not net_csv or not os.path.exists(net_csv):
        return None
    try:
        first = pd.read_csv(net_csv, header=None, sep=",", nrows=1)
        skiprows = 0
        try:
            float(first.iloc[0, 1])
            float(first.iloc[0, 2])
            float(first.iloc[0, 3])
        except (ValueError, TypeError):
            skiprows = 1
        df = pd.read_csv(net_csv, header=None, sep=",", skiprows=skiprows)
        df.columns = ["type", "x", "y", "z", "label"]
        electrodes = df[df["type"] == "Electrode"]
        if electrodes.empty:
            return None
        raw_positions = electrodes[["x", "y", "z"]].to_numpy(dtype=float)
        _, nearest_idx = cKDTree(points).query(raw_positions, k=1)
        positions = (
            _local_coords(raw_positions, *frame) if frame is not None else raw_positions
        )
        return {
            "positions": positions,
            "labels": electrodes["label"].to_numpy(),
            "valid_mask": mask[nearest_idx],
        }
    except Exception as exc:
        logger.warning(f"Error loading skin visualization electrodes: {exc}")
        return None


def _plot_skin_region(
    plot_points,
    mask,
    out_png,
    out_pdf,
    guard_mask=None,
    guard_boundary_mask=None,
    electrodes=None,
):
    views = [
        ("top x/y", 0, 1, np.ones(plot_points.shape[0], dtype=bool), False),
        ("front x/z", 0, 2, plot_points[:, 1] >= 0, False),
        ("right y/z", 1, 2, plot_points[:, 0] >= 0, False),
        ("left y/z", 1, 2, plot_points[:, 0] <= 0, True),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    for idx, (title, x_idx, y_idx, view_mask, invert_x) in enumerate(views):
        ax = axes[idx // 2, idx % 2]
        invalid_view = (~mask) & view_mask
        valid_view = mask & view_mask
        if invalid_view.any():
            ax.scatter(
                plot_points[invalid_view, x_idx],
                plot_points[invalid_view, y_idx],
                c="#c7c7c7",
                alpha=0.25,
                s=0.25,
                label="Invalid",
                rasterized=True,
            )
        if valid_view.any():
            ax.scatter(
                plot_points[valid_view, x_idx],
                plot_points[valid_view, y_idx],
                c="#178c36",
                alpha=0.9,
                s=0.25,
                label="Valid",
                rasterized=True,
            )
        if guard_mask is not None and guard_mask.any():
            guard_view = guard_mask & view_mask
            ax.scatter(
                plot_points[guard_view, x_idx],
                plot_points[guard_view, y_idx],
                c="#c7c7c7",
                alpha=0.25,
                s=0.25,
                rasterized=True,
            )
        if guard_boundary_mask is not None and guard_boundary_mask.any():
            boundary_view = guard_boundary_mask & view_mask
            ax.scatter(
                plot_points[boundary_view, x_idx],
                plot_points[boundary_view, y_idx],
                c="#c62828",
                alpha=0.9,
                s=1.0,
                label="Eye/ear exclusion",
                rasterized=True,
            )
        if electrodes is not None:
            elec_pos = electrodes["positions"]
            elec_valid = electrodes["valid_mask"]
            labels = electrodes["labels"]
            if elec_valid.any():
                ax.scatter(
                    elec_pos[elec_valid, x_idx],
                    elec_pos[elec_valid, y_idx],
                    c="#2b5db8",
                    s=42,
                    marker="o",
                    label="Valid electrodes",
                    edgecolors="white",
                    linewidth=0.7,
                    zorder=10,
                )
                for pos, label in zip(elec_pos[elec_valid], labels[elec_valid]):
                    ax.annotate(
                        label,
                        (pos[x_idx], pos[y_idx]),
                        fontsize=6,
                        ha="center",
                        va="center",
                        color="white",
                        zorder=11,
                    )
            invalid_elec = ~elec_valid
            if invalid_elec.any():
                ax.scatter(
                    elec_pos[invalid_elec, x_idx],
                    elec_pos[invalid_elec, y_idx],
                    c="#c62828",
                    s=44,
                    marker="X",
                    label="Invalid electrodes",
                    edgecolors="white",
                    linewidth=0.8,
                    zorder=10,
                )
        ax.set_title(title)
        ax.axis("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.legend(loc="upper right", fontsize=8, frameon=False)
        if invert_x:
            ax.invert_xaxis()
    fig.tight_layout()
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_pdf, dpi=600, bbox_inches="tight")
    plt.close(fig)
