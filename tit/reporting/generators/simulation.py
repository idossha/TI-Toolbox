"""Simulator report: one self-contained HTML record per simulated montage.

Built on :mod:`tit.reporting.html.components` (ARCHITECTURE.md §14) like the DTI report. Everything
is read from what the simulation wrote: ``documentation/config.json`` (montage, currents,
electrodes, conductivity), the SimNIBS log (whether the DTI tensor was used, the solver, the
calibration error), ``high_Frequency/analysis/fields_summary.txt`` (per-carrier grey-matter percentiles),
and the grey/white-matter envelope: the run's NIfTIs when it wrote them (``map_to_vol``), else
its grey/white field meshes voxelised onto the T1 grid in a scratch directory, by the same
conversion, and not kept. The page has no checks.

The default view is the verdict with the grey-matter envelope (99.9th percentile, median and where its
maximum is, in MNI through charm's warp), the montage on the app's EEG-cap overlay with its dose, and the envelope in three planes;
per-carrier fields, methods, references and the run record are collapsed under Technical details.

``tit.sim`` writes one after every montage (:meth:`tit.sim.base.BaseSimulation.run`). Rebuild one
(nothing is re-simulated)::

    simnibs_python -m tit.reporting.generators.simulation <project> <subject> <simulation> [--out DIR]
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from tit.reporting.generators import common
from tit.reporting.generators.common import fmt
from tit.reporting.html import components as c
from tit.reporting.html.components import esc

logger = logging.getLogger(__name__)

REPORT_PREFIX = "simulation_report"
#: Report size budget (bytes); the rebuild command and tests check it.
SIZE_BUDGET = 1_500_000

_CONDUCTIVITY = {
    "scalar": "isotropic (SimNIBS standard tissue values)",
    "vn": "anisotropic, volume-normalised (vn)",
    "dir": "anisotropic, direct mapping (dir)",
    "mc": "anisotropic, mean conductivity (mc)",
}
#: The source of the tensor-to-conductivity mapping the page names (SimNIBS's anisotropy_type).
_CONDUCTIVITY_CITE = {
    "vn": ("opitz2011_tissue_efield",),
    "mc": ("opitz2011_tissue_efield",),
    "dir": ("tuch2001_conductivity", "rullmann2009_dti_conductivity"),
}


# ── reading the simulation's outputs ─────────────────────────────────────


def parse_fields_summary(text: str) -> list[dict]:
    """Per carrier (``ernie_TDCS_1``, …): the grey-matter ``magnE`` percentiles SimNIBS printed."""
    out = []
    for block in re.split(r"\n(?=\S+\n=+\n)", text.strip()):
        name = block.split("\n", 1)[0].strip()
        head = re.search(r"\|Field\s*\|(.+)\|", block)
        row = re.search(r"\|magnE\s*\|(.+)\|", block)
        if not (head and row):
            continue
        pcts = [h.strip().rstrip("%") for h in head.group(1).split("|")]
        vals = [float(v.split()[0]) for v in row.group(1).split("|")]
        out.append({"name": name, **{f"p{p}": v for p, v in zip(pcts, vals)}})
    return out


def parse_log(text: str) -> dict:
    """What the SimNIBS log says about the run: the tensor, the solver, the calibration error, the
    SimNIBS version."""
    tensor = re.search(r"Using anisotropic .*? based on the file: (\S+)", text)
    solver = re.search(r"Using solver options: (\S+)", text)
    return {
        "tensor": tensor.group(1) if tensor else None,
        "solver": solver.group(1) if solver else None,
        "calibration_error_pct": [
            float(v) for v in re.findall(r"current calibration error: ([\d.]+)%", text)
        ],
        "simnibs": (re.search(r"simnibs (\d[\w.]*)", text) or [None, None])[1],
    }


def _envelope_niftis(sim_dir: Path, name: str, mode: str) -> dict[str, Path]:
    """``{"grey": …, "white": …}`` subject-space envelope NIfTIs (``<mode>/niftis/<tissue>_<name>_*_subject_*TI_max.nii.gz``).

    mesh2nii also writes ``*_MNI_*`` volumes beside them; those are 4-D and in another frame.
    """
    out = {}
    for tissue in ("grey", "white"):
        hits = sorted(
            (sim_dir / mode / "niftis").glob(
                f"{tissue}_{glob.escape(name)}_*_subject_*TI_max.nii.gz"
            )
        )
        if hits:
            out[tissue] = hits[0]
    return out


def _voxelised_envelope(
    sim_dir: Path, name: str, mode: str, m2m: Path, scratch: Path
) -> dict[str, Path]:
    """``{"grey": …, "white": …}`` envelope NIfTIs voxelised from the field meshes into *scratch*.

    The on-demand path's conversion (:func:`tit.volume_fields.voxelise`, onto the T1 grid) of
    ``<mode>/mesh/<tissue>_<name>_<mode>.msh``'s envelope only; nothing is written into the
    simulation.

    Raises:
        FieldUnavailableError: a tissue's field mesh is missing or carries no envelope.
        RuntimeError: the conversion did not write a volume.
    """
    from tit.volume_fields import voxelise

    field = "mTI_max" if mode == "mTI" else "TI_max"
    return {
        tissue: voxelise(
            sim_dir / mode / "mesh" / f"{tissue}_{name}_{mode}.msh",
            m2m,
            scratch,
            [field],
        )[field]
        for tissue in ("grey", "white")
    }


def _volume(img) -> np.ndarray:
    """The image's voxels as float32, 3-D: trailing single frames (``(X, Y, Z, 1)``) dropped."""
    data = np.asarray(img.dataobj, dtype=np.float32)
    while data.ndim > 3 and data.shape[-1] == 1:
        data = data[..., 0]
    return data


