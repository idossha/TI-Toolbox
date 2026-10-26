"""``POST /api/plan/{kind}`` names the directory each runner then writes, for every kind.

What this pins (2026-10-22)
    The plan's ``output_dir`` is what the overwrite guard (409 "outputs exist") checks and what
    the run pages show; if it is not where the runner writes, a re-run silently replaces an
    analysis the guard never saw. Before this:

    - a mesh cortical analysis of a bare name (``"insula"``) was planned as
      ``cortical_insula_DK40`` and written to ``cortical_2regions_DK40_<md5>`` (the runner named
      the folder after the lh+rh atlas keys it resolved); a repeated name was planned twice and
      written once;
    - a group analysis was planned as its per-subject folders only (with ``output_dir`` set,
      that one folder once per subject), never naming the group folder the runner writes its
      summary into, while the per-subject analyses went to their own default folders;
    - a sub-cortical label with ``(`` or ``,`` (FreeSurfer thalamic nuclei ``Left-MV(Re)``,
      Harvard-Oxford ``...Gyrus,-pars-triangularis``) named a folder the Results page could not
      open (``/summary`` refuses a name outside the entity-name alphabet);
    - an fsaverage projection that already existed was planned as "will overwrite" although the
      runner, without ``overwrite``, keeps it (the Replace answer then replaced nothing).

Where the expectations come from
    The oracle is each runner's own resolution: its ``main()`` runs on the config the plan was
    asked about, with the science replaced by fakes that return small hand-made arrays, and the
    directory is read back from where ``results.csv`` (or the runner's own first file) landed on
    disk. Nothing is restated from a naming formula. Catalog listing and ``/summary`` are read
    through the real routes; ``roi_mean`` is compared with the ``results.csv`` the runner wrote.

Run: .venv/bin/python -m pytest tests/test_plan_vs_runner_output_dir.py -q -p no:cacheprovider
Deliberately elsewhere: flex/ex/mEx (their own packages), blender (p22's runners),
``tests/numerical/test_stats_runner_real_path.py`` (stats on real NIfTIs in the container).
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import time
import types
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.analyzer.analyzer import Analyzer  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token-plan-runner"
BASE = "http://127.0.0.1:8765"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
SIM = "M1"
SUBJECTS = ("001", "002")
SHAPE = (4, 4, 4)
#: 20 mm voxels from -40 mm: voxel centres at -40, -20, 0, 20 mm on each axis, so every
#: sphere below holds at least one voxel.
AFFINE = np.diag([20.0, 20.0, 20.0, 1.0])
AFFINE[:3, 3] = -40.0
#: Six surface nodes: three left (lh first, as SimNIBS joins the central surface), three right.
N_LH = N_RH = 3
NODES = np.array(
    [[-30, 0, 0], [-30, 5, 0], [-30, 0, 5], [30, 0, 0], [30, 5, 0], [30, 0, 5]], float
)
#: Hand-written per-file voxel values, distinct so a mixed-up file shows in roi_mean.
VOXEL_FILES = {
    "grey_M1_TI_subject_TI_max.nii.gz": 1.0,
    "white_M1_TI_subject_TI_max.nii.gz": 2.0,
    "M1_TI_subject_TI_max.nii.gz": 3.0,
    "grey_M1_TI_subject_hf_peak.nii.gz": 4.0,
}
ATLAS = "atlas_labels.nii.gz"
MASK = "roi_mask.nii.gz"


class _Img:
    """What the analyzer reads off a nibabel image."""

    def __init__(self, data: np.ndarray) -> None:
        self._data = data
        self.affine = AFFINE.copy()
        self.header = None
        self.shape = data.shape

    @property
    def dataobj(self):
        return self._data

    def get_fdata(self, dtype=None):
        return self._data.astype(float)


def _fake_load(path) -> _Img:
    name = os.path.basename(str(path))
    if name in VOXEL_FILES:
        return _Img(np.full(SHAPE, VOXEL_FILES[name]))
    return _Img(np.ones(SHAPE))  # atlases, masks: every voxel is in the ROI


def _atlas2subject(m2m, atlas, split_labels=True):
    lh = {"insula": np.array([1, 1, 0], bool), "precentral": np.array([0, 0, 1], bool)}
    rh = {"insula": np.array([1, 0, 0], bool), "precentral": np.array([0, 1, 1], bool)}
    for i in range(10):  # a 12-region list draws from these
        lh[f"r{i}"] = np.array([1, 0, 1], bool)
    return {"lh": lh, "rh": rh}


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "dataset_description.json").write_text("{}")
    pm = get_path_manager(str(root))
    for sid in SUBJECTS:
        m2m = Path(pm.m2m(sid))
        m2m.mkdir(parents=True)
        (m2m / f"{sid}.msh").write_bytes(b"")
        sim = Path(pm.simulation(sid, SIM))
        (sim / "TI" / "mesh").mkdir(parents=True)
        (sim / "TI" / "mesh" / f"{SIM}_TI.msh").write_bytes(b"")
        (sim / "TI" / "niftis").mkdir(parents=True)
        for name in VOXEL_FILES:
            (sim / "TI" / "niftis" / name).write_bytes(b"")
    (root / ATLAS).write_bytes(b"")
    (root / MASK).write_bytes(b"")
    return root


@pytest.fixture()
def fake_science(monkeypatch, project: Path):
    """Replace every library read with small hand-made arrays; keep every naming decision."""
    import tit.atlas.islands as islands
    import tit.opt.masks as opt_masks

    nib = sys.modules["nibabel"]
    monkeypatch.setattr(nib, "load", _fake_load)
    monkeypatch.setattr(
        nib.affines,
        "apply_affine",
        lambda aff, pts: np.asarray(pts) @ np.asarray(aff)[:3, :3].T
        + np.asarray(aff)[:3, 3],
    )
    processing = types.ModuleType("nibabel.processing")
    processing.resample_from_to = lambda img, target, **_: _Img(np.ones(target[0]))
    monkeypatch.setitem(sys.modules, "nibabel.processing", processing)
    monkeypatch.setattr(
        sys.modules["scipy.ndimage"],
        "map_coordinates",
        lambda arr, coords, **_: np.ones(np.asarray(coords).shape[1]),
    )
    monkeypatch.setattr(
        sys.modules["simnibs.utils.transformations"], "atlas2subject", _atlas2subject
    )
    surface = types.SimpleNamespace(nodes=types.SimpleNamespace(node_coord=NODES))
    monkeypatch.setattr(Analyzer, "_load_surface_mesh", lambda self: surface)
    monkeypatch.setattr(Analyzer, "_field_values", lambda self, s: np.arange(1.0, 7.0))
    monkeypatch.setattr(
        Analyzer, "_node_areas", staticmethod(lambda s: np.ones(len(NODES)))
    )
    monkeypatch.setattr(
        Analyzer, "_maybe_transform_coords", lambda self, c, cs: np.asarray(c, float)
    )
    monkeypatch.setattr(
        Analyzer, "_resolve_voxel_atlas", lambda self, atlas: project / ATLAS
    )
    monkeypatch.setattr(
        Analyzer, "_resolve_mni_atlas", staticmethod(lambda atlas: project / ATLAS)
    )
    monkeypatch.setattr(Analyzer, "_find_voxel_region_id", lambda self, path, name: 1)
    monkeypatch.setattr(
        islands, "keep_main_components", lambda m, what=None: (m, None, None)
    )
    monkeypatch.setattr(opt_masks, "prepare_mask", lambda path, *a, **k: path)
    monkeypatch.setenv("TIT_NO_ROI_PLATE", "1")
    monkeypatch.delenv("TIT_JOB_ID", raising=False)


@pytest.fixture()
def client(project: Path) -> TestClient:
    return TestClient(
        create_app(ServerSettings(project_dir=str(project), token=TOKEN)),
        base_url=BASE,
    )


def _files(root: Path, name: str) -> set[Path]:
    return {p.resolve() for p in root.rglob(name)}


def _run(module, config: dict, project: Path, tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / f"{module.__name__}.json"
    path.write_text(json.dumps({**config, "project_dir": str(project)}))
    monkeypatch.setattr(sys, "argv", [module.__name__, str(path)])
    try:
        module.main()
    except SystemExit as exc:
        assert exc.code in (0, None), f"{module.__name__} exited {exc.code}"


def _plan(client: TestClient, kind: str, config: dict, subjects=None) -> dict:
    body = {"config": config}
    if subjects is not None:
        body["subject_ids"] = subjects
    resp = client.post(f"/api/plan/{kind}", json=body, headers=BEARER)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _real(path: str | Path) -> Path:
    return Path(os.path.realpath(path))


# ---------------------------------------------------------------------------------------------
# analyzer, single subject
# ---------------------------------------------------------------------------------------------

_SPHERE = {"analysis_type": "spherical", "center": [-35, 5, 5], "radius": 10}

SINGLE_CASES = {
    "sphere-mesh-int-radius": {**_SPHERE, "space": "mesh"},
    "sphere-mesh-float-radius-mni": {
        **_SPHERE,
        "space": "mesh",
        "radius": 7.5,
        "coordinate_space": "mni",
    },
    "sphere-voxel-negative-zero": {
        "analysis_type": "spherical",
        "space": "voxel",
        "center": [-0.001, 0.0, 1.0],
        "radius": 1.5,
    },
    "sphere-voxel-wm": {**_SPHERE, "space": "voxel", "tissue_type": "WM"},
    "sphere-voxel-both": {**_SPHERE, "space": "voxel", "tissue_type": "both"},
    "sphere-voxel-hf-peak": {**_SPHERE, "space": "voxel", "field": "hf_peak"},
    "sphere-mesh-hf-peak": {**_SPHERE, "space": "mesh", "field": "hf_peak"},
    "sphere-mesh-explicit-envelope": {**_SPHERE, "space": "mesh", "field": "TI_max"},
    "cortical-mesh-bare-name": {
        "analysis_type": "cortical",
        "space": "mesh",
        "atlas": "DK40",
        "region": "insula",
    },
    "cortical-mesh-repeated-name": {
        "analysis_type": "cortical",
        "space": "mesh",
        "atlas": "DK40",
        "region": ["lh.insula", "lh.insula", "rh.precentral"],
    },
    "cortical-mesh-single": {
        "analysis_type": "cortical",
        "space": "mesh",
        "atlas": "DK40",
        "region": "lh.insula",
    },
    "cortical-mesh-12-regions": {
        "analysis_type": "cortical",
        "space": "mesh",
        "atlas": "DK40",
        "region": ["lh.insula", "rh.insula"] + [f"lh.r{i}" for i in range(10)],
    },
    "cortical-voxel-list": {
        "analysis_type": "cortical",
        "space": "voxel",
        "atlas": "DK40",
        "region": ["Left-Insula", "Right-Insula"],
    },
    "cortical-voxel-repeated-name": {
        "analysis_type": "cortical",
        "space": "voxel",
        "atlas": "DK40",
        "region": ["Left-Insula", "Left-Insula", "Right-Insula"],
    },
    "subcortical-voxel-repeated-label": {
        "analysis_type": "subcortical",
        "space": "voxel",
        "atlas": "labeling.nii.gz",
        "region": ["Left-Thalamus", "Left-Thalamus"],
    },
    "subcortical-voxel-parenthesis": {
        "analysis_type": "subcortical",
        "space": "voxel",
        "atlas": "ThalamicNuclei.v13.T1.mgz",
        "region": "Left-MV(Re)",
    },
    "subcortical-voxel-comma": {
        "analysis_type": "subcortical",
        "space": "voxel",
        "atlas": "HarvardOxford-cort-maxprob-thr25-1mm.nii.gz",
        "coordinate_space": "mni",
        "region": "Left-Inferior-Frontal-Gyrus,-pars-triangularis",
    },
    "subcortical-mesh-two": {
        "analysis_type": "subcortical",
        "space": "mesh",
        "atlas": "labeling.nii.gz",
        "region": ["Left-Thalamus", "Right-Thalamus"],
    },
}


def _mask_cases(project: Path) -> dict:
    mask = str(project / MASK)
    return {
        "mask-voxel-subject": {
            "analysis_type": "mask",
            "space": "voxel",
            "mask_path": mask,
        },
        "mask-mesh-mni": {
            "analysis_type": "mask",
            "space": "mesh",
            "mask_path": mask,
            "coordinate_space": "mni",
        },
    }


def _single_config(case: dict) -> dict:
    return {
        "mode": "single",
        "subject_id": "001",
        "simulation": SIM,
        "visualize": False,
        **case,
    }


def _assert_listed_with_summary(client: TestClient, written: Path) -> None:
    """The catalog lists the folder and its summary is the CSV the runner wrote."""
    listed = client.get(
        "/api/catalog/analyses",
        params={"subject": "001", "simulation": SIM},
        headers=BEARER,
    )
    assert listed.status_code == 200, listed.text
    entry = next(
        (e for e in listed.json() if _real(e["csv"]) == written / "results.csv"), None
    )
    assert entry is not None, f"{written} is not listed: {listed.json()}"
    summary = client.get(
        f"/api/catalog/analyses/{entry['name']}/summary",
        params={"subject": "001", "simulation": SIM},
        headers=BEARER,
    )
    assert summary.status_code == 200, summary.text
    with open(written / "results.csv", newline="") as fh:
        rows = {row["Metric"]: row["Value"] for row in csv.DictReader(fh)}
    assert str(rows["roi_mean"]) in json.dumps(summary.json())


@pytest.mark.parametrize("case", [*SINGLE_CASES, "mask-voxel-subject", "mask-mesh-mni"])
def test_analyzer_single_writes_where_the_plan_says(
    case, client, project, fake_science, tmp_path, monkeypatch
) -> None:
    from tit.analyzer import __main__ as runner

    spec = {**SINGLE_CASES, **_mask_cases(project)}[case]
    config = _single_config(spec)
    planned = _plan(client, "analyzer", config)["jobs"]
    before = _files(project, "results.csv")
    _run(runner, config, project, tmp_path, monkeypatch)
    written = _files(project, "results.csv") - before
    assert len(written) == 1, written
    folder = next(iter(written)).parent
    assert [(j["subject"], _real(j["output_dir"])) for j in planned] == [
        ("001", folder)
    ]
    _assert_listed_with_summary(client, folder)
    # A re-plan now sees that folder as the existing output the guard asks about.
    again = _plan(client, "analyzer", config)["jobs"][0]
    assert again["exists"] is True and again["will_overwrite"] is True


def test_bare_mesh_name_folder_differs_from_its_hemisphere_spelling(
    client, project, fake_science
) -> None:
    """The bare name is the request's own identity; it is still analysed as both hemispheres."""
    bare = _plan(
        client, "analyzer", _single_config(SINGLE_CASES["cortical-mesh-bare-name"])
    )
    left = _plan(
        client, "analyzer", _single_config(SINGLE_CASES["cortical-mesh-single"])
    )
    assert bare["jobs"][0]["output_dir"] != left["jobs"][0]["output_dir"]


