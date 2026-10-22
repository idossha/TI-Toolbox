"""Nilearn figures label a weak field's display range legibly, not "0.01-0.01" (p35).

What this pins, 2026-10-22: the multi-slice PDF's colourbar end ticks and title, and the
glass-brain PDF's title, print the two cutoffs (V/m) with three significant figures: each
label reads back within 0.5 % of the number it stands for (half a unit in the third
figure), and the two labels differ. The spec is relative precision, which does not depend
on the field's scale. A low-current montage averages to a weak field (peak 0.012 V/m, p95
about 0.006, p99.9 about 0.011): with the former ``:.2f`` both ends printed "0.01", so the
colourbar said the range was empty.

Where the numbers come from: the synthetic field below is built by hand to that shape, and
the cutoffs it should label are ``numpy.percentile`` of its non-zero voxels at 95 and 99.9
-- the data-driven default the config documents -- computed here, not read from the code
under test. A second, explicit pair (0.00637 / 0.0114 V/m, typed by a user) has a value two
significant figures would misreport by 3.5 % ("0.011"), so a label precision below three
figures fails here even when the data-driven pair happens to round exactly. nilearn and matplotlib are mocked on the host (tests/conftest.py); the figure
calls are captured, so the strings checked are exactly the ones handed to matplotlib.

Reproduce: ``.venv/bin/python -m pytest tests/test_nilearn_colorbar_precision.py -q -p no:cacheprovider``.
Deliberately elsewhere: real rendering on Dataset 000 (``tests/numerical/test_nilearn_render_realdata.py``).
"""

from __future__ import annotations

import re
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

pytestmark = pytest.mark.unit

#: A weak averaged field: 9,500 voxels up to 0.0063 V/m, 490 up to 0.011, 10 up to 0.012.
WEAK = np.concatenate(
    [
        np.linspace(1e-4, 0.0063, 9500),
        np.linspace(0.0063, 0.011, 490),
        np.linspace(0.011, 0.012, 10),
    ]
)
P95 = float(np.percentile(WEAK, 95.0))
P999 = float(np.percentile(WEAK, 99.9))
#: Relative precision of three significant figures: half a unit in the third figure.
REL = 0.005
#: cutoffs given -> the V/m pair the labels must stand for.
CUTOFFS = {
    "data-driven": ((None, None), (P95, P999)),
    "explicit": ((0.00637, 0.0114), (0.00637, 0.0114)),
}


class _Field:
    """Stands in for a nibabel image: the averaged field on a 3-D grid (zeros outside)."""

    def __init__(self, values: np.ndarray):
        grid = np.zeros(20 * 25 * 30)
        grid[: values.size] = values
        self._data = grid.reshape(20, 25, 30)

    def get_fdata(self) -> np.ndarray:
        return self._data


def _assert_labels(lo_text: str, hi_text: str, expected: tuple[float, float]) -> None:
    assert lo_text != hi_text, f"both ends read {lo_text!r}"
    assert float(lo_text) == pytest.approx(expected[0], rel=REL), lo_text
    assert float(hi_text) == pytest.approx(expected[1], rel=REL), hi_text


def test_the_synthetic_field_has_the_weak_shape_the_spec_names():
    assert WEAK.max() == pytest.approx(0.012)
    assert P95 == pytest.approx(0.006, rel=0.1)
    assert P999 == pytest.approx(0.011, rel=0.05)


@pytest.mark.parametrize("cutoffs", CUTOFFS)
def test_slice_pdf_colourbar_ticks_and_title_tell_the_two_cutoffs_apart(
    init_pm, tmp_path, monkeypatch, cutoffs
):
    (min_cutoff, max_cutoff), expected = CUTOFFS[cutoffs]
    from tit.plotting.nilearn import visualizer

    fig = MagicMock(name="figure")
    axes = np.empty((3, 7), dtype=object)
    for idx in np.ndindex(axes.shape):
        axes[idx] = MagicMock(name=f"axes{idx}")
    plt = MagicMock(name="pyplot")
    plt.subplots.return_value = (fig, axes)
    monkeypatch.setattr(visualizer, "plt", plt)
    monkeypatch.setattr(visualizer, "plotting", MagicMock(name="nilearn.plotting"))
    monkeypatch.setattr(visualizer, "threshold_img", MagicMock(name="threshold_img"))
    for mod in ("matplotlib.cm", "matplotlib.colors"):
        monkeypatch.setitem(sys.modules, mod, MagicMock(name=mod))

    out = visualizer.NilearnVisualizer().create_pdf_visualization_group(
        _Field(WEAK),
        "group",
        str(tmp_path),
        min_cutoff=min_cutoff,
        max_cutoff=max_cutoff,
        atlas_name="no_such_atlas",
    )

    assert out == str(tmp_path / "group_multiple_views.pdf")
    cbar = fig.colorbar.return_value
    ticks = cbar.set_ticks.call_args.args[0]
    assert ticks == pytest.approx(list(expected))
    labels = cbar.set_ticklabels.call_args.args[0]
    _assert_labels(*labels, expected)

    title = fig.suptitle.call_args.args[0]
    lo_text, hi_text = re.search(r"\n(\S+)-(\S+) V/m Range$", title).groups()
    _assert_labels(lo_text, hi_text, expected)


@pytest.mark.parametrize("cutoffs", CUTOFFS)
@pytest.mark.parametrize("callback", [True, False], ids=["runner", "script"])
def test_glass_brain_title_tells_the_two_cutoffs_apart(
    tmp_path, monkeypatch, callback, cutoffs
):
    from tit.plotting.nilearn.img_glass import create_glass_brain_entry_point_group

    (min_cutoff, max_cutoff), expected = CUTOFFS[cutoffs]

    plotting = MagicMock(name="nilearn.plotting")
    monkeypatch.setattr(sys.modules["nilearn"], "plotting", plotting)
    lines: list[str] = []

    out = create_glass_brain_entry_point_group(
        _Field(WEAK),
        "group",
        str(tmp_path),
        min_cutoff=min_cutoff,
        max_cutoff=max_cutoff,
        output_callback=lines.append if callback else None,
    )

    assert out == str(tmp_path / "group_glass_brain.pdf")
    kwargs = plotting.plot_glass_brain.call_args.kwargs
    assert (kwargs["threshold"], kwargs["vmax"]) == pytest.approx(expected)
    lo_text, hi_text = re.search(r"\n(\S+)-(\S+) V/m$", kwargs["title"]).groups()
    _assert_labels(lo_text, hi_text, expected)
