#!/usr/bin/env simnibs_python
"""Configuration dataclasses for TI/mTI simulations."""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Union


class SimulationMode(Enum):
    TI = "TI"
    MTI = "mTI"


class ConductivityType(Enum):
    SCALAR = "scalar"
    VN = "vn"
    DIR = "dir"
    MC = "mc"


class MTIFieldMethod(Enum):
    RECURSIVE_TI = "recursive_ti"
    FULL_FIELD_DIRECTIONAL_AM = "full_field_directional_am"


@dataclass
class ElectrodeConfig:
    """
    Electrode shape and geometry (2-layer: gel + rubber).

    SimNIBS models the electrode–skin interface as two stacked layers:
      [TOP]  Silicone rubber  (rubber_thickness)
             Saline gel       (gel_thickness)
      [SKIN] ── head surface ──

    Attributes:
        shape (str): Electrode shape — "ellipse" or "rect".
        dimensions (List[float]): [x, y] size in mm (diameters for ellipse,
            sides for rect).
        gel_thickness (float): Saline gel layer thickness in mm. Defaults to 4.0.
        rubber_thickness (float): Silicone rubber layer thickness in mm.
            Defaults to 2.0.
    """

    shape: str = "ellipse"
    dimensions: List[float] = field(default_factory=lambda: [8.0, 8.0])
    gel_thickness: float = 4.0
    rubber_thickness: float = 2.0


@dataclass
class IntensityConfig:
    """Per-pair current intensities in mA. Supports N pairs (any even count)."""

    values: List[float] = field(default_factory=lambda: [1.0, 1.0])

    @classmethod
    def from_string(cls, s: str) -> "IntensityConfig":
        v = [float(x.strip()) for x in s.split(",")]
        n = len(v)
        if n == 1:
            return cls(values=[v[0], v[0]])
        if n >= 2 and n % 2 == 0:
            return cls(values=v)
        raise ValueError(
            f"Invalid intensity format: expected 1 or an even number of values; got {n}: {s!r}"
        )

    # Backward-compat properties for code that accesses pair1–pair4 directly.
    @property
    def pair1(self) -> float:
        return self.values[0] if len(self.values) > 0 else 1.0

    @property
    def pair2(self) -> float:
        return self.values[1] if len(self.values) > 1 else 1.0

    @property
    def pair3(self) -> float:
        return self.values[2] if len(self.values) > 2 else 1.0

    @property
    def pair4(self) -> float:
        return self.values[3] if len(self.values) > 3 else 1.0


@dataclass
class LabelMontage:
    """Montage defined by EEG cap electrode labels (e.g. 'Cz', 'E1')."""

    name: str
    electrode_pairs: List[Tuple[str, str]]
    eeg_net: str
    is_xyz: bool = field(default=False, init=False, repr=False)

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


@dataclass
class XYZMontage:
    """Montage defined by 3-D coordinates in mm (freehand / flex-optimized)."""

    name: str
    electrode_pairs: List[Tuple[List[float], List[float]]]
    eeg_net: Optional[str] = None
    is_xyz: bool = field(default=True, init=False, repr=False)

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


# Union alias — use for type annotations; instantiate LabelMontage or XYZMontage directly.
MontageConfig = Union[LabelMontage, XYZMontage]


@dataclass
class SimulationConfig:
    subject_id: str
    project_dir: str
    conductivity_type: ConductivityType
    intensities: IntensityConfig
    electrode: ElectrodeConfig
    mti_field_method: MTIFieldMethod = MTIFieldMethod.RECURSIVE_TI
    direct_field_pair_polarity: str = "first_positive_second_negative"
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