def test_bare_mesh_name_is_analysed_over_both_hemispheres(
    project, fake_science
) -> None:
    result = Analyzer("001", SIM, space="mesh").analyze_cortex("DK40", "insula")
    # lh.insula = nodes 0,1 and rh.insula = node 3 (_atlas2subject); field = 1..6, unit areas.
    assert result.region_name == "lh.insula+rh.insula"
    assert result.roi_mean == pytest.approx((1 + 2 + 4) / 3)


def test_region_key_names_each_requested_region_once_in_order() -> None:
    from tit.analyzer.masks import analysis_region_key

    assert analysis_region_key(["b", "a", "b", "a"]) == "b+a"
    assert analysis_region_key(["a", "a"]) == analysis_region_key("a") == "a"
    assert analysis_region_key(None) == analysis_region_key([]) == ""


@pytest.mark.parametrize(
    "spec, unique",
    [
        (
            SINGLE_CASES["cortical-mesh-repeated-name"],
            ["lh.insula", "rh.precentral"],
        ),
        (
            SINGLE_CASES["cortical-voxel-repeated-name"],
            ["Left-Insula", "Right-Insula"],
        ),
        (SINGLE_CASES["subcortical-voxel-repeated-label"], "Left-Thalamus"),
    ],
    ids=["cortical-mesh", "cortical-voxel", "subcortical-voxel"],
)
def test_a_repeated_region_is_the_analysis_of_it_named_once(
    spec, unique, client, project, fake_science, tmp_path, monkeypatch
) -> None:
    """Asking for a region twice is the same ROI (a union), so the same folder."""
    from tit.analyzer import __main__ as runner

    repeated = _single_config(spec)
    once = _single_config({**spec, "region": unique})
    planned = _plan(client, "analyzer", repeated)["jobs"][0]["output_dir"]
    assert planned == _plan(client, "analyzer", once)["jobs"][0]["output_dir"]
    before = _files(project, "results.csv")
    _run(runner, once, project, tmp_path, monkeypatch)
    assert {p.parent for p in _files(project, "results.csv") - before} == {
        _real(planned)
    }


