#!/usr/bin/env simnibs_python
"""Figures for the microscale polarization map (matplotlib, headless).

A deliberately small, literature-standard set (Aberra et al. 2020/2023; Wang et
al. 2022; Shirinpour et al. 2021) -- not a gallery:

* :func:`render_polarization_summary` -- THE default figure: the cortical patch
  colored by somatic ΔVm next to the population histogram of ΔVm, annotated with
  the firing-threshold margin.  Emitted by
  :func:`tit.microscale.population.run_population`.
* :func:`plot_polarization_map` / :func:`plot_polarization_histogram` -- the two
  panels, reusable on plain NumPy arrays.
* :func:`plot_morphology` -- a single cell colored by region or by the applied
  quasipotential Ψ (the field-induced dipole along the morphology).
* :func:`render_population_region` / :func:`plot_population_3d` -- the optional
  "populated gyrus" publication figure: many L5 cells embedded in a named GM
  region, oriented to the cortical normal.

All figures run with the ``Agg`` backend (no pyvista/VTK); they take NumPy
arrays so they are decoupled from NEURON.
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


def _add_scale_bar(ax, coords, length, unit="µm"):
    """Draw a 3D scale bar of *length* near the lower-front of *coords*."""
    coords = np.asarray(coords).reshape(-1, 3)
    lo = coords.min(0)
    span = (coords.max(0) - coords.min(0)).max()
    x0, y0, z0 = lo[0], lo[1], lo[2] - 0.05 * span
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


def window_patch(coords_mm, tris, scalar, focus_mm, span_mm):
    """Crop a triangular surface to a contiguous patch around *focus_mm*.

    Keeps vertices within ``span_mm`` of the focus and the triangles wholly
    inside, remapping triangle indices to the cropped vertex set.  Used to render
    a clean, fast patch around the field hotspot instead of a whole hemisphere.

    Returns
    -------
    tuple
        ``(patch_coords (K,3), patch_tris (G,3), patch_scalar (K,))``.
    """
    coords = np.asarray(coords_mm, dtype=float).reshape(-1, 3)
    scalar = np.asarray(scalar, dtype=float).reshape(-1)
    focus = np.asarray(focus_mm, dtype=float).reshape(3)
    near = np.linalg.norm(coords - focus, axis=1) <= span_mm
    if not near.any():
        near = np.ones(len(coords), dtype=bool)
    used = np.where(near)[0]
    remap = np.full(len(coords), -1, dtype=int)
    remap[used] = np.arange(len(used))
    if tris is not None and len(tris):
        tris = np.asarray(tris, dtype=int)
        keep = near[tris].all(axis=1)
        patch_tris = remap[tris[keep]]
    else:
        patch_tris = np.empty((0, 3), dtype=int)
    return coords[used], patch_tris, scalar[used]


def instantaneous_field(e1_vec, e2_vec, f1, f2, t_ms):
    """Instantaneous TI E-field resultant over time, ``E1·sin + E2·sin``.

    When the two pair fields point in different directions the tip of this
    vector sweeps a Lissajous locus and its *direction rotates* over the beat
    period -- the defining feature of temporal interference (and the reason the
    time-domain view needs the two HF fields, not the scalar TI envelope).

    Parameters
    ----------
    e1_vec, e2_vec : ndarray (3,)
        Pair-1 and pair-2 E-field vectors (V/m).
    f1, f2 : float
        Carrier frequencies (Hz).
    t_ms : ndarray (T,)
        Time samples (ms).

    Returns
    -------
    ndarray (T, 3)
        ``E_inst(t)`` in V/m.
    """
    e1 = np.asarray(e1_vec, dtype=float).reshape(3)
    e2 = np.asarray(e2_vec, dtype=float).reshape(3)
    t_s = np.asarray(t_ms, dtype=float).reshape(-1) / 1000.0
    s1 = np.sin(2.0 * np.pi * f1 * t_s).reshape(-1, 1)
    s2 = np.sin(2.0 * np.pi * f2 * t_s).reshape(-1, 1)
    return s1 * e1 + s2 * e2


# ---------------------------------------------------------------------------
# Polarization map (the headline figure)
# ---------------------------------------------------------------------------


def plot_polarization_map(
    coords_mm,
    tris,
    delta_vm,
    ax=None,
    title: str = "Somatic polarization ΔVm",
    clabel: str = "ΔVm (mV)",
    vlim=None,
):
    """Render a cortical patch colored by somatic polarization ΔVm.

    ΔVm is signed (depolarizing positive, hyperpolarizing negative), so a
    diverging colormap centered on zero is used.  The surface is the TI central
    surface (or a windowed patch of it); pass :func:`window_patch` output for a
    focal montage so the render stays fast and legible.

    Parameters
    ----------
    coords_mm : ndarray (N, 3)
    tris : ndarray (F, 3)
    delta_vm : ndarray (N,)
        Per-vertex somatic ΔVm in mV.
    vlim : tuple, optional
        Symmetric color limits; defaults to ``(-m, m)`` with
        ``m = 98th percentile of |ΔVm|``.
    """
    import matplotlib.pyplot as plt

    if ax is None:
        fig = plt.figure(figsize=(6.5, 6))
        ax = fig.add_subplot(111, projection="3d")

    sp = np.asarray(coords_mm, dtype=float).reshape(-1, 3)
    tris = np.asarray(tris, dtype=int).reshape(-1, 3)
    dvm = np.asarray(delta_vm, dtype=float).reshape(-1)
    if vlim is None:
        finite = np.abs(dvm[np.isfinite(dvm)])
        m = (float(np.percentile(finite, 98)) if finite.size else 0.0) or 1e-6
        vlim = (-m, m)

    tri = ax.plot_trisurf(
        sp[:, 0],
        sp[:, 1],
        sp[:, 2],
        triangles=tris,
        linewidth=0.0,
        antialiased=True,
        shade=False,
    )
    tri.set_array(dvm[tris].mean(axis=1))
    tri.set_cmap("coolwarm")
    tri.set_clim(*vlim)
    cb = ax.figure.colorbar(tri, ax=ax, shrink=0.55, pad=0.02, fraction=0.04)
    cb.set_label(clabel, fontsize=9)
    cb.ax.tick_params(labelsize=8)
    _equal_3d(ax, sp, pad=0.02)
    ax.set_axis_off()
    ax.set_title(title)
    return ax


def plot_polarization_histogram(
    delta_vm_cluster,
    ax=None,
    neuron_delta_vm=None,
    title: str = "ΔVm distribution across the cluster",
):
    """Histogram of analytic somatic ΔVm over the cluster vertices.

    Overlays the NEURON-subsample ΔVm (if given) so the morphology/orientation
    spread around the analytic central estimate is visible.

    Parameters
    ----------
    delta_vm_cluster : ndarray (N,)
        Analytic ΔVm at every cluster vertex (mV).
    neuron_delta_vm : ndarray, optional
        Flattened NEURON-subsample ΔVm values (mV) to overlay.
    """
    import matplotlib.pyplot as plt

    if ax is None:
        _fig, ax = plt.subplots(figsize=(5.5, 4.5))

    dvm = np.asarray(delta_vm_cluster, dtype=float).reshape(-1)
    dvm = dvm[np.isfinite(dvm)]
    ax.hist(dvm, bins=40, color="#4c72b0", alpha=0.8, label="analytic (all vertices)")
    if dvm.size:
        ax.axvline(float(np.mean(dvm)), color="#c44e52", lw=1.5, label="mean")
        ax.axvline(0.0, color="#555555", lw=0.8, ls="--")
    if neuron_delta_vm is not None:
        nv = np.asarray(neuron_delta_vm, dtype=float).reshape(-1)
        nv = nv[np.isfinite(nv)]
        if nv.size:
            ax.hist(
                nv,
                bins=20,
                color="#dd8452",
                alpha=0.6,
                density=True,
                histtype="step",
                lw=1.6,
                label="NEURON subsample",
            )
    ax.set(xlabel="somatic ΔVm (mV)", ylabel="vertices", title=title)
    ax.legend(fontsize=8, frameon=False)
    return ax


def render_polarization_summary(subject_id, cfg, result, out_dir, span_mm=18.0):
    """Write the default two-panel polarization figure for a population run.

    Left: the cortical patch around the field focus colored by somatic ΔVm.
    Right: the ΔVm histogram across the whole cluster, annotated with the
    subthreshold margin (peak delivered field vs the Wang et al. 2022 firing
    threshold).

    Returns
    -------
    str
        Path to ``<stem>_polarization.png``.
    """
    import os

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from tit.microscale.config import LFS_THRESHOLD_VM
    from tit.microscale.metrics import region_summary
    from tit.microscale.population import load_cluster_triangles

    coords = np.asarray(result["vertices_mm"], dtype=float).reshape(-1, 3)
    analytic = np.asarray(result["analytic_delta_vm"], dtype=float).reshape(-1)
    cluster_idx = np.asarray(result["cluster_idx"], dtype=int).reshape(-1)
    e_normal = np.asarray(result["ti_normal"], dtype=float).reshape(-1)

    try:
        tris = load_cluster_triangles(subject_id, cfg)
    except Exception:  # noqa: BLE001 - histogram still works without triangles
        tris = np.empty((0, 3), dtype=int)

    focus = coords[int(np.argmax(np.abs(e_normal)))]
    patch_coords, patch_tris, patch_dvm = window_patch(
        coords, tris, analytic, focus, span_mm
    )

    # Wide layout with a generous gap so the 3D map and the histogram do not
    # crowd each other (the 3D axis carries a colorbar on its right).
    fig = plt.figure(figsize=(15, 6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.15, 1.0], wspace=0.32)
    axm = fig.add_subplot(gs[0, 0], projection="3d")
    plot_polarization_map(
        patch_coords,
        patch_tris,
        patch_dvm,
        ax=axm,
        title=f"Somatic ΔVm around the field focus\nsub-{subject_id} • {cfg.sim_name}",
    )
    axh = fig.add_subplot(gs[0, 1])
    cluster_dvm = analytic[cluster_idx] if cluster_idx.size else analytic
    plot_polarization_histogram(
        cluster_dvm, ax=axh, neuron_delta_vm=result.get("neuron_delta_vm")
    )

    summ = region_summary(result)
    peak_e = summ["e_normal_peak_abs_Vm"]
    margin = summ["subthreshold_margin_x"]
    note = (
        f"peak |E_normal| = {peak_e:.3g} V/m\n"
        f"firing threshold (Wang 2022) ≈ {LFS_THRESHOLD_VM[0]:g}-"
        f"{LFS_THRESHOLD_VM[1]:g} V/m\n"
        f"≈ {margin:.0f}× below threshold → subthreshold polarization"
    )
    axh.text(
        0.02,
        0.98,
        note,
        transform=axh.transAxes,
        fontsize=8,
        va="top",
        ha="left",
        bbox=dict(boxstyle="round", fc="white", ec="#999999", alpha=0.85),
    )

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(
        out_dir, f"sub-{subject_id}_sim-{cfg.sim_name}_polarization.png"
    )
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Single-cell morphology (quasipotential along the cell)
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
    If *values* (a per-segment array, e.g. the applied quasipotential Ψ) is
    given, every compartment is instead colored by that value on *cmap* -- the
    field-induced dipole along the morphology (Shirinpour et al. 2021, Fig. 2F).
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
        ax.figure.colorbar(sm, ax=ax, shrink=0.55, pad=0.08, label="Ψ (mV)")
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


# ---------------------------------------------------------------------------
# Populated cortex (optional "populated gyrus" publication figure)
# ---------------------------------------------------------------------------


def plot_population_3d(
    placed_cells,
    surf_coords_mm,
    surf_tris,
    surf_scalar=None,
    color_scheme: str = "aberra",
    ax=None,
    title: str = "Populated cortex",
    region_label: str | None = None,
    scale_bar_mm: float = 1.0,
    lw: float = 0.6,
):
    """Render a populated cortical patch in 3D (clean, anatomical, no overlap).

    The cortical patch is drawn as a smooth lit surface colored by ``TI_normal``;
    the L5 neurons are drawn as 3D poly-lines colored by neurite type and
    embedded on the sheet, oriented to the local cortical normal.  3D avoids the
    self-overlap a 2D projection of a folded gyrus suffers.
    """
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Line3DCollection

    if ax is None:
        fig = plt.figure(figsize=(9, 7.5))
        ax = fig.add_subplot(111, projection="3d")

    sp = np.asarray(surf_coords_mm, dtype=float)
    tris = np.asarray(surf_tris, dtype=int)
    tri = ax.plot_trisurf(
        sp[:, 0],
        sp[:, 1],
        sp[:, 2],
        triangles=tris,
        linewidth=0.0,
        antialiased=True,
        alpha=0.6,
        shade=True,
    )
    if surf_scalar is not None:
        tri.set_array(np.asarray(surf_scalar)[tris].mean(axis=1))
        tri.set_cmap("magma")
        cb = ax.figure.colorbar(tri, ax=ax, shrink=0.5, pad=0.02, fraction=0.035)
        cb.set_label("TI_normal (V/m)", fontsize=8)
        cb.ax.tick_params(labelsize=7)
    else:
        tri.set_color("#cfc7b8")

    # Neurons: one Line3DCollection per neurite type (fast, clean).
    by_color: dict = {}
    soma_pts = []
    for cell in placed_cells:
        for kind, pts in cell:
            pts = np.asarray(pts, dtype=float)
            if kind == "soma":
                soma_pts.append(pts.mean(0))
                continue
            segs = np.stack([pts[:-1], pts[1:]], axis=1)
            by_color.setdefault(_kind_color(kind, color_scheme), []).append(segs)
    for color, seglist in by_color.items():
        lc = Line3DCollection(np.concatenate(seglist), colors=color, linewidths=lw)
        ax.add_collection3d(lc)
    if soma_pts:
        soma_pts = np.array(soma_pts)
        ax.scatter(
            soma_pts[:, 0],
            soma_pts[:, 1],
            soma_pts[:, 2],
            s=5,
            color="#111111",
            depthshade=False,
        )

    allpts = np.vstack([c[1] for cell in placed_cells for c in cell] + [sp])
    _equal_3d(ax, allpts, pad=0.02)
    ax.set_axis_off()
    lo = allpts.min(0)
    span = (allpts.max(0) - allpts.min(0)).max()
    ax.plot(
        [lo[0], lo[0] + scale_bar_mm], [lo[1], lo[1]], [lo[2], lo[2]], color="k", lw=3
    )
    ax.text(
        lo[0] + scale_bar_mm / 2,
        lo[1],
        lo[2] - 0.03 * span,
        f"{scale_bar_mm * 1000:g} µm",
        fontsize=8,
        ha="center",
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
        ax.text2D(
            0.02,
            0.98,
            region_label,
            transform=ax.transAxes,
            fontsize=9,
            va="top",
            ha="left",
            bbox=dict(boxstyle="round", fc="white", ec="#999999", alpha=0.85),
        )
    ax.set_title(title)
    return ax


def render_population_region(
    subject_id,
    cfg,
    out_dir,
    spec,
    name: str,
    n_cells: int = 40,
    span_mm: float = 14.0,
    color_scheme: str = "aberra",
    dpi: int = 220,
):
    """Populate a GM cortical region with L5 pyramidal neurons and render it.

    *spec* is a :class:`~tit.microscale.config.RegionSpec` (atlas / sphere /
    mask, subject or fsaverage).  The selected region is windowed to a clean
    patch around the field focus, drawn as a lit cortical sheet (colored by
    ``TI_normal``) with the neurons placed on it, oriented to the local cortical
    normal and colored by neurite type.

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
    from tit.microscale.population import place_spec_world, select_region

    reg = select_region(subject_id, cfg, spec)
    coords, normals, scalar, tris = (
        reg["coords_mm"],
        reg["normals"],
        reg["scalar"],
        reg["tris"],
    )

    morph = pyramidal_l5(seed=cfg.seed)  # L5 pyramidal only
    rng = np.random.default_rng(cfg.seed)

    focus = coords[int(np.argmax(scalar))]
    patch_coords, patch_tris, patch_scalar = window_patch(
        coords, tris, scalar, focus, span_mm
    )
    near = np.linalg.norm(coords - focus, axis=1) <= span_mm
    used = np.where(near)[0] if near.any() else np.arange(len(coords))

    site_local = (
        rng.choice(len(used), n_cells, replace=False)
        if len(used) > n_cells
        else np.arange(len(used))
    )
    placed = [
        place_spec_world(morph, coords[used[i]], normals[used[i]]) for i in site_local
    ]

    ax = plot_population_3d(
        placed,
        surf_coords_mm=patch_coords,
        surf_tris=patch_tris,
        surf_scalar=patch_scalar,
        color_scheme=color_scheme,
        scale_bar_mm=1.0,
        region_label=f"sub-{subject_id} • {spec.space} space\n{reg['label']}\n"
        f"{len(placed)} L5 pyramidal cells",
        title=f"Populated {name}",
    )
    stem = f"sub-{subject_id}_sim-{cfg.sim_name}"
    path = os.path.join(out_dir, f"{stem}_population_{name}.png")
    ax.figure.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(ax.figure)
    return path


