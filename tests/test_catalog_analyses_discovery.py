"""``tit.catalog`` finds an analysis wherever the runner wrote it (lane FX3).

The failure this pins: :meth:`tit.analyzer.Analyzer._resolve_output_dir` honours
``output_dir`` verbatim -- it is a documented argument of the public scripting API -- but
:func:`tit.catalog.analyses` used to scan only ``Analyses/Mesh`` and ``Analyses/Voxel``.
A run with any other output directory finished, wrote its ``analysis.json`` and
``results.csv``, and was then invisible to ``GET /api/catalog/analyses`` and to Results
(lane S1 hit this and had to move its own smoke row into ``Analyses/<Space>/``).

The fix reads what the runner wrote: any directory under the simulation holding both
``analysis.json`` and ``results.csv`` is an analysis. Names are unchanged for the two
standard locations -- existing clients and the ``/api/catalog/analyses/{name}/summary``
URL keep working -- and a run found elsewhere is named by its path relative to the
simulation, with the separators flattened so the name still works as a URL path segment
(measured: a name containing ``/`` misses that route even percent-encoded, and the server
answers the router's ``{"detail":"Not found"}``).

Reproduce: ``python3 -m pytest -q tests/test_catalog_analyses_discovery.py``
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tit import catalog
from tit.paths import PathManager

_ANALYSIS_JSON = {
    "field_name": "TI_max",
    "regions": ["Left-Thalamus"],
    "coordinate_space": "subject",
}


def _write_analysis(directory: str, field: str = "TI_max") -> str:
    """The pair :mod:`tit.analyzer` writes: this is what makes a directory an analysis."""
    os.makedirs(directory, exist_ok=True)
    Path(directory, "analysis.json").write_text(
        json.dumps({**_ANALYSIS_JSON, "field_name": field})
    )
    Path(directory, "results.csv").write_text(f"Metric,Value\nfield_name,{field}\n")
    return directory


@pytest.fixture()
def pm(tmp_path: Path) -> PathManager:
    """One subject ``ernie`` with one simulation ``L_Insula`` and no analyses yet."""
    pm = PathManager(project_dir=str(tmp_path))
    os.makedirs(pm.m2m("ernie"))
    sim = pm.simulation("ernie", "L_Insula")
    # The bulk output a real simulation directory carries; none of it is an analysis.
    for sub in ("TI/niftis", "TI/mesh", "documentation", "high_Frequency/mesh"):
        os.makedirs(os.path.join(sim, sub))
    Path(sim, "documentation", "config.json").write_text("{}")
    (tmp_path / "dataset_description.json").write_text("{}")
    return pm


@pytest.mark.unit
class TestStandardLocations:
    def test_mesh_and_voxel_runs_keep_their_bare_names(self, pm: PathManager) -> None:
        sim = pm.simulation("ernie", "L_Insula")
        _write_analysis(os.path.join(sim, "Analyses", "Mesh", "sphere_r10"))
        _write_analysis(os.path.join(sim, "Analyses", "Voxel", "cortical_aparc"))

        names = [a["name"] for a in catalog.analyses(pm, "ernie", "L_Insula")]
        assert names == ["sphere_r10", "cortical_aparc"]

    def test_a_directory_without_both_files_is_not_an_analysis(
        self, pm: PathManager
    ) -> None:
        sim = pm.simulation("ernie", "L_Insula")
        half = os.path.join(sim, "Analyses", "Mesh", "aborted")
        os.makedirs(half)
        Path(half, "analysis.json").write_text("{}")

        assert catalog.analyses(pm, "ernie", "L_Insula") == []


@pytest.mark.unit
class TestCustomOutputDir:
    def test_a_run_outside_mesh_and_voxel_is_still_listed(
        self, pm: PathManager
    ) -> None:
        sim = pm.simulation("ernie", "L_Insula")
        _write_analysis(os.path.join(sim, "Analyses", "Custom", "smoke-1"))

        entries = catalog.analyses(pm, "ernie", "L_Insula")
        assert [e["name"] for e in entries] == ["Analyses__Custom__smoke-1"]
        assert entries[0]["csv"].endswith(
            os.path.join("Analyses", "Custom", "smoke-1", "results.csv")
        )

    def test_a_run_directly_under_the_simulation_is_listed(
        self, pm: PathManager
    ) -> None:
        sim = pm.simulation("ernie", "L_Insula")
        _write_analysis(os.path.join(sim, "my_scratch_analysis"))

        assert [a["name"] for a in catalog.analyses(pm, "ernie", "L_Insula")] == [
            "my_scratch_analysis"
        ]

    def test_standard_runs_come_first_and_keep_their_order(
        self, pm: PathManager
    ) -> None:
        sim = pm.simulation("ernie", "L_Insula")
        _write_analysis(os.path.join(sim, "Analyses", "Custom", "aaa"))
        _write_analysis(os.path.join(sim, "Analyses", "Voxel", "zzz"))
        _write_analysis(os.path.join(sim, "Analyses", "Mesh", "mmm"))

        assert [a["name"] for a in catalog.analyses(pm, "ernie", "L_Insula")] == [
            "mmm",
            "zzz",
            "Analyses__Custom__aaa",
        ]

    def test_a_custom_name_cannot_collide_with_a_standard_one(
        self, pm: PathManager
    ) -> None:
        sim = pm.simulation("ernie", "L_Insula")
        _write_analysis(os.path.join(sim, "Analyses", "Mesh", "run1"), field="TI_max")
        _write_analysis(
            os.path.join(sim, "Analyses", "Custom", "run1"), field="TI_norm"
        )

        by_name = {a["name"]: a for a in catalog.analyses(pm, "ernie", "L_Insula")}
        assert set(by_name) == {"run1", "Analyses__Custom__run1"}
        assert by_name["run1"]["field"] == "TI_max"
        assert by_name["Analyses__Custom__run1"]["field"] == "TI_norm"

    def test_every_listed_name_is_one_url_path_segment(self, pm: PathManager) -> None:
        """A ``/`` in a name is unreachable, not just ugly.

        ``GET /api/catalog/analyses/{name}/summary`` takes the name as a path segment;
        the client percent-encodes it and the ASGI server decodes ``%2F`` back to ``/``
        before routing, so a slashed name misses the route and answers the router's
        ``{"detail":"Not found"}`` (measured against the dev container, 2026-09-03) --
        i.e. an analysis that is listed but whose summary can never be fetched.
        """
        sim = pm.simulation("ernie", "L_Insula")
        _write_analysis(os.path.join(sim, "Analyses", "Mesh", "standard"))
        _write_analysis(os.path.join(sim, "Analyses", "Custom", "deep", "run1"))
        _write_analysis(os.path.join(sim, "scratch"))

        names = [a["name"] for a in catalog.analyses(pm, "ernie", "L_Insula")]
        assert names == ["standard", "Analyses__Custom__deep__run1", "scratch"]
        assert not any("/" in name for name in names)


@pytest.mark.unit
class TestSummaryLookup:
    def test_summary_resolves_a_standard_name(self, pm: PathManager) -> None:
        sim = pm.simulation("ernie", "L_Insula")
        _write_analysis(os.path.join(sim, "Analyses", "Mesh", "sphere_r10"))

        table = catalog.analysis_summary(pm, "ernie", "L_Insula", "sphere_r10")
        assert table["columns"] == ["Metric", "Value"]

    def test_summary_resolves_a_custom_name(self, pm: PathManager) -> None:
        sim = pm.simulation("ernie", "L_Insula")
        _write_analysis(os.path.join(sim, "Analyses", "Custom", "smoke-1"))

        table = catalog.analysis_summary(
            pm, "ernie", "L_Insula", "Analyses__Custom__smoke-1"
        )
        assert table["rows"] == [["field_name", "TI_max"]]

    def test_summary_also_resolves_the_runs_own_relative_path(
        self, pm: PathManager
    ) -> None:
        """The string a script already holds (``output_dir`` relative to the simulation)
        resolves without the caller having to flatten it first."""
        sim = pm.simulation("ernie", "L_Insula")
        _write_analysis(os.path.join(sim, "Analyses", "Custom", "smoke-1"))

        table = catalog.analysis_summary(
            pm, "ernie", "L_Insula", "Analyses/Custom/smoke-1"
        )
        assert table["rows"] == [["field_name", "TI_max"]]

    def test_an_unknown_name_is_none(self, pm: PathManager) -> None:
        assert catalog.analysis_summary(pm, "ernie", "L_Insula", "nope") is None


@pytest.mark.unit
class TestWalkCost:
    def test_an_analysis_is_not_descended_into(self, pm: PathManager) -> None:
        """A directory inside an analysis is part of it, not a second analysis."""
        sim = pm.simulation("ernie", "L_Insula")
        outer = _write_analysis(os.path.join(sim, "Analyses", "Mesh", "run1"))
        _write_analysis(os.path.join(outer, "nested"))

        assert [a["name"] for a in catalog.analyses(pm, "ernie", "L_Insula")] == [
            "run1"
        ]

    def test_the_simulation_root_is_not_its_own_analysis(self, pm: PathManager) -> None:
        _write_analysis(pm.simulation("ernie", "L_Insula"))

        assert catalog.analyses(pm, "ernie", "L_Insula") == []
