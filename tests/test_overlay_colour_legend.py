"""The cap image, the NIfTI electrode overlay and the reports name and colour channels alike, and
the 2-D cap templates are well-formed and match the 3-D caps.

What this pins (2026-10-22, package p13, task overlay-colour-legend-contract):

* one channel order everywhere: the montage PNG's rings, arcs and legend
  (``tit.tools.montage_visualizer``), the overlay LUT (``tit.tools.electrode_overlay``) and the
  report's channel list (``tit.reporting.generators.common``) all give channel *i* the same
  colour and the same name (Channel 1, Channel 2, ...; channel k is electrodes Ek+ and Ek-);
* the overlay LUT's RGB values are the CSS Color 4 named colours the PNG draws with (typed
  here from the CSS Color Module Level 4 named-colour table, not from the code);
* ``resources/amv``: GSN-256.png is 1816 x 1536 (read from its IHDR chunk; the legend is
  anchored to that height), the template CSVs have a header, no blank rows, unique labels and
  integer pixels inside the image, and every tracked file there is loaded by the code (the
  986 KB GSN-256.png.backup was not);
* the templates agree with the 3-D caps: corr(x_px, x_mni) >= 0.9, corr(y_px, -y_mni) >= 0.9,
  median azimuth error < 10 deg about the vertex, left/right never swapped beyond 15 mm of the
  midline, front/back agreeing for >= 90 % beyond 15 mm of Cz. Measured 2026-10-22: GSN vs the
  MNI 256 cap 0.932 / 0.959 / 5.9 deg; 10-10 vs Jurak 0.969 / 0.970 / 4.3 deg (Neuroelectrics
  7.9 deg, the largest); front/back 1.0 except Okamoto (18 sites) 0.93, whose T8 is 17.5 mm
  behind the vertex in MNI but drawn level with Cz. 3-D caps: ``resources/ElectrodeCaps_MNI``
  (GSN) and SimNIBS's 10-10 caps as stored in ``tit/scene/guide-mni``; the vertex is SimNIBS
  Jurak Cz (0.0, -8.2, 97.3) mm.

Reproduce: ``.venv/bin/python -m pytest tests/test_overlay_colour_legend.py -q``.
"""

from __future__ import annotations

import csv
import json
import re
import struct
import subprocess
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from tit.reporting.generators.common import CAP_COLOURS, channel_rows
from tit.tools import electrode_overlay, montage_visualizer

REPO = Path(__file__).resolve().parents[1]
AMV = REPO / "resources" / "amv"

# CSS Color Module Level 4, section 6.1 "Named Colors".
CSS_NAMED = {
    "blue": (0, 0, 255),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "purple": (128, 0, 128),
    "orange": (255, 165, 0),
    "cyan": (0, 255, 255),
    "chocolate": (210, 105, 30),
    "violet": (238, 130, 238),
}
# Channel k is the k-th electrode pair, made of Ek+ and Ek- (maintainer, 2026-10-28) -- never "A"/"B".
NAMES = [f"Channel {k}" for k in range(1, 9)]


def test_one_channel_colour_order_everywhere():
    assert (
        list(montage_visualizer._COLORS)
        == list(electrode_overlay._DEFAULT_MONTAGE_COLORS)
        == list(CAP_COLOURS)
        == electrode_overlay._montage_color_names()
    )
    assert len(set(CAP_COLOURS)) == 8


def test_overlay_rgb_is_the_css_named_colour():
    assert electrode_overlay._MONTAGE_COLOR_RGB == CSS_NAMED
    assert set(CAP_COLOURS) == set(CSS_NAMED)


def test_overlay_lut_colours_channels_in_order(tmp_path):
    path = electrode_overlay.write_electrode_overlay_lut(tmp_path / "o.lut", 9)
    rows = [
        line.split()
        for line in Path(path).read_text().splitlines()
        if not line.startswith("#")
    ]
    assert [int(r[0]) for r in rows] == list(range(1, 10))
    for idx, row in enumerate(rows):
        colour = CAP_COLOURS[idx % 8]
        assert tuple(int(v) for v in row[2:5]) == CSS_NAMED[colour], (idx, row)
        assert row[5] == "255"


