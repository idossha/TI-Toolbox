"""Blender exports of an mTI simulation read the files that simulation actually wrote.

What this pins (2026-10-22): a TI run writes its central surface to
``TI/mesh/surfaces/<sim>_TI_central.msh``; an mTI run writes ONLY
``mTI/mesh/surfaces/<sim>_mTI_central.msh`` (``tit/sim/mTI.py`` runs ``msh2cortex`` on
``<sim>_mTI.msh`` into ``dirs["mti_surfaces"]``; ``tit/sim/utils.py`` names that directory), and
its envelope field is spelled ``mTI_max``. Its carrier meshes are renamed ``TDCS_1..N`` ->
``TDCS_A..`` when the run files them (``MTISimulation._organize_files``). The region, vector and
montage exporters used to hard-code the TI surface (and the vector exporter TDCS_1..4), so every
mTI export failed reading a file the run never writes.

Where the expected values come from: the paths are spelled out here from that simulator layout,
never asked of ``PathManager`` or the exporters; the mTI envelope over N channels is
``tit.calc.get_TI_vectors`` over all N fields (the same call ``tit/sim/mTI.py`` makes for
``mTI_max``), a second implementation the exporter must agree with.

Host leg (SimNIBS is mocked; only path resolution and the field arithmetic run).
Reproduce: ``.venv/bin/python -m pytest tests/test_blender_mti_surface.py -q -p no:cacheprovider``
Deliberately elsewhere: preflight-vs-runner agreement for every mode, the mTI surface
included, is ``tests/test_blender_preflight_matches_runner.py``; arrow geometry is
``tests/numerical/test_vector_export_geometry.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tit.blender import montage_publication, region_exporter, vector_field_exporter
from tit.blender.config import RegionConfig, VectorConfig
from tit.calc import get_TI_vectors

pytestmark = pytest.mark.unit

SID = "001"
SIM = "Deep"


def _sim_dir(project: Path, sim: str = SIM) -> Path:
    return project / "derivatives" / "SimNIBS" / f"sub-{SID}" / "Simulations" / sim


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def _mti_sim(project: Path, n_channels: int = 4, *, surface: bool = True) -> Path:
    """An mTI run's tree as ``MTISimulation`` leaves it (N channels, letters A..)."""
    sim = _sim_dir(project)
    (sim / "mTI" / "mesh").mkdir(parents=True)
    # Every run makes TI/mesh/surfaces too (setup dirs), but only a 2-pair run fills it.
    (sim / "TI" / "mesh" / "surfaces").mkdir(parents=True)
    _touch(sim / "mTI" / "mesh" / f"{SIM}_mTI.msh")
    if surface:
        _touch(sim / "mTI" / "mesh" / "surfaces" / f"{SIM}_mTI_central.msh")
    for i in range(n_channels):
        _touch(
            sim / "high_Frequency" / "mesh" / f"{SID}_TDCS_{'ABCDEFGH'[i]}_scalar.msh"
        )
    doc = sim / "documentation" / "config.json"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        json.dumps(
            {
                "conductivity": "scalar",
                "eeg_net": "GSN-HydroCel-185.csv",
                "electrode_pairs": [["E1", "E2"]] * n_channels,
            }
        )
    )
    return sim


def _ti_sim(project: Path) -> Path:
    sim = _sim_dir(project)
    _touch(sim / "TI" / "mesh" / f"{SIM}_TI.msh")
    _touch(sim / "TI" / "mesh" / "surfaces" / f"{SIM}_TI_central.msh")
    for i in (1, 2):
        _touch(sim / "high_Frequency" / "mesh" / f"{SID}_TDCS_{i}_scalar.msh")
    doc = sim / "documentation" / "config.json"
    doc.parent.mkdir(parents=True)
    doc.write_text(json.dumps({"conductivity": "scalar", "eeg_net": "x.csv"}))
    return sim


def _mti_surface(project: Path) -> str:
    return str(
        _sim_dir(project) / "mTI" / "mesh" / "surfaces" / f"{SIM}_mTI_central.msh"
    )


def _ti_surface(project: Path) -> str:
    return str(_sim_dir(project) / "TI" / "mesh" / "surfaces" / f"{SIM}_TI_central.msh")


