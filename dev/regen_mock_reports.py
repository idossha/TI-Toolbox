#!/usr/bin/env python3
"""Write the mock server's reports: real generator HTML and the real catalog's listing of it.

The desktop mock server (``desktop/tests/mock-server/server.mjs``) serves
``desktop/tests/fixtures/reports.json`` as ``GET /api/catalog/reports`` and the HTML under
``desktop/tests/fixtures/reports/<sid>/<stem>.html`` as ``GET /api/files/report/<sid>/<stem>``.
Both used to be written by hand (ids like ``ernie-thalamus-2026-08-01``, kind ``simulation``,
700-byte stub pages with no script), so no e2e ever rendered a real report. This script makes
them the real thing:

* the pages are ``tit.reporting.generators.simulation.build_html`` and
  ``tit.reporting.generators.ex_search.build_html`` run on synthetic simulation and ex-search
  folders (the file shapes the simulator and ex-search write; values authored here), written
  under the name grammar of ``common.write_report`` (``<prefix>_<YYYYMMDD>_<HHMMSS>.html``);
* ``reports.json`` is ``tit.catalog.reports`` over a project holding exactly those files, with
  the temporary root rewritten to the mock's ``/mnt/example``.

The mock world: ernie's ``Thalamus`` (TI) and ``docs_example`` (mTI) simulations have a report,
ernie's ``L_Insula`` has none (the Results page shows its artifacts instead), ernie's ex run
``ex_L_Insula_20260812_090000`` has its ex-search report, and 101's ``Thalamus`` has one.

Deterministic: the generation time, the file times and the toolbox version printed on the page
are pinned (the version as ``FIXTURE_VERSION``, so a release does not stale the fixtures); the
EEG-cap overlay (ImageMagick, absent on most hosts) is left out so the bytes do not depend on
the machine, and the envelope figure is a small grey ramp PNG made here.

Regenerate: ``.venv/bin/python dev/regen_mock_reports.py``; ``--check`` exits 1 when a committed
file differs (``tests/test_contract_fixtures_fresh.py`` runs the same check in the host suite).
"""

from __future__ import annotations

import argparse
import calendar
import importlib.util
import json
import os
import struct
import sys
import tempfile
import zlib
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "desktop" / "tests" / "fixtures"
MOCK_ROOT = "/mnt/example"
FIXTURE_VERSION = "0.0.0+mock-fixture"
NET_1010 = "EEG10-10_Cutini_2011.csv"

#: (subject, simulation, mode, pairs, mA, report time)
SIMULATIONS = [
    (
        "ernie",
        "Thalamus",
        "TI",
        [["F7", "P7"], ["F8", "P8"]],
        1.0,
        "2026-08-01T11:00:00",
    ),
    (
        "ernie",
        "docs_example",
        "mTI",
        [["F3", "F4"], ["P3", "P4"], ["C3", "C4"], ["O1", "O2"]],
        0.5,
        "2026-07-20T11:00:00",
    ),
    ("101", "Thalamus", "TI", [["F7", "P7"], ["F8", "P8"]], 1.5, "2026-08-05T11:00:00"),
]
#: (subject, run, report time)
EX_RUNS = [("ernie", "ex_L_Insula_20260812_090000", "2026-08-12T09:30:00")]

_LOG = (
    "[ simnibs 4.6.0 - 2026-08-01 10:58:22,260 - 3343 ]INFO: Currents (A): [{a}, -{a}]\n"
    "[ simnibs 4.6.0 - 2026-08-01 10:58:46,851 - 3343 ]INFO: Using solver options: hypre\n"
    "[ simnibs 4.6.0 - 2026-08-01 10:58:55,381 - 3343 ]INFO: Time to solve:   5.3871 s\n"
    "[ simnibs 4.6.0 - 2026-08-01 10:58:55,933 - 3343 ]INFO: Estimated current calibration error: 2.1%\n"
)
_CARRIER = (
    "{sid}_TDCS_{i}\n============\nGray Matter\n\nField Percentiles\n-----------------\n"
    "|Field |99.9%        |99.0%        |95.0%        |\n"
    "|------|-------------|-------------|-------------|\n"
    "|E     |{p:.2e} V/m |{q:.2e} V/m |{r:.2e} V/m |\n"
    "|magnE |{p:.2e} V/m |{q:.2e} V/m |{r:.2e} V/m |\n"
)
_LEADFIELD_LOG = (
    "[ simnibs 4.6.0 - 2026-08-11 17:38:24,694 - 936 ]INFO: Running simulations\n"
    "[ simnibs 4.6.0 - 2026-08-11 17:38:37,711 - 936 ]INFO: Placing Electrode:\n"
    "definition: plane\nshape: ellipse\ncentre: Fp1\ndimensions: [8, 8]\nthickness:[4]\n"
)


