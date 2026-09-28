"""What the simulator, flex-search and ex-search reports share: the montage on the EEG cap, the
ROI's name and writing the file, plus the simulator's current advisory.

The cap figure is the app's own overlay (:func:`tit.tools.montage_visualizer.visualize_montage`,
the image a simulation writes to ``montage_imgs/``), converted to WebP; nothing here draws a head.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from tit.reporting.html import components as c
from tit.reporting.html.components import Check, esc
from tit.reporting.qc_rules import RULES

logger = logging.getLogger(__name__)

STAMP = "%Y-%m-%d %H:%M"
#: Colour names of the cap overlay's channels, in pair order (montage_visualizer._COLORS).
CAP_COLOURS = (
    "blue",
    "red",
    "green",
    "purple",
    "orange",
    "cyan",
    "chocolate",
    "violet",
)

#: Cassarà 2025 gives frequency-dependent TI limits; the review could not tell whether they are
#: per channel or for the total current, so the report says exactly that.
KHZ_CAUTION = (
    "Cassarà 2025, Table 3: whether its kHz limits apply per channel or to the total "
    "current is not verified"
)


def fmt(v: float, digits: int = 3) -> str:
    return f"{v:.{digits}g}"


def per_channel(mA: list[float]) -> str:
    """``"1"`` when every channel carries the same current, else ``"0.7 / 1.3"`` (mA)."""
    return fmt(mA[0]) if len(set(mA)) == 1 else " / ".join(fmt(v) for v in mA)


def current_check(section: str, per_channel_mA: list[float]) -> Check:
    """The electrode-current advisory. Each electrode carries its channel's current, so the peak
    electrode current is the largest channel current; the total is their sum."""
    r = RULES[section]["electrode_peak_current"]
    peak, total = max(per_channel_mA), sum(per_channel_mA)
    return Check(
        "electrode_peak_current",
        r["label"],
        r["plain"],
        f"{fmt(peak)} mA per electrode ({fmt(total)} mA total)",
        f"< {r['value']:g} {r['unit']}",
        "pass" if peak < r["value"] else "warn",
        role=r["role"],
        value=peak,
        cite=r["cite"],
        note=KHZ_CAUTION,
    )


def rule_check(
    section: str, key: str, status: str, shown: str, threshold: str = ""
) -> Check:
    """A row for rule *key*, with its label, plain text, role and citations from ``RULES``."""
    r = RULES[section][key]
    return Check(
        key,
        r["label"],
        r["plain"],
        shown,
        threshold,
        status,
        role=r["role"],
        cite=r["cite"],
        note=r["note"],
    )


def attention_callouts(checks: list[Check], cite: c.Cites) -> str:
    """One callout per advisory that needs attention."""
    return "".join(
        c.callout(
            a.status,
            f"{esc(a.label)}: {esc(a.shown)} (rule {esc(a.threshold)}).",
            f"<p>{c.inline(a.description)} {cite.dois(list(a.cite))}</p>",
        )
        for a in checks
        if a.role == "advisory" and a.status in ("warn", "fail")
    )


def channel_rows(
    pairs: list[list[str]], currents_mA: list[float]
) -> list[tuple[str, str]]:
    """``(Ch 1A, "AF3 → PO10, 1 mA")`` per pair, named as the cap image's legend names them."""
    rows = []
    for i, (pair, mA) in enumerate(zip(pairs, currents_mA)):
        name = f"Ch {i // 2 + 1}{'AB'[i % 2]}"
        colour = CAP_COLOURS[i % len(CAP_COLOURS)]
        rows.append((f"{name} ({colour})", f"{esc(' → '.join(pair))}, {fmt(mA)} mA"))
    return rows


