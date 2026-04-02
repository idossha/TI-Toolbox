#!/usr/bin/env simnibs_python
"""Configuration dataclasses for TI/mTI simulations.

Defines the primary configuration types consumed by
:func:`tit.sim.run_simulation`:

* :class:`SimulationConfig` -- full run parameters (subject, conductivity,
  electrode geometry, mapping flags).
* :class:`Montage` -- a named electrode montage with pair definitions.
* :class:`SimulationMode` -- enum distinguishing TI from mTI.
* :func:`parse_intensities` -- helper to parse intensity strings from
  the CLI or GUI.

See Also
--------
tit.sim.utils.run_simulation : Consumes ``SimulationConfig`` to drive
    the simulation pipeline.
tit.sim.base.BaseSimulation : Uses ``SimulationConfig`` and ``Montage``
    at runtime.
"""

from dataclasses import dataclass, field
from enum import Enum


class SimulationMode(Enum):
    """Simulation type: standard two-pair TI or multi-channel mTI.

    Attributes
    ----------
    TI : str
        Standard 2-pair temporal interference.
    MTI : str
        Multi-channel temporal interference (4+ pairs).

    See Also
    --------
    Montage.simulation_mode : Auto-detects mode from pair count.
    """

    TI = "TI"
    MTI = "mTI"


class MontageMode(Enum):
    """How electrode positions are specified.

    ``NET`` and ``FLEX_MAPPED`` use EEG-cap label names resolved against an
    EEG-net CSV.  ``FLEX_FREE`` and ``FREEHAND`` use raw 3-D XYZ
    coordinates (no net required).

    Attributes
    ----------
    NET : str
        Standard EEG-cap electrode labels.
    FLEX_MAPPED : str
        Flex-search result mapped back to EEG-cap labels.
    FLEX_FREE : str
        Flex-search result with free XYZ coordinates.
    FREEHAND : str
        User-specified XYZ coordinates (manual placement).
    """

    NET = "net"
    FLEX_MAPPED = "flex_mapped"
    FLEX_FREE = "flex_free"
    FREEHAND = "freehand"


@dataclass
class Montage:
    """A named electrode montage used in a TI/mTI simulation.

    Wraps the electrode pair definitions for a single montage.  Electrodes
    may be referenced by EEG-cap label names (``NET`` / ``FLEX_MAPPED``
    modes) or by 3-D XYZ coordinates (``FLEX_FREE`` / ``FREEHAND`` modes).

    The simulation type is auto-detected from the number of electrode
    pairs: 2 pairs = standard TI, 4+ pairs = multi-channel mTI.

    Attributes
    ----------
    name : str
        Human-readable montage name (e.g. ``"M1_left"``).
    mode : MontageMode
        How electrode positions are specified.  See :class:`MontageMode`.
    electrode_pairs : list[tuple]
        List of electrode pairs.  Each element is a tuple of two electrode
        identifiers (label strings or XYZ coordinate lists).
    eeg_net : str or None
        Filename of the EEG-net CSV (e.g. ``"GSN-HydroCel-185.csv"``).
        Required for ``NET`` and ``FLEX_MAPPED`` modes, ignored otherwise.

    See Also
    --------
    SimulationConfig : Holds one or more ``Montage`` instances.
    load_montages : Build ``Montage`` objects from ``montage_list.json``.
    """

    Mode = MontageMode

    name: str
    mode: MontageMode
    electrode_pairs: list[tuple]
    eeg_net: str | None = None

    @property
    def is_xyz(self) -> bool:
        """Whether electrodes are specified as 3-D XYZ coordinates.

        Returns
        -------
        bool
            ``True`` for ``FLEX_FREE`` and ``FREEHAND`` modes.
        """
        return self.mode in (MontageMode.FLEX_FREE, MontageMode.FREEHAND)

    @property
    def simulation_mode(self) -> SimulationMode:
        """Infer TI vs mTI from the number of electrode pairs.

        Returns
        -------
        SimulationMode
            ``SimulationMode.TI`` for 2 pairs, ``SimulationMode.MTI``
            for 4 or more pairs.

        Raises
        ------
        ValueError
            If the pair count is not 2 or >= 4.

        See Also
        --------
        SimulationMode : The returned enum type.
        """
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
        """Number of electrode pairs in this montage.

        Returns
        -------
        int
            Length of :attr:`electrode_pairs`.
        """
        return len(self.electrode_pairs)


