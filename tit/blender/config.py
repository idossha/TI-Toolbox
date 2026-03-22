"""Configuration dataclasses for Blender/SimNIBS export utilities.

Pure Python -- no SimNIBS, numpy, or heavy dependencies.
Mirrors the tit.opt.config / tit.sim.config pattern.

All paths are resolved automatically via PathManager based on
subject_id and simulation_name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


# ── Montage config ──────────────────────────────────────────────────────────


@dataclass
class MontageConfig:
    """Configuration for montage publication scene generation.

    Creates a publication-ready Blender scene (.blend) containing the scalp,
    gray-matter surface, and electrode placements for a given simulation.
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


# ── Vector field config ─────────────────────────────────────────────────────


@dataclass
class VectorConfig:
    """Configuration for TI/mTI vector arrow export to PLY.

    Vectors are placed at face barycenters of the central surface mesh and
    exported as colored PLY arrow geometry.

    All paths are resolved automatically from ``subject_id`` +
    ``simulation_name`` via PathManager.  mTI mode is auto-detected
    when TDCS meshes 3 and 4 exist.
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
    """

    class Format(StrEnum):
        """Output mesh format for region export."""

        STL = "stl"
        PLY = "ply"

    class Surface(StrEnum):
        """Cortical surface type for msh2cortex extraction."""

        CENTRAL = "central"
        PIAL = "pial"
        WHITE = "white"

    # ── Required ──
    subject_id: str
    simulation_name: str

    # ── Format ──
    format: Format = Format.PLY

    # ── Atlas and surface ──
    atlas: str = "DK40"
    surface: Surface = Surface.CENTRAL
    field_name: str = "TI_max"
    msh2cortex_path: str | None = None

    # ── Alternative mesh input (bypasses auto-resolved central surface) ──
    gm_mesh: str | None = None

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
        if isinstance(self.surface, str):
            self.surface = RegionConfig.Surface(self.surface)

        # field_range validation
        if self.field_range is not None:
            if len(self.field_range) != 2:
                raise ValueError("field_range must be a (min, max) pair")
            if self.field_range[0] > self.field_range[1]:
                raise ValueError("field_range min must be <= max")
