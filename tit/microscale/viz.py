#!/usr/bin/env simnibs_python
"""Publication-oriented visualizations for microscale coupling.

Renders, all via matplotlib (no pyvista/VTK needed) so they run headless inside
the SimNIBS container:

* :func:`plot_morphology` -- the neuron's 3D morphology, colored by part.
* :func:`plot_cell_in_cortex` -- the neuron embedded in a patch of the subject's
  cortical surface at the target, oriented along the cortical normal.
* :func:`plot_efield_vectors` -- the TI E-field as 3D arrows around the target,
  with the neuron for scale.
* :func:`animate_response` -- a GIF clip: membrane potential along the neuron
  and the oscillating E-field drive over time.

The plotting functions take plain NumPy arrays (placed coordinates, per-section
spans, traces) so they are decoupled from NEURON; only the convenience wrappers
that build a cell touch :mod:`tit.microscale.models`.

KIND_COLORS maps the coarse section label to a color.
"""

from __future__ import annotations

import numpy as np

KIND_COLORS = {
    "soma": "#222222",
    "dendrite": "#1f78b4",
    "axon": "#e31a1c",
    "other": "#999999",
}


# ---------------------------------------------------------------------------
# Geometry helpers (pure)
# ---------------------------------------------------------------------------


def section_polylines(world_um: np.ndarray, spans: list) -> list:
    """Split placed segment coordinates into per-section polylines.

    Parameters
    ----------
    world_um : ndarray, shape (M, 3)
        Placed segment coordinates (um), segment order.
    spans : list
        ``Cell.section_spans()`` output: ``(name, kind, diam, start, count)``.

    Returns
    -------
    list of dict
        ``{"name", "kind", "diam", "coords"}`` per section.
    """
    world_um = np.asarray(world_um, dtype=float).reshape(-1, 3)
    out = []
    for name, kind, diam, start, count in spans:
        out.append(
            {
                "name": name,
                "kind": kind,
                "diam": diam,
                "coords": world_um[start : start + count],
            }
        )
    return out


def _equal_3d(ax, coords: np.ndarray, pad: float = 0.1) -> None:
    """Give a 3D axis an equal aspect bounding box around *coords*."""
    coords = np.asarray(coords).reshape(-1, 3)
    c = coords.mean(0)
    r = (coords.max(0) - coords.min(0)).max() * (0.5 + pad)
    r = max(r, 1.0)
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    try:
        ax.set_box_aspect((1, 1, 1))
    except Exception:  # noqa: BLE001 - older mpl
        pass


def crop_surface_patch(coords_mm, tris, center_mm, radius_mm):
    """Crop a triangular surface to a disk of *radius_mm* around *center_mm*.

    Keeps triangles whose vertices are all within the radius and remaps their
    vertex indices to the cropped node set.

    Parameters
    ----------
    coords_mm : ndarray (N, 3)
    tris : ndarray (F, 3)
    center_mm : ndarray (3,)
    radius_mm : float

    Returns
    -------
    tuple
        ``(patch_coords (K,3), patch_tris (G,3), keep_mask (N,))``.
    """
    coords = np.asarray(coords_mm, dtype=float).reshape(-1, 3)
    tris = np.asarray(tris, dtype=int).reshape(-1, 3)
    center = np.asarray(center_mm, dtype=float).reshape(3)
    within = np.linalg.norm(coords - center, axis=1) <= radius_mm
    keep_tri = within[tris].all(axis=1)
    sub_tris = tris[keep_tri]
    used = np.unique(sub_tris)
    remap = {old: new for new, old in enumerate(used)}
    new_tris = (
        np.vectorize(remap.get)(sub_tris) if len(sub_tris) else sub_tris.reshape(0, 3)
    )
    return coords[used], np.asarray(new_tris).reshape(-1, 3), within


def grid_around(center_mm, radius_mm, n=4):
    """Regular 3D grid of points within ±radius around a center (mm)."""
    center = np.asarray(center_mm, dtype=float).reshape(3)
    lin = np.linspace(-radius_mm, radius_mm, n)
    gx, gy, gz = np.meshgrid(lin, lin, lin, indexing="ij")
    return center + np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()])


# ---------------------------------------------------------------------------
# Static renders
# ---------------------------------------------------------------------------