def test_explicit_output_dir_single_is_used_verbatim(
    client, project, fake_science, tmp_path, monkeypatch
) -> None:
    from tit.analyzer import __main__ as runner

    custom = project / "derivatives" / "custom" / "run1"
    config = _single_config({**_SPHERE, "space": "voxel", "output_dir": str(custom)})
    planned = _plan(client, "analyzer", config)["jobs"]
    _run(runner, config, project, tmp_path, monkeypatch)
    assert (custom / "results.csv").is_file()
    assert [_real(j["output_dir"]) for j in planned] == [_real(custom)]


# ---------------------------------------------------------------------------------------------
# analyzer, group mode
# ---------------------------------------------------------------------------------------------


def _group_run(config, project, tmp_path, monkeypatch):
    """Run the group runner; return (per-subject result folders, the group folder)."""
    import tit.analyzer as analyzer_pkg
    from tit.analyzer import __main__ as runner
    from tit.analyzer import group

    # matplotlib is mocked on the host: the plot is not what is being checked.
    monkeypatch.setattr(
        group, "_generate_comparison_plot", lambda df, out: out / "group_comparison.pdf"
    )
    real = analyzer_pkg.run_group_analysis
    results = []

    def recording(*args, **kwargs):
        result = real(*args, **kwargs)
        results.append(result)
        return result

    monkeypatch.setattr(analyzer_pkg, "run_group_analysis", recording)
    before = _files(project, "results.csv")
    _run(runner, config, project, tmp_path, monkeypatch)
    written = _files(project, "results.csv") - before
    assert len(results) == 1
    return {p.parent for p in written}, _real(results[0].summary_csv_path.parent)