def collect(
    sim_dir: str | Path, *, m2m: Path | None = None, scratch: Path | None = None
) -> dict:
    """Everything the report shows, from one simulation folder.

    With *m2m* and *scratch*, a run that wrote no envelope NIfTIs has its field meshes
    voxelised into *scratch* (:func:`_voxelised_envelope`) for the envelope statistics and figure.
    """
    sim_dir = Path(sim_dir)
    doc = sim_dir / "documentation"
    config = json.loads((doc / "config.json").read_text())
    logs = sorted(doc.glob("simnibs_simulation_*.log"))
    log = parse_log(logs[-1].read_text(errors="replace")) if logs else parse_log("")
    summary = sim_dir / "high_Frequency" / "analysis" / "fields_summary.txt"
    mode = "mTI" if str(config.get("simulation_mode", "TI")).upper() == "MTI" else "TI"
    rec = {
        "name": config.get("simulation_name") or sim_dir.name,
        "mode": mode,
        "config": config,
        "log": log,
        "carriers": (
            parse_fields_summary(summary.read_text()) if summary.is_file() else []
        ),
        "envelope": None,
    }
    # A carrier-only control computes no envelope; a TI volume in its folder is from another run.
    niftis = (
        {}
        if config.get("carrier_only")
        else _envelope_niftis(sim_dir, rec["name"], mode)
    )
    if not config.get("carrier_only") and "grey" not in niftis and scratch is not None:
        from tit.volume_fields import FieldUnavailableError

        try:
            niftis = _voxelised_envelope(sim_dir, rec["name"], mode, Path(m2m), scratch)
        except (FieldUnavailableError, RuntimeError) as exc:
            # The report stands without its envelope figure, and says why on the page.
            rec["figure_note"] = str(exc)
            logger.warning(f"Simulation report: envelope not voxelised ({exc})")
    if "grey" in niftis:
        import nibabel as nib

        img = nib.load(niftis["grey"])
        gm = _volume(img)
        v = gm[gm > 0]
        if v.size:
            ijk = np.unravel_index(np.nanargmax(gm), gm.shape)
            rec["envelope"] = {
                "median": float(np.median(v)),
                "p99_9": float(np.percentile(v, 99.9)),
                "max": float(v.max()),
                "peak_world": [
                    float(x) for x in img.affine[:3, :3] @ ijk + img.affine[:3, 3]
                ],
                "peak_mni": None,
            }
    rec["niftis"] = {k: str(p) for k, p in niftis.items()}
    return rec