def plot_morphology(cell, ax=None, title: str = "Neuron morphology"):
    """Draw the cell's 3D morphology, colored by part, linewidth ∝ diameter."""
    import matplotlib.pyplot as plt  # noqa: F401

    world = cell.segment_coords_um()
    lines = section_polylines(world, cell.section_spans())
    if ax is None:
        fig = plt.figure(figsize=(5, 6))
        ax = fig.add_subplot(111, projection="3d")
    seen = set()
    for ln in lines:
        c = KIND_COLORS.get(ln["kind"], KIND_COLORS["other"])
        label = ln["kind"] if ln["kind"] not in seen else None
        seen.add(ln["kind"])
        ax.plot(
            ln["coords"][:, 0],
            ln["coords"][:, 1],
            ln["coords"][:, 2],
            color=c,
            lw=max(1.0, ln["diam"]),
            solid_capstyle="round",
            label=label,
        )
    _equal_3d(ax, world)
    ax.set(xlabel="x (µm)", ylabel="y (µm)", zlabel="z (µm)", title=title)
    ax.legend(fontsize=8, loc="upper left")
    return ax


def plot_cell_in_cortex(
    world_um: np.ndarray,
    spans: list,
    patch_coords_mm: np.ndarray,
    patch_tris: np.ndarray,
    patch_scalar: np.ndarray | None = None,
    ax=None,
    title: str = "Neuron in cortical patch",
):
    """Render a cortical surface patch (mm) with the embedded neuron (um).

    The neuron coordinates are um in subject space; the patch is mm.  Both are
    drawn in mm (neuron converted) so the scales match.
    """
    import matplotlib.pyplot as plt
    from matplotlib.tri import Triangulation  # noqa: F401

    if ax is None:
        fig = plt.figure(figsize=(6.5, 6))
        ax = fig.add_subplot(111, projection="3d")

    pc = np.asarray(patch_coords_mm, dtype=float)
    tris = np.asarray(patch_tris, dtype=int)
    coll = ax.plot_trisurf(
        pc[:, 0],
        pc[:, 1],
        pc[:, 2],
        triangles=tris,
        linewidth=0,
        antialiased=True,
        alpha=0.5,
    )
    if patch_scalar is not None:
        coll.set_array(np.asarray(patch_scalar)[tris].mean(axis=1))
        coll.set_cmap("viridis")

    world_mm = np.asarray(world_um, dtype=float) / 1000.0
    for ln in section_polylines(world_mm, spans):
        ax.plot(
            ln["coords"][:, 0],
            ln["coords"][:, 1],
            ln["coords"][:, 2],
            color=KIND_COLORS.get(ln["kind"], KIND_COLORS["other"]),
            lw=max(1.2, ln["diam"]),
            solid_capstyle="round",
        )
    allpts = np.vstack([pc, world_mm])
    _equal_3d(ax, allpts, pad=0.05)
    ax.set(xlabel="x (mm)", ylabel="y (mm)", zlabel="z (mm)", title=title)
    return ax


def plot_efield_vectors(
    grid_mm: np.ndarray,
    e_vectors: np.ndarray,
    world_um: np.ndarray,
    spans: list,
    ax=None,
    title: str = "TI E-field around target",
    length_mm: float = 3.0,
):
    """3D quiver of E-field samples (mm) with the embedded neuron for scale."""
    import matplotlib.pyplot as plt

    if ax is None:
        fig = plt.figure(figsize=(6.5, 6))
        ax = fig.add_subplot(111, projection="3d")

    g = np.asarray(grid_mm, dtype=float).reshape(-1, 3)
    e = np.asarray(e_vectors, dtype=float).reshape(-1, 3)
    mag = np.linalg.norm(e, axis=1)
    unit = e / (mag.max() + 1e-12)
    q = ax.quiver(
        g[:, 0],
        g[:, 1],
        g[:, 2],
        unit[:, 0],
        unit[:, 1],
        unit[:, 2],
        length=length_mm,
        normalize=False,
        color="#444444",
        alpha=0.6,
        lw=1,
    )
    world_mm = np.asarray(world_um, dtype=float) / 1000.0
    for ln in section_polylines(world_mm, spans):
        ax.plot(
            ln["coords"][:, 0],
            ln["coords"][:, 1],
            ln["coords"][:, 2],
            color=KIND_COLORS.get(ln["kind"], KIND_COLORS["other"]),
            lw=max(1.2, ln["diam"]),
            solid_capstyle="round",
        )
    _equal_3d(ax, np.vstack([g, world_mm]), pad=0.1)
    ax.set(xlabel="x (mm)", ylabel="y (mm)", zlabel="z (mm)", title=title)
    ax.text2D(
        0.02,
        0.98,
        f"|E| max {mag.max():.2f} V/m",
        transform=ax.transAxes,
        fontsize=8,
        va="top",
    )
    return q


# ---------------------------------------------------------------------------
# Animation
# ---------------------------------------------------------------------------


