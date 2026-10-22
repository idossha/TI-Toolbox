#!/usr/bin/env python3
"""Write desktop/tests/fixtures/contracts/: real server responses the desktop's tests consume.

Each file is what the real code answers for a synthetic project this script builds in a temporary
directory, so a desktop unit test that reads it is held to the server's actual output, not to a
hand-written guess of it:

* ``candidate_detail_flex.json``, ``candidate_detail_ex.json``, ``candidate_detail_mex.json`` --
  ``tit.opt.candidate_catalog.candidate_detail`` (the body of ``GET
  /api/catalog/optimization-candidates/{id}``) for a flex 2-channel run with recorded electrode
  poses and a head-mesh identity, an ex net 2-pair run and an mEx 4-pair run. Read by
  ``desktop/tests/unit/candidate-handoff.test.ts`` ("Use in Simulator" submits exactly what the
  server resolved) and served by the mock server's candidate-detail route.
* ``overview.json`` -- ``tit.server.routes.overview.build_overview`` (the body of ``GET
  /api/catalog/overview``) for one subject of each kind the Overview page tells apart, plus the
  job list it was given. Read by ``desktop/tests/unit/overview-contract.test.ts``.

Every fixture carries the request (or the project spec) it answers. Temporary paths are
rewritten to the mock server's project root, ``/mnt/example``.

Regenerate: ``.venv/bin/python dev/make_contract_fixtures.py``; ``--check`` exits 1 when a
committed file differs from what the code produces now (``tests/test_contract_fixtures_fresh.py``
runs the same comparison in the host suite). The output is deterministic.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "desktop" / "tests" / "fixtures" / "contracts"
MOCK_ROOT = "/mnt/example"
SUBJECT = "ernie"
NET = "GSN-HydroCel-185.csv"
FLEX_RUN = "flex_Thalamus_20260810_101500"
EX_RUN = "ex_L_Insula_20260812_090000"
MEX_RUN = "mex_Thalamus_20260814_140000"
FLEX_CANDIDATE = "trial-2"

# ── synthetic inputs (authored; shapes are the writers': tit.opt.flex candidate recorder,
#    tit.opt.ex/mex final_output.csv + run_config.json) ──────────────────────────────────────

#: One flex candidate: carrier 1 at 0.7 mA, carrier 2 at 1.3 mA, rect 9x17 mm, 3 mm gel, 1 mm
#: rubber. Each electrode's pose is a rotation about z plus its centre.
_FLEX_CENTRES = [
    [11.0, 13.0, 14.0],
    [21.0, 23.0, 24.0],
    [31.0, 33.0, 34.0],
    [41.0, 43.0, 44.0],
]
_FLEX_CURRENTS_MA = (0.7, 1.3)


def _write(path: Path, text: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


def _csv(header: list[str], rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def _flex_run(pm, mesh: Path) -> None:
    run = Path(pm.flex_search_run(SUBJECT, FLEX_RUN))
    history = run / "candidate_history" / "00"
    _write(
        history / "candidate_manifest.json",
        json.dumps(
            {
                "schema_version": 1,
                "objective": "focality_tf",
                "comparability_key": "ernie-surface-gm",
                "config": {"anisotropy_type": "scalar", "aniso_maxratio": 10},
                "head_mesh_identity": {
                    "path": f"/mnt/example/derivatives/SimNIBS/sub-{SUBJECT}/m2m_{SUBJECT}/{SUBJECT}.msh",
                    "sha256": hashlib.sha256(mesh.read_bytes()).hexdigest(),
                },
                "metric_definitions": {
                    "roi_mean": "unweighted mean of target samples, V/m"
                },
                "optimizer_termination": {
                    "accepted_stage": "global",
                    "global": {
                        "success": True,
                        "message": "Maximum number of iterations reached",
                        "iterations": 33,
                        "evaluations": 3536,
                    },
                },
            }
        ),
    )
    header = [
        "candidate_id",
        "evaluation",
        "objective",
        "roi_mean",
        "roi_p99_9",
        "non_roi_mean",
        "non_roi_p95",
        "target_background_ratio",
        "current_ch1_mA",
        "current_ch2_mA",
        "geometry_file",
    ]
    rows = [
        [
            "trial-1",
            1,
            -1.15,
            0.12,
            0.21,
            0.10,
            0.17,
            1.15,
            0.7,
            1.3,
            "candidate_geometry.jsonl",
        ],
        [
            FLEX_CANDIDATE,
            9,
            -1.8,
            0.04,
            0.08,
            0.022,
            0.034,
            1.8,
            0.7,
            1.3,
            "candidate_geometry.jsonl",
        ],
    ]
    _write(history / "candidates.csv", _csv(header, rows))
    records = []
    for candidate_id, objective in (("trial-1", -1.15), (FLEX_CANDIDATE, -1.8)):
        channels = []
        for carrier, mA in enumerate(_FLEX_CURRENTS_MA):
            cells = []
            for polarity, centre in zip(
                (1, -1), _FLEX_CENTRES[2 * carrier : 2 * carrier + 2]
            ):
                x, y, z = centre
                cells.append(
                    {
                        "posmat": [
                            [0, -1, 0, x],
                            [1, 0, 0, y],
                            [0, 0, 1, z],
                            [0, 0, 0, 1],
                        ],
                        "current_A": polarity * mA / 1000,
                        "shape": "rect",
                        "dimensions": [9, 17],
                        "thickness": [3, 1],
                    }
                )
            channels.append(cells)
        records.append(
            {
                "candidate_id": candidate_id,
                "objective": objective,
                "electrodes": channels,
            }
        )
    _write(
        history / "candidate_geometry.jsonl",
        "".join(json.dumps(r) + "\n" for r in records),
    )


def _ex_run(pm, kind: str) -> None:
    getter = pm.ex_search_run if kind == "ex" else pm.m_ex_search_run
    run = Path(getter(SUBJECT, EX_RUN if kind == "ex" else MEX_RUN))
    config = {
        "subject_id": SUBJECT,
        "leadfield_hdf": f"{MOCK_ROOT}/derivatives/SimNIBS/sub-{SUBJECT}/leadfields/{SUBJECT}_leadfield_{NET[:-4]}.hdf5",
        "roi_name": "L_Insula.csv",
    }
    header = [
        "Montage",
        "Current_Ch1_mA",
        "Current_Ch2_mA",
        "TImax_ROI",
        "TImean_ROI",
        "TImean_GM",
        "Focality",
        "Composite_Index",
    ]
    if kind == "ex":
        config |= {"total_current": 2.0, "current_step": 0.5}
        rows = [
            [
                "E020_E074 <> E101_E133_I1-1.5mA_I2-0.5mA",
                1.5,
                0.5,
                0.40,
                0.25,
                0.12,
                1.6,
                0.40,
            ],
            [
                "E020_E101 <> E074_E133_I1-1.0mA_I2-1.0mA",
                1.0,
                1.0,
                0.30,
                0.20,
                0.10,
                1.5,
                0.30,
            ],
        ]
    else:
        config |= {"current_mA": 1.0}
        header = [
            "Montage",
            "TImax_ROI",
            "TImean_ROI",
            "TImean_GM",
            "Focality",
            "Composite_Index",
        ]
        rows = [
            [
                "E024_E124 <> E067_E077 <> E031_E080 <> E055_E110_I-1.0mA",
                1.30,
                0.55,
                0.50,
                1.10,
                0.605,
            ],
        ]
    _write(run / "run_config.json", json.dumps(config))
    _write(run / "final_output.csv", _csv(header, rows))


def _overview_project(pm) -> tuple[dict[str, str], list[dict]]:
    """One subject of each kind the Overview page tells apart, and the job list it is given."""
    spec = {
        "full": "raw MRI, head model with one EEG net and its leadfield, one simulation",
        "m2monly": "head model only (no raw MRI, no EEG net, no leadfield)",
        "rawonly": "raw MRI only",
        "staged": "DICOMs staged in sourcedata/, nothing converted",
        "queued": "raw MRI, and a pre-processing job queued for it",
        "lffailed": "head model with one EEG net, and its newest leadfield job failed",
    }
    cap = "Electrode,-37.6,66.4,5.3,E001\nElectrode,10.3,73.0,9.9,E002\n"
    for sid in ("full", "rawonly", "queued"):
        _write(Path(pm.bids_anat(sid)) / f"sub-{sid}_T1w.nii.gz", b"\0")
    for sid in ("full", "m2monly", "lffailed"):
        _write(Path(pm.m2m(sid)) / f"{sid}.msh", b"\0")
    for sid in ("full", "lffailed"):
        _write(Path(pm.eeg_positions(sid)) / NET, cap)
    _write(Path(pm.leadfields("full")) / f"full_leadfield_{NET[:-4]}.hdf5", b"\0")
    _write(
        Path(pm.simulation("full", "Thalamus")) / "documentation" / "config.json", "{}"
    )
    _write(Path(pm.sourcedata_subject("staged")) / "T1w" / "IM0001.dcm", b"\0")
    jobs = [
        {"id": "job-3", "kind": "pre", "state": "queued", "subject_ids": ["queued"]},
        {
            "id": "job-2",
            "kind": "leadfield",
            "state": "failed",
            "subject_ids": ["lffailed"],
        },
        {
            "id": "job-1",
            "kind": "leadfield",
            "state": "succeeded",
            "subject_ids": ["lffailed"],
        },
    ]
    return spec, jobs


def _rewrite_root(value, root: Path):
    """Replace the temporary project root by the mock's, in every string of *value*."""
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


