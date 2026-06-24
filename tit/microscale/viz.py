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

# Region palette following Shirinpour et al. 2021 (Fig. 2D): red soma, orange
# basal, green apical, blue tuft, purple axon; AIS/nodes highlighted.
KIND_COLORS = {
    "soma": "#d62728",
    "basal": "#ff7f0e",
    "apical": "#2ca02c",
    "tuft": "#1f78b4",
    "ais": "#9467bd",
    "axon": "#6a3d9a",
    "node": "#111111",
    "dendrite": "#1f78b4",  # back-compat (ball_stick)
    "other": "#999999",
}


# Aberra et al. 2018/2020 neurite-TYPE palette (their populated-gyrus figure):
# axon red, apical dendrite blue, basal dendrite green, soma dark.
NEURITE_COLORS_ABERRA = {
    "soma": "#222222",
    "basal": "#2ca02c",
    "apical": "#1f3fb4",
    "tuft": "#1f3fb4",
    "ais": "#c81e1e",
    "axon": "#c81e1e",
    "node": "#c81e1e",
    "dendrite": "#1f3fb4",
    "other": "#999999",
}

#: Available color schemes for neuron rendering.
COLOR_SCHEMES = {"region": KIND_COLORS, "aberra": NEURITE_COLORS_ABERRA}


def _kind_color(kind: str, scheme: str = "region") -> str:
    """Color for a region tag under a named color scheme."""
    table = COLOR_SCHEMES.get(scheme, KIND_COLORS)
    return table.get(kind, table.get("other", "#999999"))


def _lw_for_diam(diam: float) -> float:
    """Line width for a compartment diameter (um), clipped for readability."""
    return float(min(6.0, max(0.6, diam * 1.1)))


def _add_scale_bar(ax, coords, length, unit="µm"):
    """Draw a 3D scale bar of *length* near the lower-front of *coords*."""
    coords = np.asarray(coords).reshape(-1, 3)
    lo = coords.min(0)
    span = (coords.max(0) - coords.min(0)).max()
    x0 = lo[0]
    y0 = lo[1]
    z0 = lo[2] - 0.05 * span
    ax.plot([x0, x0 + length], [y0, y0], [z0, z0], color="k", lw=3)
    ax.text(
        x0 + length / 2,
        y0,
        z0 - 0.04 * span,
        f"{length:g} {unit}",
        fontsize=8,
        ha="center",
        va="top",
    )


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
# Temporal-interference field physics (pure)
# ---------------------------------------------------------------------------


def instantaneous_field(
    e1_vec: np.ndarray,
    e2_vec: np.ndarray,
    f1: float,
    f2: float,
    t_ms: np.ndarray,
) -> np.ndarray:
    """Instantaneous TI E-field vector over time.

    The resultant of two carrier fields that point in *different* directions::

        E_inst(t) = e1_vec * sin(2π f1 t) + e2_vec * sin(2π f2 t)

    When ``e1_vec`` and ``e2_vec`` are non-parallel, the tip of this vector
    sweeps a Lissajous-like locus and its *direction* rotates over the beat
    period -- the defining "rotating modulation vector" of temporal
    interference.  When they are parallel the resultant stays collinear.

    Parameters
    ----------
    e1_vec, e2_vec : ndarray, shape (3,)
        Pair-1 and pair-2 E-field vectors in V/m.
    f1, f2 : float
        Carrier frequencies in Hz.
    t_ms : ndarray, shape (T,)
        Time samples in ms.

    Returns
    -------
    ndarray, shape (T, 3)
        ``E_inst(t)`` in V/m.
    """
    e1 = np.asarray(e1_vec, dtype=float).reshape(3)
    e2 = np.asarray(e2_vec, dtype=float).reshape(3)
    t_s = np.asarray(t_ms, dtype=float).reshape(-1) / 1000.0
    s1 = np.sin(2.0 * np.pi * f1 * t_s).reshape(-1, 1)
    s2 = np.sin(2.0 * np.pi * f2 * t_s).reshape(-1, 1)
    return s1 * e1 + s2 * e2


# ---------------------------------------------------------------------------
# Static renders
# ---------------------------------------------------------------------------


