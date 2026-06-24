#!/usr/bin/env simnibs_python
"""Simulate a population of unconnected morphologically-realistic neurons.

This module is the public API for the *population* pipeline of
:mod:`tit.microscale`.  It simulates a CLUSTER of independent (no synaptic
connectivity) cortical neurons -- the standard approach for subthreshold
polarization and activation-threshold questions in TI/tDCS modelling
(Aberra et al. 2018, 2020; Seo & Jun 2017; Shirinpour et al. 2021).  The
population is the cross product of morphological *clones*, *azimuthal rotations*
about the cortical normal, and *cluster sites* on the central surface.

Quasi-uniform justification
---------------------------
Each neuron is small relative to the spatial scale over which the macroscopic
E-field varies, so it sees a locally near-uniform field.  Under the quasi-static,
quasi-uniform approximation the extracellular potential at compartment *s* is
``ψ = −E·s`` (the field, sampled at the soma, integrated over the morphology;
Wang et al. 2022).  Because each cell only sees the externally imposed field and
its own cable currents, the cells are **independent**: there is no connectivity
to solve, and the population reduces to an embarrassingly parallel sweep over
sites × clones × azimuths.

Two-tier estimate
------------------
1. **Central estimate (analytic, cheap, vectorized over all cluster vertices).**
   First-order somatic polarization is linear in the normal field,
   ``ΔVm = coupling · E_normal`` with ``coupling ≈ 0.27 mV/(V/m)`` for L5
   pyramidal somata (Radman et al. 2009; Bikson et al. 2004 measured 0.12 for a
   different cell/orientation).  Computed for *every* cluster vertex with no
   NEURON.
2. **Distribution (NEURON, a modest subsample).**  NEURON characterizes how
   morphology, dendritic vs somatic poles and orientation spread distribute the
   polarization around the analytic central value, on a small representative
   subsample of vertices.  It does **not** move the central estimate.

References
----------
Aberra, Wang, Grill & Peterchev (2018) *J. Neural Eng.* 15:066023.
Aberra, Peterchev & Grill (2020) *J. Neural Eng.* 17:046027.
Seo & Jun (2017) *Front. Comput. Neurosci.* 11:91.
Radman, Ramos, Brumberg & Bikson (2009) *Brain Stimul.* 2:215.
Bikson et al. (2004) *J. Physiol.* 557:175.
Shirinpour et al. (2021) *Brain Stimul.* 14:1470.
"""

from __future__ import annotations

import glob
import os

import numpy as np

# ---------------------------------------------------------------------------
# Pure math (NEURON-free, unit tested)
# ---------------------------------------------------------------------------


def analytic_polarization_map(
    e_normal_values: np.ndarray, coupling_mV_per_Vm: float
) -> np.ndarray:
    """First-order somatic polarization per vertex (the central estimate).

    ``ΔVm = coupling · E_normal`` -- linear in the normal field component
    (Radman et al. 2009; Bikson et al. 2004).

    Parameters
    ----------
    e_normal_values : ndarray, shape (N,)
        Normal-component field per vertex in V/m.
    coupling_mV_per_Vm : float
        Somatic polarization coupling in mV per (V/m).

    Returns
    -------
    ndarray, shape (N,)
        Somatic ΔVm per vertex in mV.
    """
    e = np.asarray(e_normal_values, dtype=float).reshape(-1)
    return coupling_mV_per_Vm * e


