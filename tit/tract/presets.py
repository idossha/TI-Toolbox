"""Named region sets to pick a network by: DK40 parcels and label-volume names, nothing more.

A preset is two sets of region names, and the network it gives is every edge of this subject's
``network.npz`` joining the two. It is a convenience for choosing, not an anatomical claim: which
of its edges exist, and how many streamlines they hold, depend on the tractography. Standard
library and numpy only (the server reads this module).

Thalamocortical presets keep same-hemisphere edges by default (``Preset.same_side``). The test is
the atlas labels in the subject's own space (``Left-Thalamus-Proper`` with ``lh.*``,
``Right-Thalamus-Proper`` with ``rh.*``), never a midline plane, and the result is plain region
pairs, so the mask, assess stage, ranking and render read one definition. The edges left out and
their counts are always reported, and the caller can add them back.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

HEMIS = ("lh", "rh")
THALAMI = ("Left-Thalamus-Proper", "Right-Thalamus-Proper")


def _both(*parcels: str) -> tuple[str, ...]:
    return tuple(f"{hemi}.{parcel}" for hemi in HEMIS for parcel in parcels)


FRONTAL = (
    "superiorfrontal",
    "rostralmiddlefrontal",
    "caudalmiddlefrontal",
    "parsopercularis",
    "parstriangularis",
    "parsorbitalis",
    "lateralorbitofrontal",
    "medialorbitofrontal",
    "frontalpole",
    "precentral",
    "paracentral",
)
POSTERIOR = (
    "superiorparietal",
    "inferiorparietal",
    "supramarginal",
    "postcentral",
    "precuneus",
    "lateraloccipital",
    "lingual",
    "cuneus",
    "pericalcarine",
)
TEMPORAL = (
    "superiortemporal",
    "middletemporal",
    "inferiortemporal",
    "bankssts",
    "fusiform",
    "transversetemporal",
    "temporalpole",
    "entorhinal",
    "parahippocampal",
)
CINGULATE = (
    "caudalanteriorcingulate",
    "isthmuscingulate",
    "posteriorcingulate",
    "rostralanteriorcingulate",
)
#: Every DK40 parcel of one hemisphere (FreeSurfer's ``unknown`` and ``corpuscallosum`` are no
#: region a streamline connects, and the network stage does not name them).
CORTEX_PARCELS = FRONTAL + POSTERIOR + TEMPORAL + CINGULATE + ("insula",)
CORTEX = _both(*CORTEX_PARCELS)


@dataclass(frozen=True)
class Preset:
    """Every edge joining a region of ``seeds`` to one of ``targets``.

    ``seeds`` are what the render lights, as the thalami are in a thalamocortical render.
    ``same_side``: its opposite-hemisphere seed-target edges are left out unless asked for.
    """

    id: str
    label: str
    seeds: tuple[str, ...]
    targets: tuple[str, ...]
    same_side: bool = False


PRESETS = (
    Preset(
        "frontal_thalamocortical",
        "Frontal thalamocortical",
        THALAMI,
        _both(*FRONTAL),
        same_side=True,
    ),
    Preset(
        "posterior_thalamocortical",
        "Posterior thalamocortical",
        THALAMI,
        _both(*POSTERIOR),
        same_side=True,
    ),
    Preset(
        "temporal_thalamocortical",
        "Temporal thalamocortical",
        THALAMI,
        _both(*TEMPORAL),
        same_side=True,
    ),
    Preset(
        "hippocampal_cortical",
        "Hippocampal-cortical",
        ("Left-Hippocampus", "Right-Hippocampus"),
        CORTEX,
    ),
    Preset("cingulate_cortical", "Cingulate-cortical", _both(*CINGULATE), CORTEX),
    Preset(
        "precentral_brainstem",
        "Precentral-brainstem",
        ("Brain-Stem",),
        _both("precentral"),
    ),
    Preset("insular_cortical", "Insular-cortical", _both("insula"), CORTEX),
    Preset(
        "amygdala_cortical",
        "Amygdala-cortical",
        ("Left-Amygdala", "Right-Amygdala"),
        CORTEX,
    ),
    Preset(
        "basal_ganglia_cortical",
        "Basal ganglia-cortical",
        (
            "Left-Caudate",
            "Left-Putamen",
            "Left-Pallidum",
            "Right-Caudate",
            "Right-Putamen",
            "Right-Pallidum",
        ),
        CORTEX,
    ),
    Preset(
        "interhemispheric_cortical",
        "Interhemispheric cortical",
        tuple(f"lh.{parcel}" for parcel in CORTEX_PARCELS),
        tuple(f"rh.{parcel}" for parcel in CORTEX_PARCELS),
    ),
)


def _hemi(name: str) -> str:
    """``"lh"``, ``"rh"`` or ``""`` from a region's own label."""
    if name.startswith(("lh.", "Left-")):
        return "lh"
    if name.startswith(("rh.", "Right-")):
        return "rh"
    return ""