def _write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")


def ramp_png(width: int = 124, height: int = 50) -> bytes:
    """A grey left-to-right ramp, as PNG bytes (stdlib only, byte-deterministic)."""
    row = bytes([0]) + bytes(int(255 * x / (width - 1)) for x in range(width))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (
            struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(row * height, 9))
        + chunk(b"IEND", b"")
    )


def _simulation(pm, sid: str, name: str, mode: str, pairs: list, mA: float) -> Path:
    sim_dir = Path(pm.simulation(sid, name))
    config = {
        "subject_id": sid,
        "simulation_name": name,
        "simulation_mode": mode,
        "montage_mode": "net",
        "eeg_net": NET_1010,
        "conductivity": "scalar",
        "electrode_pairs": pairs,
        "is_xyz_montage": False,
        "intensities": [mA] * len(pairs),
        "electrode_geometry": {
            "shape": "ellipse",
            "dimensions": [8, 8],
            "gel_thickness": 4,
            "rubber_thickness": 2,
        },
        "output_fields": ["TI_max"] if mode == "TI" else ["mTI_max"],
        "created_at": "2026-08-01T10:58:20",
    }
    doc = sim_dir / "documentation"
    _write(doc / "config.json", json.dumps(config, indent=1))
    _write(doc / "simnibs_simulation_20260801-105820.log", _LOG.format(a=mA / 1e3))
    _write(
        sim_dir / "high_Frequency" / "analysis" / "fields_summary.txt",
        "\n\n".join(
            _CARRIER.format(
                sid=sid, i=i, p=0.2 * i * mA, q=0.1 * i * mA, r=0.05 * i * mA
            )
            for i in range(1, len(pairs) + 1)
        ),
    )
    return sim_dir


def _ex_run(pm, sid: str, run: str) -> Path:
    run_dir = Path(pm.ex_search_run(sid, run))
    _write(
        run_dir / "run_config.json",
        json.dumps(
            {
                "subject_id": sid,
                "roi_name": "L_Insula.csv",
                "roi_radius": 3.0,
                "leadfield_hdf": f"{sid}_leadfield_{NET_1010[:-4]}.hdf5",
                "electrode_mode": "bucket",
                "electrodes": {
                    "e1_plus": ["F7", "F3"],
                    "e1_minus": ["P7", "P3"],
                    "e2_plus": ["F8", "F4"],
                    "e2_minus": ["P8", "P4"],
                },
                "total_current_mA": 2.0,
                "current_step_mA": 0.5,
                "channel_limit_mA": 1.5,
            }
        ),
    )
    lines = [
        "Montage,Current_Ch1_mA,Current_Ch2_mA,TImax_ROI,TImean_ROI,TImean_GM,Focality,Composite_Index"
    ]
    plus1, minus1, plus2, minus2 = (
        ["F7", "F3"],
        ["P7", "P3"],
        ["F8", "F4"],
        ["P8", "P4"],
    )
    n = 0
    for a in plus1:
        for b in minus1:
            for c in plus2:
                for d in minus2:
                    for i1 in (0.5, 1.0, 1.5):
                        i2 = 2.0 - i1
                        n += 1
                        mean = 0.05 + 0.01 * ((n * 7) % 17)
                        foc = 0.9 + 0.02 * ((n * 5) % 13)
                        lines.append(
                            f"{a}_{b} <> {c}_{d}_I1-{i1}mA_I2-{i2}mA,{i1},{i2},"
                            f"{2 * mean:.4f},{mean:.4f},{mean / foc:.4f},{foc:.4f},{mean * foc:.4f}"
                        )
    _write(run_dir / "final_output.csv", "\n".join(lines) + "\n")
    _write(
        Path(pm.leadfields(sid)) / "simnibs_simulation_20260811-173824.log",
        _LEADFIELD_LOG,
    )
    return run_dir


def _stamp(iso: str) -> tuple[datetime, str, int]:
    when = datetime.fromisoformat(iso)
    return when, when.strftime("%Y%m%d_%H%M%S"), calendar.timegm(when.timetuple())


