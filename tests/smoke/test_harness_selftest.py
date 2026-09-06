"""Self-tests for the smoke harness itself -- no server, no dataset, runs in the default suite.

What this pins
--------------
The harness cannot rot silently while nobody has a container up. Every rule the matrix relies
on is checked here off disk: rows are unique and complete, every builder produces a
JSON-serializable body, every path a row claims is namespaced under ``smoke-<runid>``, the
cleanup manifest deletes only what it created, and the payload loader really does prefer a
recorded UI payload over the built-in config.

The failure it prevents
-----------------------
A matrix that no longer imports, a row whose config stopped being JSON, or a namespacing typo
that would point cleanup at a real output directory -- each of which is only discovered on the
maintainer's dataset, at the moment it does damage, if this file does not exist.

Deliberately **not** marked ``smoke``: these are ordinary unit tests (~30 ms) and they must run
in ``python3 -m pytest -q`` so a broken harness is red before anyone starts a container.

Reproduce: ``python3 -m pytest -q tests/smoke/test_harness_selftest.py``.

Written 2026-09-03 (lane S1).
"""

from __future__ import annotations

import ast
import json
import os

import pytest

from tests.smoke import matrix, test_kinds
from tests.smoke.cleanup import Manifest
from tests.smoke.matrix import BEHAVIOURS, COMPLETED, REFUSED, ROWS, STARTED_THEN_CANCEL, Ctx


@pytest.fixture
def ctx() -> Ctx:
    return Ctx(run_id="selftest", root="/mnt/000")


def test_matrix_is_not_empty_and_ids_are_unique():
    assert len(ROWS) >= 15, "the §3 fixture matrix lost rows"
    ids = [r.id for r in ROWS]
    assert len(ids) == len(set(ids)), f"duplicate row ids: {ids}"


@pytest.mark.parametrize("row", ROWS, ids=[r.id for r in ROWS])
def test_row_is_complete(row, ctx: Ctx):
    assert row.behaviour in BEHAVIOURS
    assert row.why_subject.strip(), f"{row.id}: §3 requires a 'why this subject' sentence"
    assert row.budget_s > 0
    submission = row.build(ctx)
    # JSON-serializable: the client posts this verbatim.
    json.dumps(
        {
            "kind": submission.kind,
            "config": submission.config,
            "subject_ids": submission.subject_ids,
        }
    )
    assert submission.kind
    if row.behaviour == REFUSED:
        assert row.refusal, f"{row.id}: a refused row must say what a readable refusal looks like"
    else:
        assert row.banner or row.no_banner_reason, (
            f"{row.id}: needs a banner pattern to prove the runner started, or a stated "
            "no_banner_reason"
        )
    if row.behaviour == COMPLETED:
        # Something on disk or in the catalog must be checked. A row with no named artifact
        # file still has its output directory: test_kinds asserts every claimed directory
        # exists and is non-empty after a success, which is why creates() counts here.
        assert (
            row.expect_files(ctx)
            or row.catalog is not None
            or row.creates(ctx)
            or row.id == "project_init"
        ), f"{row.id}: a completed row must check an artifact, a directory or a catalog listing" 


