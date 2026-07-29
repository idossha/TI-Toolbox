"""FEM-based evaluator for arbitrary (continuous-position) electrode montages.

Flex-search (SimNIBS ``TesFlexOptimization``) optimizes electrode positions
as continuous points on the scalp, then maps the result post-hoc onto a
real EEG net via Hungarian assignment (:mod:`tit.tools.map_electrodes`).
There is no leadfield for continuous positions -- leadfields are only ever
built for a fixed EEG net -- so the only way to score flex-search's raw
optimizer output (before mapping) is to FEM-simulate it directly. This
module does that and returns the same metric shape used to score
leadfield-based montages (:class:`tit.opt.ex.engine.ExSearchEngine`), so
the two are directly comparable -- e.g. to quantify how much field quality
is lost when continuous positions get snapped onto discrete electrodes.

Mesh-mismatch problem
----------------------
Each electrode pair is simulated as its own ``TDCSLIST`` within a shared
SimNIBS ``SESSION``. Each ``TDCSLIST`` inserts its *own* electrodes into a
copy of the head mesh before solving, so the two (or more) channels' output
meshes have slightly different element counts -- observed as a 24-element
difference out of 5.9M elements on subject ``ernie`` (electrode geometry
perturbs the local tetrahedralization under and around the electrodes).
Combining the raw per-channel fields elementwise is therefore unsafe.

The fix: crop every channel's output mesh to the brain tissue tags (WM=1,
GM=2, matching the ``tissues=[1, 2]`` convention used by
:mod:`tit.opt.leadfield`) *before* combining. On ``ernie`` this made the
cropped element counts, tag arrays, and barycenters identical across
channels (max barycenter displacement 0.0 mm) -- the electrode-induced
remeshing is confined entirely to non-brain tissue. This mirrors the
crop-then-combine pattern already used, untested for the mismatch case, by
:class:`tit.sim.TI.TISimulation` and :class:`tit.sim.mTI.mTISimulation` in
production. :func:`_align_channel_fields` verifies the crop actually
produces matching element sets (tag array equality, not just counts)
before combining directly; if it does not, it falls back to
:class:`scipy.spatial.cKDTree` nearest-neighbour interpolation of every
other channel's field onto the first channel's element grid, and logs the
interpolation displacement so a large mismatch is visible.

See Also
--------
tit.opt.ex.engine.ExSearchEngine.compute_ti_field : The leadfield-based
    scorer this module's metric dict matches.
tit.calc.mti_modulation_depth : Envelope/carrier-power computation shared
    with the leadfield path.
tit.sim.TI.TISimulation : Production 2-pair TI simulation this module's
    SESSION/TDCSLIST construction and crop-to-brain-tags pattern mirrors.
tit.tools.map_electrodes : Hungarian mapping of continuous positions onto
    a real EEG net -- the post-hoc step whose accuracy cost this module
    measures.
"""

import logging
import os
import shutil
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from tit.calc import mti_modulation_depth

log = logging.getLogger(__name__)

WM_TAG = 1
GM_TAG = 2
_BRAIN_TAGS = [WM_TAG, GM_TAG]


