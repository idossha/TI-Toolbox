"""Stats configs refuse numbers that crash late or cannot give a meaningful result (p23).

What this pins: ``GroupComparisonConfig`` / ``CorrelationConfig`` (``tit/stats/config.py``)
refuse each case below in ``__post_init__``, so ``deserialize_config(strict=True)`` raises and
``POST /api/validate/stats`` answers ``ok: false`` with the field the error is about. Before
this, every case was accepted and either crashed in the engine (``n_permutations=0``:
``IndexError`` taking the null quantile), silently dropped a subject from both groups
(``response=2``), reported a threshold no p-value could reach (5 permutations at alpha 0.05)
or "succeeded" with zero clusters (constant effect sizes: ``r = 0/0``).

Where the expected values come from, never from the code under test:

- The permutation floor. A permutation p-value is ``(b + 1) / (m + 1)`` (Phipson & Smyth 2010,
  "Permutation p-values should never be zero"), so the smallest attainable p is ``1/(m + 1)``,
  and the engine calls a cluster significant only when ``p < alpha`` (strict; ``engine.py``
  ``_identify_significant_clusters`` and ``surface.py`` alike). So a result needs
  ``1/(m + 1) < alpha``. By hand: alpha 0.05 -> m >= 20 (1/21 = 0.0476; 19 gives exactly
  1/20 = 0.05, which is not below 0.05); alpha 0.01 -> m >= 100; alpha 0.2 -> m >= 5 (1/6;
  4 gives 1/5 = 0.2); alpha 0.03 -> m >= 33 (1/34 = 0.0294; 32 gives 1/33 = 0.0303).
- Numbers from numpy (a pandas column, a notebook) are numbers: ``np.int64``/``np.float32``
  effect sizes and an ``np.int64`` permutation count are accepted like ``int``/``float``, and a
  whole-valued float count (``1000.0``, what a JSON writer can emit) is the integer 1000.
- Probabilities (alpha, the cluster-forming p threshold) lie strictly between 0 and 1.
- Response is the 0/1 group label the dataclass documents; a paired t-test pairs one
  responder with one non-responder, so both groups need the same size.
- Pearson/Spearman r is ``cov(x, y) / (sd_x * sd_y)``: undefined when every effect size is
  equal (sd_y = 0). Weights are relative frequencies: positive and finite.

Reproduce: ``.venv/bin/python -m pytest tests/test_stats_config_validation.py -q -p no:cacheprovider``.
Deliberately elsewhere: the desktop gate that blocks the same cases before a request
(``desktop/tests/unit/cluster-permutation-gates.test.tsx``), the corpus agreement
(``tests/test_desktop_config_corpus.py``). Dated 2026-10-22.
"""

from __future__ import annotations

import copy
import json
import math
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

# /api/validate/stats resolves tit.stats.config through tit.stats, which imports scipy.ndimage
# / scipy.stats eagerly (not in tests/conftest.py's mocks) -- the fallback the corpus test uses.
for _mod in ("scipy.ndimage", "scipy.stats"):
    sys.modules.setdefault(_mod, MagicMock())

from fastapi.testclient import TestClient  # noqa: E402

from tit.config_io import deserialize_config  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402
from tit.stats.config import CorrelationConfig, GroupComparisonConfig  # noqa: E402

TOKEN = "stats-validation-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


def _comparison(**overrides) -> dict:
    data = {
        "_type": "GroupComparisonConfig",
        "analysis_name": "validation",
        "subjects": [
            {"subject_id": "001", "simulation_name": "M1", "response": 1},
            {"subject_id": "002", "simulation_name": "M1", "response": 1},
            {"subject_id": "003", "simulation_name": "M1", "response": 0},
            {"subject_id": "004", "simulation_name": "M1", "response": 0},
        ],
    }
    data.update(overrides)
    return data


def _correlation(**overrides) -> dict:
    data = {
        "_type": "CorrelationConfig",
        "analysis_name": "validation",
        "subjects": [
            {"subject_id": "001", "simulation_name": "M1", "effect_size": 0.4},
            {"subject_id": "002", "simulation_name": "M1", "effect_size": 1.2},
            {"subject_id": "003", "simulation_name": "M1", "effect_size": -0.3},
            {"subject_id": "004", "simulation_name": "M1", "effect_size": 2.0},
        ],
    }
    data.update(overrides)
    return data


def _with_subject(data: dict, index: int, **fields) -> dict:
    out = copy.deepcopy(data)
    out["subjects"][index].update(fields)
    return out


def _cls(data: dict) -> type:
    return (
        CorrelationConfig
        if data["_type"] == "CorrelationConfig"
        else GroupComparisonConfig
    )


def _build(data: dict):
    body = {k: v for k, v in data.items() if k != "_type"}
    return deserialize_config(_cls(data), body, strict=True)


