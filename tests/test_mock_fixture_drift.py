"""The desktop mock server's catalog fixtures have the real server's shapes and value domains.

What this pins (2026-10-22, package p39): ``desktop/tests/fixtures/{simulations, analyses,
group_catalog, rois_seed, flex_runs, ex_runs, reports}.json`` are what the mock server answers
for the catalog routes every e2e spec reads. They were written by hand and had drifted: NIfTIs
under ``TI/subject_overlays/`` (the simulator writes ``TI/niftis/<sim>_TI_subject_<field>``),
mesh kinds ``ti``/``mti``, analyses without ``analysis_space``/``figures``/``scene`` under
``Analyses/<name>/summary.csv``, group runs under ``derivatives/group/``, ROIs with a radius,
``png`` artifacts, ex nets without ``.csv``, reports with invented ids.

Where the expectations come from: the real server. The synthetic project of
``tests/contract_project.py`` (shaped like Dataset 000) is served by the real FastAPI app
through ``TestClient``, and for each object type the mock fixture is compared with the real
response:

* key sets are equal, object by object;
* enum-like values are inside the real domain (the values the real response carries, or the
  real constant the server draws them from: ``catalog.SIM_NIFTI_FIELDS``,
  ``catalog._REPORT_KIND_TITLES``);
* every path follows the real layout: its directory is the real response's directory with the
  identifiers swapped, and its file name is read back by the real classifier
  (``catalog.classify_sim_nifti`` for NIfTIs, ``catalog._dir_artifacts`` for run artifacts);
* a simulation's ``report_ids`` are what ``catalog._report_ids_for_simulation`` links from the
  generated report pages (``dev/regen_mock_reports.py``).

Reproduce: ``.venv/bin/python -m pytest tests/test_mock_fixture_drift.py -q``. The mock's
report HTML and listing are regenerated and checked for freshness in
``tests/test_contract_fixtures_fresh.py``; the mock's report CSP and id grammar against the real
source in ``desktop/tests/mock-server/contract.test.ts``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tests.contract_project import ContractProject, build_contract_project  # noqa: E402
from tit import catalog  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "desktop" / "tests" / "fixtures"
MOCK_ROOT = "/mnt/example"
TOKEN = "mock-fixture-drift"
GROUP_ANALYSIS = "cohort_TI_max_DK40"


def _mock(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture()
def real(tmp_path: Path) -> dict:
    """The real server's catalog responses for the synthetic project, root-relative paths kept."""
    project: ContractProject = build_contract_project(tmp_path / "project")
    group_dir = project.root / "derivatives" / "ti-toolbox" / "group_analysis"
    (group_dir / GROUP_ANALYSIS).mkdir(parents=True)
    (group_dir / GROUP_ANALYSIS / "group_summary.csv").write_text("subject,mean\n")
    sid, sim = project.subject, project.ti_sim
    app = create_app(ServerSettings(project_dir=str(project.root), token=TOKEN))
    headers = {"Authorization": f"Bearer {TOKEN}"}
    urls = {
        "simulations": f"/api/catalog/simulations?subject={sid}",
        "analyses": f"/api/catalog/analyses?subject={sid}&simulation={sim}",
        "group": "/api/catalog/group",
        "rois": f"/api/catalog/rois?subject={sid}",
        "flex_runs": f"/api/catalog/flex-runs?subject={sid}",
        "ex_runs": f"/api/catalog/ex-runs?subject={sid}&kind=ex",
        "reports": f"/api/catalog/reports?subject={sid}",
    }
    out = {"root": str(project.root), "project": project}
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        for key, url in urls.items():
            response = client.get(url, headers=headers)
            assert response.status_code == 200, (url, response.text)
            out[key] = response.json()
    out["simulations"] = out["simulations"]["simulations"]
    return out


def _flat(mapping) -> list:
    """Every object of a ``{subject: [...]}`` or ``{subject: {kind: [...]}}`` fixture."""
    items = []
    for value in mapping.values():
        if isinstance(value, dict):
            for inner in value.values():
                items.extend(inner)
        else:
            items.extend(value)
    return items


def _keys(objects: list[dict], label: str) -> set[str]:
    assert objects, f"no real {label} to compare with: the synthetic project lost them"
    keys = {frozenset(o) for o in objects}
    assert len(keys) == 1, f"real {label} objects disagree on their keys: {keys}"
    return set(next(iter(keys)))


def _rel_dir(path: str, root: str) -> str:
    for prefix in sorted({root, os.path.realpath(root)}, key=len, reverse=True):
        if path.startswith(prefix + "/"):
            return os.path.dirname(path[len(prefix) + 1 :])
    raise AssertionError(f"{path} is not under the project {root}")


