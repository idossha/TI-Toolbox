"""Tests for the ``tit.source`` EEG forward / fsaverage-map module."""

import json
from unittest.mock import MagicMock as _MagicMock

import pytest

# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestForwardConfig:
    def test_defaults(self):
        from tit.source import ForwardConfig

        cfg = ForwardConfig()
        assert cfg.eeg_net == "GSN-HydroCel-185"
        assert cfg.fsaverage_spacing == 5
        assert cfg.cpus == 1
        assert cfg.overwrite is False

    @pytest.mark.parametrize("spacing", [4, 8, 0])
    def test_invalid_spacing_raises(self, spacing):
        from tit.source import ForwardConfig

        with pytest.raises(ValueError):
            ForwardConfig(fsaverage_spacing=spacing)


class TestFsavgMapConfig:
    def test_defaults(self):
        from tit.source import FsavgMapConfig

        cfg = FsavgMapConfig()
        assert cfg.fields == ("TI_max", "TI_normal", "magnitude", "hf_max")
        assert cfg.fsaverage_spacing == 5

    def test_hf_max_is_a_valid_field(self):
        from tit.source import FsavgMapConfig

        cfg = FsavgMapConfig(fields=("hf_max",))
        assert cfg.fields == ("hf_max",)

    def test_unknown_field_raises(self):
        from tit.source import FsavgMapConfig

        with pytest.raises(ValueError):
            FsavgMapConfig(fields=("TI_max", "bogus"))

    def test_empty_fields_raises(self):
        from tit.source import FsavgMapConfig

        with pytest.raises(ValueError):
            FsavgMapConfig(fields=())

    @pytest.mark.parametrize("spacing", [3, 9])
    def test_invalid_spacing_raises(self, spacing):
        from tit.source import FsavgMapConfig

        with pytest.raises(ValueError):
            FsavgMapConfig(fsaverage_spacing=spacing)


# ---------------------------------------------------------------------------
# PathManager wiring
# ---------------------------------------------------------------------------


class TestForwardPaths:
    def test_forward_dir(self, init_pm):
        expected = init_pm.sub("001") + "/forward"
        assert init_pm.forward("001").replace("//", "/") == expected.replace("//", "/")

    def test_forward_fsaverage_nested_under_forward(self, init_pm):
        assert init_pm.forward_fsaverage("001").startswith(init_pm.forward("001"))
        assert init_pm.forward_fsaverage("001").endswith("forward/fsaverage")

    def test_forward_distinct_from_leadfields(self, init_pm):
        assert init_pm.forward("001") != init_pm.leadfields("001")


# ---------------------------------------------------------------------------
# fsaverage projector helpers
# ---------------------------------------------------------------------------