def resolve_preset(
    preset: Preset, names: list[str], pairs: np.ndarray, counts: np.ndarray
) -> dict:
    """The preset on one subject's network (``names``, edge ``pairs``, edge ``counts``).

    Returns its ``pairs`` as region names, ``n_edges``, ``n_streamlines``, the ``missing`` labels
    and, when it cannot be chosen, the ``reason``: a whole side absent from the network's labels
    (another atlas), or no streamline joining the two sides. ``opposite_pairs``, ``n_opposite``
    and the two ``*_to_*`` counts are the opposite-hemisphere edges a ``same_side`` preset left
    out of ``pairs`` (empty for any other preset).
    """
    index = {name: i for i, name in enumerate(names)}
    wanted = (preset.seeds, preset.targets)
    missing = sorted({name for side in wanted for name in side if name not in index})
    side_a, side_b = (
        np.array([index[n] for n in side if n in index]) for side in wanted
    )
    pairs, counts = np.asarray(pairs), np.asarray(counts)
    kept: list[list[str]] = []
    opposite: list[list[str]] = []
    n_kept = 0
    by_direction = {
        "right_thalamus_to_left_cortex": 0,
        "left_thalamus_to_right_cortex": 0,
    }
    reason = None
    if not len(side_a) or not len(side_b):
        shown = ", ".join(missing[:4]) + ("…" if len(missing) > 4 else "")
        reason = f"These labels are not in this network: {shown}"
    else:
        a_in, b_in = (np.isin(pairs, side).reshape(-1, 2) for side in (side_a, side_b))
        picked = np.flatnonzero((a_in[:, 0] & b_in[:, 1]) | (a_in[:, 1] & b_in[:, 0]))
        if not len(picked):
            reason = "0 streamlines join these regions in this network."
        for edge in picked.tolist():
            a, b = names[pairs[edge][0]], names[pairs[edge][1]]
            n = int(counts[edge])
            if preset.same_side and {_hemi(a), _hemi(b)} == {"lh", "rh"}:
                opposite.append([a, b])
                seed = a if a in preset.seeds else b
                direction = "left" if _hemi(seed) == "lh" else "right"
                other = "right" if direction == "left" else "left"
                by_direction[f"{direction}_thalamus_to_{other}_cortex"] += n
            else:
                kept.append([a, b])
                n_kept += n
    return {
        "id": preset.id,
        "label": preset.label,
        "seeds": [name for name in preset.seeds if name in index],
        "same_side": preset.same_side,
        "pairs": kept,
        "n_edges": len(kept),
        "n_streamlines": n_kept,
        "opposite_pairs": opposite,
        "n_opposite": sum(by_direction.values()),
        **by_direction,
        "missing": missing,
        "reason": reason,
    }


def opposite_removed(resolved: dict, selection_pairs) -> dict | None:
    """What a ``same_side`` preset left out of *selection_pairs*, or ``None`` when it left nothing.

    *resolved* is :func:`resolve_preset`'s answer. A selection holding the opposite edges (the
    user asked for them) has removed none, so this reads the selection, not a setting.
    """
    if not resolved["same_side"]:
        return None
    chosen = {frozenset(p) for p in selection_pairs}
    if any(frozenset(p) in chosen for p in resolved["opposite_pairs"]):
        return None
    return {
        "n_kept": resolved["n_streamlines"],
        "n_with_opposite": resolved["n_streamlines"] + resolved["n_opposite"],
        "n_removed": resolved["n_opposite"],
        "right_thalamus_to_left_cortex": resolved["right_thalamus_to_left_cortex"],
        "left_thalamus_to_right_cortex": resolved["left_thalamus_to_right_cortex"],
    }
