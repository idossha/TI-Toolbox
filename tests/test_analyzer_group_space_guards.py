"""Sphere coordinate spaces are checked in the library, not only in the desktop (2026-10-31).

What this pins
    * A group spherical analysis is one sphere for every subject, so its centre must be MNI:
      ``AnalyzerConfig`` (the job path) and ``run_group_analysis`` (the Python path) refuse
      subject coordinates, as they already refused a subject-space group mask. Before, only the
      desktop UI refused it and every subject was analysed at the same subject-space point.
    * ``coordinate_space`` is ``"subject"`` or ``"mni"`` (any case). Anything else
      (``"MNI152"``) used to fall through to subject space silently; ``analyze_sphere``,
      ``analyze_spheres`` and ``run_group_analysis`` now raise ``ValueError``.
    * ``run_group_analysis(analysis_type="spherical")`` with neither ``center`` nor ``spheres``
      is a ``ValueError`` (it was a ``TypeError`` from unpacking ``None``); a subject's missing
      region (``KeyError``) names the subject, as its ``ValueError`` already did.

Where the expectations come from: the rule as the desktop and the group-mask check state it;
the surface is a ten-node line authored here, so a subject-space sphere has statistics and only
the space can refuse it.

Run: .venv/bin/python -m pytest tests/test_analyzer_group_space_guards.py -q -p no:cacheprovider
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tit.analyzer.analyzer import Analyzer
from tit.analyzer.config import AnalyzerConfig
from tit.analyzer.group import run_group_analysis


def test_config_refuses_a_group_sphere_in_subject_coordinates() -> None:
    with pytest.raises(ValueError, match="coordinate_space"):
        AnalyzerConfig(
            mode="group",
            subject_ids=["a", "b"],
            analysis_type="spherical",
            center=[0.0, 0.0, 0.0],
            radius=5.0,
            coordinate_space="subject",
        )
    # The same sphere in MNI coordinates, and a single-subject sphere in its own space, stand.
    AnalyzerConfig(
        mode="group",
        subject_ids=["a", "b"],
        analysis_type="spherical",
        center=[0.0, 0.0, 0.0],
        radius=5.0,
        coordinate_space="mni",
    )
    AnalyzerConfig(subject_id="a", center=[0.0, 0.0, 0.0], radius=5.0)


@pytest.fixture()
def group_analyzer(tmp_path):
    """The ``Analyzer`` class ``run_group_analysis`` sees, mocked (its sphere check is real)."""
    with (
        patch("tit.analyzer.group.Analyzer") as cls,
        patch("tit.analyzer.group.add_file_handler"),
        patch("tit.analyzer.group._resolve_output_dir", return_value=tmp_path),
        patch("tit.analyzer.group._build_summary_df"),
        patch("tit.analyzer.group._generate_comparison_plot"),
    ):
        cls._checked_spheres = Analyzer._checked_spheres
        yield cls


def _group(**kwargs):
    args = dict(
        subject_ids=["001", "002"],
        simulation="sim1",
        analysis_type="spherical",
        center=(10.0, 20.0, 30.0),
        radius=5.0,
        coordinate_space="MNI",
    )
    args.update(kwargs)
    return run_group_analysis(**args)


@pytest.mark.parametrize("space", ["subject", "Subject"])
def test_run_group_analysis_refuses_a_subject_space_sphere_before_any_subject(
    space,
) -> None:
    with (
        patch("tit.analyzer.group.Analyzer") as cls,
        patch("tit.analyzer.group._resolve_output_dir") as out,
        patch("tit.analyzer.group.add_file_handler"),  # nothing on disk if it ever ran
    ):
        cls._checked_spheres = Analyzer._checked_spheres
        with pytest.raises(ValueError, match="coordinate_space"):
            run_group_analysis(
                ["001", "002"],
                "sim1",
                center=(1.0, 2.0, 3.0),
                radius=5.0,
                coordinate_space=space,
            )
        with pytest.raises(ValueError, match="coordinate_space"):
            run_group_analysis(
                ["001"], "sim1", spheres=[(1, 2, 3, 4)], coordinate_space=space
            )
    cls.assert_not_called()
    out.assert_not_called()


@pytest.mark.parametrize("space", ["MNI152", "mni305", "native", ""])
def test_run_group_analysis_refuses_an_unknown_coordinate_space(space) -> None:
    with (
        patch("tit.analyzer.group.Analyzer") as cls,
        patch("tit.analyzer.group._resolve_output_dir") as out,
        patch("tit.analyzer.group.add_file_handler"),  # nothing on disk if it ever ran
    ):
        cls._checked_spheres = Analyzer._checked_spheres
        with pytest.raises(ValueError, match="coordinate_space"):
            run_group_analysis(
                ["001"],
                "sim1",
                center=(1.0, 2.0, 3.0),
                radius=5.0,
                coordinate_space=space,
            )
    cls.assert_not_called()
    out.assert_not_called()


def test_a_group_sphere_in_mni_coordinates_still_runs(group_analyzer) -> None:
    _group(coordinate_space="mni")
    assert group_analyzer.return_value.analyze_sphere.call_count == 2


def test_a_group_sphere_without_a_centre_is_a_value_error() -> None:
    with patch("tit.analyzer.group.Analyzer") as cls:
        cls._checked_spheres = Analyzer._checked_spheres
        with pytest.raises(ValueError, match="center"):
            run_group_analysis(["001"], "sim1", coordinate_space="MNI")
        with pytest.raises(ValueError, match="center"):
            run_group_analysis(
                ["001"], "sim1", center=(1.0, 2.0, 3.0), coordinate_space="MNI"
            )
    cls.assert_not_called()


def test_a_subjects_missing_region_names_the_subject(group_analyzer) -> None:
    group_analyzer.return_value.analyze_cortex.side_effect = KeyError(
        "Region 'lh.nowhere' not found in atlas."
    )
    with pytest.raises(KeyError) as raised:
        _group(
            analysis_type="cortical",
            atlas="DK40",
            region="lh.nowhere",
            center=None,
            radius=None,
        )
    assert raised.value.args[0] == "sub-001: Region 'lh.nowhere' not found in atlas."


def _line_analyzer(tmp_path: Path) -> Analyzer:
    """A mesh analyzer on ten unit-area nodes along x (field 2 V/m at x <= 3, 1 elsewhere)."""
    x = np.arange(10.0)
    analyzer = object.__new__(Analyzer)
    analyzer.space, analyzer.field_name, analyzer.tissue_type = "mesh", "TI_max", "GM"
    analyzer.field_path = tmp_path / "M1_TI.msh"
    analyzer.output_dir = str(tmp_path / "out")
    analyzer._pm = SimpleNamespace(ensure=lambda p: Path(p).mkdir(parents=True) or p)
    analyzer._is_mti = False
    analyzer._surface_mesh = SimpleNamespace(
        nodes=SimpleNamespace(node_coord=np.c_[x, np.zeros(10), np.zeros(10)]),
        field={"TI_max": SimpleNamespace(value=np.where(x <= 3, 2.0, 1.0))},
        nodes_areas=lambda: np.ones(10),
    )
    analyzer._surface_mesh_path = tmp_path / "M1_TI_central.msh"
    analyzer._get_normal_stats = lambda *a: None
    return analyzer


@pytest.mark.parametrize("space", ["MNI152", "mni305", "native"])
def test_analyze_sphere_and_spheres_refuse_an_unknown_coordinate_space(
    tmp_path, space
) -> None:
    analyzer = _line_analyzer(tmp_path)
    with pytest.raises(ValueError, match="coordinate_space"):
        analyzer.analyze_sphere((1.5, 0.0, 0.0), 2.0, coordinate_space=space)
    with pytest.raises(ValueError, match="coordinate_space"):
        analyzer.analyze_spheres([(1.5, 0.0, 0.0, 2.0)], coordinate_space=space)


@pytest.mark.parametrize("space", ["subject", "SUBJECT"])
def test_subject_coordinates_in_any_case_are_analysed(tmp_path, space) -> None:
    result = _line_analyzer(tmp_path).analyze_sphere(
        (1.5, 0.0, 0.0), 2.0, coordinate_space=space
    )
    assert result.n_elements == 4 and result.roi_mean == 2.0  # nodes x = 0..3