def plot_morphology(
    cell,
    ax=None,
    title: str = "Neuron morphology",
    values=None,
    cmap: str = "coolwarm",
    vlim=None,
    scale_bar: float = 100.0,
):
    """Draw the cell's 3D morphology, linewidth ∝ diameter.

    By default each section is colored by its region (Shirinpour-style palette).
    If *values* (a per-segment array, e.g. Vm or quasipotential) is given, every
    compartment is instead colored by that value on *cmap*.
    """
    import matplotlib.pyplot as plt

    spans = cell.section_spans()
    world = cell.segment_coords_um()
    if ax is None:
        fig = plt.figure(figsize=(5.5, 6.5))
        ax = fig.add_subplot(111, projection="3d")

    if values is not None:
        values = np.asarray(values, dtype=float)
        if vlim is None:
            vlim = (float(np.percentile(values, 2)), float(np.percentile(values, 98)))
        norm = plt.Normalize(*vlim)
        cm = plt.get_cmap(cmap)
        for _name, _kind, diam, start, count in spans:
            seg = world[start : start + count]
            vv = values[start : start + count]
            for k in range(len(seg) - 1):
                ax.plot(
                    seg[k : k + 2, 0],
                    seg[k : k + 2, 1],
                    seg[k : k + 2, 2],
                    color=cm(norm(0.5 * (vv[k] + vv[k + 1]))),
                    lw=_lw_for_diam(diam),
                    solid_capstyle="round",
                )
        sm = plt.cm.ScalarMappable(cmap=cm, norm=norm)
        ax.figure.colorbar(sm, ax=ax, shrink=0.55, pad=0.08, label="value")
    else:
        seen = set()
        for ln in section_polylines(world, spans):
            c = KIND_COLORS.get(ln["kind"], KIND_COLORS["other"])
            label = ln["kind"] if ln["kind"] not in seen else None
            seen.add(ln["kind"])
            ax.plot(
                ln["coords"][:, 0],
                ln["coords"][:, 1],
                ln["coords"][:, 2],
                color=c,
                lw=_lw_for_diam(ln["diam"]),
                solid_capstyle="round",
                label=label,
            )
        ax.legend(fontsize=8, loc="upper left", markerscale=0.5)

    _equal_3d(ax, world)
    if scale_bar:
        _add_scale_bar(ax, world, scale_bar)
    ax.set(title=title)
    ax.set_axis_off()
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
        alpha=0.3,
    )
    if patch_scalar is not None:
        coll.set_array(np.asarray(patch_scalar)[tris].mean(axis=1))
        coll.set_cmap("viridis")

    # Neuron drawn prominently on top: thicker than its true diameter so the
    # ~1 mm cell stays visible against a multi-mm cortical patch.
    world_mm = np.asarray(world_um, dtype=float) / 1000.0
    for ln in section_polylines(world_mm, spans):
        ax.plot(
            ln["coords"][:, 0],
            ln["coords"][:, 1],
            ln["coords"][:, 2],
            color=KIND_COLORS.get(ln["kind"], KIND_COLORS["other"]),
            lw=max(1.6, _lw_for_diam(ln["diam"]) * 0.9),
            solid_capstyle="round",
            zorder=5,
        )
    soma_mm = world_mm[: spans[0][4]].mean(0) if spans else world_mm.mean(0)
    ax.scatter(*soma_mm, color=KIND_COLORS["soma"], s=40, zorder=6)
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
    e1_vec: np.ndarray,
    e2_vec: np.ndarray,
    f1: float,
    f2: float,
    out_path: str,
    n_frames: int = 60,
    fps: int = 15,
    vlim: tuple | None = None,
):
    """Write a GIF: membrane potential along the neuron + the rotating TI field.

    The green field arrow through the soma follows the *true* instantaneous TI
    resultant ``E_inst(t) = e1*sin(2π f1 t) + e2*sin(2π f2 t)``, so it both
    rotates in direction and changes length frame to frame as the modulation
    vector sweeps over the beat cycle.

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
    e1_vec, e2_vec : ndarray (3,)
        Pair-1 and pair-2 E-field vectors (V/m) at the target.
    f1, f2 : float
        Carrier frequencies (Hz) of the two pairs.
    out_path : str
        Output ``.gif`` path.
    """
    import matplotlib.pyplot as plt
    from matplotlib import animation

    world = np.asarray(world_um, dtype=float)
    v_all = np.asarray(v_all, dtype=float)
    t_ms = np.asarray(t_ms, dtype=float)
    frames = np.linspace(0, v_all.shape[1] - 1, min(n_frames, v_all.shape[1])).astype(
        int
    )
    if vlim is None:
        vlim = (float(np.percentile(v_all, 1)), float(np.percentile(v_all, 99)))
    center = world.mean(0)
    span = (world.max(0) - world.min(0)).max()
    arrow_len = 0.45 * span

    # Precompute the full rotating field vector once; normalize the arrow by the
    # max magnitude over the clip so the longest arrow fits the scene.
    e_inst = instantaneous_field(e1_vec, e2_vec, f1, f2, t_ms)  # (T, 3)
    e_mag = np.linalg.norm(e_inst, axis=1)
    e_mag_max = float(e_mag.max()) + 1e-12

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
    comp_colors = ("#1f77b4", "#ff7f0e", "#2ca02c")  # Ex, Ey, Ez
    comp_labels = ("Ex", "Ey", "Ez")

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
        # Field arrow through the soma ALONG the true rotating resultant, with
        # length proportional to |E_inst| (normalized by the clip max).
        evec = e_inst[fr]
        d = (evec / e_mag_max) * arrow_len
        ax.quiver(
            center[0] - d[0],
            center[1] - d[1],
            center[2] - d[2],
            2 * d[0],
            2 * d[1],
            2 * d[2],
            color="#33a02c",
            lw=2,
            arrow_length_ratio=0.15,
        )
        _equal_3d(ax, world, pad=0.25)
        ax.set(
            title=f"t = {t_ms[fr]:.1f} ms  |E| = {e_mag[fr]:.1f} V/m",
            xticklabels=[],
            yticklabels=[],
            zticklabels=[],
        )

        axv.cla()
        axv.plot(t_ms[: fr + 1], v_all[soma_idx, : fr + 1], color="#222")
        axv.set(xlim=(t_ms[0], t_ms[-1]), ylim=vlim, ylabel="soma Vm (mV)")
        axv.axvline(t_ms[fr], color="r", lw=0.8)

        axd.cla()
        for j in range(3):
            axd.plot(
                t_ms[: fr + 1],
                e_inst[: fr + 1, j],
                color=comp_colors[j],
                lw=0.9,
                label=comp_labels[j],
            )
        axd.set(
            xlim=(t_ms[0], t_ms[-1]),
            ylim=(float(e_inst.min()), float(e_inst.max())),
            xlabel="time (ms)",
            ylabel="E_inst (V/m)",
        )
        axd.axvline(t_ms[fr], color="r", lw=0.8)
        axd.legend(fontsize=6, ncol=3, loc="upper right")
        return []

    anim = animation.FuncAnimation(fig, draw, frames=frames, blit=False)
    anim.save(out_path, writer=animation.PillowWriter(fps=fps))
    plt.close(fig)
    return out_path