class TestRegionExport:
    def test_mti_reads_the_mti_surface_and_its_mti_max_field(
        self, init_pm, tmp_project
    ):
        _mti_sim(tmp_project)
        cfg = RegionConfig(subject_id=SID, simulation_name=SIM)
        region_exporter._resolve_paths(cfg)
        assert cfg.mesh == _mti_surface(tmp_project)
        # The mTI surface's envelope node field is named after the mTI mesh's element field.
        assert cfg.field_name == "mTI_max"

    def test_a_field_without_an_alias_keeps_its_name(self, init_pm, tmp_project):
        _mti_sim(tmp_project)
        cfg = RegionConfig(subject_id=SID, simulation_name=SIM, field_name="hf_peak")
        region_exporter._resolve_paths(cfg)
        assert cfg.field_name == "hf_peak"

    def test_ti_still_reads_the_ti_surface(self, init_pm, tmp_project):
        _ti_sim(tmp_project)
        cfg = RegionConfig(subject_id=SID, simulation_name=SIM, field_name="mTI_max")
        region_exporter._resolve_paths(cfg)
        assert cfg.mesh == _ti_surface(tmp_project)
        assert cfg.field_name == "TI_max"


class TestVectorExport:
    def test_mti_reads_its_surface_and_all_four_lettered_carriers(
        self, init_pm, tmp_project
    ):
        sim = _mti_sim(tmp_project)
        cfg = VectorConfig(subject_id=SID, simulation_name=SIM)
        carriers = vector_field_exporter._resolve_paths(cfg)
        assert cfg.central_surface == _mti_surface(tmp_project)
        hf = sim / "high_Frequency" / "mesh"
        expected = [str(hf / f"{SID}_TDCS_{c}_scalar.msh") for c in "ABCD"]
        assert carriers == expected
        assert [cfg.mesh1, cfg.mesh2, cfg.mesh3, cfg.mesh4] == expected
        assert cfg.is_mti

    def test_six_channel_mti_uses_every_channel(self, init_pm, tmp_project):
        sim = _mti_sim(tmp_project, n_channels=6)
        cfg = VectorConfig(subject_id=SID, simulation_name=SIM)
        carriers = vector_field_exporter._resolve_paths(cfg)
        hf = sim / "high_Frequency" / "mesh"
        assert carriers == [str(hf / f"{SID}_TDCS_{c}_scalar.msh") for c in "ABCDEF"]

    def test_ti_keeps_its_two_numbered_carriers(self, init_pm, tmp_project):
        sim = _ti_sim(tmp_project)
        cfg = VectorConfig(subject_id=SID, simulation_name=SIM)
        carriers = vector_field_exporter._resolve_paths(cfg)
        hf = sim / "high_Frequency" / "mesh"
        assert carriers == [str(hf / f"{SID}_TDCS_{i}_scalar.msh") for i in (1, 2)]
        assert cfg.central_surface == _ti_surface(tmp_project)
        assert not cfg.is_mti

    def test_the_envelope_is_computed_over_all_n_channels(self, monkeypatch):
        """Six channel fields in -> get_TI_vectors over all six, not over the first four."""
        rng = np.random.default_rng(7)
        fields = [rng.normal(size=(5, 3)) for _ in range(6)]
        meshes = [object() for _ in fields]
        lookup = {id(m): f for m, f in zip(meshes, fields)}
        monkeypatch.setattr(
            vector_field_exporter,
            "_interpolate_field_to_surface",
            lambda mesh, positions, field_name="E": lookup[id(mesh)],
        )
        cfg = VectorConfig(subject_id=SID, simulation_name=SIM, export_sum=True)
        out = vector_field_exporter._compute_fields(cfg, meshes, np.zeros((5, 3)))

        np.testing.assert_allclose(out["TI"], get_TI_vectors(fields))
        four = np.linalg.norm(get_TI_vectors(fields[:4]), axis=1)
        assert not np.allclose(np.linalg.norm(out["TI"], axis=1), four)
        np.testing.assert_allclose(out["E_sum"], np.sum(fields, axis=0))
        np.testing.assert_allclose(out["E1"], fields[0])
        np.testing.assert_allclose(out["E2"], fields[1])


class TestMontageExport:
    def test_mti_gm_surface_is_the_mti_central_surface(self, init_pm, tmp_project):
        sim = _mti_sim(tmp_project)
        found = montage_publication._find_central_surface_mesh(str(sim), SID, SIM)
        assert found == _mti_surface(tmp_project)

    def test_missing_mti_surface_is_named_in_the_error(self, init_pm, tmp_project):
        sim = _mti_sim(tmp_project, surface=False)
        with pytest.raises(FileNotFoundError, match="mTI_central.msh"):
            montage_publication._find_central_surface_mesh(str(sim), SID, SIM)
