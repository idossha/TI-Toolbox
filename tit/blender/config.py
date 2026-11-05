"""Configuration dataclasses for Blender/SimNIBS export utilities.

Pure Python -- no SimNIBS, numpy, or heavy dependencies.
Mirrors the ``tit.opt.config`` / ``tit.sim.config`` pattern.

All paths are resolved automatically via
:func:`tit.paths.get_path_manager` based on ``subject_id`` and
``simulation_name``.

Classes
-------
MontageConfig
    Publication-ready montage scene generation.
VectorConfig
    TI/mTI vector arrow PLY export.
RegionConfig
    Atlas-labelled cortical region mesh export.

Functions
---------
central_surface_path, surface_field_name, carrier_mesh_paths, scalp_source_mesh
    Which files of a TI or mTI simulation an export reads. The runners and
    :mod:`tit.jobs.preflight` both call these, so the check before a job and
    the job itself cannot disagree about where an input lives.

See Also
--------
tit.config_io : Serialise configs to/from JSON for CLI dispatch.
"""

from __future__ import annotations

import os
import string
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from tit.blender.network_setup import ALL_VIEWS, validate_overrides
from tit.tract.config import Selection

# ── Simulation inputs (shared by the runners and tit.jobs.preflight) ─────────


def _is_mti(subject_id: str, simulation_name: str) -> bool:
    from tit.analyzer.field_selector import is_mti_simulation

    return is_mti_simulation(subject_id, simulation_name)


def central_surface_path(subject_id: str, simulation_name: str) -> str:
    """The central cortical surface *simulation_name* wrote.

    An mTI run writes only ``mTI/mesh/surfaces/<sim>_mTI_central.msh``; a 2-pair TI
    run writes ``TI/mesh/surfaces/<sim>_TI_central.msh``.

    Args:
        subject_id: Subject identifier (without ``sub-``).
        simulation_name: Simulation folder name.

    Returns:
        The path (existence is not checked).
    """
    from tit.paths import get_path_manager

    pm = get_path_manager()
    if _is_mti(subject_id, simulation_name):
        return pm.mti_central_surface(subject_id, simulation_name)
    return pm.ti_central_surface(subject_id, simulation_name)


def surface_field_name(subject_id: str, simulation_name: str, field_name: str) -> str:
    """*field_name* as this simulation spells it.

    ``TI_max`` and ``mTI_max`` are one quantity: a 2-pair mesh calls it ``TI_max``,
    an mTI mesh ``mTI_max`` (the alias rule of
    :func:`tit.analyzer.field_selector.select_field_file`). Every other field keeps
    its name.
    """
    from tit import constants as const

    if field_name in (const.FIELD_TI_MAX, const.FIELD_MTI_MAX):
        if _is_mti(subject_id, simulation_name):
            return const.FIELD_MTI_MAX
        return const.FIELD_TI_MAX
    return field_name


def carrier_mesh_paths(
    subject_id: str, simulation_name: str, conductivity: str
) -> list[str]:
    """Every channel's high-frequency volume mesh, in channel order.

    A TI run keeps SimNIBS's ``<sid>_TDCS_1_<cond>.msh`` and ``..._TDCS_2_...``; an
    mTI run renames channel ``i`` to the ``i``-th letter when it files them
    (``MTISimulation._organize_files``), so its N channels are ``TDCS_A`` .. and at
    least four (A-D) are always listed, so a missing one is named.

    Returns:
        Paths under ``high_Frequency/mesh/`` (existence is not checked beyond
        counting the mTI channels).
    """
    from tit.paths import get_path_manager

    hf = os.path.join(
        get_path_manager().simulation(subject_id, simulation_name),
        "high_Frequency",
        "mesh",
    )

    def path(channel: str) -> str:
        return os.path.join(hf, f"{subject_id}_TDCS_{channel}_{conductivity}.msh")

    if not _is_mti(subject_id, simulation_name):
        return [path("1"), path("2")]
    letters = list(string.ascii_uppercase[:4])
    for letter in string.ascii_uppercase[4:]:
        if not os.path.exists(path(letter)):
            break
        letters.append(letter)
    return [path(letter) for letter in letters]


