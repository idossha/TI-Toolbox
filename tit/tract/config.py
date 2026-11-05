"""Configuration dataclasses for :mod:`tit.tract` (white-matter network targeting).

One :class:`TractConfig` drives ``simnibs_python -m tit.tract config.json`` through any of
its four stages, in order: ``track`` (whole-brain tractogram), ``network`` (endpoint
labels and the region x region connectome), ``assess`` (TI fields on the streamlines of
one or more simulations) and ``target`` (a tract-density ROI mask for the optimizers and a
direction-aware montage ranking).

No field has a stimulation threshold by default: ``AssessConfig.thresholds`` is empty
unless the user supplies values, and no metric is designated over another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

#: Stages, in the order the runner executes them.
STAGES = ("track", "network", "assess", "target")
SELECTION_KINDS = (
    "all",
    "between",
    "edges",
    "from",
    "through",
    "to_cortex",
    "top_edges",
)


def _positive(value: float, name: str) -> None:
    if not value > 0:
        raise ValueError(f"{name} must be > 0 (was {value!r})")


@dataclass
class Selection:
    """A named subset of the whole-brain tractogram.

    Attributes:
        name: Output stem (``<name>.trx``); letters, digits, ``_`` and ``-``.
        kind: ``"all"``; ``"between"`` (one end in ``regions[0]``, the other in
            ``regions[1]``); ``"edges"`` (the union of the region pairs in ``pairs``);
            ``"from"`` (either end in any of ``regions``); ``"through"``
            (any point inside ``mask_path``, or inside label ``label`` of it);
            ``"to_cortex"`` (one end in any of ``regions``, the other in a cortical label:
            ``lh.``/``rh.`` annotation or ``ctx-`` volume names; e.g. thalamocortical);
            ``"top_edges"`` (the ``k`` edges of ``regions[0]`` with most streamlines).
        regions: Region names as the network stage names them (``"lh.insula"`` for a
            cortical annotation label, the label table name such as ``"Left-Thalamus-Proper"``
            for a volume label).
        mask_path: NIfTI in m2m T1 space, for ``"through"``.
        label: Integer label inside ``mask_path``; ``None`` means every voxel > 0.
        k: Edge count for ``"top_edges"``.
        pairs: Region-name pairs ``[[a, b], ...]`` for ``"edges"``; order inside a pair does
            not matter. Names, not edge ids: ids renumber when the network is rebuilt.
    """

    name: str = "all"
    kind: Literal[
        "all", "between", "edges", "from", "through", "to_cortex", "top_edges"
    ] = "all"
    regions: list[str] = field(default_factory=list)
    mask_path: str | None = None
    label: int | None = None
    k: int = 5
    pairs: list[list[str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind not in SELECTION_KINDS:
            raise ValueError(f"Selection kind must be one of {SELECTION_KINDS}")
        if not self.name or not all(c.isalnum() or c in "_-" for c in self.name):
            raise ValueError(f"Selection name {self.name!r}: use letters, digits, _ -")
        need = {"between": 2, "from": 1, "to_cortex": 1, "top_edges": 1}.get(
            self.kind, 0
        )
        if len(self.regions) < need:
            raise ValueError(f"{self.kind!r} needs {need} region(s)")
        if self.kind == "through" and not self.mask_path:
            raise ValueError("'through' needs mask_path")
        if self.kind == "edges" and (
            not self.pairs or any(len(p) != 2 for p in self.pairs)
        ):
            raise ValueError("'edges' needs pairs: [[region_a, region_b], ...]")


@dataclass
class TrackConfig:
    """Whole-brain tractography (the ``track`` stage).

    QSIPrep-preprocessed DWI, single-shell CSD on b0 + one shell, ACT on charm
    tissues, DIPY probabilistic tracking. A subject without QSIPrep output is refused.

    Attributes:
        pmf_threshold: Fibre-ODF values below this fraction are not followed.
        n_seeds: Random seeds placed in white matter.
        step_mm: Tracking step.
        max_angle: Maximum turning angle per step, degrees.
        min_length_mm, max_length_mm: Streamline length window.
        sh_order: CSD spherical-harmonic order.
        shell: CSD shell b-value; ``None`` = the shell closest to b3000 among shells with
            >= 30 directions (``tracking.pick_shell``).
        random_seed: Tracking and seeding RNG seed (> 0 is reproducible).
        n_jobs: Worker threads/processes; ``-1`` = the job CPU budget.
        flip_test: Run the 8 gradient-axis-flip frame check (coherence with the DTI V1).
        export_acpc_tck: Also write ``tractogram_acpc.tck`` in QSIPrep ACPC world.
        overwrite: Replace an existing tractogram.
    """

    pmf_threshold: float = 0.1
    n_seeds: int = 200_000
    step_mm: float = 0.5
    max_angle: float = 30.0
    min_length_mm: float = 20.0
    max_length_mm: float = 250.0
    sh_order: int = 8
    shell: float | None = None
    random_seed: int = 1
    n_jobs: int = -1
    flip_test: bool = True
    export_acpc_tck: bool = True
    overwrite: bool = False

    def __post_init__(self) -> None:
        for name in ("n_seeds", "step_mm", "max_angle", "min_length_mm"):
            _positive(getattr(self, name), name)
        if self.max_length_mm <= self.min_length_mm:
            raise ValueError("max_length_mm must exceed min_length_mm")


@dataclass
class NetworkConfig:
    """Endpoint-to-region association (the ``network`` stage).

    Attributes:
        atlas: Cortical annotation name in ``m2m/segmentation`` (``"DK40"`` ->
            ``lh.<sid>_DK40.annot``). Without annotations every region comes from the
            label volume.
        label_volume: Volume atlas for subcortical (and, without annotations, cortical)
            labels; default: charm ``segmentation/labeling.nii.gz``, else FastSurfer
            ``aparc.DKTatlas+aseg.deep.nii.gz``.
        surface: m2m surface the annotation labels sit on (``central``, ``white``, ``pial``).
        radius_mm: An endpoint takes the nearest labelled vertex or voxel within this
            distance, else it is unassigned (-1).
    """

    atlas: str = "DK40"
    label_volume: str | None = None
    surface: str = "central"
    radius_mm: float = 3.0

    def __post_init__(self) -> None:
        _positive(self.radius_mm, "radius_mm")


@dataclass
class AssessConfig:
    """TI fields along streamlines (the ``assess`` stage).

    Attributes:
        simulations: Simulation folder names under ``Simulations/``.
        selections: Bundles to write; each gets ``<name>.trx`` in ``Simulations/<sim>/tract/``.
            Edges, connectomes and per-streamline metrics always cover every streamline.
        step_mm: Uniform arc-length step the streamlines are resampled to before sampling.
            The activating function converges once the step is at most a quarter of
            ``af_scale_mm`` (on ernie, 0.5 vs 0.25 mm moves its median maximum by 1 %).
        af_scale_mm: Half-width of the triangle the activating function's ``E . t`` is
            smoothed over before differentiating (a piecewise-constant field has no
            pointwise derivative at a finite scale otherwise).
        thresholds: User thresholds (V/m) for the fraction-above summaries; none by default.
        profile_points: Nodes of the along-tract profiles.
        min_streamlines: Edges with fewer streamlines are left out of the ``top_edges``
            ranking in ``summary.json`` (they stay in every raw output).
    """

    simulations: list[str] = field(default_factory=list)
    selections: list[Selection] = field(default_factory=lambda: [Selection()])
    step_mm: float = 0.5
    af_scale_mm: float = 2.0
    thresholds: list[float] = field(default_factory=list)
    profile_points: int = 100
    min_streamlines: int = 5

    def __post_init__(self) -> None:
        _positive(self.step_mm, "step_mm")
        _positive(self.af_scale_mm, "af_scale_mm")
        if self.profile_points < 2:
            raise ValueError("profile_points must be >= 2")
        names = [s.name for s in self.selections]
        if len(set(names)) != len(names):
            raise ValueError(f"selection names must be unique: {names}")


@dataclass
class TargetConfig:
    """Tract-density ROI and direction-aware ranking (the ``target`` stage).

    Attributes:
        selection: The bundle the mask is made from.
        min_count: Voxels crossed by at least this many streamlines are in the mask.
        leadfield_hdf: Leadfield for the ranking (name under ``leadfields/`` or a path);
            ``None`` skips the ranking.
        ex_run: ex-search run whose ``final_output.csv`` montages are ranked.
        montages: Explicit montages ``[e1+, e1-, e2+, e2-]`` to rank.
        pool: Electrodes whose every two-pair montage is ranked.
        top_n: Montages read from ``ex_run`` (its top rows by composite index).
        current_mA: Channel currents for the ranking.
    """

    selection: Selection = field(default_factory=Selection)
    min_count: int = 1
    leadfield_hdf: str | None = None
    ex_run: str | None = None
    montages: list[list[str]] = field(default_factory=list)
    pool: list[str] = field(default_factory=list)
    top_n: int = 20
    current_mA: list[float] = field(default_factory=lambda: [1.0, 1.0])

    def __post_init__(self) -> None:
        if self.min_count < 1:
            raise ValueError("min_count must be >= 1")
        if any(len(m) != 4 for m in self.montages):
            raise ValueError("each montage is [e1+, e1-, e2+, e2-]")


@dataclass
class TractConfig:
    """One ``tit.tract`` run for one subject.

    Attributes:
        subject_id: Subject (without ``sub-``).
        stages: Any of :data:`STAGES`; run in that order.
        skip_existing: A track or network stage whose output exists is skipped (a network only
            when it was built with this atlas), the Pre-processing page's "skip" policy.
    """

    subject_id: str
    stages: list[str] = field(default_factory=lambda: ["track", "network", "assess"])
    track: TrackConfig = field(default_factory=TrackConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    assess: AssessConfig = field(default_factory=AssessConfig)
    target: TargetConfig = field(default_factory=TargetConfig)
    skip_existing: bool = False

    def __post_init__(self) -> None:
        bad = [s for s in self.stages if s not in STAGES]
        if bad or not self.stages:
            raise ValueError(
                f"stages must be a non-empty subset of {STAGES} (got {bad})"
            )
        if "assess" in self.stages and not self.assess.simulations:
            raise ValueError("the assess stage needs assess.simulations")
