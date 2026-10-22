"""Configuration dataclasses for TI optimization.

Pure Python -- no SimNIBS, numpy, or heavy dependencies.
Mirrors the ``tit.sim.config`` pattern.

Public API
----------
FlexConfig
    Full configuration for flex-search (differential-evolution) optimization.
FlexResult
    Result container for a completed flex-search run.
ExConfig
    Full configuration for exhaustive (grid) search optimization.
ExResult
    Result container for a completed exhaustive search run.
MExConfig
    Full configuration for multipolar (4-pair) exhaustive search.
MExResult
    Result container for a completed multipolar exhaustive search run.

See Also
--------
tit.opt.flex.flex.run_flex_search : Consumes :class:`FlexConfig`.
tit.opt.ex.ex.run_ex_search : Consumes :class:`ExConfig`.
tit.opt.mex.mex.run_m_ex_search : Consumes :class:`MExConfig`.
"""

import math
import numbers
import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


def _as_list(value) -> list:
    """Wrap a scalar in a single-element list; pass lists/tuples through.

    Strings are treated as scalars (``"lh"`` -> ``["lh"]``), never iterated
    character-by-character.  Used to normalise ROI fields that accept either a
    single value (one region) or a list (a union of several regions).
    """
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


#: Threshold specifications that mean "let SimNIBS choose" rather than naming an
#: explicit numeric threshold.  The empty string is included so a blank GUI field
#: is treated the same as an unset one.
_THRESHOLD_PLACEHOLDERS = frozenset({"", "dynamic", "auto"})