def tetrahedral_mesh_candidates(sim_dir: str) -> list[str]:
    """Legacy volume meshes under *sim_dir* that hold the head's skin.

    ``TI/mesh/*_TI_final.msh`` / ``*_T1.msh`` and every ``high_Frequency/mesh/*.msh``,
    unsorted.
    """
    candidates: list[str] = []
    ti_mesh_dir = os.path.join(sim_dir, "TI", "mesh")
    if os.path.isdir(ti_mesh_dir):
        for f in os.listdir(ti_mesh_dir):
            if f.endswith("_TI_final.msh") or f.endswith("_T1.msh"):
                candidates.append(os.path.join(ti_mesh_dir, f))
    hf_mesh_dir = os.path.join(sim_dir, "high_Frequency", "mesh")
    if os.path.isdir(hf_mesh_dir):
        for f in os.listdir(hf_mesh_dir):
            if f.endswith(".msh"):
                candidates.append(os.path.join(hf_mesh_dir, f))
    return candidates


def scalp_source_mesh(ti_mesh: str, sim_dir: str) -> str | None:
    """The tetrahedral mesh a montage scene cuts its scalp from.

    Args:
        ti_mesh: The run's ``TI/mesh/<sim>_TI.msh`` (``PathManager.ti_mesh``).
        sim_dir: The simulation folder (``PathManager.simulation``).

    Returns:
        *ti_mesh* when it exists; otherwise the first, sorted, of
        :func:`tetrahedral_mesh_candidates` (an mTI run has only its high-frequency
        meshes); ``None`` when the simulation holds no volume mesh at all.
    """
    if os.path.isfile(ti_mesh):
        return ti_mesh
    candidates = tetrahedral_mesh_candidates(sim_dir)
    return sorted(candidates)[0] if candidates else None


# ── Montage config ──────────────────────────────────────────────────────────


@dataclass
class MontageConfig:
    """Configuration for montage publication scene generation.

    Creates a publication-ready Blender scene (``.blend``) containing the
    scalp, grey-matter surface, and electrode placements for a given
    simulation.

    Attributes
    ----------
    subject_id : str
        Subject identifier (without ``sub-`` prefix).
    simulation_name : str
        Name of the simulation directory.
    output_dir : str or None
        Output directory.  Resolved automatically when ``None``.
    show_full_net : bool
        If ``True``, place the entire electrode net; otherwise only
        montage electrodes.
    electrode_diameter_mm : float
        Electrode cylinder diameter in millimetres.
    electrode_height_mm : float
        Electrode cylinder height in millimetres.

    See Also
    --------
    tit.blender.montage_publication.run_montage : Entry point that
        consumes this config.
    """

    subject_id: str
    simulation_name: str
    output_dir: str | None = None
    show_full_net: bool = True
    electrode_diameter_mm: float = 10.0
    electrode_height_mm: float = 6.0

    def __post_init__(self) -> None:
        if not (self.subject_id or "").strip():
            raise ValueError("subject_id is required")
        if not (self.simulation_name or "").strip():
            raise ValueError("simulation_name is required")
        if self.electrode_diameter_mm <= 0:
            raise ValueError("electrode_diameter_mm must be > 0")
        if self.electrode_height_mm <= 0:
            raise ValueError("electrode_height_mm must be > 0")


# ── Tract config ────────────────────────────────────────────────────────────


