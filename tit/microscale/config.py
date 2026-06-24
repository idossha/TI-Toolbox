#!/usr/bin/env simnibs_python
"""Configuration dataclasses for microscale (field -> neuron) coupling.

Defines the typed configs consumed by :mod:`tit.microscale`:

* :class:`NeuronModelSpec` -- describes a vendored multicompartment neuron
  model (morphology + mechanisms) registered in
  :mod:`tit.microscale.models`.
* :class:`MicroscaleConfig` -- parameters for driving neuron models with a
  simulation's TI/mTI field (targets, carrier frequencies, integration step,
  duration).

See Also
--------
tit.microscale.coupling : Consumes :class:`MicroscaleConfig`.
tit.microscale.models : Registry of :class:`NeuronModelSpec`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Default kHz carrier pair for temporal interference (Hz).  The difference
#: (here 10 Hz) is the envelope/beat frequency the neuron is expected to track.
DEFAULT_CARRIERS: tuple[float, float] = (2000.0, 2010.0)

#: Minimum carrier-period-to-timestep ratio enforced by validation.  The kHz
#: carriers must be sampled finely enough to integrate; ``dt`` is rejected if it
#: exceeds ``carrier_period / MIN_STEPS_PER_PERIOD``.
MIN_STEPS_PER_PERIOD: int = 10


@dataclass(frozen=True)
class NeuronModelSpec:
    """Description of a vendored multicompartment neuron model.

    Attributes
    ----------
    name : str
        Registry key (e.g. ``"ball_stick"``).
    description : str
        Human-readable summary.
    morphology : str
        Filename of the morphology asset (``.hoc``/``.swc``) relative to the
        model's package directory, or ``""`` for models built procedurally in
        Python.
    mechanisms : tuple of str
        ``.mod`` mechanism directory names that must be compiled for this model.
    has_active_channels : bool
        Whether the model carries voltage-gated channels.  Temporal-interference
        demodulation requires active channels (Mirzakhalili et al. 2020), so
        models with ``False`` here are rejected for TI runs.
    license : str
        SPDX identifier of the asset's upstream license (must be permissive,
        e.g. ``"MIT"`` or ``"Apache-2.0"``).
    """

    name: str
    description: str = ""
    morphology: str = ""
    mechanisms: tuple[str, ...] = ()
    has_active_channels: bool = True
    license: str = ""


@dataclass(frozen=True)
class MicroscaleConfig:
    """Parameters for driving neuron models with a simulation's TI field.

    Attributes
    ----------
    sim_name : str
        Name of the completed simulation whose field drives the neurons.  Used
        to locate the TI mesh and the two high-frequency pair meshes via
        :class:`~tit.paths.PathManager`.
    model : str
        Registry key of the :class:`NeuronModelSpec` to place at each target.
    targets : tuple of (float, float, float)
        Target coordinates in **mm**, SimNIBS subject space, where each neuron's
        soma is placed.  May be empty when targets are sampled from an ROI at
        run time.
    conductivity : str
        Conductivity tag in the HF mesh filenames (``{sid}_TDCS_1_{cond}.msh``).
    carrier_freqs : tuple of (float, float)
        The two kHz carrier frequencies in Hz.  Their difference is the envelope
        frequency.  Equal frequencies disable the beat (used as a control).
    duration : float
        Simulated duration in ms.
    dt : float
        Integration timestep in ms.  Must resolve the carriers (see
        :data:`MIN_STEPS_PER_PERIOD`).
    temperature : float
        Simulation temperature in degrees C (NEURON ``celsius``).
    amplitude_scale : float
        Global multiplier applied to the sampled field before driving the cell.
        ``threshold`` mode bisects on this value.
    cpus : int
        Number of targets simulated in parallel (1 = serial).
    overwrite : bool
        Recompute even when a cached result exists.
    """

    sim_name: str
    model: str = "l5_pyramidal"
    targets: tuple[tuple[float, float, float], ...] = ()
    conductivity: str = "scalar"
    carrier_freqs: tuple[float, float] = field(default_factory=lambda: DEFAULT_CARRIERS)
    duration: float = 100.0
    dt: float = 0.005
    temperature: float = 37.0
    amplitude_scale: float = 1.0
    cpus: int = 1
    overwrite: bool = False

    def __post_init__(self) -> None:
        if not self.sim_name:
            raise ValueError("sim_name is required.")
        if len(self.carrier_freqs) != 2:
            raise ValueError(
                f"carrier_freqs must be a (f1, f2) pair, got {self.carrier_freqs!r}"
            )
        f1, f2 = self.carrier_freqs
        if f1 <= 0 or f2 <= 0:
            raise ValueError(f"carrier frequencies must be positive, got {(f1, f2)!r}")
        if self.duration <= 0:
            raise ValueError(f"duration must be positive, got {self.duration}")
        if self.dt <= 0:
            raise ValueError(f"dt must be positive, got {self.dt}")
        # The carriers are in Hz (cycles/s); a period in ms is 1000 / f.  Reject
        # a timestep that under-samples the faster carrier.
        fastest = max(f1, f2)
        min_period_ms = 1000.0 / fastest
        max_dt = min_period_ms / MIN_STEPS_PER_PERIOD
        if self.dt > max_dt:
            raise ValueError(
                f"dt={self.dt} ms is too coarse for a {fastest:g} Hz carrier; "
                f"need dt <= {max_dt:g} ms ({MIN_STEPS_PER_PERIOD} steps/period)."
            )
        for t in self.targets:
            if len(t) != 3:
                raise ValueError(f"each target must be (x, y, z) mm, got {t!r}")

    @property
    def envelope_freq(self) -> float:
        """Beat/envelope frequency in Hz (``|f1 - f2|``)."""
        f1, f2 = self.carrier_freqs
        return abs(f1 - f2)


def _validate_carriers_dt(
    carrier_freqs: tuple[float, float], duration: float, dt: float
) -> None:
    """Shared carrier/dt/Nyquist validation (see :class:`MicroscaleConfig`)."""
    if len(carrier_freqs) != 2:
        raise ValueError(
            f"carrier_freqs must be a (f1, f2) pair, got {carrier_freqs!r}"
        )
    f1, f2 = carrier_freqs
    if f1 <= 0 or f2 <= 0:
        raise ValueError(f"carrier frequencies must be positive, got {(f1, f2)!r}")
    if duration <= 0:
        raise ValueError(f"duration must be positive, got {duration}")
    if dt <= 0:
        raise ValueError(f"dt must be positive, got {dt}")
    fastest = max(f1, f2)
    min_period_ms = 1000.0 / fastest
    max_dt = min_period_ms / MIN_STEPS_PER_PERIOD
    if dt > max_dt:
        raise ValueError(
            f"dt={dt} ms is too coarse for a {fastest:g} Hz carrier; "
            f"need dt <= {max_dt:g} ms ({MIN_STEPS_PER_PERIOD} steps/period)."
        )


@dataclass(frozen=True)
class PopulationConfig:
    """Parameters for a population of unconnected morphologically-realistic cells.

    Simulates a CLUSTER/POPULATION of independent neurons (no synaptic
    connectivity) -- the standard approach for subthreshold-polarization and
    activation-threshold questions (Aberra et al. 2018, 2020; Seo & Jun 2017;
    Shirinpour et al. 2021).  The population is the cross product of *clones*,
    *azimuthal rotations*, and *cluster sites*.

    The central estimate is the cheap analytic somatic polarization
    ``ΔVm = polarization_coupling * E_normal`` (Radman et al. 2009; Bikson et al.
    2004), computed over *all* cluster vertices.  NEURON solves a modest
    *subsample* only to characterize the distribution (morphology, dendritic vs
    somatic poles, orientation spread) -- it does not move the analytic estimate.

    Attributes
    ----------
    sim_name : str
        Name of the completed simulation whose field drives the population.
    model : str
        Registry key of the :class:`NeuronModelSpec` to clone.
    conductivity : str
        Conductivity tag in the HF pair-mesh filenames.
    n_clones : int
        Number of morphological clones (distinct seeds) per cluster site.
    n_azimuth : int
        Number of azimuthal rotations about the surface normal per clone.
    cluster_normal_field : str
        Name of the normal-component field on the central surface that defines
        the analytic map and the cluster threshold (e.g. ``"TI_normal"``).
    cluster_threshold : float or None
        Keep cluster vertices whose ``cluster_normal_field`` >= this value.
        ``None`` keeps the whole surface.
    n_subsample : int
        Number of cluster vertices solved with NEURON (0 = analytic only).
    polarization_coupling : float
        First-order somatic coupling in mV per (V/m), used for the analytic map.
        Default 0.27 for L5 pyramidal somata (Radman et al. 2009).
    carrier_freqs : tuple of (float, float)
        The two kHz carrier frequencies in Hz.
    duration : float
        Simulated duration in ms.
    dt : float
        Integration timestep in ms (must resolve the carriers).
    temperature : float
        Simulation temperature in degrees C (NEURON ``celsius``).
    cpus : int
        Number of parallel workers (1 = serial).
    seed : int
        Base seed; clone ``c`` uses ``seed + c``.
    overwrite : bool
        Recompute even when a cached result exists.
    """

    sim_name: str
    model: str = "l5_pyramidal"
    conductivity: str = "scalar"
    n_clones: int = 5
    n_azimuth: int = 6
    cluster_normal_field: str = "TI_normal"
    cluster_threshold: float | None = None
    n_subsample: int = 50
    polarization_coupling: float = 0.27
    carrier_freqs: tuple[float, float] = field(default_factory=lambda: DEFAULT_CARRIERS)
    duration: float = 100.0
    dt: float = 0.005
    temperature: float = 37.0
    cpus: int = 1
    seed: int = 0
    overwrite: bool = False

    def __post_init__(self) -> None:
        if not self.sim_name:
            raise ValueError("sim_name is required.")
        _validate_carriers_dt(self.carrier_freqs, self.duration, self.dt)
        if self.n_clones < 1:
            raise ValueError(f"n_clones must be >= 1, got {self.n_clones}")
        if self.n_azimuth < 1:
            raise ValueError(f"n_azimuth must be >= 1, got {self.n_azimuth}")
        if self.n_subsample < 0:
            raise ValueError(f"n_subsample must be >= 0, got {self.n_subsample}")

    @property
    def envelope_freq(self) -> float:
        """Beat/envelope frequency in Hz (``|f1 - f2|``)."""
        f1, f2 = self.carrier_freqs
        return abs(f1 - f2)
