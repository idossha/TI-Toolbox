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

Written 2026-09-03 (lane S1).
"""

from __future__ import annotations

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


@pytest.mark.parametrize("n_pairs", [1, 3])
def test_a_pair_count_the_mode_cannot_classify_still_constructs(n_pairs: int):
    """Unchanged behaviour, deliberately: `Montage.simulation_mode` raises for 1 or 3 pairs and
    `run_simulation` is where that has always surfaced. Deciding it in ``__post_init__`` would
    make configs that existing callers build on purpose unconstructable."""
    config = SimulationConfig(subject_id="101", montages=[_montage("odd", n_pairs)])
    assert config.montages[0].num_pairs == n_pairs


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
