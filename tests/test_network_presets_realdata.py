"""The thalamocortical presets on sub-CHN's real network (Dataset 000).

What this pins: same-side filtering on real labels, against edge counts tallied independently of
this code from ``network.npz``'s ``pairs`` and ``counts`` in the 2026-11-05 proof-of-concept report
(1e: left thalamus 756 left + 24 right, right thalamus 167 left + 651 right, 1,598 in all; frontal
77 crossed of 3,198), and the automatic setup those counts give.

Why the synthetic half (``tests/test_network_setup.py``) is not enough: only real labels show that
the preset names match what the network stage writes.

Reads the dataset read-only.
    export TIT_DATASET_000=/path/to/000
    .venv/bin/python -m pytest tests/test_network_presets_realdata.py -q
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from tit.blender.network_setup import resolve_network_setup
from tit.tract.config import Selection
from tit.tract.presets import PRESETS, resolve_preset

ROOT = os.environ.get("TIT_DATASET_000")


@pytest.fixture(scope="module")
def network():
    if not ROOT:
        pytest.skip("skipping: TIT_DATASET_000 is unset")
    path = Path(ROOT, "derivatives/SimNIBS/sub-CHN/tractography/network.npz")
    if not path.is_file():
        pytest.skip(f"skipping: {path} is missing (TIT_DATASET_000)")
    with np.load(path, allow_pickle=False) as data:
        return [str(n) for n in data["names"]], data["pairs"], data["counts"]


def resolved(network, preset_id: str) -> dict:
    return resolve_preset(next(p for p in PRESETS if p.id == preset_id), *network)


def test_posterior_keeps_the_same_side_and_counts_the_rest_by_direction(
    network,
) -> None:
    out = resolved(network, "posterior_thalamocortical")
    assert out["n_streamlines"] == 756 + 651
    assert out["right_thalamus_to_left_cortex"] == 167
    assert out["left_thalamus_to_right_cortex"] == 24
    assert out["n_streamlines"] + out["n_opposite"] == 1598
    assert out["n_edges"] + len(out["opposite_pairs"]) == 27


def test_frontal_has_the_crossed_count_the_report_measured(network) -> None:
    out = resolved(network, "frontal_thalamocortical")
    assert out["n_opposite"] == 77
    assert out["n_streamlines"] + out["n_opposite"] == 3198


def test_every_preset_is_choosable_on_this_network(network) -> None:
    assert [p.id for p in PRESETS if resolved(network, p.id)["reason"]] == []


def test_the_reference_network_is_set_up_as_it_was_approved(network) -> None:
    names, pairs, counts = network
    out = resolved(network, "posterior_thalamocortical")
    every = out["pairs"] + out["opposite_pairs"]
    selection = Selection(
        name="posterior_thalamocortical_with_opposite",
        kind="edges",
        regions=out["seeds"],
        pairs=every,
    )
    setup = resolve_network_setup(
        selection,
        {
            (names[a], names[b]): int(n)
            for (a, b), n in zip(pairs.tolist(), counts.tolist())
        },
    )
    values = setup["values"]
    assert setup["n_drawn"] == 1598
    assert values["lateral_side"] == -1
    assert values["highlight_regions"] == out["seeds"]
    assert values["iso_shell_percentile"] == 95.0
