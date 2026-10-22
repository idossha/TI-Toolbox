"""Montage and free-hand writes refuse what the contract and the simulator refuse.

What this pins (p15, 2026-10-22)
--------------------------------
``PUT /api/catalog/montages/{net}/{kind}/{name}`` saved ``[["E1","E1"],["E2"],["E3","E4","E5"]]``
with a 200, and ``PUT /api/catalog/freehand/{name}`` saved ``type: "Q"``, ``"nan"``/``"inf"``
coordinates (``json.dump`` wrote ``NaN``/``Infinity`` tokens) and electrode counts no montage can
be built from. Every such body must now answer 422 and leave the files exactly as they were
(byte compare), while a valid body still round-trips through GET.

Where the expected values come from
-----------------------------------
* ``contracts/openapi.yaml``: ``MontagePairs`` items are arrays of exactly two labels;
  ``FreehandConfig.type`` is ``[U, M]``; ``ElectrodePosition.x/y/z`` are numbers (JSON has no
  NaN or infinity).
* The pair-count rule, written in ``upsert_montage``'s docstring and
  ``tit.constants.is_valid_pair_count``: uni-polar is 2 pairs (TI), multi-polar an even number
  from 4 (mTI), at most 26 (mTI's A-Z channel names).
* Electrode physics, as the Simulator applies it (``desktop/.../simulator/types.ts``): an
  electrode is used once in a montage and two electrodes are at least 1 mm apart.
* Free-hand positions are paired consecutively (``resolve_freehand_montage``): 4 for U,
  8, 12, ... for M.

Reproduce: ``.venv/bin/python -m pytest tests/test_catalog_write_validation.py -q -p no:cacheprovider``
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

TOKEN = "test-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
NET = "GSN-HydroCel-185.csv"
SEED = {
    "nets": {
        NET: {
            "uni_polar_montages": {"L_Insula": [["E001", "E002"], ["E003", "E004"]]},
            "multi_polar_montages": {},
        }
    }
}


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    pm = get_path_manager(str(tmp_path))
    os.makedirs(pm.m2m("ernie"))
    os.makedirs(pm.config_dir())
    Path(pm.config_dir(), "montage_list.json").write_text(json.dumps(SEED))
    stim = Path(pm.m2m("ernie"), "stim_configs")
    stim.mkdir()
    (stim / "kept.json").write_text('{"name": "kept"}')
    return tmp_path


@pytest.fixture()
def client(project: Path, tmp_path_factory, monkeypatch) -> TestClient:
    telemetry_file = tmp_path_factory.mktemp("telemetry") / "telemetry.json"
    monkeypatch.setattr("tit.telemetry._config_path", lambda: telemetry_file)
    monkeypatch.setattr("tit.telemetry._cached_config", None)
    settings = ServerSettings(project_dir=str(project), token=TOKEN)
    return TestClient(create_app(settings), base_url="http://127.0.0.1:8765")


def _montage_file() -> bytes:
    return Path(get_path_manager().config_dir(), "montage_list.json").read_bytes()


def _stim_files() -> dict[str, bytes]:
    stim = Path(get_path_manager().m2m("ernie"), "stim_configs")
    return {p.name: p.read_bytes() for p in stim.iterdir()}


def _labels(n_pairs: int) -> list[list[str]]:
    return [[f"E{2 * i + 1:03d}", f"E{2 * i + 2:03d}"] for i in range(n_pairs)]


BAD_MONTAGES = [
    ("uni_polar", [], "no pairs"),
    ("uni_polar", [["E1", "E2"]], "one pair is tACS, not TI"),
    ("uni_polar", _labels(3), "odd pair count"),
    ("multi_polar", _labels(3), "odd pair count"),
    ("multi_polar", _labels(5), "odd pair count"),
    ("uni_polar", _labels(4), "4 pairs are mTI, not uni-polar"),
    ("multi_polar", _labels(2), "2 pairs are TI, not multi-polar"),
    ("multi_polar", _labels(28), "more pairs than A-Z channel names"),
    ("uni_polar", [["E1", "E1"], ["E2", "E3"]], "an electrode as its own return"),
    ("uni_polar", [["E1", "E2"], ["E1", "E3"]], "two channels on one electrode"),
    ("uni_polar", [["E1"], ["E2", "E3"]], "a pair of one"),
    ("uni_polar", [["E1", "E2", "E3"], ["E4", "E5"]], "a pair of three"),
    ("uni_polar", ["E1E2", "E3E4"], "a pair that is a string"),
    ("uni_polar", [[1, 2], [3, 4]], "labels that are not strings"),
    ("uni_polar", [["", "E2"], ["E3", "E4"]], "an empty label"),
]


@pytest.mark.parametrize(
    "kind, pairs, why", BAD_MONTAGES, ids=[b[2] for b in BAD_MONTAGES]
)
def test_an_invalid_montage_is_refused_and_nothing_is_written(
    client: TestClient, kind: str, pairs, why: str
) -> None:
    before = _montage_file()
    r = client.put(
        f"/api/catalog/montages/{NET}/{kind}/Junk",
        json={"pairs": pairs},
        headers=BEARER,
    )
    assert r.status_code == 422, why
    assert _montage_file() == before
    listed = client.get("/api/catalog/montages", headers=BEARER).json()
    assert listed == {
        "nets": {
            NET: {
                "uni_polar": SEED["nets"][NET]["uni_polar_montages"],
                "multi_polar": {},
            }
        }
    }


@pytest.mark.parametrize(
    "kind, n_pairs", [("uni_polar", 2), ("multi_polar", 4), ("multi_polar", 26)]
)
def test_a_valid_montage_round_trips(client: TestClient, kind: str, n_pairs: int):
    pairs = _labels(n_pairs)
    r = client.put(
        f"/api/catalog/montages/{NET}/{kind}/Good",
        json={"pairs": pairs},
        headers=BEARER,
    )
    assert r.status_code == 200
    assert r.json() == pairs
    listed = client.get("/api/catalog/montages", headers=BEARER).json()
    assert listed["nets"][NET][kind]["Good"] == pairs


def test_the_python_writer_applies_the_same_rules() -> None:
    """``catalog.put_montage`` itself refuses (the route is not the only caller)."""
    from tit import catalog

    pm = get_path_manager()
    with pytest.raises(ValueError, match="more than once"):
        catalog.put_montage(pm, NET, "uni_polar", "X", [["E1", "E1"], ["E2", "E3"]])
    with pytest.raises(ValueError, match="uni_polar"):
        catalog.put_montage(pm, NET, "uni_polar", "X", _labels(4))


@pytest.mark.parametrize("kind", ["bipolar", "Multi_polar", "M", ""])
def test_the_python_writer_refuses_a_kind_outside_the_two_buckets(
    project: Path, kind: str
) -> None:
    """The route checks ``kind`` before calling it; a script calling ``put_montage`` does not.

    Four pairs, so the uni-polar-is-2-pairs rule cannot be what refuses it: without the enum,
    ``"bipolar"`` would be filed as multi-polar.
    """
    from tit import catalog

    before = _montage_file()
    with pytest.raises(ValueError, match="kind must be uni_polar or multi_polar"):
        catalog.put_montage(get_path_manager(), NET, kind, "X", _labels(4))
    assert _montage_file() == before


def test_saving_a_name_under_the_other_polarity_moves_it_instead_of_keeping_both(
    client: TestClient,
) -> None:
    """One montage name is one ``Simulations/<name>/`` folder, and ``load_montages`` refuses a
    name saved under both polarities, so a PUT replaces the montage whichever bucket held it.

    The Simulator's editor deletes the old bucket's entry in a request that races this PUT;
    the server must not depend on which one lands first. A same-named montage of another net
    is a different montage and is left alone.
    """
    from tit.sim.utils import load_montages

    other = "EEG10-10_UI_Jurak_2007.csv"
    two, four = _labels(2), _labels(4)
    assert (
        client.put(
            f"/api/catalog/montages/{other}/uni_polar/L_Insula",
            json={"pairs": two},
            headers=BEARER,
        ).status_code
        == 200
    )
    r = client.put(
        f"/api/catalog/montages/{NET}/multi_polar/L_Insula",
        json={"pairs": four},
        headers=BEARER,
    )
    assert r.status_code == 200
    listed = client.get("/api/catalog/montages", headers=BEARER).json()
    assert listed == {
        "nets": {
            NET: {"uni_polar": {}, "multi_polar": {"L_Insula": four}},
            other: {"uni_polar": {"L_Insula": two}, "multi_polar": {}},
        }
    }
    (montage,) = load_montages(["L_Insula"], NET, include_flex=False)
    assert [list(pair) for pair in montage.electrode_pairs] == four

    # And back: a multi-polar name saved as uni-polar leaves the multi-polar bucket.
    r = client.put(
        f"/api/catalog/montages/{NET}/uni_polar/L_Insula",
        json={"pairs": two},
        headers=BEARER,
    )
    assert r.status_code == 200
    listed = client.get("/api/catalog/montages", headers=BEARER).json()
    assert listed["nets"][NET] == {"uni_polar": {"L_Insula": two}, "multi_polar": {}}


# ── free-hand ────────────────────────────────────────────────────────────────

_SQUARE = [
    (-60.0, 10.0, 40.0),
    (60.0, 10.0, 40.0),
    (-60.0, -40.0, 40.0),
    (60.0, -40.0, 40.0),
]


def _positions(n: int) -> list[dict]:
    """*n* distinct points, 10 mm apart along x at two heights (well over 1 mm)."""
    return [
        {"label": f"P{i + 1}", "x": 10.0 * i - 40.0, "y": 0.0, "z": 50.0 + i % 2}
        for i in range(n)
    ]


def _square() -> list[dict]:
    return [
        {"label": f"P{i + 1}", "x": x, "y": y, "z": z}
        for i, (x, y, z) in enumerate(_SQUARE)
    ]


def _with(position: int, **coords) -> list[dict]:
    rows = _square()
    rows[position].update(coords)
    return rows


BAD_FREEHAND = [
    ({"type": "Q", "electrode_positions": _square()}, "type outside [U, M]"),
    ({"type": "U", "electrode_positions": _with(0, x="nan")}, "x 'nan'"),
    ({"type": "U", "electrode_positions": _with(1, y="inf")}, "y 'inf'"),
    ({"type": "U", "electrode_positions": _with(2, z="-inf")}, "z '-inf'"),
    ({"type": "U", "electrode_positions": _with(3, x="1e309")}, "x overflows to inf"),
    ({"type": "U", "electrode_positions": _positions(6)}, "6 positions"),
    ({"type": "M", "electrode_positions": _positions(6)}, "6 positions as M"),
    ({"type": "U", "electrode_positions": _positions(2)}, "one pair"),
    ({"type": "U", "electrode_positions": []}, "no positions"),
    ({"type": "U", "electrode_positions": _positions(8)}, "8 positions are M"),
    ({"type": "M", "electrode_positions": _square()}, "4 positions are U"),
    ({"type": "M", "electrode_positions": _positions(10)}, "5 pairs"),
    # An odd count leaves the last electrode without a partner: pairing consecutively would
    # drop it without a word (5 as M looks like 2 pairs, 9 like 4).
    ({"type": "M", "electrode_positions": _positions(5)}, "5 positions as M"),
    ({"type": "M", "electrode_positions": _positions(7)}, "7 positions as M"),
    ({"type": "M", "electrode_positions": _positions(9)}, "9 positions as M"),
    ({"type": "U", "electrode_positions": _positions(5)}, "5 positions as U"),
    # The enum on its own: an M-sized placement under a type outside [U, M].
    ({"type": "Q", "electrode_positions": _positions(8)}, "type 'Q' with 8 positions"),
    (
        {"type": "m", "electrode_positions": _positions(8)},
        "type 'm' (the enum is U, M)",
    ),
    ({"type": None, "electrode_positions": _positions(8)}, "type null"),
    ({"type": ["M"], "electrode_positions": _positions(8)}, "type a list"),
    # ElectrodePosition.label is a string; a number would be written as a JSON key "7" and
    # read back as text, so the listing would not equal the write.
    (
        {
            "type": "U",
            "electrode_positions": [{**row, "label": 5} for row in _square()],
        },
        "a numeric label four times",
    ),
    (
        {
            "type": "U",
            "electrode_positions": [
                {**row, "label": 7} if i == 0 else row
                for i, row in enumerate(_square())
            ],
        },
        "one numeric label",
    ),
    (
        {
            "type": "U",
            "electrode_positions": [
                {"label": f"P{i}", "x": 0, "y": 0, "z": 0} for i in range(4)
            ],
        },
        "four never-placed rows at the origin",
    ),
    (
        {"type": "U", "electrode_positions": _with(3, x=-59.5, y=10.0, z=40.0)},
        "electrodes 1 and 4 half a millimetre apart",
    ),
    ({"type": "U", "electrode_positions": "P1"}, "positions not a list"),
]


@pytest.mark.parametrize("body, why", BAD_FREEHAND, ids=[b[1] for b in BAD_FREEHAND])
def test_an_invalid_freehand_config_is_refused_and_nothing_is_written(
    client: TestClient, body: dict, why: str
) -> None:
    before = _stim_files()
    r = client.put(
        "/api/catalog/freehand/F1",
        params={"subject": "ernie"},
        json=body,
        headers=BEARER,
    )
    assert r.status_code == 422, why
    assert _stim_files() == before


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e309"])
def test_a_non_finite_json_number_is_refused(client: TestClient, token: str) -> None:
    """The raw tokens Python's json accepts (and ``1e309``, which parses to inf)."""
    rows = ", ".join(
        f'{{"label": "P{i + 1}", "x": {token if i == 0 else x}, "y": {y}, "z": {z}}}'
        for i, (x, y, z) in enumerate(_SQUARE)
    )
    before = _stim_files()
    r = client.put(
        "/api/catalog/freehand/F1",
        params={"subject": "ernie"},
        content=f'{{"type": "U", "electrode_positions": [{rows}]}}',
        headers={**BEARER, "Content-Type": "application/json"},
    )
    assert r.status_code == 422
    assert _stim_files() == before