def _finite(value, name: str) -> float:
    """*value* as a finite float, or a ValueError naming *name*."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number (was {value!r})") from None
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite (was {value!r})")
    return number


def _positive(value, name: str) -> float:
    """*value* as a finite float greater than zero, or a ValueError naming *name*."""
    number = _finite(value, name)
    if number <= 0.0:
        raise ValueError(f"{name} must be greater than 0 (was {number:g})")
    return number


def _count(value, name: str) -> int:
    """*value* as a whole number of at least 1, or a ValueError naming *name*."""
    if isinstance(value, bool) or not float(_finite(value, name)).is_integer():
        raise ValueError(f"{name} must be a whole number (was {value!r})")
    if int(value) < 1:
        raise ValueError(f"{name} must be at least 1 (was {int(value)})")
    return int(value)


def _thresholds_text(thresholds) -> str | None:
    """*thresholds* in its text spelling: ``None`` and text pass through.

    A number (a JSON number from an agent) or a list of numbers (a notebook)
    becomes the comma-separated text the builder, the manifest and the report
    read, e.g. ``0.2`` -> ``"0.2"`` and ``[0.1, 0.2]`` -> ``"0.1,0.2"``.

    Raises
    ------
    ValueError
        Naming ``thresholds``, for any other type.
    """
    if thresholds is None or isinstance(thresholds, str):
        return thresholds
    if isinstance(thresholds, numbers.Real):
        return str(thresholds)
    if isinstance(thresholds, (list, tuple)) and all(
        isinstance(value, numbers.Real) for value in thresholds
    ):
        return ",".join(str(value) for value in thresholds)
    raise ValueError(
        f"thresholds {thresholds!r}: give text such as '0.1,0.2' (V/m), a number "
        "or a list of numbers"
    )


def _parse_thresholds(thresholds) -> list[float] | None:
    """Validate a focality threshold specification; ``None`` when it is unset.

    ``None`` and the placeholders in :data:`_THRESHOLD_PLACEHOLDERS` mean "no
    explicit thresholds". Otherwise SimNIBS's ``measures.ROC`` takes one value
    (non-ROI max = ROI min) or two (non-ROI max, ROI min: a safety gap, so the
    first may not exceed the second), each an E-field magnitude in V/m. A
    number or a list of numbers is read as its text (:func:`_thresholds_text`).

    Raises
    ------
    ValueError
        Naming ``thresholds``, for anything else.
    """
    thresholds = _thresholds_text(thresholds)
    if not _has_usable_thresholds(thresholds):
        return None
    parts = [part.strip() for part in str(thresholds).split(",")]
    if len(parts) > 2:
        raise ValueError(
            f"thresholds {thresholds!r}: give one value (non-ROI max = ROI min) or "
            f"two (non-ROI max, ROI min) in V/m, not {len(parts)}"
        )
    values = []
    for part in parts:
        try:
            value = float(part)
        except ValueError:
            raise ValueError(
                f"thresholds {thresholds!r}: {part!r} is not a number"
            ) from None
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(
                f"thresholds {thresholds!r}: every value must be a finite field "
                "strength greater than 0 V/m"
            )
        values.append(value)
    if len(values) == 2 and values[0] > values[1]:
        raise ValueError(
            f"thresholds {thresholds!r}: the non-ROI maximum ({values[0]:g} V/m) "
            f"may not exceed the ROI minimum ({values[1]:g} V/m)"
        )
    return values


def _has_usable_thresholds(thresholds) -> bool:
    """True when *thresholds* names explicit numeric focality thresholds.

    ``None`` and the placeholders in :data:`_THRESHOLD_PLACEHOLDERS` both mean
    "let SimNIBS pick".  SimNIBS's built-in ROC goal supplies its own defaults in
    that case, but a Python-side ROC objective (as used by the current-ratio
    search) has nothing to fall back on.
    """
    thresholds = _thresholds_text(thresholds)
    if thresholds is None:
        return False
    return thresholds.strip().lower() not in _THRESHOLD_PLACEHOLDERS


# ── Flex-search config ───────────────────────────────────────────────────────


@dataclass
class FlexConfig:
    """Full configuration for flex-search optimization.

    Wraps all parameters needed to drive a SimNIBS
    ``TesFlexOptimization`` run, including subject, ROI definition,
    electrode geometry, DE hyperparameters, and output control.

    Attributes
    ----------
    subject_id : str
        Subject identifier matching the m2m directory name.
    goal : OptGoal
        Optimization objective (``"mean"``, ``"max"``, ``"focality"``, or
        ``"focality_tf"``).
    postproc : FieldPostproc
        Field post-processing method (``"max_TI"``, ``"dir_TI_normal"``,
        or ``"dir_TI_tangential"``).
    current_mA : float
        Current per channel in mA -- each of the two electrode pairs
        injects ``+current_mA`` / ``-current_mA`` (a 1:1 split), so the
        total injected current is ``2 * current_mA``.
    electrode : ElectrodeConfig
        Electrode geometry configuration.
    roi : SphericalROI or AtlasROI or SubcorticalROI
        Target region of interest.
    anisotropy_type : str
        Conductivity tensor type (``"scalar"`` or ``"vn"``).  Default
        ``"scalar"``.
    aniso_maxratio : float
        Maximum anisotropy eigenvalue ratio.  Default ``10.0``.
    aniso_maxcond : float
        Maximum anisotropic conductivity (S/m).  Default ``2.0``.
    non_roi_method : NonROIMethod or None
        How to define the non-ROI region for focality optimization.
        ``None`` when goal is not focality.
    non_roi : SphericalROI or AtlasROI or SubcorticalROI or None
        Explicit non-ROI region when *non_roi_method* is ``"specific"``.
    thresholds : str or None
        Focality thresholds in V/m for the ROC-based ``"focality"`` goal: one
        value (non-ROI max = ROI min) or two, ``"<non-ROI max>,<ROI min>"``
        (e.g. ``"0.1,0.2"``), each finite and greater than 0, the first not
        above the second (SimNIBS ``measures.ROC``'s safety gap).  A number or
        a list of numbers is stored as that text (``0.2`` -> ``"0.2"``).
        ``None`` and the placeholders ``""``, ``"dynamic"``, ``"auto"`` mean
        unset and are stored as ``None``.  A single ``"focality"`` run
        requires them -- SimNIBS has no default -- while ``mode="flex_adaptive"`` /
        ``"flex_pareto"`` (or a config carrying *adaptive* / *pareto*
        settings, whose mode the job kind supplies) derive them per step.
    intensity_weight : float
        Weight ``w`` in ``[0, 1]`` trading ROI intensity against focality
        for the ``"focality_tf"`` goal.  ``0.0`` gives the balanced form,
        ``1.0`` weights raw ROI intensity most heavily.  Ignored by the
        other goals.
    optimize_current_ratio : bool
        If True, jointly search the electrode placement **and** the
        current split between the two channels instead of fixing it at
        1:1.  Applies to any goal.  Scoring then happens in a Python
        callable rather than in SimNIBS, which has two consequences:
        ``goal="focality"`` in ``mode="flex"`` requires explicit
        *thresholds* (the adaptive and multi-threshold modes derive them
        per step), and *detailed_results* cannot be used.
    ratio_total_mA : float or None
        Total current (mA) shared by the two channels during the ratio
        search.  ``None`` uses ``2 * current_mA``, i.e. the 1:1 split is
        contained in the search range.  When set explicitly it must be
        greater than zero.
    ratio_levels : int
        Number of discrete current splits evaluated per candidate
        placement.  Must be at least 2 when *optimize_current_ratio* is
        True.
    eeg_net : str or None
        EEG net name or filename (e.g. ``"GSN-HydroCel-185"`` or
        ``"GSN-HydroCel-185.csv"``) for electrode-name mapping.
        ``None`` (default) to use raw electrode indices.
    enable_mapping : bool
        If True, map optimal indices to named EEG positions.  Default
        ``False``.
    disable_mapping_simulation : bool
        If True, skip the final named-electrode simulation after mapping.
        Default ``False``.
    observe_background : bool
        If True, also record observation-only background (non-ROI) field
        metrics for every candidate, independent of the goal.  Like the
        callable goals it is incompatible with *detailed_results*.
        Default ``False``.
    output_folder : str or None
        Override for the output directory path.  Defaults to an
        auto-generated timestamped folder.
    run_final_electrode_simulation : bool
        If True, run a full SimNIBS simulation with the winning
        electrode configuration.
    n_multistart : int
        Number of independent DE restarts (default ``1``).  Higher values
        reduce sensitivity to local optima; this is the only thing
        *cpus* parallelises.
    max_iterations : int or None
        Maximum DE generations per restart.  ``None`` for solver default.
    population_size : int or None
        DE population size.  ``None`` for solver default.
    tolerance : float or None
        Convergence tolerance for DE.  ``None`` for solver default.
    mutation : str or None
        DE mutation strategy string.  ``None`` for solver default.
    recombination : float or None
        DE crossover probability.  ``None`` for solver default.
    cpus : int or None
        Number of parallel workers for the multi-start restarts (the DE
        search itself is single-process).  ``None`` uses the global CPU
        limit (:func:`tit.cpu.cpu_limit`); a larger value is clamped to it.
    min_electrode_distance : float
        Minimum distance (mm) SimNIBS keeps between any two electrodes,
        greater than 0.  Default ``5.0``.  SimNIBS measures it as the
        straight-line distance between the skin-mesh nodes under each
        electrode (``check_electrode_distance``), not edge to edge: nodes
        sit inside the footprint, so the physical gap between two discs
        (centre distance minus both radii) can be several millimetres
        smaller -- 1.75 mm for the 5 mm default between 8 mm discs on a
        real head (audit 2026-10-22).
    detailed_results : bool
        If True, save per-restart detailed output.  Incompatible with any
        configuration whose goal is a Python callable -- ``"focality_tf"``
        or *optimize_current_ratio* -- because SimNIBS writes ``opt.goal``
        into the detailed-results HDF5 file and h5py cannot serialise a
        function.  The combination is rejected at config time rather than
        after the (potentially hours-long) optimization has finished.
    visualize_valid_skin_region : bool
        If True, save a mesh showing the valid electrode placement region.
    skin_visualization_net : str or None
        EEG net to overlay on the skin visualization.
    skin_region_margin_mm : float
        Signed margin in millimeters applied to the SimNIBS valid-skin
        region. Positive values expand the region, negative values
        constrict it. The default ``0.0`` preserves SimNIBS behavior.
    avoid_landmark_regions : bool
        If True, positive skin-region margins keep fiducial-derived
        ear and orbital exclusion regions invalid.
    mode : Mode
        Which driver runs this config: a single run (``"flex"``, the
        default), :func:`tit.opt.flex.drivers.run_adaptive_focality`
        (``"flex_adaptive"``), or :func:`tit.opt.flex.drivers.run_pareto_sweep`
        (``"flex_pareto"``). Set by the job kind
        (``tit.jobs.kinds.MODULE_FOR_KIND``); ``tit.opt.flex.__main__``
        dispatches on it.
    adaptive : AdaptiveFocalityConfig or None
        Threshold percentages for ``mode="flex_adaptive"``. Defaulted when
        left ``None`` under that mode.
    pareto : ParetoSweepConfig or None
        Threshold percentage grid for ``mode="flex_pareto"``. Defaulted
        when left ``None`` under that mode.

    Raises
    ------
    ValueError
        If *goal* is ``"focality"`` with *non_roi_method* ``"specific"``
        but *non_roi* is ``None`` or equal to *roi*, if *thresholds* is
        malformed (see *thresholds*) or missing for a single ``"focality"``
        run, if *current_mA*, *min_electrode_distance*, an electrode size or
        a sphere radius is not a positive finite number (or a sphere centre
        is not finite), if *n_multistart* or *cpus* is below 1, if an
        ``"ellipse"`` electrode has unequal dimensions, if a subcortical
        *atlas_space* is neither ``"subject"`` nor ``"mni"``, if
        *output_folder*'s last component breaks :data:`tit.paths.NAME_RE`,
        if *intensity_weight* falls outside ``[0, 1]``, if
        *ratio_levels* is below 2 while *optimize_current_ratio* is True,
        if *ratio_total_mA* is set but not positive, if
        *optimize_current_ratio* is combined with ``goal="focality"``
        in ``mode="flex"`` without explicit *thresholds*, if
        *detailed_results* is combined with a callable-goal configuration
        (``goal="focality_tf"``, *optimize_current_ratio* or
        *observe_background*), or if *mode* is
        ``"flex_adaptive"``/``"flex_pareto"`` while *goal* is not
        ``"focality"``.

    Examples
    --------
    Enum-valued fields accept their string values:

    >>> from tit.opt import FlexConfig
    >>> cfg = FlexConfig(
    ...     subject_id="ernie",
    ...     goal="mean",                       # "mean" | "max" | "focality" | "focality_tf"
    ...     postproc="max_TI",                 # "max_TI" | "dir_TI_normal" | "dir_TI_tangential"
    ...     current_mA=1.0,
    ...     electrode=FlexConfig.ElectrodeConfig(shape="ellipse", dimensions=[8.0, 8.0]),
    ...     roi=FlexConfig.SphericalROI(x=-35.0, y=5.0, z=5.0, radius=10.0, use_mni=True),
    ...     n_multistart=3,
    ... )
    >>> cfg.goal is FlexConfig.OptGoal.MEAN, cfg.is_focality
    (True, False)

    A focality goal defaults its non-ROI region to everything outside the ROI:

    >>> foc = FlexConfig(
    ...     subject_id="ernie", goal="focality_tf", postproc="max_TI", current_mA=1.0,
    ...     electrode=FlexConfig.ElectrodeConfig(),
    ...     roi=FlexConfig.AtlasROI(atlas_path="lh.aparc.annot", label=24, hemisphere="lh"),
    ... )
    >>> foc.non_roi_method.value
    'everything_else'

    Then ``run_flex_search(cfg)`` (needs SimNIBS and the subject's m2m
    directory).

    See Also
    --------
    FlexResult : Result container returned by :func:`~tit.opt.flex.flex.run_flex_search`.
    tit.opt.flex.flex.run_flex_search : Consumes this config.
    """

    # ── Nested enums ──────────────────────────────────────────────────

    class OptGoal(StrEnum):
        """Optimization goal.

        Attributes
        ----------
        MEAN : str
            Maximize mean field intensity in the ROI.
        MAX : str
            Maximize the 99.9th percentile field intensity in the ROI.
        FOCALITY : str
            Maximize ROI-to-non-ROI focality via SimNIBS's threshold-based
            ROC measure (``measures.ROC``).
        FOCALITY_TF : str
            Maximize a threshold-free focality contrast,
            ``mean(E_ROI) ** (1 + w) / mean(E_nonROI)``.  Because it needs no
            thresholds it avoids the threshold-selection failure mode of the
            ROC goal, whose landscape flattens when the requested ROI and
            non-ROI thresholds are jointly infeasible (as happens at deep
            targets).  The weight ``w`` is
            :attr:`FlexConfig.intensity_weight`.
        """

        MEAN = "mean"
        MAX = "max"
        FOCALITY = "focality"
        FOCALITY_TF = "focality_tf"

    class FieldPostproc(StrEnum):
        """Field post-processing method applied to the TI envelope.

        Attributes
        ----------
        MAX_TI : str
            Maximum TI amplitude (direction-independent).
        DIR_TI_NORMAL : str
            TI component normal to the cortical surface.
        DIR_TI_TANGENTIAL : str
            TI component tangential to the cortical surface.
        """

        MAX_TI = "max_TI"
        DIR_TI_NORMAL = "dir_TI_normal"
        DIR_TI_TANGENTIAL = "dir_TI_tangential"

    class NonROIMethod(StrEnum):
        """Non-ROI specification method for focality optimization.

        Attributes
        ----------
        EVERYTHING_ELSE : str
            Use all mesh elements outside the ROI.
        SPECIFIC : str
            Use an explicitly defined non-ROI region.
        """

        EVERYTHING_ELSE = "everything_else"
        SPECIFIC = "specific"

    class Mode(StrEnum):
        """Which flex-search driver runs this config (``tit.jobs.kinds.MODULE_FOR_KIND``
        maps ``flex``/``flex_adaptive``/``flex_pareto`` job kinds to this same module;
        ``tit.opt.flex.__main__`` dispatches on this field to pick the driver).

        Attributes
        ----------
        FLEX : str
            A single :func:`~tit.opt.flex.flex.run_flex_search` run (any goal).
        FLEX_ADAPTIVE : str
            Two-step adaptive focality: a ``"mean"`` run to find the achievable ROI
            intensity, then a ``"focality"`` run with thresholds derived from
            :attr:`FlexConfig.adaptive`. Requires ``goal="focality"``.
        FLEX_PARETO : str
            A ``"mean"`` calibration run followed by a grid of ``"focality"`` runs
            over :attr:`FlexConfig.pareto`'s threshold percentages. Requires
            ``goal="focality"``.
        """

        FLEX = "flex"
        FLEX_ADAPTIVE = "flex_adaptive"
        FLEX_PARETO = "flex_pareto"

    # ── Nested driver configs (adaptive / Pareto sweep) ────────────────

    @dataclass
    class AdaptiveFocalityConfig:
        """Thresholds for :func:`tit.opt.flex.drivers.run_adaptive_focality`.

        Both percentages are applied to the achievable mean ROI intensity found by
        the driver's own step-1 ``"mean"`` optimization run -- never to a value the
        caller supplies directly, since that intensity is subject- and ROI-specific
        and cannot be known ahead of time.

        Attributes
        ----------
        roi_percentage : float
            ROI focality threshold, as a percentage (0-100 exclusive) of the
            achievable mean ROI intensity.
        nonroi_percentage : float
            Non-ROI focality threshold, as a percentage (0-100 exclusive) of the
            same achievable intensity. Must be strictly less than
            *roi_percentage*.

        Raises
        ------
        ValueError
            If either percentage is outside ``(0, 100)``, or if
            *nonroi_percentage* is not strictly less than *roi_percentage*.
        """

        roi_percentage: float = 80.0
        nonroi_percentage: float = 20.0

        def __post_init__(self):
            self.roi_percentage = float(self.roi_percentage)
            self.nonroi_percentage = float(self.nonroi_percentage)
            for name, value in (
                ("roi_percentage", self.roi_percentage),
                ("nonroi_percentage", self.nonroi_percentage),
            ):
                if not (0.0 < value < 100.0):
                    raise ValueError(f"{name} must be in (0, 100) (was {value})")
            if self.nonroi_percentage >= self.roi_percentage:
                raise ValueError(
                    "nonroi_percentage must be less than roi_percentage (got "
                    f"nonroi_percentage={self.nonroi_percentage}, "
                    f"roi_percentage={self.roi_percentage})"
                )

    @dataclass
    class ParetoSweepConfig:
        """Threshold grid for :func:`tit.opt.flex.drivers.run_pareto_sweep`.

        The driver runs one ``"focality"`` optimization per (roi_pct, nonroi_pct)
        combination in the Cartesian product of *roi_pcts* and *nonroi_pcts| --
        ``len(roi_pcts) * len(nonroi_pcts)`` runs total, in addition to the single
        step-1 ``"mean"`` calibration run. See
        :func:`tit.opt.flex.pareto.compute_sweep_grid`.

        Attributes
        ----------
        roi_pcts : list of float
            ROI threshold percentages to sweep (each in ``(0, 100)``).
        nonroi_pcts : list of float
            Non-ROI threshold percentages to sweep (each in ``(0, 100)``).

        Raises
        ------
        ValueError
            If either list is empty, if any value falls outside ``(0, 100)``,
            or if any ``(roi_pct, nonroi_pct)`` combination has
            ``nonroi_pct >= roi_pct``.
        """

        roi_pcts: list[float] = field(default_factory=lambda: [80.0])
        nonroi_pcts: list[float] = field(default_factory=lambda: [20.0, 30.0, 40.0])

        def __post_init__(self):
            self.roi_pcts = [float(v) for v in _as_list(self.roi_pcts)]
            self.nonroi_pcts = [float(v) for v in _as_list(self.nonroi_pcts)]
            for name, values in (
                ("roi_pcts", self.roi_pcts),
                ("nonroi_pcts", self.nonroi_pcts),
            ):
                if not values:
                    raise ValueError(f"{name} must be non-empty")
                for v in values:
                    if not (0.0 < v < 100.0):
                        raise ValueError(f"{name} value {v} out of range (0, 100)")
            bad = [(r, n) for r in self.roi_pcts for n in self.nonroi_pcts if n >= r]
            if bad:
                raise ValueError(
                    "nonroi_pcts must be strictly less than roi_pcts for every "
                    f"combination; invalid pairs: {bad}"
                )

    # ── Nested ROI types ──────────────────────────────────────────────

    @dataclass
    class SphericalROI:
        """Spherical region of interest defined by center and radius.

        By default the sphere is evaluated on the cortical surface
        (``volumetric=False``).  Set ``volumetric=True`` to evaluate on
        volume tetrahedra instead -- useful for deep/subcortical targets
        like the amygdala or hippocampus where surface-only evaluation
        would capture overlying cortex rather than the target structure.

        When ``volumetric=True``, the *tissues* field controls which
        tissue compartments are included (same semantics as
        :class:`SubcorticalROI.tissues`).

        Each of *x*, *y*, *z*, *radius* accepts either a single value (one
        sphere) or a list of values (a union of several spheres evaluated as
        one combined target).  The coordinate lists must be non-empty and of
        equal length; *radius* may be a scalar (shared by every sphere) or a
        list matching the number of centers.

        Attributes
        ----------
        x : float or list of float
            Center x-coordinate(s) (mm).
        y : float or list of float
            Center y-coordinate(s) (mm).
        z : float or list of float
            Center z-coordinate(s) (mm).
        radius : float or list of float
            Sphere radius/radii in mm.  A scalar is shared by all spheres.
        use_mni : bool
            If True, coordinates are in MNI space and SimNIBS will transform
            them to subject space during ROI setup.
        volumetric : bool
            If True, evaluate on volume tetrahedra instead of the cortical
            surface.
        tissues : str
            Tissue compartments to include when *volumetric* is True.
            One of ``"GM"``, ``"WM"``, or ``"both"``.

        Raises
        ------
        ValueError
            If *x*/*y*/*z* are empty or unequal length, or *radius* is a list
            whose length neither equals 1 nor the number of centers.
        """

        x: float | list[float]
        y: float | list[float]
        z: float | list[float]
        radius: float | list[float] = 10.0
        use_mni: bool = False
        volumetric: bool = False
        tissues: str = "GM"  # "GM", "WM", or "both" — only used when volumetric=True

        def __post_init__(self):
            xs, ys, zs = _as_list(self.x), _as_list(self.y), _as_list(self.z)
            if not xs or not (len(xs) == len(ys) == len(zs)):
                raise ValueError(
                    "SphericalROI x, y, z must be non-empty and of equal length"
                )
            if len(_as_list(self.radius)) not in (1, len(xs)):
                raise ValueError(
                    "SphericalROI radius must be a scalar or match the number of "
                    "centers"
                )
            for name, values in (("x", xs), ("y", ys), ("z", zs)):
                for value in values:
                    _finite(value, f"SphericalROI {name}")
            for value in _as_list(self.radius):
                _positive(value, "SphericalROI radius (mm)")

    @dataclass
    class AtlasROI:
        """Cortical surface ROI from a FreeSurfer annotation atlas.

        Each of *atlas_path*, *label*, *hemisphere* accepts either a single
        value (one region) or a list (a union of several regions evaluated as
        one combined target).  Because ``.annot`` files are per-hemisphere,
        carrying a per-region *hemisphere* (and matching *atlas_path*) allows a
        target that spans **both** hemispheres, or even different atlases.
        Scalars broadcast to the number of labels; lists must match its length.

        Attributes
        ----------
        atlas_path : str or list of str
            Path(s) to the FreeSurfer ``.annot`` annotation file(s).
        label : int or list of int
            Integer label index/indices within the annotation atlas.
        hemisphere : str or list of str
            Hemisphere(s) to use (``"lh"`` or ``"rh"``), one per label.

        Raises
        ------
        ValueError
            If *label* is empty, or *atlas_path*/*hemisphere* is a list whose
            length neither equals 1 nor the number of labels.
        """

        atlas_path: str | list[str]
        label: int | list[int]
        hemisphere: str | list[str] = "lh"

        def __post_init__(self):
            n = len(_as_list(self.label))
            if n == 0:
                raise ValueError("AtlasROI label must be non-empty")
            if len(_as_list(self.atlas_path)) not in (1, n):
                raise ValueError(
                    "AtlasROI atlas_path must be a scalar or match the number "
                    "of labels"
                )
            if len(_as_list(self.hemisphere)) not in (1, n):
                raise ValueError(
                    "AtlasROI hemisphere must be a scalar or match the number "
                    "of labels"
                )

    @dataclass
    class SubcorticalROI:
        """Subcortical volume ROI from a volumetric atlas.

        *label* accepts either a single value (one region) or a list (a union
        of several regions -- e.g. both hippocampi from one ``aseg`` atlas --
        evaluated as one combined target).  *atlas_path* may be a scalar
        (shared by every label) or a list matching the number of labels; a
        single shared *tissues* and *atlas_space* apply to the whole union.

        Attributes
        ----------
        atlas_path : str or list of str
            Path(s) to the volumetric atlas NIfTI file(s).
        label : int or list of int
            Integer label index/indices, or None to select all positive mask voxels.
        tissues : str
            Tissue compartments to include.  One of ``"GM"``, ``"WM"``,
            or ``"both"``.
        atlas_space : str
            Space of the atlas NIfTI.  One of ``"subject"`` or ``"mni"``.
            MNI-space masks are transformed by SimNIBS during ROI setup.

        Raises
        ------
        ValueError
            If *label* is empty, or *atlas_path* is a list whose length
            neither equals 1 nor the number of labels.
        """

        atlas_path: str | list[str]
        label: int | list[int] | None
        tissues: str = "GM"  # "GM", "WM", or "both"
        atlas_space: Literal["subject", "mni"] = "subject"

        def __post_init__(self):
            # One spelling everywhere: confirm_roi and the mask resolver compare
            # lower-case, so "MNI" must not reach one of them as a third space.
            space = str(self.atlas_space).strip().lower()
            if space not in ("subject", "mni"):
                raise ValueError(
                    "SubcorticalROI atlas_space must be 'subject' or 'mni' "
                    f"(was {self.atlas_space!r})"
                )
            self.atlas_space = space
            if self.label is None and not isinstance(self.atlas_path, str):
                raise ValueError("A whole-file mask requires one atlas_path")
            n = len(_as_list(self.label))
            if n == 0:
                raise ValueError("SubcorticalROI label must be non-empty")
            if len(_as_list(self.atlas_path)) not in (1, n):
                raise ValueError(
                    "SubcorticalROI atlas_path must be a scalar or match the "
                    "number of labels"
                )

    # ── Nested electrode config ───────────────────────────────────────

    @dataclass
    class ElectrodeConfig:
        """Electrode geometry for flex-search.

        Only *gel_thickness* is needed here -- the optimization leadfield
        uses point electrodes; *gel_thickness* is recorded in the manifest
        for downstream simulation.

        Attributes
        ----------
        shape : str
            Electrode shape (``"ellipse"`` or ``"rect"``).  Default
            ``"ellipse"``.  Flex-search supports circular electrodes only,
            so an ``"ellipse"`` must have equal *dimensions*.
        dimensions : list of float
            Electrode dimensions in mm (``[width, height]``).  Default
            ``[8.0, 8.0]``.
        gel_thickness : float
            Conductive gel thickness in mm.  Default ``4.0``.
        """

        shape: str = "ellipse"  # "ellipse" or "rect"
        dimensions: list[float] = field(default_factory=lambda: [8.0, 8.0])
        gel_thickness: float = 4.0

        def __post_init__(self):
            if self.shape not in ("ellipse", "rect"):
                raise ValueError(
                    f"electrode shape must be 'ellipse' or 'rect' (was {self.shape!r})"
                )
            dims = list(self.dimensions)
            if len(dims) != 2:
                raise ValueError(
                    "electrode dimensions must be [width, height] in mm "
                    f"(was {self.dimensions!r})"
                )
            self.dimensions = [_positive(d, "electrode dimensions (mm)") for d in dims]
            self.gel_thickness = _positive(self.gel_thickness, "gel_thickness (mm)")
            # SimNIBS's flex electrode is a disc (one radius); the builder would
            # refuse this only after the ROI was confirmed, so refuse it here.
            if self.shape == "ellipse" and self.dimensions[0] != self.dimensions[1]:
                raise ValueError(
                    "Flex optimization supports circular electrodes only: ellipse "
                    f"dimensions must be equal (were {self.dimensions}); select equal "
                    "dimensions or a rectangle."
                )

    # ── required ──
    subject_id: str
    goal: OptGoal
    postproc: FieldPostproc
    current_mA: float
    electrode: ElectrodeConfig
    roi: "FlexConfig.SphericalROI | FlexConfig.AtlasROI | FlexConfig.SubcorticalROI"

    anisotropy_type: str = "scalar"
    aniso_maxratio: float = 10.0
    aniso_maxcond: float = 2.0

    # ── focality ──
    non_roi_method: NonROIMethod | None = None
    non_roi: "FlexConfig.SphericalROI | FlexConfig.AtlasROI | FlexConfig.SubcorticalROI | None" = (None)
    thresholds: str | None = None
    intensity_weight: float = 0.0

    # ── current-ratio search ──
    optimize_current_ratio: bool = False
    ratio_total_mA: float | None = None
    ratio_levels: int = 21

    # ── eeg mapping ──
    eeg_net: str | None = None
    enable_mapping: bool = False
    disable_mapping_simulation: bool = False

    # Observation-only background fields are benchmark-gated independently of the goal.
    observe_background: bool = False

    # ── output ──
    output_folder: str | None = None
    run_final_electrode_simulation: bool = False

    # ── solver ──
    n_multistart: int = 1
    max_iterations: int | None = None
    population_size: int | None = None
    tolerance: float | None = None
    mutation: str | None = None
    recombination: float | None = None
    cpus: int | None = None
    min_electrode_distance: float = 5.0

    # ── debug ──
    detailed_results: bool = False
    visualize_valid_skin_region: bool = True
    skin_visualization_net: str | None = None
    skin_region_margin_mm: float = 0.0
    avoid_landmark_regions: bool = True

    # ── driver dispatch (tit.opt.flex.__main__ / tit.opt.flex.drivers) ──
    mode: Mode = Mode.FLEX
    adaptive: "FlexConfig.AdaptiveFocalityConfig | None" = None
    pareto: "FlexConfig.ParetoSweepConfig | None" = None

    def __post_init__(self):
        if isinstance(self.goal, str):
            self.goal = FlexConfig.OptGoal(self.goal)
        if isinstance(self.postproc, str):
            self.postproc = FlexConfig.FieldPostproc(self.postproc)
        if isinstance(self.non_roi_method, str):
            self.non_roi_method = FlexConfig.NonROIMethod(self.non_roi_method)
        if isinstance(self.mode, str):
            self.mode = FlexConfig.Mode(self.mode)
        if isinstance(self.adaptive, dict):
            self.adaptive = FlexConfig.AdaptiveFocalityConfig(**self.adaptive)
        if isinstance(self.pareto, dict):
            self.pareto = FlexConfig.ParetoSweepConfig(**self.pareto)
        if self.mode is not FlexConfig.Mode.FLEX:
            if self.goal is not FlexConfig.OptGoal.FOCALITY:
                raise ValueError(
                    f"mode={self.mode.value!r} requires goal='focality' (the "
                    "ROC threshold-based goal both driver workflows compute "
                    f"thresholds for); got goal={self.goal.value!r}"
                )
            if self.mode is FlexConfig.Mode.FLEX_ADAPTIVE and self.adaptive is None:
                self.adaptive = FlexConfig.AdaptiveFocalityConfig()
            if self.mode is FlexConfig.Mode.FLEX_PARETO and self.pareto is None:
                self.pareto = FlexConfig.ParetoSweepConfig()
        # Any focality goal (ROC or threshold-free) needs a non-ROI region; default to
        # "everything else" so a config that omits the method still runs.
        if self.is_focality and self.non_roi_method is None:
            self.non_roi_method = FlexConfig.NonROIMethod.EVERYTHING_ELSE
        if (
            self.is_focality
            and self.non_roi_method is FlexConfig.NonROIMethod.SPECIFIC
            and self.non_roi is None
        ):
            raise ValueError(
                f"goal='{self.goal.value}' with method='specific' requires a "
                "non_roi specification"
            )
        if (
            self.is_focality
            and self.non_roi_method is FlexConfig.NonROIMethod.SPECIFIC
            and self.non_roi == self.roi
        ):
            # ROI and non-ROI fields are then the same samples: every candidate
            # scores the same contrast (a ratio of 1), so the search is blind.
            raise ValueError(
                f"goal='{self.goal.value}': the non_roi region is identical to the "
                "roi, so ROI and background are the same samples; pick a different "
                "non-ROI region or non_roi_method='everything_else'"
            )
        # One spelling for every reader (builder, manifest, report): text.
        self.thresholds = _thresholds_text(self.thresholds)
        # The adaptive and multi-threshold drivers set thresholds on every
        # focality step themselves (tit.opt.flex.drivers). A config carrying
        # their settings is such a driver config even where its mode is not
        # spelled out: the job kind supplies it (the job manager writes
        # mode=kind into the runner's config.json), and /api/validate, /api/plan
        # and group planning see the body without it.
        derived_thresholds = (
            self.mode is not FlexConfig.Mode.FLEX
            or self.adaptive is not None
            or self.pareto is not None
        )
        # The ratio search scores candidates itself, so the ROC goal can no
        # longer lean on SimNIBS's own threshold handling. Catch it here:
        # otherwise it surfaces as a ValueError raised deep inside the
        # `simnibs_python -m tit.opt.flex` child process, long after launch.
        if (
            self.optimize_current_ratio
            and self.goal is FlexConfig.OptGoal.FOCALITY
            and not derived_thresholds
            and not _has_usable_thresholds(self.thresholds)
        ):
            raise ValueError(
                "optimize_current_ratio=True with goal='focality' requires "
                "explicit numeric thresholds, because the current-ratio "
                "search scores candidates with its own ROC objective "
                f"(thresholds={self.thresholds!r}). Set thresholds (e.g. "
                "'0.1,0.2'), use goal='focality_tf' which needs none, or "
                "set optimize_current_ratio=False."
            )
        # Placeholders ("", "dynamic", "auto") mean "unset": store them as None so
        # the builder, the manifest and the report all see one spelling.
        if _parse_thresholds(self.thresholds) is None:
            self.thresholds = None
        # A single ROC run has no driver deriving its thresholds, and SimNIBS has
        # no default: TESoptimize raises "Please define TESoptimze.threshold for
        # focality optimization!" only once the run starts, after the ROI is
        # confirmed.
        if (
            self.goal is FlexConfig.OptGoal.FOCALITY
            and not derived_thresholds
            and self.thresholds is None
        ):
            raise ValueError(
                "goal='focality' with fixed thresholds (mode='flex') requires "
                "thresholds: one value (non-ROI max = ROI min) or two (non-ROI "
                "max, ROI min) in V/m, e.g. '0.1,0.2'. SimNIBS has no default. "
                "Use mode='flex_adaptive' or 'flex_pareto' to derive them, or "
                "goal='focality_tf', which needs none."
            )
        self.current_mA = _positive(self.current_mA, "current_mA")
        self.min_electrode_distance = _positive(
            self.min_electrode_distance, "min_electrode_distance (mm)"
        )
        self.n_multistart = _count(self.n_multistart, "n_multistart")
        if self.cpus is not None:
            self.cpus = _count(self.cpus, "cpus")
        if self.output_folder is not None:
            from tit.paths import is_valid_name

            # The folder name becomes a run name every catalog listing validates
            # (tit.paths.NAME_RE); one that fails it hides the subject's runs.
            run_name = os.path.basename(os.path.normpath(str(self.output_folder)))
            if not is_valid_name(run_name):
                raise ValueError(
                    f"output_folder run name {run_name!r}: letters, digits, '.', "
                    "'_', '-' and inner spaces only, not starting with '.' or a "
                    "space, at most 128 characters"
                )
        self.intensity_weight = float(self.intensity_weight)
        if not 0.0 <= self.intensity_weight <= 1.0:
            raise ValueError(
                f"intensity_weight must be in [0, 1] (was {self.intensity_weight})"
            )
        self.ratio_levels = int(self.ratio_levels)
        if self.optimize_current_ratio and self.ratio_levels < 2:
            raise ValueError(
                f"ratio_levels must be >= 2 when optimize_current_ratio is "
                f"enabled (was {self.ratio_levels})"
            )
        if self.ratio_total_mA is not None:
            self.ratio_total_mA = float(self.ratio_total_mA)
            if self.ratio_total_mA <= 0.0:
                raise ValueError(
                    f"ratio_total_mA must be > 0 when set (was "
                    f"{self.ratio_total_mA}); leave it None to use "
                    f"2 * current_mA"
                )
        # SimNIBS serialises opt.goal into the detailed-results HDF5 file, and
        # h5py cannot store a Python function. That failure fires only after the
        # optimization completes, so reject the combination up front.
        if self.detailed_results and (
            self.goal is FlexConfig.OptGoal.FOCALITY_TF
            or self.optimize_current_ratio
            or self.observe_background
        ):
            trigger = (
                "goal='focality_tf'"
                if self.goal is FlexConfig.OptGoal.FOCALITY_TF
                else (
                    "optimize_current_ratio=True"
                    if self.optimize_current_ratio
                    else "observe_background=True"
                )
            )
            raise ValueError(
                f"detailed_results=True is not supported with {trigger}: that "
                "configuration scores candidates with a Python callable goal, "
                "and SimNIBS writes opt.goal into its detailed-results HDF5 "
                "file, where h5py rejects a callable: TypeError: Object dtype "
                "dtype('O') has no native HDF5 equivalent. The error is "
                "raised only after the optimization finishes, discarding the "
                "whole run. Set detailed_results=False."
            )
        self.skin_region_margin_mm = float(self.skin_region_margin_mm)

    @property
    def is_focality(self) -> bool:
        """True for any focality goal (ROC-based or threshold-free).

        Focality goals share the same ROI/non-ROI setup (a target ROI plus a
        non-ROI region), so callers use this to gate non-ROI construction and
        reporting. Threshold-specific logic keeps comparing against
        ``OptGoal.FOCALITY`` directly, since only the ROC goal uses thresholds.
        """
        return self.goal in (
            FlexConfig.OptGoal.FOCALITY,
            FlexConfig.OptGoal.FOCALITY_TF,
        )


@dataclass
class FlexResult:
    """Result from a flex-search optimization run.

    Attributes
    ----------
    success : bool
        True if the optimization completed without error.
    output_folder : str
        Absolute path to the output directory containing manifests, logs,
        and optional simulation results.
    function_values : list of float
        Objective function value for each multistart run.
    best_value : float
        Best (highest) objective value across all restarts.
    best_run_index : int
        Zero-based index of the restart that produced the best result.

    Examples
    --------
    >>> res = run_flex_search(cfg)  # doctest: +SKIP
    >>> res.success, res.best_value, res.output_folder  # doctest: +SKIP
    (True, 0.31, '.../flex-search/ernie_...')

    See Also
    --------
    FlexConfig : Configuration consumed by :func:`~tit.opt.flex.flex.run_flex_search`.
    tit.opt.flex.flex.run_flex_search : Returns this result.
    """

    success: bool
    output_folder: str
    function_values: list[float]
    best_value: float
    best_run_index: int


# ── Exhaustive search config ─────────────────────────────────────────────────


@dataclass
class ExConfig:
    """Full configuration for exhaustive search optimization.

    Exhaustive search evaluates every valid electrode combination from
    a user-defined pool or bucket set, sweeping current amplitudes at
    discrete steps.

    Attributes
    ----------
    subject_id : str
        Subject identifier matching the m2m directory name.
    leadfield_hdf : str
        Filename of the precomputed leadfield HDF5 (e.g.
        ``"ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5"``), resolved under
        the subject's ``leadfields/`` directory
        (:meth:`tit.paths.PathManager.leadfields`); an absolute path is
        also accepted.
    roi_name : str
        ROI CSV filename (e.g. ``"target.csv"``) in the subject's ``ROIs/``
        directory (:meth:`tit.paths.PathManager.rois`).  The ``".csv"``
        suffix is appended automatically if missing.  Used as the
        metric-key prefix and (with the net name) the output-directory
        label.
    roi_names : list of str or None
        Optional list of ROI CSV filenames to **union** into a single
        target.  When provided (combined mode), the spherical masks of
        every listed ROI are OR-folded into one region.  ``None``
        (default) keeps single-ROI behavior driven by *roi_name*.  An
        explicit empty list means "no spherical centers at all" -- useful
        for a purely atlas-driven ROI (*roi_atlas* only).  Each entry gets
        the ``".csv"`` suffix appended if missing.
    roi_atlas : list of AtlasROI or None
        Volumetric atlas or mask ROI(s) to union with the spherical
        centers from *roi_name*/*roi_names*.  ``None`` (default) keeps
        the existing spherical-only behavior.
    roi_coordinate_space : str
        Space of the *roi_name*/*roi_names* CSV centers -- ``"subject"``
        (default) or ``"mni"``.  MNI centers are transformed to subject
        space with ``simnibs.mni2subject_coords`` before the search runs.
        Does not affect *roi_atlas*, which declares its own atlas_space.
    electrodes : BucketElectrodes or PoolElectrodes
        Electrode specification, either a single shared pool
        (:class:`PoolElectrodes`) or separate per-channel buckets
        (:class:`BucketElectrodes`).  A plain dict is auto-converted
        in ``__post_init__``.
    total_current : float
        Total injected current in mA, split across the two channels.
        Default ``2.0``.
    current_step : float
        Current amplitude step size in mA for the sweep.  Default ``0.5``.
    channel_limit : float or None
        Maximum current per channel in mA.  ``None`` (default) means
        ``total_current - current_step``.
    roi_radius : float
        Spherical ROI radius in mm for the target region.  Default ``3.0``.
    run_name : str or None
        Optional name for this run.  Defaults to a datetime stamp.  The
        run name is the output directory, so a repeated name overwrites
        the earlier run in place.
    n_jobs : int
        Worker processes evaluating candidates in parallel.  ``-1``
        (default) uses the global CPU limit (Settings; 70 % of the
        container's cores by default, see :func:`tit.cpu.cpu_limit`);
        a larger explicit value is clamped to that limit; ``1``
        evaluates in-process.  Results and CSV ordering do not depend
        on it.
    symmetric_bucket : bool
        When True in bucket mode, evaluate only left/right mirrored
        montages (see :func:`tit.opt.ex.buckets.build_electrode_mirror_map`).
    symmetry_eeg_csv : str or None
        EEG-position CSV used to derive mirrored electrode pairs.  If
        unset, it is inferred from the leadfield's net name.
    symmetry_pairing : str
        Symmetry interpretation when *symmetric_bucket* is True.
        ``"within_pairs"``: each pair's minus electrode is the mirror of
        its plus electrode (e.g. F7-F8).  ``"cross_pairs"``: pair 2 is the
        mirror image of pair 1 (``e2+ = mirror(e1+)``, ``e2- = mirror(e1-)``).

    Raises
    ------
    ValueError
        If *current_step*, *total_current*, or *channel_limit* are
        non-positive, if *symmetric_bucket* is set with pool electrodes,
        if *symmetry_pairing* is not ``"within_pairs"``/``"cross_pairs"``,
        or if *roi_coordinate_space* is not ``"subject"`` or ``"mni"``.

    Examples
    --------
    >>> from tit.opt import ExConfig
    >>> cfg = ExConfig(
    ...     subject_id="ernie",
    ...     leadfield_hdf="ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
    ...     roi_name="L-Insula",                 # ".csv" is appended
    ...     electrodes=ExConfig.PoolElectrodes(
    ...         electrodes=["Fp1", "Fp2", "C3", "C4", "Cz", "Pz", "T7", "T8"]),
    ...     total_current=2.0, current_step=0.5, channel_limit=1.2,
    ...     roi_coordinate_space="mni",
    ... )
    >>> cfg.roi_name
    'L-Insula.csv'

    Per-channel buckets instead of one pool:

    >>> ExConfig.BucketElectrodes(e1_plus=["F7"], e1_minus=["F8"],
    ...                           e2_plus=["P7"], e2_minus=["P8"]).e2_minus
    ['P8']

    Then ``run_ex_search(cfg)`` (needs the leadfield HDF5 under the
    subject's leadfield folder).

    See Also
    --------
    ExResult : Result container returned by :func:`~tit.opt.ex.ex.run_ex_search`.
    tit.opt.ex.ex.run_ex_search : Consumes this config.
    """

    # ── Nested ROI types ─────────────────────────────────────────────────
    @dataclass
    class AtlasROI:
        """Volumetric atlas or mask ROI, unioned with the spherical center(s).

        Attributes
        ----------
        atlas_path : str
            Path to a volumetric atlas or mask file -- NIfTI (``.nii``,
            ``.nii.gz``) or FreeSurfer (``.mgz``), e.g. one discovered by
            :class:`tit.atlas.voxel.VoxelAtlasManager`.
        label : int or None
            Integer label to select within the atlas (elements are
            included where the voxel value equals *label*).  ``None``
            treats the whole file as a binary mask (voxel value ``> 0``).
        atlas_space : str
            Space of the atlas file, ``"subject"`` (default) or ``"mni"``.
            MNI masks are warped to subject space before the search.

        Raises
        ------
        ValueError
            If *atlas_space* is not ``"subject"`` or ``"mni"``.
        """

        atlas_path: str
        label: int | None = None
        atlas_space: Literal["subject", "mni"] = "subject"

        def __post_init__(self):
            if self.atlas_space not in ("subject", "mni"):
                raise ValueError("atlas_space must be subject or mni")

    # ── Nested electrode types ─────────────────────────────────────────
    @dataclass
    class BucketElectrodes:
        """Separate electrode lists for each bipolar channel position.

        Attributes
        ----------
        e1_plus : list of str
            Candidate electrodes for channel 1 anode.
        e1_minus : list of str
            Candidate electrodes for channel 1 cathode.
        e2_plus : list of str
            Candidate electrodes for channel 2 anode.
        e2_minus : list of str
            Candidate electrodes for channel 2 cathode.
        """

        e1_plus: list[str]
        e1_minus: list[str]
        e2_plus: list[str]
        e2_minus: list[str]

    @dataclass
    class PoolElectrodes:
        """Single electrode pool -- all positions draw from the same set.

        Attributes
        ----------
        electrodes : list of str
            List of electrode names available for any channel position.
        """

        electrodes: list[str]

    # ── Required fields ────────────────────────────────────────────────
    subject_id: str
    leadfield_hdf: str
    roi_name: str
    electrodes: BucketElectrodes | PoolElectrodes

    # ── Current parameters ────────────────────────────────────────────
    total_current: float = 2.0
    current_step: float = 0.5
    channel_limit: float | None = None

    # ── ROI ────────────────────────────────────────────────────────────
    roi_radius: float = 3.0
    roi_names: list[str] | None = None
    roi_atlas: list[AtlasROI] | None = None
    roi_coordinate_space: Literal["subject", "mni"] = "subject"

    # ── Output naming (defaults to datetime stamp) ─────────────────────
    run_name: str | None = None

    # ── Parallelism ────────────────────────────────────────────────────
    n_jobs: int = -1

    # ── Symmetric bucket search ─────────────────────────────────────────
    symmetric_bucket: bool = False
    symmetry_eeg_csv: str | None = None
    symmetry_pairing: str = "within_pairs"

    def __post_init__(self):
        if isinstance(self.electrodes, dict):
            if "electrodes" in self.electrodes:
                self.electrodes = ExConfig.PoolElectrodes(**self.electrodes)
            else:
                self.electrodes = ExConfig.BucketElectrodes(**self.electrodes)
        if not self.roi_name.endswith(".csv"):
            self.roi_name += ".csv"
        if self.roi_names is not None:
            self.roi_names = [
                n if n.endswith(".csv") else f"{n}.csv" for n in self.roi_names
            ]
        if self.roi_atlas is not None:
            self.roi_atlas = [
                a if isinstance(a, ExConfig.AtlasROI) else ExConfig.AtlasROI(**a)
                for a in self.roi_atlas
            ]
        if self.roi_names == [] and not self.roi_atlas:
            raise ValueError(
                "roi_names=[] means 'no spherical centers', which requires at "
                "least one roi_atlas target; otherwise the ROI is empty"
            )
        self.roi_coordinate_space = str(self.roi_coordinate_space).strip().lower()
        if self.roi_coordinate_space not in ("subject", "mni"):
            raise ValueError(
                "roi_coordinate_space must be 'subject' or 'mni' (was "
                f"{self.roi_coordinate_space!r})"
            )

        # Validation
        if self.current_step <= 0:
            raise ValueError("current_step must be positive")
        if self.total_current <= 0:
            raise ValueError("total_current must be positive")
        if self.channel_limit is not None and self.channel_limit <= 0:
            raise ValueError("channel_limit must be positive")
        if self.symmetric_bucket and isinstance(
            self.electrodes, ExConfig.PoolElectrodes
        ):
            raise ValueError("symmetric_bucket is only supported for bucket electrodes")
        if self.symmetry_pairing not in ("within_pairs", "cross_pairs"):
            raise ValueError("symmetry_pairing must be 'within_pairs' or 'cross_pairs'")


@dataclass
class ExResult:
    """Result from an exhaustive search run.

    Attributes
    ----------
    success : bool
        True if the search completed without error.
    output_dir : str
        Absolute path to the output directory.
    n_combinations : int
        Total number of electrode/current combinations evaluated.
    results_csv : str or None
        Path to the CSV file containing ranked results.  ``None`` if the
        run failed before writing results.
    config_json : str or None
        Path to the saved configuration JSON.  ``None`` if the run failed
        before writing config.

    See Also
    --------
    ExConfig : Configuration consumed by :func:`~tit.opt.ex.ex.run_ex_search`.
    tit.opt.ex.ex.run_ex_search : Returns this result.
    """

    success: bool
    output_dir: str
    n_combinations: int
    results_csv: str | None = None
    config_json: str | None = None


# ── Multipolar exhaustive search config ──────────────────────────────────────


@dataclass
class MExConfig:
    """Full configuration for multipolar (4-pair, 8-electrode) exhaustive search.

    Evaluates every valid combination of four bipolar electrode pairs from
    a user-defined pool or bucket set, at one fixed current per pair, and
    scores each candidate with the verified N>2 mTI envelope
    (:func:`tit.calc.get_TI_vectors`).

    Attributes
    ----------
    subject_id : str
        Subject identifier matching the m2m directory name.
    leadfield_hdf : str
        Filename of the precomputed leadfield HDF5, resolved under the
        subject's ``leadfields/`` directory (an absolute path also works).
    roi_name : str
        ROI CSV filename (e.g. ``"target.csv"``) in the subject's ``ROIs/``
        directory.  The ``".csv"`` suffix is appended automatically if
        missing.
    electrodes : BucketElectrodes or PoolElectrodes
        Electrode specification, either a single shared pool
        (:class:`PoolElectrodes`) or four separate per-pair buckets
        (:class:`BucketElectrodes`).  A plain dict is auto-converted in
        ``__post_init__``.
    current_mA : float
        Current in mA delivered by each of the four pairs.  Default ``2.0``.
    roi_radius : float
        Spherical ROI radius in mm for the target region.  Default ``3.0``.
    roi_names : list of str or None
        Optional list of ROI CSV filenames to **union** into a single
        target.  ``None`` (default) keeps single-ROI behavior driven by
        *roi_name*.  An explicit empty list means "no spherical centers at
        all" -- required for a purely atlas-driven ROI (*roi_atlas* only),
        in which case *roi_name* is only a naming label and no CSV is read.
        Each entry gets the ``".csv"`` suffix appended if missing.
    roi_atlas : list of AtlasROI or None
        Volumetric atlas or mask ROI(s) to union with the spherical center
        from *roi_name*.  ``None`` (default) keeps the existing
        spherical-only behavior.
    roi_coordinate_space : str
        Space of the *roi_name* CSV center -- ``"subject"`` (default) or
        ``"mni"``.  An MNI center is transformed to subject space with
        ``simnibs.mni2subject_coords`` before the search runs.  Does not
        affect *roi_atlas*, which declares its own atlas_space.
    run_name : str or None
        Optional name for this run.  Defaults to a datetime stamp.
    n_jobs : int
        Worker processes evaluating candidates in parallel.  ``-1``
        (default) uses the global CPU limit (Settings; 70 % of the
        container's cores by default, see :func:`tit.cpu.cpu_limit`);
        a larger explicit value is clamped to that limit; ``1``
        evaluates in-process.  Results and CSV ordering do not depend
        on it.
    symmetric_bucket : bool
        When True in bucket mode, evaluate only left/right mirrored
        electrode pairs (see :func:`tit.opt.ex.buckets.build_electrode_mirror_map`).
    symmetry_eeg_csv : str or None
        EEG-position CSV used to derive mirrored electrode pairs.  If
        unset, it is inferred from the leadfield's net name.
    symmetry_pairing : str
        Symmetry interpretation for bucket mode when *symmetric_bucket*
        is True.  ``"within_pairs"`` mirrors each pair's plus/minus
        electrodes independently; ``"cross_pairs"`` additionally mirrors
        pair 1<->3 and pair 2<->4.

    Raises
    ------
    ValueError
        If *current_mA* is non-positive, if *symmetric_bucket* is set
        with pool electrodes, if *symmetry_pairing* is not one of
        ``"within_pairs"``/``"cross_pairs"``, or if *roi_coordinate_space*
        is not ``"subject"`` or ``"mni"``.

    Examples
    --------
    >>> from tit.opt import MExConfig
    >>> cfg = MExConfig(
    ...     subject_id="ernie",
    ...     leadfield_hdf="ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
    ...     roi_name="L-Insula",
    ...     electrodes=MExConfig.PoolElectrodes(
    ...         electrodes=["Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4", "O1", "O2"]),
    ...     current_mA=1.0,
    ... )
    >>> cfg.roi_name, cfg.current_mA
    ('L-Insula.csv', 1.0)

    Then ``run_m_ex_search(cfg)``.

    See Also
    --------
    MExResult : Result container returned by :func:`~tit.opt.mex.mex.run_m_ex_search`.
    tit.opt.mex.mex.run_m_ex_search : Consumes this config.
    tit.calc.get_TI_vectors : Modulation-amplitude envelope.
    """

    # ── Nested ROI types ─────────────────────────────────────────────────
    @dataclass
    class AtlasROI:
        """Volumetric atlas or mask ROI, unioned with the spherical center.

        Attributes
        ----------
        atlas_path : str
            Path to a volumetric atlas or mask file -- NIfTI (``.nii``,
            ``.nii.gz``) or FreeSurfer (``.mgz``), e.g. one discovered by
            :class:`tit.atlas.voxel.VoxelAtlasManager`.
        label : int or None
            Integer label to select within the atlas (elements are
            included where the voxel value equals *label*).  ``None``
            treats the whole file as a binary mask (voxel value ``> 0``).
        atlas_space : str
            Space of the atlas file, ``"subject"`` (default) or ``"mni"``.
            MNI masks are warped to subject space before the search.

        Raises
        ------
        ValueError
            If *atlas_space* is not ``"subject"`` or ``"mni"``.
        """

        atlas_path: str
        label: int | None = None
        atlas_space: Literal["subject", "mni"] = "subject"

        def __post_init__(self):
            if self.atlas_space not in ("subject", "mni"):
                raise ValueError("atlas_space must be subject or mni")

    # ── Nested electrode types ─────────────────────────────────────────
    @dataclass
    class BucketElectrodes:
        """Separate electrode lists for each of the four bipolar pairs.

        Attributes
        ----------
        e1_plus, e1_minus, e2_plus, e2_minus, e3_plus, e3_minus, e4_plus, e4_minus : list of str
            Candidate electrodes for each pair's anode/cathode position.
        """

        e1_plus: list[str]
        e1_minus: list[str]
        e2_plus: list[str]
        e2_minus: list[str]
        e3_plus: list[str]
        e3_minus: list[str]
        e4_plus: list[str]
        e4_minus: list[str]

    @dataclass
    class PoolElectrodes:
        """Single electrode pool -- all eight positions draw from the same set.

        Attributes
        ----------
        electrodes : list of str
            List of electrode names available for any pair position.
        """

        electrodes: list[str]

    # ── Required fields ────────────────────────────────────────────────
    subject_id: str
    leadfield_hdf: str
    roi_name: str
    electrodes: "MExConfig.BucketElectrodes | MExConfig.PoolElectrodes"

    # ── Current ─────────────────────────────────────────────────────────
    current_mA: float = 2.0

    # ── ROI ────────────────────────────────────────────────────────────
    roi_radius: float = 3.0
    roi_names: list[str] | None = None
    roi_atlas: list[AtlasROI] | None = None
    roi_coordinate_space: Literal["subject", "mni"] = "subject"

    # ── Output naming (defaults to datetime stamp) ─────────────────────
    run_name: str | None = None

    # ── Parallelism ────────────────────────────────────────────────────
    n_jobs: int = -1

    # ── Symmetric bucket search ─────────────────────────────────────────
    symmetric_bucket: bool = False
    symmetry_eeg_csv: str | None = None
    symmetry_pairing: str = "within_pairs"

    def __post_init__(self):
        if isinstance(self.electrodes, dict):
            if "electrodes" in self.electrodes:
                self.electrodes = MExConfig.PoolElectrodes(**self.electrodes)
            else:
                self.electrodes = MExConfig.BucketElectrodes(**self.electrodes)
        if not self.roi_name.endswith(".csv"):
            self.roi_name += ".csv"
        if self.roi_names is not None:
            self.roi_names = [
                n if n.endswith(".csv") else f"{n}.csv" for n in self.roi_names
            ]
        if self.roi_atlas is not None:
            self.roi_atlas = [
                a if isinstance(a, MExConfig.AtlasROI) else MExConfig.AtlasROI(**a)
                for a in self.roi_atlas
            ]
        if self.roi_names == [] and not self.roi_atlas:
            raise ValueError(
                "roi_names=[] means 'no spherical centers', which requires at "
                "least one roi_atlas target; otherwise the ROI is empty"
            )
        self.roi_coordinate_space = str(self.roi_coordinate_space).strip().lower()
        if self.roi_coordinate_space not in ("subject", "mni"):
            raise ValueError(
                "roi_coordinate_space must be 'subject' or 'mni' (was "
                f"{self.roi_coordinate_space!r})"
            )

        if self.current_mA <= 0:
            raise ValueError("current_mA must be positive")
        if self.symmetric_bucket and isinstance(
            self.electrodes, MExConfig.PoolElectrodes
        ):
            raise ValueError("symmetric_bucket is only supported for bucket electrodes")
        if self.symmetry_pairing not in ("within_pairs", "cross_pairs"):
            raise ValueError("symmetry_pairing must be 'within_pairs' or 'cross_pairs'")


@dataclass
class MExResult:
    """Result from a multipolar exhaustive search run.

    Attributes
    ----------
    success : bool
        True if the search completed without error.
    output_dir : str
        Absolute path to the output directory.
    n_combinations : int
        Total number of eight-electrode combinations evaluated.
    results_csv : str or None
        Path to the CSV file containing ranked results.  ``None`` if the
        run failed before writing results.
    config_json : str or None
        Path to the saved configuration JSON.  ``None`` if the run failed
        before writing config.

    See Also
    --------
    MExConfig : Configuration consumed by :func:`~tit.opt.mex.mex.run_m_ex_search`.
    tit.opt.mex.mex.run_m_ex_search : Returns this result.
    """

    success: bool
    output_dir: str
    n_combinations: int
    results_csv: str | None = None
    config_json: str | None = None


#: Exhaustive-search modes. ``TI`` searches two bipolar pairs, ``mTI`` four.
SEARCH_MODE_TI = "TI"
SEARCH_MODE_MTI = "mTI"


def search_backend_for_mode(mode):
    """Return ``(module path, config class)`` for an exhaustive-search mode.

    Args:
        mode: :data:`SEARCH_MODE_TI` or :data:`SEARCH_MODE_MTI`.

    Returns:
        ``(module_path, config_class)``; *module_path* is passed to
        ``simnibs_python -m <module_path>`` and *config_class* is the
        dataclass to build for that mode.

    Raises:
        ValueError: If *mode* is not a known search mode.
    """
    if mode == SEARCH_MODE_TI:
        return "tit.opt.ex", ExConfig
    if mode == SEARCH_MODE_MTI:
        return "tit.opt.mex", MExConfig
    raise ValueError(f"Unknown search mode: {mode!r}")
