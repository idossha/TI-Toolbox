"""``SimulationConfig`` rejects a montage/intensity mismatch at construction time.

What this pins
--------------
``POST /api/validate/sim`` can only report what a config dataclass itself raises: the route
deserializes through ``tit.config_io.deserialize_config`` and reports whatever ``__post_init__``
says (``tit/server/routes/validate.py``). The rule "an mTI montage needs one intensity per pair"
lived only in ``tit.sim.utils._validate_simulation_inputs``, which runs inside the job -- so the
UI was told a config was valid and the job then died on it one second later.

Where the numbers come from
---------------------------
Measured on the dev container 2026-09-03 with the Level A smoke harness (row ``sim_mti``):
``POST /api/validate/sim`` -> ``{"ok": true, "errors": []}``; job ``cdf272b6556c43fa`` then
failed with ``ValueError: Montage 'smoke-182517-mti' requires 4 current intensities; got 2.``
(4 electrode pairs, the default ``intensities=[1.0, 1.0]``).

Reproduce: ``python3 -m pytest -q tests/test_sim_config_cross_field_rules.py``.

Deliberately elsewhere: the filesystem-dependent half of the same validation (the ``m2m``
directory, the EEG-net CSV) stays in ``tit.sim.utils`` and is tested with the simulation runner;
mode inference itself is ``tests/test_config_io.py``'s.

Written 2026-09-03 (lane S1). 2026-10-21: an odd pair count is rejected here too (it failed
only at run time, "Invalid number of electrode pairs: 5", for a 10-position free-hand job).
"""

from __future__ import annotations

import math
import os
import string
from copy import deepcopy

import pytest

from tit.sim.config import Montage, MontageMode, SimulationConfig


def _montage(name: str, n_pairs: int) -> Montage:
    labels = [f"E{i:03d}" for i in range(2 * n_pairs)]
    pairs = [(labels[2 * i], labels[2 * i + 1]) for i in range(n_pairs)]
    return Montage(
        name=name, mode=MontageMode.NET, electrode_pairs=pairs, eeg_net="net.csv"
    )


def test_mti_montage_with_the_default_two_intensities_is_rejected():
    """The exact shape the UI submitted: 4 pairs, `intensities` left at its default."""
    with pytest.raises(ValueError, match="requires 4 current intensities; got 2"):
        SimulationConfig(subject_id="101", montages=[_montage("mti", 4)])


def test_mti_montage_with_one_intensity_per_pair_is_accepted():
    config = SimulationConfig(
        subject_id="101", montages=[_montage("mti", 4)], intensities=[1.0] * 4
    )
    assert len(config.intensities) == 4


def test_ti_montage_needs_only_two_intensities():
    config = SimulationConfig(subject_id="101", montages=[_montage("ti", 2)])
    assert len(config.intensities) == 2


def test_an_electrode_pair_that_is_not_a_pair_is_rejected():
    montage = Montage(
        name="bad",
        mode=MontageMode.NET,
        electrode_pairs=[("A1", "A2"), ("A3",)],
        eeg_net="net.csv",
    )
    with pytest.raises(ValueError, match="invalid electrode pair"):
        SimulationConfig(subject_id="101", montages=[montage])


@pytest.mark.parametrize("n_pairs", [1, 3, 5])
def test_a_pair_count_the_mode_cannot_classify_is_rejected(n_pairs: int):
    """Changed 2026-10-21: an odd pair count used to construct and fail only inside the job
    (a 10-position free-hand placement -> "Invalid number of electrode pairs: 5" at run time).
    It is now refused here, so validate, plan and submit all reject it up front."""
    with pytest.raises(
        ValueError, match=f"'odd': Invalid number of electrode pairs: {n_pairs}"
    ):
        SimulationConfig(
            subject_id="101",
            montages=[_montage("odd", n_pairs)],
            intensities=[1.0] * n_pairs,
        )


def test_the_job_submission_check_refuses_a_five_pair_freehand_montage():
    """The reported job: a 10-position free-hand placement submitted as one sim job."""
    from tit.jobs.config_check import check_job_config

    pairs = [[[k, 0.0, 0.0], [k, 1.0, 0.0]] for k in range(5)]
    config = {
        "subject_id": "101",
        "montages": [
            {
                "_type": "Montage",
                "name": "hand10",
                "mode": "freehand",
                "electrode_pairs": pairs,
                "eeg_net": None,
            }
        ],
        "intensities": [1.0] * 5,
    }
    with pytest.raises(ValueError, match="Invalid number of electrode pairs: 5"):
        check_job_config("sim", config)