@pytest.mark.parametrize(
    "spec, variant",
    [
        ({**_SPHERE, "space": "voxel", "tissue_type": "WM"}, "_WM"),
        (
            {
                "analysis_type": "cortical",
                "space": "mesh",
                "atlas": "DK40",
                "region": "insula",
                "field": "hf_peak",
            },
            "_hf_peak",
        ),
    ],
    ids=["sphere-voxel-wm", "cortical-mesh-bare-hf-peak"],
)
def test_analyzer_group_plans_each_subject_and_the_group_folder(
    spec, variant, client, project, fake_science, tmp_path, monkeypatch
) -> None:
    # One clock for the plan and the run: the group folder is named by the second it starts.
    stamp = "20261022_010203"
    monkeypatch.setattr(time, "strftime", lambda fmt, *a: stamp)
    config = {
        "mode": "group",
        "subject_ids": list(SUBJECTS),
        "simulation": SIM,
        "visualize": False,
        **spec,
    }
    planned = _plan(client, "analyzer", config)["jobs"]
    subject_dirs, group_dir = _group_run(config, project, tmp_path, monkeypatch)

    by_subject = {}
    for job in planned:
        by_subject.setdefault(job["subject"], []).append(_real(job["output_dir"]))
    assert {s: d for s, d in by_subject.items() if s} == {
        sid: [d] for sid, d in zip(SUBJECTS, sorted(subject_dirs))
    }
    assert {d.parents[4].name for d in subject_dirs} == {f"sub-{s}" for s in SUBJECTS}
    assert by_subject[""] == [group_dir]
    assert group_dir.parent.name == "group_analysis"
    # The group folder carries the field/tissue the way each subject's folder does, so a
    # TI_max/GM group run of the same ROI started in the same second is another folder.
    assert group_dir.name.startswith(f"{SIM}_{spec['space']}_")
    assert group_dir.name.endswith(f"{variant}_{stamp}")
    assert all(d.name.endswith(variant) for d in subject_dirs)


