"""The tissue-thickness figure is readable, and drawing it changed no number (2026-10-22).

What it pins, on the authored head of ``test_tissue_geometry.py`` (concentric shells of
CSF, bone and skin around a two-hemisphere brain):

* the statistics box and the legend lie beside the histogram, never over a bar;
* every view's colour map starts at a colour that stands out from the white background
  (the CSF figure used ``Blues``, which starts at white, so thin CSF vanished);
* drawing raises no warning (the old layout raised matplotlib's tight_layout warning);
* every number the analyzer writes -- the result, the text report, the statistics box and
  the legend -- equals what the analyzer wrote before the figure change.

The last check compares with ``tests/fixtures/tissue_head_outputs.json``, captured by
``capture`` below from the analyzer as it was before the change (commit b82a774a)::

    git show b82a774a:tit/pre/tissue_analyzer.py > /tmp/tissue_analyzer_b82a774a.py
    simnibs_python -m tests.numerical.test_tissue_figure /tmp/tissue_analyzer_b82a774a.py \\
        > tests/fixtures/tissue_head_outputs.json

Real matplotlib is needed for all but the result-and-report check (marked ``host_numerical``),
so the rest runs in the image (``idossha/ti-toolbox``); the view geometry, the centre-of-mass
cut and the histogram bins are checked in ``test_tissue_geometry.py``.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pytest

from tests.numerical.test_tissue_geometry import (  # noqa: F401 -- ta is a fixture
    CENTRE,
    SHAPE,
    ZOOMS,
    _head,
    _save,
    ta,
)

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "tissue_head_outputs.json"
TISSUES = ("bone", "csf", "skin")


def _draw(analyzer, plt, filtered=None, stats=None):
    """Draw *analyzer*'s thickness figure as ``analyze`` does (its style and font sizes)
    without writing it or the methodology figure; returns the open figure.

    *filtered* and *stats* default to the analyzer's own masks and thickness.
    """
    tissue = analyzer._create_tissue_mask()
    brain = analyzer._create_brain_mask()
    if filtered is None:
        filtered = analyzer._filter_to_brain_region(tissue, brain)
        stats = analyzer._calculate_thickness(tissue, filtered)
    saved = plt.savefig, plt.close, analyzer._create_methodology_figure
    plt.savefig = lambda *a, **k: None
    plt.close = lambda *a: None
    analyzer._create_methodology_figure = lambda *a, **k: None
    try:
        type(analyzer)._create_visualizations(analyzer, tissue, brain, filtered, stats)
        return plt.gcf()
    finally:
        plt.savefig, plt.close, analyzer._create_methodology_figure = saved


def capture(module, workdir: Path, plt=None) -> dict:
    """Every number *module*'s analyzer writes for the authored head, per tissue.

    ``result`` is ``analyze()``'s dict without its path, ``report`` the text report without
    its ``Input:`` line (a temporary path); with *plt*, ``figure`` holds the statistics box
    and the legend labels of the thickness figure.
    """
    labels, affine, _ = _head(SHAPE, ZOOMS, CENTRE)
    path = workdir / "labeling.nii.gz"
    _save(path, labels, affine)
    out = {}
    for tissue in TISSUES:
        analyzer = module.TissueAnalyzer(
            path, workdir / tissue, tissue, logging.getLogger("tissue-figure")
        )
        analyzer._create_visualizations = lambda *a, **k: None
        result = analyzer.analyze()
        report = Path(result.pop("report_path")).read_text(encoding="utf-8")
        entry = {
            "result": result,
            "report": [ln for ln in report.splitlines() if not ln.startswith("Input:")],
        }
        if plt is not None:
            fig = _draw(analyzer, plt)
            entry["figure"] = {
                "stats": [
                    t.get_text()
                    for ax in fig.axes
                    for t in ax.texts
                    if t.get_text().startswith("Statistics")
                ],
                "legend": [
                    t.get_text()
                    for ax in fig.axes
                    if ax.get_legend() is not None
                    for t in ax.get_legend().get_texts()
                ],
            }
            plt.close(fig)
        out[tissue] = entry
    return out


def _real_pyplot():
    import matplotlib.pyplot as plt

    return plt


def _expected():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))["tissues"]


@pytest.mark.host_numerical
def test_result_and_report_are_those_before_the_figure_change(ta, tmp_path):
    expected = _expected()

    got = capture(ta, tmp_path)

    for tissue in TISSUES:
        want = expected[tissue]
        assert got[tissue]["report"] == want["report"], tissue
        result = got[tissue]["result"]
        assert result["voxels"] == want["result"]["voxels"], tissue
        # Same arithmetic on the same arrays; the tolerance absorbs only a last-bit
        # difference between the host's and the image's numpy summation.
        for key in ("volume_cm3", "volume_mm3"):
            assert result[key] == pytest.approx(want["result"][key], rel=1e-12), key
        for stat in ("mean", "std", "min", "max"):
            assert result["thickness"][stat] == pytest.approx(
                want["result"]["thickness"][stat], rel=1e-12
            ), (tissue, stat)


def test_statistics_box_and_legend_are_those_before_the_figure_change(ta, tmp_path):
    expected = _expected()

    got = capture(ta, tmp_path, _real_pyplot())

    for tissue in TISSUES:
        assert got[tissue]["figure"] == expected[tissue]["figure"], tissue
        assert len(got[tissue]["figure"]["stats"]) == 1, tissue
        assert len(got[tissue]["figure"]["legend"]) == 5, tissue


@pytest.fixture
def head_path(tmp_path):
    labels, affine, _ = _head(SHAPE, ZOOMS, CENTRE)
    path = tmp_path / "labeling.nii.gz"
    _save(path, labels, affine)
    return path


def _skewed_thickness():
    """A filtered block and a thickness map shaped like ernie's bone: the thinnest value
    (2 mm) is the commonest, so the tallest bar stands at the histogram's left edge, where
    the old statistics box sat. Values are the 1 mm grid's ``2*sqrt(k)``."""
    rng = np.random.default_rng(0)
    filtered = np.zeros((40, 40, 40), dtype=np.uint8)
    filtered[5:35, 5:35, 5:35] = 1
    k = np.repeat([1, 2, 3, 4, 5, 9, 16, 25], [500, 200, 100, 150, 80, 60, 30, 10])
    thickness_map = np.full(filtered.shape, np.nan)
    sites = rng.choice(np.flatnonzero(filtered), size=k.size, replace=False)
    thickness_map.flat[sites] = 2 * np.sqrt(k)
    values = thickness_map[np.isfinite(thickness_map)]
    stats = {
        "mean": float(values.mean()),
        "std": float(values.std()),
        "min": float(values.min()),
        "max": float(values.max()),
        "thickness_map": thickness_map,
    }
    return filtered, stats


