"""The magnitude-scale percentiles must rise blue <= green <= red, or the config refuses.

What this pins (2026-10-22): ``VectorConfig`` documents three percentile thresholds for the
blue -> green -> red ramp. It only range-checked them, and the runner
(``_map_magnitude_to_colors_magscale``) silently raised green to blue and red to green, so
"blue 90 / green 50 / red 95" ran as 90/90/95 -- not the ramp the user typed. The config now
refuses a non-monotone order in magnitude-scale mode, naming the three values; equal neighbours
stay allowed (a step), and RGB colouring, which reads no percentile, is not checked.

Where the expected values come from: the ordering rule is the ramp's own definition (each
threshold is the start of the next colour band); the cases are typed out here.

Host leg. Reproduce:
``.venv/bin/python -m pytest tests/test_blender_vector_percentiles.py -q -p no:cacheprovider``
The ramp's colours themselves are pinned in tests/numerical/test_vector_export_geometry.py.
"""

from __future__ import annotations

import pytest

from tit.blender.config import VectorConfig

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "blue, green, red",
    [(90, 50, 95), (10, 80, 60), (50, 40, 30), (100, 0, 100)],
)
def test_non_monotone_percentiles_are_refused(blue, green, red):
    with pytest.raises(ValueError, match="blue <= green <= red") as info:
        VectorConfig(
            subject_id="101",
            simulation_name="L_Insula",
            color="magscale",
            blue_percentile=blue,
            green_percentile=green,
            red_percentile=red,
        )
    assert f"{blue}" in str(info.value) and f"{red}" in str(info.value)


def test_rgb_colouring_reads_no_percentile_so_their_order_is_not_checked():
    cfg = VectorConfig(
        subject_id="101",
        simulation_name="L_Insula",
        color="rgb",
        blue_percentile=90,
        green_percentile=50,
        red_percentile=95,
    )
    assert cfg.green_percentile == 50


@pytest.mark.parametrize(
    "blue, green, red", [(50, 80, 95), (0, 0, 100), (90, 90, 90), (0, 50, 50)]
)
def test_monotone_percentiles_are_kept_as_typed(blue, green, red):
    cfg = VectorConfig(
        subject_id="101",
        simulation_name="L_Insula",
        color="magscale",
        blue_percentile=blue,
        green_percentile=green,
        red_percentile=red,
    )
    assert (cfg.blue_percentile, cfg.green_percentile, cfg.red_percentile) == (
        blue,
        green,
        red,
    )


def test_out_of_range_is_still_refused_first():
    with pytest.raises(ValueError, match="red_percentile must be in"):
        VectorConfig(subject_id="101", simulation_name="s", red_percentile=101)
