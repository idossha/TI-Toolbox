"""The desktop's generated contract fixtures are what the real code produces today.

What this pins (2026-10-22, package p39): two committed generators write fixtures the desktop
tests and the mock server read, from the real server code on synthetic projects:

* ``dev/make_contract_fixtures.py`` -> ``desktop/tests/fixtures/contracts/`` (the real
  ``candidate_detail`` for a flex, an ex and an mEx run; the real ``build_overview``; the real
  ``POST /api/plan/analyzer`` answers), ``contracts/job_output_dirs.json`` (the real ``GET
  /api/jobs/{id}`` ``output_dir`` for each kind of job) and ``analyses.json`` (the real ``GET
  /api/catalog/analyses`` listing of the analyses the mock project holds);
* ``dev/regen_mock_reports.py`` -> ``desktop/tests/fixtures/reports/<sid>/*.html`` (the real
  simulation and ex-search report generators) and ``reports.json`` (the real
  ``tit.catalog.reports`` listing of those pages).

Each generator is run in-process here and must reproduce the committed files byte for byte, so a
change to the producers (a renamed key, a new montage name, a report section) shows up as a
stale fixture instead of a desktop test that keeps passing against the old shape. The semantic
checks live with the readers: ``desktop/tests/unit/candidate-handoff.test.ts``,
``desktop/tests/unit/overview-contract.test.ts``, ``desktop/tests/mock-server/contract.test.ts``
and ``tests/test_mock_fixture_drift.py``.

Reproduce: ``.venv/bin/python dev/make_contract_fixtures.py && .venv/bin/python
dev/regen_mock_reports.py && .venv/bin/python -m pytest tests/test_contract_fixtures_fresh.py -q``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "desktop" / "tests" / "fixtures"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "dev" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def contracts() -> dict[str, str]:
    return _load("make_contract_fixtures").build()


@pytest.fixture(scope="module")
def reports() -> dict[str, str]:
    return _load("regen_mock_reports").build()


def test_contract_fixtures_are_fresh(contracts: dict[str, str]) -> None:
    assert sorted(contracts) == [
        "analyses.json",
        "contracts/analyzer_plans.json",
        "contracts/candidate_detail_ex.json",
        "contracts/candidate_detail_flex.json",
        "contracts/candidate_detail_mex.json",
        "contracts/job_output_dirs.json",
        "contracts/overview.json",
    ]
    committed = sorted(
        f"contracts/{p.name}" for p in (FIXTURES / "contracts").iterdir()
    )
    assert committed == sorted(
        k for k in contracts if k.startswith("contracts/")
    ), "a committed contract fixture no generator writes"
    for name, text in contracts.items():
        assert (FIXTURES / name).read_text(
            encoding="utf-8"
        ) == text, f"{name} is stale: run dev/make_contract_fixtures.py"


def test_candidate_fixtures_answer_their_own_requests(
    contracts: dict[str, str],
) -> None:
    """Each fixture is the detail of the candidate its request names, in its run and kind."""
    for kind, pairs in (("flex", 2), ("ex", 2), ("mex", 4)):
        data = json.loads(contracts[f"contracts/candidate_detail_{kind}.json"])
        request, response = data["request"], data["response"]
        assert request["kind"] == kind
        assert response["candidate"]["id"] == request["candidate_id"]
        config = response["simulation_config"]
        assert config["subject_id"] == request["subject"]
        (montage,) = config["montages"]
        assert montage["provenance"]["run"] == request["run"]
        assert montage["provenance"]["candidate_id"] == request["candidate_id"]
        assert len(montage["electrode_pairs"]) == pairs == len(config["intensities"])
        assert re.fullmatch(r"candidate_[0-9a-f]{16}", montage["name"])
        # No temporary path survives the rewrite to the mock's project root.
        assert "/tmp" not in contracts[f"contracts/candidate_detail_{kind}.json"]
        assert (
            "/var/folders" not in contracts[f"contracts/candidate_detail_{kind}.json"]
        )


def test_analyzer_plans_follow_the_documented_folder_grammar(
    contracts: dict[str, str],
) -> None:
    """Every planned folder, derived by hand from the grammar ``PathManager`` documents.

    ``Simulations/<sim>/Analyses/<Mesh|Voxel>/<roi><_field><_tissue>``: a sphere is
    ``sphere_x<.2f>_y<.2f>_z<.2f>_r<radius>_<MNI|subject>``; an atlas region
    ``cortical_<region>_<atlas>``, several regions ``cortical_<n>regions_<atlas>_<md5[:8]>``, a
    label a folder cannot carry ``cortical_<sanitised>_<atlas>_<md5[:8]>``, no region
    ``whole_head_<atlas>``, subcortical the same with ``sub`` in front; a NIfTI mask is the region
    ``mask_<stem>_<space>_<sha256(path:space)[:10]>`` of no atlas. A field other than the envelope
    adds ``_<field>``; a voxel tissue other than GM adds ``_WM``/``_both``. This catches a generator
    whose config keys the route silently dropped (``deserialize_config`` ignores unknown keys).
    """
    plans = json.loads(contracts["contracts/analyzer_plans.json"])

    def md5(text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()[:8]

    def analyses(sid: str, sim: str) -> str:
        return f"/mnt/example/derivatives/SimNIBS/sub-{sid}/Simulations/{sim}/Analyses"

    thalamus = analyses("ernie", "Thalamus")
    mask = "/mnt/example/derivatives/SimNIBS/sub-ernie/m2m_ernie/masks/roi.nii.gz"
    mask_digest = hashlib.sha256(f"{mask}:subject".encode()).hexdigest()[:10]
    label = "Inferior Frontal Gyrus, pars triangularis"
    expected = {
        "held_ernie_Thalamus": f"{thalamus}/Mesh/cortical_2regions_DK40_"
        + md5("lh.bankssts+rh.bankssts"),
        "held_ernie_L_Insula": analyses("ernie", "L_Insula")
        + "/Mesh/cortical_lh.G_insular_short_a2009s",
        "held_ernie_docs_example": analyses("ernie", "docs_example")
        + "/Voxel/sphere_x-38.00_y44.00_z26.00_r10.0_MNI",
        "held_101_Thalamus": analyses("101", "Thalamus")
        + "/Mesh/sphere_x-12.00_y-18.00_z6.00_r5.0_subject",
        "another_field": f"{thalamus}/Mesh/cortical_lh.insula_DK40_hf_peak",
        "repeated_regions": f"{thalamus}/Mesh/cortical_2regions_DK40_"
        + md5("rh.insula+lh.insula"),
        "unsafe_label": f"{thalamus}/Voxel/cortical_Inferior Frontal Gyrus_ pars "
        f"triangularis_HarvardOxford-cort-maxprob-thr25-1mm_{md5(label)}",
        "subcortical_tissue": f"{thalamus}/Voxel/subcortical_Left-Thalamus_aparc_a2009s_aseg_both",
        "whole_head": f"{thalamus}/Mesh/whole_head_DK40",
        "sphere_rounding": f"{thalamus}/Voxel/sphere_x0.12_y-1.38_z2.50_r7.5_MNI_WM",
        "mesh_ignores_tissue": f"{thalamus}/Mesh/sphere_x1.00_y2.00_z3.00_r5.0_subject",
        "explicit_output_dir": "/mnt/example/derivatives/custom/insula_run",
        "mask": f"{thalamus}/Voxel/cortical_mask_roi_subject_{mask_digest}_unknown_atlas",
    }
    # A group run: each subject's default folder, and the cohort summary in output_dir.
    insula = "Simulations/Thalamus/Analyses/Mesh/cortical_lh.insula_DK40"
    group = [
        ("ernie", f"/mnt/example/derivatives/SimNIBS/sub-ernie/{insula}"),
        ("101", f"/mnt/example/derivatives/SimNIBS/sub-101/{insula}"),
        ("", "/mnt/example/derivatives/ti-toolbox/group_analysis/insula_cohort"),
    ]
    got = {
        c["id"]: [(j["subject"], j["output_dir"]) for j in c["jobs"]]
        for c in plans["cases"]
    }
    want = {
        case: [(_planned_subject(plans, case), folder)]
        for case, folder in expected.items()
    }
    assert got == {**want, "group_output_dir": group}
    for case in plans["cases"]:
        for job in case["jobs"]:
            # A held folder exists and, the analyzer replacing it, needs an overwrite; no other.
            assert (job["exists"], job["will_overwrite"]) == (case["held"],) * 2, case


def _planned_subject(plans: dict, case_id: str) -> str:
    """The one subject a single-subject case was planned for (its config's ``subject_id``)."""
    (case,) = [c for c in plans["cases"] if c["id"] == case_id]
    assert case["subject_ids"] == [case["config"]["subject_id"]]
    return case["config"]["subject_id"]


def test_the_mock_analyses_are_the_held_plans(contracts: dict[str, str]) -> None:
    """``analyses.json`` lists exactly the held folders, described as their configs say."""
    plans = json.loads(contracts["contracts/analyzer_plans.json"])
    listing = json.loads(contracts["analyses.json"])
    listed = {
        (sid, sim, os.path.dirname(a["csv"])): a
        for sid, sims in listing.items()
        for sim, rows in sims.items()
        for a in rows
    }
    held = {
        (
            c["config"]["subject_id"],
            c["config"]["simulation"],
            c["jobs"][0]["output_dir"],
        ): c["config"]
        for c in plans["cases"]
        if c["held"]
    }
    assert set(listed) == set(held)
    for key, config in held.items():
        a = listed[key]
        folder = key[2]
        assert a["name"] == os.path.basename(folder)
        assert a["analysis_space"] == config["space"]
        assert a["field"] == config["field"]
        mni = config.get("coordinate_space") == "mni"
        assert a["space"] == ("mni" if mni else "subject")
        region = config.get("region")
        regions = [region] if isinstance(region, str) else (region or [])
        assert a["roi"] == "+".join(regions)


def test_mock_reports_are_fresh(reports: dict[str, str]) -> None:
    pages = sorted(k for k in reports if k.startswith("reports/"))
    assert len(pages) == 4
    committed = sorted(
        str(p.relative_to(FIXTURES)) for p in (FIXTURES / "reports").rglob("*.html")
    )
    assert committed == pages, "a committed report page no generator writes"
    for rel, text in reports.items():
        assert (FIXTURES / rel).read_text(
            encoding="utf-8"
        ) == text, f"{rel} is stale: run dev/regen_mock_reports.py"


def test_mock_report_listing_names_every_generated_page(
    reports: dict[str, str],
) -> None:
    listing = json.loads(reports["reports.json"])
    listed = sorted(
        f"reports/{sid}/{row['id'].split('/', 1)[1]}.html"
        for sid, rows in listing.items()
        for row in rows
    )
    assert listed == sorted(k for k in reports if k.startswith("reports/"))
    # The page's own title is what links a simulation report to its simulation.
    for rel, text in reports.items():
        if "/simulation_report_" in rel:
            assert re.search(r"<title>[^<]+ simulation</title>", text), rel


def test_a_simulation_reports_listed_title_names_its_simulation(
    reports: dict[str, str],
) -> None:
    listing = json.loads(reports["reports.json"])
    checked = 0
    for sid, rows in listing.items():
        for row in rows:
            if row["kind"] != "simulation_report":
                continue
            page = reports[f"reports/{sid}/{row['id'].split('/', 1)[1]}.html"]
            simulation = re.search(r"<title>([^<]+) simulation</title>", page)[1]
            checked += 1
            assert simulation in row["title"], (row["id"], row["title"])
    assert checked >= 2