def plot_field_hodograph(
    e1_vec: np.ndarray,
    e2_vec: np.ndarray,
    f1: float,
    f2: float,
    ax=None,
    n_cycles: int = 1,
    title: str = "TI field hodograph (rotating modulation vector)",
):
    """Draw the 2D hodograph of the rotating TI resultant.

    Projects ``E_inst(t)`` over *n_cycles* of the beat period onto the plane
    spanned by ``e1_vec`` and ``e2_vec`` and plots the tip trajectory, colored
    by time.  The two pair-field axes (E1 green, E2 magenta) are drawn as
    reference arrows.  A closed, non-degenerate locus proves the resultant
    rotates; a line means the two fields are collinear.

    Parameters
    ----------
    e1_vec, e2_vec : ndarray, shape (3,)
        Pair-1 and pair-2 E-field vectors (V/m).
    f1, f2 : float
        Carrier frequencies (Hz).
    n_cycles : int
        Number of beat periods to trace.
    """
    import matplotlib.pyplot as plt

    e1 = np.asarray(e1_vec, dtype=float).reshape(3)
    e2 = np.asarray(e2_vec, dtype=float).reshape(3)

    # Orthonormal basis (u, w) for the plane spanned by e1, e2: u along e1,
    # w the component of e2 orthogonal to u. If e1, e2 are collinear, w is
    # degenerate and the locus collapses to a line (still meaningful).
    n1 = np.linalg.norm(e1)
    u = e1 / n1 if n1 > 0 else np.array([1.0, 0.0, 0.0])
    w_raw = e2 - (e2 @ u) * u
    nw = np.linalg.norm(w_raw)
    w = w_raw / nw if nw > 1e-12 else np.zeros(3)

    # Beat period (s) -> sample over n_cycles. Fall back to a fixed window when
    # the carriers are equal (no beat).
    df = abs(f1 - f2)
    beat_s = 1.0 / df if df > 0 else 1.0 / max(f1, f2, 1.0)
    t_ms = np.linspace(0.0, n_cycles * beat_s * 1000.0, 2000)
    e_inst = instantaneous_field(e1, e2, f1, f2, t_ms)  # (T, 3)

    px = e_inst @ u
    py = e_inst @ w

    if ax is None:
        fig, ax = plt.subplots(figsize=(5.5, 5.5))

    pts = np.column_stack([px, py])
    segs = np.stack([pts[:-1], pts[1:]], axis=1)
    from matplotlib.collections import LineCollection

    lc = LineCollection(segs, cmap="viridis", array=t_ms[:-1], lw=1.6)
    ax.add_collection(lc)
    ax.figure.colorbar(lc, ax=ax, shrink=0.75, label="time (ms)")

    # Reference pair-field axes in the same (u, w) plane.
    e1u, e1w = e1 @ u, e1 @ w
    e2u, e2w = e2 @ u, e2 @ w
    ax.annotate(
        "",
        xy=(e1u, e1w),
        xytext=(0, 0),
        arrowprops=dict(arrowstyle="->", color="#2ca02c", lw=2),
    )
    ax.annotate(
        "",
        xy=(e2u, e2w),
        xytext=(0, 0),
        arrowprops=dict(arrowstyle="->", color="#d62728", lw=2),
    )
    ax.text(e1u, e1w, " E1", color="#2ca02c", fontsize=9, va="center")
    ax.text(e2u, e2w, " E2", color="#d62728", fontsize=9, va="center")

    lim = float(np.abs(pts).max()) * 1.15 + 1e-9
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal", "box")
    ax.axhline(0, color="#cccccc", lw=0.6, zorder=0)
    ax.axvline(0, color="#cccccc", lw=0.6, zorder=0)
    ax.set(
        xlabel="E along E1 (V/m)",
        ylabel="E perpendicular (V/m)",
        title=title,
    )
    angle = float(
        np.degrees(
            np.arccos(np.clip((e1 @ e2) / (n1 * np.linalg.norm(e2) + 1e-12), -1, 1))
        )
    )
    ax.text(
        0.02,
        0.98,
        f"∠(E1,E2) = {angle:.0f}°",
        transform=ax.transAxes,
        fontsize=8,
        va="top",
    )
    return ax


