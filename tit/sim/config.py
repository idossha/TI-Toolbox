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
* :func:`check_electrode_pairs` -- the electrode rules every saved or
  simulated montage meets (pair shape, 2-26 pairs, each electrode its own
  point). ``SimulationConfig`` also refuses two montages with one name and a
  zero or non-finite current on a channel a montage uses.

See Also
--------
tit.sim.utils.run_simulation : Consumes ``SimulationConfig`` to drive
    the simulation pipeline.
tit.sim.base.BaseSimulation : Uses ``SimulationConfig`` and ``Montage``
    at runtime.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from numbers import Real

from tit import constants as const


class SimulationMode(Enum):
    """Simulation type: standard two-channel TI or multi-channel mTI.

    Attributes
    ----------
    TI : str
        Standard two-channel temporal interference.
    MTI : str
        Multi-channel temporal interference (4 or more channels).

    See Also
    --------
    Montage.simulation_mode : Auto-detects mode from the channel count.
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

    Wraps the channel definitions of a single montage: one electrode pair
    per channel, channel k being electrodes Ek+ and Ek-.  Electrodes
    may be referenced by EEG-cap label names (``NET`` / ``FLEX_MAPPED``
    modes) or by 3-D XYZ coordinates (``FLEX_FREE`` / ``FREEHAND`` modes).

    The simulation type is auto-detected from the number of channels:
    2 channels = standard TI, 4 or more (even) = multi-channel mTI.

    Attributes
    ----------
    name : str
        Human-readable montage name (e.g. ``"M1_left"``).
    mode : MontageMode
        How electrode positions are specified.  See :class:`MontageMode`.
    electrode_pairs : list[tuple]
        One entry per channel, in channel order.  Each element is a tuple of
        two electrode identifiers (label strings or XYZ coordinate lists),
        ``(Ek+, Ek-)``.
    eeg_net : str or None
        Filename of the EEG-net CSV (e.g. ``"GSN-HydroCel-185.csv"``).
        Required for ``NET`` and ``FLEX_MAPPED`` modes, ignored otherwise.
    display_name : str or None
        Optional user-facing label.  ``name`` remains the storage and lookup key.
    electrode_poses : list[list[list[float]]] or None
        Optional full 4x4 homogeneous pose (row-major) per electrode, one
        per XYZ position in ``electrode_pairs`` order.  Only meaningful for
        XYZ modes; preserves rectangular-electrode orientation when a
        flex-search candidate is replayed.  ``None`` (default) lets SimNIBS
        orient the electrodes itself.
    provenance : dict[str, str] or None
        Free-form origin metadata (e.g. ``{"head_mesh_sha256": ...}``)
        checked by :func:`run_simulation` when present.

    Raises
    ------
    ValueError
        If *electrode_poses* is given for a label-based montage, does not
        contain exactly one 4x4 right-handed homogeneous transform per
        electrode, or its translations do not match ``electrode_pairs``.

    Examples
    --------
    >>> from tit.sim import Montage, MontageMode
    >>> m = Montage(
    ...     name="L_Insula",
    ...     mode=MontageMode.NET,
    ...     electrode_pairs=[("E010", "E011"), ("E012", "E013")],
    ...     eeg_net="GSN-HydroCel-185.csv",
    ... )
    >>> m.num_pairs, m.simulation_mode.value, m.is_xyz
    (2, 'TI', False)

    A free-hand montage uses subject-space millimetre coordinates and no net:

    >>> free = Montage(
    ...     name="custom",
    ...     mode=MontageMode.FREEHAND,
    ...     electrode_pairs=[([-60.0, 10.0, 40.0], [60.0, 10.0, 40.0]),
    ...                      ([-60.0, -40.0, 40.0], [60.0, -40.0, 40.0])],
    ... )
    >>> free.is_xyz
    True

    See Also
    --------
    SimulationConfig : Holds one or more ``Montage`` instances.
    load_montages : Build ``Montage`` objects from ``montage_list.json``.
    """

    Mode = MontageMode

    name: str
    mode: MontageMode
    electrode_pairs: list[tuple[str | list[float], str | list[float]]]
    eeg_net: str | None = None
    display_name: str | None = None
    # Full subject-space poses preserve rectangular-electrode orientation on candidate replay.
    electrode_poses: list[list[list[float]]] | None = None
    provenance: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.electrode_poses is None:
            return
        positions = [position for pair in self.electrode_pairs for position in pair]
        if (
            not self.is_xyz
            or not isinstance(self.electrode_poses, (list, tuple))
            or len(self.electrode_poses) != len(positions)
        ):
            raise ValueError("Electrode poses require one pose per XYZ electrode.")
        for pose, position in zip(self.electrode_poses, positions):
            if (
                not isinstance(pose, (list, tuple))
                or len(pose) != 4
                or any(
                    not isinstance(row, (list, tuple)) or len(row) != 4 for row in pose
                )
            ):
                raise ValueError("Each electrode pose must be a 4x4 matrix.")
            if not all(
                isinstance(value, Real)
                and not isinstance(value, bool)
                and math.isfinite(value)
                for row in pose
                for value in row
            ):
                raise ValueError("Electrode poses must be finite.")
            if list(pose[3]) != [0, 0, 0, 1]:
                raise ValueError("Electrode poses must be homogeneous transforms.")
            if not isinstance(position, (list, tuple)) or len(position) != 3:
                raise ValueError("Electrode poses require XYZ positions.")
            if not all(
                isinstance(value, Real)
                and not isinstance(value, bool)
                and math.isfinite(value)
                for value in position
            ):
                raise ValueError("Electrode positions must be finite XYZ coordinates.")
            if any(abs(pose[i][3] - position[i]) > 1e-9 for i in range(3)):
                raise ValueError(
                    "Electrode pose centres must match the montage positions."
                )
            for column in range(3):
                if abs(sum(pose[i][column] ** 2 for i in range(3)) - 1) > 1e-5:
                    raise ValueError("Electrode pose axes must be unit vectors.")
            for left, right in ((0, 1), (0, 2), (1, 2)):
                if abs(sum(pose[i][left] * pose[i][right] for i in range(3))) > 1e-5:
                    raise ValueError("Electrode pose axes must be orthogonal.")
            determinant = (
                pose[0][0] * (pose[1][1] * pose[2][2] - pose[1][2] * pose[2][1])
                - pose[0][1] * (pose[1][0] * pose[2][2] - pose[1][2] * pose[2][0])
                + pose[0][2] * (pose[1][0] * pose[2][1] - pose[1][1] * pose[2][0])
            )
            if abs(determinant - 1.0) > 1e-5:
                raise ValueError(
                    "Electrode pose axes must form a right-handed rotation."
                )

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
        """Infer TI vs mTI from the number of channels (electrode pairs).

        Returns
        -------
        SimulationMode
            ``SimulationMode.TI`` for 2 channels, ``SimulationMode.MTI``
            for 4 or more (even).

        Raises
        ------
        ValueError
            If the channel count is not allowed by
            :func:`tit.constants.is_valid_pair_count` -- an even count of at
            least 2.  One channel is tACS, not TI; an odd count leaves a channel
            with nothing to beat against.

        See Also
        --------
        SimulationMode : The returned enum type.
        """
        n = len(self.electrode_pairs)
        if not const.is_valid_pair_count(n):
            raise ValueError(
                f"Invalid number of electrode pairs: {n}. Expected "
                f"{const.PAIR_COUNT_RULE}."
            )
        return (
            SimulationMode.TI if n == const.TI_ELECTRODE_PAIRS else SimulationMode.MTI
        )

    @property
    def num_pairs(self) -> int:
        """Number of channels (electrode pairs) in this montage.

        Returns
        -------
        int
            Length of :attr:`electrode_pairs`.
        """
        return len(self.electrode_pairs)


