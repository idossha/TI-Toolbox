#!/usr/bin/env simnibs_python
"""
Configuration dataclasses for TI simulations.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Union


class SimulationMode(Enum):
    """Simulation mode enumeration."""

    TI = "TI"  # 2-pair temporal interference
    MTI = "mTI"  # 4-pair multipolar temporal interference


class ConductivityType(Enum):
    """SimNIBS conductivity type enumeration."""

    SCALAR = "scalar"  # Isotropic conductivity
    VN = "vn"  # Volume normalized
    DIR = "dir"  # Direct mapping (uses DTI tensor)
    MC = "mc"  # Monte Carlo


@dataclass
class ElectrodeConfig:
    """Configuration for electrode properties."""

    shape: str = "ellipse"  # "ellipse" or "rect"
    dimensions: List[float] = field(
        default_factory=lambda: [8.0, 8.0]
    )  # [x_dim, y_dim] in mm
    thickness: float = 4.0  # Gel thickness in mm
    sponge_thickness: float = 2.0  # Sponge thickness in mm


@dataclass
class IntensityConfig:
    """
    Configuration for current intensities in TI simulations.

    Each pair requires one intensity value (in mA). SimNIBS automatically
    applies equal and opposite currents to the two electrodes in each pair.
    For example: pair1=2.0 means electrode1=+2.0mA and electrode2=-2.0mA

    TI mode (2 pairs): Uses pair1 and pair2
    mTI mode (4 pairs): Uses pair1, pair2, pair3, and pair4
    """

    pair1: float = 1.0  # mA - intensity for first electrode pair
    pair2: float = 1.0  # mA - intensity for second electrode pair
    pair3: float = 1.0  # mA - intensity for third electrode pair (mTI only)
    pair4: float = 1.0  # mA - intensity for fourth electrode pair (mTI only)

    @classmethod
    def from_string(cls, intensity_str: str) -> "IntensityConfig":
        """
        Parse intensity from string format.

        Formats:
        - "2.0" -> all pairs: 2.0 mA
        - "2.0,1.5" -> pair1: 2.0, pair2: 1.5 (both set to 1.0 for pair3/pair4)
        - "2.0,1.5,1.0,0.5" -> pair1: 2.0, pair2: 1.5, pair3: 1.0, pair4: 0.5

        Args:
            intensity_str: Comma-separated intensity values

        Returns:
            IntensityConfig object
        """
        intensities = [float(x.strip()) for x in intensity_str.split(",")]

        if len(intensities) == 1:
            # Single value: use for all pairs
            val = intensities[0]
            return cls(val, val, val, val)
        elif len(intensities) == 2:
            # Two values: pair1, pair2 (TI mode)
            return cls(intensities[0], intensities[1], 1.0, 1.0)
        elif len(intensities) == 4:
            # Four values: all pairs specified (mTI mode)
            return cls(*intensities)
        else:
            raise ValueError(
                f"Invalid intensity format: {intensity_str}. "
                f"Expected 1, 2, or 4 comma-separated values."
            )


@dataclass
class MontageConfig:
    """Configuration for a single montage."""

    name: str
    electrode_pairs: List[Tuple[Union[str, List[float]], Union[str, List[float]]]]
    is_xyz: bool = (
        False  # True if positions are XYZ coordinates, False if electrode names
    )
    eeg_net: Optional[str] = None  # Override EEG net (for flex montages)

    @property
    def simulation_mode(self) -> SimulationMode:
        """Determine simulation mode based on number of electrode pairs."""
        if len(self.electrode_pairs) == 2:
            return SimulationMode.TI
        elif len(self.electrode_pairs) >= 4:
            return SimulationMode.MTI
        else:
            raise ValueError(
                f"Invalid number of electrode pairs: {len(self.electrode_pairs)}"
            )

    @property
    def num_pairs(self) -> int:
        """Get number of electrode pairs."""
        return len(self.electrode_pairs)


@dataclass
class ParallelConfig:
    """Configuration for parallel simulation execution."""

    enabled: bool = False
    max_workers: int = 0  # 0 = auto-detect (uses cpu_count // 2)

    def __post_init__(self):
        """Set max_workers to sensible default if auto-detect."""
        if self.max_workers <= 0:
            # Use half of available CPUs (simulations are memory-intensive)
            cpu_count = os.cpu_count() or 4
            # Limit to max 4 workers by default (memory constraint)
            self.max_workers = min(4, max(1, cpu_count // 2))

    @property
    def effective_workers(self) -> int:
        """Get the effective number of workers."""
        return self.max_workers

    def get_memory_warning(self) -> Optional[str]:
        """Return memory warning if parallel execution may cause issues."""
        if not self.enabled:
            return None
        if self.max_workers > 2:
            return (
                f"⚠️ Running {self.max_workers} parallel simulations may require "
                f"significant memory (~4-8 GB per simulation). Consider reducing "
                f"workers if you experience memory issues."
            )
        return None


@dataclass
class SimulationConfig:
    """Main configuration for TI simulation."""

    subject_id: str
    project_dir: str
    conductivity_type: ConductivityType
    intensities: IntensityConfig
    electrode: ElectrodeConfig
    eeg_net: str = "GSN-HydroCel-185.csv"
    map_to_surf: bool = True
    map_to_vol: bool = True
    map_to_mni: bool = True
    map_to_fsavg: bool = False
    tissues_in_niftis: str = "all"
    open_in_gmsh: bool = False
    parallel: ParallelConfig = field(default_factory=ParallelConfig)

    def __post_init__(self):
        """Convert string conductivity type to enum if needed."""
        if isinstance(self.conductivity_type, str):
            self.conductivity_type = ConductivityType(self.conductivity_type)
        if isinstance(self.parallel, dict):
            self.parallel = ParallelConfig(**self.parallel)
