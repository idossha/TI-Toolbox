"""Every config a desktop page builds is accepted by the server exactly when the page accepts it.

What this pins: for each case in ``tests/fixtures/desktop_configs/<page>/<case>.json`` (written by
the REAL desktop builders and page gates in ``desktop/tests/unit/desktop-config-corpus.test.ts``),
the server's verdict equals the page's ``desktop.accepts``. The server's verdict is the
conjunction of every check a submission meets before a runner starts:

1. ``tit.jobs.config_check.check_job_config`` (the submit-time guard of ``POST /api/jobs``);
2. ``tit.config_io.deserialize_config(cls_for(kind), config, strict=True)`` -- the dataclass
   ``__post_init__`` rules, which are the spec;
3. ``POST /api/validate/{kind}`` returns ``ok: true``;
4. ``POST /api/plan/{kind}`` returns 200 with at least one job, every ``output_dir`` inside the
   project (a plan that resolves to nothing would run nothing).

Where the expected values come from: the page side is the committed fixture (the TypeScript wrote
it); the server side is computed here by the real validators, never retyped. Disagreements found
on 2026-10-22 are listed one file each in ``tests/fixtures/desktop_configs/known_gaps/`` with the
package that owns the fix; those cases are ``xfail(strict=True)`` so that a fix turns them red
until the gap file is deleted.

Paths in the corpus sit under the placeholder root ``/corpus/project``; each test maps it onto a
synthetic tmp project (m2m folders, empty files for every path the config names), the same way
``tests/test_plan_routes.py`` builds its project.

Reproduce: ``.venv/bin/python -m pytest tests/test_desktop_config_corpus.py -q -p no:cacheprovider``
Regenerate the corpus: ``cd desktop && UPDATE_DESKTOP_CONFIGS=1 npx vitest run
tests/unit/desktop-config-corpus.test.ts``. Runner dispatch of the accepted cases is
``tests/test_runner_dispatch_replay.py``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

# kind="stats"/"nifti_average"/"nilearn" import tit.stats, which eagerly imports scipy.ndimage /
# scipy.stats (not in tests/conftest.py's mocks) -- the same local fallback test_plan_routes.py uses.
for _mod in ("scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

from tit.config_io import deserialize_config  # noqa: E402
from tit.jobs.config_check import check_job_config  # noqa: E402
from tit.paths import get_path_manager, is_within  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.routes.validate import ENVELOPE_KEYS, cls_for  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

CORPUS = Path(__file__).parent / "fixtures" / "desktop_configs"
PLACEHOLDER = "/corpus/project"
PAGES = (
    "simulator",
    "optimizer-flex",
    "optimizer-ex",
    "analyzer",
    "preprocess",
    "panels-stats",
    "panels-nifti",
    "panels-nilearn",
    "visual-exporter",
)
TOKEN = "corpus-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
#: Extensions of the input files a config may name (masks, atlases, leadfields).
_INPUT_SUFFIXES = (".nii", ".nii.gz", ".hdf5", ".annot", ".mgz", ".csv")


def _case_files() -> list[Path]:
    return sorted(p for page in PAGES for p in (CORPUS / page).glob("*.json"))


def _known_gaps() -> dict[str, list[dict[str, Any]]]:
    """case id -> the known-gap records naming it."""
    gaps: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((CORPUS / "known_gaps").glob("*.json")):
        gap = json.loads(path.read_text())
        gap["file"] = path.name
        for case_id in gap["case_ids"]:
            gaps.setdefault(case_id, []).append(gap)
    return gaps


def known_gap_marks(case_id: str, check: str) -> list[pytest.MarkDecorator]:
    """``xfail(strict=True)`` for a case a known-gap file lists under *check*."""
    for gap in _known_gaps().get(case_id, []):
        if check in gap["checks"]:
            return [
                pytest.mark.xfail(
                    strict=True,
                    reason=f"known gap {gap['file']} (owner {gap['owner']}): {gap['reason']}",
                )
            ]
    return []


def load_case(path: Path, project: Path) -> dict[str, Any]:
    """The case with the placeholder root mapped onto *project*."""
    return json.loads(path.read_text().replace(PLACEHOLDER, str(project)))


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def make_project(root: Path, case: dict[str, Any]) -> None:
    """A synthetic project: three subjects' m2m folders and every input file the case names."""
    pm = get_path_manager(str(root))
    for sid in ("001", "002", "003"):
        os.makedirs(pm.m2m(sid), exist_ok=True)
    (root / "dataset_description.json").write_text("{}")
    for text in _strings(case["jobs"]):
        if text.startswith(str(root)) and text.endswith(_INPUT_SUFFIXES):
            Path(text).parent.mkdir(parents=True, exist_ok=True)
            Path(text).touch()