def cap_figure(
    num: int,
    pairs: list[list[str]],
    eeg_net: str,
    currents_mA: list[float],
    caption: str = "",
) -> str:
    """The montage on the app's EEG-cap overlay, beside the channel list; the list alone when
    the net has no cap template."""
    from tit.tools.montage_visualizer import montage_webp

    listing = c.kv(channel_rows(pairs, currents_mA))
    image = montage_webp(pairs, eeg_net)
    if image is None:
        return listing
    net = esc(Path(str(eeg_net)).stem)
    body = (
        f'<div class="split"><div class="cap">{c.img(image, f"Montage on the {net} cap: " + "; ".join(" to ".join(p) for p in pairs))}</div>'
        f"<div>{listing}</div></div>"
    )
    return c.figure(
        num,
        "Montage on the EEG cap",
        body,
        caption
        or f"Top view, nose up. Each colour is one channel, drawn on the {net} layout the app uses.",
    )


def _local_atlas(path: str) -> str:
    """An atlas path recorded inside the container, resolved to this machine's resources."""
    if os.path.isfile(path):
        return path
    from tit.paths import resolve_resource_path

    return resolve_resource_path("atlas", os.path.basename(path))


def roi_summary(run_dir: str | Path) -> dict | None:
    """The target as the run's ROI confirmation recorded it (``roi.tetravox.json``), with label
    names from the atlas's lookup table: ``{name, atlas, volume_mm3, centroid, gm_overlap}``.
    """
    scene = Path(run_dir) / "roi.tetravox.json"
    if not scene.is_file():
        return None
    meta = json.loads(scene.read_text()).get("meta") or {}
    name, atlas = meta.get("roi") or "", ""
    sources, labels = meta.get("source"), meta.get("label")
    if sources and labels is not None:
        from tit.opt.roi_spec import resolve_volume_label_names

        sources = sources if isinstance(sources, list) else [sources]
        labels = labels if isinstance(labels, list) else [labels]
        spaces = meta.get("space")
        spaces = spaces if isinstance(spaces, list) else [spaces] * len(sources)
        names = []
        for src, lab, space in zip(sources, labels, spaces):
            table = resolve_volume_label_names(_local_atlas(src), space or "subject")
            names.append(table.get(int(lab), f"label {lab}").replace("-", " "))
        name = " + ".join(dict.fromkeys(names))
        stems = dict.fromkeys(
            Path(s).name.split(".nii")[0] + (" (MNI)" if sp == "mni" else "")
            for s, sp in zip(sources, spaces)
        )
        atlas = ", ".join(stems)
    for s in meta.get("spheres") or []:
        x, y, z = s["centre_ras"]
        name = (
            name
            or f"sphere at ({x:.0f}, {y:.0f}, {z:.0f}) mm, radius {s['radius_mm']:g} mm"
        )
    return {
        "name": name or "target ROI",
        "atlas": atlas,
        "volume_mm3": meta.get("volume_mm3"),
        "centroid": meta.get("centroid_ras"),
        "gm_overlap": meta.get("gm_overlap"),
    }


def footer(generated: datetime) -> str:
    import tit

    return f"<span>TI-Toolbox {esc(tit.__version__)}</span><span>Generated {generated.strftime(STAMP)}</span>"


def write_report(
    html: str,
    project_dir: str | Path,
    subject_id: str,
    prefix: str,
    budget: int,
    out_dir: str | Path | None = None,
    t0: float | None = None,
    label: str = "Report",
) -> Path:
    """Write ``<reports>/sub-<id>/<prefix>_<timestamp>.html`` (or into *out_dir*), log its size and
    time, and record it as a ``report`` artifact of the running job (a no-op outside a job).
    """
    from tit.jobs import events
    from tit.paths import get_path_manager

    out = (
        Path(out_dir)
        if out_dir
        else Path(get_path_manager(str(project_dir)).reports()) / f"sub-{subject_id}"
    )
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    path.write_text(html, encoding="utf-8")
    size = path.stat().st_size
    took = f", {time.time() - t0:.1f} s" if t0 else ""
    logger.info(f"{label}: {path} ({size / 1e6:.2f} MB{took})")
    if size > budget:
        logger.warning(
            f"{label} is {size / 1e6:.2f} MB, over its {budget / 1e6:.1f} MB budget"
        )
    events.emit_artifact(str(path), kind="report", label=label)
    return path