_VALID_CONDUCTIVITIES = {"scalar", "vn", "dir", "mc"}

#: mTI names its channels A..Z (``tit.sim.mTI``), so a montage holds at most 26 pairs.
MAX_ELECTRODE_PAIRS = 26

#: Two electrodes closer than this are one point: SimNIBS would place both pads on the same
#: patch of scalp. Mirrors the desktop's ``MIN_ELECTRODE_SEPARATION_MM``
#: (``desktop/src/renderer/pages/simulator/types.ts``); real montages measure 11.5-127 mm.
MIN_ELECTRODE_SEPARATION_MM = 1.0


def _is_finite_number(value) -> bool:
    return (
        isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)
    )


def check_electrode_pairs(pairs, *, xyz: bool) -> None:
    """Raise ``ValueError`` unless *pairs* is a montage SimNIBS can place.

    The rules a montage's electrodes must meet wherever it is saved or run:
    every pair holds exactly two electrodes; the pair count is an allowed one
    (:func:`tit.constants.is_valid_pair_count`) and at most
    :data:`MAX_ELECTRODE_PAIRS`; every electrode is its own point -- a label is
    a non-empty string used once in the montage (an electrode cannot be its own
    return, and two channels cannot share one), an XYZ electrode is three
    finite numbers at least :data:`MIN_ELECTRODE_SEPARATION_MM` from every other.

    Parameters
    ----------
    pairs : sequence
        The montage's electrode pairs, in channel order.
    xyz : bool
        ``True`` when electrodes are ``[x, y, z]`` coordinates, ``False`` for
        EEG-cap labels.

    Raises
    ------
    ValueError
        Naming the first rule the montage breaks.
    """
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(
                f"invalid electrode pair {pair!r}; each pair must contain exactly "
                "two electrodes."
            )
    n = len(pairs)
    if not const.is_valid_pair_count(n):
        raise ValueError(
            f"Invalid number of electrode pairs: {n}. Expected {const.PAIR_COUNT_RULE}."
        )
    if n > MAX_ELECTRODE_PAIRS:
        raise ValueError(
            f"{n} electrode pairs; mTI names its channels A-Z, so at most "
            f"{MAX_ELECTRODE_PAIRS} pairs."
        )
    electrodes = [electrode for pair in pairs for electrode in pair]
    if not xyz:
        for electrode in electrodes:
            if not isinstance(electrode, str) or not electrode.strip():
                raise ValueError(
                    f"electrode label {electrode!r} must be a non-empty string."
                )
        repeated = sorted({e for e in electrodes if electrodes.count(e) > 1})
        if repeated:
            raise ValueError(
                f"{', '.join(repeated)} used more than once: an electrode cannot be its "
                "own return, and two channels cannot share one."
            )
        return
    for i, point in enumerate(electrodes, start=1):
        if (
            not isinstance(point, (list, tuple))
            or len(point) != 3
            or not all(_is_finite_number(v) for v in point)
        ):
            raise ValueError(
                f"electrode {i} must be three finite numbers [x, y, z]; got {point!r}."
            )
    for i, a in enumerate(electrodes):
        for j in range(i + 1, len(electrodes)):
            if math.dist(a, electrodes[j]) < MIN_ELECTRODE_SEPARATION_MM:
                raise ValueError(
                    f"electrodes {i + 1} and {j + 1} are less than "
                    f"{MIN_ELECTRODE_SEPARATION_MM:g} mm apart: each electrode needs "
                    "its own place on the scalp."
                )