@pytest.mark.parametrize("data", ["head", "skewed"])
def test_statistics_and_legend_cover_no_bar(ta, head_path, data):
    """The skewed case is the one that catches a box over the tallest, leftmost bar."""
    from matplotlib.patches import Rectangle

    plt = _real_pyplot()
    analyzer = ta.TissueAnalyzer(
        head_path, head_path.parent / "o", "bone", logging.getLogger("t")
    )
    if data == "head":
        fig = _draw(analyzer, plt)
    else:
        fig = _draw(analyzer, plt, *_skewed_thickness())
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    (hist,) = [ax for ax in fig.axes if ax.get_title() == "D. Thickness Distribution"]
    bars = [
        p.get_window_extent(renderer)
        for p in hist.patches
        if isinstance(p, Rectangle) and p.get_height() > 0
    ]
    (stats,) = [
        t for ax in fig.axes for t in ax.texts if t.get_text().startswith("Statistics")
    ]
    (legend,) = [ax.get_legend() for ax in fig.axes if ax.get_legend() is not None]
    boxes = {
        "statistics": stats.get_bbox_patch().get_window_extent(renderer),
        "legend": legend.get_window_extent(renderer),
    }

    assert bars, "the histogram drew no bar to check"
    for name, box in boxes.items():
        assert not any(box.overlaps(bar) for bar in bars), name
        assert fig.bbox.contains(box.x0, box.y0) and fig.bbox.contains(box.x1, box.y1)
    assert not boxes["statistics"].overlaps(boxes["legend"])
    plt.close(fig)


def _luminance(rgb):
    """WCAG relative luminance of an sRGB colour (channels 0..1)."""
    c = np.asarray(rgb[:3], dtype=float)
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return float(c @ [0.2126, 0.7152, 0.0722])


@pytest.mark.parametrize("tissue", TISSUES)
def test_thinnest_tissue_stands_out_from_the_background(ta, head_path, tissue):
    """The colour the views give the smallest thickness has 3:1 contrast with the axes.

    3:1 is WCAG's minimum for graphical objects; ``Blues`` (the old CSF map) starts at
    1.1:1 against white. The largest thickness need only not be the background.
    """
    plt = _real_pyplot()
    analyzer = ta.TissueAnalyzer(
        head_path, head_path.parent / "o", tissue, logging.getLogger("t")
    )
    fig = _draw(analyzer, plt)
    views = [ax for ax in fig.axes if " View" in ax.get_title()]
    assert len(views) == 3

    for ax in views:
        background = ax.get_facecolor()
        thickness = ax.images[-1]  # drawn over the faint tissue
        low, high = thickness.cmap(0.0), thickness.cmap(1.0)
        lum = sorted([_luminance(low), _luminance(background)])
        assert (lum[1] + 0.05) / (lum[0] + 0.05) >= 3.0, (ax.get_title(), low)
        assert np.abs(np.subtract(high[:3], background[:3])).max() > 0.25, high
    plt.close(fig)


def test_drawing_the_figures_raises_no_warning(ta, head_path):
    """The old layout warned 'not compatible with tight_layout' on every figure."""
    plt = _real_pyplot()
    for tissue in TISSUES:
        analyzer = ta.TissueAnalyzer(
            head_path, head_path.parent / tissue, tissue, logging.getLogger("t")
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            fig = _draw(analyzer, plt)
            fig.canvas.draw()
        plt.close(fig)


def _load(path: str):
    """Import an analyzer module from a file, as part of ``tit.pre`` (relative imports)."""
    spec = importlib.util.spec_from_file_location(
        "tit.pre._tissue_analyzer_capture", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    import matplotlib

    matplotlib.use("Agg")
    source = sys.argv[1]
    with tempfile.TemporaryDirectory() as tmp:
        tissues = capture(_load(source), Path(tmp), _real_pyplot())
    json.dump(
        {
            "source": f"tests/numerical/test_tissue_figure.py capture of {Path(source).name}",
            "head": {"shape": SHAPE, "zooms": ZOOMS, "centre": CENTRE},
            "tissues": tissues,
        },
        sys.stdout,
        indent=1,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