def evaluate_montage_fem(
    subject_id: str,
    pairs: list[tuple[Sequence[float], Sequence[float]]],
    currents_mA: list[float],
    roi_mask_fn: Callable[[np.ndarray], np.ndarray],
    electrode_shape: str = "ellipse",
    dimensions: Sequence[float] = (8.0, 8.0),
    thickness: float = 4.0,
    workdir: str | None = None,
    cleanup: bool = True,
) -> dict[str, float]:
    """FEM-simulate a montage at continuous scalp positions and score it.

    Builds a SimNIBS ``SESSION`` with one ``TDCSLIST`` per electrode pair
    (each pair's two electrodes placed at fixed XYZ centres, current
    ``[+I, -I]``), runs one FEM solve for the whole montage, then combines
    the per-pair fields into the same TI/mTI modulation-depth envelope and
    ROI metrics :class:`~tit.opt.ex.engine.ExSearchEngine` computes from a
    leadfield -- see the module docstring for how the per-channel mesh
    mismatch is resolved.

    Parameters
    ----------
    subject_id : str
        Subject identifier resolved via
        :class:`tit.paths.PathManager` (``pm.m2m(subject_id)`` must exist).
    pairs : list of (centre_a, centre_b)
        One entry per electrode pair (2 pairs = standard TI, 4+ = mTI).
        Each *centre* is an ``[x, y, z]`` coordinate in subject space (mm)
        -- this is exactly the format of ``optimized_positions`` in
        flex-search's ``electrode_positions.json``, paired up by
        ``channel_array_indices``.
    currents_mA : list of float
        Current amplitude per pair, in mA. Must have the same length as
        *pairs*; each pair's two electrodes get ``[+I, -I]``.
    roi_mask_fn : callable
        ``roi_mask_fn(barycenters) -> bool array``. Called once with the
        ``(N, 3)`` array of barycenters of the montage's *grey-matter*
        elements (subject-space mm, after the brain-tissue crop) and must
        return a boolean mask of length ``N`` selecting the ROI elements.
        Use :func:`make_atlas_label_roi_fn` to build one from a volumetric
        atlas label by exact voxel containment.
    electrode_shape : str, default "ellipse"
        ``"ellipse"`` or ``"rect"`` -- passed through to each electrode.
    dimensions : sequence of float, default (8.0, 8.0)
        ``[width, height]`` of each electrode in mm.
    thickness : float, default 4.0
        Electrode (gel) thickness in mm.
    workdir : str or None
        Directory for SimNIBS FEM output. If ``None``, a temporary
        directory is created and removed afterward regardless of
        *cleanup* (there would be nothing else to keep it for). If given,
        an existing project directory can be reused; *cleanup* then
        controls only whether the large intermediate ``.msh`` files it
        writes are deleted afterward, not the directory itself.
    cleanup : bool, default True
        Delete large FEM intermediates (each per-channel ``.msh`` is
        roughly 200-300 MB) after metrics have been extracted.

    Returns
    -------
    dict
        ``roi_mean_Vm``, ``gm_mean_Vm``, ``focality_roi_over_gm``,
        ``roi_max_Vm``, ``roi_p999_Vm``, ``focality_cm``,
        ``carrier_rms_gm_Vm``, ``carrier_peak_gm_Vm``, plus
        ``n_roi_elements`` / ``n_gm_elements`` for diagnostics.
        See :func:`_compute_metrics` for the exact definitions.

    Raises
    ------
    ValueError
        If ``len(pairs) != len(currents_mA)``, or *roi_mask_fn* selects
        zero elements.

    See Also
    --------
    make_atlas_label_roi_fn : Build *roi_mask_fn* from a volumetric atlas.
    tit.opt.ex.engine.ExSearchEngine.compute_ti_field : Leadfield-based
        equivalent this function's output is directly comparable to.
    """
    if len(pairs) != len(currents_mA):
        raise ValueError(
            f"pairs and currents_mA must have the same length, got "
            f"{len(pairs)} and {len(currents_mA)}"
        )

    from simnibs import mesh_io, run_simnibs, sim_struct

    from tit.paths import get_path_manager

    pm = get_path_manager()
    m2m_dir = pm.m2m(subject_id)
    head_mesh = os.path.join(m2m_dir, f"{subject_id}.msh")

    own_workdir = workdir is None
    workdir = workdir or tempfile.mkdtemp(prefix="montage_eval_")
    os.makedirs(workdir, exist_ok=True)

    try:
        session = _build_session(
            m2m_dir,
            head_mesh,
            workdir,
            pairs,
            currents_mA,
            electrode_shape,
            dimensions,
            thickness,
        )
        log.info(
            f"FEM: {len(pairs)}-pair montage, subject={subject_id}, "
            f"currents_mA={currents_mA}"
        )
        run_simnibs(session)

        channel_meshes = _load_channel_meshes(mesh_io, workdir, subject_id, len(pairs))
        cropped = [m.crop_mesh(tags=_BRAIN_TAGS) for m in channel_meshes]
        e_fields, ref_mesh = _align_channel_fields(cropped)

        return _compute_metrics(e_fields, ref_mesh, roi_mask_fn)
    finally:
        if cleanup:
            _cleanup_workdir(workdir, remove_dir=own_workdir)