@dataclass
class TractVisualConfig:
    """Tractography renders of one simulation's ``tract/`` outputs.

    Streamlines become emissive tubes in a glass brain, coloured by a field metric along
    each fibre. Stills, the web viewer and the connectome figure are on by default; the
    turntable and the propagation animation are opt-in because they render many frames.

    Attributes
    ----------
    subject_id, simulation_name : str
        The simulation whose ``tract/`` directory is read.
    tractogram : str
        A ``.trx`` file name inside ``Simulations/<sim>/tract/`` or an absolute path; its
        directory supplies ``edges.json`` and ``connectome_*.npz``. Blank picks ``all.trx``,
        else the directory's only ``.trx``.
    metric : Metric
        What colours the tubes: ``ti_along``, ``ti_max``, ``ti_ratio``, ``align_index``
        (``ti_along / ti_avg``: field along the fibre over a random direction's, diverging
        about 1) or ``direction``.
    focus : bool
        Network-focused stills and videos: the bundle and top edges as full tubes, the rest
        of the tractogram as faint context, their endpoint regions lit from the subject's own
        labels. ``False`` draws a subsample of the whole tractogram.
    network_bundle : str
        A bundle file of the tract directory (``insula_lh`` for ``insula_lh.trx``); blank
        foregrounds the top edges only.
    network_top_edges, network_min_streamlines : int
        How many of ``summary.json``'s top edges join the foreground, and the streamline
        count an edge needs to be one of them.
    context_streamlines : int
        Faint context fibres drawn behind the network (0: none).
    network_from, network_to, network_name : list of str, list of str, str
        A network by its regions: every streamline whose edge joins a region of
        ``network_from`` to one of ``network_to`` (either way round), all drawn at one width,
        none subsampled. Overrides ``network_bundle`` and the top edges.
    selection : Selection or None
        A named network, kind ``"edges"``: the one definition the optimizer's mask and the ranking
        also use. Its ``<name>.trx`` is read when it exists, else ``all.trx``; ``regions`` holds its
        seeds. Its render is set up by :func:`tit.blender.network_setup.resolve_network_setup`, and
        outputs carry its name, so networks of one simulation coexist. Replaces every other network
        field, and the fields ``overrides`` can set.
    preset : str
        The :mod:`tit.tract.presets` id ``selection`` came from, if any. It adds nothing to what is
        drawn; a same-side preset's opposite-hemisphere edges left out of ``selection`` are stated
        in the caption and the manifest from it, with their count.
    overrides : dict
        With ``selection`` (or one bundle, ``network_top_edges`` 0), the keys of :data:`tit.blender.network_setup.OVERRIDABLE` replacing the
        automatic value (``iso_shell_percentile: null`` draws no shell).
    highlight_regions : list of str
        Regions lit evenly (e.g. both thalami) in place of the strongest endpoint regions.
    region_labels : bool
        Name the lit regions on the still.
    lateral_side : int
        -1 left, 1 right, 0 the side of the strongest field.
    iso_shell_percentile : float or None
        Draw one translucent TI_max isosurface of the brain at this volume-weighted percentile.
    prune_keep_fraction : float or None
        In a named-network turntable sequence, sweep away all but this fraction of the
        streamlines, the strongest by mean TI_max along each, then name where they end.
    label_regions : int
        How many cortical regions the pruned network names.
    turntable_crossfade : bool
        The turntable shows direction colours for its first half, crossfades over 2 s, then
        shows ``metric`` (a scalar metric) for the second half.
    max_streamlines : int
        Rendering budget; a larger tractogram is subsampled toward its high-field fibres.
    vmax_v_per_m : float or None
        Top of the colour window; ``None`` uses the 99.5th percentile of the shown metric.
        Fix it to compare runs on one scale (``ti_ratio`` always spans 0-1).
    stills, turntable, propagation, web, connectome : bool
        Which outputs to write.
    views : list of str
        The stills to render: ``lateral``, ``superior``, ``oblique``, ``posterior``. Empty renders
        the first three (with ``selection``, the views :mod:`tit.blender.network_setup` chooses).
    quality : Quality
        ``final`` (32 samples per still; videos 1920x1080 at 16) or ``preview`` (8 samples per
        still; videos 960x540 at 6), for checking a choice before a long render.
    thalamocortical_sequence : bool
        One video of ``all.trx``: the frontal, then the posterior thalamocortical network (DK40
        parcels), each going from direction colours to TI_max on one shared window, pruned to
        its strongest 15 % by mean TI_max, with the regions those fibres reach named in their
        own colours. It sets its own network, metric and shell, so it runs alone: ``stills``,
        ``turntable``, ``propagation`` and the network fields must be off or empty.
    width, height : int
        Still resolution in pixels.
    turntable_frames, turntable_degrees : int, float
        Orbit length (24 fps) and sweep.
    front_speed_mm_per_frame : float
        Propagation-front speed along the arc.
    roi_center_mm, roi_radius_mm : list of float or None, float
        A target sphere to draw, in subject mm.
    output_dir : str or None
        Resolved to ``visual_exports/sub-<id>/<sim>/tract`` when ``None``.
    seed : int
        Subsampling seed.
    """

    class Metric(StrEnum):
        """Per-vertex colouring of the streamline tubes."""

        TI_ALONG = "ti_along"
        TI_MAX = "ti_max"
        TI_RATIO = "ti_ratio"
        ALIGN_INDEX = "align_index"
        DIRECTION = "direction"

    class Quality(StrEnum):
        """How much sampling and video resolution a render spends."""

        FINAL = "final"
        PREVIEW = "preview"

    subject_id: str
    simulation_name: str
    tractogram: str = ""
    metric: Metric = Metric.TI_ALONG
    max_streamlines: int = 15_000
    vmax_v_per_m: float | None = None
    focus: bool = True
    network_bundle: str = ""
    network_top_edges: int = 5
    network_min_streamlines: int = 10
    context_streamlines: int = 0
    network_from: list[str] = field(default_factory=list)
    network_to: list[str] = field(default_factory=list)
    network_name: str = ""
    selection: Selection | None = None
    preset: str = ""
    overrides: dict[str, Any] = field(default_factory=dict)
    highlight_regions: list[str] = field(default_factory=list)
    region_labels: bool = True
    lateral_side: int = 0
    iso_shell_percentile: float | None = None
    turntable_crossfade: bool = False
    prune_keep_fraction: float | None = None
    label_regions: int = 5
    stills: bool = True
    turntable: bool = False
    propagation: bool = False
    web: bool = True
    connectome: bool = True
    views: list[str] = field(default_factory=list)
    quality: Quality = Quality.FINAL
    thalamocortical_sequence: bool = False
    width: int = 2400
    height: int = 1600
    turntable_frames: int = 120
    turntable_degrees: float = 360.0
    front_speed_mm_per_frame: float = 1.5
    roi_center_mm: list[float] | None = None
    roi_radius_mm: float = 10.0
    output_dir: str | None = None
    seed: int = 0

    def __post_init__(self) -> None:
        if not (self.subject_id or "").strip():
            raise ValueError("subject_id is required")
        if not (self.simulation_name or "").strip():
            raise ValueError("simulation_name is required")
        self.metric = TractVisualConfig.Metric(self.metric)
        self.quality = TractVisualConfig.Quality(self.quality)
        unknown = set(self.views) - set(ALL_VIEWS)
        if unknown:
            raise ValueError(f"unknown views: {sorted(unknown)}")
        if self.selection is not None:
            if self.selection.kind != "edges":
                raise ValueError("selection draws region pairs: kind must be 'edges'")
            if (
                self.thalamocortical_sequence
                or self.network_from
                or (self.network_bundle or "").strip()
            ):
                raise ValueError(
                    "selection is the network: leave network_from, network_bundle and "
                    "thalamocortical_sequence empty"
                )
        elif self.overrides and not (
            (self.network_bundle or "").strip() and not self.network_top_edges
        ):
            raise ValueError("overrides adjust a selection's automatic setup")
        validate_overrides(self.overrides)
        if self.thalamocortical_sequence and (
            self.stills
            or self.turntable
            or self.propagation
            or self.network_from
            or self.network_bundle
        ):
            raise ValueError(
                "thalamocortical_sequence runs alone: stills, turntable, propagation "
                "and the network fields must be off or empty"
            )
        if self.max_streamlines <= 0:
            raise ValueError("max_streamlines must be > 0")
        if self.vmax_v_per_m is not None and not self.vmax_v_per_m > 0:
            raise ValueError("vmax_v_per_m must be > 0")
        if self.network_top_edges < 0 or self.network_min_streamlines < 1:
            raise ValueError(
                "network_top_edges must be >= 0, network_min_streamlines >= 1"
            )
        if self.context_streamlines < 0:
            raise ValueError("context_streamlines must be >= 0")
        if bool(self.network_from) != bool(self.network_to):
            raise ValueError("network_from and network_to go together")
        if self.lateral_side not in (-1, 0, 1):
            raise ValueError("lateral_side is -1, 0 or 1")
        if (
            self.iso_shell_percentile is not None
            and not 0 < self.iso_shell_percentile < 100
        ):
            raise ValueError("iso_shell_percentile must be in (0, 100)")
        if (
            self.turntable_crossfade
            and self.metric == TractVisualConfig.Metric.DIRECTION
        ):
            raise ValueError("turntable_crossfade fades direction into a scalar metric")
        if (
            self.prune_keep_fraction is not None
            and not 0 < self.prune_keep_fraction < 1
        ):
            raise ValueError("prune_keep_fraction must be in (0, 1)")
        if self.label_regions < 0:
            raise ValueError("label_regions must be >= 0")
        name = (self.network_bundle or "").strip()
        if name and (os.sep in name or name.startswith(".")):
            raise ValueError("network_bundle is a bundle name in the tract directory")
        if self.width < 64 or self.height < 64:
            raise ValueError("width and height must be at least 64 px")
        if self.turntable_frames < 2:
            raise ValueError("turntable_frames must be >= 2")
        if self.front_speed_mm_per_frame <= 0:
            raise ValueError("front_speed_mm_per_frame must be > 0")
        if self.roi_center_mm is not None and len(self.roi_center_mm) != 3:
            raise ValueError("roi_center_mm must be [x, y, z]")
        if self.roi_radius_mm <= 0:
            raise ValueError("roi_radius_mm must be > 0")


