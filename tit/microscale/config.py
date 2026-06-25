#!/usr/bin/env simnibs_python
"""Configuration dataclasses and literature constants for microscale coupling.

Defines the typed configs consumed by :mod:`tit.microscale`:

* :class:`PopulationConfig` -- parameters for the headline polarization-map
  pipeline (:func:`tit.microscale.population.run_population`).
* :class:`RegionSpec` -- a cortical region (atlas label / sphere / mask) to
  populate for the optional populated-gyrus figure.
* :class:`NeuronModelSpec` -- describes a neuron model registered in
  :mod:`tit.microscale.models`.
* :class:`MicroscaleConfig` -- the *experimental* single-cell demonstrator
  config (kept for the fenced, library-only spike/threshold functions).

Plus the literature constants the pipeline and docs report against:
:data:`DEFAULT_COUPLING_MV_PER_VM`, :data:`LFS_THRESHOLD_VM`,
:data:`KHZ_TIS_THRESHOLD_VM`, :data:`CONDUCTION_BLOCK_VM`.

See Also
--------
tit.microscale.population : Consumes :class:`PopulationConfig` / :class:`RegionSpec`.
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

#: First-order somatic polarization coupling for an L5 pyramidal neuron, in mV
#: per (V/m), under a field aligned with the somatodendritic axis.  This is the
#: single representative regular-spiking L5 cell of Radman et al. 2009 (Brain
#: Stimul 2:215, Fig. 1C), measured at near-optimal orientation -- it is NOT a
#: population mean.  Across 51 cortical cells Radman et al. report a polarization
#: length spanning roughly -0.29 to +0.49 mm (== mV/(V/m)); Bikson et al. 2004
#: (J Physiol 557:175) measured 0.12 for hippocampal CA1.  Treat 0.27 as a
#: central estimate within a ~0.1-0.5 range, not a hard constant.
DEFAULT_COUPLING_MV_PER_VM: float = 0.27

#: Single-cell activation / block thresholds for an L5 pyramidal neuron under a
#: *uniform total* E-field, reported by Wang et al. 2022 (J Neural Eng 19:066047)
#: in V/m.  Provided as honest context: scalp-realistic human TI envelope fields
#: at depth (~0.1-0.6 V/m; Rampersad et al. 2019) are two-to-three orders of
#: magnitude below these, so this tool reports *subthreshold polarization*, not
#: predicted firing.  The only suprathreshold single-cell regime (block) needs
#: fields that cannot be delivered through the scalp.
LFS_THRESHOLD_VM: tuple[float, float] = (16.9, 47.4)  # 10 Hz low-freq sinusoid
KHZ_TIS_THRESHOLD_VM: tuple[float, float] = (75.0, 230.0)  # kHz / TIS / AM-HFS
CONDUCTION_BLOCK_VM: float = 1700.0  # TIS conduction block (some orientations)


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
    """Parameters for the *single-cell* demonstrator (experimental).

    .. warning::

       This drives a single neuron at explicit target coordinates with the kHz
       carriers and is intended for **qualitative exploration only**.  The
       built-in cells use NEURON's vanilla Hodgkin-Huxley channels, which Wang
       et al. 2022 show are "ill suited" to kHz transcranial stimulation, so the
       absolute spike counts and firing thresholds it produces are *not*
       quantitatively faithful.  For the robust, literature-grounded analysis
       use the population polarization map (:class:`PopulationConfig` /
       :func:`tit.microscale.population.run_population`).  For trustworthy
       single-cell thresholds, register a validated multi-channel cortical cell
       (e.g. a Hay et al. 2011 / Aberra et al. 2018 model) via
       :func:`tit.microscale.models.register_model`.

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
    activation-threshold questions (Aberra et al. 2018; Aberra et al. 2020;
    Seo & Jun 2017; Shirinpour et al. 2021).  The population is the cross product
    of *clones*, *azimuthal rotations*, and *cluster sites*.

    The central estimate is the cheap analytic somatic polarization
    ``ΔVm = polarization_coupling * E_normal`` (Radman et al. 2009; Bikson et al.
    2004), computed over *all* cluster vertices.  NEURON solves a modest
    *subsample* only to characterize the distribution (morphology, dendritic vs
    somatic poles, orientation spread) -- it does not move the analytic estimate.

    **Scope.** An unconnected population is the accepted standard for *direct*
    subthreshold polarization and activation thresholds, but it cannot model
    network-level effects -- oscillation entrainment, recruitment, or the
    TI-selectivity mechanism that depends on network time constants
    (Esmaeilpour et al. 2021).  The map answers "how strongly, and in what sign,
    does this montage polarize cortical neurons", not "will it evoke spikes".

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
        Defaults to :data:`DEFAULT_COUPLING_MV_PER_VM` (0.27 for an L5 pyramidal
        soma at optimal orientation; Radman et al. 2009).  See that constant for
        the defensible range and caveats.
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
    render_population : bool
        Also emit the standalone populated-cortex figure (L5 cells embedded in
        the cortical patch at the field focus).  Default ``True``.
    render_video : bool
        Also emit the time-domain animation at the field focus (the neuron
        colored by the instantaneous applied quasipotential, the rotating TI
        field vector, and the oscillation/beat trace).  Reads the two HF pair
        meshes; best-effort.  Default ``True``.
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
    polarization_coupling: float = DEFAULT_COUPLING_MV_PER_VM
    carrier_freqs: tuple[float, float] = field(default_factory=lambda: DEFAULT_CARRIERS)
    duration: float = 100.0
    dt: float = 0.005
    temperature: float = 37.0
    cpus: int = 1
    seed: int = 0
    render_population: bool = True
    render_video: bool = True
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