def render_population_figure(
    subject_id,
    cfg,
    result,
    out_dir,
    per_vertex: bool = True,
    max_cells: int = 2500,
    span_mm: float = 10.0,
    n_cells: int = 32,
    dpi=220,
):
    """Standalone populated-cortex figure from an in-memory population result.

    Places **one L5 pyramidal neuron per vertex of the analyzed ROI** (the dense,
    Aberra-style populated cortex), oriented to the local cortical normal and
    embedded in the cortical sheet (colored by ``TI_normal``).  The ROI is:

    * the **analyzed cluster** when ``cfg.cluster_threshold`` scoped it (one cell
      per cluster vertex), or
    * a **window around the field focus** (``span_mm``) when the whole surface was
      analyzed -- the full surface (hundreds of thousands of vertices) is too
      large to fill, so the figure shows the focal region.

    ``per_vertex=True`` (default) places one cell per ROI vertex, subsampled down
    to ``max_cells`` if the ROI is larger (logged).  ``per_vertex=False`` falls
    back to a random ``n_cells`` sample.  Emitted automatically by
    :func:`tit.microscale.population.run_population` when ``cfg.render_population``.

    Returns
    -------
    str
        Path to ``<stem>_population.png``.
    """
    import os

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from tit.microscale.morphology import pyramidal_l5
    from tit.microscale.population import load_cluster_triangles, place_spec_world

    coords = np.asarray(result["vertices_mm"], dtype=float).reshape(-1, 3)
    normals = np.asarray(result["normals"], dtype=float).reshape(-1, 3)
    scalar = np.asarray(result["ti_normal"], dtype=float).reshape(-1)
    cluster_idx = np.asarray(result["cluster_idx"], dtype=int).reshape(-1)
    try:
        tris = load_cluster_triangles(subject_id, cfg)
    except Exception:  # noqa: BLE001 - render floating cells if triangles absent
        tris = np.empty((0, 3), dtype=int)

    # Define the ROI to populate.  A real (thresholded) cluster IS the ROI; an
    # unthresholded whole-surface run falls back to a focal window.
    scoped = getattr(
        cfg, "cluster_threshold", None
    ) is not None and 0 < cluster_idx.size < len(coords)
    if scoped:
        roi = cluster_idx
        center = coords[roi].mean(0)
        d = np.linalg.norm(coords[roi] - center, axis=1)
        radius = float(min(np.percentile(d, 95) + 3.0, 30.0))
        roi_label = f"cluster (TI_normal ≥ {cfg.cluster_threshold:g})"
    else:
        center = coords[int(np.argmax(np.abs(scalar)))]
        radius = span_mm
        roi = np.where(np.linalg.norm(coords - center, axis=1) <= radius)[0]
        roi_label = "field focus"

    patch_coords, patch_tris, patch_scalar = window_patch(
        coords, tris, scalar, center, radius
    )

    if per_vertex:
        site = roi
        if site.size > max_cells:
            pick = np.linspace(0, site.size - 1, max_cells).round().astype(int)
            site = site[pick]
            print(
                f"  (population figure: {roi.size} ROI vertices capped to "
                f"{max_cells} cells)",
                flush=True,
            )
        mode = "one per vertex"
    else:
        rng = np.random.default_rng(cfg.seed)
        site = roi if roi.size <= n_cells else rng.choice(roi, n_cells, replace=False)
        mode = "sampled"

    morph = pyramidal_l5(seed=cfg.seed)
    placed = [place_spec_world(morph, coords[i], normals[i]) for i in site]
    n = len(placed)
    # Thin the neurites as the population gets denser so the forest stays legible.
    lw = float(np.clip(30.0 / np.sqrt(max(n, 1)), 0.25, 1.4))

    ax = plot_population_3d(
        placed,
        surf_coords_mm=patch_coords,
        surf_tris=patch_tris,
        surf_scalar=patch_scalar,
        scale_bar_mm=1.0,
        lw=lw,
        region_label=f"sub-{subject_id} • {cfg.sim_name}\n{roi_label}\n"
        f"{n} L5 pyramidal cells ({mode})",
        title="Meso-scale population (L5 pyramidal)",
    )
    stem = f"sub-{subject_id}_sim-{cfg.sim_name}"
    path = os.path.join(out_dir, f"{stem}_population.png")
    ax.figure.savefig(path, dpi=dpi, bbox_inches="tight")
    plt.close(ax.figure)
    return path