# ── Vector field config ─────────────────────────────────────────────────────


@dataclass
class VectorConfig:
    """Configuration for TI/mTI vector arrow export to PLY.

    Vectors are placed at face barycenters of the central surface mesh
    and exported as coloured PLY arrow geometry.

    All paths are resolved automatically from ``subject_id`` +
    ``simulation_name`` via PathManager.  mTI mode is auto-detected
    when TDCS meshes 3 and 4 exist.

    Attributes
    ----------
    subject_id : str
        Subject identifier.
    simulation_name : str
        Name of the simulation directory.
    export_ch1_ch2 : bool
        Export individual channel arrows.
    export_sum : bool
        Export E-field sum arrows.
    export_ti_normal : bool
        Export ``TI_normal`` arrows: the envelope along the surface normal.
    export_combined : bool
        Export all channels merged into one PLY.
    top_percent : float or None
        Keep only the top *N* percent of vectors by magnitude.
    count : int
        Maximum number of arrows to export.
    all_nodes : bool
        If ``True``, ignore *count* and export every node.
    seed : int
        Random seed for reproducible sub-sampling.
    length_mode : Length
        ``"linear"`` or ``"visual"`` arrow-length mapping.
    length_scale : float
        Multiplicative length factor.
    vector_scale : float
        Global arrow size scale.
    vector_width : float
        Arrow shaft width multiplier.
    vector_length : float
        Arrow shaft length multiplier.
    anchor : Anchor
        ``"tail"`` or ``"head"`` -- which end touches the surface.
    color : Color
        ``"rgb"`` (channel colours) or ``"magscale"`` (percentile ramp).
    blue_percentile : float
        Percentile threshold for the blue end of the magscale ramp.
    green_percentile : float
        Percentile threshold for green.
    red_percentile : float
        Percentile threshold for red.
    verbose : bool
        Enable verbose logging.

    See Also
    --------
    tit.blender.vector_field_exporter.run_vectors : Entry point that
        consumes this config.
    """

    class Color(StrEnum):
        """Color mapping strategy for vector-field arrows."""

        RGB = "rgb"
        MAGSCALE = "magscale"

    class Anchor(StrEnum):
        """Which end of the arrow touches the surface barycenter."""

        TAIL = "tail"
        HEAD = "head"

    class Length(StrEnum):
        """Arrow length mapping mode."""

        LINEAR = "linear"
        VISUAL = "visual"

    # ── Required ──
    subject_id: str
    simulation_name: str

    # ── Optional outputs ──
    export_ch1_ch2: bool = False
    export_sum: bool = False
    export_ti_normal: bool = False
    export_combined: bool = False

    # ── Filtering and sampling ──
    top_percent: float | None = None
    count: int = 100_000
    all_nodes: bool = False
    seed: int = 42

    # ── Arrow styling ──
    length_mode: Length = Length.LINEAR
    length_scale: float = 1.0
    vector_scale: float = 1.0
    vector_width: float = 1.0
    vector_length: float = 1.0
    anchor: Anchor = Anchor.TAIL

    # ── Color ──
    color: Color = Color.RGB
    blue_percentile: float = 50.0
    green_percentile: float = 80.0
    red_percentile: float = 95.0

    # ── Debug ──
    verbose: bool = False

    # ── Internal — resolved by run_vectors() via PathManager ──
    mesh1: str = field(default="", repr=False)
    mesh2: str = field(default="", repr=False)
    output_dir: str = field(default="", repr=False)
    central_surface: str = field(default="", repr=False)
    mesh3: str | None = field(default=None, repr=False)
    mesh4: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not (self.subject_id or "").strip():
            raise ValueError("subject_id is required")
        if not (self.simulation_name or "").strip():
            raise ValueError("simulation_name is required")

        # Coerce string enums
        if isinstance(self.length_mode, str):
            self.length_mode = VectorConfig.Length(self.length_mode)
        if isinstance(self.anchor, str):
            self.anchor = VectorConfig.Anchor(self.anchor)
        if isinstance(self.color, str):
            self.color = VectorConfig.Color(self.color)

        # mTI requires both mesh3 and mesh4
        if (self.mesh3 is None) != (self.mesh4 is None):
            raise ValueError("mTI mode requires both mesh3 and mesh4")

        # Sampling
        if self.count <= 0:
            raise ValueError("count must be positive")
        if self.top_percent is not None and not (0.0 < self.top_percent <= 100.0):
            raise ValueError("top_percent must be in (0, 100]")

        # Arrow styling
        if self.vector_scale <= 0:
            raise ValueError("vector_scale must be positive")
        if self.vector_width <= 0:
            raise ValueError("vector_width must be positive")
        if self.vector_length <= 0:
            raise ValueError("vector_length must be positive")
        if self.length_scale <= 0:
            raise ValueError("length_scale must be positive")

        # Percentile ordering
        if not (0.0 <= self.blue_percentile <= 100.0):
            raise ValueError("blue_percentile must be in [0, 100]")
        if not (0.0 <= self.green_percentile <= 100.0):
            raise ValueError("green_percentile must be in [0, 100]")
        if not (0.0 <= self.red_percentile <= 100.0):
            raise ValueError("red_percentile must be in [0, 100]")
        # Each threshold starts the next colour band; the runner used to clamp a
        # non-monotone order silently into a ramp nobody typed. RGB colouring
        # reads none of them.
        if self.color == VectorConfig.Color.MAGSCALE and not (
            self.blue_percentile <= self.green_percentile <= self.red_percentile
        ):
            raise ValueError(
                "magnitude-scale percentiles must rise blue <= green <= red; got "
                f"blue {self.blue_percentile}, green {self.green_percentile}, "
                f"red {self.red_percentile}"
            )

    @property
    def is_mti(self) -> bool:
        """True when four meshes are provided (mTI mode)."""
        return self.mesh3 is not None and self.mesh4 is not None