_VALID_CONDUCTIVITIES = {"scalar", "vn", "dir", "mc"}


@dataclass
class SimulationConfig:
    """Full configuration for a TI or mTI simulation run.

    Passed to :func:`tit.sim.run_simulation` to execute one or more
    montage simulations for a single subject.  Electrode geometry,
    conductivity model, and output mapping options are all set here.

    Attributes
    ----------
    subject_id : str
        Subject identifier (e.g. ``"sub-001"``).
    montages : list[Montage]
        One or more :class:`Montage` definitions to simulate.
    conductivity : str
        Tissue conductivity model.  One of:

        - ``"scalar"`` -- isotropic scalar conductivities (default).
        - ``"vn"`` -- volume-normalized anisotropic conductivities.
        - ``"dir"`` -- directly-mapped anisotropic conductivities.
        - ``"mc"`` -- mean-conductivity anisotropic conductivities.

        The anisotropic modes (``"vn"``, ``"dir"``, ``"mc"``) require
        DTI tensors registered to the head mesh.
    intensities : list[float]
        Per-pair current intensities in mA.  Length must be 1 (broadcast
        to all pairs) or match the total number of electrode pairs.
        Defaults to ``[1.0, 1.0]``.
    electrode_shape : str
        Electrode shape (``"ellipse"`` or ``"rect"``).
    electrode_dimensions : list[float]
        ``[width, height]`` of each electrode in mm.
    gel_thickness : float
        Conductive-gel layer thickness in mm.
    rubber_thickness : float
        Rubber (silicone) layer thickness in mm.
    map_to_surf : bool
        Map results onto the cortical surface.  Must be ``True`` because
        TI_normal calculation requires surface overlays.
    map_to_vol : bool
        Reserved for NIfTI output (handled externally by
        ``tit.tools.mesh2nii``, not by SimNIBS SESSION).
    map_to_mni : bool
        Reserved; not currently passed to SimNIBS.
    map_to_fsavg : bool
        Reserved; not currently passed to SimNIBS.
    open_in_gmsh : bool
        Open results in Gmsh after simulation.
    tissues_in_niftis : str
        Tissue selection for NIfTI export (``"all"`` or a
        comma-separated list).
    aniso_maxratio : float
        Maximum eigenvalue ratio clamp for anisotropic conductivity
        tensors.
    aniso_maxcond : float
        Maximum absolute conductivity clamp (S/m) for anisotropic
        tensors.

    Raises
    ------
    ValueError
        If *conductivity* is not one of the valid model names.

    See Also
    --------
    Montage : Electrode montage contained in ``montages``.
    run_simulation : Entry point that consumes this config.
    parse_intensities : Helper to build the ``intensities`` list.
    """

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
    """Parse a comma-separated intensity string into a list of floats.

    A single value is duplicated to form a pair (``"2.0"`` becomes
    ``[2.0, 2.0]``).  Otherwise the value count must be even so that
    each electrode pair receives two intensities.

    Parameters
    ----------
    s : str
        Comma-separated intensity values (e.g. ``"1.0,2.0"``).

    Returns
    -------
    list[float]
        List of floats with an even number of elements.

    Raises
    ------
    ValueError
        If the number of values is odd and greater than 1.

    See Also
    --------
    SimulationConfig.intensities : Field populated by this function.
    """
    v = [float(x.strip()) for x in s.split(",")]
    n = len(v)
    if n == 1:
        return [v[0], v[0]]
    if n >= 2 and n % 2 == 0:
        return v
    raise ValueError(
        f"Invalid intensity format: expected 1 or an even number of values; got {n}: {s!r}"
    )
