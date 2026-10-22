"""Re-rendering an mTI montage image starts from the blank cap template.

What this pins (2026-10-22, package p13, task mti-image-no-accumulation): for ``sim_mode="M"``
``visualize_montage`` used the existing ``combined_montage_visualization.png`` as its base.
A simulation's ``mTI/montage_imgs`` is per montage and an overwrite re-run does not clear it,
so re-running a montage with other electrodes drew the new rings on top of the old ones.

Two legs:

* host: ``subprocess.run`` is replaced by a fake ``convert`` that appends a marker to the
  image it writes (so drawing changes the bytes); the first ``convert`` of every render must
  read exactly the bytes of ``resources/amv/GSN-256.png``;
* ImageMagick (skips without ``convert`` and the DejaVu-Sans font the legend uses; runs in the
  image): the real PNG, read back with Pillow. After a second render with other electrodes,
  the 110 px boxes around the first render's electrodes (pixels from ``GSN-256.csv``) hold no
  channel-coloured pixels, while the second render's electrodes do; and rendering the same
  call twice into one folder gives the pixels of a single render in a fresh folder.

Reproduce: ``.venv/bin/python -m pytest tests/test_mti_image_rerender.py -q``; the ImageMagick
leg: ``simnibs_python -m pytest tests/test_mti_image_rerender.py`` inside the image.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tit.tools.montage_visualizer import (
    _RESOURCES_DIR,
    get_expected_output_filename,
    visualize_montage,
)

TEMPLATE = Path(_RESOURCES_DIR) / "GSN-256.png"
NET = "GSN-HydroCel-185.csv"
# Frontal pairs first, then posterior ones: their rings and arcs never share a 110 px box.
FIRST = [["E022", "E015"], ["E006", "E005"]]
SECOND = [["E116", "E150"], ["E087", "E153"]]


def _final(folder: Path) -> Path:
    return folder / get_expected_output_filename("x", "M")


class _FakeConvert:
    """Record what each ``convert`` call reads, then "draw" by appending to its output."""

    def __init__(self):
        self.inputs: list[bytes] = []

    def __call__(self, argv, check):
        assert argv[0] == "convert"
        self.inputs.append(Path(argv[1]).read_bytes())
        with open(argv[-1], "ab") as f:
            f.write(b"<drawn>")


def _render(folder: Path, pairs) -> _FakeConvert:
    fake = _FakeConvert()
    with patch("tit.tools.montage_visualizer.subprocess.run", side_effect=fake):
        visualize_montage("x", pairs, NET, str(folder), sim_mode="M")
    return fake


def test_every_mti_render_starts_from_the_blank_template(tmp_path):
    template = TEMPLATE.read_bytes()
    first = _render(tmp_path, FIRST)
    assert first.inputs[0] == template
    second = _render(tmp_path, SECOND)
    assert second.inputs[0] == template


def test_the_same_mti_render_twice_gives_the_same_file(tmp_path):
    _render(tmp_path / "once", FIRST)
    _render(tmp_path / "twice", FIRST)
    _render(tmp_path / "twice", FIRST)
    assert (
        _final(tmp_path / "twice").read_bytes()
        == _final(tmp_path / "once").read_bytes()
    )


# ── ImageMagick leg ──────────────────────────────────────────────────────────────────


def _imagemagick_ready() -> bool:
    if not shutil.which("convert"):
        return False
    fonts = subprocess.run(["convert", "-list", "font"], capture_output=True, text=True)
    return "DejaVu-Sans" in fonts.stdout


_needs_convert = pytest.mark.skipif(
    not _imagemagick_ready(),
    reason="skipping: ImageMagick convert with the DejaVu-Sans font is needed (in the image)",
)


def _pixels(path: Path):
    image_module = pytest.importorskip("PIL.Image", reason="Pillow reads the render")
    with image_module.open(path) as image:
        return image.convert("RGB")


def _channel_pixels(image, label: str, channel: int) -> int:
    with open(Path(_RESOURCES_DIR) / "GSN-256.csv", newline="") as f:
        x, y = next(
            (int(r["x"]), int(r["y"]))
            for r in csv.DictReader(f)
            if r["electrode_name"] == label
        )
    box = image.crop((x - 55, y - 55, x + 55, y + 55)).getdata()
    if channel == 0:  # blue
        return sum(b > 120 and b > 1.5 * r and b > 1.5 * g for r, g, b in box)
    return sum(r > 120 and r > 1.5 * g and r > 1.5 * b for r, g, b in box)  # red


@_needs_convert
def test_a_rerun_with_other_electrodes_leaves_no_old_rings(tmp_path):
    visualize_montage("x", FIRST, NET, str(tmp_path), sim_mode="M")
    visualize_montage("x", SECOND, NET, str(tmp_path), sim_mode="M")
    image = _pixels(_final(tmp_path))
    for channel, pair in enumerate(SECOND):
        for label in pair:
            assert _channel_pixels(image, label, channel) > 50, label
    for channel, pair in enumerate(FIRST):
        for label in pair:
            assert _channel_pixels(image, label, channel) == 0, label


@_needs_convert
def test_rendering_twice_gives_the_pixels_of_one_render(tmp_path):
    visualize_montage("x", FIRST, NET, str(tmp_path / "once"), sim_mode="M")
    for _ in range(2):
        visualize_montage("x", FIRST, NET, str(tmp_path / "twice"), sim_mode="M")
    once = _pixels(_final(tmp_path / "once"))
    twice = _pixels(_final(tmp_path / "twice"))
    assert once.size == twice.size
    assert once.tobytes() == twice.tobytes()