# ── Region export config ────────────────────────────────────────────────────


@dataclass
class RegionConfig:
    """Configuration for cortical region mesh export (STL or PLY).

    Extracts atlas-labelled cortical regions and optionally the whole GM
    surface from a SimNIBS surface mesh.

    All paths are resolved automatically from ``subject_id`` +
    ``simulation_name`` via PathManager.

    Attributes
    ----------
    subject_id : str
        Subject identifier.
    simulation_name : str
        Name of the simulation directory.
    format : Format
        Output mesh format (``"stl"`` or ``"ply"``).
    atlas : str
        Atlas name, e.g. ``"DK40"``.
    field_name : str
        Scalar field to map onto region meshes.
    skip_regions : bool
        Skip per-region export (export only whole GM).
    skip_whole_gm : bool
        Skip whole-GM export.
    regions : list of str
        Region names to export.  Empty means all regions.
    keep_meshes : bool
        Also save intermediate ``.msh`` files alongside PLY/STL.
    scalars : bool
        PLY-only: embed raw scalar values instead of vertex colours.
    colormap : str
        Matplotlib colormap name for PLY vertex colours.
    field_range : tuple of float or None
        ``(vmin, vmax)`` for colour normalisation.
    global_from_nifti : str or None
        Path to a NIfTI for computing a global colour range.

    See Also
    --------
    tit.blender.region_exporter.run_regions : Entry point that
        consumes this config.
    """

    class Format(StrEnum):
        """Output mesh format for region export."""

        STL = "stl"
        PLY = "ply"

    # ── Required ──
    subject_id: str
    simulation_name: str

    # ── Format ──
    format: Format = Format.PLY

    # ── Atlas and field ──
    atlas: str = "DK40"
    field_name: str = "TI_max"

    # ── Output scope ──
    skip_regions: bool = False
    skip_whole_gm: bool = False
    regions: list[str] = field(default_factory=list)
    keep_meshes: bool = False

    # ── PLY-only options (ignored for STL) ──
    scalars: bool = False
    colormap: str = "viridis"
    field_range: tuple[float, float] | None = None
    global_from_nifti: str | None = None

    # ── Internal — resolved by run_regions() via PathManager ──
    m2m_dir: str = field(default="", repr=False)
    output_dir: str = field(default="", repr=False)
    mesh: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not (self.subject_id or "").strip():
            raise ValueError("subject_id is required")
        if not (self.simulation_name or "").strip():
            raise ValueError("simulation_name is required")

        # Coerce string enums
        if isinstance(self.format, str):
            self.format = RegionConfig.Format(self.format)

        # field_range validation
        if self.field_range is not None:
            if len(self.field_range) != 2:
                raise ValueError("field_range must be a (min, max) pair")
            if self.field_range[0] > self.field_range[1]:
                raise ValueError("field_range min must be <= max")