# ---------------------------------------------------------------------------
# Populated cortex (Aberra-style "populated gyrus")
# ---------------------------------------------------------------------------


def plot_population_in_cortex(
    placed_cells,
    surface_pts_mm=None,
    surface_tris=None,
    surface_scalar=None,
    project_axes=(0, 2),
    color_scheme: str = "aberra",
    scale_bar_mm: float = 0.25,
    ax=None,
    title: str = "Populated cortex",
    region_label: str | None = None,
    lw: float = 0.35,
):
    """Render many neurons along a cortical cross-section, Aberra-figure style.

    A clean **2D** projection (the slab axis dropped), drawn with one
    ``LineCollection`` per neurite type for speed and print-quality — neurites
    colored by TYPE (axon red / apical blue / basal green under ``"aberra"``),
    embedded in the cortical sheet (the projected surface triangles), with a
    scale bar.

    Parameters
    ----------
    placed_cells : list
        List of cells; each cell is a list of ``(kind, points_mm (K,3))`` from
        :func:`tit.microscale.population.place_spec_world`.
    surface_pts_mm : ndarray (N,3), optional
        Cortical surface vertices (the gyral sheet the cells sit on).
    surface_tris : ndarray (F,3), optional
        Triangles of *surface_pts_mm*; if given, the cortical ribbon is drawn as
        a translucent filled cross-section so the cells are *embedded*, not
        floating.  If absent, the vertices are scattered faintly instead.
    surface_scalar : ndarray (N,), optional
        Per-vertex scalar (e.g. ``TI_normal``) to color the cortical ribbon.
    project_axes : tuple of int
        The two world axes to project onto (default (x, z); the slab axis y is
        dropped).
    color_scheme : str
        ``"aberra"`` (neurite type) or ``"region"``.
    scale_bar_mm : float
        Scale-bar length in mm (0.25 = 250 µm).
    region_label : str, optional
        Anatomical context annotated on the figure (atlas region / sphere / space).
    """
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection, PolyCollection

    ix, iy = project_axes
    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 7))

    allpts = []
    if surface_pts_mm is not None and len(surface_pts_mm):
        sp = np.asarray(surface_pts_mm, dtype=float).reshape(-1, 3)
        if surface_tris is not None and len(surface_tris):
            tris = np.asarray(surface_tris, dtype=int)
            polys = sp[tris][:, :, [ix, iy]]  # (F, 3, 2)
            pc = PolyCollection(polys, zorder=0, linewidths=0.0)
            if surface_scalar is not None:
                pc.set_array(np.asarray(surface_scalar)[tris].mean(axis=1))
                pc.set_cmap("viridis")
                pc.set_alpha(0.35)
            else:
                pc.set_facecolor("#d9d2c5")
                pc.set_alpha(0.45)
            ax.add_collection(pc)
        else:
            ax.scatter(sp[:, ix], sp[:, iy], s=6, color="#888888", alpha=0.5, zorder=1)
        allpts.append(sp[:, [ix, iy]])

    # Group segments by color -> one LineCollection per neurite type.
    by_color: dict = {}
    soma_pts = []
    for cell in placed_cells:
        for kind, pts in cell:
            pts = np.asarray(pts, dtype=float)[:, [ix, iy]]
            allpts.append(pts)
            if kind == "soma":
                soma_pts.append(pts.mean(0))
                continue
            segs = np.stack([pts[:-1], pts[1:]], axis=1)
            by_color.setdefault(_kind_color(kind, color_scheme), []).append(segs)
    for color, seglist in by_color.items():
        lc = LineCollection(np.concatenate(seglist), colors=color, linewidths=lw)
        lc.set_zorder(2)
        ax.add_collection(lc)
    if soma_pts:
        soma_pts = np.array(soma_pts)
        ax.scatter(
            soma_pts[:, 0],
            soma_pts[:, 1],
            s=4,
            color=_kind_color("soma", color_scheme),
            zorder=3,
        )

    pts_all = np.vstack(allpts) if allpts else np.zeros((1, 2))
    ax.set_aspect("equal", "box")
    ax.autoscale_view()
    # Scale bar (lower-left).
    lo = pts_all.min(0)
    span = (pts_all.max(0) - pts_all.min(0)).max()
    x0, y0 = lo[0] + 0.02 * span, lo[1] - 0.04 * span
    ax.plot([x0, x0 + scale_bar_mm], [y0, y0], color="k", lw=2.5)
    ax.text(
        x0 + scale_bar_mm / 2,
        y0 - 0.02 * span,
        f"{scale_bar_mm * 1000:g} µm",
        ha="center",
        va="top",
        fontsize=8,
    )
    if color_scheme == "aberra":
        from matplotlib.lines import Line2D

        ax.legend(
            handles=[
                Line2D([0], [0], color="#c81e1e", lw=2, label="axon"),
                Line2D([0], [0], color="#1f3fb4", lw=2, label="apical dendrite"),
                Line2D([0], [0], color="#2ca02c", lw=2, label="basal dendrite"),
            ],
            fontsize=8,
            loc="upper right",
            frameon=False,
        )
    if region_label:
        ax.text(
            0.02,
            0.98,
            region_label,
            transform=ax.transAxes,
            fontsize=9,
            va="top",
            ha="left",
            bbox=dict(boxstyle="round", fc="white", ec="#999999", alpha=0.8),
        )
    ax.axis("off")
    ax.set_title(title)
    return ax


