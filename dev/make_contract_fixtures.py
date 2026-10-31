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
* ``analyzer_plans.json`` -- what ``POST /api/plan/analyzer`` answers (the folder
  ``PathManager.analysis_output_dir`` names, whether it exists, whether running replaces it) for
  the analyses the mock project holds and for one config per remaining piece of the folder-name
  grammar. ``desktop/tests/mock-server/contract.test.ts`` posts every config to the mock and
  expects the same answer.
* ``job_output_dirs.json`` -- the ``output_dir`` ``GET /api/jobs/{id}`` answers (the one folder
  the desktop's folder buttons open) for a simulation, a flex search, an ex search, an analysis
  and a pre-processing stage, each with the artifacts its runner had registered when asked, and
  for the jobs that have no folder to open. Read by
  ``desktop/tests/unit/run-jobTerminal-reveal.test.tsx``.
* ``../analyses.json`` -- the mock server's analyses catalog: the real ``GET
  /api/catalog/analyses`` listing of the folders the plan route named for the held analyses, so
  the mock's plan and its catalog agree about where an analysis lives.

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
FIXTURES = ROOT / "desktop" / "tests" / "fixtures"
MOCK_ROOT = "/mnt/example"
TOKEN = "contract-fixtures"
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


def _head_model(pm, sid: str, mesh: bytes = b"\0") -> Path:
    """A finished charm head model for *sid*: the mesh and the final segmentation.

    ``tit.catalog`` shows a head model only when pre-processing's own completion rule
    (:func:`tit.pre.preflight.step_output_complete`) holds, which needs both files.
    """
    m2m = Path(pm.m2m(sid))
    _write(m2m / "final_tissues.nii.gz", b"\0")
    _write(m2m / f"{sid}.msh", mesh)
    return m2m / f"{sid}.msh"


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
        # ex carries the carrier columns a search writes now; the mEx run below is a CSV
        # written before them, so its candidates report them as null.
        header += ["HFpeak_Focality", "TI_Selectivity"]
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
                1.25,
                1.28,
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
                1.5,
                1.0,
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
        _head_model(pm, sid)
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


#: The analyses the mock project holds, as the configs that produced them: (subject, config,
#: files the run left beside ``analysis.json`` and ``results.csv``). The subjects and simulations
#: are the mock's (``simulations.json``). Ernie's Thalamus analysis is the one the Results e2e
#: specs open: two DK40 regions, as ``fixtures/analysis_summary.csv`` (its ``results.csv``) says.
HELD_ANALYSES: list[tuple[str, dict, tuple[str, ...]]] = [
    (
        "ernie",
        {
            "simulation": "Thalamus",
            "space": "mesh",
            "analysis_type": "cortical",
            "atlas": "DK40",
            "region": ["lh.bankssts", "rh.bankssts"],
            "field": "TI_max",
        },
        ("histogram.pdf", "TI_max_masked.nii.gz"),
    ),
    (
        "ernie",
        {
            "simulation": "L_Insula",
            "space": "mesh",
            "analysis_type": "cortical",
            "atlas": "a2009s",
            "region": "lh.G_insular_short",
            "field": "TI_max",
        },
        (),
    ),
    (
        "ernie",
        {
            "simulation": "docs_example",
            "space": "voxel",
            "analysis_type": "spherical",
            "center": [-38, 44, 26],
            "radius": 10,
            "coordinate_space": "mni",
            "field": "mTI_max",
        },
        (),
    ),
    (
        "101",
        {
            "simulation": "Thalamus",
            "space": "mesh",
            "analysis_type": "spherical",
            "center": [-12, -18, 6],
            "radius": 5,
            "field": "TI_max",
        },
        (),
    ),
]

#: Configs the project does not hold, each pinning one more piece of the folder-name grammar.
PLANNED_ANALYSES: list[tuple[str, list[str], dict]] = [
    (
        # Another field is another folder: ``_<field>`` after the ROI.
        "another_field",
        ["ernie"],
        {
            "simulation": "Thalamus",
            "space": "mesh",
            "analysis_type": "cortical",
            "atlas": "DK40",
            "region": "lh.insula",
            "field": "hf_peak",
        },
    ),
    (
        # Each region once, in first-seen order, then hashed: ``cortical_<n>regions_<atlas>_<md5>``.
        "repeated_regions",
        ["ernie"],
        {
            "simulation": "Thalamus",
            "space": "mesh",
            "analysis_type": "cortical",
            "atlas": "DK40",
            "region": ["rh.insula", "lh.insula", "rh.insula"],
        },
    ),
    (
        # A label a folder cannot carry is sanitised and hashed; an atlas file loses its suffix.
        "unsafe_label",
        ["ernie"],
        {
            "simulation": "Thalamus",
            "space": "voxel",
            "analysis_type": "cortical",
            "atlas": "HarvardOxford-cort-maxprob-thr25-1mm.nii.gz",
            "region": "Inferior Frontal Gyrus, pars triangularis",
        },
    ),
    (
        # ``subcortical_`` prefix; ``+`` and ``.`` in an atlas name become ``_``; voxel tissue.
        "subcortical_tissue",
        ["ernie"],
        {
            "simulation": "Thalamus",
            "space": "voxel",
            "tissue_type": "both",
            "analysis_type": "subcortical",
            "atlas": "aparc.a2009s+aseg.mgz",
            "region": "Left-Thalamus",
        },
    ),
    (
        # No region: the whole head of the atlas.
        "whole_head",
        ["ernie"],
        {
            "simulation": "Thalamus",
            "space": "mesh",
            "analysis_type": "cortical",
            "atlas": "DK40",
        },
    ),
    (
        # Python's ``:.2f`` rounds an exact binary tie to even (0.125 -> 0.12); MNI; WM tissue;
        # the Auto field (null) is the envelope and adds nothing.
        "sphere_rounding",
        ["ernie"],
        {
            "simulation": "Thalamus",
            "space": "voxel",
            "tissue_type": "WM",
            "analysis_type": "spherical",
            "center": [0.125, -1.375, 2.5],
            "radius": 7.5,
            "coordinate_space": "mni",
            "field": None,
        },
    ),
    (
        # A mesh analysis is grey-matter surface: the tissue never reaches the name.
        "mesh_ignores_tissue",
        ["ernie"],
        {
            "simulation": "Thalamus",
            "space": "mesh",
            "tissue_type": "WM",
            "analysis_type": "spherical",
            "center": [1, 2, 3],
            "radius": 5,
        },
    ),
    (
        # A single-subject run with an output folder writes exactly there.
        "explicit_output_dir",
        ["ernie"],
        {
            "simulation": "Thalamus",
            "space": "mesh",
            "analysis_type": "cortical",
            "atlas": "DK40",
            "region": "lh.insula",
            "output_dir": f"{MOCK_ROOT}/derivatives/custom/insula_run",
        },
    ),
    (
        # A NIfTI mask is named by its file and space plus a hash of both, with no atlas.
        "mask",
        ["ernie"],
        {
            "simulation": "Thalamus",
            "space": "voxel",
            "analysis_type": "mask",
            "mask_path": f"{MOCK_ROOT}/derivatives/SimNIBS/sub-ernie/m2m_ernie/masks/roi.nii.gz",
            "coordinate_space": "subject",
        },
    ),
    (
        # A group run never hands its output folder to the subjects: each analysis goes to its
        # default folder, and the folder holds the cohort summary (the job with subject "").
        "group_output_dir",
        ["ernie", "101"],
        {
            "mode": "group",
            "subject_ids": ["ernie", "101"],
            "simulation": "Thalamus",
            "space": "mesh",
            "analysis_type": "cortical",
            "atlas": "DK40",
            "region": "lh.insula",
            "output_dir": f"{MOCK_ROOT}/derivatives/ti-toolbox/group_analysis/insula_cohort",
        },
    ),
]


def _analysis_metadata(config: dict) -> dict:
    """The ``analysis.json`` ``Analyzer._save_metadata`` writes for *config* (its keys)."""
    sphere = config["analysis_type"] == "spherical"
    region = config.get("region")
    metadata = {
        "analysis_type": config["analysis_type"],
        "space": config["space"],
        "field_name": config["field"],
    }
    if config["space"] == "voxel":
        metadata["tissue_types"] = ["GM"]
    metadata.update(
        {
            "atlas": config.get("atlas"),
            "regions": [region] if isinstance(region, str) else region,
            "center": config["center"] if sphere else None,
            "radius": config["radius"] if sphere else None,
            "spheres": [[*config["center"], config["radius"]]] if sphere else None,
            "coordinate_space": config.get("coordinate_space", "subject"),
        }
    )
    return metadata


def _analyzer_fixtures(pm, root: Path) -> tuple[dict, dict]:
    """The plan table and the analyses catalog, from the real routes on one project.

    Each held analysis is written into the folder the plan route names for its config; then
    every config (held or not) is planned again, so a held one plans as existing, and the
    analyses route lists the held folders.
    """
    from unittest import mock

    from fastapi.testclient import TestClient

    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    client = TestClient(
        create_app(ServerSettings(project_dir=str(root), token=TOKEN)),
        base_url="http://127.0.0.1:8765",
    )
    headers = {"Authorization": f"Bearer {TOKEN}"}

    def plan(subject_ids: list[str], config: dict) -> dict:
        config = dict(config)
        if config.get("output_dir"):
            # An output folder must be inside the project the route serves.
            config["output_dir"] = config["output_dir"].replace(MOCK_ROOT, str(root))
        body = {"config": config, "subject_ids": subject_ids}
        # The mask case names the mock's own file (its path is part of the folder's hash), which
        # does not exist here; the route's "is it readable" check is the one step skipped.
        with mock.patch("tit.analyzer.masks.validate_mask_path"):
            response = client.post("/api/plan/analyzer", json=body, headers=headers)
        if response.status_code != 200:
            raise RuntimeError(f"{config}: HTTP {response.status_code} {response.text}")
        return response.json()

    def single(sid: str, cfg: dict) -> dict:
        return {"subject_id": sid, **cfg}

    cases = [
        (f"held_{sid}_{cfg['simulation']}", [sid], single(sid, cfg), True)
        for sid, cfg, _files in HELD_ANALYSES
    ] + [
        (
            case_id,
            ids,
            cfg if cfg.get("mode") == "group" else single(ids[0], cfg),
            False,
        )
        for case_id, ids, cfg in PLANNED_ANALYSES
    ]
    for sid, cfg, files in HELD_ANALYSES:
        _head_model(pm, sid)
        (job,) = plan([sid], single(sid, cfg))["jobs"]
        folder = Path(job["output_dir"])
        _write(folder / "analysis.json", json.dumps(_analysis_metadata(cfg), indent=2))
        _write(folder / "results.csv", "Metric,Value\n")
        for name in files:
            _write(folder / name, b"\0")

    table = []
    for case_id, subject_ids, config, held in cases:
        answer = plan(subject_ids, config)
        table.append(
            {
                "id": case_id,
                "subject_ids": subject_ids,
                "held": held,
                "config": config,
                "jobs": [
                    {
                        key: job[key]
                        for key in ("subject", "output_dir", "exists", "will_overwrite")
                    }
                    for job in answer["jobs"]
                ],
            }
        )

    catalog: dict[str, dict[str, list]] = {}
    for sid, cfg, _files in HELD_ANALYSES:
        sim = cfg["simulation"]
        response = client.get(
            "/api/catalog/analyses",
            params={"subject": sid, "simulation": sim},
            headers=headers,
        )
        if response.status_code != 200:
            raise RuntimeError(f"{sid}/{sim}: HTTP {response.status_code}")
        catalog.setdefault(sid, {})[sim] = response.json()
    plans = {
        "generated_by": "dev/make_contract_fixtures.py",
        "catalog": "desktop/tests/fixtures/analyses.json lists the held cases",
        "cases": table,
    }
    return _rewrite_root(plans, root), _rewrite_root(catalog, root)


def _job_output_fixture(pm, root: Path) -> dict:
    """``output_dir`` from the real ``GET /api/jobs/{id}``, for each kind of job.

    Each job is submitted to a real :class:`~tit.jobs.manager.JobManager` that is never started
    (so it stays queued, as a job that has reported nothing yet) and given the artifact events
    its runner emits (``tit/sim/__main__.py`` registers ``Simulations/<montage>`` as a ``dir``
    and then the mesh; ``tit/opt/ex/__main__.py`` registers the two files of its run folder).
    The run folders are created first where the runner would already have created them.
    """
    from fastapi.testclient import TestClient

    from tit.config_io import serialize_config
    from tit.jobs import bootstrap
    from tit.jobs.manager import JobManager
    from tit.jobs.plans import plan_preprocessing
    from tit.jobs.spec import Cost
    from tit.opt.config import FlexConfig
    from tit.pre.config import PreprocessConfig
    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    manager = JobManager(
        str(root), runner_cwd=str(root), budget=Cost(cpus=8, mem_gb=64)
    )
    bootstrap.set_manager_for_testing(manager)
    client = TestClient(
        create_app(ServerSettings(project_dir=str(root), token=TOKEN)),
        base_url="http://127.0.0.1:8765",
    )
    headers = {"Authorization": f"Bearer {TOKEN}"}
    cases = []

    def case(case_id: str, kind: str, config: dict, subject_ids: list, artifacts=()):
        job_id = manager.submit(kind, config, subject_ids)["id"]
        with manager._lock:
            manager._apply_events(
                job_id,
                manager._status[job_id],
                [{"type": "artifact", **a} for a in artifacts],
            )
        response = client.get(f"/api/jobs/{job_id}", headers=headers)
        if response.status_code != 200:
            raise RuntimeError(
                f"{case_id}: HTTP {response.status_code} {response.text}"
            )
        detail = response.json()
        cases.append(
            {
                "id": case_id,
                "kind": kind,
                "subject_ids": subject_ids,
                "artifacts": detail["artifacts"],
                "output_dir": detail["output_dir"],
            }
        )

    def sim_config(*names: str) -> dict:
        montages = [
            {
                "_type": "Montage",
                "name": name,
                "mode": "net",
                "electrode_pairs": [["E020", "E074"], ["E101", "E133"]],
                "eeg_net": NET,
            }
            for name in names
        ]
        return {
            "subject_id": SUBJECT,
            "montages": montages,
            "output_fields": ["TI_max"],
        }

    def flex_config(**overrides) -> dict:
        return serialize_config(
            FlexConfig(
                subject_id=SUBJECT,
                goal="mean",
                postproc="max_TI",
                current_mA=1.0,
                electrode=FlexConfig.ElectrodeConfig(),
                roi=FlexConfig.SphericalROI(x=-38.0, y=44.0, z=26.0, radius=10.0),
                **overrides,
            )
        )

    ex_config = {
        "subject_id": SUBJECT,
        "leadfield_hdf": f"{SUBJECT}_leadfield_{NET[:-4]}.hdf5",
        "roi_name": "L_Insula.csv",
        "electrodes": {
            "_type": "PoolElectrodes",
            "electrodes": ["E020", "E074", "E101", "E133"],
        },
        "total_current": 2.0,
        "current_step": 1.0,
    }

    try:
        # Simulation: the montage's folder is created when the run starts, and registered as a
        # ``dir`` when it ends.
        case("sim_queued_folder_not_created", "sim", sim_config("Thalamus"), [SUBJECT])
        sim = Path(pm.simulation(SUBJECT, "L_Insula"))
        sim.mkdir(parents=True)
        case("sim_running", "sim", sim_config("L_Insula"), [SUBJECT])
        mesh = Path(pm.ti_mesh(SUBJECT, "L_Insula"))
        _write(mesh, b"\0")
        case(
            "sim_finished",
            "sim",
            sim_config("L_Insula"),
            [SUBJECT],
            [
                {"path": str(sim), "kind": "dir", "label": "L_Insula"},
                {"path": str(mesh), "kind": "mesh", "label": "L_Insula"},
            ],
        )
        Path(pm.simulation(SUBJECT, "R_Insula")).mkdir(parents=True)
        case(
            "sim_two_montages",
            "sim",
            sim_config("L_Insula", "R_Insula"),
            [SUBJECT],
        )

        # Flex search: the Optimizer page always names the run folder.
        flex_run = Path(pm.flex_search_run(SUBJECT, FLEX_RUN))
        flex_run.mkdir(parents=True)
        case(
            "flex_running", "flex", flex_config(output_folder=str(flex_run)), [SUBJECT]
        )
        case(
            "flex_finished",
            "flex",
            flex_config(output_folder=str(flex_run)),
            [SUBJECT],
            [{"path": str(flex_run), "kind": "dir", "label": "output_folder"}],
        )

        # Ex search with no run name: the runner stamps one, known only from its results.
        _ex_run(pm, "ex")
        ex_run = Path(pm.ex_search_run(SUBJECT, EX_RUN))
        case("ex_running_unnamed", "ex", ex_config, [SUBJECT])
        case(
            "ex_finished",
            "ex",
            ex_config,
            [SUBJECT],
            [
                {
                    "path": str(ex_run / "final_output.csv"),
                    "kind": "csv",
                    "label": "results",
                },
                {
                    "path": str(ex_run / "run_config.json"),
                    "kind": "json",
                    "label": "config",
                },
            ],
        )

        # Analysis: the plan route's folder, whichever file the runner registered first.
        analysis = {
            "subject_id": SUBJECT,
            "simulation": "L_Insula",
            "space": "mesh",
            "analysis_type": "spherical",
            "center": [-38.0, 44.0, 26.0],
            "radius": 10.0,
        }
        planned = client.post(
            "/api/plan/analyzer",
            json={"config": analysis, "subject_ids": [SUBJECT]},
            headers=headers,
        ).json()["jobs"]
        folder = Path(planned[0]["output_dir"])
        _write(folder / "results.csv", "Metric,Value\n")
        _write(folder / "figures" / "histogram.pdf", b"\0")
        case(
            "analyzer_finished",
            "analyzer",
            analysis,
            [SUBJECT],
            [
                {"path": str(folder / "figures" / "histogram.pdf"), "kind": "pdf"},
                {"path": str(folder / "results.csv"), "kind": "csv"},
            ],
        )

        # Pre-processing: one job per stage per subject; charm's folder is m2m_<id>.
        (charm,) = plan_preprocessing(
            PreprocessConfig(subject_ids=[SUBJECT], create_m2m=True), [SUBJECT]
        )
        _head_model(pm, SUBJECT)
        case("pre_charm", charm.kind, charm.config, charm.subject_ids)
    finally:
        bootstrap.reset_manager()
    return {
        "generated_by": "dev/make_contract_fixtures.py",
        "note": "output_dir is GET /api/jobs/{id}'s answer for a job of this kind, holding "
        "exactly these artifacts",
        "cases": cases,
    }


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
    """``{path under desktop/tests/fixtures: text}`` for every fixture, from the real code."""
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
        mesh = _head_model(pm, SUBJECT, b"synthetic head mesh bytes\n")
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
            out[f"contracts/candidate_detail_{kind}.json"] = render(
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
        out["contracts/overview.json"] = render(
            {
                "subjects": spec,
                "jobs": jobs,
                "catalog_subjects": listed,
                "response": _rewrite_root(response, root),
            }
        )
        reset_path_manager()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        pm = get_path_manager(str(root))
        plans, analyses = _analyzer_fixtures(pm, root)
        out["contracts/analyzer_plans.json"] = render(plans)
        out["analyses.json"] = render(analyses)
        reset_path_manager()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "project"
        root.mkdir()
        (root / "dataset_description.json").write_text("{}")
        pm = get_path_manager(str(root))
        out["contracts/job_output_dirs.json"] = render(
            _rewrite_root(_job_output_fixture(pm, root), root)
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
        path = FIXTURES / name
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