# ── Sub-cortical config ─────────────────────────────────────────────────────


@dataclass
class SubcorticalConfig:
    """Configuration for sub-cortical mesh export from a labelled NIfTI.

    The v2.5.0 GUI ran this mode in-process (``VisualExporterWidget._run``'s
    sub-cortical branch); v3 runs it as a ``blender`` job so it appears in the
    Jobs rail and terminal like every other computation.  The field order and
    the values below are exactly what that branch used, so the files written
    are byte-identical to 2.5.0's.

    Attributes
    ----------
    subject_id : str
        Subject identifier (without ``sub-`` prefix).
    simulation_name : str
        Simulation directory name.  Empty means "no simulation" -- geometry
        only, no field-coloured PLY (the Qt widget's own rule).
    nifti_path : str
        Labelled volume to mesh.  Empty resolves to
        ``<m2m>/segmentation/labeling.nii.gz``.
    labels : list of int
        Label values to extract first.  Empty means the whole volume
        (suffix ``full`` rather than ``labels_<a>_<b>``).
    clean_components : bool
        Remove small disconnected components (threshold 0.1).
    field_name : str
        Field whose subject-space NIfTI colours the PLY export.
    output_dir : str
        Resolved by :func:`tit.blender.subcortical_exporter.run_subcortical`
        to ``derivatives/ti-toolbox/visual_exports/sub-<id>/sub-cortical``.

    See Also
    --------
    tit.blender.subcortical_exporter.run_subcortical : Entry point that
        consumes this config.
    """

    subject_id: str
    simulation_name: str = ""
    nifti_path: str = ""
    labels: list[int] = field(default_factory=list)
    clean_components: bool = False
    field_name: str = "TI_max"

    # ── Internal — resolved by run_subcortical() via PathManager ──
    output_dir: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not (self.subject_id or "").strip():
            raise ValueError("subject_id is required")
        if not (self.field_name or "").strip():
            raise ValueError("field_name is required")
        try:
            self.labels = [int(v) for v in (self.labels or [])]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"labels must be integers: {exc}") from exc