def render_population_region(
    subject_id,
    cfg,
    out_dir,
    region: dict,
    name: str,
    n_cells: int = 50,
    thickness_mm: float = 2.0,
    color_scheme: str = "aberra",
):
    """Populate and render an arbitrary region (atlas / MNI-sphere / subcortical).

    See :func:`tit.microscale.population.select_region` for the *region* spec.
    Cortical regions are drawn as an embedded gyral cross-section; subcortical
    (volume) regions as the nucleus point-cloud with radially-oriented cells.

    Returns
    -------
    str
        Path to ``<stem>_population_<name>.png``.
    """
    import os

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from tit.microscale.morphology import pyramidal_l5
    from tit.microscale.population import (
        place_spec_world,
        sample_cortical_strip,
        select_region,
    )

    reg = select_region(subject_id, cfg, region)
    coords, normals, scalar = reg["coords_mm"], reg["normals"], reg["scalar"]
    if len(coords) == 0:
        raise ValueError(f"region {name!r} selected 0 vertices")

    spec = pyramidal_l5(seed=cfg.seed)
    rng = np.random.default_rng(cfg.seed)

    if reg["domain"] == "surface":
        slab_axis = int(np.argmin(np.ptp(coords - coords.mean(0), axis=0)))
        project_axes = tuple(a for a in range(3) if a != slab_axis)
        c0 = float(np.median(coords[:, slab_axis]))
        if reg["tris"] is not None and len(reg["tris"]):
            tri_c = coords[reg["tris"]].mean(axis=1)
            slab_tris = reg["tris"][
                np.abs(tri_c[:, slab_axis] - c0) <= thickness_mm / 2.0
            ]
        else:
            slab_tris = None
        strip_xyz, strip_nrm = sample_cortical_strip(
            coords,
            normals,
            n_cells,
            axis=slab_axis,
            thickness_mm=thickness_mm,
            rng=rng,
        )
        placed = [
            place_spec_world(spec, xyz, nrm) for xyz, nrm in zip(strip_xyz, strip_nrm)
        ]
        ax = plot_population_in_cortex(
            placed,
            surface_pts_mm=coords,
            surface_tris=slab_tris,
            surface_scalar=scalar,
            project_axes=project_axes,
            color_scheme=color_scheme,
            scale_bar_mm=1.0,
            region_label=f"sub-{subject_id} • {reg['label']}\n{len(placed)} cells",
            title=f"Populated {name} — {len(placed)} {cfg.model} cells",
        )
    else:  # volume (subcortical): subsample the nucleus cloud, radial cells
        if len(coords) > n_cells:
            pick = rng.choice(len(coords), n_cells, replace=False)
        else:
            pick = np.arange(len(coords))
        placed = [place_spec_world(spec, coords[i], normals[i]) for i in pick]
        # project onto the two widest axes of the cloud
        widths = np.ptp(coords, axis=0)
        project_axes = tuple(int(a) for a in np.argsort(widths)[::-1][:2])
        ax = plot_population_in_cortex(
            placed,
            surface_pts_mm=coords,
            surface_tris=None,
            project_axes=project_axes,
            color_scheme=color_scheme,
            scale_bar_mm=1.0,
            region_label=f"sub-{subject_id} • {reg['label']}\n"
            f"{len(placed)} cells (radial orientation)",
            title=f"Populated {name} — {len(placed)} {cfg.model} cells",
        )

    stem = f"sub-{subject_id}_{cfg.sim_name}"
    path = os.path.join(out_dir, f"{stem}_population_{name}.png")
    ax.figure.savefig(path, dpi=150)
    plt.close(ax.figure)
    return path