def _rewrite_root(value, root: Path):
    roots = sorted({str(root), os.path.realpath(root)}, key=len, reverse=True)
    if isinstance(value, str):
        for prefix in roots:
            value = value.replace(prefix, MOCK_ROOT)
        return value
    if isinstance(value, list):
        return [_rewrite_root(v, root) for v in value]
    if isinstance(value, dict):
        return {k: _rewrite_root(v, root) for k, v in value.items()}
    return value


def build() -> dict[str, str]:
    """``{path relative to desktop/tests/fixtures: text}`` for every report file and the listing."""
    import tit
    from tit import catalog
    from tit.paths import get_path_manager, reset_path_manager
    from tit.reporting.generators import ex_search
    from tit.reporting.generators import simulation as sim

    out: dict[str, str] = {}
    images = {
        "image": ramp_png(),
        "labels": ["sagittal", "coronal", "axial"],
        "tile": (50, 40),
        "shape": (50, 124),
        "lo": 0.17,
        "hi": 0.36,
        "stops": ["#000004", "#fcffa4"],
        "centred_on": "the grey-matter hot spot (top 0.1 %)",
    }
    with (
        tempfile.TemporaryDirectory() as tmp,
        patch.object(tit, "__version__", FIXTURE_VERSION),
        patch("tit.tools.montage_visualizer.montage_webp", return_value=None),
    ):
        root = Path(tmp) / "project"
        root.mkdir()
        reset_path_manager()
        pm = get_path_manager(str(root))
        subjects = (
            "101",
            "MNI152",
            "ernie",
        )  # the mock's subjects; a head model makes each known
        for sid in subjects:
            _write(Path(pm.m2m(sid)) / f"{sid}.msh", b"\0")
        written: list[tuple[Path, int]] = []
        for sid, name, mode, pairs, mA, iso in SIMULATIONS:
            when, stamp, epoch = _stamp(iso)
            rec = sim.collect(_simulation(pm, sid, name, mode, pairs, mA))
            rec["envelope"] = {
                "median": round(0.17 * mA, 4),
                "p99_9": round(0.36 * mA, 4),
                "hotspot_world": [-12.0, -18.0, 8.0],
                "hotspot_mni": [-12.4, -19.1, 7.9],
            }
            html = sim.build_html(rec, images, sid, generated=when)
            path = (
                Path(pm.reports()) / f"sub-{sid}" / f"{sim.REPORT_PREFIX}_{stamp}.html"
            )
            _write(path, html)
            written.append((path, epoch))
        for sid, run, iso in EX_RUNS:
            when, stamp, epoch = _stamp(iso)
            rec = ex_search.collect(_ex_run(pm, sid, run), pm.leadfields(sid))
            html = ex_search.build_html(rec, sid, generated=when)
            path = (
                Path(pm.reports())
                / f"sub-{sid}"
                / f"{ex_search.REPORT_PREFIX}_{stamp}.html"
            )
            _write(path, html)
            written.append((path, epoch))
        for path, epoch in written:
            os.utime(path, (epoch, epoch))
            out[f"reports/{path.parent.name[4:]}/{path.name}"] = path.read_text(
                encoding="utf-8"
            )
        listing = {
            sid: _rewrite_root(catalog.reports(pm, sid), root) for sid in subjects
        }
        reset_path_manager()
    out["reports.json"] = json.dumps(listing, indent=2) + "\n"
    return out


def _stub_missing_runtime_libraries() -> None:
    """The host suite's stubs for image-only libraries (``dev/gen_plan_output_dirs.py``)."""
    path = ROOT / "dev" / "gen_plan_output_dirs.py"
    spec = importlib.util.spec_from_file_location("gen_plan_output_dirs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._stub_missing_runtime_libraries()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if a committed file is stale"
    )
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    _stub_missing_runtime_libraries()
    files = build()
    stale = []
    for rel, text in files.items():
        path = FIXTURES / rel
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(rel)
            continue
        _write(path, text)
        print(f"wrote {path.relative_to(ROOT)}")
    extra = sorted(
        str(p.relative_to(FIXTURES))
        for p in (FIXTURES / "reports").rglob("*.html")
        if str(p.relative_to(FIXTURES)) not in files
    )
    if extra:
        print(f"not generated (delete): {', '.join(extra)}")
        stale.extend(extra)
    if stale:
        print(f"stale (run dev/regen_mock_reports.py): {', '.join(stale)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
