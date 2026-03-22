#!/usr/bin/env simnibs_python
"""Configuration dataclasses for TI/mTI simulations."""

from dataclasses import dataclass, field
from enum import Enum


class SimulationMode(Enum):
    TI = "TI"
    MTI = "mTI"


class MontageMode(Enum):
    NET = "net"
    FLEX_MAPPED = "flex_mapped"
    FLEX_FREE = "flex_free"
    FREEHAND = "freehand"


@dataclass
class Montage:
    """Unified montage: EEG-cap labels or 3-D XYZ coordinates."""

    Mode = MontageMode

    name: str
    mode: MontageMode
    electrode_pairs: list[tuple]
    eeg_net: str | None = None

    @property
    def is_xyz(self) -> bool:
        return self.mode in (MontageMode.FLEX_FREE, MontageMode.FREEHAND)

    @property
    def simulation_mode(self) -> SimulationMode:
        n = len(self.electrode_pairs)
        if n == 2:
            return SimulationMode.TI
        if n >= 4:
            return SimulationMode.MTI
        raise ValueError(
            f"Invalid number of electrode pairs: {n}. Expected 2 (TI) or 4+ (mTI)."
        )

    @property
    def num_pairs(self) -> int:
        return len(self.electrode_pairs)


_VALID_CONDUCTIVITIES = {"scalar", "vn", "dir", "mc"}


@dataclass
class SimulationConfig:
    subject_id: str
    montages: list[Montage]
    conductivity: str = "scalar"
    intensities: list[float] = field(default_factory=lambda: [1.0, 1.0])
    electrode_shape: str = "ellipse"
    electrode_dimensions: list[float] = field(default_factory=lambda: [8.0, 8.0])
    gel_thickness: float = 4.0
    rubber_thickness: float = 2.0
    # map_to_surf must be True — TI_normal calculation requires surface overlays.
    map_to_surf: bool = True
    # NIfTI conversion is handled by tit.tools.mesh2nii (not SimNIBS SESSION).
    # These are kept for documentation/serialization but are not passed to SimNIBS.
    map_to_vol: bool = False
    map_to_mni: bool = False
    map_to_fsavg: bool = False
    open_in_gmsh: bool = False
    tissues_in_niftis: str = "all"
    aniso_maxratio: float = 10.0
    aniso_maxcond: float = 2.0

    def __post_init__(self):
        if self.conductivity not in _VALID_CONDUCTIVITIES:
            raise ValueError(
                f"Invalid conductivity {self.conductivity!r}, "
                f"must be one of {_VALID_CONDUCTIVITIES}"
            )


def parse_intensities(s: str) -> list[float]:
    """Parse comma-separated intensity string into list of floats."""
    v = [float(x.strip()) for x in s.split(",")]
    n = len(v)
    if n == 1:
        return [v[0], v[0]]
    if n >= 2 and n % 2 == 0:
        return v
    raise ValueError(
        f"Invalid intensity format: expected 1 or an even number of values; got {n}: {s!r}"
    )
