"""One desktop-built Ex config and one mEx config run validate -> plan -> ``python -m`` -> files,
and every reader of those files agrees with a hand calculation.

What this pins (2026-10-22). The configs are the desktop-config corpus cases
``tests/fixtures/desktop_configs/optimizer-ex/bucketed-saved.json`` (Ex, four 2-electrode buckets,
2 mA in 0.2 mA steps, 1.6 mA channel limit) and ``mex-saved.json`` (mEx, eight buckets, 2 mA per
pair), written by the real ``buildExConfig``/``buildMExConfig`` (``desktop/tests/unit/
desktop-config-corpus.test.ts``). Each one, unchanged, is

1. accepted by ``POST /api/validate/{kind}`` and planned by ``POST /api/plan/{kind}``;
2. run by ``tit.opt.ex.__main__.main`` / ``tit.opt.mex.__main__.main`` in-process, on a tmp project
   whose leadfield is synthetic (SimNIBS is absent on the host: ``TI_utils`` is replaced by a fake
   ``load_leadfield``/``get_field``/``get_maxTI``, the last being ``tit.calc``'s K=1 TI envelope);
3. read back by everything that reads a run: ``final_output.csv`` and ``run_config.json``, the
   job's events (``result``), ``tit.catalog.ex_runs`` (``best``), ``tit.opt.candidate_catalog``
   (``list_candidates`` and the ``candidate_detail`` simulator replay), the HTML report the runner
   writes, and the desktop Results pane (``parseExRunConfig``, in
   ``desktop/tests/unit/ex-chain-preview.test.ts``, on copies of these files committed under
   ``desktop/tests/fixtures/ex_chain/``; this test fails when the copies drift).

Where the expected numbers come from -- by hand, never from the engine:

* The leadfield (``WEIGHTS``) gives every electrode a field along x only, so all channel fields
  are collinear. For two collinear fields the TI envelope is ``2*min(|E1|, |E2|)`` per element
  (Grossman et al. 2017); for the mEx pairs, the low-passed square of the x signal is
  ``P + Q*cos(dw*t)`` with ``P = sum_k A_k^2 / 2`` and ``Q = |A1*A2 + A3*A4|`` (the cross terms
  between the two carriers average out), so the envelope ``sqrt(2*LP)`` swings by
  ``sqrt2*(sqrt(P+Q) - sqrt(P-Q))``. ``A_k = I_k[A] * (w_plus - w_minus)``.
* ROI = the elements within 3 mm of ``L_Insula.csv``'s centre (0, 0, 0): elements 0, 1, 2. Grey
  matter = tag 2: elements 0, 1, 3, 4. Means are volume weighted (``VOLUMES``). Focality = ROI
  mean / GM mean, Composite = ROI mean * Focality.
* Counts: Ex = 2^4 bucket montages (the buckets are disjoint) x 7 splits (0.4 ... 1.6 mA in
  0.2 mA steps) = 112; mEx = 2^4 x 1^4 = 16.

Tolerances: the CSV writes 4 decimals (half a unit = 5e-5). The mEx envelope is a direction
search that evaluates the exact envelope at sampled directions, so it never exceeds the true
maximum and misses it by <= 1.6e-5 relative (measured; ``tests/test_mex_symmetry_numeric.py``):
bounded here at 1e-4 relative.

Reproduce: ``.venv/bin/python -m pytest tests/test_ex_desktop_runner_chain.py -q -p no:cacheprovider``.
Refresh the desktop copies: ``UPDATE_EX_CHAIN_FIXTURES=1`` with the same command.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
import time
from itertools import product
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from tests.test_desktop_config_corpus import load_case, make_project  # noqa: E402
from tit.calc import get_TI_vectors  # noqa: E402
from tit.paths import get_path_manager  # noqa: E402
from tit.server.app import create_app  # noqa: E402
from tit.server.settings import ServerSettings  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "tests" / "fixtures" / "desktop_configs" / "optimizer-ex"
DESKTOP_FIXTURES = REPO / "desktop" / "tests" / "fixtures" / "ex_chain"
PLACEHOLDER = "/corpus/project"
CASES = {"ex": "bucketed-saved", "mex": "mex-saved"}
RUNNER = {"ex": "tit.opt.ex.__main__", "mex": "tit.opt.mex.__main__"}
STAMP = "20261022_101500"
TOKEN = "chain-token"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
HALF = 5e-5
SID = "001"

#: Element barycentres (mm), tissue tags and volumes of the synthetic head mesh.
CENTRES = np.array(
    [[0, 0, 0], [1, 0, 0], [0, 1, 0], [20, 0, 0], [0, 20, 0], [0, 0, 20]], dtype=float
)
TAGS = np.array([2, 2, 1, 2, 2, 1])
VOLUMES = np.array([1.0, 2.0, 1.0, 2.0, 1.0, 3.0])
ROI = [0, 1, 2]  # within 3 mm of (0, 0, 0)
GM = [0, 1, 3, 4]  # tag 2
#: x-component of each electrode's field per ampere, per element (V/m/A).
WEIGHTS = {
    "E010": [120, 60, 30, 10, 0, 40],
    "E011": [-40, 20, -30, 50, 20, 0],
    "E012": [90, 100, 50, 0, 30, 10],
    "E013": [10, -50, 0, 30, -20, 20],
    "E020": [-80, 30, 70, 0, 10, -10],
    "E021": [60, -20, -10, 20, 40, 30],
    "E022": [50, 90, 20, -30, 0, 50],
    "E023": [-30, -10, 60, 10, 10, -20],
    "E030": [30, 0, 20, 10, -10, 0],
    "E031": [-10, 40, 0, 0, 20, 10],
    "E040": [20, -20, 10, 40, 0, 0],
    "E041": [0, 30, -20, 10, 10, 30],
}
NET = "GSN-HydroCel-185"


# ── the synthetic leadfield (stands in for simnibs.utils.TI_utils) ─────────────────────────────


def _fake_ti():
    names = list(WEIGHTS)
    leadfield = np.zeros((len(names), len(CENTRES), 3))
    for i, name in enumerate(names):
        leadfield[i, :, 0] = WEIGHTS[name]
    mesh = SimpleNamespace(
        elements_baricenters=lambda: SimpleNamespace(value=CENTRES),
        elements_volumes_and_areas=lambda: SimpleNamespace(value=VOLUMES),
        elm=SimpleNamespace(tag1=TAGS),
    )
    return SimpleNamespace(
        load_leadfield=lambda path: (leadfield, mesh, names),
        get_field=lambda pair, lf, idx: pair[2]
        * (lf[idx.index(pair[0])] - lf[idx.index(pair[1])]),
        get_maxTI=lambda e1, e2: np.linalg.norm(get_TI_vectors([e1, e2]), axis=1),
    )


# ── hand values ──────────────────────────────────────────────────────────────────────────────


def _amplitude(plus: str, minus: str, current_mA: float) -> np.ndarray:
    return current_mA / 1000 * (np.array(WEIGHTS[plus]) - np.array(WEIGHTS[minus]))


def _metrics(envelope: np.ndarray) -> dict:
    roi_mean = float(np.dot(envelope[ROI], VOLUMES[ROI]) / VOLUMES[ROI].sum())
    gm_mean = float(np.dot(envelope[GM], VOLUMES[GM]) / VOLUMES[GM].sum())
    focality = roi_mean / gm_mean
    return {
        "TImax_ROI": float(envelope[ROI].max()),
        "TImean_ROI": roi_mean,
        "TImean_GM": gm_mean,
        "Focality": focality,
        "Composite_Index": roi_mean * focality,
    }


def _splits(total: float, step: float, limit: float) -> list[tuple[float, float]]:
    n = round(total / step)
    out = []
    for k in range(1, n):
        a, b = round(k * step, 6), round((n - k) * step, 6)
        if a <= limit + 1e-9 and b <= limit + 1e-9:
            out.append((a, b))
    return out


def _hand_rows(kind: str, config: dict) -> dict[tuple, dict]:
    """(electrodes, currents) -> hand metrics, over the itertools enumeration of the buckets."""
    e = config["electrodes"]
    n_pairs = 2 if kind == "ex" else 4
    keys = [f"e{k}_{s}" for k in range(1, n_pairs + 1) for s in ("plus", "minus")]
    montages = [m for m in product(*(e[k] for k in keys)) if len(set(m)) == len(m)]
    rows = {}
    for m in montages:
        if kind == "ex":
            splits = _splits(
                config["total_current"], config["current_step"], config["channel_limit"]
            )
            for i1, i2 in splits:
                a1, a2 = _amplitude(m[0], m[1], i1), _amplitude(m[2], m[3], i2)
                rows[(m, (i1, i2))] = _metrics(2 * np.minimum(np.abs(a1), np.abs(a2)))
        else:
            cur = config["current_mA"]
            a = [_amplitude(m[2 * k], m[2 * k + 1], cur) for k in range(4)]
            p = sum(x**2 for x in a) / 2
            q = np.abs(a[0] * a[1] + a[2] * a[3])
            md = np.sqrt(2) * (np.sqrt(p + q) - np.sqrt(np.maximum(p - q, 0)))
            rows[(m, (cur,) * 4)] = _metrics(md)
    return rows


def _montage_name(electrodes: tuple, currents: tuple) -> str:
    pairs = " <> ".join(
        f"{electrodes[i]}_{electrodes[i + 1]}" for i in range(0, len(electrodes), 2)
    )
    if len(currents) == 2:
        return f"{pairs}_I1-{currents[0]:.1f}mA_I2-{currents[1]:.1f}mA"
    return f"{pairs}_I-{currents[0]:.1f}mA"


# ── the chain, run once per kind ─────────────────────────────────────────────────────────────


def _new_handlers(before: dict) -> list[tuple[logging.Logger, logging.Handler]]:
    out = []
    for name in [None, *logging.Logger.manager.loggerDict]:
        logger = logging.getLogger(name)
        if not isinstance(logger, logging.Logger):
            continue
        for handler in logger.handlers:
            if handler not in before.get(name, ()):
                out.append((logger, handler))
    return out


@pytest.fixture(scope="module", params=["ex", "mex"])
def chain(request, tmp_path_factory):
    import tit.jobs.events as events_mod
    import tit.logger as logger_mod
    import tit.opt.ex.engine as ex_engine
    import tit.opt.mex.engine as mex_engine
    import tit.plotting.ti_metrics as ti_metrics

    kind = request.param
    project = tmp_path_factory.mktemp(f"chain_{kind}")
    case = load_case(CORPUS / f"{CASES[kind]}.json", project)
    (job,) = case["jobs"]
    config = job["config"]
    make_project(project, case)
    pm = get_path_manager(str(project))
    rois = Path(pm.rois(SID))
    rois.mkdir(parents=True, exist_ok=True)
    (rois / "L_Insula.csv").write_text("0,0,0\n")
    events_file = project / "events.jsonl"
    runner_file = project / "config.json"
    runner_file.write_text(json.dumps({**config, "project_dir": str(project)}))

    real_strftime = time.strftime
    handlers_before = {
        name: list(logging.getLogger(name).handlers)
        for name in [None, *logging.Logger.manager.loggerDict]
        if isinstance(logging.getLogger(name), logging.Logger)
    }
    with pytest.MonkeyPatch.context() as mp:
        # The run folder is named by a timestamp when run_name is null (the corpus case); the
        # plan and the runner each take one, so pin it to compare their output_dir.
        mp.setattr(
            time,
            "strftime",
            lambda fmt, *a: STAMP if fmt == "%Y%m%d_%H%M%S" else real_strftime(fmt, *a),
        )
        fake = _fake_ti()
        mp.setattr(ex_engine, "TI", fake)
        mp.setattr(mex_engine, "TI", fake)
        # The real envelope, whatever an earlier test module left bound in the engine module.
        mp.setattr(mex_engine, "get_TI_vectors", get_TI_vectors)
        # matplotlib is mocked on the host; the PNGs are not a reader of the results.
        for figure in (
            "plot_montage_distributions",
            "plot_intensity_vs_focality",
            "plot_electrode_score_heatmap",
            "plot_montage_score_map",
        ):
            mp.setattr(ti_metrics, figure, lambda **kw: kw["output_file"])
        mp.setenv("TIT_JOB_CPUS", "1")  # a 1-CPU job: candidates evaluate in-process
        mp.setenv("TIT_EVENTS_FILE", str(events_file))
        mp.delenv("TIT_JOB_ID", raising=False)
        logger_mod._event_sinks.clear()
        events_mod._reset_state()

        client = TestClient(
            create_app(ServerSettings(project_dir=str(project), token=TOKEN)),
            base_url="http://127.0.0.1:8765",
        )
        validated = client.post(
            f"/api/validate/{kind}", json={"config": config}, headers=BEARER
        )
        planned = client.post(
            f"/api/plan/{kind}",
            json={"config": config, "subject_ids": job["subject_ids"]},
            headers=BEARER,
        )

        module = __import__(RUNNER[kind], fromlist=["main"])
        mp.setattr(sys, "argv", [RUNNER[kind], str(runner_file)])
        try:
            module.main()
            code = 0
        except SystemExit as exc:
            code = exc.code
        finally:
            logger_mod._event_sinks.clear()
            events_mod._reset_state()
            for logger, handler in _new_handlers(handlers_before):
                logger.removeHandler(handler)
                handler.close()

    events = [json.loads(line) for line in events_file.read_text().splitlines()]
    (result,) = [e for e in events if e["type"] == "result"]
    run_dir = Path(result["outputs"]["output_dir"])
    with open(run_dir / "final_output.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    hand = _hand_rows(kind, config)
    winner = max(hand, key=lambda k: hand[k]["Composite_Index"])
    return SimpleNamespace(
        kind=kind,
        project=project,
        pm=pm,
        config=config,
        validated=validated,
        planned=planned,
        code=code,
        events=events,
        result=result,
        run_dir=run_dir,
        rows=rows,
        run_config=json.loads((run_dir / "run_config.json").read_text()),
        hand=hand,
        winner=winner,
    )


def _row_key(kind: str, row: dict) -> tuple:
    pairs = row["Montage"].split(" <> ")
    pairs[-1] = pairs[-1].rsplit("_I", 2 if kind == "ex" else 1)[0]
    electrodes = tuple(e for pair in pairs for e in pair.split("_"))
    n = 2 if kind == "ex" else 4
    currents = tuple(float(row[f"Current_Ch{k}_mA"]) for k in range(1, n + 1))
    return electrodes, currents


# ── the tests ────────────────────────────────────────────────────────────────────────────────


def test_the_hand_ranking_has_one_clear_winner(chain):
    scores = sorted((m["Composite_Index"] for m in chain.hand.values()), reverse=True)
    assert len(chain.hand) == {"ex": 2**4 * 7, "mex": 2**4}[chain.kind]
    # Far beyond the CSV rounding and the mEx search error: the winner is well defined.
    assert scores[0] - scores[1] > 1e-2


def test_the_server_validates_and_plans_what_the_runner_then_writes(chain):
    assert chain.validated.status_code == 200 and chain.validated.json() == {
        "ok": True,
        "errors": [],
    }
    assert chain.planned.status_code == 200, chain.planned.text
    plan = chain.planned.json()
    (job,) = plan["jobs"]
    assert job["subject"] == SID and job["exists"] is False
    assert chain.code == 0
    outputs = chain.result["outputs"]
    assert outputs["success"] is True
    assert Path(job["output_dir"]) == chain.run_dir
    assert chain.run_dir.parent == Path(
        chain.pm.ex_search(SID) if chain.kind == "ex" else chain.pm.m_ex_search(SID)
    )
    n = len(chain.hand)
    assert plan["resolved"]["search_space"]["n_combinations"] == n
    assert outputs["n_combinations"] == n
    assert chain.run_config["n_combinations"] == n
    assert len(chain.rows) == n
    assert chain.events[-1] == {**chain.events[-1], "type": "exit", "code": 0}


def test_the_csv_holds_every_enumerated_montage_with_its_hand_metrics(chain):
    tol = 1e-12 if chain.kind == "ex" else 1e-4
    got = {}
    for row in chain.rows:
        key = _row_key(chain.kind, row)
        assert key not in got, f"repeated {row['Montage']}"
        got[key] = row
        assert row["Montage"] == _montage_name(*key)
    assert set(got) == set(chain.hand)
    for key, row in got.items():
        hand = chain.hand[key]
        for metric, value in hand.items():
            # The mEx search reaches the true maximum from below (relative error <= tol).
            assert abs(float(row[metric]) - value) <= HALF + tol * abs(value) + 1e-12, (
                row["Montage"],
                metric,
                row[metric],
                value,
            )


def test_run_config_records_the_search_the_desktop_asked_for(chain):
    rc, config = chain.run_config, chain.config
    assert rc["subject_id"] == SID
    assert rc["roi_name"] == "L_Insula.csv"
    assert rc["roi_radius"] == config["roi_radius"]
    assert rc["leadfield_hdf"] == config["leadfield_hdf"]
    assert rc["electrode_mode"] == "bucket"
    assert rc["electrodes"] == {
        k: v for k, v in config["electrodes"].items() if k != "_type"
    }
    if chain.kind == "ex":
        assert (
            rc["total_current_mA"],
            rc["current_step_mA"],
            rc["channel_limit_mA"],
        ) == (
            config["total_current"],
            config["current_step"],
            config["channel_limit"],
        )
    else:
        assert rc["current_mA"] == config["current_mA"]


def test_the_catalog_names_the_hand_winner_best(chain):
    from tit.catalog import ex_runs

    (run,) = ex_runs(chain.pm, SID, chain.kind)
    assert run["run_name"] == chain.run_dir.name
    assert run["eeg_net"] == f"{NET}.csv"
    assert run["best"]["montage"] == _montage_name(*chain.winner)
    tol = 0 if chain.kind == "ex" else 1e-4
    hand = chain.hand[chain.winner]["Composite_Index"]
    assert abs(run["best"]["score"] - hand) <= HALF + tol * hand


def test_the_candidate_browser_and_replay_rebuild_the_winner(chain):
    from tit.opt.candidate_catalog import candidate_detail, list_candidates

    page = list_candidates(
        chain.pm, SID, chain.kind, chain.run_dir.name, sort="objective", limit=3
    )
    assert page["total"] == len(chain.hand)
    top = page["candidates"][0]
    electrodes, currents = chain.winner
    pairs = [list(electrodes[i : i + 2]) for i in range(0, len(electrodes), 2)]
    assert top["pairs"] == pairs
    assert top["currents_mA"] == list(currents)
    assert top["eeg_net"] == f"{NET}.csv"

    detail = candidate_detail(chain.pm, SID, chain.kind, chain.run_dir.name, top["id"])
    sim = detail["simulation_config"]
    (montage,) = sim["montages"]
    # The same pairs in the same polarity (first electrode is the anode), on the same net.
    assert montage["electrode_pairs"] == pairs
    assert montage["eeg_net"] == f"{NET}.csv"
    assert sim["intensities"] == list(currents)
    assert sim["subject_id"] == SID


def test_the_report_leads_with_the_hand_winner(chain):
    reports = [
        a["path"] for a in chain.result.get("artifacts", []) if a["kind"] == "report"
    ]
    assert len(reports) == 1, chain.result
    html = Path(reports[0]).read_text()
    electrodes, currents = chain.winner
    name = " ‖ ".join(
        "–".join(electrodes[i : i + 2]) for i in range(0, len(electrodes), 2)
    )
    assert f"{name} leads {len(chain.hand):,} montages" in html
    best = chain.hand[chain.winner]
    assert f"<b>{best['TImean_ROI']:.3f} V/m</b>" in html


def _normalised(text: str, project: Path) -> str:
    return text.replace(str(project), PLACEHOLDER)


def test_the_desktop_fixture_copies_are_these_files(chain):
    """``desktop/tests/fixtures/ex_chain/<kind>/`` is what this chain writes today."""
    target = DESKTOP_FIXTURES / chain.kind
    files = {
        "run_config.json": _normalised(
            (chain.run_dir / "run_config.json").read_text(), chain.project
        ),
        "final_output.csv": (chain.run_dir / "final_output.csv").read_text(),
    }
    if os.environ.get("UPDATE_EX_CHAIN_FIXTURES"):
        target.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (target / name).write_text(text)
    for name, text in files.items():
        assert (
            target / name
        ).read_text() == text, (
            f"{target / name} drifted; refresh with UPDATE_EX_CHAIN_FIXTURES=1"
        )
