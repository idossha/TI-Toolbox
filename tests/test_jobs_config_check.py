"""A job config the runner cannot deserialise is rejected at submit time, not at run time.

The regression: a ``sim`` job was accepted with ``{"__mock_fast": true, "__mock_fail": false}``
as its config; ``tit/sim/__main__.py``'s ``deserialize_config(SimulationConfig, data)`` then
raised ``TypeError: SimulationConfig.__init__() missing 2 required positional arguments:
'subject_id' and 'montages'`` inside the runner, so the user saw a dead job with a traceback
instead of a rejected request.

The first test here is the level that would have caught it earliest: the *exact* config the
desktop app's ``pages/simulator/buildConfig.ts`` builds, for each of its three montage sources,
round-tripped through the same call the runner makes.
"""

from __future__ import annotations

import pytest

from tit.config_io import deserialize_config
from tit.jobs.config_check import CONFIG_CLASS_FOR_KIND, check_job_config
from tit.sim.config import SimulationConfig


def _ui_config(montage: dict) -> dict:
    """A literal transcription of `buildSimulationConfig()`'s output for one row.

    Deliberately hand-written rather than imported/generated: it is a copy of the wire shape the
    TypeScript builds, so a change on that side that drops a field makes this test's fixture and
    the app disagree only if someone edits one and not the other -- which is what the e2e half of
    this fix (the mock server's required-field gate) is for.
    """
    return {
        "subject_id": "ernie",
        "montages": [montage],
        "conductivity": "scalar",
        "intensities": [1.0, 1.0],
        "electrode_shape": "ellipse",
        "electrode_dimensions": [8, 8],
        "gel_thickness": 4,
        "output_fields": ["TI_max"],
    }


MONTAGE_ROW = {
    "_type": "Montage",
    "name": "BU_eg1",
    "mode": "net",
    "electrode_pairs": [["E010", "E011"], ["E012", "E013"]],
    "eeg_net": "GSN-HydroCel-185.csv",
}
FLEX_MAPPED_ROW = {
    "_type": "Montage",
    "name": "flex-run-1",
    "mode": "flex_mapped",
    "electrode_pairs": [["E020", "E034"], ["E070", "E095"]],
    "eeg_net": "GSN-HydroCel-185.csv",
}
FLEX_FREE_ROW = {
    "_type": "Montage",
    "name": "flex-run-2",
    "mode": "flex_free",
    "electrode_pairs": [
        [[-40.0, 20.0, 60.0], [40.0, 20.0, 60.0]],
        [[-50.0, -20.0, 40.0], [50.0, -20.0, 40.0]],
    ],
    "eeg_net": None,
}
FREEHAND_ROW = {
    "_type": "Montage",
    "name": "freehand-1",
    "mode": "freehand",
    "electrode_pairs": [
        [[-40.0, 20.0, 60.0], [40.0, 20.0, 60.0]],
        [[-50.0, -20.0, 40.0], [50.0, -20.0, 40.0]],
    ],
    "eeg_net": None,
}


@pytest.mark.parametrize(
    "montage",
    [MONTAGE_ROW, FLEX_MAPPED_ROW, FLEX_FREE_ROW, FREEHAND_ROW],
    ids=["montage", "flex_mapped", "flex_free", "freehand"],
)
def test_ui_built_sim_config_deserialises_like_the_runner(montage: dict) -> None:
    data = _ui_config(montage)
    config = deserialize_config(SimulationConfig, data)  # the tit/sim/__main__.py:48 call
    assert config.subject_id == "ernie"
    assert len(config.montages) == 1
    assert config.montages[0].name == montage["name"]
    assert config.montages[0].mode.value == montage["mode"]
    assert len(config.montages[0].electrode_pairs) == 2
    # And the same config passes the submit-time guard.
    check_job_config("sim", {**data, "project_dir": "/mnt/000"})


def test_sim_config_without_subject_id_and_montages_is_rejected() -> None:
    """The exact body that produced the reported failure."""
    with pytest.raises(ValueError, match="SimulationConfig"):
        check_job_config("sim", {"__mock_fail": False, "__mock_fast": True})


@pytest.mark.parametrize("field", ["subject_id", "montages"])
def test_each_required_sim_field_is_enforced(field: str) -> None:
    data = _ui_config(MONTAGE_ROW)
    data.pop(field)
    with pytest.raises(ValueError):
        check_job_config("sim", data)


def test_project_dir_is_not_treated_as_an_unknown_field() -> None:
    """The manager injects `project_dir`; the runner pops it before deserialising, so must we."""
    check_job_config("sim", {**_ui_config(MONTAGE_ROW), "project_dir": "/mnt/000"})


def test_unlisted_kinds_are_a_no_op() -> None:
    # `pre`/`analyzer`/`source` runners tolerate configs deserialize_config rejects.
    for kind in ("pre", "analyzer", "source", "tools", "report", "not-a-kind"):
        assert kind not in CONFIG_CLASS_FOR_KIND
        check_job_config(kind, {"nonsense": True})