@pytest.mark.parametrize("row", ROWS, ids=[r.id for r in ROWS])
def test_every_claimed_path_is_namespaced_or_a_new_subject(row, ctx: Ctx):
    """Cleanup may only ever target a smoke-namespaced path or a subject this run creates.

    The failure it prevents: a builder that names a real run (``Simulations/Thalamus``) would
    make :meth:`Manifest.remove_created` a delete of the maintainer's data the first time the
    pre-existence check is bypassed or the path is created fresh.
    """
    allowed_unnamespaced = {  # noqa: E501 - one path per line is the point
        "/mnt/000/sub-102",  # pre_dicom creates this subject; nothing else owns it
        "/mnt/000/derivatives/SimNIBS/sub-102",
        "/mnt/000/derivatives/fastsurfer/sub-102",
        "/mnt/000/derivatives/ti-toolbox/reports/sub-102",
        "/mnt/000/derivatives/ti-toolbox/reports/sub-MNI152",
        "/mnt/000/derivatives/ti-toolbox/tissue_analysis/sub-MNI152",
        "/mnt/000/derivatives/SimNIBS/sub-101/forward",
        "/mnt/000/derivatives/SimNIBS/sub-101/leadfields/101_leadfield_GSN-HydroCel-185.hdf5",
        "/mnt/000/derivatives/SimNIBS/sub-101/leadfields/101_electrodes_GSN-HydroCel-185.msh",
        # per-kind parent directories a first run of that kind creates (claimed after the run
        # directory, so an existing one is recorded as pre-existing and never deleted)
        "/mnt/000/derivatives/ti-toolbox/nifti_average",
        "/mnt/000/derivatives/ti-toolbox/nilearn_visuals",
        "/mnt/000/derivatives/ti-toolbox/stats",
        "/mnt/000/derivatives/ti-toolbox/stats/group_comparison",
    }
    for path in row.creates(ctx):
        assert path.startswith("/mnt/000/"), f"{row.id}: claim outside the project: {path}"
        assert "smoke-selftest" in path or path in allowed_unnamespaced, (
            f"{row.id}: claims {path}, which is neither namespaced nor a known new output"
        )


def test_heavy_rows_are_the_fem_class():
    heavy = {r.id for r in ROWS if r.heavy}
    assert {"sim_ti", "sim_mti", "flex", "leadfield", "pre_charm", "pre_fastsurfer"} <= heavy
    assert "analyzer_mesh" not in heavy and "ex" not in heavy


def test_rows_for_selects_by_id_and_by_kind():
    assert [r.id for r in matrix.rows_for(["sim_ti"])] == ["sim_ti"]
    assert {r.id for r in matrix.rows_for(["sim"])} == {"sim_ti", "sim_mti"}
    assert len(matrix.rows_for(None)) == len(ROWS)
    with pytest.raises(SystemExit):
        matrix.rows_for(["not_a_kind"])


# -- cleanup manifest -------------------------------------------------------------------------


def test_manifest_removes_only_what_it_created(tmp_path):
    pre = tmp_path / "pre_existing"
    pre.mkdir()
    (pre / "keep.txt").write_text("the maintainer's data")
    manifest = Manifest(container_root="/mnt/000", host_root=str(tmp_path))
    manifest.claim("row", "/mnt/000/pre_existing")
    manifest.claim("row", "/mnt/000/created")
    (tmp_path / "created").mkdir()  # created *after* the claim, as a real run would

    removed = manifest.remove_created()

    assert [c.container_path for c in removed] == ["/mnt/000/created"]
    assert pre.exists(), "a pre-existing path must survive cleanup (decision P6)"
    assert not (tmp_path / "created").exists()


def test_manifest_keep_deletes_nothing(tmp_path):
    manifest = Manifest(container_root="/mnt/000", host_root=str(tmp_path), keep=True)
    manifest.claim("row", "/mnt/000/created")
    (tmp_path / "created").mkdir()
    assert manifest.remove_created() == []
    assert (tmp_path / "created").exists()


def test_manifest_never_claims_a_path_twice(tmp_path):
    manifest = Manifest(container_root="/mnt/000", host_root=str(tmp_path))
    first = manifest.claim("row", "/mnt/000/x")
    second = manifest.claim("other", "/mnt/000/x")
    assert first is second and len(manifest.claims) == 1


def test_claim_produced_takes_a_file_this_run_wrote_out_of_a_shared_directory(tmp_path):
    """A report written beside the maintainer's own reports must still be cleaned up."""
    shared = tmp_path / "reports" / "sub-102"
    shared.mkdir(parents=True)
    theirs = shared / "pre_processing_report_20260403.html"
    theirs.write_text("the maintainer's report")
    os.utime(theirs, (1000.0, 1000.0))
    ours = shared / "pre_processing_report_20260903.html"
    ours.write_text("this run's report")

    manifest = Manifest(container_root="/mnt/000", host_root=str(tmp_path))
    since = os.path.getmtime(ours) - 1
    assert manifest.claim_produced("row", "/mnt/000/reports/sub-102/pre_processing_report_20260903.html", since)
    assert manifest.claim_produced("row", "/mnt/000/reports/sub-102/pre_processing_report_20260403.html", since) is None

    manifest.remove_created()
    assert theirs.exists(), "a file older than the job must never be claimed as produced"
    assert not ours.exists()