def server_verdict(
    client: TestClient, project: Path, jobs: list[dict[str, Any]]
) -> str | None:
    """``None`` when every server-side check accepts every job, else the first refusal."""
    for job in jobs:
        kind, config = job["kind"], job["config"]
        try:
            check_job_config(kind, config)
        except ValueError as exc:
            return f"check_job_config: {exc}"
        cls = cls_for(kind, config)
        body = {k: v for k, v in config.items() if k not in ENVELOPE_KEYS}
        try:
            deserialize_config(cls, body, strict=True)
        except (ValueError, TypeError, KeyError) as exc:
            return f"deserialize_config(strict=True): {exc}"
        resp = client.post(
            f"/api/validate/{kind}", json={"config": config}, headers=BEARER
        )
        assert resp.status_code == 200, resp.text
        if not resp.json()["ok"]:
            return f"/api/validate: {resp.json()['errors']}"
        resp = client.post(
            f"/api/plan/{kind}",
            json={"config": config, "subject_ids": job["subject_ids"]},
            headers=BEARER,
        )
        if resp.status_code != 200:
            return f"/api/plan {resp.status_code}: {resp.json().get('detail')}"
        planned = resp.json()["jobs"]
        if not planned:
            return "/api/plan resolves to no job"
        outside = [
            j["output_dir"]
            for j in planned
            if not is_within(str(project), j["output_dir"])
        ]
        if outside:
            return f"/api/plan output_dir outside the project: {outside}"
    return None


def _client(project: Path) -> TestClient:
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def _params(check: str) -> list:
    return [
        pytest.param(
            path,
            id=f"{path.parent.name}/{path.stem}",
            marks=known_gap_marks(f"{path.parent.name}/{path.stem}", check),
        )
        for path in _case_files()
    ]


@pytest.mark.parametrize("path", _params("verdict"))
def test_server_accepts_exactly_what_the_page_accepts(
    path: Path, tmp_path: Path
) -> None:
    case = load_case(path, tmp_path)
    make_project(tmp_path, case)
    refusal = server_verdict(_client(tmp_path), tmp_path, case["jobs"])
    desktop = case["desktop"]
    assert (refusal is None) == desktop["accepts"], (
        f"{case['id']}: page {'accepts' if desktop['accepts'] else 'refuses'} "
        f"({desktop['reason']}); server {'accepts' if refusal is None else 'refuses'}"
        f" ({refusal})"
    )


def test_the_validators_are_live_on_this_host(tmp_path: Path) -> None:
    """Canary: a config Python must refuse IS refused at every layer.

    ``check_job_config`` returns silently when the config class cannot be imported, which would
    make every verdict above an "accept". A 1-pair montage (``SimulationConfig`` needs 2, or an
    even count from 4: ``tit.constants.is_valid_pair_count``) proves each layer really ran.
    """
    config = {
        "subject_id": "001",
        "montages": [
            {
                "_type": "Montage",
                "name": "one_pair",
                "mode": "net",
                "electrode_pairs": [["E1", "E2"]],
                "eeg_net": "GSN-HydroCel-185.csv",
            }
        ],
        "intensities": [1.0, 1.0],
    }
    with pytest.raises(ValueError, match="SimulationConfig"):
        check_job_config("sim", config)
    with pytest.raises(ValueError):
        deserialize_config(cls_for("sim", config), config, strict=True)
    case = {"jobs": [{"kind": "sim", "subject_ids": ["001"], "config": config}]}
    make_project(tmp_path, case)
    refusal = server_verdict(_client(tmp_path), tmp_path, case["jobs"])
    assert refusal is not None and refusal.startswith("check_job_config")


def test_every_page_has_cases_and_both_verdicts_occur() -> None:
    files = _case_files()
    pages = {p.parent.name for p in files}
    assert pages == set(PAGES), f"pages without corpus cases: {set(PAGES) - pages}"
    verdicts = {json.loads(p.read_text())["desktop"]["accepts"] for p in files}
    # A corpus where the page accepts everything cannot show a refusal agrees with the server.
    assert verdicts == {True, False}
    assert len(files) >= 60


def test_known_gap_files_name_real_cases_and_an_owner() -> None:
    files = sorted((CORPUS / "known_gaps").glob("*.json"))
    assert files, "known gaps to check"
    ids = {f"{p.parent.name}/{p.stem}" for p in _case_files()}
    for path in files:
        gap = json.loads(path.read_text())
        assert set(gap) == {"case_ids", "owner", "reason", "checks"}, path.name
        assert gap["case_ids"] and set(gap["case_ids"]) <= ids, path.name
        assert gap["checks"] and set(gap["checks"]) <= {"verdict", "dispatch"}
        assert gap["owner"] == "triage" or (
            gap["owner"].startswith("p") and gap["owner"][1:].isdigit()
        ), path.name
        assert path.name.startswith(gap["case_ids"][0].split("/")[0] + "-")