def test_group_runs_of_one_roi_for_two_fields_keep_two_group_folders(
    client, project, fake_science, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(time, "strftime", lambda fmt, *a: "20261022_010203")
    base = {
        "mode": "group",
        "subject_ids": list(SUBJECTS),
        "simulation": SIM,
        "visualize": False,
        **_SPHERE,
        "space": "voxel",
    }
    folders = []
    for config in (base, {**base, "field": "hf_peak"}):
        planned = _plan(client, "analyzer", config)["jobs"]
        _, group_dir = _group_run(config, project, tmp_path, monkeypatch)
        group_job = next(j for j in planned if not j["subject"])
        # The hf_peak run is not planned as replacing the TI_max run's summary.
        assert (_real(group_job["output_dir"]), group_job["exists"]) == (
            group_dir,
            False,
        )
        folders.append(group_dir)
    assert folders[0] != folders[1]


def test_analyzer_group_with_output_dir_plans_it_once_for_the_group(
    client, project, fake_science, tmp_path, monkeypatch
) -> None:
    group_out = project / "derivatives" / "ti-toolbox" / "group_analysis" / "mine"
    config = {
        "mode": "group",
        "subject_ids": list(SUBJECTS),
        "simulation": SIM,
        "visualize": False,
        "output_dir": str(group_out),
        **_SPHERE,
        "space": "mesh",
    }
    planned = _plan(client, "analyzer", config)["jobs"]
    # Nothing is on disk yet: no job is an existing output the guard would ask about.
    assert [(j["exists"], j["will_overwrite"]) for j in planned] == [(False, False)] * 3
    subject_dirs, group_dir = _group_run(config, project, tmp_path, monkeypatch)
    assert group_dir == _real(group_out)
    assert sorted(_real(j["output_dir"]) for j in planned if j["subject"]) == sorted(
        subject_dirs
    )
    assert [_real(j["output_dir"]) for j in planned if not j["subject"]] == [
        _real(group_out)
    ]
    assert _real(group_out) not in subject_dirs

    # A second run would replace the summary the first one wrote into output_dir, and each
    # subject's analysis: the re-plan says so for every folder, the group one included.
    again = {j["subject"]: j for j in _plan(client, "analyzer", config)["jobs"]}
    assert sorted(again) == ["", *SUBJECTS]
    assert {s: (j["exists"], j["will_overwrite"]) for s, j in again.items()} == {
        s: (True, True) for s in again
    }


def test_existing_group_output_dir_is_409_until_overwrite_is_confirmed(
    client, project, fake_science, tmp_path, monkeypatch
) -> None:
    """The submit guard refuses to replace the group summary folder without confirmation."""
    from fastapi import HTTPException

    from tit.server.overwrite_policy import check_overwrite_permission

    group_out = project / "derivatives" / "ti-toolbox" / "group_analysis" / "mine"
    config = {
        "mode": "group",
        "subject_ids": list(SUBJECTS),
        "simulation": SIM,
        "visualize": False,
        "output_dir": str(group_out),
        **_SPHERE,
        "space": "mesh",
    }
    check_overwrite_permission("analyzer", config, [])  # a first run is not refused
    subject_dirs, _ = _group_run(config, project, tmp_path, monkeypatch)
    # Only the group folder is left on disk, so the refusal can come from nothing else.
    for folder in subject_dirs:
        shutil.rmtree(folder)
    assert group_out.is_dir()

    with pytest.raises(HTTPException) as refused:
        check_overwrite_permission("analyzer", config, [])
    assert refused.value.status_code == 409
    assert refused.value.detail.endswith(": " + str(group_out))
    check_overwrite_permission("analyzer", config, [], overwrite=True)


# ---------------------------------------------------------------------------------------------
# stats, nifti_average, nilearn
# ---------------------------------------------------------------------------------------------


class _Stop(Exception):
    """The runner resolved its folder; nothing after that matters here."""


@pytest.mark.parametrize(
    "extra",
    [
        {"_type": "GroupComparisonConfig"},
        {"_type": "CorrelationConfig"},
        {"_type": "CorrelationConfig", "space": "fsaverage"},
        {"mode": "correlation"},
    ],
    ids=["group", "correlation", "correlation-fsaverage", "legacy-mode"],
)
def test_stats_writes_where_the_plan_says(
    extra, client, project, tmp_path, monkeypatch
) -> None:
    from tit.stats import __main__ as runner
    from tit.stats import permutation

    seen: list[str] = []

    def stop(output_dir, *a, **k):
        seen.append(output_dir)
        raise _Stop

    monkeypatch.setattr(permutation, "_setup_logger", stop)
    monkeypatch.setattr(runner, "_hold_locks", lambda *a: nullcontext())
    rows = [
        {
            "subject_id": f"00{i}",
            "simulation_name": SIM,
            "response": i % 2,
            "effect_size": 0.1 * i,
        }
        for i in range(1, 5)
    ]
    config = {"analysis_name": "cohort", "subjects": rows, "n_permutations": 100}
    config.update(extra)
    planned = _plan(client, "stats", config)["jobs"]
    with pytest.raises(_Stop):
        _run(runner, config, project, tmp_path, monkeypatch)
    assert [_real(j["output_dir"]) for j in planned] == [_real(seen[0])]
    assert Path(seen[0]).is_dir()


def test_nifti_average_writes_where_the_plan_says(
    client, project, tmp_path, monkeypatch
) -> None:
    from tit.stats import nifti_average as runner

    monkeypatch.setattr(
        runner,
        "load_grouped_subjects_ti_toolbox",
        lambda configs, **_: (
            {"A": np.ones((2, 2, 2, 1)), "B": np.zeros((2, 2, 2, 1))},
            _Img(np.ones((2, 2, 2))),
            {"A": ["001"], "B": ["002"]},
        ),
    )
    monkeypatch.setattr(runner, "_hold_locks", lambda *a: nullcontext())
    config = {
        "output_name": "avg1",
        "subjects": [
            {"subject_id": "001", "simulation_name": SIM, "group": "A"},
            {"subject_id": "002", "simulation_name": SIM, "group": "B"},
        ],
    }
    planned = _plan(client, "nifti_average", config)["jobs"]
    before = _files(project, "config.json")
    _run(runner, config, project, tmp_path, monkeypatch)
    written = _files(project, "config.json") - before
    assert [_real(j["output_dir"]) for j in planned] == [next(iter(written)).parent]


def test_nilearn_writes_where_the_plan_says(
    client, project, tmp_path, monkeypatch
) -> None:
    from tit.plotting.nilearn import __main__ as runner

    monkeypatch.setattr(
        runner,
        "_average_fields",
        lambda pairs: _Img(np.linspace(0.0, 1.0, 27).reshape(3, 3, 3)),
    )

    def render(img, base, output_dir, *a, **k):
        path = Path(output_dir) / f"{base}.pdf"
        path.write_bytes(b"%PDF")
        return str(path)

    monkeypatch.setattr(runner, "create_pdf_entry_point_group", render)
    monkeypatch.setattr(runner, "_hold_locks", lambda *a: nullcontext())
    config = {
        "subject_simulation_pairs": [
            {"subject_id": "001", "simulation_name": SIM},
            {"subject_id": "002", "simulation_name": SIM},
        ],
        "subdir_name": "viz1",
        "create_glass_brain": False,
    }
    planned = _plan(client, "nilearn", config)["jobs"]
    before = _files(project, "*.pdf")
    _run(runner, config, project, tmp_path, monkeypatch)
    written = _files(project, "*.pdf") - before
    assert [_real(j["output_dir"]) for j in planned] == [next(iter(written)).parent]


# ---------------------------------------------------------------------------------------------
# source
# ---------------------------------------------------------------------------------------------


def test_source_forward_writes_where_the_plan_says(
    client, project, tmp_path, monkeypatch
) -> None:
    from tit.source import __main__ as runner
    from tit.source import forward

    monkeypatch.setattr(forward, "_ensure_fork_start_method", lambda: None)
    monkeypatch.setattr(forward, "_check_forward_dependencies", lambda: None)

    def stop(*a, **k):
        raise RuntimeError("stopped after the forward folder was made")

    monkeypatch.setattr(forward, "_read_simnibs_montage", stop)
    monkeypatch.setattr(runner, "_hold_locks", lambda *a: nullcontext())
    config = {"mode": "forward", "subject_ids": ["001"], "forward": {}}
    planned = _plan(client, "source", config)["jobs"]
    before = {p for p in project.rglob("*") if p.is_dir()}
    path = tmp_path / "source.json"
    path.write_text(json.dumps({**config, "project_dir": str(project)}))
    monkeypatch.setattr(sys, "argv", ["tit.source", str(path)])
    with pytest.raises(SystemExit):
        runner.main()
    made = {p.resolve() for p in project.rglob("*") if p.is_dir()} - {
        p.resolve() for p in before
    }
    assert [_real(j["output_dir"]) for j in planned] == sorted(made)


def _fsavg_run(
    project, tmp_path, monkeypatch, overwrite: bool, spacing: int = 5
) -> list[str]:
    from tit.source import __main__ as runner
    from tit.source import fsaverage

    computed: list[str] = []

    def compute(pm, sid, sim, cfg):
        computed.append(sid)
        return {}

    def write(out_path, maps, spacing, meta):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"msh")

    monkeypatch.setattr(fsaverage, "_compute_fields", compute)
    monkeypatch.setattr(fsaverage, "write_fsaverage_msh", write)
    monkeypatch.setattr(fsaverage, "_recorded_carrier_only", lambda *a: False)
    monkeypatch.setattr(runner, "_hold_locks", lambda *a: nullcontext())
    config = _fsavg_config(overwrite, spacing)
    path = tmp_path / "fsavg.json"
    path.write_text(json.dumps({**config, "project_dir": str(project)}))
    monkeypatch.setattr(sys, "argv", ["tit.source", str(path)])
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 0
    return computed