class TestFsavgHelpers:
    def test_morph_split_node_mismatch_raises(self):
        import numpy as np

        from tit.source import fsaverage

        # 10 values can't split into 4 + 5 = 9 lh+rh nodes.
        with pytest.raises(ValueError):
            fsaverage._morph_split(
                np.zeros(10), 4, 5, morph=None, hemispheres=("lh", "rh")
            )

    def test_output_path_naming(self, init_pm):
        from tit.source import fsaverage

        path = fsaverage._output_path(init_pm, "001", "TI_sim", 5)
        assert path.name == "sub-001_sim-TI_sim_space-fsaverage5_fields.npz"
        assert str(path.parent).endswith("forward/fsaverage")

    def test_carrier_volume_meshes_skips_central_overlays(self, tmp_path):
        """Locate the per-pair VOLUME meshes, not the *_central.msh overlays."""
        from types import SimpleNamespace

        from tit.source import fsaverage

        sim_dir = tmp_path / "TI_sim"
        vol_dir = sim_dir / "high_Frequency" / "mesh"
        vol_dir.mkdir(parents=True)
        overlays = sim_dir / "TI" / "surface_overlays"
        overlays.mkdir(parents=True)
        for pair in (1, 2):
            (vol_dir / f"001_TDCS_{pair}_scalar.msh").write_text("")
            # Central overlays must NOT be picked up as the volume mesh.
            (overlays / f"001_TDCS_{pair}_scalar_central.msh").write_text("")

        pm = SimpleNamespace(simulation=lambda sid, sim: str(sim_dir))
        v1, v2 = fsaverage._carrier_volume_meshes(pm, "001", "TI_sim")
        assert v1.name == "001_TDCS_1_scalar.msh"
        assert v2.name == "001_TDCS_2_scalar.msh"

    def test_carrier_volume_meshes_missing_raises(self, tmp_path):
        from types import SimpleNamespace

        from tit.source import fsaverage

        pm = SimpleNamespace(simulation=lambda sid, sim: str(tmp_path))
        with pytest.raises(FileNotFoundError):
            fsaverage._carrier_volume_meshes(pm, "001", "TI_sim")

    def test_hf_max_and_magnitude_from_carrier_vectors(self, monkeypatch):
        """hf_max = |E1|+|E2|, magnitude = |E1+E2|, from the interpolated vectors."""
        import numpy as np

        from tit.source import fsaverage
        from tit.source.config import FsavgMapConfig

        # Two anti-parallel carriers: |E1|+|E2| = 2, but |E1+E2| = 0.
        e1 = np.array([[1.0, 0.0, 0.0]])
        e2 = np.array([[-1.0, 0.0, 0.0]])
        monkeypatch.setattr(
            fsaverage, "_carrier_volume_meshes", lambda *a: ("v1", "v2")
        )
        monkeypatch.setattr(
            fsaverage,
            "_carrier_vectors_on_central",
            lambda vol, central, hemis: e1 if vol == "v1" else e2,
        )
        monkeypatch.setattr(fsaverage, "_morph_split", lambda v, *a: v)
        monkeypatch.setattr(fsaverage, "_FSAVG_NODES", {5: 1})

        self._mock_simnibs_core(monkeypatch)
        out = fsaverage._compute_fields(
            _MagicMock(),
            "001",
            "TI_sim",
            FsavgMapConfig(fields=("hf_max", "magnitude")),
        )
        assert out["hf_max"][0] == pytest.approx(2.0)
        assert out["magnitude"][0] == pytest.approx(0.0)

    def test_carrier_failure_keeps_ti_fields(self, monkeypatch):
        """A carrier read failure drops hf_max/magnitude but keeps TI_max/TI_normal."""
        import numpy as np

        from tit.source import fsaverage
        from tit.source.config import FsavgMapConfig

        def _boom(*a):
            raise FileNotFoundError("no volume mesh")

        monkeypatch.setattr(fsaverage, "_carrier_volume_meshes", _boom)
        monkeypatch.setattr(
            fsaverage, "_read_surface_scalar", lambda path, name: np.array([0.5])
        )
        monkeypatch.setattr(fsaverage, "_ti_max_overlay", lambda *a: "ti")
        monkeypatch.setattr(fsaverage, "_ti_normal_overlay", lambda *a: "tn")
        monkeypatch.setattr(fsaverage, "_morph_split", lambda v, *a: v)
        monkeypatch.setattr(fsaverage, "_FSAVG_NODES", {5: 1})

        self._mock_simnibs_core(monkeypatch)
        out = fsaverage._compute_fields(_MagicMock(), "001", "TI_sim", FsavgMapConfig())
        assert "TI_max" in out and "TI_normal" in out
        assert "hf_max" not in out and "magnitude" not in out

    @staticmethod
    def _mock_simnibs_core(monkeypatch):
        """Stub SubjectFiles / cross_subject_map / load_subject_surfaces (1 lh node)."""
        import sys
        from types import SimpleNamespace

        sys.modules["simnibs.utils.file_finder"].SubjectFiles = lambda **kw: _MagicMock(
            hemispheres=("lh",)
        )
        sys.modules["simnibs.utils.transformations"].cross_subject_map = (
            lambda *a, **kw: {}
        )
        sys.modules["simnibs.mesh_tools"].mesh_io.load_subject_surfaces = (
            lambda sf, kind: {
                "lh": SimpleNamespace(nodes=SimpleNamespace(nr=1)),
                "rh": SimpleNamespace(nodes=SimpleNamespace(nr=0)),
            }
        )


# ---------------------------------------------------------------------------
# __main__ dispatch
# ---------------------------------------------------------------------------


class TestMainDispatch:
    def _write_config(self, tmp_path, project_dir, **extra):
        config = {"project_dir": project_dir, **extra}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        return str(path)

    def test_unknown_mode_raises(self, tmp_project, tmp_path, monkeypatch):
        from tit.source import __main__ as entry

        config_path = self._write_config(tmp_path, str(tmp_project), mode="bogus")
        monkeypatch.setattr("sys.argv", ["tit.source", config_path])
        with pytest.raises(SystemExit):
            entry.main()

    def test_forward_mode_dispatches(self, tmp_project, tmp_path, monkeypatch):
        from tit.source import __main__ as entry

        calls = []
        monkeypatch.setattr(
            "tit.source.forward.prepare_forward",
            lambda sid, cfg, **kw: calls.append((sid, cfg.eeg_net))
            or (__import__("pathlib").Path(f"{sid}-fwd.fif"),) * 3,
        )
        config_path = self._write_config(
            tmp_path,
            str(tmp_project),
            mode="forward",
            subject_ids=["001"],
            eeg_net="GSN-HydroCel-185",
        )
        monkeypatch.setattr("sys.argv", ["tit.source", config_path])
        entry.main()
        assert calls == [("001", "GSN-HydroCel-185")]

    def test_fsavg_mode_dispatches(self, tmp_project, tmp_path, monkeypatch):
        from tit.source import __main__ as entry

        captured = {}
        monkeypatch.setattr(
            "tit.source.fsaverage.project_fields_to_fsaverage",
            lambda pairs, cfg: captured.update(pairs=pairs, fields=cfg.fields) or [],
        )
        config_path = self._write_config(
            tmp_path,
            str(tmp_project),
            mode="fsavg_map",
            pairs=[{"subject_id": "001", "simulation": "TI_sim"}],
            fields=["TI_max"],
        )
        monkeypatch.setattr("sys.argv", ["tit.source", config_path])
        entry.main()
        assert captured["pairs"] == [("001", "TI_sim")]
        assert captured["fields"] == ("TI_max",)
