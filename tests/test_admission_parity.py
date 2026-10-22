"""``/api/validate``, ``/api/plan`` and ``POST /api/jobs`` give one verdict for every config.

What this pins
--------------
The three doors a config reaches a runner through must agree: a config ``POST /api/validate``
calls fine is planned (``POST /api/plan`` is not 422) and submitted (``POST /api/jobs`` is 201),
and a config one of them refuses is refused by all three. Before this file, ``validate`` and
``plan`` read a ``flex_adaptive``/``flex_pareto`` config without the ``mode`` the job manager
writes into the runner's ``config.json`` (``JobManager._runner_config_path``), so a pareto sweep
with ``goal='mean'`` was "ok" at validate and planned, then refused at submit by
``check_job_config`` ("mode='flex_pareto' requires goal='focality'"); and an ex-search pool of
three electrodes (the page: "Add at least four electrodes to the pool.") was accepted by all
three and only refused by the runner, with no montage to evaluate.

Configs: every job of every case in ``tests/fixtures/desktop_configs/<page>/`` (written by the
real desktop builders), each in its own tmp project where the files the case names exist
(``tests/test_desktop_config_corpus.py::make_project``), plus planted variants of corpus cases
(flex_pareto/flex_adaptive with ``goal='mean'``, a single flex run carrying pareto settings in
place of thresholds, an ex pool of three and of four entries with three labels, an ex bucket
left empty, an mEx pool of seven, an mEx bucket left empty, analyzer fields no simulation has).

Where the expected values come from: the verdicts are computed by the real FastAPI app through
``TestClient`` -- the oracle is their agreement, never a retyped verdict. The planted variants'
expected refusal comes from the runner and the page (the sentences of
``desktop/src/renderer/pages/optimizer/plan.ts`` / ``cost.ts``; FlexConfig's mode/goal rule).

Decisions recorded here (named, asserted, never skipped)
--------------------------------------------------------
* Required-input checks are not this file's subject: ``POST /api/jobs`` runs the
  :mod:`tit.jobs.preflight` sweep (and, for ``pre`` with FreeSurfer, the sourcedata check)
  before the overwrite/plan check, and its verdict depends on files, not on the config
  (``tests/test_jobs_preflight.py`` and ``tests/test_submit_strict.py`` pin it). Both are
  replaced by "nothing missing" here, so the submit verdict is the config verdict:
  ``check_job_config`` + ``refuse_unknown_keys`` + the plan the overwrite check runs.
* Submit runs the dataclass rules of every kind: ``check_job_config`` covers
  sim/flex*/ex/mex/pre strictly, and ``check_overwrite_permission`` runs ``plan`` (the same
  ``deserialize_config`` + ``__post_init__``) for every other kind, so stats / nifti_average /
  nilearn / source / blender / analyzer need no second check (the analyzer and source runners'
  filtered-constructor fallback is left as it is).
* :data:`PRE_LEGACY_KEY_EXCEPTION`: a ``pre`` key from before the FastSurfer stage
  (``run_recon``) is flagged by ``/api/validate`` and translated by ``/api/plan`` and submit,
  as their runner does (``migrate_legacy_keys``) -- the one deliberate disagreement, asserted
  below so a change to it is seen.

Reproduce: ``.venv/bin/python -m pytest tests/test_admission_parity.py -q -p no:cacheprovider``.
Deliberately elsewhere: the page's own verdict for each case (``tests/test_desktop_config_corpus.py``),
unknown keys at submit (``tests/test_submit_strict.py``). Written 2026-10-22 (package c1_5).
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tests.test_desktop_config_corpus import (  # noqa: E402
    CORPUS,
    PAGES,
    load_case,
    make_project,
)
from tit.jobs import bootstrap  # noqa: E402
from tit.jobs.manager import JobManager  # noqa: E402
from tit.jobs.spec import Cost  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "admission-parity-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}

#: validate flags a pre-FastSurfer ``pre`` key; plan and submit translate it (module docstring).
PRE_LEGACY_KEY_EXCEPTION = "run_recon"


def _corpus_jobs() -> list[tuple[str, int]]:
    """(case file, job index) for every job of every corpus case."""
    out = []
    for page in PAGES:
        for path in sorted((CORPUS / page).glob("*.json")):
            jobs = json.loads(path.read_text())["jobs"]
            out.extend((str(path), i) for i in range(len(jobs)))
    return out


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr("tit.surfer_settings.available_threads", lambda: 8)
    monkeypatch.setattr(
        "tit.surfer_settings.settings_path", lambda: tmp_path / "preferences.json"
    )
    # File presence is preflight's verdict, not the config's (module docstring).
    monkeypatch.setattr(
        "tit.server.routes.jobs.preflight", lambda kind, config, project_dir: []
    )
    monkeypatch.setattr(
        "tit.pre.preflight.find_missing_preprocessing_inputs", lambda *a, **k: []
    )
    get_path_manager(str(tmp_path))
    fake = str(Path(__file__).parent / "fake_runner.py")
    jobs = JobManager(
        str(tmp_path),
        runner_cwd=str(tmp_path),
        poll_interval=0.05,
        budget=Cost(cpus=8, mem_gb=64),
        command_for=lambda kind, config, spec: [sys.executable, fake, spec],
    )
    jobs.start()
    bootstrap.set_manager_for_testing(jobs)
    settings = ServerSettings(project_dir=str(tmp_path), token=TOKEN)
    yield TestClient(create_app(settings), base_url="http://127.0.0.1:8765")
    jobs.shutdown()
    bootstrap.reset_manager()


def verdicts(
    client: TestClient, kind: str, config: dict[str, Any], subject_ids: list[str]
) -> dict[str, str | None]:
    """door -> ``None`` (accepted) or its refusal text, for validate, plan and submit."""
    v = client.post(f"/api/validate/{kind}", json={"config": config}, headers=BEARER)
    assert v.status_code == 200, v.text
    validate = None if v.json()["ok"] else v.json()["errors"][0]["message"]
    p = client.post(
        f"/api/plan/{kind}",
        json={"config": config, "subject_ids": subject_ids},
        headers=BEARER,
    )
    assert p.status_code in (200, 422), p.text
    plan = None if p.status_code == 200 else str(p.json()["detail"])
    s = client.post(
        "/api/jobs",
        json={"kind": kind, "config": config, "subject_ids": subject_ids},
        headers=BEARER,
    )
    assert s.status_code in (201, 422), s.text
    submit = None if s.status_code == 201 else str(s.json()["detail"])
    return {"validate": validate, "plan": plan, "submit": submit}


def _agree(found: dict[str, str | None]) -> bool:
    return len({text is None for text in found.values()}) == 1


def test_the_corpus_has_jobs_of_every_page() -> None:
    jobs = _corpus_jobs()
    assert {Path(path).parent.name for path, _ in jobs} == set(PAGES)
    assert len(jobs) >= 60


@pytest.mark.parametrize(
    ("path", "index"),
    [
        pytest.param(path, i, id=f"{Path(path).parent.name}/{Path(path).stem}#{i}")
        for path, i in _corpus_jobs()
    ],
)
def test_every_corpus_config_gets_one_verdict(
    path: str, index: int, client: TestClient, tmp_path: Path
) -> None:
    case = load_case(Path(path), tmp_path)
    make_project(tmp_path, case)
    job = case["jobs"][index]
    found = verdicts(client, job["kind"], job["config"], job["subject_ids"])
    assert _agree(found), f"{case['id']} ({job['kind']}): {found}"


# ---------------------------------------------------------------------------------------------
# planted variants: every door refuses, with the runner's / the page's reason
# ---------------------------------------------------------------------------------------------


def _corpus_job(case_id: str, project: Path) -> dict[str, Any]:
    case = load_case(CORPUS / f"{case_id}.json", project)
    make_project(project, case)
    return copy.deepcopy(case["jobs"][0])


def _refused_everywhere(found: dict[str, str | None], *needles: str) -> None:
    for door, text in found.items():
        assert text is not None, f"{door} accepted: {found}"
        for needle in needles:
            assert needle in text, f"{door} refused without {needle!r}: {text}"


@pytest.mark.parametrize("kind", ["flex_pareto", "flex_adaptive"])
def test_a_driver_sweep_with_goal_mean_is_refused_at_every_door(
    kind: str, client: TestClient, tmp_path: Path
) -> None:
    job = _corpus_job("optimizer-flex/focality-pareto", tmp_path)
    config = {**job["config"], "goal": "mean"}
    if kind == "flex_adaptive":
        config["pareto"] = None
    found = verdicts(client, kind, config, job["subject_ids"])
    _refused_everywhere(found, f"mode='{kind}' requires goal='focality'")


def test_a_driver_sweep_with_goal_focality_is_accepted_at_every_door(
    client: TestClient, tmp_path: Path
) -> None:
    """The control for the planted goal: the corpus sweep itself passes every door."""
    job = _corpus_job("optimizer-flex/focality-pareto", tmp_path)
    found = verdicts(client, "flex_pareto", job["config"], job["subject_ids"])
    assert found == {"validate": None, "plan": None, "submit": None}


def test_a_single_flex_run_cannot_lean_on_sweep_settings_for_its_thresholds(
    client: TestClient, tmp_path: Path
) -> None:
    """``kind='flex'`` runs one ROC search: the pareto grid it carries sets no threshold."""
    job = _corpus_job("optimizer-flex/focality-pareto", tmp_path)
    assert job["config"]["thresholds"] is None and job["config"]["pareto"]
    found = verdicts(client, "flex", job["config"], job["subject_ids"])
    _refused_everywhere(found, "requires thresholds")


EX_FOUR = "Add at least four different electrodes to the pool"
MEX_EIGHT = "Add at least eight different electrodes to the pool"


@pytest.mark.parametrize(
    "pool",
    [["E010", "E011", "E012"], ["E010", "E011", "E012", "E010"]],
    ids=["three-labels", "four-entries-three-labels"],
)
def test_an_ex_pool_of_three_labels_is_refused_at_every_door(
    pool: list[str], client: TestClient, tmp_path: Path
) -> None:
    job = _corpus_job("optimizer-ex/pool-mask", tmp_path)
    config = {
        **job["config"],
        "electrodes": {"_type": "PoolElectrodes", "electrodes": pool},
    }
    found = verdicts(client, "ex", config, job["subject_ids"])
    _refused_everywhere(found, EX_FOUR, "has 3")


def test_an_ex_pool_of_four_labels_is_accepted_at_every_door(
    client: TestClient, tmp_path: Path
) -> None:
    job = _corpus_job("optimizer-ex/pool-mask", tmp_path)
    pool = ["E010", "E011", "E012", "E013"]
    config = {
        **job["config"],
        "electrodes": {"_type": "PoolElectrodes", "electrodes": pool},
    }
    found = verdicts(client, "ex", config, job["subject_ids"])
    assert found == {"validate": None, "plan": None, "submit": None}


def test_an_empty_ex_bucket_is_refused_at_every_door(
    client: TestClient, tmp_path: Path
) -> None:
    job = _corpus_job("optimizer-ex/bucketed-saved", tmp_path)
    electrodes = {**job["config"]["electrodes"], "e2_minus": []}
    config = {**job["config"], "electrodes": electrodes}
    found = verdicts(client, "ex", config, job["subject_ids"])
    _refused_everywhere(found, "Fill in every electrode bucket", "e2_minus")


def test_an_mex_pool_of_seven_is_refused_and_of_eight_accepted(
    client: TestClient, tmp_path: Path
) -> None:
    job = _corpus_job("optimizer-ex/mex-saved", tmp_path)
    labels = [f"E0{n}" for n in range(10, 18)]
    seven = {
        **job["config"],
        "electrodes": {"_type": "PoolElectrodes", "electrodes": labels[:7]},
    }
    _refused_everywhere(
        verdicts(client, "mex", seven, job["subject_ids"]), MEX_EIGHT, "has 7"
    )
    eight = {**seven, "electrodes": {"_type": "PoolElectrodes", "electrodes": labels}}
    assert verdicts(client, "mex", eight, job["subject_ids"]) == {
        "validate": None,
        "plan": None,
        "submit": None,
    }


def test_an_empty_mex_bucket_is_refused_at_every_door(
    client: TestClient, tmp_path: Path
) -> None:
    job = _corpus_job("optimizer-ex/mex-saved", tmp_path)
    electrodes = {**job["config"]["electrodes"], "e4_plus": []}
    config = {**job["config"], "electrodes": electrodes}
    found = verdicts(client, "mex", config, job["subject_ids"])
    _refused_everywhere(found, "Fill in all eight electrode buckets", "e4_plus")


def test_the_pre_legacy_key_is_the_one_named_exception(
    client: TestClient, tmp_path: Path
) -> None:
    job = _corpus_job("preprocess/defaults", tmp_path)
    config = {**job["config"], PRE_LEGACY_KEY_EXCEPTION: False}
    found = verdicts(client, "pre", config, job["subject_ids"])
    assert found["plan"] is None and found["submit"] is None, found
    assert (
        found["validate"] is not None and PRE_LEGACY_KEY_EXCEPTION in found["validate"]
    )


# ---------------------------------------------------------------------------------------------
# analyzer field names: refused at the doors exactly when the runner's field selector refuses
# ---------------------------------------------------------------------------------------------

DESKTOP_FIELDS = (
    Path(__file__).resolve().parents[1]
    / "desktop"
    / "src"
    / "renderer"
    / "pages"
    / "analyzer"
    / "fields.ts"
)


def _desktop_field_names() -> list[str]:
    """What the Analyzer page's field selector can send, read from its own source.

    Its ``FIELD_REGISTRY`` entries, plus the alias ``fieldSpecForName`` maps (``mTI_max``,
    which the catalog lists for an mTI simulation and the selector then offers).
    """
    text = DESKTOP_FIELDS.read_text()
    names = re.findall(r'^\s*name: "([^"]+)",$', text, re.M)
    aliases = re.findall(r'if \(name === "([^"]+)"\) return fieldSpec\(', text)
    assert names and aliases, "the desktop field list has names to check"
    return names + aliases


def _analyzer_job(project: Path, field: str) -> dict[str, Any]:
    job = _corpus_job("analyzer/mesh-field-hf-peak", project)
    assert job["config"]["space"] == "mesh"  # TI_normal is a mesh-only field
    job["config"]["field"] = field
    return job


@pytest.mark.parametrize("field", _desktop_field_names())
def test_every_field_the_analyzer_page_offers_is_accepted_at_every_door(
    field: str, client: TestClient, tmp_path: Path
) -> None:
    from tit.analyzer.field_selector import select_field_file

    job = _analyzer_job(tmp_path, field)
    assert verdicts(client, "analyzer", job["config"], job["subject_ids"]) == {
        "validate": None,
        "plan": None,
        "submit": None,
    }
    # The runner's selector takes the name too: with no simulation on disk it gets as far
    # as looking for the file.
    with pytest.raises(FileNotFoundError):
        select_field_file("001", "M1", "mesh", field=field)


@pytest.mark.parametrize("field", ["peak", "TI_banana", "magnE", "ti_max"])
def test_a_field_the_runner_cannot_read_is_refused_at_every_door(
    field: str, client: TestClient, tmp_path: Path
) -> None:
    from tit.analyzer.config import AnalyzerConfig
    from tit.analyzer.field_selector import select_field_file

    # The runner refuses it (the oracle) ...
    with pytest.raises(ValueError, match="Unknown field"):
        select_field_file("001", "M1", "mesh", field=field)
    job = _analyzer_job(tmp_path, field)
    # ... and so do the dataclass and every door, naming it.
    with pytest.raises(ValueError, match=re.escape(repr(field))):
        AnalyzerConfig(**job["config"])
    _refused_everywhere(
        verdicts(client, "analyzer", job["config"], job["subject_ids"]), repr(field)
    )
    v = client.post(
        "/api/validate/analyzer", json={"config": job["config"]}, headers=BEARER
    ).json()
    assert v["errors"][0]["path"] == "field", v