def _fsavg_config(overwrite: bool, spacing: int = 5) -> dict:
    return {
        "mode": "fsavg_map",
        "pairs": [{"subject_id": "001", "simulation": SIM}],
        "fsavg_map": {"overwrite": overwrite, "fsaverage_spacing": spacing},
    }


def test_source_fsavg_map_writes_where_the_plan_says_and_replaces_only_on_overwrite(
    client, project, tmp_path, monkeypatch
) -> None:
    planned = _plan(client, "source", _fsavg_config(False))["jobs"]
    before = _files(project, "*.msh")
    assert _fsavg_run(project, tmp_path, monkeypatch, overwrite=False) == ["001"]
    written = _files(project, "*.msh") - before
    assert [_real(j["output_dir"]) for j in planned] == [next(iter(written)).parent]

    # The projection exists now. Without overwrite the runner keeps it, so the plan must
    # not ask to replace it; with overwrite it recomputes, and the plan says so.
    kept = _plan(client, "source", _fsavg_config(False))["jobs"][0]
    assert _fsavg_run(project, tmp_path, monkeypatch, overwrite=False) == []
    assert (kept["exists"], kept["will_overwrite"]) == (True, False)
    replaced = _plan(client, "source", _fsavg_config(True))["jobs"][0]
    assert _fsavg_run(project, tmp_path, monkeypatch, overwrite=True) == ["001"]
    assert (replaced["exists"], replaced["will_overwrite"]) == (True, True)


def test_source_fsavg_map_of_another_spacing_is_not_an_existing_output(
    client, project, tmp_path, monkeypatch
) -> None:
    """The fsaverage folder holds one projection per spacing; only the planned one counts."""
    assert _fsavg_run(project, tmp_path, monkeypatch, overwrite=False, spacing=6) == [
        "001"
    ]
    fsavg5 = _plan(client, "source", _fsavg_config(False, spacing=5))["jobs"][0]
    # The runner computes the fsaverage5 projection: nothing of it was on disk to keep.
    assert _fsavg_run(project, tmp_path, monkeypatch, overwrite=False, spacing=5) == [
        "001"
    ]
    assert (fsavg5["exists"], fsavg5["will_overwrite"]) == (False, False)
    fsavg6 = _plan(client, "source", _fsavg_config(True, spacing=6))["jobs"][0]
    assert (fsavg6["exists"], fsavg6["will_overwrite"]) == (True, True)
    assert fsavg5["output_dir"] == fsavg6["output_dir"]