def test_claim_produced_ignores_a_path_that_does_not_exist(tmp_path):
    manifest = Manifest(container_root="/mnt/000", host_root=str(tmp_path))
    assert manifest.claim_produced("row", "/mnt/000/nothing/here.html", 0.0) is None
    assert manifest.claims == []


def test_manifest_maps_container_paths_onto_the_bind_mount(tmp_path):
    manifest = Manifest(container_root="/mnt/000", host_root="/host/000")
    assert manifest.host_path("/mnt/000/sub-101/anat") == "/host/000/sub-101/anat"
    assert manifest.host_path("/mnt/000") == "/host/000"
    assert manifest.host_path("/elsewhere/x") == "/elsewhere/x"


# -- payload loader (decision P5: both paths must be exercised) --------------------------------


def _row(row_id: str):
    return next(r for r in ROWS if r.id == row_id)


def test_loader_uses_the_builtin_config_when_no_payload_is_recorded(ctx, monkeypatch, tmp_path):
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    submission, source, origin = test_kinds.load_submission(_row("sim_ti"), ctx)
    assert source == "builtin" and origin.endswith("matrix.py")
    assert submission.config["montages"][0]["name"] == "smoke-selftest-ti"


def test_loader_prefers_a_recorded_ui_payload_over_the_builtin_config(ctx, monkeypatch, tmp_path):
    body = {
        "kind": "sim",
        "config": {"subject_id": "101", "montages": [{"_type": "Montage", "name": "from-ui"}]},
        "subject_ids": ["101"],
    }
    (tmp_path / "sim_ti.json").write_text(json.dumps(body))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    submission, source, origin = test_kinds.load_submission(_row("sim_ti"), ctx)
    assert source == "payload" and origin == "sim_ti.json"
    assert submission.subject_ids == ["101"] and submission.group is False
    # sim_ti's own payload_rename (below) rewrites the montage name on every load, so it is
    # neither the recorded "from-ui" nor the builtin config's own "smoke-selftest-ti" -- proof
    # this really is the *payload's* montage (only field present here), rewritten, not a
    # silently substituted builtin one.
    assert submission.config["montages"][0]["name"] == "smoke-selftest-sim_ti-0"


def test_loader_falls_back_from_row_id_to_kind_for_the_first_row_of_that_kind(ctx, monkeypatch, tmp_path):
    (tmp_path / "sim.json").write_text(json.dumps({"config": {"subject_id": "101"}}))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    _, source, origin = test_kinds.load_submission(_row("sim_ti"), ctx)
    assert source == "payload" and origin == "sim.json"


def test_the_kind_fallback_never_reaches_a_second_row_of_the_same_kind(ctx, monkeypatch, tmp_path):
    """sim_ti and sim_mti replaying one sim.json submit the same montage name twice, and the
    second job dies on SimNIBS's "Found already existing simulation results in directory"
    (job caad925a2e9c4142, 2026-09-03)."""
    (tmp_path / "sim.json").write_text(json.dumps({"config": {"subject_id": "101"}}))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    _, source, _ = test_kinds.load_submission(_row("sim_mti"), ctx)
    assert source == "builtin"


def test_the_kind_fallback_never_reaches_a_stage_tagged_row(ctx, monkeypatch, tmp_path):
    """A recorded pre.json encodes one stage combination; every other pre row is about a
    different stage tag and would look for a job the group does not contain."""
    (tmp_path / "pre.json").write_text(json.dumps({"config": {"run_tissue_analysis": True}}))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    for row_id in ("pre_dicom", "pre_charm", "pre_tissue"):
        _, source, _ = test_kinds.load_submission(_row(row_id), ctx)
        assert source == "builtin", row_id


def test_an_exact_row_id_payload_still_wins_for_any_row(ctx, monkeypatch, tmp_path):
    (tmp_path / "pre_charm.json").write_text(json.dumps({"config": {"create_m2m": True}}))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    _, source, origin = test_kinds.load_submission(_row("pre_charm"), ctx)
    assert source == "payload" and origin == "pre_charm.json"