# (case id, config, the field the error is about, a phrase the message must carry)
REFUSED = [
    (
        "zero-permutations",
        _comparison(n_permutations=0),
        "n_permutations",
        "at least 20",
    ),
    (
        "negative-permutations",
        _comparison(n_permutations=-5),
        "n_permutations",
        "at least 20",
    ),
    (
        "5-perms-at-alpha-0.05",
        _comparison(n_permutations=5),
        "n_permutations",
        "at least 20",
    ),
    (
        "19-perms-at-alpha-0.05",
        _comparison(n_permutations=19),
        "n_permutations",
        "at least 20",
    ),
    (
        "99-perms-at-alpha-0.01",
        _comparison(n_permutations=99, alpha=0.01),
        "n_permutations",
        "at least 100",
    ),
    (
        "9-perms-at-alpha-0.1",
        _correlation(n_permutations=9, alpha=0.1),
        "n_permutations",
        "at least 10",
    ),
    (
        "4-perms-at-alpha-0.2",
        _correlation(n_permutations=4, alpha=0.2),
        "n_permutations",
        "at least 5",
    ),
    (
        "32-perms-at-alpha-0.03",
        _comparison(n_permutations=32, alpha=0.03),
        "n_permutations",
        "at least 33",
    ),
    (
        "fractional-permutations",
        _comparison(n_permutations=100.5),
        "n_permutations",
        "whole number",
    ),
    ("alpha-2", _comparison(alpha=2.0), "alpha", "between 0 and 1"),
    ("alpha-0", _comparison(alpha=0.0), "alpha", "between 0 and 1"),
    ("alpha-1", _correlation(alpha=1.0), "alpha", "between 0 and 1"),
    ("alpha-nan", _comparison(alpha=math.nan), "alpha", "between 0 and 1"),
    (
        "threshold-negative",
        _comparison(cluster_threshold=-1),
        "cluster_threshold",
        "between 0 and 1",
    ),
    (
        "threshold-1",
        _correlation(cluster_threshold=1.0),
        "cluster_threshold",
        "between 0 and 1",
    ),
    (
        "threshold-0",
        _comparison(cluster_threshold=0),
        "cluster_threshold",
        "between 0 and 1",
    ),
    (
        "response-2",
        _with_subject(_comparison(), 3, response=2),
        "subjects",
        "subjects[3]",
    ),
    (
        "response-minus-1",
        _with_subject(_comparison(), 0, response=-1),
        "subjects",
        "subjects[0]",
    ),
    (
        "paired-2v1",
        {**_comparison(test_type="paired"), "subjects": _comparison()["subjects"][:3]},
        "test_type",
        "got 2 responders and 1 non-responder",
    ),
    (
        "effect-null",
        _with_subject(_correlation(), 1, effect_size=None),
        "subjects",
        "subjects[1]",
    ),
    (
        "effect-nan",
        _with_subject(_correlation(), 2, effect_size=math.nan),
        "subjects",
        "subjects[2]",
    ),
    (
        "effect-inf",
        _with_subject(_correlation(), 0, effect_size=math.inf),
        "subjects",
        "subjects[0]",
    ),
    (
        "effect-constant",
        _correlation(
            subjects=[
                {"subject_id": sid, "simulation_name": "M1", "effect_size": 2.0}
                for sid in ("001", "002", "003")
            ]
        ),
        "subjects",
        "same effect size",
    ),
    ("weight-0", _with_subject(_correlation(), 2, weight=0), "subjects", "subjects[2]"),
    (
        "weight-negative",
        _with_subject(_correlation(), 1, weight=-2),
        "subjects",
        "subjects[1]",
    ),
    (
        "weight-inf",
        _with_subject(_correlation(), 3, weight=math.inf),
        "subjects",
        "subjects[3]",
    ),
]

#: Neighbours of the refused cases that are valid: the smallest count whose minimum p is below
#: alpha, a paired test with equal groups, and weights that are switched off are never read.
ACCEPTED = [
    ("20-perms-at-alpha-0.05", _comparison(n_permutations=20)),
    ("100-perms-at-alpha-0.01", _correlation(n_permutations=100, alpha=0.01)),
    ("5-perms-at-alpha-0.2", _comparison(n_permutations=5, alpha=0.2)),
    ("33-perms-at-alpha-0.03", _correlation(n_permutations=33, alpha=0.03)),
    ("paired-2v2", _comparison(test_type="paired")),
    (
        "weight-0-unused",
        {**_with_subject(_correlation(), 2, weight=0), "use_weights": False},
    ),
    ("two-distinct-effects", _with_subject(_correlation(), 0, effect_size=1.2)),
]


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> TestClient:
    project = tmp_path_factory.mktemp("project")
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


@pytest.mark.parametrize(
    "data,field,phrase",
    [pytest.param(d, f, p, id=i) for i, d, f, p in REFUSED],
)
def test_the_dataclass_refuses(data: dict, field: str, phrase: str) -> None:
    with pytest.raises(ValueError) as err:
        _build(data)
    assert phrase in str(err.value)