def render_population_cortex(
    subject_id,
    cfg,
    out_dir,
    n_cells: int = 50,
    thickness_mm: float = 2.0,
    patch_radius_mm: float = 12.0,
    color_scheme: str = "aberra",
):
    """Produce an Aberra-style populated-gyrus figure for a subject's cluster.

    Localizes to a cortical patch around the field focus (the max-``TI_normal``
    vertex), takes a thin slab through it, **embeds** the neurons in the actual
    cortical-surface ribbon of that slab (a translucent cross-section colored by
    ``TI_normal``), places one neuron at each surface site (oriented to the local
    cortical normal), and colors them by neurite type with a scale bar -- so the
    cells sit *in* the gyrus, not floating.

    Returns
    -------
    str
        Path to the written ``<stem>_population_cortex.png``.
    """
    import os

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from tit.microscale.morphology import pyramidal_l5
    from tit.microscale.population import (
        load_cluster_surface,
        load_cluster_triangles,
        place_spec_world,
        sample_cortical_strip,
    )

    coords_mm, normals, ti_normal = load_cluster_surface(subject_id, cfg)
    tris = load_cluster_triangles(subject_id, cfg)

    # Localize to a patch around the field focus (else a slab cuts the whole
    # cortex into a chaotic cross-section and the cells are sub-pixel). Crop
    # inline so vertices, normals, scalar and triangles all share one indexing.
    focus = coords_mm[int(np.argmax(ti_normal))]
    near = np.linalg.norm(coords_mm - focus, axis=1) <= patch_radius_mm
    keep_tri = near[tris].all(axis=1)
    used = np.unique(tris[keep_tri])
    remap = np.full(len(coords_mm), -1, dtype=int)
    remap[used] = np.arange(len(used))
    patch_coords = coords_mm[used]
    patch_nrm = normals[used]
    patch_scalar = ti_normal[used]
    patch_tris = remap[tris[keep_tri]]

    # Slab axis = the patch's THINNEST in-plane direction, so the slab is a clean
    # gyral cross-section rather than an oblique cut.
    slab_axis = int(np.argmin(np.ptp(patch_coords - patch_coords.mean(0), axis=0)))
    project_axes = tuple(a for a in range(3) if a != slab_axis)

    # Keep only the ribbon triangles whose centroid falls in the slab.
    c0 = float(np.median(patch_coords[:, slab_axis]))
    tri_c = patch_coords[patch_tris].mean(axis=1)
    slab_tris = patch_tris[np.abs(tri_c[:, slab_axis] - c0) <= thickness_mm / 2.0]

    rng = np.random.default_rng(cfg.seed)
    strip_xyz, strip_nrm = sample_cortical_strip(
        patch_coords,
        patch_nrm,
        n_cells,
        axis=slab_axis,
        thickness_mm=thickness_mm,
        rng=rng,
    )

    spec = pyramidal_l5(seed=cfg.seed)
    placed = [
        place_spec_world(spec, xyz, nrm) for xyz, nrm in zip(strip_xyz, strip_nrm)
    ]
    ax = plot_population_in_cortex(
        placed,
        surface_pts_mm=patch_coords,
        surface_tris=slab_tris,
        surface_scalar=patch_scalar,
        project_axes=project_axes,
        color_scheme=color_scheme,
        scale_bar_mm=1.0,
        region_label=f"sub-{subject_id} • subject space\n"
        f"patch r={patch_radius_mm:g} mm around TI_normal focus\n"
        f"ribbon colored by TI_normal",
        title=f"Populated cortex — {len(placed)} {cfg.model} cells "
        f"(sub-{subject_id})",
    )
    stem = f"sub-{subject_id}_{cfg.sim_name}"
    path = os.path.join(out_dir, f"{stem}_population_cortex.png")
    ax.figure.savefig(path, dpi=150)
    plt.close(ax.figure)
    return path


