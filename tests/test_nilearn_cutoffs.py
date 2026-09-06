"""The nilearn runner's display range is derived from the data, not guessed (lane FX3).

The failure this pins: ``NilearnConfig.min_cutoff`` used to default to ``0.3`` V/m, which
is above every real TI field. ernie's MNI-space ``L_Insula`` ``TI_max`` peaks at
**0.1385 V/m** (p95 **0.0616**), so a default run resolved a display range of
0.3 - 0.1147 V/m and died three frames deep inside matplotlib with ``minvalue must be
less than or equal to maxvalue`` (job ``287e3e0c2eb94134``), naming neither cutoff nor
data. Now an unset cutoff is the 95th/99.9th percentile of the loaded field -- the pair
``tit.reporting.generators.simulation._compute_field_thresholds`` already derives from
real data -- and an explicit cutoff above the field is refused up front by a message
that names the range.

The synthetic field below is shaped like ernie's: a long tail of small values with a few
large ones, so its p95 sits well under its maximum and a fixed 0.3 V/m floor is above all
of it. The measured ernie numbers appear only in the header; the assertions are formulas
over the fixture, so nothing here is a retyped number.

Reproduce: ``python3 -m pytest -q tests/test_nilearn_cutoffs.py``
"""

from __future__ import annotations

import numpy as np
import pytest

from tit.plotting.nilearn.cutoffs import (
    DEFAULT_MAX_PERCENTILE,
    DEFAULT_MIN_PERCENTILE,
    blank_figure_warning,
    field_summary,
    resolve_cutoffs,
)
from tit.plotting.nilearn.config import NilearnConfig, NilearnSubjectSimulation


@pytest.fixture
def field() -> np.ndarray:
    """A TI-shaped field: 10 000 non-zero voxels, max 0.1385 V/m, heavy low tail."""
    rng = np.random.default_rng(20260904)
    values = rng.gamma(shape=1.5, scale=0.012, size=10_000)
    return np.clip(values, 1e-6, 0.1385)


@pytest.mark.unit
class TestDefaults:
    def test_the_config_default_is_not_a_fixed_voltage(self):
        cfg = NilearnConfig(
            subject_simulation_pairs=[NilearnSubjectSimulation("ernie", "L_Insula")]
        )
        assert cfg.min_cutoff is None
        assert cfg.max_cutoff is None

    def test_unset_cutoffs_come_from_the_field(self, field):
        lo, hi = resolve_cutoffs(field, None, None)
        assert lo == pytest.approx(float(np.percentile(field, DEFAULT_MIN_PERCENTILE)))
        assert hi == pytest.approx(float(np.percentile(field, DEFAULT_MAX_PERCENTILE)))
        assert lo < hi <= float(field.max())

    def test_the_old_fixed_default_would_have_been_above_this_field(self, field):
        """The exact condition that killed job 287e3e0c2eb94134."""
        assert 0.3 > float(field.max())
        with pytest.raises(ValueError):
            resolve_cutoffs(field, 0.3, None)

    def test_an_explicit_cutoff_still_wins(self, field):
        lo, hi = resolve_cutoffs(field, 0.01, 0.12)
        assert (lo, hi) == (0.01, 0.12)


@pytest.mark.unit
class TestPreflightMessage:
    def _message(self, field, min_cutoff, max_cutoff=None, **kw) -> str:
        with pytest.raises(ValueError) as excinfo:
            resolve_cutoffs(field, min_cutoff, max_cutoff, **kw)
        return str(excinfo.value)

    def test_it_names_the_data_range(self, field):
        msg = self._message(field, 0.3)
        assert f"{float(field.max()):.4f}" in msg
        assert f"{float(field.min()):.4f}" in msg
        assert f"{field.size} non-zero voxels" in msg

    def test_it_names_the_cutoff_that_was_asked_for(self, field):
        assert "min_cutoff 0.3000 V/m" in self._message(field, 0.3)

    def test_it_names_the_data_driven_default_as_the_way_out(self, field):
        msg = self._message(field, 0.3)
        assert f"{float(np.percentile(field, DEFAULT_MIN_PERCENTILE)):.4f}" in msg
        assert "use_percentiles" in msg

    def test_it_is_readable_prose_not_a_matplotlib_error(self, field):
        msg = self._message(field, 0.3)
        assert "minvalue" not in msg
        assert "Traceback" not in msg

    def test_an_empty_field_is_refused_by_name(self):
        msg = self._message(np.array([]), None)
        assert "no non-zero field values" in msg


@pytest.mark.unit
class TestPercentileMode:
    def test_both_cutoffs_are_read_as_percentiles(self, field):
        lo, hi = resolve_cutoffs(field, 95.0, 99.0, use_percentiles=True)
        assert lo == pytest.approx(float(np.percentile(field, 95.0)))
        assert hi == pytest.approx(float(np.percentile(field, 99.0)))

    def test_unset_percentiles_fall_back_to_the_defaults(self, field):
        assert resolve_cutoffs(
            field, None, None, use_percentiles=True
        ) == pytest.approx(resolve_cutoffs(field, None, None))

    def test_an_inverted_percentile_pair_is_refused(self, field):
        with pytest.raises(ValueError, match="display range is empty"):
            resolve_cutoffs(field, 99.0, 50.0, use_percentiles=True)


@pytest.mark.unit
class TestFieldSummary:
    def test_it_reports_the_percentiles_the_defaults_use(self, field):
        summary = field_summary(field)
        for pct in (50.0, DEFAULT_MIN_PERCENTILE, DEFAULT_MAX_PERCENTILE):
            assert f"{float(np.percentile(field, pct)):.4f}" in summary

    def test_an_empty_field_does_not_crash_the_summary(self):
        assert "no non-zero voxels" in field_summary(np.array([]))


@pytest.mark.unit
class TestBlankFigureWarning:
    """A floor above the data with a ceiling above *that* is the silent half of the bug.

    ``resolve_cutoffs`` only refuses ``min >= max``. The desktop panel's former default
    sends ``min_cutoff`` 0.3 with ``max_cutoff`` 5 (`tests/smoke/payloads/nilearn.json`),
    which passes that check and then renders PDFs with nothing on them -- the same failure
    as the crash, only silent. The runner logs this line so the job log says why.
    """

    def test_a_floor_above_the_peak_is_called_out(self, field):
        msg = blank_figure_warning(field, 0.3)
        assert msg is not None
        assert f"{float(field.max()):.4f} V/m" in msg
        assert f"{float(np.percentile(field, DEFAULT_MIN_PERCENTILE)):.4f}" in msg

    def test_the_data_driven_default_never_warns(self, field):
        lo, _hi = resolve_cutoffs(field, None, None)
        assert blank_figure_warning(field, lo) is None

    def test_a_floor_exactly_at_the_peak_still_warns(self, field):
        assert blank_figure_warning(field, float(field.max())) is not None

    def test_an_empty_field_has_nothing_to_warn_about(self):
        assert blank_figure_warning(np.array([]), 0.3) is None