# ── the envelope figure ──────────────────────────────────────────────────


def hotspot_centre(grey: np.ndarray, hi: float) -> tuple[int, int, int]:
    """The voxel the envelope figure is centred on, inside the grey-matter hot spot.

    The hot spot is the face-connected set of grey-matter voxels at or above *hi* (the grey
    99.9th percentile) that holds the grey maximum; the centre is its voxel nearest to its
    centroid, so the three slices cross it and the field there is at least *hi*. Only grey
    matter counts, and NaN voxels are neither the peak nor hot. (The mean position of every
    grey or white voxel above *hi*, used before, fell between hot spots: 9-17 voxels from any
    of them on 4 of 6 Dataset 000 simulations.)

    Args:
        grey: Grey-matter envelope (V/m), 3-D.
        hi: The grey-matter 99.9th percentile (V/m).

    Returns:
        The centre voxel's indices.
    """
    g = np.where(np.isnan(grey), -np.inf, grey)
    peak = tuple(int(i) for i in np.unravel_index(np.argmax(g), g.shape))
    hot = {tuple(p) for p in np.argwhere(g >= hi).tolist()}
    if peak not in hot:
        return peak
    spot, frontier = {peak}, [peak]
    while frontier:
        grown = []
        for i, j, k in frontier:
            for n in (
                (i - 1, j, k),
                (i + 1, j, k),
                (i, j - 1, k),
                (i, j + 1, k),
                (i, j, k - 1),
                (i, j, k + 1),
            ):
                if n in hot and n not in spot:
                    spot.add(n)
                    grown.append(n)
        frontier = grown
    pts = np.array(sorted(spot))
    best = pts[np.argmin(((pts - pts.mean(axis=0)) ** 2).sum(axis=1))]
    return tuple(int(v) for v in best)


def field_images(rec: dict, t1_path: str | Path) -> dict | None:
    """Axial, coronal and sagittal envelope panels through the grey-matter hot spot, over the T1;
    WebP bytes plus label geometry."""
    import nibabel as nib

    from tit.plotting import slices as s

    if "grey" not in rec["niftis"] or not rec["envelope"]:
        return None
    t1_img = nib.load(str(t1_path))
    t1, affine = s.canonical(_volume(t1_img), t1_img.affine)
    field = np.zeros_like(t1)
    tissues = {}
    for tissue, path in rec["niftis"].items():
        img = nib.load(path)
        f, _ = s.canonical(_volume(img), img.affine)
        if f.shape != t1.shape:
            return None
        field = np.maximum(field, f)
        tissues[tissue] = f
    brain = field > 0
    lo, hi = rec["envelope"]["median"], rec["envelope"]["p99_9"]
    # A uniform envelope (median == 99.9th percentile) is drawn at the top of the scale, not 0 / 0;
    # the step is relative because the volume is float32 (hi > 0: it is a percentile of field > 0).
    draw_lo = lo if hi > lo else hi * (1 - 1e-6)
    centre = hotspot_centre(tissues["grey"], hi)
    box = s.brain_box(brain)
    t1_lo, t1_hi = np.percentile(t1[brain], [1, 99])
    grey = (
        np.clip((t1 - t1_lo) / (t1_hi - t1_lo), 0, 1)
        if t1_hi > t1_lo
        else np.zeros_like(t1)  # a constant T1 has no contrast to show
    )
    world = affine[:3, :3] @ centre + affine[:3, 3]
    names = ("sagittal", "coronal", "axial")
    tiles, labels = [], []
    for axis in (2, 1, 0):
        rgb = s.overlay(
            s.oriented(grey, axis, centre[axis], box),
            s.oriented(field, axis, centre[axis], box),
            draw_lo,
            hi,
        )
        tiles.append(rgb)
        labels.append(f"{names[axis]} {'xyz'[axis]} = {world[axis]:+.0f} mm")
    image, tile = s.mosaic(tiles, cols=3)
    return {
        "image": s.render(image, []),
        "labels": labels,
        "tile": tile,
        "shape": image.shape,
        "lo": lo,
        "hi": hi,
        "stops": s.colour_stops(),
        "centred_on": "the grey-matter hot spot (top 0.1 %)",
    }