def _template(rel_dir: str, **ids: str) -> str:
    """A real directory with its identifiers turned into ``{placeholders}``, segment by segment."""
    segments = []
    for seg in rel_dir.split("/"):
        for key, value in ids.items():
            if seg == value:
                seg = "{" + key + "}"
                break
            if seg == f"sub-{value}":
                seg = "sub-{" + key + "}"
                break
        segments.append(seg)
    return "/".join(segments)


def _mock_dir(path: str) -> str:
    assert path.startswith(
        MOCK_ROOT + "/"
    ), f"{path} is not under the mock root {MOCK_ROOT}"
    return os.path.dirname(path[len(MOCK_ROOT) + 1 :])


# ── key sets ──────────────────────────────────────────────────────────────────


def test_every_mock_object_has_the_real_objects_keys(real: dict) -> None:
    sims = _flat(_mock("simulations.json"))
    analyses = [
        a
        for per_sim in _mock("analyses.json").values()
        for rows in per_sim.values()
        for a in rows
    ]
    group = _mock("group_catalog.json")
    flex = _flat(_mock("flex_runs.json"))
    ex = _flat(_mock("ex_runs.json"))
    pairs = [
        ("simulation", real["simulations"], sims),
        (
            "simulation nifti",
            [n for s in real["simulations"] for n in s["niftis"]],
            [n for s in sims for n in s["niftis"]],
        ),
        (
            "simulation mesh",
            [m for s in real["simulations"] for m in s["meshes"]],
            [m for s in sims for m in s["meshes"]],
        ),
        ("analysis", real["analyses"], analyses),
        (
            "analysis figure",
            [f for a in real["analyses"] for f in a["figures"]],
            [f for a in analyses for f in a["figures"]],
        ),
        ("group stats run", real["group"]["stats"], group["stats"]),
        ("group nilearn visual", real["group"]["nilearn"], group["nilearn"]),
        ("group analysis", real["group"]["group_analyses"], group["group_analyses"]),
        ("NIfTI average", real["group"]["nifti_average"], group["nifti_average"]),
        ("ROI", real["rois"], _flat(_mock("rois_seed.json"))),
        ("flex run", real["flex_runs"], flex),
        (
            "flex run artifact",
            [a for r in real["flex_runs"] for a in r["artifacts"]],
            [a for r in flex for a in r["artifacts"]],
        ),
        (
            "flex net mapping",
            [m for r in real["flex_runs"] for m in r["mappings"]],
            [m for r in flex for m in r["mappings"]],
        ),
        ("ex run", real["ex_runs"], ex),
        ("ex run best", [r["best"] for r in real["ex_runs"]], [r["best"] for r in ex]),
        (
            "ex run artifact",
            [a for r in real["ex_runs"] for a in r["artifacts"]],
            [a for r in ex for a in r["artifacts"]],
        ),
        ("report", real["reports"], _flat(_mock("reports.json"))),
    ]
    assert set(group) == set(real["group"]), "the group catalog's sections"
    for label, real_objects, mock_objects in pairs:
        want = _keys(real_objects, label)
        assert mock_objects, f"the mock has no {label} to check"
        for obj in mock_objects:
            assert (
                set(obj) == want
            ), f"mock {label} {obj.get('name') or obj.get('path') or obj}: {sorted(set(obj) ^ want)}"


# ── simulations: layout, classifier, aggregates, report links ────────────────


