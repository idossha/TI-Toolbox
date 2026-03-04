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


@dataclass
class ElectrodeConfig:
    shape: str = "ellipse"
    dimensions: List[float] = field(default_factory=lambda: [8.0, 8.0])
    thickness: float = 4.0
    sponge_thickness: float = 2.0


@dataclass
class IntensityConfig:
    """Per-pair current intensities in mA. TI uses pair1+pair2; mTI uses all four."""

    pair1: float = 1.0
    pair2: float = 1.0
    pair3: float = 1.0
    pair4: float = 1.0

    @classmethod
    def from_string(cls, s: str) -> "IntensityConfig":
        v = [float(x.strip()) for x in s.split(",")]
        if len(v) == 1:
            return cls(v[0], v[0], v[0], v[0])
        if len(v) == 2:
            return cls(v[0], v[1], 1.0, 1.0)
        if len(v) == 4:
            return cls(*v)
        raise ValueError(f"Expected 1, 2, or 4 intensity values; got: {s!r}")


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
        raise ValueError(f"Invalid number of electrode pairs: {n}. Expected 2 (TI) or 4+ (mTI).")

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
        raise ValueError(f"Invalid number of electrode pairs: {n}. Expected 2 (TI) or 4+ (mTI).")

    @property
    def num_pairs(self) -> int:
        return len(self.electrode_pairs)


# Union alias — use for type annotations; instantiate LabelMontage or XYZMontage directly.
MontageConfig = Union[LabelMontage, XYZMontage]


@dataclass
class ParallelConfig:
    enabled: bool = False
    max_workers: int = 0

    def __post_init__(self):
        if self.max_workers <= 0:
            self.max_workers = min(4, max(1, (os.cpu_count() or 4) // 2))

    @property
    def effective_workers(self) -> int:
        return self.max_workers


@dataclass
class SimulationConfig:
    subject_id: str
    project_dir: str
    conductivity_type: ConductivityType
    intensities: IntensityConfig
    electrode: ElectrodeConfig
    map_to_surf: bool = True
    map_to_vol: bool = True
    map_to_mni: bool = True
    map_to_fsavg: bool = False
    tissues_in_niftis: str = "all"
    open_in_gmsh: bool = False
    parallel: ParallelConfig = field(default_factory=ParallelConfig)

    def __post_init__(self):
        if isinstance(self.conductivity_type, str):
            self.conductivity_type = ConductivityType(self.conductivity_type)
        if isinstance(self.parallel, dict):
            self.parallel = ParallelConfig(**self.parallel)