def test_the_validate_route_now_reports_the_mismatch():
    """End of the chain: the same body, through the route the UI calls."""
    from tit.server.routes.validate import ValidateRequest, validate

    result = validate(
        "sim",
        ValidateRequest(
            config={
                "subject_id": "101",
                "montages": [
                    {
                        "_type": "Montage",
                        "name": "smoke-mti",
                        "mode": "net",
                        "eeg_net": "BioSemi-128-A1.csv",
                        "electrode_pairs": [
                            ["A1", "A2"],
                            ["A4", "A3"],
                            ["B1", "B2"],
                            ["B4", "B3"],
                        ],
                    }
                ],
                "intensities": [1, 1],
            }
        ),
    )
    assert not result.ok
    assert "requires 4 current intensities" in result.errors[0].message


# ── p15 (2026-10-22): the rules a config is refused for before any FEM solve ──────────────────
#
# Where the expected values come from: the spec, not the code under test.
# * mTI channels are named A..Z (``tit/sim/mTI.py``, ``string.ascii_uppercase``), so a montage
#   holds at most 26 pairs; before this, a 28-pair config constructed and failed only in
#   ``mTISimulation._post_process``, after 28 FEM solves.
# * Every montage writes ``Simulations/<name>/``, so two montages of one config with one name
#   would overwrite each other.
# * A TI montage reads the first two currents, an mTI montage one per pair (the class docstring).
# * An electrode is one point on the scalp: a pair ["E1","E1"] is a channel shorted on itself, an
#   electrode shared by two channels shorts them, and two XYZ electrodes closer than 1 mm are one
#   pad (the desktop's MIN_ELECTRODE_SEPARATION_MM, desktop/src/renderer/pages/simulator/types.ts,
#   which this layer must agree with: the server accepts what the Simulator accepts).
# * A 0 mA channel makes the envelope 0 everywhere; a non-finite current is not a current.


def _xyz_montage(name: str, points: list[list[float]]) -> Montage:
    pairs = [(points[i], points[i + 1]) for i in range(0, len(points), 2)]
    return Montage(name=name, mode=MontageMode.FREEHAND, electrode_pairs=pairs)


_FOUR_POINTS = [
    [-60.0, 10.0, 40.0],
    [60.0, 10.0, 40.0],
    [-60.0, -40.0, 40.0],
    [60.0, -40.0, 40.0],
]


def test_the_largest_montage_the_a_to_z_channel_names_allow_is_accepted():
    n = len(string.ascii_uppercase)  # 26 channel letters
    config = SimulationConfig(
        subject_id="101", montages=[_montage("az", n)], intensities=[1.0] * n
    )
    assert config.montages[0].num_pairs == 26


def test_a_28_pair_montage_is_refused_at_construction_not_after_its_fem_solves():
    with pytest.raises(ValueError, match="'big'.*at most 26"):
        SimulationConfig(
            subject_id="101", montages=[_montage("big", 28)], intensities=[1.0] * 28
        )


def test_two_montages_with_one_name_are_refused_because_they_share_one_folder():
    with pytest.raises(ValueError, match="'twin'.*more than once"):
        SimulationConfig(
            subject_id="101", montages=[_montage("twin", 2), _montage("twin", 2)]
        )
    # Different names are fine (the control: the rule is the name, not the count).
    SimulationConfig(subject_id="101", montages=[_montage("a", 2), _montage("b", 2)])


class _FakeElectrode:
    pass


class _FakeTdcs:
    def __init__(self):
        self.electrode, self.cond, self.currents = [], [], None

    def add_electrode(self):
        self.electrode.append(_FakeElectrode())
        return self.electrode[-1]


class _FakeSession:
    def __init__(self):
        self.poslists = []

    def add_tdcslist(self, tdcs=None):
        self.poslists.append(tdcs if tdcs is not None else _FakeTdcs())
        return self.poslists[-1]