@dataclass
class SimulationConfig:
    """Full configuration for a TI or mTI simulation run.

    Passed to :func:`tit.sim.run_simulation` to execute one or more
    montage simulations for a single subject.  Electrode geometry,
    conductivity model, and output mapping options are all set here.

    Attributes
    ----------
    subject_id : str
        Subject identifier without the ``sub-`` prefix (e.g. ``"ernie"``,
        ``"101"``); must match an existing ``m2m_<subject_id>`` directory.
    montages : list[Montage]
        One or more :class:`Montage` definitions to simulate.  Two channels
        (electrode pairs) is TI, four or more (even) is mTI -- detected
        per montage, so a list may mix both.
    conductivity : str
        Tissue conductivity model.  One of:

        - ``"scalar"`` -- isotropic scalar conductivities (default).
        - ``"vn"`` -- volume-normalized anisotropic conductivities.
        - ``"dir"`` -- directly-mapped anisotropic conductivities.
        - ``"mc"`` -- mean-conductivity anisotropic conductivities.

        The anisotropic modes (``"vn"``, ``"dir"``, ``"mc"``) require
        DTI tensors registered to the head mesh.
    intensities : list[float]
        Current per channel in mA, in ``electrode_pairs`` order (one value
        per channel).  A TI montage reads the first two values; an mTI montage
        needs one value per channel (``len(intensities) >= num_pairs``).  A
        single value is **not** broadcast -- a 4-channel montage with the default
        two values is rejected.  Default ``[1.0, 1.0]``.
    electrode_shape : str
        Electrode shape, ``"ellipse"`` or ``"rect"``.  Default
        ``"ellipse"``.
    electrode_dimensions : list[float]
        ``[width, height]`` of each electrode in mm.  Default
        ``[8.0, 8.0]``.
    gel_thickness : float
        Conductive-gel (saline) layer thickness in mm, between the skin and
        the rubber.  Default ``1.0``.
    rubber_thickness : float
        Rubber (silicone) layer thickness in mm.  Default ``2.0``.
    map_to_vol : bool
        Write NIfTI volumes of the field meshes (SimNIBS's own meaning of the
        name; ``tit.tools.mesh2nii`` does the conversion after the run): one
        3-D ``<mesh>_subject_<field>.nii.gz`` per field of each field mesh --
        the brain-tissue mesh and its grey- and white-matter copies -- so the
        NIfTI set is the mesh field set, name for name, plus each channel's
        ``magnE``.  Default ``False``: the field meshes are the output, and a
        step that needs a NIfTI (a voxel analysis, the group tools) writes the
        one it reads on demand (:mod:`tit.volume_fields`).
    map_to_mni : bool
        Also write each field NIfTI in MNI space (``<mesh>_MNI_MNI_<field>.nii.gz``)
        and the T1 in MNI space.  MNI output is itself a NIfTI, so ``True`` turns
        *map_to_vol* on as well (subject and MNI NIfTIs).  Default ``False``.
    map_to_fsavg : bool
        After each TI montage finishes, project its surface fields
        (``TI_max``, ``TI_normal``, ``hf_peak``, ``hf_rms``) onto fsaverage5
        for group surface analysis.  Default ``True``; set ``False`` to
        skip.  Failures are logged and never abort the simulation.
    aniso_maxratio : float
        Maximum eigenvalue ratio clamp for anisotropic conductivity
        tensors.  Default ``10.0``.
    aniso_maxcond : float
        Maximum absolute conductivity clamp (S/m) for anisotropic
        tensors.  Default ``2.0``.
    output_fields : list[str]
        Which volume-mesh fields to compute and write. Logical names from
        :data:`tit.constants.SELECTABLE_OUTPUT_FIELDS`: ``"TI_max"``,
        ``"TI_avg"``, ``"hf_peak"``, ``"hf_rms"``, ``"hf_power_density"``.
        ``"TI_max"`` maps to ``mTI_max`` on disk for mTI meshes. ``None``
        (the default) is :data:`tit.constants.DEFAULT_OUTPUT_FIELDS` --
        ``["TI_max", "hf_peak", "hf_rms"]``, the envelope and the carrier
        fields an analysis's carrier metrics read -- or, for a *carrier_only*
        run, which has no envelope, ``["hf_peak", "hf_rms"]``.  ``TI_avg`` and
        ``hf_power_density`` are opt-in; a field not saved here is computed
        later, from the kept channel meshes, by the step that needs it
        (``hf_power_density`` excepted: its conductivity is not kept).
        ``hf_power_density`` (W/m^3) uses the conductivity of this run's own
        solve, the full tensor under the anisotropic models.
    tissue_conductivities : dict[int, float] or None
        Per-tissue conductivity overrides (S/m), keyed by SimNIBS tissue
        number (1-based, matching ``tdcs.cond`` index + 1). ``None`` (the
        default) uses SimNIBS's own tissue defaults for every tissue.
        JSON object keys are always strings, so this round-trips as
        ``{"<tissue number>": <S/m>}`` on disk; :func:`tit.config_io.deserialize_config`
        coerces the keys back to ``int``, and this dataclass's own
        ``__post_init__`` does the same for an instance built directly
        with string keys. Applied to every channel's TDCS list by
        ``tit.sim.base.BaseSimulation._apply_tissue_conductivities`` and
        recorded in the run's ``config.json``.
    carrier_only : bool
        Carrier-only control: both channels run at the same frequency, in
        phase (ΔF = 0), so there is no beat.  The carrier fields ``hf_peak``,
        ``hf_rms`` and ``hf_power_density`` then add the two channel fields
        coherently (``|E1+E2|``, see :func:`tit.calc.hf_peak`) and no envelope
        field (``TI_max``, ``TI_avg``, ``TI_normal``) is computed.  Requires a
        two-channel TI montage; an explicit ``output_fields`` must be drawn
        from those carrier fields (the default already is).  Default ``False``.

    Raises
    ------
    ValueError
        If *conductivity* is not one of the valid model names, if
        *output_fields* contains an unknown name or is empty, if any
        montage has a channel that is not exactly two electrodes, if
        *intensities* is shorter than a montage needs (2 for TI, one per
        channel for mTI), if *tissue_conductivities* contains a tissue
        number outside 1..1000 or a non-positive value, if *electrode_shape* is not
        ``"ellipse"`` or ``"rect"`` or any electrode dimension, *gel_thickness*
        or *rubber_thickness* is not a finite number above 0, if *carrier_only* is set with an envelope
        output field or a montage that is not two-channel TI.  Filesystem checks (the m2m directory, the
        EEG-net CSV) happen later, in :func:`run_simulation`.

    Examples
    --------
    >>> from tit.sim import SimulationConfig, Montage, MontageMode
    >>> montage = Montage(
    ...     name="L_Insula", mode=MontageMode.NET,
    ...     electrode_pairs=[("E010", "E011"), ("E012", "E013")],
    ...     eeg_net="GSN-HydroCel-185.csv",
    ... )
    >>> cfg = SimulationConfig(
    ...     subject_id="ernie",
    ...     montages=[montage],
    ...     conductivity="scalar",
    ...     intensities=[1.0, 1.0],
    ...     electrode_shape="ellipse",
    ...     electrode_dimensions=[8.0, 8.0],
    ...     output_fields=["TI_max", "hf_peak"],
    ... )
    >>> cfg.output_fields
    ['TI_max', 'hf_peak']

    A carrier-only control of the same montage (both channels at one
    frequency, in phase; no envelope, so only carrier fields):

    >>> sham = SimulationConfig(
    ...     subject_id="ernie", montages=[montage], intensities=[1.0, 1.0],
    ...     carrier_only=True,
    ... )
    >>> sham.output_fields
    ['hf_peak', 'hf_rms']

    Then ``run_simulation(cfg)`` (needs SimNIBS and the subject's m2m
    directory).

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
    gel_thickness: float = 1.0
    rubber_thickness: float = 2.0
    # NIfTI conversion is handled by tit.tools.mesh2nii (not SimNIBS SESSION).
    map_to_vol: bool = False
    map_to_mni: bool = False
    map_to_fsavg: bool = True
    aniso_maxratio: float = 10.0
    aniso_maxcond: float = 2.0
    output_fields: list[str] | None = None
    tissue_conductivities: dict[int, float] | None = None
    carrier_only: bool = False

    def __post_init__(self):
        if self.conductivity not in _VALID_CONDUCTIVITIES:
            raise ValueError(
                f"Invalid conductivity {self.conductivity!r}, "
                f"must be one of {_VALID_CONDUCTIVITIES}"
            )
        if self.electrode_shape not in ("ellipse", "rect"):
            raise ValueError(
                f"electrode_shape must be 'ellipse' or 'rect' (was {self.electrode_shape!r})"
            )
        sizes = [*self.electrode_dimensions, self.gel_thickness, self.rubber_thickness]
        if len(self.electrode_dimensions) != 2 or not all(
            _is_finite_number(v) and v > 0 for v in sizes
        ):
            raise ValueError(
                "electrode_dimensions ([width, height]), gel_thickness and "
                "rubber_thickness must be finite numbers above 0 mm; got "
                f"{self.electrode_dimensions!r}, {self.gel_thickness!r}, "
                f"{self.rubber_thickness!r}"
            )
        if self.output_fields is None:
            # One rule for both modes: every default field the run defines.
            self.output_fields = [
                name
                for name in const.DEFAULT_OUTPUT_FIELDS
                if not self.carrier_only or name in const.CARRIER_OUTPUT_FIELDS
            ]
        if self.map_to_mni:
            # MNI output is itself a NIfTI: asking for it asks for the NIfTIs.
            self.map_to_vol = True
        invalid = sorted(set(self.output_fields) - set(const.SELECTABLE_OUTPUT_FIELDS))
        if invalid:
            raise ValueError(
                f"Invalid output field(s) {invalid}, must be a subset of "
                f"{list(const.SELECTABLE_OUTPUT_FIELDS)}"
            )
        if not self.output_fields:
            raise ValueError(
                "output_fields must not be empty; at least one output field "
                "must be selected"
            )
        # Cross-field rules that need nothing but the config itself. They used to live only
        # in `tit.sim.utils._validate_simulation_inputs`, which runs inside the job -- so
        # `POST /api/validate/sim` answered {"ok": true} for a config the runner rejected one
        # second later (measured 2026-09-03, job cdf272b6556c43fa: a 4-pair mTI montage with
        # the default 2 intensities -> "requires 4 current intensities; got 2"). Anything that
        # needs the filesystem (the m2m directory, the EEG-net CSV) stays in utils, which is
        # why this is a split and not a move.
        names = [montage.name for montage in self.montages]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValueError(
                f"Montage name(s) {', '.join(map(repr, repeated))} used more than once: "
                "each montage writes Simulations/<name>/, so one would overwrite the other."
            )
        for montage in self.montages:
            for pair in montage.electrode_pairs:
                if len(pair) != 2:
                    raise ValueError(
                        f"Montage {montage.name!r} has an invalid electrode pair {pair!r}; "
                        "each pair must contain exactly two electrodes."
                    )
            # A pair count `simulation_mode` cannot classify (1, 3, 5, ...) is refused here, not
            # only in `run_simulation`: a 5-pair free-hand job was accepted and then failed at
            # run time with "Invalid number of electrode pairs: 5" (2026-10-21).
            try:
                mode = montage.simulation_mode
                # 2026-10-22: the A-Z pair cap, repeated or coincident electrodes and
                # non-finite coordinates failed only after the FEM solves, or never.
                check_electrode_pairs(montage.electrode_pairs, xyz=montage.is_xyz)
            except ValueError as exc:
                raise ValueError(f"Montage {montage.name!r}: {exc}") from exc
            required = 2 if mode == SimulationMode.TI else montage.num_pairs
            if len(self.intensities) < required:
                raise ValueError(
                    f"Montage {montage.name!r} requires {required} current "
                    f"intensities; got {len(self.intensities)}."
                )
            # A 0 mA channel makes the envelope 0 everywhere. A negative current is a
            # polarity (an optimiser candidate's swapped pads), not an error.
            for channel, current in enumerate(self.intensities[:required], start=1):
                if not _is_finite_number(current) or current == 0:
                    raise ValueError(
                        f"Montage {montage.name!r}: channel {channel} needs a finite "
                        f"current other than 0 mA; got {current!r}."
                    )
        if not all(_is_finite_number(v) for v in self.intensities):
            raise ValueError(
                f"intensities must be finite numbers (mA); got {self.intensities!r}."
            )

        if self.carrier_only:
            envelope = sorted(
                set(self.output_fields) - set(const.CARRIER_OUTPUT_FIELDS)
            )
            if envelope:
                raise ValueError(
                    f"carrier_only has no envelope (ΔF = 0); output_fields {envelope} "
                    "are undefined -- select from "
                    f"{', '.join(const.CARRIER_OUTPUT_FIELDS)}."
                )
            if any(m.num_pairs != 2 for m in self.montages):
                raise ValueError("carrier_only requires two-channel TI montages.")

        if self.tissue_conductivities is not None:
            # JSON object keys are always strings; deserialize_config coerces them back
            # to int (see tit.config_io._deserialize_value's dict-origin branch), but a
            # config built directly in Python (as here) may still hand in string keys.
            self.tissue_conductivities = {
                int(k): float(v) for k, v in self.tissue_conductivities.items()
            }
            # SimNIBS's standard_cond() has ElementTags.TH_END + 1 = 1000 entries.
            bad = [k for k in self.tissue_conductivities if not 1 <= k <= 1000]
            if bad:
                raise ValueError(
                    f"tissue_conductivities: tissue number(s) {sorted(bad)} out of range; "
                    "SimNIBS tissue numbers are 1..1000"
                )
            non_positive = {
                k: v for k, v in self.tissue_conductivities.items() if v <= 0
            }
            if non_positive:
                raise ValueError(
                    "tissue_conductivities values must be > 0 S/m; got "
                    f"{non_positive}"
                )


def parse_intensities(s: str) -> list[float]:
    """Parse a comma-separated intensity string into a list of floats.

    Intensities are one current per channel (electrode pair).  A single
    value is used for both channels of a TI montage (``"2.0"`` becomes
    ``[2.0, 2.0]``).  Otherwise the value count must be even: two channels
    for TI, four or more for mTI.

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