def test_loader_reads_a_group_payload_as_a_group_submission(ctx, monkeypatch, tmp_path):
    body = {
        "kind": "pre",
        "config": {"subject_ids": ["102"], "convert_dicom": True},
        "subject_ids": ["102"],
        "parallel_subjects": 2,
    }
    (tmp_path / "pre_dicom.json").write_text(json.dumps(body))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    submission, source, _ = test_kinds.load_submission(_row("pre_dicom"), ctx)
    assert source == "payload" and submission.group is True
    assert submission.parallel_subjects == 2


# -- payload rename (decision P6, HX 2026-09-04): a replayed payload must not name a fixed ----
# -- output, so a second replay of the same recorded file finds a *fresh* target, not the -----
# -- first replay's own output -----------------------------------------------------------------


def test_loader_rewrites_analyzer_payload_output_dir_to_the_smoke_tag(ctx, monkeypatch, tmp_path):
    """A payload's ``output_dir: null`` is turned into a deterministic sphere-name directory by
    ``Analyzer._resolve_output_dir`` -- same config, same path, every replay -- so the second
    replay found it ``exists`` and skipped instead of running (found 2026-09-04)."""
    body = {
        "config": {
            "subject_id": "ernie",
            "simulation": "Thalamus",
            "space": "mesh",
            "output_dir": None,
        }
    }
    (tmp_path / "analyzer_mesh.json").write_text(json.dumps(body))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    submission, source, _ = test_kinds.load_submission(_row("analyzer_mesh"), ctx)
    assert source == "payload"
    assert submission.config["output_dir"] == (
        "/mnt/000/derivatives/SimNIBS/sub-ernie/Simulations/Thalamus/Analyses/Mesh/"
        "smoke-selftest-analyzer_mesh"
    )


def test_loader_rewrites_stats_analysis_name_to_the_smoke_tag(ctx, monkeypatch, tmp_path):
    body = {"config": {"analysis_name": "smoke-ui-4863", "subjects": []}}
    (tmp_path / "stats_group.json").write_text(json.dumps(body))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    submission, source, _ = test_kinds.load_submission(_row("stats_group"), ctx)
    assert source == "payload"
    assert submission.config["analysis_name"] == "smoke-selftest-stats_group"


def test_loader_rewrites_nifti_average_output_name(ctx, monkeypatch, tmp_path):
    body = {"config": {"output_name": "smoke-ui-90719", "subjects": []}}
    (tmp_path / "nifti_average.json").write_text(json.dumps(body))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    submission, source, _ = test_kinds.load_submission(_row("nifti_average"), ctx)
    assert source == "payload"
    assert submission.config["output_name"] == "smoke-selftest-nifti_average"


def test_loader_rewrites_nilearn_subdir_name(ctx, monkeypatch, tmp_path):
    body = {"config": {"subdir_name": "smoke-ui-90719"}}
    (tmp_path / "nilearn.json").write_text(json.dumps(body))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    submission, source, _ = test_kinds.load_submission(_row("nilearn"), ctx)
    assert source == "payload"
    assert submission.config["subdir_name"] == "smoke-selftest-nilearn"


def test_loader_rewrites_sim_montage_names(ctx, monkeypatch, tmp_path):
    body = {"config": {"montages": [{"_type": "Montage", "name": "smoke-ui-71595-ti"}]}}
    (tmp_path / "sim_ti.json").write_text(json.dumps(body))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    submission, source, _ = test_kinds.load_submission(_row("sim_ti"), ctx)
    assert source == "payload"
    assert submission.config["montages"][0]["name"] == "smoke-selftest-sim_ti-0"