def render(data: dict) -> str:
    """The committed text of one fixture."""
    return json.dumps(data, indent=2, sort_keys=False) + "\n"


def build() -> dict[str, str]:
    """``{file name: text}`` for every fixture, from the real code on a fresh project."""
    from tit.catalog import list_subjects
    from tit.opt.candidate_catalog import candidate_detail
    from tit.paths import get_path_manager, reset_path_manager
    from tit.server.routes.overview import build_overview

    out: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        reset_path_manager()
        pm = get_path_manager(str(root))
        mesh = Path(pm.m2m(SUBJECT)) / f"{SUBJECT}.msh"
        _write(mesh, b"synthetic head mesh bytes\n")
        _flex_run(pm, mesh)
        _ex_run(pm, "ex")
        _ex_run(pm, "mex")
        for kind, run, candidate_id in (
            ("flex", FLEX_RUN, FLEX_CANDIDATE),
            ("ex", EX_RUN, "ex-0"),
            ("mex", MEX_RUN, "ex-0"),
        ):
            response = candidate_detail(pm, SUBJECT, kind, run, candidate_id)
            request = {
                "subject": SUBJECT,
                "kind": kind,
                "run": run,
                "candidate_id": candidate_id,
            }
            out[f"candidate_detail_{kind}.json"] = render(
                {"request": request, "response": _rewrite_root(response, root)}
            )
        reset_path_manager()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        pm = get_path_manager(str(root))
        spec, jobs = _overview_project(pm)
        response = build_overview(pm, jobs).model_dump(mode="json")
        # What ``GET /api/catalog/subjects`` lists for the same project: the subject list the
        # Results page shows, which Overview's "Open in Results" lands in.
        listed = [row["id"] for row in list_subjects(pm)]
        out["overview.json"] = render(
            {
                "subjects": spec,
                "jobs": jobs,
                "catalog_subjects": listed,
                "response": _rewrite_root(response, root),
            }
        )
        reset_path_manager()
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
        "--check", action="store_true", help="exit 1 if a committed fixture is stale"
    )
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    _stub_missing_runtime_libraries()
    stale = []
    for name, text in build().items():
        path = OUT / name
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
            continue
        _write(path, text)
        print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print(f"stale (run dev/make_contract_fixtures.py): {', '.join(stale)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
