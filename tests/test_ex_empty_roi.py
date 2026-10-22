"""An ex/mEx ROI that selects no leadfield element fails before the search; the report survives
degenerate rankings.

Pins (2026-10-22):

* Engine and runners. Every metric of an empty ROI is undefined (a mean over nothing), and
  ``tit/opt/ex/ex.py`` says "a misplaced ROI is invisible in every number this search produces".
  ``ExSearchEngine._find_roi_elements`` used to log "Found 0 ROI elements" and go on; ``_roi_metrics``
  then scored every montage 0, the search "succeeded" with an arbitrary ranking, and the report
  was lost to a ``ZeroDivisionError``. Now ``initialize()`` raises a ``ValueError`` that names the
  ROI and its 0-element count, ``run_ex_search``/``run_m_ex_search`` leave no
  ``final_output.csv``/``run_config.json``, and ``python -m tit.opt.ex`` exits 1 with that sentence.
* Report (``tit/reporting/generators/ex_search.py``). ``density_chart`` used to divide by the
  range of ROI means and focalities (zero for one row, or for all-zero rows) and ``int()`` a NaN.
  It now draws those cases with the winner inside the plot; rows whose numbers are not finite
  are left out and the page says how many; an unparsable montage cell is skipped; a single row is
  the search median; an all-zero results file is refused with a ``ValueError`` naming the ROI.

Expected values are hand-derived: a five-element fake mesh with barycentres at (0,0,0), (1,0,0),
(0,1,0), (20,0,0), (0,20,0) mm; a 3 mm sphere at the origin holds the first three (distance
<= 3), one at (60,0,0) holds none (nearest is 40 mm away). Chart geometry: 720x380 SVG, plot area
x in [50, 704], y in [16, 340] (``density_chart``'s margins).

Reproduce: ``.venv/bin/python -m pytest tests/test_ex_empty_roi.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

CENTRES = np.array(
    [
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [20.0, 0.0, 0.0],
        [0.0, 20.0, 0.0],
    ]
)
_FIELDS = "TImax_ROI,TImean_ROI,TImean_GM,Focality,Composite_Index"
_HEADER = f"Montage,Current_Ch1_mA,Current_Ch2_mA,{_FIELDS}"


def _mesh():
    return SimpleNamespace(
        elements_baricenters=lambda: SimpleNamespace(value=CENTRES),
        elements_volumes_and_areas=lambda: SimpleNamespace(value=np.ones(len(CENTRES))),
        elm=SimpleNamespace(tag1=np.array([2, 2, 1, 2, 2])),
    )


def _no_search_ti():
    def never(*args, **kwargs):
        raise AssertionError("the search started on an empty ROI")

    return SimpleNamespace(
        load_leadfield=lambda path: (np.zeros(1), _mesh(), None),
        get_field=never,
        get_maxTI=never,
    )


@pytest.fixture
def fake_ti(monkeypatch):
    import tit.opt.ex.engine as engine_mod
    import tit.opt.mex.engine as mex_mod

    ti = _no_search_ti()
    monkeypatch.setattr(engine_mod, "TI", ti)
    monkeypatch.setattr(mex_mod, "TI", ti)
    return ti


def _engine(roi_file, roi_name="target.csv"):
    from tit.opt.ex.engine import ExSearchEngine

    return ExSearchEngine("/lf.hdf5", roi_file, roi_name, MagicMock())


# ── engine ──────────────────────────────────────────────────────────────


def test_a_sphere_on_the_mesh_finds_its_elements(fake_ti, tmp_path):
    """Control: the sphere test counts what it should, so the refusal below is not a blanket one."""
    roi = tmp_path / "near.csv"
    roi.write_text("0,0,0\n")
    engine = _engine(str(roi))
    engine.initialize(roi_radius=3.0)
    assert sorted(engine.roi_indices.tolist()) == [0, 1, 2]


def test_a_sphere_outside_the_mesh_is_refused_before_the_search(fake_ti, tmp_path):
    roi = tmp_path / "far.csv"
    roi.write_text("60,0,0\n")
    engine = _engine(str(roi), roi_name="far.csv")
    with pytest.raises(ValueError, match=r"far\.csv") as err:
        engine.initialize(roi_radius=3.0)
    assert re.search(r"\b0 (leadfield )?(mesh )?elements\b", str(err.value)), err.value


def _atlas(monkeypatch, label_voxel):
    """A 4x4x4 atlas, identity affine, label 17 at *label_voxel* only (nibabel is mocked here)."""
    data = np.zeros((4, 4, 4))
    data[label_voxel] = 17
    img = SimpleNamespace(get_fdata=lambda: data, affine=np.eye(4))
    monkeypatch.setattr(sys.modules["nibabel"], "load", lambda path: img, raising=False)


def test_an_atlas_label_that_covers_an_element_is_kept(fake_ti, monkeypatch):
    _atlas(monkeypatch, (1, 0, 0))  # element 1's barycentre is voxel (1, 0, 0)
    engine = _engine([("/atlas.nii.gz", 17)], roi_name="Left-Thalamus.csv")
    engine.initialize(roi_radius=3.0)
    assert engine.roi_indices.tolist() == [1]


def test_an_atlas_label_that_misses_every_element_is_refused(fake_ti, monkeypatch):
    _atlas(monkeypatch, (3, 3, 3))  # no barycentre maps to voxel (3, 3, 3)
    engine = _engine([("/atlas.nii.gz", 17)], roi_name="Left-Thalamus.csv")
    with pytest.raises(ValueError, match="Left-Thalamus") as err:
        engine.initialize(roi_radius=3.0)
    assert re.search(r"\b0 (leadfield )?(mesh )?elements\b", str(err.value))


# ── runners ─────────────────────────────────────────────────────────────


def _pm(tmp_path):
    pm = MagicMock()
    pm.project_dir = str(tmp_path)
    pm.logs.return_value = str(tmp_path / "logs")
    pm.ex_search_run.return_value = str(tmp_path / "ex-run")
    pm.m_ex_search_run.return_value = str(tmp_path / "mex-run")
    pm.rois.return_value = str(tmp_path / "rois")
    pm.leadfields.return_value = str(tmp_path / "leadfields")
    pm.m2m.return_value = str(tmp_path / "m2m_001")
    (tmp_path / "rois").mkdir()
    (tmp_path / "rois" / "far.csv").write_text("60,0,0\n")
    return pm


def _assert_no_run(run_dir: Path):
    assert not (run_dir / "final_output.csv").exists()
    assert not (run_dir / "run_config.json").exists()


def test_run_ex_search_refuses_an_empty_roi_and_writes_no_run(fake_ti, tmp_path):
    from tit.opt.config import ExConfig
    from tit.opt.ex.ex import run_ex_search

    config = ExConfig(
        subject_id="001",
        leadfield_hdf="001_leadfield_NET.hdf5",
        roi_name="far.csv",
        electrodes=ExConfig.PoolElectrodes(electrodes=["A", "B", "C", "D"]),
        n_jobs=1,
    )
    with (
        patch("tit.opt.ex.ex.get_path_manager", return_value=_pm(tmp_path)),
        patch("tit.opt.ex.ex.add_file_handler"),
        pytest.raises(ValueError, match=r"far\.csv"),
    ):
        run_ex_search(config)
    _assert_no_run(tmp_path / "ex-run")


def test_run_m_ex_search_refuses_an_empty_roi_and_writes_no_run(fake_ti, tmp_path):
    from tit.opt.config import MExConfig
    from tit.opt.mex.mex import run_m_ex_search

    config = MExConfig(
        subject_id="001",
        leadfield_hdf="001_leadfield_NET.hdf5",
        roi_name="far.csv",
        electrodes=MExConfig.PoolElectrodes(electrodes=list("ABCDEFGH")),
        current_mA=1.0,
        n_jobs=1,
    )
    with (
        patch("tit.opt.mex.mex.get_path_manager", return_value=_pm(tmp_path)),
        patch("tit.opt.mex.mex.add_file_handler"),
        pytest.raises(ValueError, match=r"far\.csv"),
    ):
        run_m_ex_search(config)
    _assert_no_run(tmp_path / "mex-run")


def test_the_ex_runner_exits_1_with_the_empty_roi_sentence(fake_ti, tmp_path):
    from tit.opt.ex.__main__ import main

    project = tmp_path / "project"
    rois = project / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001" / "ROIs"
    rois.mkdir(parents=True)
    (rois / "far.csv").write_text("60,0,0\n")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "project_dir": str(project),
                "subject_id": "001",
                "leadfield_hdf": "001_leadfield_NET.hdf5",
                "roi_name": "far.csv",
                "run_name": "empty",
                "n_jobs": 1,
                "electrodes": {"_type": "PoolElectrodes", "electrodes": list("ABCD")},
            }
        )
    )
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger("tit.opt.ex_search")
    logger.addHandler(handler)
    try:
        with (
            patch("tit.opt.ex.__main__._make_stdout_logger"),
            patch("tit.opt.ex.ex.add_file_handler"),
            patch.object(sys, "argv", ["prog", str(config)]),
            pytest.raises(SystemExit) as exit_info,
        ):
            main()
    finally:
        logger.removeHandler(handler)
    assert exit_info.value.code == 1
    errors = [r.getMessage() for r in records if r.levelno >= logging.ERROR]
    assert any(
        "far.csv" in m and re.search(r"\b0 .*elements\b", m) for m in errors
    ), errors
    run_dir = project / "derivatives" / "SimNIBS" / "sub-001" / "ex-search" / "empty"
    _assert_no_run(run_dir)


# ── report: degenerate rankings ─────────────────────────────────────────


def _row(mean, foc, timax=None, montage=("AF3", "PO10", "AF4", "Oz")):
    a, b, c, d = montage
    return {
        "TImean_ROI": mean,
        "Focality": foc,
        "Composite_Index": mean * foc,
        "TImax_ROI": 2 * mean if timax is None else timax,
        "TImean_GM": 0.05,
        "I1": 1.0,
        "I2": 1.0,
        "pairs": [[a, b], [c, d]],
    }


_WINNER = re.compile(r'<circle cx="([-\d.]+)" cy="([-\d.]+)" r="6" fill="var\(--s2\)"')


def _winner_xy(svg: str) -> tuple[float, float]:
    (match,) = _WINNER.findall(svg)
    return float(match[0]), float(match[1])


@pytest.mark.parametrize(
    "rows",
    [
        pytest.param([_row(0.1, 0.0)], id="one row, focality 0"),
        pytest.param([_row(0.0, 0.0), _row(0.0, 0.0)], id="all-zero rows"),
        pytest.param([_row(0.12, 1.1)], id="one ordinary row"),
    ],
)
def test_density_chart_draws_degenerate_rankings_with_the_winner_inside(rows):
    from tit.reporting.generators import ex_search

    svg = ex_search.density_chart(rows)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "nan" not in svg.lower() and "inf" not in svg.lower()
    x, y = _winner_xy(svg)
    assert 50 <= x <= 704 and 16 <= y <= 340


def _run_dir(tmp_path: Path, lines: list[str], cfg: dict | None = None) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    (run / "run_config.json").write_text(
        json.dumps(
            cfg
            or {
                "subject_id": "X",
                "roi_name": "thal.csv",
                "roi_radius": 3.0,
                "leadfield_hdf": "X_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
                "electrode_mode": "pool",
                "electrodes": {"electrodes": ["AF3", "PO10", "AF4", "Oz", "F3"]},
                "total_current_mA": 2.0,
                "current_step_mA": 0.5,
                "channel_limit_mA": 1.5,
            }
        )
    )
    (run / "final_output.csv").write_text("\n".join([_HEADER, *lines]) + "\n")
    return run


def _html(run: Path) -> str:
    from tit.reporting.generators import ex_search

    with patch("tit.tools.montage_visualizer.montage_webp", return_value=None):
        return ex_search.build_html(ex_search.collect(run), "X")


def test_rows_with_non_finite_numbers_are_left_out_and_counted(tmp_path):
    run = _run_dir(
        tmp_path,
        [
            "AF3_PO10 <> AF4_Oz_I1-1.0mA_I2-1.0mA,1.0,1.0,0.2,0.1,0.05,2.0,0.2",
            "F3_PO10 <> AF4_Oz_I1-1.0mA_I2-1.0mA,1.0,1.0,0.3,0.15,0.05,nan,0.3",
            "F3_PO10 <> AF3_Oz_I1-1.0mA_I2-1.0mA,1.0,1.0,0.3,0.15,0.05,inf,0.3",
            "AF3_F3 <> AF4_Oz_I1-1.0mA_I2-1.0mA,1.0,1.0,0.1,0.05,0.05,1.0,0.05",
        ],
    )
    html = _html(run)
    # Two finite rows remain; the winner is the 0.2-composite AF3-PO10 row.
    assert "leads 2 montages" in html
    assert "AF3–PO10 ‖ AF4–Oz leads" in html
    assert re.search(
        r"\b2 rows?\b[^<]*(left out|not finite|dropped)", html
    ), "no drop note"
    assert "nan" not in _density(html).lower()


def _density(html: str) -> str:
    return html.split('<svg class="chart"', 1)[1].split("</svg>", 1)[0]


def test_an_unparsable_montage_cell_is_skipped_not_a_crash(tmp_path):
    run = _run_dir(
        tmp_path,
        [
            "AF3_PO10 <> AF4_Oz_I1-1.0mA_I2-1.0mA,1.0,1.0,0.2,0.1,0.05,2.0,0.2",
            "garbage,1.0,1.0,0.9,0.9,0.05,9.0,8.1",
        ],
    )
    html = _html(run)
    assert "leads 1 montages" in html or "leads 1 montage" in html
    assert "AF3–PO10 ‖ AF4–Oz" in html
    assert re.search(
        r"\b1 row\b[^<]*(left out|not finite|dropped|could not be read)", html
    )


def test_a_single_row_is_its_own_search_median(tmp_path):
    run = _run_dir(
        tmp_path,
        ["AF3_PO10 <> AF4_Oz_I1-1.0mA_I2-1.0mA,1.0,1.0,0.25,0.125,0.05,2.5,0.3125"],
    )
    html = _html(run)
    assert "search median 0.125 V/m" in html


def test_two_rows_report_the_mean_of_the_middle_pair_as_median(tmp_path):
    # Median of {0.1, 0.3} is 0.2 by definition; the upper-middle element would say 0.3.
    run = _run_dir(
        tmp_path,
        [
            "AF3_PO10 <> AF4_Oz_I1-1.0mA_I2-1.0mA,1.0,1.0,0.6,0.3,0.05,2.0,0.6",
            "F3_PO10 <> AF4_Oz_I1-1.0mA_I2-1.0mA,1.0,1.0,0.2,0.1,0.05,1.0,0.1",
        ],
    )
    assert "search median 0.200 V/m" in _html(run)


def test_an_all_zero_results_file_is_refused_naming_the_roi(tmp_path):
    from tit.reporting.generators import ex_search

    run = _run_dir(
        tmp_path,
        [
            "AF3_PO10 <> AF4_Oz_I1-1.0mA_I2-1.0mA,1.0,1.0,0.0,0.0,0.0,0.0,0.0",
            "F3_PO10 <> AF4_Oz_I1-1.0mA_I2-1.0mA,1.0,1.0,0.0,0.0,0.0,0.0,0.0",
        ],
    )
    with pytest.raises(ValueError, match=r"thal\.csv") as err:
        ex_search.create_ex_search_report(tmp_path, "X", run, out_dir=tmp_path / "out")
    assert "scored 0" in str(err.value) and not (tmp_path / "out").exists()


def test_a_run_with_one_scoring_montage_is_still_reported(tmp_path):
    """The all-zero refusal is about the whole file: one non-zero row makes a real ranking."""
    from tit.reporting.generators import ex_search

    run = _run_dir(
        tmp_path,
        [
            "AF3_PO10 <> AF4_Oz_I1-1.0mA_I2-1.0mA,1.0,1.0,0.0,0.0,0.0,0.0,0.0",
            "F3_PO10 <> AF4_Oz_I1-1.0mA_I2-1.0mA,1.0,1.0,0.02,0.01,0.05,0.2,0.002",
        ],
    )
    with patch("tit.tools.montage_visualizer.montage_webp", return_value=None):
        path = ex_search.create_ex_search_report(
            tmp_path, "X", run, out_dir=tmp_path / "out"
        )
    assert "F3–PO10 ‖ AF4–Oz leads 2 montages" in path.read_text()