# ---------------------------------------------------------------------------
# SESSION / TDCSLIST construction
# ---------------------------------------------------------------------------


def _build_session(
    m2m_dir: str,
    head_mesh: str,
    workdir: str,
    pairs: list[tuple[Sequence[float], Sequence[float]]],
    currents_mA: list[float],
    electrode_shape: str,
    dimensions: Sequence[float],
    thickness: float,
):
    """Build a SimNIBS SESSION with one TDCSLIST per electrode pair.

    Mirrors :meth:`tit.sim.base.BaseSimulation._init_session` /
    ``_add_electrode_pair`` for the XYZ (no EEG cap) case, but is
    self-contained here so this module has no dependency on
    :mod:`tit.sim`. Leaves ``S.fields`` at the SimNIBS default (``"eE"``)
    -- this already includes the vector ``"E"`` field the crop/combine
    step needs; explicitly narrowing it (e.g. to ``"e"``, magnitude only)
    is what breaks :meth:`_align_channel_fields`.
    """
    from simnibs import sim_struct

    session = sim_struct.SESSION()
    session.subpath = m2m_dir
    session.fnamehead = head_mesh
    session.pathfem = workdir
    session.map_to_surf = False
    session.map_to_vol = False
    session.map_to_MNI = False
    session.open_in_gmsh = False

    for (centre_a, centre_b), current_mA in zip(pairs, currents_mA):
        current_A = current_mA / 1000.0
        tdcs = session.add_tdcslist()
        tdcs.currents = [current_A, -current_A]
        for idx, centre in enumerate((centre_a, centre_b)):
            el = tdcs.add_electrode()
            el.channelnr = idx + 1
            el.centre = list(centre)
            el.shape = electrode_shape
            el.dimensions = list(dimensions)
            el.thickness = [thickness]

    return session


def _load_channel_meshes(mesh_io, workdir: str, subject_id: str, n_pairs: int):
    """Load the per-pair output meshes SimNIBS wrote into *workdir*.

    Globs rather than assuming ``anisotropy_type == "scalar"`` in the
    filename, so this keeps working if a caller adds anisotropic
    conductivity support later.
    """
    meshes = []
    for i in range(1, n_pairs + 1):
        matches = sorted(Path(workdir).glob(f"{subject_id}_TDCS_{i}_*.msh"))
        matches = [p for p in matches if not p.name.endswith(".msh.opt")]
        if not matches:
            raise FileNotFoundError(
                f"No SimNIBS output mesh found for pair {i} in {workdir} "
                f"(expected {subject_id}_TDCS_{i}_*.msh)"
            )
        meshes.append(mesh_io.read_msh(str(matches[0])))
    return meshes


# ---------------------------------------------------------------------------
# Mesh-mismatch resolution
# ---------------------------------------------------------------------------


def _align_channel_fields(cropped_meshes: list):
    """Return ``(e_fields, reference_mesh)`` with every channel's vector E
    field aligned onto the first channel's (brain-tissue-cropped) element
    grid.

    Verifies alignment by comparing the cropped ``elm.tag1`` arrays
    (element count *and* tissue-tag order), not just element counts --
    two meshes can have the same count with different tags per position.
    If every channel matches, fields are combined directly with no
    interpolation (verified on subject ``ernie``: exact match, 0.0 mm
    barycenter displacement). Otherwise, falls back to 1-nearest-neighbour
    interpolation (:class:`scipy.spatial.cKDTree`) of the mismatched
    channel's field onto the reference channel's barycenters, and logs the
    interpolation displacement.

    Parameters
    ----------
    cropped_meshes : list of simnibs Msh
        Per-pair output meshes, already cropped to brain tissue tags.

    Returns
    -------
    e_fields : list of (M, 3) ndarray
        One vector field per pair, ordered to match *cropped_meshes*, all
        aligned to the first mesh's element grid.
    reference_mesh : simnibs Msh
        ``cropped_meshes[0]`` -- element tags/barycenters/volumes for
        every returned field.
    """
    ref = cropped_meshes[0]
    ref_tags = ref.elm.tag1
    e_fields = [ref.field["E"].value]
    interpolated_any = False

    for m in cropped_meshes[1:]:
        tags = m.elm.tag1
        if len(tags) == len(ref_tags) and np.array_equal(tags, ref_tags):
            e_fields.append(m.field["E"].value)
        else:
            interpolated_any = True
            e_fields.append(_nn_interpolate_field(m, ref))

    if interpolated_any:
        log.warning(
            "Per-channel brain-tissue element sets differ after cropping to "
            f"tags={_BRAIN_TAGS}; used nearest-neighbour interpolation to "
            "align channel fields. See preceding log line for displacement."
        )
    else:
        log.info(
            f"Brain-tissue element sets match exactly across "
            f"{len(cropped_meshes)} channel(s) after cropping to "
            f"tags={_BRAIN_TAGS} ({len(ref_tags)} elements) -- combined "
            "fields directly, no interpolation needed."
        )

    return e_fields, ref