def to_mni(world: list[float], m2m: Path) -> list[float] | None:
    """Subject mm to MNI mm through charm's warp (``toMNI/Conform2MNI_nonl``), read at one voxel;
    ``None`` without the warp."""
    import nibabel as nib

    warp = m2m / "toMNI" / "Conform2MNI_nonl.nii.gz"
    if not warp.is_file():
        return None
    img = nib.load(str(warp))
    ijk = np.round(np.linalg.inv(img.affine) @ [*world, 1])[:3].astype(int)
    if (ijk < 0).any() or (ijk >= img.shape[:3]).any():
        return None
    return [float(v) for v in np.asarray(img.dataobj[tuple(ijk)])]


def _peak_at(env: dict) -> str:
    """``MNI (-12, -80, 4) mm``, or subject-space mm when there is no warp."""
    if env["peak_mni"]:
        return "MNI ({:.0f}, {:.0f}, {:.0f}) mm".format(*env["peak_mni"])
    return "({:.0f}, {:.0f}, {:.0f}) mm, subject space".format(*env["peak_world"])


def _colour_bar(lo: float, hi: float, stops: list[str]) -> str:
    grad = ",".join(stops)
    return (
        f'<div class="cbar"><span class="num">{lo:.2f}</span><i style="background:linear-gradient(90deg,{grad})"></i>'
        f'<span class="num">{hi:.2f} V/m</span></div>'
    )


EXTRA_CSS = (
    ".cbar{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--ink-2);margin-top:8px;max-width:460px}"
    ".cbar i{flex:1;height:10px;border-radius:2px}"
)


# ── the page ─────────────────────────────────────────────────────────────