@pytest.mark.parametrize("kind, n", [("U", 4), ("M", 8), ("M", 12)])
def test_a_valid_freehand_config_round_trips(client: TestClient, kind: str, n: int):
    body = {"type": kind, "electrode_positions": _positions(n)}
    r = client.put(
        "/api/catalog/freehand/Good",
        params={"subject": "ernie"},
        json=body,
        headers=BEARER,
    )
    assert r.status_code == 200
    assert r.json() == {"name": "Good", **body}
    listed = client.get(
        "/api/catalog/freehand", params={"subject": "ernie"}, headers=BEARER
    ).json()
    assert next(c for c in listed if c["name"] == "Good") == {"name": "Good", **body}
    # The file itself is strict JSON (no NaN/Infinity tokens).
    raw = Path(get_path_manager().m2m("ernie"), "stim_configs", "Good.json").read_text()
    json.loads(raw, parse_constant=lambda tok: pytest.fail(f"non-JSON token {tok}"))


def test_a_saved_freehand_config_resolves_into_the_montage_it_describes(
    client: TestClient,
) -> None:
    """What the writer accepts, the simulator's resolver builds: 8 positions -> 4 pairs of mTI."""
    from tit.sim.config import SimulationConfig
    from tit.sim.montage_sources import resolve_freehand_montage

    body = {"type": "M", "electrode_positions": _positions(8)}
    assert (
        client.put(
            "/api/catalog/freehand/Good",
            params={"subject": "ernie"},
            json=body,
            headers=BEARER,
        ).status_code
        == 200
    )
    montage = resolve_freehand_montage(get_path_manager(), "ernie", "Good")
    assert montage.num_pairs == 4
    SimulationConfig(subject_id="ernie", montages=[montage], intensities=[1.0] * 4)
