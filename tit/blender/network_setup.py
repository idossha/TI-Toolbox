"""Automatic render setup of a named network: one pure, deterministic function.

:func:`resolve_network_setup` turns a :class:`~tit.tract.config.Selection` and its streamline
counts per edge into every setting a network render needs, so any network reads well with no
tuning. The Plan shows the result before anything renders, the render's ``manifest.json`` records
it, and a key of ``TractVisualConfig.overrides`` replaces any one value.

Counts per edge are all it reads, so the Plan (``network.npz``) and the render (the assessed
bundle) reach the same answer, and nothing here looks at a field value: the choice of what to draw
never favours a metric. Standard library only.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from typing import Any

#: A network's figure: these four panels, two to a row, left to right and top to bottom.
PANELS = ("lateral", "superior", "anterior", "posterior")

#: Each hemisphere holds at least this share of the ends: bilateral, and its lateral panel shows left.
BILATERAL_MIN_SHARE = 0.25
#: Highlighted when no seed names itself: the two busiest ends of the network.
BUSIEST_ENDPOINTS = 2
#: Above this many streamlines tubes merge into one mass; an even sample is drawn and stated.
STREAMLINE_BUDGET = 8_000
#: Tube radius of a network of at least REFERENCE_STREAMLINES, the approved render's look.
TUBE_RADIUS_MM = 0.09
REFERENCE_STREAMLINES = 1_598
#: A thin network's tubes widen as sqrt(1/n) up to this factor, or a few fibres cannot be seen.
TUBE_MAX_WIDENING = 4.0
#: The TI_max shell's volume-weighted brain percentile.
SHELL_PERCENTILE = 95.0
#: Below this many streamlines there are too few fibres to judge against a shell, which hides them.
SHELL_MIN_STREAMLINES = 10

OVERRIDABLE = (
    "highlight_regions",
    "lateral_side",
    "max_streamlines",
    "tube_radius_mm",
    "vmax_v_per_m",
    "iso_shell_percentile",
)

#: DK40 parcel names as words, for the thalamocortical sequence's labels.
DK40_WORDS = {
    "superiorfrontal": "superior frontal",
    "rostralmiddlefrontal": "rostral middle frontal",
    "caudalmiddlefrontal": "caudal middle frontal",
    "parsopercularis": "pars opercularis",
    "parstriangularis": "pars triangularis",
    "parsorbitalis": "pars orbitalis",
    "lateralorbitofrontal": "lateral orbitofrontal",
    "medialorbitofrontal": "medial orbitofrontal",
    "frontalpole": "frontal pole",
    "precentral": "precentral",
    "paracentral": "paracentral",
    "superiorparietal": "superior parietal",
    "inferiorparietal": "inferior parietal",
    "supramarginal": "supramarginal",
    "postcentral": "postcentral",
    "precuneus": "precuneus",
    "lateraloccipital": "lateral occipital",
    "lingual": "lingual",
    "cuneus": "cuneus",
    "pericalcarine": "pericalcarine",
    "superiortemporal": "superior temporal",
    "middletemporal": "middle temporal",
    "inferiortemporal": "inferior temporal",
    "bankssts": "banks of the STS",
    "fusiform": "fusiform",
    "transversetemporal": "transverse temporal",
    "temporalpole": "temporal pole",
    "entorhinal": "entorhinal",
    "parahippocampal": "parahippocampal",
    "caudalanteriorcingulate": "caudal anterior cingulate",
    "isthmuscingulate": "isthmus cingulate",
    "posteriorcingulate": "posterior cingulate",
    "rostralanteriorcingulate": "rostral anterior cingulate",
    "insula": "insula",
}


def region_words(name: str) -> str:
    """``"lh.superiorfrontal"`` -> ``"L superior frontal"``; other names unchanged."""
    hemi, _, parcel = name.partition(".")
    if hemi in ("lh", "rh") and parcel:
        return f"{hemi[0].upper()} {DK40_WORDS.get(parcel, parcel)}"
    return name


def region_hemi(name: str) -> int:
    """-1 for a left region, 1 for a right one, 0 for one on the midline (``Brain-Stem``)."""
    if name.startswith(("lh.", "Left-", "ctx-lh-", "ctx_lh_")):
        return -1
    if name.startswith(("rh.", "Right-", "ctx-rh-", "ctx_rh_")):
        return 1
    return 0


def validate_overrides(overrides: Mapping[str, Any]) -> None:
    """Refuse an unknown key or a value no render can use. ``ValueError`` names which."""
    unknown = sorted(set(overrides) - set(OVERRIDABLE))
    if unknown:
        raise ValueError(f"unknown overrides {unknown}; allowed: {OVERRIDABLE}")
    if overrides.get("lateral_side", -1) not in (-1, 1):
        raise ValueError("overrides.lateral_side is -1 or 1")
    for key in ("max_streamlines", "tube_radius_mm", "vmax_v_per_m"):
        value = overrides.get(key)
        if value is not None and not value > 0:
            raise ValueError(f"overrides.{key} must be > 0")
    shell = overrides.get("iso_shell_percentile")
    if shell is not None and not 0 < shell < 100:
        raise ValueError("overrides.iso_shell_percentile must be in (0, 100), or null")


def resolve_network_setup(
    selection,
    counts: Mapping[tuple[str, str], int],
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Every setting of one network's render, from its edges alone.

    Args:
        selection: A ``Selection`` of kind ``"edges"``; ``regions`` holds its seeds, if any.
        counts: Streamlines per edge, keyed by ``(region_a, region_b)`` in either order. An edge
            of ``selection.pairs`` absent here holds no streamline.
        overrides: Keys of :data:`OVERRIDABLE` replacing the automatic value.

    Returns:
        ``values`` (the settings), ``reasons`` (one sentence per automatic value), ``overridden``
        (the keys the user set), ``n_streamlines`` and ``n_drawn``.
    """
    per_pair = {frozenset(pair): int(n) for pair, n in counts.items()}
    ends: Counter[str] = Counter()
    for a, b in selection.pairs:
        n = per_pair.get(frozenset((a, b)), 0)
        ends[a] += n
        ends[b] += n
    n_streamlines = sum(ends.values()) // 2
    # Sorted by count, then name: a tie must not depend on the order the pairs came in.
    regions = sorted(ends, key=lambda r: (-ends[r], r))

    left = sum(n for r, n in ends.items() if region_hemi(r) == -1)
    right = sum(n for r, n in ends.items() if region_hemi(r) == 1)
    sided = left + right
    bilateral = sided == 0 or min(left, right) / sided >= BILATERAL_MIN_SHARE
    seeds = [r for r in selection.regions if ends.get(r)]

    values: dict[str, Any] = {
        "highlight_regions": seeds or regions[:BUSIEST_ENDPOINTS],
        "lateral_side": 1 if right > left and not bilateral else -1,
        "max_streamlines": STREAMLINE_BUDGET,
        "tube_radius_mm": TUBE_RADIUS_MM
        * min(
            TUBE_MAX_WIDENING,
            max(1.0, math.sqrt(REFERENCE_STREAMLINES / max(n_streamlines, 1))),
        ),
        "vmax_v_per_m": None,
        "iso_shell_percentile": (
            SHELL_PERCENTILE if n_streamlines >= SHELL_MIN_STREAMLINES else None
        ),
    }
    side = "left" if values["lateral_side"] < 0 else "right"
    reasons = {
        "highlight_regions": (
            "The regions it was chosen by."
            if seeds
            else "No seed: the busiest ends of the network."
        ),
        "lateral_side": (
            f"Both hemispheres hold a quarter of its ends or more ({left} left, {right} right): "
            "the lateral panel shows the left."
            if bilateral
            else f"The {side} side holds more of its ends ({left} left, {right} right)."
        ),
        "max_streamlines": (
            f"Above {STREAMLINE_BUDGET:,} an even sample is drawn, and network.json says so."
        ),
        "tube_radius_mm": "A thin network's tubes widen so a few fibres can be seen.",
        "vmax_v_per_m": "The top of the colours: the 99.5th percentile along the drawn fibres.",
        "iso_shell_percentile": (
            f"Brain p{SHELL_PERCENTILE:g} of TI_max."
            if values["iso_shell_percentile"]
            else f"Off: under {SHELL_MIN_STREAMLINES} streamlines, which a shell would hide."
        ),
    }
    overrides = dict(overrides or {})
    values.update(overrides)
    for key in overrides:
        reasons.pop(key, None)
    return {
        "values": values,
        "reasons": reasons,
        "overridden": sorted(overrides),
        "n_streamlines": n_streamlines,
        "n_drawn": min(n_streamlines, int(values["max_streamlines"])),
    }
