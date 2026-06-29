#!/usr/bin/env simnibs_python
"""Render fsaverage surface field/stat maps on the inflated cortex.

The :class:`~tit.plotting.nilearn.visualizer.NilearnVisualizer` renders MNI
*volumes* (optionally projected onto a surface).  This module is the missing
counterpart: it paints a per-vertex fsaverage array -- a group-mean field, a
t/r map, or a thresholded significant-cluster mask -- directly on the
fsaverage inflated surface (lateral + medial, both hemispheres), the layout
used for cortical group figures.

Inputs are the ``(n_vertices,)`` arrays produced by
:func:`tit.source.project_fields_to_fsaverage` (per-subject field caches) and by
:mod:`tit.stats.surface` (group ``surface_maps.npz``).  The vertex order is
``[lh; rh]``, matching nilearn's left/right hemispheres.

See Also
--------
tit.plotting.nilearn.visualizer.NilearnVisualizer : Volume / volume-to-surface.
tit.stats.surface : Produces the surface stats ``.npz`` rendered here.
"""

from __future__ import annotations

import os

import numpy as np

from tit.plotting._common import ensure_headless_matplotlib_backend
from tit.source.fsaverage import _FSAVG_NODES

_VIEWS = ("lateral", "medial")
_HEMIS = ("left", "right")


def render_fsaverage_map(
    values,
    spacing: int = 5,
    *,
    title: str | None = None,
    threshold: float | None = None,
    cmap: str = "cold_hot",
    symmetric_cbar="auto",
    out_path: str | None = None,
):
    """Paint a ``(n_vertices,)`` fsaverage map on the inflated cortex.

    Parameters
    ----------
    values : array-like
        Per-vertex values in ``[lh; rh]`` order, length ``_FSAVG_NODES[spacing]``.
    spacing : int
        fsaverage subdivision factor (5, 6, or 7).
    title : str, optional
        Figure suptitle.
    threshold : float, optional
        Hide ``|value| < threshold`` (e.g. to show only significant vertices).
    cmap : str
        Matplotlib/nilearn colormap.  ``cold_hot`` suits signed t/r maps;
        use a sequential map (e.g. ``"inferno"``) for magnitude fields.
    symmetric_cbar : bool or "auto"
        Passed to nilearn; keep signed maps symmetric about zero.
    out_path : str, optional
        If given, save the figure there and return the path; else return the
        Matplotlib figure.

    Returns
    -------
    str or matplotlib.figure.Figure
        The saved path (when *out_path* is given) or the figure.
    """
    ensure_headless_matplotlib_backend()
    import matplotlib.pyplot as plt
    from nilearn import datasets, plotting

    n_total = _FSAVG_NODES[spacing]
    values = np.asarray(values, dtype=float).reshape(-1)
    if values.shape[0] != n_total:
        raise ValueError(
            f"expected {n_total} fsaverage{spacing} vertices, got {values.shape[0]}"
        )
    n_lh = n_total // 2

    fs = datasets.fetch_surf_fsaverage(f"fsaverage{spacing}")
    hemi_data = {
        "left": (values[:n_lh], fs["infl_left"], fs["sulc_left"]),
        "right": (values[n_lh:], fs["infl_right"], fs["sulc_right"]),
    }

    fig, axes = plt.subplots(2, 2, figsize=(11, 9), subplot_kw={"projection": "3d"})
    for col, hemi in enumerate(_HEMIS):
        stat_map, mesh, bg_map = hemi_data[hemi]
        for row, view in enumerate(_VIEWS):
            plotting.plot_surf_stat_map(
                mesh,
                stat_map,
                bg_map=bg_map,
                hemi=hemi,
                view=view,
                threshold=threshold,
                cmap=cmap,
                colorbar=(row == 0 and col == 1),
                symmetric_cbar=symmetric_cbar,
                axes=axes[row, col],
                figure=fig,
            )
            axes[row, col].set_title(f"{hemi} {view}")

    if title:
        fig.suptitle(title)
    if out_path is None:
        return fig
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


def render_surface_stats_result(npz_path: str, out_dir: str, spacing: int = 5):
    """Render a :mod:`tit.stats.surface` ``surface_maps.npz`` to PDFs.

    Paints the effect map (signed ``r`` if present, else ``t``) and the
    thresholded significant-cluster mask onto the inflated cortex.

    Returns
    -------
    list of str
        Paths of the figures written into *out_dir*.
    """
    os.makedirs(out_dir, exist_ok=True)
    written: list[str] = []
    with np.load(npz_path) as data:
        effect_key = "r" if "r" in data.files else "t"
        effect = np.asarray(data[effect_key], dtype=float)
        sig_mask = (
            np.asarray(data["sig_mask"], dtype=float)
            if "sig_mask" in data.files
            else None
        )

    effect_pdf = os.path.join(out_dir, f"surface_{effect_key}_map.pdf")
    render_fsaverage_map(
        effect, spacing, title=f"{effect_key} map", out_path=effect_pdf
    )
    written.append(effect_pdf)

    if sig_mask is not None and float(sig_mask.sum()) > 0:
        sig_pdf = os.path.join(out_dir, "surface_significant_clusters.pdf")
        render_fsaverage_map(
            effect * sig_mask,
            spacing,
            title="significant clusters",
            threshold=1e-9,
            out_path=sig_pdf,
        )
        written.append(sig_pdf)
    return written