def select_cluster(
    field_values: np.ndarray,
    threshold: float | None,
    n_subsample: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Select the cluster and a NEURON subsample from a per-vertex field.

    Parameters
    ----------
    field_values : ndarray, shape (N,)
        Per-vertex field magnitude (e.g. ``TI_normal``).
    threshold : float or None
        Keep vertices with ``field_values >= threshold``.  ``None`` keeps all.
    n_subsample : int
        Number of cluster vertices to draw for NEURON.  ``0`` returns an empty
        subsample; values larger than the cluster size are capped.
    rng : numpy.random.Generator
        Source of randomness (pass a seeded generator for determinism).

    Returns
    -------
    tuple of ndarray
        ``(cluster_idx, subsample_idx)`` -- indices into *field_values*.
        ``subsample_idx`` is a sorted subset of ``cluster_idx``.
    """
    values = np.asarray(field_values, dtype=float).reshape(-1)
    if threshold is None:
        cluster_idx = np.arange(values.size, dtype=int)
    else:
        cluster_idx = np.flatnonzero(values >= threshold).astype(int)

    k = min(int(n_subsample), cluster_idx.size)
    if k <= 0:
        return cluster_idx, np.empty(0, dtype=int)
    chosen = rng.choice(cluster_idx, size=k, replace=False)
    return cluster_idx, np.sort(chosen)


def azimuths(n: int) -> list[float]:
    """Return *n* evenly spaced azimuth angles in degrees over ``[0, 360)``.

    Parameters
    ----------
    n : int
        Number of angles (>= 1).

    Returns
    -------
    list of float
        ``[0, 360/n, 2*360/n, ...]``.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    return [360.0 * i / n for i in range(n)]


# ---------------------------------------------------------------------------
# Surface loading (lazy simnibs)
# ---------------------------------------------------------------------------


def load_cluster_surface(subject_id: str, cfg):
    """Load the TI central surface coordinates, normals, and normal field.

    Globs ``<ti_mesh_dir>/surfaces/*_TI_central.msh`` for per-node coordinates
    and node normals, and the parent ``<ti_mesh_dir>/*_normal.msh`` for the
    ``cfg.cluster_normal_field`` node field.  The sim folder name (e.g.
    ``"L_Insula_scalar"``) need not match the mesh stem (e.g. ``"L_Insula"``),
    so both are resolved by glob.

    If no ``*_normal.msh`` is found, falls back to reading
    ``cfg.cluster_normal_field`` directly from the central surface.

    Parameters
    ----------
    subject_id : str
        Subject identifier.
    cfg : PopulationConfig
        Population configuration (provides ``sim_name`` and
        ``cluster_normal_field``).

    Returns
    -------
    tuple of ndarray
        ``(coords_mm, normals, ti_normal)`` -- shapes ``(N, 3)``, ``(N, 3)``,
        ``(N,)`` respectively, one row per surface node.

    Raises
    ------
    FileNotFoundError
        If the central surface cannot be located.
    KeyError
        If the normal field cannot be resolved from any source.
    """
    from simnibs.mesh_tools import mesh_io

    from tit.paths import get_path_manager

    pm = get_path_manager()
    mesh_dir = pm.ti_mesh_dir(subject_id, cfg.sim_name)
    surf_glob = os.path.join(mesh_dir, "surfaces", "*_TI_central.msh")
    matches = sorted(glob.glob(surf_glob))
    if not matches:
        raise FileNotFoundError(f"No central surface matched {surf_glob!r}")
    central_path = matches[0]
    central = mesh_io.read_msh(central_path)

    coords_mm = np.asarray(central.nodes.node_coord, dtype=float).reshape(-1, 3)
    normals = np.asarray(central.nodes_normals().value, dtype=float).reshape(-1, 3)

    field = cfg.cluster_normal_field
    ti_normal = None
    normal_glob = os.path.join(mesh_dir, "*_normal.msh")
    normal_matches = sorted(glob.glob(normal_glob))
    if normal_matches:
        nmesh = mesh_io.read_msh(normal_matches[0])
        if field in nmesh.field:
            ti_normal = np.asarray(nmesh.field[field].value, dtype=float).reshape(-1)
        elif len(nmesh.field) == 1:
            # A dedicated *_normal.msh typically carries the single scalar field.
            only = next(iter(nmesh.field.values()))
            ti_normal = np.asarray(only.value, dtype=float).reshape(-1)
    if ti_normal is None and field in central.field:
        ti_normal = np.asarray(central.field[field].value, dtype=float).reshape(-1)
    if ti_normal is None:
        raise KeyError(
            f"Could not resolve normal field {field!r} from {normal_glob!r} "
            f"or from {central_path!r} (fields: {list(central.field.keys())})"
        )

    # Align lengths defensively (node fields and node coords must match).
    n = min(len(coords_mm), len(normals), len(ti_normal))
    return coords_mm[:n], normals[:n], ti_normal[:n]


def load_cluster_triangles(subject_id: str, cfg):
    """Load the triangle connectivity of the TI central surface.

    Returns the ``(F, 3)`` 0-based vertex indices of the cortical surface used
    by :func:`load_cluster_surface`, so a population render can embed the cells
    in the actual cortical sheet (not just floating points).

    Returns
    -------
    ndarray (F, 3)
    """
    from simnibs.mesh_tools import mesh_io

    from tit.paths import get_path_manager

    pm = get_path_manager()
    surf_glob = os.path.join(
        pm.ti_mesh_dir(subject_id, cfg.sim_name), "surfaces", "*_TI_central.msh"
    )
    matches = sorted(glob.glob(surf_glob))
    if not matches:
        raise FileNotFoundError(f"No central surface matched {surf_glob!r}")
    m = mesh_io.read_msh(matches[0])
    tris = m.elm.node_number_list[m.elm.elm_type == 2][:, :3] - 1
    return np.asarray(tris, dtype=int)


# ---------------------------------------------------------------------------
# Orchestration (lazy NEURON / simnibs)
# ---------------------------------------------------------------------------


def _summary_stats(values: np.ndarray, prefix: str) -> dict:
    """Mean/std/percentile summary of a flat array under a key *prefix*."""
    v = np.asarray(values, dtype=float).reshape(-1)
    v = v[np.isfinite(v)]
    if v.size == 0:
        nan = float("nan")
        return {
            f"{prefix}_mean": nan,
            f"{prefix}_std": nan,
            f"{prefix}_p5": nan,
            f"{prefix}_p50": nan,
            f"{prefix}_p95": nan,
        }
    return {
        f"{prefix}_mean": float(np.mean(v)),
        f"{prefix}_std": float(np.std(v)),
        f"{prefix}_p5": float(np.percentile(v, 5)),
        f"{prefix}_p50": float(np.percentile(v, 50)),
        f"{prefix}_p95": float(np.percentile(v, 95)),
    }


def sample_cortical_strip(
    coords_mm, normals, n_cells, axis=1, thickness_mm=2.0, rng=None
):
    """Select cortical vertices forming a thin gyral cross-section ("slab").

    Keeps vertices within ``±thickness_mm/2`` of the cluster centroid along
    *axis* (a coronal/sagittal slab), then evenly subsamples ``n_cells`` of them
    ordered along the in-plane sweep -- the set of placement sites for an
    Aberra-style "populated gyrus" render.

    Parameters
    ----------
    coords_mm : ndarray (N, 3)
    normals : ndarray (N, 3)
    n_cells : int
        Number of placement sites to return.
    axis : int
        Slab-normal axis (0=x, 1=y, 2=z).
    thickness_mm : float
        Slab thickness.
    rng : numpy Generator, optional

    Returns
    -------
    tuple
        ``(strip_coords (M,3), strip_normals (M,3))`` with ``M <= n_cells``.
    """
    coords = np.asarray(coords_mm, dtype=float).reshape(-1, 3)
    norms = np.asarray(normals, dtype=float).reshape(-1, 3)
    # Median (not mean) centers the slab robustly against outlier vertices.
    c0 = float(np.median(coords[:, axis]))
    in_slab = np.where(np.abs(coords[:, axis] - c0) <= thickness_mm / 2.0)[0]
    if in_slab.size == 0:
        return coords[:0], norms[:0]
    # order along the longest in-plane spread for an anatomical left->right sweep
    plane_axes = [a for a in range(3) if a != axis]
    spread = np.ptp(coords[in_slab][:, plane_axes], axis=0)
    sweep_axis = plane_axes[int(np.argmax(spread))]
    order = in_slab[np.argsort(coords[in_slab, sweep_axis])]
    if order.size > n_cells:
        pick = np.linspace(0, order.size - 1, n_cells).round().astype(int)
        order = order[pick]
    return coords[order], norms[order]


def place_spec_world(spec, target_mm, normal, azimuth_deg=0.0):
    """Place a :class:`~tit.microscale.morphology.MorphologySpec` at a site.

    Orients the spec's apical axis along *normal* (with optional azimuth about
    it) and translates the soma to *target_mm*.  Pure geometry (no NEURON) --
    used for population rendering.

    Returns
    -------
    list of (kind, points_mm)
        One entry per section: its region tag and placed polyline in mm.
    """
    from tit.microscale.field_sampler import place_morphology

    target_mm = np.asarray(target_mm, dtype=float).reshape(3)
    all_pts = []
    slices = []
    i = 0
    for s in spec.sections:
        pts = np.asarray(s.points, dtype=float)[:, :3]
        slices.append((s.kind, i, len(pts)))
        all_pts.append(pts)
        i += len(pts)
    local_um = np.vstack(all_pts)
    soma = spec.by_name(spec.soma_name)
    soma_local_um = np.asarray(soma.points, dtype=float)[:, :3].mean(0)
    world_um = place_morphology(
        local_um, soma_local_um, target_mm * 1000.0, normal, azimuth_deg=azimuth_deg
    )
    world_mm = world_um / 1000.0
    return [(kind, world_mm[s : s + n]) for kind, s, n in slices]


def _gm_surface(subject_id: str, cfg, space: str):
    """Load the GM cortical surface (coords, normals, TI_normal, tris) for a space.

    ``space="subject"`` uses the simulation's TI central surface.  ``"fsaverage"``
    is reserved for a later iteration.
    """
    if space == "subject":
        coords, normals, scalar = load_cluster_surface(subject_id, cfg)
        tris = load_cluster_triangles(subject_id, cfg)
        return coords, normals, scalar, tris
    raise NotImplementedError(
        f"space={space!r} not yet supported (subject only for now)"
    )


def _center_subject_mm(subject_id, spec):
    """Resolve a sphere center to subject-space mm (MNI mapped if needed)."""
    if spec.center_subject is not None:
        return np.asarray(spec.center_subject, dtype=float).reshape(3)
    from simnibs import mni2subject_coords

    from tit.paths import get_path_manager

    m2m = get_path_manager().m2m(subject_id)
    c = mni2subject_coords([list(spec.center_mni)], m2m)
    return np.asarray(c, dtype=float).reshape(3)


def _atlas_vertex_mask(subject_id, spec, coords_mm):
    """Boolean mask of surface vertices in an atlas label (nearest-neighbour).

    The atlas annotation lives on the m2m surface; the TI surface is remeshed, so
    labels are transferred by nearest neighbour within ``spec.snap_mm``.
    """
    import nibabel as nib
    from scipy.spatial import cKDTree

    from tit.paths import get_path_manager

    m2m = get_path_manager().m2m(subject_id)
    hemis = ("lh", "rh") if spec.hemi == "both" else (spec.hemi,)
    region_xyz = []
    for hemi in hemis:
        gii = nib.load(os.path.join(m2m, "surfaces", f"{hemi}.central.gii"))
        surf_xyz = np.asarray(gii.darrays[0].data, dtype=float)
        ann = sorted(
            glob.glob(os.path.join(m2m, "segmentation", f"{hemi}.*_{spec.atlas}.annot"))
        )
        if not ann:
            raise FileNotFoundError(f"No {spec.atlas} annot for {hemi} in {m2m}")
        lab, _ctab, names = nib.freesurfer.read_annot(ann[0])
        names = [n.decode() if isinstance(n, bytes) else n for n in names]
        want = spec.label.lower()
        # Exact match first; only fall back to substring if exact yields nothing
        # (and reject ambiguous substring matches like "temporal" -> 4 labels).
        idx = [i for i, n in enumerate(names) if n.lower() == want]
        if not idx:
            idx = [i for i, n in enumerate(names) if want in n.lower()]
            if len(idx) > 1:
                raise KeyError(
                    f"label {spec.label!r} is ambiguous in {spec.atlas} ({hemi}); "
                    f"matches {[names[i] for i in idx]} — use an exact label name"
                )
        if not idx:
            raise KeyError(
                f"label {spec.label!r} not in {spec.atlas} ({hemi}); "
                f"have e.g. {names[:8]}"
            )
        region_xyz.append(surf_xyz[np.isin(lab, idx)])
    region_xyz = np.vstack(region_xyz)
    d, _ = cKDTree(region_xyz).query(coords_mm)
    return d <= spec.snap_mm


def _mask_vertex_mask(spec, coords_mm):
    """Boolean mask of surface vertices inside a binary NIfTI mask (GM inclusion).

    The mask NIfTI must be in the **same subject space** (scanner/world mm) as
    the cortical surface; vertices are mapped to voxels via the mask's affine and
    included where the mask is nonzero.
    """
    import nibabel as nib

    img = nib.load(spec.mask_path)
    data = np.asarray(img.dataobj)
    inv = np.linalg.inv(img.affine)
    homog = np.c_[coords_mm, np.ones(len(coords_mm))]
    vox = (homog @ inv.T)[:, :3]
    ijk = np.rint(vox).astype(int)
    inb = np.all((ijk >= 0) & (ijk < np.array(data.shape[:3])), axis=1)
    out = np.zeros(len(coords_mm), dtype=bool)
    vi = ijk[inb]
    out[inb] = data[vi[:, 0], vi[:, 1], vi[:, 2]] > 0
    return out


def select_region(subject_id: str, cfg, spec) -> dict:
    """Select a GM cortical region to populate with L5 pyramidal neurons.

    The region is a subset of the gray-matter cortical surface, chosen by an
    atlas label, a sphere, or a binary mask (see
    :class:`~tit.microscale.config.RegionSpec`), in subject (or, later,
    fsaverage) space.

    Returns
    -------
    dict
        ``{"coords_mm", "normals", "scalar", "tris", "label"}`` -- the cropped
        surface (vertices, normals, ``TI_normal`` scalar, re-indexed triangles)
        and a human-readable label.
    """
    coords, normals, scalar, tris = _gm_surface(subject_id, cfg, spec.space)

    if spec.kind == "atlas":
        vmask = _atlas_vertex_mask(subject_id, spec, coords)
    elif spec.kind == "sphere":
        center = _center_subject_mm(subject_id, spec)
        vmask = np.linalg.norm(coords - center, axis=1) <= spec.radius_mm
    else:  # mask
        vmask = _mask_vertex_mask(spec, coords)

    if not vmask.any():
        raise ValueError(f"region {spec.label_text!r} selected 0 GM vertices")

    used = np.where(vmask)[0]
    remap = np.full(len(coords), -1, dtype=int)
    remap[used] = np.arange(len(used))
    keep_tri = vmask[tris].all(axis=1)
    return {
        "coords_mm": coords[used],
        "normals": normals[used],
        "scalar": scalar[used],
        "tris": remap[tris[keep_tri]],
        "label": spec.label_text,
    }


def run_population(subject_id: str, cfg) -> dict:
    """Run the population pipeline for one subject.

    Computes the analytic central polarization map over the whole cluster, then
    (when ``cfg.n_subsample > 0``) solves a NEURON polarization for each
    subsample vertex × clone × azimuth to characterize the distribution around
    that central estimate.

    Parameters
    ----------
    subject_id : str
        Subject identifier.
    cfg : PopulationConfig
        Population configuration.

    Returns
    -------
    dict
        ``{"cluster_idx", "vertices_mm", "normals", "ti_normal",
        "analytic_delta_vm", "subsample_idx", "neuron_delta_vm",
        "amplification", "summary"}``.  ``neuron_delta_vm`` and
        ``amplification`` have shape ``(n_sub, n_clones, n_azimuth)``;
        ``summary`` holds mean/std/percentiles of the somatic ΔVm and of the
        NEURON/analytic amplification factor.
    """
    from tit.microscale.coupling import _load_pair_meshes, per_pair_quasipotentials
    from tit.microscale.models import build_cell
    from tit.microscale.morphology import pyramidal_l5

    print(
        f"[sub-{subject_id}] population sim={cfg.sim_name} model={cfg.model}",
        flush=True,
    )

    coords_mm, normals, ti_normal = load_cluster_surface(subject_id, cfg)
    print(f"  loaded {len(coords_mm)} surface vertices", flush=True)

    # (1) Analytic central estimate over the whole surface.
    analytic_all = analytic_polarization_map(ti_normal, cfg.polarization_coupling)

    # (2) Cluster + subsample selection.
    rng = np.random.default_rng(cfg.seed)
    cluster_idx, subsample_idx = select_cluster(
        ti_normal, cfg.cluster_threshold, cfg.n_subsample, rng
    )
    print(
        f"  cluster={cluster_idx.size} vertices, "
        f"NEURON subsample={subsample_idx.size}",
        flush=True,
    )

    azs = azimuths(cfg.n_azimuth)
    n_sub = subsample_idx.size
    neuron_dvm = np.full((n_sub, cfg.n_clones, cfg.n_azimuth), np.nan, dtype=float)
    amplification = np.full_like(neuron_dvm, np.nan)

    if n_sub > 0:
        from neuron import h

        m1, m2 = _load_pair_meshes(subject_id, cfg)
        h.celsius = cfg.temperature

        for si, vidx in enumerate(subsample_idx):
            target_mm = coords_mm[vidx]
            normal = normals[vidx]
            analytic_v = float(analytic_all[vidx])
            print(
                f"  [{si + 1}/{n_sub}] vertex {vidx} "
                f"(analytic ΔVm={analytic_v:.4g} mV)",
                flush=True,
            )
            for ci in range(cfg.n_clones):
                cell = build_cell(cfg.model)
                # The model's clones come from the seed; rebuild from the spec
                # with a clone-specific seed when the model supports it.
                if cfg.model == "l5_pyramidal":
                    from tit.microscale.models import build_from_spec

                    cell = build_from_spec(pyramidal_l5(seed=cfg.seed + ci), cfg.model)
                soma_idx = next(
                    i
                    for i, (sec, _seg) in enumerate(cell.segments())
                    if sec is cell.soma
                )
                for ai, az in enumerate(azs):
                    dvm = _static_soma_polarization(
                        h, cell, soma_idx, target_mm, normal, m1, m2, az
                    )
                    neuron_dvm[si, ci, ai] = dvm
                    if analytic_v != 0.0:
                        amplification[si, ci, ai] = dvm / analytic_v

    summary = {}
    summary.update(_summary_stats(neuron_dvm, "neuron_delta_vm"))
    summary.update(_summary_stats(amplification, "amplification"))
    summary.update(_summary_stats(analytic_all[cluster_idx], "analytic_delta_vm"))

    result = {
        "cluster_idx": cluster_idx,
        "vertices_mm": coords_mm,
        "normals": normals,
        "ti_normal": ti_normal,
        "analytic_delta_vm": analytic_all,
        "subsample_idx": subsample_idx,
        "neuron_delta_vm": neuron_dvm,
        "amplification": amplification,
        "summary": summary,
    }

    from tit.microscale.metrics import (
        write_population_npz,
        write_population_summary_csv,
    )
    from tit.paths import get_path_manager

    pm = get_path_manager()
    out_dir = pm.microscale_sim(subject_id, cfg.sim_name)
    stem = f"sub-{subject_id}_sim-{cfg.sim_name}"
    npz_path = os.path.join(out_dir, f"{stem}_population.npz")
    csv_path = os.path.join(out_dir, f"{stem}_population_summary.csv")
    write_population_npz(npz_path, result)
    write_population_summary_csv(csv_path, result)
    print(f"  ✓ wrote {npz_path}", flush=True)
    print(f"  ✓ wrote {csv_path}", flush=True)

    # Aberra-style populated-gyrus figure (pure geometry; cheap).
    try:
        from tit.microscale.viz import render_population_cortex

        fig_path = render_population_cortex(subject_id, cfg, out_dir)
        print(f"  ✓ wrote {fig_path}", flush=True)
        result["population_cortex_png"] = fig_path
    except Exception as exc:  # noqa: BLE001 - figure is optional, don't fail the run
        print(f"  (skipped populated-cortex figure: {exc})", flush=True)

    print("  ✓ population complete", flush=True)
    return result


def _static_soma_polarization(
    h, cell, soma_idx, target_mm, normal, mesh_pair1, mesh_pair2, azimuth_deg
):
    """Steady-state somatic ΔVm (mV) under the static superposed pair fields.

    Mirrors :func:`tit.microscale.coupling.polarization_map` but with an
    *azimuth* applied to the placement and returning only the somatic value.
    """
    from tit.microscale.field_sampler import (
        place_morphology,
        sample_at,
        uniform_quasipotential,
    )

    segs = list(cell.segments())
    target_mm = np.asarray(target_mm, dtype=float).reshape(3)
    local_um = cell.segment_coords_um()
    soma_local_um = cell.soma_coord_um()
    target_um = target_mm * 1000.0
    world_um = place_morphology(
        local_um, soma_local_um, target_um, normal, azimuth_deg=azimuth_deg
    )
    e1 = np.asarray(sample_at(mesh_pair1, target_mm.reshape(1, 3))).reshape(3)
    e2 = np.asarray(sample_at(mesh_pair2, target_mm.reshape(1, 3))).reshape(3)
    ve1 = uniform_quasipotential(e1, world_um, target_um)
    ve2 = uniform_quasipotential(e2, world_um, target_um)
    ve_static = ve1 + ve2

    try:
        for _sec, seg in segs:
            seg.e_extracellular = 0.0
        h.finitialize(-65.0)
        h.continuerun(50.0)
        v_rest = segs[soma_idx][1].v

        for i, (_sec, seg) in enumerate(segs):
            seg.e_extracellular = float(ve_static[i])
        h.finitialize(-65.0)
        h.continuerun(50.0)
        v_pol = segs[soma_idx][1].v
    finally:
        for _sec, seg in segs:
            seg.e_extracellular = 0.0
    return float(v_pol - v_rest)
