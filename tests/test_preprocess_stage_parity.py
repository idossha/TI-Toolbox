"""The Pre-processing page's stage columns come from the server planner, for every flag combination.

What this pins: ``tests/fixtures/pre_stages.json`` (written by ``dev/gen_pre_stages.py`` from
:func:`tit.jobs.plans.plan_preprocessing`) is current, so the desktop test that reads it
(``desktop/tests/unit/preprocess-stage-parity.test.ts`` -> ``plannedStageIds``) compares the page
against what the planner does today. A page column the planner never makes would become a stray
matrix column (``planModelFrom`` appends unknown stages).

Independent check: ``plan_preprocessing``'s docstring names one stage group per step flag, in
G1, G2a, G2b, G2c, G3, G4, G5, G6 order; every entry must be exactly the groups of its set flags
in that order (the table below is the docstring's, not the code's).

Reproduce: ``.venv/bin/python -m pytest tests/test_preprocess_stage_parity.py -q -p no:cacheprovider``;
regenerate: ``.venv/bin/python dev/gen_pre_stages.py``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "pre_stages.json"

#: ``plan_preprocessing`` docstring: step flag -> stage group, in dependency order.
DOCSTRING_GROUPS = (
    ("convert_dicom", "G1"),
    ("create_m2m", "G2a"),
    ("run_fastsurfer", "G2b"),
    ("run_freesurfer", "G2c"),
    ("run_tissue_analysis", "G3"),
    ("run_qsiprep", "G4"),
    ("run_qsirecon", "G5"),
    ("extract_dti", "G6"),
)


def _generator():
    spec = importlib.util.spec_from_file_location(
        "gen_pre_stages", REPO / "dev" / "gen_pre_stages.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_is_what_the_planner_plans_today() -> None:
    assert (
        FIXTURE.read_text() == _generator().build()
    ), "tests/fixtures/pre_stages.json is stale; run dev/gen_pre_stages.py"


def test_every_flag_combination_is_its_set_flags_groups_in_docstring_order() -> None:
    entries = json.loads(FIXTURE.read_text())
    combos = {tuple(sorted(e["flags"].items())) for e in entries}
    assert len(entries) == 256 and len(combos) == 256
    for entry in entries:
        want = [group for flag, group in DOCSTRING_GROUPS if entry["flags"][flag]]
        assert entry["stages"] == want, entry["flags"]