def build_html(
    rec: dict,
    images: dict | None,
    subject_id: str,
    generated: datetime | None = None,
) -> str:
    """The whole report from the collected record and the rendered envelope figure."""
    import tit

    generated = generated or datetime.now()
    cfg, log, env = rec["config"], rec["log"], rec["envelope"]
    cite = c.Cites()
    fig_no = iter(range(1, 20))
    raw_pairs = [list(p) for p in cfg.get("electrode_pairs") or []]
    xyz = any(isinstance(e, (list, tuple)) for p in raw_pairs for e in p)
    pairs = [[common.electrode_name(e) for e in p] for p in raw_pairs]
    # One current per pair: SimNIBS read the first two for TI and one per pair for mTI, and a
    # config.json written before 2026-10-22 recorded every configured value.
    currents = [float(v) for v in cfg.get("intensities") or []]
    currents = currents[: len(pairs)] if pairs else currents
    total = sum(abs(v) for v in currents)  # a negative current is a polarity
    seal = "pass"
    cond = cfg.get("conductivity", "scalar")
    overrides = ", ".join(
        f"tissue {k} = {v:g} S/m"
        for k, v in sorted(
            (int(k), float(v))
            for k, v in (cfg.get("tissue_conductivities") or {}).items()
        )
    )
    carrier_only = bool(cfg.get("carrier_only"))
    # A coordinate already holds minus signs, so its pairs read "a → b", not "a–b".
    montage = (
        " and ".join((" → " if xyz else "–").join(p) for p in pairs) or rec["name"]
    )
    per_ch = common.per_channel(currents)

    # ── 1. verdict ──
    if env:
        headline = f"{env['p99_9']:.3f} V/m peak envelope in grey matter"
    elif carrier_only:
        headline = f"{rec['name']}: carrier-only control, no envelope (ΔF = 0)"
    else:
        headline = f"{rec['name']} simulated; no grey-matter envelope was written"
    tensor = log["tensor"]
    cond_txt = _CONDUCTIVITY.get(cond, esc(cond))
    if cond != "scalar":
        cond_txt += (
            " from the subject's DTI tensor"
            if tensor
            else " (the log does not confirm a tensor was read)"
        )
    if overrides and cond == "scalar":
        cond_txt = f"isotropic (SimNIBS standard tissue values except {overrides})"
    elif overrides:
        cond_txt += f"; {overrides}"
    if carrier_only:
        kind = "Carrier-only control"
    elif rec["mode"] == "mTI":
        kind = "Multichannel temporal interference"
    else:
        kind = "Temporal interference"
    lede = (
        f"{kind} with {esc(montage)} "
        f"at {per_ch} mA per channel ({fmt(total)} mA total), {cond_txt}."
    )
    if carrier_only:
        lede += (
            " Both channels ran at one frequency, in phase, so the carriers add without a "
            "beat and there is no envelope."
        )
    if env:
        lede += (
            f" In grey matter the envelope reaches {env['p99_9']:.3f} V/m (99.9th percentile), "
            f"median {env['median']:.3f} V/m; its maximum, {env['max']:.3f} V/m, is at {_peak_at(env)}."
        )
    key = []
    if env:
        key += [
            (
                "Grey matter 99.9th pct",
                f"{env['p99_9']:.3f}<small>V/m</small>",
                "peak envelope",
            ),
            (
                "Grey matter median",
                f"{env['median']:.3f}<small>V/m</small>",
                "half of grey matter is above this",
            ),
            (
                "Grey matter maximum",
                f"{env['max']:.3f}<small>V/m</small>",
                esc(f"at {_peak_at(env)}"),
            ),
        ]
    key.append(
        (
            "Total current",
            f"{fmt(total)}<small>mA</small>",
            f"{len(currents)} channels × {per_ch} mA",
        )
    )
    verdict_sec = c.verdict_section(seal, headline, lede, c.stats(key))

    # ── 2. montage ──
    geo = cfg.get("electrode_geometry") or {}
    dims = "×".join(f"{d:g}" for d in geo.get("dimensions") or [])
    dose = [
        (
            "Electrodes",
            esc(
                f"{geo.get('shape', '?')} {dims} mm, gel {geo.get('gel_thickness', '?')} mm, rubber {geo.get('rubber_thickness', '?')} mm"
            ),
        ),
        (
            "Current",
            f"{per_ch} mA per channel, {fmt(total)} mA total (each electrode carries its channel's current)",
        ),
        (
            "Carrier frequencies",
            (
                "one frequency for both channels, in phase (ΔF = 0)"
                if carrier_only
                else "not part of the field model (quasi-static); set them on the stimulator"
            ),
        ),
        (
            "EEG net",
            (
                "none: electrodes placed at subject-space coordinates (mm)"
                if xyz
                else esc(Path(str(cfg.get("eeg_net") or "—")).stem)
            ),
        ),
        (
            "Conductivity",
            cond_txt + (f": <code>{esc(Path(tensor).name)}</code>" if tensor else ""),
        ),
    ]
    if xyz or cfg.get("is_xyz_montage") or not cfg.get("eeg_net"):
        cap = c.kv(common.channel_rows(pairs, currents))
    else:
        cap = common.cap_figure(next(fig_no), pairs, cfg["eeg_net"], currents)
    montage_sec = c.section(
        "montage",
        "Montage and dose",
        cap + '<h3 class="sub">Dose</h3>' + c.kv(dose),
        lead="Where the current goes in and how much.",
    )

    # ── 3. field ──
    body = ""
    if images:
        labels = c.tile_labels(images["labels"], 3, images["tile"], images["shape"])
        body += c.figure(
            next(fig_no),
            "TI envelope amplitude",
            f'<div class="lightbox"><div class="lb-inner">{c.img(images["image"], "TI envelope over the T1, through " + images["centred_on"])}{labels}</div></div>'
            + _colour_bar(images["lo"], images["hi"], images["stops"]),
            f"Slices through {images['centred_on']}. Coloured where the envelope is above the grey-matter median "
            f"({images['lo']:.2f} V/m), up to its 99.9th percentile; grey and white matter only. "
            "Neurological convention: subject left on image left.",
        )
    elif carrier_only:
        body = '<p class="muted">No envelope figure: a carrier-only control has no envelope.</p>'
    elif rec.get("figure_note"):
        body = f'<p class="muted">No envelope figure: {esc(rec["figure_note"])}</p>'
    else:
        body = '<p class="muted">No envelope figure: the grey-matter envelope or the T1 could not be read.</p>'
    field_sec = c.section(
        "field",
        "Field",
        body,
        lead=(
            "A carrier-only control has no envelope (ΔF = 0)."
            if carrier_only
            else "Where the envelope is strongest."
        ),
    )

    # ── 4. technical details ──
    tech = ""
    if rec["carriers"]:
        pct = [k for k in rec["carriers"][0] if k.startswith("p")]
        tech += c.details(
            "Carrier fields",
            c.table(
                ["Carrier", "Channel"] + [f"{k[1:]} %" for k in pct],
                [
                    [
                        esc(cr["name"]),
                        (
                            esc(common.channel_electrodes(pairs[i], i))
                            if i < len(pairs)
                            else ""
                        ),
                    ]
                    + [f"{cr[k]:.3f}" for k in pct]
                    for i, cr in enumerate(rec["carriers"])
                ],
                caption="Each high-frequency carrier alone: grey-matter |E| percentiles (V/m) from SimNIBS's field summary.",
                right=set(range(2, 2 + len(pct))),
            )
            + (
                f'<p class="muted" style="font-size:13px;margin-top:10px">SimNIBS estimated the electrode current calibration error at '
                f"{', '.join(f'{v:g} %' for v in log['calibration_error_pct'])}.</p>"
                if log["calibration_error_pct"]
                else ""
            ),
            "per-carrier grey-matter percentiles",
        )
    paras = [
        (
            "A carrier-only control (both channels at one frequency, in phase) was"
            if carrier_only
            else "Temporal interference stimulation was"
        )
        + " simulated in TI-Toolbox with SimNIBS "
        f"{esc(log['simnibs'] or '')} {cite('saturnino2019_simnibs21')} on the head model of subject {esc(subject_id)} {cite('puonti2020_charm')}. "
        f"{len(pairs)} channels ({esc(montage)}) each delivered {per_ch} mA through {esc(geo.get('shape', ''))} {dims} mm electrodes with "
        f"{geo.get('gel_thickness', '?')} mm gel"
        + (
            f"; positions from the {esc(Path(str(cfg.get('eeg_net'))).stem)} layout {cite('jurcak2007_eeg_positions')}"
            if cfg.get("eeg_net") and "10-" in str(cfg.get("eeg_net"))
            else ""
        )
        + ". "
        + (
            f"Tissue conductivities were anisotropic in white and grey matter, derived from diffusion tensors ({esc(cond)}) "
            f"{cite(*_CONDUCTIVITY_CITE.get(cond, ()))}"
            + (f"; {overrides}" if overrides else "")
            + "."
            if cond != "scalar"
            else "Tissue conductivities were isotropic SimNIBS standard values"
            + (f" except {overrides}" if overrides else "")
            + "."
        ),
        (
            "With no frequency difference there is no beat and no envelope; the fields written "
            f"({esc(', '.join(cfg.get('output_fields') or []))}) are those of the summed carriers."
            if carrier_only
            else "The TI envelope was taken as the maximal modulation amplitude over field orientations "
            f"{cite('grossman2017_ti')}"
            + (
                f"; in grey matter its 99.9th percentile was {env['p99_9']:.3f} V/m and its median {env['median']:.3f} V/m."
                if env
                else "."
            )
        ),
    ]
    tech += c.details(
        "Methods and references",
        c.methods(paras) + '<h3 class="sub">References</h3>' + cite.listing(),
        "boilerplate generated from this run; check before use",
    )
    run = [
        ("Simulation", esc(rec["name"])),
        ("Created", esc(str(cfg.get("created_at", "—"))[:16].replace("T", " "))),
        ("TI-Toolbox", esc(tit.__version__)),
        ("SimNIBS", esc(log["simnibs"] or "not recorded")),
        ("Solver", esc(log["solver"] or "not recorded")),
    ]
    tech += c.details(
        "Run record",
        c.kv(run)
        + '<h3 class="sub">config.json</h3>'
        + c.code(json.dumps(cfg, indent=1)),
        "versions and the configuration as run",
    )

    masthead = c.masthead(
        (
            "Carrier-only control"
            if carrier_only
            else "TI simulation" if rec["mode"] == "TI" else "mTI simulation"
        ),
        rec["name"],
        [
            ("Subject", esc(subject_id)),
            ("Conductivity", esc(cond) + (" + custom tissues" if overrides else "")),
            ("Total current", f"{fmt(total)} mA"),
            ("Report", generated.strftime(common.STAMP)),
        ],
    )
    toc = [
        ("verdict", "Verdict", seal),
        ("montage", "Montage and dose", None),
        ("field", "Field", None),
        ("technical", "Technical details", None),
    ]
    return c.page(
        title=f"{rec['name']} simulation",
        kind="Simulation report",
        subject=f"sub-{subject_id}",
        toc=toc,
        body=masthead
        + verdict_sec
        + montage_sec
        + field_sec
        + c.section("technical", "Technical details", tech),
        footer=common.footer(generated),
        description=f"Simulation report for sub-{subject_id}, {rec['name']}: {headline}",
        generator=f"TI-Toolbox {tit.__version__}",
        extra_css=EXTRA_CSS,
    )