def _nn_interpolate_field(source_mesh, ref_mesh) -> np.ndarray:
    """Resample *source_mesh*'s vector E field onto *ref_mesh*'s barycenters.

    1-nearest-neighbour in mm space via ``scipy.spatial.cKDTree``. Used
    only when :func:`_align_channel_fields` finds the brain-tissue-cropped
    element sets do not already match one-to-one.
    """
    from scipy.spatial import cKDTree

    src_bary = source_mesh.elements_baricenters().value
    ref_bary = ref_mesh.elements_baricenters().value

    tree = cKDTree(src_bary)
    dists, nn_idx = tree.query(ref_bary, k=1)
    log.info(
        f"NN interpolation displacement (mm): max={dists.max():.3f} "
        f"mean={dists.mean():.3f}"
    )
    return source_mesh.field["E"].value[nn_idx]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _element_volumes(mesh) -> np.ndarray:
    v = mesh.elements_volumes_and_areas().value
    return v[:, 0] if v.ndim > 1 else v


def _compute_metrics(
    e_fields: list[np.ndarray],
    ref_mesh,
    roi_mask_fn: Callable[[np.ndarray], np.ndarray],
) -> dict[str, float]:
    """Compute the leadfield-comparable metric dict from aligned E fields.

    ``e_fields`` is one vector field per electrode *pair* -- exactly the
    ``[E_1a, E_1b, E_2a, E_2b, ...]`` sub-channel layout, one array per
    pair, that :func:`tit.calc.mti_modulation_depth` expects (K=1 pair for
    standard 2-pair TI, K=n_pairs/2 sub-channel groups for mTI via the
    "multiband" scheme -- see :mod:`tit.opt.fast_eval`). Envelope and
    carrier-power definitions mirror
    :meth:`tit.opt.ex.engine.ExSearchEngine.compute_ti_field` exactly
    (``mti_modulation_depth`` for the envelope,
    ``0.5 * sum_k |E_k|^2`` for the direction-free carrier power) so the
    two are numerically comparable, not just shaped the same.

    Metric definitions
    -------------------
    roi_mean_Vm / gm_mean_Vm
        Volume-weighted mean envelope magnitude in the ROI / whole GM.
    focality_roi_over_gm
        ``roi_mean_Vm / gm_mean_Vm`` -- matches
        ``ExSearchEngine``'s ``{roi_name}_Focality``.
    roi_max_Vm / roi_p999_Vm
        Max / 99.9th-percentile envelope magnitude within the ROI.
    carrier_rms_gm_Vm / carrier_peak_gm_Vm
        RMS / sqrt(peak) of the direction-free total carrier power over
        GM -- matches ``ExSearchEngine``'s ``CarrierRMS_GM`` /
        ``CarrierPeak_GM``.
    focality_cm
        Geometric companion to the (unitless) ``focality_roi_over_gm``
        ratio: the equivalent-sphere radius, in cm, of the GM volume
        where the envelope exceeds 50% of ``roi_max_Vm`` (the classic
        "half-max spread" focality construction, e.g. Dmochowski et al.
        2011, reported here as a linear length rather than a volume).
        Smaller is more focal. This metric name/definition does not exist
        elsewhere in the codebase; it is defined here as the spatial
        (length-valued) counterpart to ``focality_roi_over_gm``
        (a dimensionless intensity ratio) since no prior implementation
        was found to match against.

    Parameters
    ----------
    e_fields : list of (M, 3) ndarray
        Aligned per-pair vector E fields (volts/meter), from
        :func:`_align_channel_fields`.
    ref_mesh : simnibs Msh
        Brain-tissue-cropped reference mesh (element tags/barycenters/
        volumes correspond 1:1 with *e_fields*).
    roi_mask_fn : callable
        See :func:`evaluate_montage_fem`.

    Returns
    -------
    dict
        See module-level summary in :func:`evaluate_montage_fem`.

    Raises
    ------
    ValueError
        If *roi_mask_fn* selects zero GM elements.
    """
    md_result = mti_modulation_depth(e_fields)
    envelope = md_result["md"]
    carrier_power_total = 0.5 * sum(np.sum(e * e, axis=1) for e in e_fields)

    tags = ref_mesh.elm.tag1
    volumes = _element_volumes(ref_mesh)
    barycenters = ref_mesh.elements_baricenters().value

    gm_mask = tags == GM_TAG
    gm_bary = barycenters[gm_mask]
    gm_vol = volumes[gm_mask]
    gm_env = envelope[gm_mask]
    gm_carrier = carrier_power_total[gm_mask]

    roi_mask = np.asarray(roi_mask_fn(gm_bary), dtype=bool)
    roi_idx = np.flatnonzero(roi_mask)
    if len(roi_idx) == 0:
        raise ValueError(
            "roi_mask_fn selected 0 elements out of "
            f"{len(gm_bary)} grey-matter elements"
        )

    roi_env = gm_env[roi_idx]
    roi_vol = gm_vol[roi_idx]

    roi_mean = float(np.average(roi_env, weights=roi_vol))
    roi_max = float(np.max(roi_env))
    roi_p999 = float(np.percentile(roi_env, 99.9))
    gm_mean = float(np.average(gm_env, weights=gm_vol))
    focality_roi_over_gm = roi_mean / gm_mean if gm_mean > 0 else 0.0
    carrier_rms_gm = float(np.sqrt(np.average(gm_carrier, weights=gm_vol)))
    carrier_peak_gm = float(np.sqrt(np.max(gm_carrier)))
    focality_cm = _half_max_spread_cm(gm_env, gm_vol, roi_max)

    log.info(
        f"Metrics: roi_mean={roi_mean:.4f} V/m, gm_mean={gm_mean:.4f} V/m, "
        f"focality={focality_roi_over_gm:.3f}, roi_max={roi_max:.4f} V/m, "
        f"n_roi={len(roi_idx)}, n_gm={len(gm_bary)}"
    )

    return {
        "roi_mean_Vm": roi_mean,
        "gm_mean_Vm": gm_mean,
        "focality_roi_over_gm": focality_roi_over_gm,
        "roi_max_Vm": roi_max,
        "roi_p999_Vm": roi_p999,
        "focality_cm": focality_cm,
        "carrier_rms_gm_Vm": carrier_rms_gm,
        "carrier_peak_gm_Vm": carrier_peak_gm,
        "n_roi_elements": int(len(roi_idx)),
        "n_gm_elements": int(len(gm_bary)),
    }


