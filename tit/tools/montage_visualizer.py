#!/usr/bin/env simnibs_python
"""
Montage Visualizer — renders PNG visualizations of electrode placements.

Public API
----------
    visualize_montage(montage_name, electrode_pairs, eeg_net, output_dir, sim_mode)
"""

import os
import subprocess
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

_RESOURCES_DIR = "/ti-toolbox/resources/amv"

_COORD_FILES: Dict[str, str] = {
    "GSN-HydroCel-185.csv":        "GSN-256.csv",
    "GSN-HydroCel-256.csv":        "GSN-256.csv",
    "GSN-HydroCel-185":            "GSN-256.csv",  # legacy alias
    "EEG10-10_UI_Jurak_2007.csv":  "10-10.csv",
    "EEG10-10_Cutini_2011.csv":    "10-10.csv",
    "EEG10-20_Okamoto_2004.csv":   "10-10.csv",
    "EEG10-10_Neuroelectrics.csv": "10-10.csv",
}

_SKIP_NETS = {"easycap_BC_TMS64_X21.csv", "EEG10-20_extended_SPM12",
              "freehand", "flex_mode"}

_COLORS = ["blue", "red", "green", "purple", "orange", "cyan", "chocolate", "violet"]
_RINGS  = [f"pair{i}ring.png" for i in range(1, 9)]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_coordinates(eeg_net: str) -> Optional[Dict[str, Tuple[int, int]]]:
    """Return {electrode_label: (x, y)} for the given EEG net, or None if unsupported."""
    fname = _COORD_FILES.get(eeg_net)
    coords: Dict[str, Tuple[int, int]] = {}
    with open(os.path.join(_RESOURCES_DIR, fname)) as f:
        for line in f:
            parts = line.strip().split(",")
            coords[parts[0]] = (int(float(parts[1])), int(float(parts[2])))
    return coords


def _overlay_ring(image: str, x: int, y: int, color: str, ring: str) -> None:
    subprocess.run([
        "convert", image,
        "(", ring, "-fill", color, "-colorize", "100,100,100", ")",
        "-geometry", f"+{x - 50}+{y - 50}",
        "-composite", image,
    ], check=True)


def _draw_arc(image: str, x1: int, y1: int, x2: int, y2: int, color: str) -> None:
    dx, dy = x2 - x1, y2 - y1
    dist = (dx**2 + dy**2) ** 0.5
    if dist == 0:
        return
    ux, uy = dx / dist, dy / dist
    sx, sy = x1 + ux * 15, y1 + uy * 15
    ex, ey = x2 - ux * 15, y2 - uy * 15
    cx = (sx + ex) / 2 + (-dy / dist) * dist * 0.25
    cy = (sy + ey) / 2 + (dx / dist) * dist * 0.25
    subprocess.run([
        "convert", image,
        "-stroke", color, "-strokewidth", "3", "-fill", "none",
        "-draw", f"bezier {sx},{sy} {cx},{cy} {ex},{ey}",
        image,
    ], check=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def visualize_montage(
    montage_name: str,
    electrode_pairs: List[List[str]],
    eeg_net: str,
    output_dir: str,
    sim_mode: str = "U",
) -> None:
    """
    Render a PNG showing electrode positions and connection arcs.

    Parameters
    ----------
    montage_name    : used as output filename base (unipolar) or "combined" (multipolar)
    electrode_pairs : list of [e1, e2] pairs, e.g. [["E030","E020"],["E095","E070"]]
    eeg_net         : EEG cap name, e.g. "GSN-HydroCel-185.csv"
    output_dir      : directory to write PNG(s) into
    sim_mode        : "U" → one image per montage; "M" → single combined image
    """
    if eeg_net in _SKIP_NETS:
        return

    coords = _load_coordinates(eeg_net)

    template = os.path.join(_RESOURCES_DIR, "GSN-256.png")
    os.makedirs(output_dir, exist_ok=True)

    if sim_mode == "U":
        out_image = os.path.join(output_dir, f"{montage_name}_highlighted_visualization.png")
        subprocess.run(["cp", template, out_image], check=True)
    else:
        out_image = os.path.join(output_dir, "combined_montage_visualization.png")
        if not os.path.exists(out_image):
            subprocess.run(["cp", template, out_image], check=True)

    for i, pair in enumerate(electrode_pairs):
        if len(pair) != 2:
            continue
        e1, e2 = pair
        color = _COLORS[i % len(_COLORS)]
        ring  = os.path.join(_RESOURCES_DIR, _RINGS[i % len(_RINGS)])
        if e1 in coords:
            _overlay_ring(out_image, *coords[e1], color, ring)
        if e2 in coords:
            _overlay_ring(out_image, *coords[e2], color, ring)
        if e1 in coords and e2 in coords:
            _draw_arc(out_image, *coords[e1], *coords[e2], color)