def _convert_calls(pairs, folder: Path) -> list[list[str]]:
    """argv of every ``convert`` call of one montage render (ImageMagick not run)."""
    calls: list[list[str]] = []
    with patch(
        "tit.tools.montage_visualizer.subprocess.run",
        side_effect=lambda argv, check: calls.append(list(argv)),
    ):
        montage_visualizer.visualize_montage(
            "legend", pairs, "GSN-HydroCel-256.csv", str(folder)
        )
    return calls


def _legend(calls) -> tuple[list[str], list[str], tuple[int, ...]]:
    """(swatch colours, texts, panel box x0 y0 x1 y1) of the legend's convert call.

    The call reads ``-fill <panel> -draw "roundrectangle x0,y0 x1,y1 r,r"``, then per row
    ``-fill <colour> -draw <swatch> ... -annotate +x+y <text>``.
    """
    (argv,) = [a for a in calls if "-annotate" in a]
    panel, *swatches = [i for i, tok in enumerate(argv) if tok == "-draw"]
    colours = [argv[i - 1] for i in swatches]
    texts = [argv[i + 2] for i, tok in enumerate(argv) if tok == "-annotate"]
    box = tuple(int(v) for v in re.findall(r"\d+", argv[panel + 1])[:4])
    return colours, texts, box


def test_image_rings_legend_and_report_name_each_channel_alike(tmp_path):
    pairs = [[f"E{2 * i + 1:03d}", f"E{2 * i + 2:03d}"] for i in range(8)]
    calls = _convert_calls(pairs, tmp_path)
    rings = [
        (a[a.index("-fill") + 1], Path(a[3]).name) for a in calls if "-colorize" in a
    ]
    arcs = [a[a.index("-stroke") + 1] for a in calls if "bezier" in " ".join(a)]
    colours, texts, _ = _legend(calls)
    report = channel_rows(pairs, [1.0] * 8)
    for i in range(8):
        colour = CAP_COLOURS[i]
        assert rings[2 * i] == rings[2 * i + 1] == (colour, f"pair{i + 1}ring.png")
        assert arcs[i] == colour
        assert colours[i] == colour
        assert texts[i] == NAMES[i]
        assert report[i][0] == f"{NAMES[i]} ({colour})"
        assert report[i][1].startswith(f"E{i + 1}+ {pairs[i][0]} · E{i + 1}- {pairs[i][1]}")


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR"
    return struct.unpack(">II", head[16:24])


def test_template_image_size_and_legend_anchor(tmp_path):
    width, height = _png_size(AMV / "GSN-256.png")
    assert (width, height) == (1816, 1536)
    calls = _convert_calls([["E001", "E002"], ["E003", "E004"]], tmp_path)
    _, texts, (x0, y0, x1, y1) = _legend(calls)
    assert texts == ["Channel 1", "Channel 2"]
    assert y1 == height - 30 and 0 <= x0 < x1 < width and 0 <= y0 < y1


@pytest.mark.parametrize("name", ["10-10.csv", "GSN-256.csv"])
def test_template_csv_is_well_formed(name):
    width, height = _png_size(AMV / "GSN-256.png")
    lines = (AMV / name).read_text().split("\n")
    assert lines[0] == "electrode_name,x,y"
    assert lines[-1] == "" and all(line.strip() for line in lines[1:-1])
    rows = [line.split(",") for line in lines[1:-1]]
    assert all(len(r) == 3 for r in rows)
    labels = [r[0] for r in rows]
    assert len(labels) == len(set(labels)) and len(labels) >= 70
    for label, x, y in rows:
        assert re.fullmatch(r"\d+", x) and re.fullmatch(r"\d+", y), label
        assert 0 <= int(x) < width and 0 <= int(y) < height, label
    pixels = [(r[1], r[2]) for r in rows]
    assert len(pixels) == len(set(pixels))