def animate_polarization(
    placed_world_mm,
    e1_vec,
    e2_vec,
    out_path,
    viz_carriers=(50.0, 60.0),
    real_carriers=(2000.0, 2010.0),
    n_frames: int = 120,
    fps: int = 20,
    n_beats: float = 1.5,
):
    """Time-domain animation of the field-induced polarization (NEURON-free).

    Shows three things over time, as the user-facing "what the TI field does to a
    neuron" clip:

    * the morphology colored by the **instantaneous applied quasipotential**
      ``Ψ(c, t) = ve1(c)·sin(2π f1 t) + ve2(c)·sin(2π f2 t)`` with
      ``ve = −E·(x − x_soma)`` -- the field-induced dipole that polarizes the cell
      (depolarizing one pole, hyperpolarizing the other), flipping with the field;
    * the **rotating instantaneous E-field vector** through the soma (the TI
      resultant rotates over the beat -- only visible from the two HF fields);
    * a **trace of the oscillation** at the most-polarized compartment with its
      beat **envelope**, so the carrier oscillation *and* the slow modulation are
      both legible.

    The carrier frequency is slowed to *viz_carriers* purely for visibility (the
    real carriers in *real_carriers* are annotated; the same |Δf| beat and the
    real field magnitudes are kept), so the kHz cycles do not alias to nothing.

    Parameters
    ----------
    placed_world_mm : list of (kind, points_mm)
        Placed morphology from :func:`tit.microscale.population.place_spec_world`.
    e1_vec, e2_vec : ndarray (3,)
        Pair-1 and pair-2 E-field vectors (V/m) at the soma.
    out_path : str
        Output ``.gif``.

    Returns
    -------
    str
        *out_path*.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import animation
    from mpl_toolkits.mplot3d.art3d import Line3DCollection

    sections = [
        (kind, np.asarray(pts, dtype=float).reshape(-1, 3))
        for kind, pts in placed_world_mm
    ]
    allpts = np.vstack([p for _, p in sections])
    soma_mm = next((p.mean(0) for k, p in sections if k == "soma"), allpts.mean(0))
    e1 = np.asarray(e1_vec, dtype=float).reshape(3)
    e2 = np.asarray(e2_vec, dtype=float).reshape(3)

    # Per-segment quasipotentials (mV): ve = -E·(x - x_soma); 1 V/m == 1 mV/mm.
    seg_xyz, seg_ve1, seg_ve2 = [], [], []
    for _kind, pts in sections:
        v1 = -((pts - soma_mm) @ e1)
        v2 = -((pts - soma_mm) @ e2)
        for k in range(len(pts) - 1):
            seg_xyz.append([pts[k], pts[k + 1]])
            seg_ve1.append(0.5 * (v1[k] + v1[k + 1]))
            seg_ve2.append(0.5 * (v2[k] + v2[k + 1]))
    seg_xyz = np.asarray(seg_xyz)
    seg_ve1 = np.asarray(seg_ve1)
    seg_ve2 = np.asarray(seg_ve2)

    f1v, f2v = viz_carriers
    df = abs(f1v - f2v) or 1.0
    # Offset the start by a quarter carrier period so frame 0 already shows the
    # polarization dipole (at t=0 both carriers cross zero and the cell is blank).
    t0 = 0.25 * 1000.0 / max(f1v, f2v)
    t_ms = t0 + np.linspace(0.0, n_beats * 1000.0 / df, n_frames)
    e_inst = instantaneous_field(e1, e2, f1v, f2v, t_ms)
    e_mag = np.linalg.norm(e_inst, axis=1)
    e_mag_max = float(e_mag.max()) + 1e-12

    # Representative (most-polarized) compartment for the oscillation trace.
    rep = int(np.argmax(np.abs(seg_ve1) + np.abs(seg_ve2)))
    rv1, rv2 = float(seg_ve1[rep]), float(seg_ve2[rep])
    s1 = np.sin(2.0 * np.pi * f1v * t_ms / 1000.0)
    s2 = np.sin(2.0 * np.pi * f2v * t_ms / 1000.0)
    drive = rv1 * s1 + rv2 * s2
    env = np.sqrt(
        rv1**2 + rv2**2 + 2.0 * rv1 * rv2 * np.cos(2.0 * np.pi * df * t_ms / 1000.0)
    )

    span = (allpts.max(0) - allpts.min(0)).max()
    arrow_len = 0.5 * span
    vmax = float(np.percentile(np.abs(seg_ve1 + seg_ve2), 98)) or 1e-6

    fig = plt.figure(figsize=(14, 6))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.05], wspace=0.28)
    ax3d = fig.add_subplot(gs[0, 0], projection="3d")
    axtr = fig.add_subplot(gs[0, 1])
    cmap = plt.get_cmap("coolwarm")
    norm = plt.Normalize(-vmax, vmax)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    # Colorbar on the LEFT of the 3D panel so it does not collide with the trace.
    fig.colorbar(
        sm, ax=ax3d, shrink=0.6, pad=0.0, location="left", label="applied Ψ (mV)"
    )
    rf1, rf2 = real_carriers
    fig.suptitle(
        f"Field-induced polarization over time  (illustrative {f1v:g}/{f2v:g} Hz; "
        f"real carriers {rf1:g}/{rf2:g} Hz, beat {df:g} Hz)",
        fontsize=10,
    )

    def draw(fr):
        ax3d.cla()
        psi = seg_ve1 * s1[fr] + seg_ve2 * s2[fr]
        lc = Line3DCollection(seg_xyz, colors=cmap(norm(psi)), linewidths=2.2)
        ax3d.add_collection3d(lc)
        d = (e_inst[fr] / e_mag_max) * arrow_len
        ax3d.quiver(
            soma_mm[0] - d[0],
            soma_mm[1] - d[1],
            soma_mm[2] - d[2],
            2 * d[0],
            2 * d[1],
            2 * d[2],
            color="#33a02c",
            lw=2.5,
            arrow_length_ratio=0.12,
        )
        _equal_3d(ax3d, allpts, pad=0.2)
        ax3d.set_axis_off()
        ax3d.set_title(f"t = {t_ms[fr]:.0f} ms   |E| = {e_mag[fr]:.3g} V/m")

        axtr.cla()
        axtr.plot(t_ms, env, color="#c44e52", lw=1.0, ls="--", label="beat envelope")
        axtr.plot(t_ms, -env, color="#c44e52", lw=1.0, ls="--")
        # Full oscillation faint for context; the elapsed part drawn bold.
        axtr.plot(t_ms, drive, color="#bbbbbb", lw=0.6)
        axtr.plot(
            t_ms[: fr + 1],
            drive[: fr + 1],
            color="#222222",
            lw=1.2,
            label="applied Ψ (apical)",
        )
        axtr.axvline(t_ms[fr], color="#888888", lw=0.8)
        axtr.set(
            xlim=(t_ms[0], t_ms[-1]),
            ylim=(-1.15 * env.max(), 1.15 * env.max()),
            xlabel="time (ms)",
            ylabel="applied Ψ at apical tuft (mV)",
        )
        axtr.legend(fontsize=8, loc="upper right", frameon=False)
        return []

    anim = animation.FuncAnimation(fig, draw, frames=n_frames, blit=False)
    anim.save(out_path, writer=animation.PillowWriter(fps=fps))
    plt.close(fig)
    return out_path