def test_a_mixed_ti_and_mti_config_gives_each_montage_its_own_leading_currents(init_pm):
    """[TI, mTI(4)] with [1, 2, 3, 4] mA: TI drives 1 and 2 mA, mTI 1, 2, 3 and 4 mA.

    SimNIBS takes amperes, one ``[+I, -I]`` per pair; the expected values are mA / 1000.
    """
    from unittest.mock import patch

    from tit.sim.mTI import mTISimulation
    from tit.sim.TI import TISimulation

    ti, mti = _montage("ti", 2), _montage("mti", 4)
    config = SimulationConfig(
        subject_id="001", montages=[ti, mti], intensities=[1.0, 2.0, 3.0, 4.0]
    )
    currents = {}
    for cls, montage in ((TISimulation, ti), (mTISimulation, mti)):
        sim = cls(config, montage, logger=None)
        with patch.object(cls, "_init_session", lambda self, out: _FakeSession()):
            session = sim._build_session("/unused")
        currents[montage.name] = [tdcs.currents for tdcs in session.poslists]
    assert currents == {
        "ti": [[0.001, -0.001], [0.002, -0.002]],
        "mti": [[0.001, -0.001], [0.002, -0.002], [0.003, -0.003], [0.004, -0.004]],
    }


@pytest.mark.parametrize("name", ["my montage", "v1.0", "abnormal"])
def test_odd_but_legal_names_survive_serialisation_and_name_their_own_folder(
    init_pm, name: str
):
    from tit.config_io import deserialize_config, serialize_config

    config = SimulationConfig(subject_id="001", montages=[_montage(name, 2)])
    data = serialize_config(config)
    data.pop("project_dir")  # what tit.sim.__main__ does before deserialising
    back = deserialize_config(SimulationConfig, data, strict=True)
    assert back.montages[0].name == name
    folder = init_pm.simulation("001", name)
    assert os.path.basename(folder) == name
    assert os.path.dirname(folder) == init_pm.simulations("001")


def test_load_montages_refuses_a_name_saved_in_both_polarity_buckets(init_pm):
    """It used to return the multi-polar pairs without a word, whatever the caller meant."""
    import json

    from tit.sim.utils import load_montages

    path = os.path.join(init_pm.config_dir(), "montage_list.json")
    uni = [["E1", "E2"], ["E3", "E4"]]
    multi = [["E1", "E2"], ["E3", "E4"], ["E5", "E6"], ["E7", "E8"]]
    with open(path, "w") as f:
        json.dump(
            {
                "nets": {
                    "net.csv": {
                        "uni_polar_montages": {"Both": uni, "OnlyUni": uni},
                        "multi_polar_montages": {"Both": multi},
                    }
                }
            },
            f,
        )
    with pytest.raises(ValueError, match="'Both'.*uni_polar.*multi_polar"):
        load_montages(["Both"], "net.csv", include_flex=False)
    (only,) = load_montages(["OnlyUni"], "net.csv", include_flex=False)
    assert [list(p) for p in only.electrode_pairs] == uni


@pytest.mark.parametrize(
    "pairs, repeated",
    [
        ([("E1", "E1"), ("E2", "E3")], "E1"),  # a channel whose return is itself
        ([("E1", "E2"), ("E1", "E3")], "E1"),  # two channels on one electrode
        ([("E1", "E2"), ("E3", "E2")], "E2"),
    ],
)
def test_a_label_montage_that_uses_one_electrode_twice_is_refused(pairs, repeated):
    montage = Montage(
        name="dup", mode=MontageMode.NET, electrode_pairs=pairs, eeg_net="net.csv"
    )
    with pytest.raises(ValueError, match=f"'dup'.*{repeated}.*more than once"):
        SimulationConfig(subject_id="101", montages=[montage])


@pytest.mark.parametrize("bad", ["", 7, None])
def test_an_empty_or_non_text_label_is_refused(bad):
    montage = Montage(
        name="lbl",
        mode=MontageMode.NET,
        electrode_pairs=[("E1", bad), ("E2", "E3")],
        eeg_net="net.csv",
    )
    with pytest.raises(ValueError, match="'lbl'.*label"):
        SimulationConfig(subject_id="101", montages=[montage])


