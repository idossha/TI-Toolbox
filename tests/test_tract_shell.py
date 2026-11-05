"""tit.tract CSD shell default (ARCHITECTURE §15; host, numpy is real).

Pins (2026-11-04): with no configured shell the track stage fits CSD on the shell whose
b is closest to 3000 s/mm^2 among shells with >= 30 directions, ties to more directions;
a configured ``shell`` overrides it. The gradient tables are written out by hand here
(acquisition shapes: CHN b1200/3000; the study's b300/1000/2000/4100 with 32/44/72/95
directions), and every expected shell is the arithmetic in the test name, not the code's.
"""

import numpy as np
import pytest

from tit.tract.tracking import CSD_SHELL_RULE, TrackingError, pick_shell


def _bvals(shells: dict[float, int], b0: int = 8, jitter: float = 0.0) -> np.ndarray:
    rng = np.random.default_rng(0)
    out = [np.zeros(b0)]
    for b, n in shells.items():
        out.append(b + rng.uniform(-jitter, jitter, n))
    return np.concatenate(out)


def test_chn_like_scan_picks_b3000():
    assert pick_shell(_bvals({1200: 60, 3000: 60}, jitter=10)) == (
        3000.0,
        60,
        CSD_SHELL_RULE,
    )


def test_study_scan_picks_b2000_since_1000_is_nearer_3000_than_1100():
    # |2000 - 3000| = 1000 < |4100 - 3000| = 1100: the noisy b4100 shell loses.
    b = _bvals({300: 32, 1000: 44, 2000: 72, 4100: 95}, jitter=5)
    assert pick_shell(b)[:2] == (2000.0, 72)


def test_shell_with_fewer_than_30_directions_is_skipped():
    assert pick_shell(_bvals({1000: 64, 3000: 29}))[:2] == (1000.0, 64)


def test_tie_goes_to_the_shell_with_more_directions():
    assert pick_shell(_bvals({2000: 40, 4000: 90}))[:2] == (4000.0, 90)


def test_configured_shell_overrides_the_default():
    assert pick_shell(_bvals({1200: 60, 3000: 60}), 1200) == (1200.0, 60, "configured")


def test_refusals():
    with pytest.raises(TrackingError, match="no shell has"):
        pick_shell(_bvals({1000: 12, 2000: 20}))
    with pytest.raises(TrackingError, match="configured shell"):
        pick_shell(_bvals({1000: 64}), 3000)