# ---------------------------------------------------------------------------
# Orchestration: produce all artifacts for one target
# ---------------------------------------------------------------------------


def render_target(
    subject_id,
    cfg,
    target_mm,
    normal,
    out_dir,
    patch_radius_mm=4.0,
    grid_radius_mm=3.0,
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

    # (3b) morphology colored by the applied quasipotential Ψ (Shirinpour Fig 2F)
    from tit.microscale.coupling import per_pair_quasipotentials

    ve1, ve2 = per_pair_quasipotentials(cell, target_mm, normal, m1, m2)
    psi = ve1 + ve2
    ax = plot_morphology(
        cell,
        values=psi,
        cmap="coolwarm",
        title="Quasipotential Ψ from the TI field (mV)",
    )
    p = os.path.join(out_dir, f"{stem}_quasipotential.png")
    ax.figure.savefig(p, dpi=130)
    plt.close(ax.figure)
    out["quasipotential"] = p

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
    t = r["t"]
    f1, f2 = clip_carriers
    p = os.path.join(out_dir, f"{stem}_clip.gif")
    animate_response(
        r["world_um"], spans, t, r["v_all"], e1, e2, f1, f2, p, n_frames=60, fps=15
    )
    out["clip"] = p

    # (5) hodograph -- the figure that proves the resultant rotates.
    ax = plot_field_hodograph(e1, e2, f1, f2, n_cycles=1)
    p = os.path.join(out_dir, f"{stem}_hodograph.png")
    ax.figure.savefig(p, dpi=130)
    plt.close(ax.figure)
    out["hodograph"] = p
    return out
