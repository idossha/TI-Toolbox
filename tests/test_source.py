"""Tests for the ``tit.source`` EEG forward / fsaverage-map module."""

import json

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

    @pytest.mark.parametrize("overlay_subdir", ["subject_overlays", "surface_overlays"])
    def test_carrier_overlays_found_in_either_layout(self, tmp_path, overlay_subdir):
        """The glob must resolve overlays both before and after file organization."""
        from types import SimpleNamespace

        from tit.source import fsaverage

        sim_dir = tmp_path / "TI_sim"
        overlays = sim_dir / "TI" / overlay_subdir
        overlays.mkdir(parents=True)
        for pair in (1, 2):
            (overlays / f"001_TDCS_{pair}_scalar_central.msh").write_text("")
        # The TI overlay must NOT be mistaken for a carrier overlay.
        (overlays / "TI_sim_TI_central.msh").write_text("")

        pm = SimpleNamespace(simulation=lambda sid, sim: str(sim_dir))
        p1, p2 = fsaverage._carrier_overlays(pm, "001", "TI_sim")
        assert p1.name == "001_TDCS_1_scalar_central.msh"
        assert p2.name == "001_TDCS_2_scalar_central.msh"

    def test_hf_max_is_sum_of_carrier_magnitudes(self, monkeypatch):
        """hf_max = |E1| + |E2| (sum of magnitudes), not |E1 + E2|."""
        import numpy as np

        from tit.source import fsaverage
        from tit.source.config import FsavgMapConfig

        # Two anti-parallel carriers: |E1|+|E2| = 2, but |E1+E2| = 0.
        e1 = np.array([[1.0, 0.0, 0.0]])
        e2 = np.array([[-1.0, 0.0, 0.0]])
        monkeypatch.setattr(fsaverage, "_carrier_overlays", lambda *a: ("p1", "p2"))
        monkeypatch.setattr(
            fsaverage, "_read_surface_vector", lambda p: e1 if p == "p1" else e2
        )
        monkeypatch.setattr(fsaverage, "_hemisphere_node_counts", lambda sf: (1, 0))
        monkeypatch.setattr(fsaverage, "_morph_split", lambda v, *a: v)
        monkeypatch.setattr(fsaverage, "_FSAVG_NODES", {5: 1})

        import sys
        from unittest.mock import MagicMock

        sys.modules["simnibs.utils.file_finder"].SubjectFiles = lambda **kw: MagicMock(
            hemispheres=("lh",)
        )
        sys.modules["simnibs.utils.transformations"].cross_subject_map = (
            lambda *a, **kw: {}
        )
        pm = MagicMock()
        out = fsaverage._compute_fields(
            pm, "001", "TI_sim", FsavgMapConfig(fields=("hf_max", "magnitude"))
        )
        assert out["hf_max"][0] == pytest.approx(2.0)
        assert out["magnitude"][0] == pytest.approx(0.0)


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