def animate_response(
    world_um: np.ndarray,
    spans: list,
    t_ms: np.ndarray,
    v_all: np.ndarray,
    drive_dir: np.ndarray,
    drive_scalar: np.ndarray,
    out_path: str,
    n_frames: int = 60,
    fps: int = 15,
    vlim: tuple | None = None,
):
    """Write a GIF: membrane potential along the neuron + the E-field drive.

    Parameters
    ----------
    world_um : ndarray (M, 3)
        Placed segment coordinates (um).
    spans : list
        ``Cell.section_spans()``.
    t_ms : ndarray (T,)
        Time base (ms).
    v_all : ndarray (M, T)
        Per-segment membrane potential (mV).
    drive_dir : ndarray (3,)
        Unit direction of the applied field (for the moving arrow).
    drive_scalar : ndarray (T,)
        Instantaneous field drive (e.g. the carrier waveform), for the arrow
        length and the time-course inset.
    out_path : str
        Output ``.gif`` path.
    """
    import matplotlib.pyplot as plt
    from matplotlib import animation

    world = np.asarray(world_um, dtype=float)
    v_all = np.asarray(v_all, dtype=float)
    t_ms = np.asarray(t_ms, dtype=float)
    drive_scalar = np.asarray(drive_scalar, dtype=float)
    frames = np.linspace(0, v_all.shape[1] - 1, min(n_frames, v_all.shape[1])).astype(
        int
    )
    if vlim is None:
        vlim = (float(np.percentile(v_all, 1)), float(np.percentile(v_all, 99)))
    center = world.mean(0)
    span = (world.max(0) - world.min(0)).max()
    arrow_len = 0.45 * span
    dscale = drive_scalar / (np.abs(drive_scalar).max() + 1e-12)

    fig = plt.figure(figsize=(9, 5.2))
    ax = fig.add_subplot(121, projection="3d")
    axv = fig.add_subplot(222)
    axd = fig.add_subplot(224)
    cmap = plt.get_cmap("coolwarm")
    norm = plt.Normalize(*vlim)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    fig.colorbar(sm, ax=ax, shrink=0.6, label="Vm (mV)")

    soma_idx = next(
        (s[3] + s[4] // 2 for s in spans if s[1] == "soma"), v_all.shape[0] // 2
    )

    def draw(fr):
        ax.cla()
        v = v_all[:, fr]
        # color each compartment by its instantaneous Vm
        for name, kind, diam, start, count in spans:
            seg = world[start : start + count]
            vv = v[start : start + count]
            for k in range(len(seg) - 1):
                ax.plot(
                    seg[k : k + 2, 0],
                    seg[k : k + 2, 1],
                    seg[k : k + 2, 2],
                    color=cmap(norm(0.5 * (vv[k] + vv[k + 1]))),
                    lw=max(1.5, diam),
                    solid_capstyle="round",
                )
        # field arrow through the soma, length/sign follows the drive
        d = dscale[fr] * arrow_len
        ax.quiver(
            center[0] - drive_dir[0] * d,
            center[1] - drive_dir[1] * d,
            center[2] - drive_dir[2] * d,
            2 * drive_dir[0] * d,
            2 * drive_dir[1] * d,
            2 * drive_dir[2] * d,
            color="#33a02c",
            lw=2,
            arrow_length_ratio=0.15,
        )
        _equal_3d(ax, world, pad=0.25)
        ax.set(
            title=f"t = {t_ms[fr]:.1f} ms",
            xticklabels=[],
            yticklabels=[],
            zticklabels=[],
        )

        axv.cla()
        axv.plot(t_ms[: fr + 1], v_all[soma_idx, : fr + 1], color="#222")
        axv.set(xlim=(t_ms[0], t_ms[-1]), ylim=vlim, ylabel="soma Vm (mV)")
        axv.axvline(t_ms[fr], color="r", lw=0.8)

        axd.cla()
        axd.plot(t_ms[: fr + 1], drive_scalar[: fr + 1], color="#33a02c")
        axd.set(
            xlim=(t_ms[0], t_ms[-1]),
            ylim=(drive_scalar.min(), drive_scalar.max()),
            xlabel="time (ms)",
            ylabel="E-drive",
        )
        axd.axvline(t_ms[fr], color="r", lw=0.8)
        return []

    anim = animation.FuncAnimation(fig, draw, frames=frames, blit=False)
    anim.save(out_path, writer=animation.PillowWriter(fps=fps))
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Orchestration: produce all artifacts for one target
# ---------------------------------------------------------------------------


def render_target(
    subject_id,
    cfg,
    target_mm,
    normal,
    out_dir,
    patch_radius_mm=8.0,
    grid_radius_mm=6.0,
    clip_carriers=(100.0, 120.0),
    clip_amplitude=400.0,
    clip_duration=60.0,
    clip_dt=0.025,
):
    """Produce the four visualization artifacts for one target.

    Writes ``<stem>_morphology.png``, ``<stem>_cortex.png``,
    ``<stem>_efield.png`` and ``<stem>_clip.gif`` under *out_dir*, where the
    clip uses a lower-frequency, amplified drive so the membrane response is
    visible (the real-amplitude kHz drive is far sub-threshold).

    Returns
    -------
    dict
        Map of artifact name -> path.
    """
    import os
    from dataclasses import replace

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from simnibs.mesh_tools import mesh_io

    from tit.microscale.coupling import _load_pair_meshes, simulate_response
    from tit.microscale.field_sampler import place_morphology, sample_at
    from tit.microscale.models import build_cell
    from tit.paths import get_path_manager

    pm = get_path_manager()
    os.makedirs(out_dir, exist_ok=True)
    stem = f"sub-{subject_id}_{cfg.sim_name}"
    target_mm = np.asarray(target_mm, dtype=float).reshape(3)
    normal = np.asarray(normal, dtype=float).reshape(3)

    cell = build_cell(cfg.model)
    spans = cell.section_spans()
    world_um = place_morphology(
        cell.segment_coords_um(), cell.soma_coord_um(), target_mm * 1000.0, normal
    )
    out = {}

    # (1) morphology
    ax = plot_morphology(cell, title=f"{cfg.model} morphology")
    p = os.path.join(out_dir, f"{stem}_morphology.png")
    ax.figure.savefig(p, dpi=130)
    plt.close(ax.figure)
    out["morphology"] = p

    # (2) cell in cortex patch (from the TI central surface). Glob for the
    # surface rather than assuming its stem matches the simulation folder name
    # (the montage name can differ from the folder, e.g. "L_Insula" vs
    # "L_Insula_scalar").
    import glob

    surf_dir = os.path.join(pm.ti_mesh_dir(subject_id, cfg.sim_name), "surfaces")
    cands = sorted(glob.glob(os.path.join(surf_dir, "*_TI_central.msh")))
    if cands:
        surf = mesh_io.read_msh(cands[0])
        coords = surf.nodes.node_coord
        tris = surf.elm.node_number_list[surf.elm.elm_type == 2][:, :3] - 1
        scal = (
            np.asarray(surf.field["TI_max"].value).reshape(-1)
            if "TI_max" in surf.field
            else None
        )
        pc, pt, mask = crop_surface_patch(coords, tris, target_mm, patch_radius_mm)
        ps = scal[mask] if scal is not None else None
        if len(pt):
            ax = plot_cell_in_cortex(
                world_um, spans, pc, pt, ps, title="Neuron in cortical patch (TI_max)"
            )
            p = os.path.join(out_dir, f"{stem}_cortex.png")
            ax.figure.savefig(p, dpi=130)
            plt.close(ax.figure)
            out["cortex"] = p
    else:
        print(
            f"      (no TI_central surface in {surf_dir}; skipping cortex panel)",
            flush=True,
        )

    # (3) E-field vectors around the target
    m1, m2 = _load_pair_meshes(subject_id, cfg)
    grid = grid_around(target_mm, grid_radius_mm, n=4)
    e1g = sample_at(m1, grid)
    e2g = sample_at(m2, grid)
    q = plot_efield_vectors(
        grid,
        np.asarray(e1g) + np.asarray(e2g),
        world_um,
        spans,
        title="TI E-field (pair1+pair2) around target",
    )
    p = os.path.join(out_dir, f"{stem}_efield.png")
    q.axes.figure.savefig(p, dpi=130)
    plt.close(q.axes.figure)
    out["efield"] = p

    # (4) animated clip (lower-frequency, amplified so Vm is visible)
    c = replace(
        cfg,
        carrier_freqs=tuple(clip_carriers),
        amplitude_scale=clip_amplitude,
        duration=clip_duration,
        dt=clip_dt,
    )
    r = simulate_response(c, target_mm, normal, m1, m2, return_traces=True)
    e1 = np.asarray(sample_at(m1, target_mm.reshape(1, 3))).reshape(3)
    e2 = np.asarray(sample_at(m2, target_mm.reshape(1, 3))).reshape(3)
    ddir = (e1 + e2) / (np.linalg.norm(e1 + e2) + 1e-12)
    t = r["t"]
    f1, f2 = clip_carriers
    drive = np.sin(2 * np.pi * f1 * t / 1000.0) + np.sin(2 * np.pi * f2 * t / 1000.0)
    p = os.path.join(out_dir, f"{stem}_clip.gif")
    animate_response(
        r["world_um"], spans, t, r["v_all"], ddir, drive, p, n_frames=60, fps=15
    )
    out["clip"] = p
    return out