#: Region kinds accepted by :class:`RegionSpec`.
VALID_REGION_KINDS: tuple[str, ...] = ("atlas", "sphere", "mask")
#: Anatomical spaces a region can be defined/rendered in.
VALID_REGION_SPACES: tuple[str, ...] = ("subject", "fsaverage")


@dataclass(frozen=True)
class RegionSpec:
    """A cortical region to populate with L5 pyramidal neurons.

    Regions are always restricted to the **gray-matter cortical surface** and
    defined one of three ways (``kind``):

    * ``"atlas"`` -- vertices in a named atlas label (``atlas`` + ``label``,
      optional ``hemi``).  Atlases: ``"DK40"``, ``"a2009s"``, ``"HCP_MMP1"``.
    * ``"sphere"`` -- GM vertices within ``radius_mm`` of a center given in MNI
      (``center_mni``) or subject (``center_subject``) coordinates.
    * ``"mask"`` -- GM vertices inside a binary NIfTI mask (``mask_path``).

    ``space`` selects ``"subject"`` or ``"fsaverage"`` for both selection and
    rendering.
    """

    kind: str
    space: str = "subject"
    # atlas
    atlas: str = "DK40"
    label: str = ""
    hemi: str = "both"
    # sphere
    center_mni: tuple | None = None
    center_subject: tuple | None = None
    radius_mm: float = 10.0
    # mask
    mask_path: str | None = None
    # atlas->surface nearest-neighbour snap tolerance (subject space)
    snap_mm: float = 2.0

    def __post_init__(self) -> None:
        if self.kind not in VALID_REGION_KINDS:
            raise ValueError(
                f"kind must be one of {VALID_REGION_KINDS}, got {self.kind!r}"
            )
        if self.space not in VALID_REGION_SPACES:
            raise ValueError(
                f"space must be one of {VALID_REGION_SPACES}, got {self.space!r}"
            )
        if self.hemi not in ("lh", "rh", "both"):
            raise ValueError(f"hemi must be lh/rh/both, got {self.hemi!r}")
        if self.kind == "atlas" and not self.label:
            raise ValueError("atlas region requires a non-empty label")
        if self.kind == "sphere":
            center = (
                self.center_mni if self.center_mni is not None else self.center_subject
            )
            if center is None:
                raise ValueError("sphere region requires center_mni or center_subject")
            if len(center) != 3:
                raise ValueError(f"sphere center must be (x, y, z), got {center!r}")
            if self.radius_mm <= 0:
                raise ValueError(f"radius_mm must be > 0, got {self.radius_mm}")
        if self.kind == "mask" and not self.mask_path:
            raise ValueError("mask region requires mask_path")
        if self.snap_mm <= 0:
            raise ValueError(f"snap_mm must be > 0, got {self.snap_mm}")

    @property
    def label_text(self) -> str:
        """Short human-readable description for figure annotation."""
        if self.kind == "atlas":
            return f"{self.atlas}:{self.label} ({self.hemi})"
        if self.kind == "sphere":
            c = self.center_mni if self.center_mni is not None else self.center_subject
            sp = "MNI" if self.center_mni is not None else "subject"
            return f"sphere r={self.radius_mm:g} mm @ {sp} {tuple(c)}"
        import os

        return f"mask {os.path.basename(self.mask_path)}"