def test_every_tracked_template_resource_is_loaded_by_code():
    listed = subprocess.run(
        ["git", "ls-files", "resources/amv"], cwd=REPO, capture_output=True, text=True
    )
    if listed.returncode != 0:
        pytest.skip("skipping: not a git checkout (the image mounts a worktree)")
    tracked = [Path(p).name for p in listed.stdout.split()]
    assert "GSN-256.png" in tracked
    source = "\n".join(p.read_text() for p in (REPO / "tit").rglob("*.py"))
    rings = {Path(r).name for r in montage_visualizer._RINGS}
    unused = [name for name in tracked if name not in source and name not in rings]
    assert not unused


# ── 2-D templates against the 3-D caps ───────────────────────────────────────────────

VERTEX = np.array([0.0, -8.2, 97.3])  # SimNIBS EEG10-10_UI_Jurak_2007 Cz, MNI mm


def _template(name: str) -> dict[str, tuple[int, int]]:
    with (AMV / name).open(newline="") as f:
        return {
            r["electrode_name"]: (int(r["x"]), int(r["y"])) for r in csv.DictReader(f)
        }


def _mni(net: str) -> dict[str, np.ndarray]:
    gsn = REPO / "resources" / "ElectrodeCaps_MNI" / f"{net}.csv"
    if gsn.is_file():
        with gsn.open(newline="") as f:
            return {
                r[4]: np.array(r[1:4], float)
                for r in csv.reader(f)
                if r and r[0] == "Electrode"
            }
    guide = REPO / "tit" / "scene" / "guide-mni" / "nets" / f"{net}.csv.json"
    return {
        e["name"]: np.array(e["world"], float)
        for e in json.loads(guide.read_text())["electrodes"]
    }


AGREEMENT = [
    ("GSN-256.csv", "GSN-HydroCel-256"),
    ("GSN-256.csv", "GSN-HydroCel-185"),
    ("10-10.csv", "EEG10-10_UI_Jurak_2007"),
    ("10-10.csv", "EEG10-10_Cutini_2011"),
    ("10-10.csv", "EEG10-10_Neuroelectrics"),
    ("10-10.csv", "EEG10-20_Okamoto_2004"),
]


@pytest.mark.parametrize("template,net", AGREEMENT)
def test_template_matches_the_3d_cap(template, net):
    ten_ten = _template("10-10.csv")
    centre = (
        float(np.median([ten_ten[k][0] for k in ("Fpz", "Cz", "Oz")])),
        ten_ten["Cz"][1],
    )
    pixels, cap = _template(template), _mni(net)
    common = sorted(set(pixels) & set(cap))
    assert len(common) >= 18
    px = np.array([pixels[k] for k in common], float)
    mm = np.array([cap[k] for k in common])
    assert np.corrcoef(px[:, 0], mm[:, 0])[0, 1] >= 0.9
    assert np.corrcoef(px[:, 1], -mm[:, 1])[0, 1] >= 0.9
    az_px = np.degrees(np.arctan2(-(px[:, 1] - centre[1]), px[:, 0] - centre[0]))
    az_mm = np.degrees(np.arctan2(mm[:, 1] - VERTEX[1], mm[:, 0] - VERTEX[0]))
    assert np.median(np.abs((az_px - az_mm + 180) % 360 - 180)) < 10
    lateral = np.abs(mm[:, 0]) > 15
    assert np.all(np.sign(px[lateral, 0] - centre[0]) == np.sign(mm[lateral, 0]))
    sagittal = np.abs(mm[:, 1] - VERTEX[1]) > 15
    front = np.sign(-(px[sagittal, 1] - centre[1])) == np.sign(
        mm[sagittal, 1] - VERTEX[1]
    )
    assert front.mean() >= 0.9
