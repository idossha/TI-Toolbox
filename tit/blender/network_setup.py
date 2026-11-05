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
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

#: The two stills of a network: from behind and above when both hemispheres hold it, where a side
#: view shows half; from its own side and obliquely when it lies mostly on one.
BILATERAL_VIEWS = ("posterior", "superior")
ONE_SIDE_VIEWS = ("lateral", "oblique")
#: Every view a config may ask for.
ALL_VIEWS = ("lateral", "superior", "oblique", "posterior")

#: Each hemisphere holds at least this share of the ends: a side view shows half a network.
BILATERAL_MIN_SHARE = 0.25
#: Above this many regions names cover the picture (20 regions: sub-CHN's posterior network).
LABEL_MAX_REGIONS = 6
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

#: What a preset's name gains when its opposite-hemisphere edges are asked for.
WITH_OPPOSITE_SUFFIX = "_with_opposite"

OVERRIDABLE = (
    "title",
    "caption",
    "highlight_regions",
    "views",
    "lateral_side",
    "region_labels",
    "max_streamlines",
    "tube_radius_mm",
    "vmax_v_per_m",
    "iso_shell_percentile",
)

#: DK40 parcel names as words, for on-screen labels and titles.
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
    views = overrides.get("views", ALL_VIEWS)
    if not views or set(views) - set(ALL_VIEWS):
        raise ValueError(f"overrides.views must be some of {ALL_VIEWS}")
    if overrides.get("lateral_side", -1) not in (-1, 1):
        raise ValueError("overrides.lateral_side is -1 or 1")
    for key in ("max_streamlines", "tube_radius_mm", "vmax_v_per_m"):
        value = overrides.get(key)
        if value is not None and not value > 0:
            raise ValueError(f"overrides.{key} must be > 0")
    shell = overrides.get("iso_shell_percentile")
    if shell is not None and not 0 < shell < 100:
        raise ValueError("overrides.iso_shell_percentile must be in (0, 100), or null")


def network_title(name: str, regions: Sequence[str]) -> str:
    """Two regions are named in words; a longer list by the network's own name."""
    if len(regions) == 2:
        return " – ".join(region_words(r) for r in regions)
    top = re.fullmatch(r"top_(\d+)_by_(\w+)", name)
    if top:
        return f"Top {top[1]} connections by {top[2]}"
    stem, marked, _ = name.partition(WITH_OPPOSITE_SUFFIX)
    words = re.sub(r"\b([lr])h\b", lambda m: m[1].upper(), stem.replace("_", " "))
    title = words[0].upper() + words[1:] + " network"
    return f"{title}, with opposite-hemisphere connections" if marked else title


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
        "title": network_title(selection.name, regions),
        "caption": None,
        "highlight_regions": seeds or regions[:BUSIEST_ENDPOINTS],
        "views": list(BILATERAL_VIEWS if bilateral else ONE_SIDE_VIEWS),
        "lateral_side": 1 if right > left else -1,
        "region_labels": len(regions) <= LABEL_MAX_REGIONS,
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
        "title": "Two regions are named; a longer list goes by the network's name.",
        "caption": "Who, how many drawn, and neutral medians along the fibres.",
        "highlight_regions": (
            "The regions it was chosen by."
            if seeds
            else "No seed: the busiest ends of the network."
        ),
        "views": (
            "Both hemispheres hold a quarter of its ends or more: a side view shows half of it."
            if bilateral
            else "It lies mostly in one hemisphere."
        ),
        "lateral_side": f"The {side} side holds more of its ends ({left} left, {right} right).",
        "region_labels": (
            f"Names drawn, each only on a view that faces it: {len(regions)} regions."
            if values["region_labels"]
            else f"No names: {len(regions)} regions would cover the picture."
        ),
        "max_streamlines": (
            f"Above {STREAMLINE_BUDGET:,} an even sample is drawn, and the caption says so."
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