def test_loader_replaying_the_same_payload_twice_yields_different_names(monkeypatch, tmp_path):
    """The whole point: two loads of one recorded payload file, in two different sessions
    (different ``run_id``), must never target each other's output."""
    body = {"config": {"analysis_name": "smoke-ui-4863", "subjects": []}}
    (tmp_path / "stats_group.json").write_text(json.dumps(body))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    first = test_kinds.load_submission(_row("stats_group"), Ctx(run_id="run-a", root="/mnt/000"))
    second = test_kinds.load_submission(_row("stats_group"), Ctx(run_id="run-b", root="/mnt/000"))
    assert first[0].config["analysis_name"] != second[0].config["analysis_name"]
    # And loading the *same* file twice under the *same* run_id (this row running twice in one
    # session) is stable, not random -- the second run's own row would still find its own first
    # run's directory, which is a real, separate P6 case (re-running the same row twice inside
    # one session), not the one this fix addresses (replaying the same *file* across sessions).
    third = test_kinds.load_submission(_row("stats_group"), Ctx(run_id="run-a", root="/mnt/000"))
    assert first[0].config["analysis_name"] == third[0].config["analysis_name"]


def test_loader_leaves_a_payload_untouched_when_no_rename_rule_applies(ctx, monkeypatch, tmp_path):
    """flex's ``output_folder: null`` is already self-namespacing (the runner timestamps it
    itself) -- there is nothing here for the loader to rewrite, and it must not invent one."""
    body = {"config": {"subject_id": "101", "output_folder": None}}
    (tmp_path / "flex.json").write_text(json.dumps(body))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    submission, source, _ = test_kinds.load_submission(_row("flex"), ctx)
    assert source == "payload"
    assert submission.config["output_folder"] is None


def test_loader_accepts_a_bare_config_object(ctx, monkeypatch, tmp_path):
    (tmp_path / "nilearn.json").write_text(json.dumps({"subject_simulation_pairs": []}))
    monkeypatch.setattr(test_kinds, "PAYLOAD_DIR", str(tmp_path))
    submission, source, _ = test_kinds.load_submission(_row("nilearn"), ctx)
    assert source == "payload" and submission.kind == "nilearn"
    assert submission.config["subject_simulation_pairs"] == []
    # nilearn's own payload_rename adds/rewrites subdir_name (below) -- the one field this bare
    # config didn't have, so its presence here is proof the rename ran, not a substituted config.
    assert submission.config["subdir_name"] == "smoke-selftest-nilearn"


def test_committed_payload_dir_holds_only_json_and_its_readme():
    stray = [
        n
        for n in os.listdir(test_kinds.PAYLOAD_DIR)
        if not (n.endswith(".json") or n == "README.md" or n.startswith("."))
    ]
    assert not stray, f"unexpected files in tests/smoke/payloads: {stray}"


# -- coverage of the product's own kind list ---------------------------------------------------


def _job_kinds_from_source() -> set[str]:
    """``JOB_KINDS`` read out of ``tit/jobs/spec.py`` with ``ast`` -- source, not an import.

    The live server publishes no OpenAPI document (``tit/server/app.py`` sets
    ``openapi_url=None``), so there is no runtime way to ask it which kinds it accepts; and
    importing ``tit`` here would drag SimNIBS mocks into a suite that is otherwise
    dependency-free. Reading the declaration off disk is the enforcement a lint cannot silence
    (agentic-rules principle 11).
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tree = ast.parse(open(os.path.join(root, "tit", "jobs", "spec.py"), encoding="utf-8").read())
    for node in tree.body:
        targets = getattr(node, "targets", []) or ([node.target] if hasattr(node, "target") else [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "JOB_KINDS":
                return {ast.literal_eval(e) for e in node.value.elts}
    raise AssertionError("JOB_KINDS not found in tit/jobs/spec.py")


def test_every_job_kind_the_server_accepts_has_a_smoke_row():
    """The `report` failure class: a kind that is planned and submittable but never run.

    Exemptions are named, not implied: `report` is only ever the trailing job of a `pre` group
    (covered by row pre_report), and flex_adaptive/flex_pareto are the same runner as `flex`
    with one config field changed.
    """
    covered = {r.kind for r in ROWS}
    exempt = {"report", "flex_adaptive", "flex_pareto"}
    known = _job_kinds_from_source() - exempt
    assert known, "no job kinds parsed out of tit/jobs/spec.py"
    assert not (known - covered), f"job kinds with no smoke row: {sorted(known - covered)}"
