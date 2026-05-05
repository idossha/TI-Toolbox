#!/usr/bin/env simnibs_python
"""Render PNG visualizations of electrode montage placements.

Overlays coloured rings and arc connections on a template EEG cap
image using ImageMagick ``convert``.  Called automatically by the
simulation pipeline to document the active montage.

Public API
----------
visualize_montage
    Render a PNG for a single montage or a combined multi-montage image.

See Also
--------
tit.tools.map_electrodes : Map optimised positions to net labels.
tit.sim : Simulation pipeline that invokes the visualiser.
"""

import os
import subprocess

# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

_RESOURCES_DIR = "/ti-toolbox/resources/amv"

_COORD_FILES: dict[str, str] = {
    "GSN-HydroCel-185.csv": "GSN-256.csv",
    "GSN-HydroCel-256.csv": "GSN-256.csv",
    "GSN-HydroCel-185": "GSN-256.csv",
    "EEG10-10_UI_Jurak_2007.csv": "10-10.csv",
    "EEG10-10_Cutini_2011.csv": "10-10.csv",
    "EEG10-20_Okamoto_2004.csv": "10-10.csv",
    "EEG10-10_Neuroelectrics.csv": "10-10.csv",
}

_SKIP_NETS = {
    "easycap_BC_TMS64_X21.csv",
    "EEG10-20_extended_SPM12",
    "freehand",
    "flex_mode",
}

_COLORS = ["blue", "red", "green", "purple", "orange", "cyan", "chocolate", "violet"]
_RINGS = [f"pair{i}ring.png" for i in range(1, 9)]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def get_expected_output_filename(montage_name: str, sim_mode: str = "U") -> str:
    """Return the expected montage visualization PNG filename."""
    if sim_mode == "U":
        return f"{montage_name}_highlighted_visualization.png"
    return "combined_montage_visualization.png"


def is_skipped_net(eeg_net: str) -> bool:
    """Return True when montage visualization is intentionally skipped."""
    return eeg_net in _SKIP_NETS


def is_supported_net(eeg_net: str) -> bool:
    """Return True when a coordinate map exists for *eeg_net*."""
    return eeg_net in _COORD_FILES


def _load_coordinates(eeg_net: str) -> dict[str, tuple[int, int]] | None:
    """Return {electrode_label: (x, y)} for the given EEG net."""
    fname = _COORD_FILES.get(eeg_net)
    if fname is None:
        raise ValueError(f"Unsupported EEG net for montage visualization: {eeg_net}")

    coords: dict[str, tuple[int, int]] = {}
    with open(os.path.join(_RESOURCES_DIR, fname)) as f:
        for lineno, line in enumerate(f):
            parts = line.strip().split(",")
            if lineno == 0 and not parts[1].replace(".", "").replace("-", "").isdigit():
                continue  # skip header row
            coords[parts[0]] = (int(float(parts[1])), int(float(parts[2])))
    return coords


def _overlay_ring(image: str, x: int, y: int, color: str, ring: str) -> None:
    """Composite a coloured ring PNG onto *image* at *(x, y)*."""
    subprocess.run(
        [
            "convert",
            image,
            "(",
            ring,
            "-fill",
            color,
            "-colorize",
            "100,100,100",
            ")",
            "-geometry",
            f"+{x - 50}+{y - 50}",
            "-composite",
            image,
        ],
        check=True,
    )


def _draw_arc(image: str, x1: int, y1: int, x2: int, y2: int, color: str) -> None:
    """Draw a Bezier arc between two electrode positions on *image*."""
    dx, dy = x2 - x1, y2 - y1
    dist = (dx**2 + dy**2) ** 0.5
    if dist == 0:
        return
    ux, uy = dx / dist, dy / dist
    sx, sy = x1 + ux * 15, y1 + uy * 15
    ex, ey = x2 - ux * 15, y2 - uy * 15
    cx = (sx + ex) / 2 + (-dy / dist) * dist * 0.25
    cy = (sy + ey) / 2 + (dx / dist) * dist * 0.25
    subprocess.run(
        [
            "convert",
            image,
            "-stroke",
            color,
            "-strokewidth",
            "3",
            "-fill",
            "none",
            "-draw",
            f"bezier {sx},{sy} {cx},{cy} {ex},{ey}",
            image,
        ],
        check=True,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def visualize_montage(
    montage_name: str,
    electrode_pairs: list[list[str]],
    eeg_net: str,
    output_dir: str,
    sim_mode: str = "U",
    logger=None,
) -> None:
    """Render a PNG showing electrode positions and connection arcs.

    Parameters
    ----------
    montage_name : str
        Used as the output filename base (unipolar) or ``"combined"``
        (multipolar).
    electrode_pairs : list of list of str
        Electrode pairs, e.g.
        ``[["E030", "E020"], ["E095", "E070"]]``.
    eeg_net : str
        EEG cap name, e.g. ``"GSN-HydroCel-185.csv"``.
    output_dir : str
        Directory to write the output PNG(s) into.
    sim_mode : str, optional
        ``"U"`` produces one image per montage; ``"M"`` produces a
        single combined image.  Default ``"U"``.
    """
    if is_skipped_net(eeg_net):
        expected = get_expected_output_filename(montage_name, sim_mode)
        if logger is not None:
            logger.warning(
                "Montage visualization unavailable for EEG net '%s'; "
                "skipping render. Expected output would be %s in %s.",
                eeg_net,
                expected,
                output_dir,
            )
        return

    coords = _load_coordinates(eeg_net)

    template = os.path.join(_RESOURCES_DIR, "GSN-256.png")
    os.makedirs(output_dir, exist_ok=True)

    if sim_mode == "U":
        out_image = os.path.join(
            output_dir, get_expected_output_filename(montage_name, sim_mode)
        )
        subprocess.run(["cp", template, out_image], check=True)
    else:
        out_image = os.path.join(
            output_dir, get_expected_output_filename(montage_name, sim_mode)
        )
        if not os.path.exists(out_image):
            subprocess.run(["cp", template, out_image], check=True)

    for i, pair in enumerate(electrode_pairs):
        e1, e2 = pair
        color = _COLORS[i % len(_COLORS)]
        ring = os.path.join(_RESOURCES_DIR, _RINGS[i % len(_RINGS)])
        if e1 in coords:
            _overlay_ring(out_image, *coords[e1], color, ring)
        if e2 in coords:
            _overlay_ring(out_image, *coords[e2], color, ring)
        if e1 in coords and e2 in coords:
            _draw_arc(out_image, *coords[e1], *coords[e2], color)