def test_simulation_files_are_named_and_placed_as_the_simulator_writes_them(
    real: dict,
) -> None:
    project, root = real["project"], real["root"]
    ids = {"sid": project.subject}
    nifti_dirs = set()
    mesh_dirs = {}
    for sim in real["simulations"]:
        for n in sim["niftis"]:
            nifti_dirs.add(_template(_rel_dir(n["path"], root), sim=sim["name"], **ids))
        for m in sim["meshes"]:
            mesh_dirs.setdefault(m["kind"], set()).add(
                _template(_rel_dir(m["path"], root), sim=sim["name"], **ids)
            )
    # The real response covers both envelope modes and the carriers, so the layouts are all there.
    assert {d.split("/")[-2] for d in nifti_dirs} == {"TI", "mTI", "high_Frequency"}
    real_tissues = {n["tissue"] for s in real["simulations"] for n in s["niftis"]}
    real_spaces = {n["space"] for s in real["simulations"] for n in s["niftis"]}
    checked = 0
    for sid, sims in _mock("simulations.json").items():
        for sim in sims:
            assert sim["path"] == f"{MOCK_ROOT}/" + _template(
                _rel_dir(real["simulations"][0]["path"] + "/x", root),
                sim=real["simulations"][0]["name"],
                **ids,
            ).format(sid=sid, sim=sim["name"])
            for n in sim["niftis"]:
                directory = _mock_dir(n["path"])
                assert directory in {
                    d.format(sid=sid, sim=sim["name"]) for d in nifti_dirs
                }, n["path"]
                info = catalog.classify_sim_nifti(
                    os.path.basename(n["path"]), sim["name"]
                )
                assert info is not None, f"the simulator never writes {n['path']}"
                assert (info["field"], info["space"], info["tissue"]) == (
                    n["field"],
                    n["space"],
                    n["tissue"],
                ), n["path"]
                mode = directory.split("/")[-2]
                assert info["kind"] == (
                    "carrier" if mode == "high_Frequency" else "envelope"
                ), n["path"]
                assert n["field"] in catalog.SIM_NIFTI_FIELDS
                assert n["space"] in real_spaces and n["tissue"] in real_tissues
                checked += 1
            for m in sim["meshes"]:
                assert (
                    m["kind"] in mesh_dirs
                ), f"mesh kind {m['kind']!r} is not one the server uses"
                assert _mock_dir(m["path"]) in {
                    d.format(sid=sid, sim=sim["name"]) for d in mesh_dirs[m["kind"]]
                }, m["path"]
    assert checked > 0


def test_simulation_aggregates_are_what_simulation_detail_derives(real: dict) -> None:
    """``fields``/``space`` are the sorted sets of the NIfTIs' (the real response obeys it too)."""
    for sim in real["simulations"] + _flat(_mock("simulations.json")):
        assert sim["fields"] == sorted({n["field"] for n in sim["niftis"]}), sim["name"]
        assert sim["space"] == sorted({n["space"] for n in sim["niftis"]}), sim["name"]
        modes = {
            p.split("/Simulations/")[1].split("/")[1]
            for p in [n["path"] for n in sim["niftis"]]
            + [m["path"] for m in sim["meshes"]]
        }
        # ``has_ti``/``has_mti`` say the mode folder exists; a listed file proves it does (an mTI
        # run's TI/ folder can hold only per-pair files the catalog does not list).
        assert sim["has_mti"] == ("mTI" in modes), sim["name"]
        assert sim["has_ti"] or "TI" not in modes, sim["name"]


def test_report_ids_are_what_the_catalog_links_from_the_report_pages() -> None:
    reports = _mock("reports.json")
    linked = 0
    for sid, sims in _mock("simulations.json").items():
        local = [
            {
                **r,
                "path": str(
                    FIXTURES / "reports" / sid / f"{r['id'].split('/', 1)[1]}.html"
                ),
            }
            for r in reports.get(sid, [])
        ]
        for sim in sims:
            assert sim["report_ids"] == catalog._report_ids_for_simulation(
                local, sim["name"]
            ), sim["name"]
            linked += len(sim["report_ids"])
    assert linked >= 3, "the mock world should link reports to its simulations"
    # ...and the e2e case for a simulation with no report exists.
    assert any(not s["report_ids"] for s in _flat(_mock("simulations.json")))


# ── analyses ──────────────────────────────────────────────────────────────────


def test_analyses_live_where_the_analyzer_writes_them(real: dict) -> None:
    project, root = real["project"], real["root"]
    layout = {}
    for a in real["analyses"]:
        layout[a["analysis_space"]] = (
            _template(
                _rel_dir(a["csv"], root),
                sid=project.subject,
                sim=project.ti_sim,
                name=a["name"],
            ),
            os.path.basename(a["csv"]),
            os.path.basename(a["json"]),
        )
    assert set(layout) == {"mesh", "voxel"}
    figure_kinds = set(catalog._ANALYSIS_FIGURE_KINDS.values())
    spaces = {a["space"] for a in real["analyses"]}
    checked = 0
    for sid, per_sim in _mock("analyses.json").items():
        for sim, rows in per_sim.items():
            for a in rows:
                folder, csv_name, json_name = layout[a["analysis_space"]]
                folder = folder.format(sid=sid, sim=sim, name=a["name"])
                assert a["space"] in spaces
                assert (_mock_dir(a["csv"]), os.path.basename(a["csv"])) == (
                    folder,
                    csv_name,
                )
                assert (_mock_dir(a["json"]), os.path.basename(a["json"])) == (
                    folder,
                    json_name,
                )
                for f in a["figures"]:
                    assert _mock_dir(f["path"]) == folder and f["kind"] in figure_kinds
                    assert f["label"] == os.path.splitext(os.path.basename(f["path"]))[
                        0
                    ].replace("_", " ")
                if a["pdf"]:
                    # Every PDF in the folder is a figure (catalog._analysis_figures).
                    assert a["pdf"] in [f["path"] for f in a["figures"]]
                checked += 1
    assert checked > 0