def test_xyz_electrodes_closer_than_1_mm_are_refused_and_1_mm_apart_is_not():
    near = deepcopy(_FOUR_POINTS)
    near[3] = [near[0][0] + 0.6, near[0][1] + 0.79, near[0][2]]  # hypot < 1 mm
    assert math.dist(near[0], near[3]) < 1.0
    with pytest.raises(ValueError, match="'near'.*electrodes 1 and 4.*1 mm"):
        SimulationConfig(subject_id="101", montages=[_xyz_montage("near", near)])

    apart = deepcopy(_FOUR_POINTS)
    apart[3] = [apart[0][0] + 0.6, apart[0][1] + 0.8, apart[0][2]]  # 3-4-5: 1.0 mm
    assert math.isclose(math.dist(apart[0], apart[3]), 1.0)
    SimulationConfig(subject_id="101", montages=[_xyz_montage("apart", apart)])


def test_four_unplaced_electrodes_at_the_origin_are_refused():
    """The free-hand editor's blank row is (0, 0, 0): four of them are one point."""
    with pytest.raises(ValueError, match="'blank'.*1 mm"):
        SimulationConfig(
            subject_id="101", montages=[_xyz_montage("blank", [[0.0, 0.0, 0.0]] * 4)]
        )


@pytest.mark.parametrize(
    "bad", [math.nan, math.inf, -math.inf, "nan", "1.0", True, [1.0, 2.0]]
)
def test_an_xyz_electrode_that_is_not_three_finite_numbers_is_refused(bad):
    points = deepcopy(_FOUR_POINTS)
    points[2] = bad if isinstance(bad, list) else [bad, -40.0, 40.0]
    with pytest.raises(ValueError, match="'xyz'.*electrode 3"):
        SimulationConfig(subject_id="101", montages=[_xyz_montage("xyz", points)])


@pytest.mark.parametrize(
    "intensities, channel",
    [
        ([0.0, 1.0], 1),
        ([1.0, 0.0], 2),
        ([math.nan, 1.0], 1),
        ([1.0, math.inf], 2),
        ([1.0, -math.inf], 2),
    ],
)
def test_a_zero_or_non_finite_current_on_a_channel_the_montage_uses_is_refused(
    intensities, channel
):
    with pytest.raises(ValueError, match=f"'ti'.*channel {channel}"):
        SimulationConfig(
            subject_id="101", montages=[_montage("ti", 2)], intensities=intensities
        )


def test_a_zero_on_the_fourth_channel_of_an_mti_montage_is_refused():
    with pytest.raises(ValueError, match="'mti'.*channel 4"):
        SimulationConfig(
            subject_id="101",
            montages=[_montage("mti", 4)],
            intensities=[1.0, 1.0, 1.0, 0.0],
        )


def test_a_ti_montage_ignores_the_currents_past_its_second():
    """Only a channel the montage uses must carry current: [1, 1, 0, 0] runs TI at 1 and 1."""
    config = SimulationConfig(
        subject_id="101", montages=[_montage("ti", 2)], intensities=[1.0, 1.0, 0.0, 0.0]
    )
    assert config.intensities[:2] == [1.0, 1.0]


def test_a_non_finite_current_is_refused_even_on_a_channel_no_montage_reads():
    with pytest.raises(ValueError, match="finite"):
        SimulationConfig(
            subject_id="101",
            montages=[_montage("ti", 2)],
            intensities=[1.0, 1.0, math.nan, 1.0],
        )


def test_a_signed_current_is_a_polarity_not_an_error():
    """An optimiser candidate keeps its signed currents (a negative channel is that channel's
    pads swapped), and the desktop sends them as they are."""
    config = SimulationConfig(
        subject_id="101", montages=[_montage("ti", 2)], intensities=[-1.5, 2.0]
    )
    assert config.intensities == [-1.5, 2.0]


@pytest.mark.parametrize("bad", [[math.nan, 0, 0], ["inf", 0, 0], [0, "-inf", 0]])
def test_config_json_never_records_a_non_finite_electrode_coordinate(bad):
    """``_as_xyz`` writes ``electrode_coordinates`` into config.json (strict JSON has no NaN)."""
    from tit.sim.utils import _as_xyz

    with pytest.raises(ValueError, match="finite"):
        _as_xyz(bad)
    assert _as_xyz(["1", 2, 3.5]) == [1.0, 2.0, 3.5]