def _half_max_spread_cm(
    gm_env: np.ndarray, gm_vol: np.ndarray, roi_max: float
) -> float:
    """Equivalent-sphere radius (cm) of the GM volume with envelope >= 50%
    of *roi_max*. See ``focality_cm`` in :func:`_compute_metrics`.
    """
    if roi_max <= 0:
        return 0.0
    threshold = 0.5 * roi_max
    vol_above_mm3 = float(gm_vol[gm_env >= threshold].sum())
    if vol_above_mm3 <= 0:
        return 0.0
    radius_mm = (3.0 * vol_above_mm3 / (4.0 * np.pi)) ** (1.0 / 3.0)
    return radius_mm / 10.0


# ---------------------------------------------------------------------------
# ROI helper: exact voxel containment against a volumetric atlas
# ---------------------------------------------------------------------------


def make_atlas_label_roi_fn(
    atlas_path: str, label: int
) -> Callable[[np.ndarray], np.ndarray]:
    """Build a ``roi_mask_fn`` selecting elements by exact voxel containment.

    Transforms each element barycenter into voxel (i, j, k) indices via
    the *inverse* of the atlas affine, rounds to the nearest voxel, and
    tests ``data[i, j, k] == label``. Using the full affine inverse (a
    single matrix multiply) rather than deriving a voxel size from
    ``np.diag(affine)`` handles oblique atlas affines correctly by
    construction -- SimNIBS volumetric atlases (e.g.
    ``segmentation/labeling.nii.gz``) can carry an affine whose scale sits
    entirely in the off-diagonal terms (a pure permutation + unit scale on
    ``ernie``), which silently zeroes out a diagonal-based voxel size and
    was the root cause of a previously-fixed empty-ROI bug in
    :mod:`tit.opt.roi` (see that module's ``_resolve_volumetric_label``
    for the equivalent, KD-tree-nearest-neighbour-based fix for the
    WM/GM-only leadfield mesh this module does not use).

    Parameters
    ----------
    atlas_path : str
        Path to a volumetric label atlas NIfTI (e.g.
        ``m2m_<subject>/segmentation/labeling.nii.gz``).
    label : int
        Integer label value to select (e.g. ``17`` = Left-Hippocampus in
        SimNIBS's ``labeling.nii.gz``).

    Returns
    -------
    callable
        ``roi_mask_fn(barycenters) -> bool ndarray``, suitable for
        :func:`evaluate_montage_fem`.

    See Also
    --------
    evaluate_montage_fem : Consumes the returned callable.
    tit.opt.roi.ROIResolver._resolve_volumetric_label : Equivalent
        resolver for the WM/GM-only leadfield mesh (KD-tree nearest
        neighbour with a voxel-size tolerance, rather than exact voxel
        containment -- the leadfield mesh's barycenters are not
        guaranteed to line up with the FEM mesh's).
    """
    import nibabel as nib

    img = nib.load(atlas_path)
    data = np.asarray(img.dataobj)
    inv_affine = np.linalg.inv(img.affine)
    shape = data.shape

    def _roi_mask_fn(barycenters: np.ndarray) -> np.ndarray:
        barycenters = np.asarray(barycenters, dtype=float)
        n = len(barycenters)
        hom = np.hstack([barycenters, np.ones((n, 1))])
        voxel_coords = (inv_affine @ hom.T).T[:, :3]
        ijk = np.round(voxel_coords).astype(int)

        in_bounds = (
            (ijk[:, 0] >= 0)
            & (ijk[:, 0] < shape[0])
            & (ijk[:, 1] >= 0)
            & (ijk[:, 1] < shape[1])
            & (ijk[:, 2] >= 0)
            & (ijk[:, 2] < shape[2])
        )

        mask = np.zeros(n, dtype=bool)
        idx_in = ijk[in_bounds]
        mask[in_bounds] = data[idx_in[:, 0], idx_in[:, 1], idx_in[:, 2]] == label
        return mask

    return _roi_mask_fn


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

_LARGE_INTERMEDIATE_GLOBS = (
    "*_TDCS_*.msh",
    "*_TDCS_*.msh.opt",
    "*_TDCS_*.geo",
    "simnibs_simulation_*.mat",
)


def _cleanup_workdir(workdir: str, remove_dir: bool) -> None:
    """Remove large FEM intermediates (each channel ``.msh`` ~200-300 MB).

    If *remove_dir* is set (the module created a private temp directory),
    the whole directory is removed. Otherwise only the large, known
    intermediate file patterns are deleted -- *workdir* may be a shared
    project directory the caller wants to keep other contents of.
    """
    if remove_dir:
        shutil.rmtree(workdir, ignore_errors=True)
        return

    for pattern in _LARGE_INTERMEDIATE_GLOBS:
        for f in Path(workdir).glob(pattern):
            f.unlink(missing_ok=True)
