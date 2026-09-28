"""Simulator report: one self-contained HTML record per simulated montage.

Built on :mod:`tit.reporting.html.components` (ARCHITECTURE.md §14) like the DTI report. Everything
is read from what the simulation wrote: ``documentation/config.json`` (montage, currents,
electrodes, conductivity), the SimNIBS log (whether the DTI tensor was used, per-carrier currents,
the solves), ``high_Frequency/analysis/fields_summary.txt`` (per-carrier grey-matter percentiles),
and the grey/white-matter envelope NIfTIs. The page has no checks.

The default view is the verdict with the grey-matter envelope (99.9th percentile, median and where its
maximum is, in MNI through charm's warp), the montage on the app's EEG-cap overlay with its dose, and the envelope in three planes;
per-carrier fields, methods, references and the run record are collapsed under Technical details.

``tit.sim`` writes one after every montage (:meth:`tit.sim.base.BaseSimulation.run`). Rebuild one
(nothing is re-simulated)::

    simnibs_python -m tit.reporting.generators.simulation <project> <subject> <simulation> [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
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
    """What the SimNIBS log says about the run: carrier currents, the tensor, the solves."""
    tensor = re.search(r"Using anisotropic .*? based on the file: (\S+)", text)
    solver = re.search(r"Using solver options: (\S+)", text)
    return {
        "currents_A": [
            [float(v) for v in m.split(",")]
            for m in re.findall(r"Currents \(A\): \[([^\]]+)\]", text)
        ],
        "tensor": tensor.group(1) if tensor else None,
        "solver": solver.group(1) if solver else None,
        "n_solved": len(re.findall(r"Time to solve:", text)),
        "calibration_error_pct": [
            float(v) for v in re.findall(r"current calibration error: ([\d.]+)%", text)
        ],
        "simnibs": (re.search(r"simnibs (\d[\w.]*)", text) or [None, None])[1],
    }


def _envelope_niftis(sim_dir: Path, name: str, mode: str) -> dict[str, Path]:
    """``{"grey": …, "white": …}`` envelope NIfTIs (``<mode>/niftis/<tissue>_<name>_*TI_max.nii.gz``)."""
    out = {}
    for tissue in ("grey", "white"):
        hits = sorted(
            (sim_dir / mode / "niftis").glob(f"{tissue}_{name}_*TI_max.nii.gz")
        )
        if hits:
            out[tissue] = hits[0]
    return out


def collect(sim_dir: str | Path) -> dict:
    """Everything the report shows, from one simulation folder."""
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
    niftis = _envelope_niftis(sim_dir, rec["name"], mode)
    if "grey" in niftis:
        import nibabel as nib

        img = nib.load(niftis["grey"])
        gm = np.asarray(img.dataobj, dtype=np.float32)
        v = gm[gm > 0]
        if v.size:
            ijk = np.unravel_index(np.argmax(gm), gm.shape)
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


def field_images(rec: dict, t1_path: str | Path) -> dict | None:
    """Axial, coronal and sagittal envelope panels through the grey-matter hot spot, over the T1;
    WebP bytes plus label geometry."""
    import nibabel as nib

    from tit.plotting import slices as s

    if "grey" not in rec["niftis"] or not rec["envelope"]:
        return None
    t1_img = nib.load(str(t1_path))
    t1, affine = s.canonical(
        np.asarray(t1_img.dataobj, dtype=np.float32), t1_img.affine
    )
    field = np.zeros_like(t1)
    for path in rec["niftis"].values():
        img = nib.load(path)
        f, _ = s.canonical(np.asarray(img.dataobj, dtype=np.float32), img.affine)
        if f.shape != t1.shape:
            return None
        field = np.maximum(field, f)
    brain = field > 0
    lo, hi = rec["envelope"]["median"], rec["envelope"]["p99_9"]
    centre = np.round(np.argwhere(field >= hi).mean(axis=0)).astype(int)
    box = s.brain_box(brain)
    grey = np.clip(
        (t1 - np.percentile(t1[brain], 1)) / np.ptp(np.percentile(t1[brain], [1, 99])),
        0,
        1,
    )
    world = affine[:3, :3] @ centre + affine[:3, 3]
    names = ("sagittal", "coronal", "axial")
    tiles, labels = [], []
    for axis in (2, 1, 0):
        rgb = s.overlay(
            s.oriented(grey, axis, centre[axis], box),
            s.oriented(field, axis, centre[axis], box),
            lo,
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
    pairs = [list(p) for p in cfg.get("electrode_pairs") or []]
    currents = [float(v) for v in cfg.get("intensities") or []]
    total = sum(currents)
    seal = "pass"
    cond = cfg.get("conductivity", "scalar")
    montage = " and ".join("–".join(p) for p in pairs) or rec["name"]
    per_ch = common.per_channel(currents)

    # ── 1. verdict ──
    headline = (
        f"{env['p99_9']:.3f} V/m peak envelope in grey matter"
        if env
        else f"{rec['name']} simulated; no grey-matter envelope was written"
    )
    tensor = log["tensor"]
    cond_txt = _CONDUCTIVITY.get(cond, esc(cond))
    if cond != "scalar":
        cond_txt += (
            " from the subject's DTI tensor"
            if tensor
            else " (the log does not confirm a tensor was read)"
        )
    lede = (
        f"{'Multichannel temporal' if rec['mode'] == 'mTI' else 'Temporal'} interference with {esc(montage)} "
        f"at {per_ch} mA per channel ({fmt(total)} mA total), {cond_txt}."
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
            "not part of the field model (quasi-static); set them on the stimulator",
        ),
        ("EEG net", esc(Path(str(cfg.get("eeg_net") or "—")).stem)),
        (
            "Conductivity",
            cond_txt + (f": <code>{esc(Path(tensor).name)}</code>" if tensor else ""),
        ),
    ]
    if cfg.get("is_xyz_montage") or not cfg.get("eeg_net"):
        cap = c.kv(common.channel_rows([[str(e) for e in p] for p in pairs], currents))
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
    else:
        body = '<p class="muted">No envelope figure: the grey-matter envelope or the T1 could not be read.</p>'
    field_sec = c.section(
        "field",
        "Field",
        body,
        lead="Where the envelope is strongest.",
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
                        esc(" → ".join(pairs[i])) if i < len(pairs) else "",
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
        "Temporal interference stimulation was simulated in TI-Toolbox with SimNIBS "
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
            f"{cite(*_CONDUCTIVITY_CITE.get(cond, ()))}."
            if cond != "scalar"
            else "Tissue conductivities were isotropic SimNIBS standard values."
        ),
        "The TI envelope was taken as the maximal modulation amplitude over field orientations "
        f"{cite('grossman2017_ti')}"
        + (
            f"; in grey matter its 99.9th percentile was {env['p99_9']:.3f} V/m and its median {env['median']:.3f} V/m."
            if env
            else "."
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
        "TI simulation" if rec["mode"] == "TI" else "mTI simulation",
        rec["name"],
        [
            ("Subject", esc(subject_id)),
            ("Conductivity", esc(cond)),
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
    rec = collect(pm.simulation(subject_id, simulation_name))
    m2m = Path(pm.m2m(subject_id))
    if rec["envelope"]:
        try:
            rec["envelope"]["peak_mni"] = to_mni(rec["envelope"]["peak_world"], m2m)
        except (OSError, ValueError) as exc:
            logger.warning(f"Simulation report: peak left in subject space ({exc})")
    try:
        images = field_images(rec, m2m / "T1.nii.gz")
    except (OSError, ValueError) as exc:
        logger.warning(f"Simulation report: no envelope figure ({exc})")
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
