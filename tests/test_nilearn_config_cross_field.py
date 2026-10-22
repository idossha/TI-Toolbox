"""NilearnConfig refuses a path-like folder, an empty display range and a repeated pair (p35).

What this pins, 2026-10-22: :class:`tit.plotting.nilearn.config.NilearnConfig` refuses, in
``__post_init__`` and so before any job runs,

1. a ``subdir_name`` that is not one folder name. The spec is the panel's help text,
   "Files are saved to derivatives/ti-toolbox/nilearn_visuals/{name}/" -- one folder -- held
   to the project's single-component grammar (:func:`tit.paths.is_valid_name`). Before this,
   ``"../stats"`` and ``"a/b"`` stayed inside the project and passed the runner's
   containment check, so the group average landed in ``derivatives/ti-toolbox/stats/``;
   ``""`` wrote into ``nilearn_visuals/`` itself, which the Results page never lists.
2. ``min_cutoff >= max_cutoff`` when both are given. The independent reference is
   :func:`tit.plotting.nilearn.cutoffs.resolve_cutoffs`, the runner's own rule after the
   data is loaded: every pair the config now refuses is one ``resolve_cutoffs`` refuses for
   any field (checked below on several random fields), so the config only moves the
   refusal earlier and never refuses a run that would have drawn something.
3. the same (subject, simulation) pair twice. The runner's mean is ``sum / len(pairs)``
   (``tit/plotting/nilearn/__main__.py::_average_fields``), so a repeat weights that field
   2/(n+1) instead of 1/n -- arithmetic, no data needed.

``POST /api/validate/nilearn`` answers each case ``ok: false`` with the field it is about,
and ``POST /api/plan/nilearn`` refuses it (422) instead of planning an output folder. The
sentences the desktop gate test mocks (``desktop/tests/unit/nilearn-visuals-gates.test.ts``,
its ``REFUSALS`` table) are read from that file and must be exactly what the real route
says, so the panel test cannot drift from the server.

Reproduce: ``.venv/bin/python -m pytest tests/test_nilearn_config_cross_field.py -q -p no:cacheprovider``.
Deliberately elsewhere: the panel's Run gate (the vitest file above); the cutoff arithmetic
over real fields (``tests/test_nilearn_cutoffs.py``).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

for _mod in ("scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

from tit.config_io import deserialize_config  # noqa: E402
from tit.plotting.nilearn.config import NilearnConfig  # noqa: E402
from tit.plotting.nilearn.cutoffs import resolve_cutoffs  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]
GATES_TEST = REPO / "desktop/tests/unit/nilearn-visuals-gates.test.ts"
TOKEN = "nilearn-cross-field-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


def _config(**overrides) -> dict:
    """A config the panel builds (tests/fixtures/desktop_configs/panels-nilearn/two-pairs.json)."""
    data = {
        "subject_simulation_pairs": [
            {"subject_id": "101", "simulation_name": "L_Insula"},
            {"subject_id": "LA", "simulation_name": "L_Insula"},
        ],
        "min_cutoff": None,
        "max_cutoff": None,
        "atlas_name": "harvard_oxford_sub",
        "selected_regions": None,
        "subdir_name": "insula_group",
        "use_percentiles": False,
        "create_glass_brain": True,
        "glass_brain_cmap": "hot",
    }
    data.update(overrides)
    return data


def _build(**overrides) -> NilearnConfig:
    return deserialize_config(NilearnConfig, _config(**overrides), strict=True)


# ── 1. subdir_name is one folder ────────────────────────────────────────────


@pytest.mark.parametrize("subdir", ["", ".", "..", "a/b", "../stats", "/abs", "a\\b"])
def test_a_subdir_that_is_not_one_folder_is_refused(subdir):
    with pytest.raises(ValueError, match=r"subdir_name") as err:
        _build(subdir_name=subdir)
    assert repr(subdir) in str(err.value)


@pytest.mark.parametrize(
    "subdir", ["insula_group", "nilearn_visuals", "thalamus montage v1", "run-2.b"]
)
def test_a_one_folder_subdir_is_accepted(subdir):
    assert _build(subdir_name=subdir).subdir_name == subdir


# ── 2. the display range is not empty ───────────────────────────────────────

#: (min, max, use_percentiles) pairs, each an empty range by arithmetic alone.
INVERTED = [
    (0.2, 0.1, False),
    (0.1, 0.1, False),
    (99.0, 90.0, True),
    (50.0, 50.0, True),
]
#: Pairs that draw something on a field that reaches them.
ORDERED = [(0.05, 0.15, False), (90.0, 99.0, True), (0.0, 100.0, True)]


@pytest.mark.parametrize("lo,hi,pct", INVERTED)
def test_an_empty_display_range_is_refused_before_any_data(lo, hi, pct):
    with pytest.raises(ValueError, match=r"min_cutoff .* must be below max_cutoff"):
        _build(min_cutoff=lo, max_cutoff=hi, use_percentiles=pct)


@pytest.mark.parametrize("lo,hi,pct", INVERTED)
def test_every_refused_range_is_one_the_runner_refuses_on_any_field(lo, hi, pct):
    # The runner's rule, applied to fields the config never sees: refusing early loses nothing.
    rng = np.random.default_rng(20261022)
    for scale in (0.01, 0.2, 5.0):
        values = rng.gamma(2.0, scale, size=5000)
        with pytest.raises(ValueError, match="display range is empty"):
            resolve_cutoffs(values, lo, hi, use_percentiles=pct)


@pytest.mark.parametrize("lo,hi,pct", ORDERED)
def test_an_ordered_range_is_accepted(lo, hi, pct):
    config = _build(min_cutoff=lo, max_cutoff=hi, use_percentiles=pct)
    assert (config.min_cutoff, config.max_cutoff) == (lo, hi)


@pytest.mark.parametrize("lo,hi", [(0.3, None), (None, 0.01)])
def test_one_given_cutoff_is_left_to_the_data(lo, hi):
    # Only the field can say whether 0.3 V/m is above its p99.9; the runner judges that.
    config = _build(min_cutoff=lo, max_cutoff=hi)
    assert (config.min_cutoff, config.max_cutoff) == (lo, hi)


# ── 3. no pair twice ────────────────────────────────────────────────────────


def test_a_repeated_pair_is_refused_by_name():
    pairs = [
        {"subject_id": "101", "simulation_name": "L_Insula"},
        {"subject_id": "LA", "simulation_name": "L_Insula"},
        {"subject_id": "101", "simulation_name": "L_Insula"},
    ]
    with pytest.raises(ValueError, match=r"sub-101 / L_Insula twice"):
        _build(subject_simulation_pairs=pairs)


def test_the_same_simulation_name_for_two_subjects_and_two_runs_of_one_subject_are_fine():
    pairs = [
        {"subject_id": "101", "simulation_name": "L_Insula"},
        {"subject_id": "LA", "simulation_name": "L_Insula"},
        {"subject_id": "101", "simulation_name": "Thalamus_example"},
    ]
    config = _build(subject_simulation_pairs=pairs)
    assert [
        (p.subject_id, p.simulation_name) for p in config.subject_simulation_pairs
    ] == [tuple(p.values()) for p in pairs]


# ── the server routes, and the sentences the panel test mocks ───────────────

#: case -> the config change the panel would send for it.
CASES = {
    "subdir": {"subdir_name": "../stats"},
    "cutoffs": {"min_cutoff": 0.2, "max_cutoff": 0.1},
    "duplicate": {
        "subject_simulation_pairs": [
            {"subject_id": "101", "simulation_name": "L_Insula"},
            {"subject_id": "101", "simulation_name": "L_Insula"},
        ]
    },
}


def _mocked_refusals() -> dict[str, dict[str, str]]:
    """The ``REFUSALS`` table of the vitest gate file: case -> {path, message}."""
    src = GATES_TEST.read_text()
    block = src.split("const REFUSALS = {", 1)[1].split("};", 1)[0]
    found = {
        case: {"path": path, "message": message}
        for case, path, message in re.findall(
            r'(\w+): \{ path: "([^"]*)", message: "([^"]*)" \}', block
        )
    }
    assert set(found) == set(CASES), f"REFUSALS cases in {GATES_TEST.name}: {found}"
    return found


@pytest.fixture()
def client(init_pm, tmp_project) -> TestClient:
    settings = ServerSettings(project_dir=str(tmp_project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


@pytest.mark.parametrize("case", sorted(CASES))
def test_validate_route_refuses_each_case_with_the_sentence_the_panel_shows(
    client, case
):
    resp = client.post(
        "/api/validate/nilearn",
        json={"config": _config(**CASES[case])},
        headers=BEARER,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["errors"] == [_mocked_refusals()[case]]


@pytest.mark.parametrize("case", sorted(CASES))
def test_plan_route_plans_no_output_folder_for_a_refused_config(client, case):
    resp = client.post(
        "/api/plan/nilearn",
        json={"config": _config(**CASES[case]), "subject_ids": ["101"]},
        headers=BEARER,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == _mocked_refusals()[case]["message"]


def test_the_valid_config_validates_and_plans_one_folder_under_nilearn_visuals(
    client, tmp_project
):
    resp = client.post(
        "/api/validate/nilearn", json={"config": _config()}, headers=BEARER
    )
    assert resp.json() == {"ok": True, "errors": []}
    plan = client.post(
        "/api/plan/nilearn",
        json={"config": _config(), "subject_ids": ["101", "LA"]},
        headers=BEARER,
    )
    assert plan.status_code == 200, plan.text
    [job] = plan.json()["jobs"]
    assert Path(job["output_dir"]) == (
        Path(tmp_project) / "derivatives/ti-toolbox/nilearn_visuals/insula_group"
    )