@pytest.mark.parametrize(
    "data,field,phrase",
    [pytest.param(d, f, p, id=i) for i, d, f, p in REFUSED],
)
def test_validate_route_refuses_with_the_field(
    client: TestClient, data: dict, field: str, phrase: str
) -> None:
    # Raw JSON text: a NaN or Infinity is what a non-strict JSON writer (Python's own) sends.
    resp = client.post(
        "/api/validate/stats",
        content=json.dumps({"config": data}),
        headers={**BEARER, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert [e["path"] for e in body["errors"]] == [field]
    assert phrase in body["errors"][0]["message"]


@pytest.mark.parametrize("data", [pytest.param(d, id=i) for i, d in ACCEPTED])
def test_valid_neighbours_are_accepted(client: TestClient, data: dict) -> None:
    config = _build(data)
    assert config.n_permutations == data.get("n_permutations", 1000)
    resp = client.post("/api/validate/stats", json={"config": data}, headers=BEARER)
    assert resp.json() == {"ok": True, "errors": []}


#: (alpha, the fewest permutations whose smallest p-value 1/(m + 1) is below alpha), by hand.
FLOOR_BY_HAND = [
    (0.05, 20),
    (0.01, 100),
    (0.1, 10),
    (0.2, 5),
    (0.5, 2),
    (0.001, 1000),
    (0.03, 33),
    (0.3, 3),
]


@pytest.mark.parametrize("alpha,m_hand", FLOOR_BY_HAND)
def test_the_floor_is_the_smallest_count_whose_minimum_p_is_below_alpha(
    alpha: float, m_hand: int
) -> None:
    """The hand value is the true minimum, the config agrees, and so does the engine's p."""
    from tit.stats.engine import pval_from_histogram

    assert 1 / (m_hand + 1) < alpha <= 1 / m_hand
    _build(_comparison(alpha=alpha, n_permutations=m_hand))
    with pytest.raises(ValueError, match=f"at least {m_hand} "):
        _build(_comparison(alpha=alpha, n_permutations=m_hand - 1))

    # The engine's own p-value for a cluster beyond every permutation (b = 0), held to the
    # engine's strict ``p < alpha``: reachable at the floor, unreachable one below it.
    def smallest_p(m: int) -> float:
        return float(pval_from_histogram([10.0], np.zeros(m), tail=1)[0])

    assert smallest_p(m_hand) < alpha
    assert not smallest_p(m_hand - 1) < alpha


def test_numpy_numbers_are_numbers() -> None:
    """A notebook's ``df.score[i]`` (np.int64 / np.float32) is an effect size like a float."""
    subjects = [
        CorrelationConfig.Subject("001", "M1", effect_size=np.int64(1)),
        CorrelationConfig.Subject("002", "M1", effect_size=np.float32(2.5)),
        CorrelationConfig.Subject("003", "M1", effect_size=np.float64(-0.5)),
        CorrelationConfig.Subject("004", "M1", effect_size=4, weight=np.float32(0.5)),
    ]
    config = CorrelationConfig(
        analysis_name="numpy",
        subjects=subjects,
        n_permutations=np.int64(200),
        alpha=np.float64(0.05),
        cluster_threshold=np.float32(0.01),
    )
    assert config.n_permutations == 200 and type(config.n_permutations) is int

    comparison = GroupComparisonConfig(
        analysis_name="numpy",
        subjects=[
            GroupComparisonConfig.Subject("001", "M1", response=np.int64(1)),
            GroupComparisonConfig.Subject("002", "M1", response=np.int64(0)),
        ],
        n_permutations=1000.0,  # a whole-valued float, as a JSON writer may send it
    )
    assert comparison.n_permutations == 1000 and type(comparison.n_permutations) is int


@pytest.mark.parametrize(
    "value",
    [np.float64(np.nan), np.float32(np.inf), np.bool_(True), True],
    ids=["np-nan", "np-inf", "np-bool", "bool"],
)
def test_a_numpy_non_number_is_still_refused(value) -> None:
    subjects = [
        {"subject_id": sid, "simulation_name": "M1", "effect_size": e}
        for sid, e in (("001", 0.4), ("002", 1.2), ("003", -0.3))
    ]
    subjects[1]["effect_size"] = value
    with pytest.raises(ValueError, match=r"subjects\[1\] effect size"):
        CorrelationConfig(
            analysis_name="numpy",
            subjects=[CorrelationConfig.Subject(**s) for s in subjects],
        )


@pytest.mark.parametrize(
    "value",
    [np.float64(1000.5), np.bool_(True), "1000"],
    ids=["np-frac", "np-bool", "text"],
)
def test_a_count_that_is_not_a_whole_number_is_refused(value) -> None:
    with pytest.raises(ValueError, match="n_permutations must be a whole number"):
        _build(_comparison(n_permutations=value))