# ── group catalog, ROIs, runs, reports ────────────────────────────────────────


def test_group_runs_live_under_the_real_group_folders(real: dict) -> None:
    root = real["root"]
    group = _mock("group_catalog.json")
    for section in ("stats", "nilearn", "group_analyses", "nifti_average"):
        templates = {
            _template(
                _rel_dir(r["path"] + "/x", root),
                name=r["name"],
                type=r.get("type", "\0"),
            )
            for r in real["group"][section]
        }
        assert templates, section
        for run in group[section]:
            got = _mock_dir(run["path"] + "/x")
            assert got in {
                t.format(name=run["name"], type=run.get("type", "")) for t in templates
            }, run["path"]
    assert {r["type"] for r in group["stats"]} <= {
        r["type"] for r in real["group"]["stats"]
    }


def test_rois_are_centres_in_a_real_space(real: dict) -> None:
    spaces = {r["space"] for r in real["rois"]}
    assert spaces == {"subject", "mni"}
    for roi in _flat(_mock("rois_seed.json")):
        assert roi["space"] in spaces
        assert all(isinstance(roi[k], float) for k in ("x", "y", "z")), roi


def test_run_artifacts_and_nets_are_labelled_by_the_real_rules(
    real: dict, tmp_path: Path
) -> None:
    root, project = real["root"], real["project"]
    flex = _flat(_mock("flex_runs.json"))
    ex = _flat(_mock("ex_runs.json"))
    real_flex_dir = _template(
        _rel_dir(real["flex_runs"][0]["path"] + "/x", root),
        sid=project.subject,
        run=real["flex_runs"][0]["name"],
    )
    real_ex_dir = _template(
        _rel_dir(real["ex_runs"][0]["path"] + "/x", root),
        sid=project.subject,
        run=real["ex_runs"][0]["run_name"],
    )
    for sid, runs in _mock("flex_runs.json").items():
        for run in runs:
            assert _mock_dir(run["path"] + "/x") == real_flex_dir.format(
                sid=sid, run=run["name"]
            )
    for sid, kinds in _mock("ex_runs.json").items():
        for kind, runs in kinds.items():
            for run in runs:
                expected = real_ex_dir.format(sid=sid, run=run["run_name"])
                if kind == "mex":
                    # No mEx run in the synthetic project: the PathManager's own layout.
                    pm = get_path_manager(root)
                    expected = _template(
                        _rel_dir(pm.m_ex_search_run(project.subject, "R") + "/x", root),
                        sid=project.subject,
                        run="R",
                    ).format(sid=sid, run=run["run_name"])
                assert _mock_dir(run["path"] + "/x") == expected
    for run in flex + ex:
        # The real labeller over the same file names.
        folder = tmp_path / "project" / "run"
        folder.mkdir(parents=True, exist_ok=True)
        for a in run["artifacts"]:
            (folder / os.path.basename(a["path"])).write_text("x")
        labelled = {
            os.path.basename(a["path"]): (a["kind"], a["label"])
            for a in catalog._dir_artifacts(
                str(folder), project_root=str(tmp_path / "project")
            )
        }
        for a in run["artifacts"]:
            assert labelled.get(os.path.basename(a["path"])) == (
                a["kind"],
                a["label"],
            ), a["path"]
        for f in folder.iterdir():
            f.unlink()
    # Ex/mEx name their net as a cap file (catalog._net_from_leadfield_hdf). A flex mapping's
    # net is what tit.sim.montage_sources wrote into it (save_mapping_result(..., "<net>.csv")),
    # pinned against the run's manifest by tests/test_flex_manifest_contract.py.
    real_ex_net = real["ex_runs"][0]["eeg_net"]
    assert real_ex_net.endswith(".csv")
    for run in ex:
        assert run["eeg_net"] == catalog._net_from_leadfield_hdf(run["eeg_net"])


def test_reports_are_listed_in_the_real_grammar(real: dict) -> None:
    root = real["root"]
    template = _template(
        _rel_dir(real["reports"][0]["path"], root), sid=real["project"].subject
    )
    for sid, rows in _mock("reports.json").items():
        for r in rows:
            stem = os.path.splitext(os.path.basename(r["path"]))[0]
            assert r["id"] == f"{sid}/{stem}"
            assert r["kind"] == catalog._report_kind_from_stem(stem)
            assert r["kind"] in catalog._REPORT_KIND_TITLES
            assert r["title"] == catalog._REPORT_KIND_TITLES[r["kind"]]
            assert _mock_dir(r["path"]) == template.format(sid=sid)