def create_simulation_report(
    project_dir: str | Path,
    subject_id: str,
    simulation_name: str,
    out_dir: str | Path | None = None,
) -> Path:
    """Write the report for one simulation folder; into the project's reports unless *out_dir*."""
    from tit.paths import get_path_manager

    t0 = time.time()
    pm = get_path_manager(str(project_dir))
    m2m = Path(pm.m2m(subject_id))
    with tempfile.TemporaryDirectory(prefix="tit-sim-report-") as scratch:
        rec = collect(
            pm.simulation(subject_id, simulation_name), m2m=m2m, scratch=Path(scratch)
        )
        if rec["envelope"]:
            try:
                rec["envelope"]["peak_mni"] = to_mni(rec["envelope"]["peak_world"], m2m)
            except (OSError, ValueError) as exc:
                logger.warning(f"Simulation report: peak left in subject space ({exc})")
        try:
            images = field_images(rec, m2m / "T1.nii.gz")
        except (OSError, ValueError) as exc:
            logger.warning(f"Simulation report: no envelope figure ({exc})")
            rec.setdefault("figure_note", str(exc))
            images = None
    html = build_html(rec, images, subject_id)
    return common.write_report(
        html,
        project_dir,
        subject_id,
        REPORT_PREFIX,
        SIZE_BUDGET,
        out_dir,
        t0,
        label="Simulation report",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild a simulation report from its outputs."
    )
    parser.add_argument("project_dir")
    parser.add_argument("subject_id")
    parser.add_argument("simulation")
    parser.add_argument(
        "--out", help="write the report here instead of into the project"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t0 = time.time()
    path = create_simulation_report(
        args.project_dir, args.subject_id, args.simulation, args.out
    )
    print(f"{path} {path.stat().st_size / 1e6:.2f} MB in {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
