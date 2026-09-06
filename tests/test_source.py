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
        assert cfg.fields == ("TI_max", "TI_normal", "hf_peak", "hf_sar")
        assert cfg.fsaverage_spacing == 5

    def test_hf_fields_are_valid(self):
        from tit.source import FsavgMapConfig

        cfg = FsavgMapConfig(fields=("hf_peak", "hf_sar"))
        assert cfg.fields == ("hf_peak", "hf_sar")

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

    def test_sim_fsaverage_nested_under_simulation(self, init_pm):
        path = init_pm.sim_fsaverage("001", "Thalamus")
        assert path.startswith(init_pm.simulation("001", "Thalamus"))
        assert path.endswith("Simulations/Thalamus/fsaverage")
        # Must NOT live under the EEG source-forward directory.
        assert "/forward/" not in path

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
        assert str(path.parent).endswith("Simulations/TI_sim/fsaverage")

    def test_carrier_volume_meshes_skips_central_overlays(self, tmp_path):
        """Locate the per-pair VOLUME meshes, not the *_central.msh overlays."""
        from types import SimpleNamespace

        from tit.source import fsaverage

        sim_dir = tmp_path / "TI_sim"
        vol_dir = sim_dir / "high_Frequency" / "mesh"
        vol_dir.mkdir(parents=True)
        # Central overlays in both layouts must NOT be picked as the volume mesh:
        # under high_Frequency/subject_overlays/ (pre-organize) and TI/ (post).
        pre_overlays = sim_dir / "high_Frequency" / "subject_overlays"
        post_overlays = sim_dir / "TI" / "surface_overlays"
        pre_overlays.mkdir(parents=True)
        post_overlays.mkdir(parents=True)
        for pair in (1, 2):
            (vol_dir / f"001_TDCS_{pair}_scalar.msh").write_text("")
            (pre_overlays / f"001_TDCS_{pair}_scalar_central.msh").write_text("")
            (post_overlays / f"001_TDCS_{pair}_scalar_central.msh").write_text("")

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

    def test_hf_peak_and_hf_sar_from_carrier_e(self, monkeypatch):
        """Both derive from the interpolated vector E (Cassarà formulas)."""
        import numpy as np

        from tit.source import fsaverage
        from tit.source.config import FsavgMapConfig

        # Anti-parallel carriers: |E1+E2|=0, |E1-E2|=2 -> hf_peak=2; hf_sar=1+1=2.
        monkeypatch.setattr(
            fsaverage, "_carrier_volume_meshes", lambda *a: ("v1", "v2")
        )
        monkeypatch.setattr(fsaverage, "_load_carrier_mesh", lambda vol: (vol, "gm"))
        monkeypatch.setattr(
            fsaverage,
            "_interp_to_central",
            lambda mesh, gm, name, central, hemis: (
                np.array([[1.0, 0.0, 0.0]] if mesh == "v1" else [[-1.0, 0.0, 0.0]])
            ),
        )
        monkeypatch.setattr(fsaverage, "_morph_split", lambda v, *a: v)
        monkeypatch.setattr(fsaverage, "_FSAVG_NODES", {5: 1})

        self._mock_simnibs_core(monkeypatch)
        out = fsaverage._compute_fields(
            _MagicMock(),
            "001",
            "TI_sim",
            FsavgMapConfig(fields=("hf_peak", "hf_sar")),
        )
        assert out["hf_peak"][0] == pytest.approx(2.0)
        assert out["hf_sar"][0] == pytest.approx(2.0)

    def test_carrier_interp_failure_keeps_ti_fields(self, monkeypatch):
        """A carrier E-interpolation failure skips hf_max/magnitude, keeps TI."""
        import numpy as np

        from tit.source import fsaverage
        from tit.source.config import FsavgMapConfig

        def _boom(*a):
            raise ValueError("interp failed")

        monkeypatch.setattr(
            fsaverage, "_carrier_volume_meshes", lambda *a: ("v1", "v2")
        )
        monkeypatch.setattr(fsaverage, "_load_carrier_mesh", lambda vol: (vol, "gm"))
        monkeypatch.setattr(fsaverage, "_interp_to_central", _boom)
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
        assert "hf_peak" not in out and "hf_sar" not in out

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
        assert "hf_peak" not in out and "hf_sar" not in out

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
        with pytest.raises(SystemExit) as exc_info:
            entry.main()
        assert exc_info.value.code == 0
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
        with pytest.raises(SystemExit) as exc_info:
            entry.main()
        assert exc_info.value.code == 0
        assert captured["pairs"] == [("001", "TI_sim")]
        assert captured["fields"] == ("TI_max",)


# ---------------------------------------------------------------------------
# SimNIBS 4.6 EEG-bridge compatibility (tit/source/_simnibs_compat.py)
# ---------------------------------------------------------------------------


def _install_fake_stack(monkeypatch, *, helper_in="impl", version="1.12.1"):
    """Stand in for the container's mne >= 1.6 + cortech layout.

    Reproduces the two shapes that break ``simnibs.eeg.utils_mne`` there:
    ``mne``'s ``lazy_loader`` namespace, which raises ``AttributeError: No
    mne.<x> attribute <y>`` for a private submodule nothing has imported, and
    ``cortech.surface.Sphere``, which holds the morph matrix under
    ``_mapping_matrix`` rather than the ``morph_mat`` SimNIBS reads.

    ``helper_in`` places ``_complete_source_space_info`` where a given mne puts
    it: ``"impl"`` = mne >= 1.6 (``mne.source_space._source_space``),
    ``"package"`` = mne 1.5 (``mne.source_space`` itself), ``"nowhere"`` = gone.
    """
    import sys
    import types

    def _lazy(module_name):
        def __getattr__(name):
            raise AttributeError(f"No {module_name} attribute {name}")

        return __getattr__

    def _module(name, lazy=False):
        mod = types.ModuleType(name)
        if lazy:
            mod.__getattr__ = _lazy(name)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    mne = _module("mne", lazy=True)
    mne.__version__ = version
    _module("mne.morph")
    forward = _module("mne.forward", lazy=True)
    mne.forward = forward
    _module("mne.forward._make_forward")
    source_space = _module("mne.source_space", lazy=True)
    impl = _module("mne.source_space._source_space")

    def helper(src):  # the real one completes a source-space dict in place
        src["completed"] = True

    if helper_in == "impl":
        impl._complete_source_space_info = helper
    elif helper_in == "package":
        source_space._complete_source_space_info = helper

    cortech_surface = _module("cortech.surface")
    _module("cortech")

    class Sphere:
        def __init__(self):
            self._mapping_matrix = None

        def project(self, target):
            self._mapping_matrix = f"map->{target}"

    cortech_surface.Sphere = Sphere
    return types.SimpleNamespace(mne=mne, helper=helper, Sphere=Sphere)


class TestSimnibsEegCompat:
    def test_binds_every_lookup_simnibs_makes(self, monkeypatch):
        import sys

        fake = _install_fake_stack(monkeypatch)
        from tit.source._simnibs_compat import ensure_simnibs_eeg_compat

        applied = ensure_simnibs_eeg_compat()

        assert set(applied) == {
            "mne.morph",
            "mne.forward._make_forward",
            "mne.source_space._complete_source_space_info",
            "cortech.surface.Sphere.morph_mat",
        }
        # Exactly the expressions simnibs/eeg/utils_mne.py evaluates:
        assert sys.modules["mne"].morph is sys.modules["mne.morph"]
        assert (
            sys.modules["mne.forward"]._make_forward
            is sys.modules["mne.forward._make_forward"]
        )
        assert (
            sys.modules["mne.source_space"]._complete_source_space_info is fake.helper
        )

    def test_without_the_shim_the_lookup_raises(self, monkeypatch):
        """The failure being fixed: job 674801945bee46aa's AttributeError."""
        import sys

        _install_fake_stack(monkeypatch)
        with pytest.raises(AttributeError, match="_complete_source_space_info"):
            sys.modules["mne.source_space"]._complete_source_space_info

    def test_morph_mat_reads_cortechs_mapping_matrix(self, monkeypatch):
        """utils_mne:103 -- ``{h: v.morph_mat for h, v in morphs.items()}``."""
        fake = _install_fake_stack(monkeypatch)
        from tit.source._simnibs_compat import ensure_simnibs_eeg_compat

        ensure_simnibs_eeg_compat()

        spheres = {"lh": fake.Sphere(), "rh": fake.Sphere()}
        for hemi, sphere in spheres.items():
            sphere.project(f"fsaverage-{hemi}")
        assert {h: v.morph_mat for h, v in spheres.items()} == {
            "lh": "map->fsaverage-lh",
            "rh": "map->fsaverage-rh",
        }

    def test_morph_mat_before_project_says_why(self, monkeypatch):
        fake = _install_fake_stack(monkeypatch)
        from tit.source._simnibs_compat import ensure_simnibs_eeg_compat

        ensure_simnibs_eeg_compat()
        with pytest.raises(AttributeError, match="project"):
            fake.Sphere().morph_mat

    def test_idempotent(self, monkeypatch):
        _install_fake_stack(monkeypatch)
        from tit.source._simnibs_compat import ensure_simnibs_eeg_compat

        assert ensure_simnibs_eeg_compat()
        assert ensure_simnibs_eeg_compat() == []

    def test_mne_15_layout_needs_no_helper_shim(self, monkeypatch):
        """On mne 1.5 the helper is already where SimNIBS looks."""
        _install_fake_stack(monkeypatch, helper_in="package", version="1.5.1")
        from tit.source._simnibs_compat import ensure_simnibs_eeg_compat

        assert "mne.source_space._complete_source_space_info" not in (
            ensure_simnibs_eeg_compat()
        )

    def test_helper_gone_upstream_raises_readably(self, monkeypatch):
        """A future mne that drops it must name itself, not AttributeError 10 min in."""
        _install_fake_stack(monkeypatch, helper_in="nowhere", version="2.0.0")
        from tit.source._simnibs_compat import ensure_simnibs_eeg_compat

        with pytest.raises(
            RuntimeError, match=r"mne 2\.0\.0.*_complete_source_space_info"
        ):
            ensure_simnibs_eeg_compat()


class TestPrepareForwardWorker:
    """The MNE assembly must go through our worker, not ``prepare_eeg_forward``."""

    def _stub_forward(self, monkeypatch, tmp_project):
        import sys
        from pathlib import Path

        from tit.source import forward as fwd

        m2m = Path(tmp_project) / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001"
        (m2m / "eeg_positions").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(fwd, "_read_simnibs_montage", lambda *a: ({"Cz": 0}, {}))
        monkeypatch.setattr(
            fwd,
            "_build_montage_info",
            lambda *a: (_MagicMock(ch_names=["Cz"]), object()),
        )
        monkeypatch.setattr(fwd, "_compute_leadfield", lambda *a: m2m / "lf.hdf5")
        monkeypatch.setattr(fwd, "_leadfield_channel_order", lambda p: ["Cz"])
        monkeypatch.setattr(fwd, "_check_forward_dependencies", lambda: None)
        monkeypatch.setattr(
            fwd,
            "_rename_generated_outputs",
            lambda d, stem: (d / "a-fwd.fif", d / "a-src.fif", d / "a-morph.h5"),
        )
        sys.modules["mne"].io.RawArray = _MagicMock()
        commands: list[list[str]] = []
        monkeypatch.setattr(
            fwd, "_run", lambda cmd, desc, cwd=None: commands.append(cmd)
        )
        return fwd, commands

    def test_invokes_the_worker_module_not_the_console_script(
        self, init_pm, tmp_project, monkeypatch
    ):
        import sys

        from tit.source.config import ForwardConfig

        fwd, commands = self._stub_forward(monkeypatch, tmp_project)
        fwd.prepare_forward("001", ForwardConfig(eeg_net="net", fsaverage_spacing=6))

        assert len(commands) == 1
        cmd = commands[0]
        # `prepare_eeg_forward` runs `python -E`, which ignores PYTHONPATH, so no
        # compatibility shim can reach it -- see tit/source/_simnibs_compat.py.
        assert "prepare_eeg_forward" not in cmd
        assert cmd[:3] == [sys.executable, "-m", "tit.source._prepare_forward"]
        assert cmd[-2:] == ["--fsaverage", "6"]

    def test_worker_argv_round_trips(self, init_pm, tmp_project, monkeypatch):
        """The command forward.py builds is one the worker can parse."""
        from tit.source import _prepare_forward
        from tit.source.config import ForwardConfig

        fwd, commands = self._stub_forward(monkeypatch, tmp_project)
        fwd.prepare_forward("001", ForwardConfig(eeg_net="net", fsaverage_spacing=5))

        args = _prepare_forward._parse_args(commands[0][3:])
        assert args.fsaverage == 5
        assert args.no_average_ref is False
        assert args.leadfield.endswith("lf.hdf5")
        assert args.info.endswith("-info.fif") and args.trans.endswith("-trans.fif")


class TestLeadfieldChannelOrder:
    """The Info must carry the leadfield's channel order, not the net CSV's."""

    def _stub(self, monkeypatch, tmp_project, csv_order, leadfield_order):
        import sys
        from pathlib import Path

        from tit.source import forward as fwd

        m2m = Path(tmp_project) / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001"
        (m2m / "eeg_positions").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            fwd,
            "_read_simnibs_montage",
            lambda *a: ({name: idx for idx, name in enumerate(csv_order)}, {}),
        )
        monkeypatch.setattr(fwd, "_compute_leadfield", lambda *a: m2m / "lf.hdf5")
        monkeypatch.setattr(fwd, "_leadfield_channel_order", lambda p: leadfield_order)
        monkeypatch.setattr(fwd, "_check_forward_dependencies", lambda: None)
        seen: list[list[str]] = []
        monkeypatch.setattr(
            fwd,
            "_build_montage_info",
            lambda electrodes, fids: (
                seen.append(list(electrodes)) or (_MagicMock(ch_names=["x"]), object())
            ),
        )
        monkeypatch.setattr(
            fwd,
            "_rename_generated_outputs",
            lambda d, stem: (d / "a-fwd.fif", d / "a-src.fif", d / "a-morph.h5"),
        )
        monkeypatch.setattr(fwd, "_run", lambda *a, **k: None)
        sys.modules["mne"].io.RawArray = _MagicMock()
        return fwd, seen

    def test_info_is_built_in_the_leadfields_order(
        self, init_pm, tmp_project, monkeypatch
    ):
        """SimNIBS stores the reference electrode first; the net CSV does not.

        Reproduces job c8ef9a4a2d454ff0's `AssertionError: Inconsistencies between
        channels in Info and leadfield` -- the same 76 names, two orders.
        """
        from tit.source.config import ForwardConfig

        csv_order = ["Fp1", "Fpz", "Fp2", "Cz"]
        leadfield_order = ["Cz", "Fpz", "Fp2", "Fp1"]
        fwd, seen = self._stub(monkeypatch, tmp_project, csv_order, leadfield_order)

        fwd.prepare_forward("001", ForwardConfig(eeg_net="net"))

        assert seen == [leadfield_order]

    def test_electrode_set_mismatch_is_readable(
        self, init_pm, tmp_project, monkeypatch
    ):
        from tit.source.config import ForwardConfig

        fwd, _ = self._stub(
            monkeypatch, tmp_project, ["Fp1", "Cz"], ["Cz", "Fp1", "Nonexistent"]
        )
        with pytest.raises(ValueError, match="different electrode sets"):
            fwd.prepare_forward("001", ForwardConfig(eeg_net="net"))

    def test_channel_order_is_read_from_the_hdf5_attrs(self, monkeypatch, tmp_path):
        """`electrode_names` off the leadfield, not a name list rebuilt by hand."""
        import sys

        from tit.source import forward as fwd

        attrs = {"electrode_names": _MagicMock(tolist=lambda: ["Cz", "Fp1"])}
        handle = _MagicMock()
        handle.__getitem__.return_value.__getitem__.return_value.__getitem__.return_value.attrs = attrs
        h5file = _MagicMock()
        h5file.return_value.__enter__.return_value = handle
        monkeypatch.setattr(sys.modules["h5py"], "File", h5file)

        assert fwd._leadfield_channel_order(tmp_path / "lf.hdf5") == ["Cz", "Fp1"]


class TestForwardDependencyPreflight:
    """A missing optional dep must be reported before the FEM, not after it."""

    def test_missing_h5io_refuses_readably(self, init_pm, monkeypatch):
        import importlib.util

        from tit.source import forward as fwd

        real = importlib.util.find_spec
        monkeypatch.setattr(
            importlib.util,
            "find_spec",
            lambda name, *a, **k: None if name == "h5io" else real(name, *a, **k),
        )
        with pytest.raises(RuntimeError, match="h5io"):
            fwd._check_forward_dependencies()

    def test_runs_before_any_leadfield_work(self, init_pm, tmp_project, monkeypatch):
        """The check is the first thing prepare_forward does after the m2m lookup."""
        from tit.source import forward as fwd
        from tit.source.config import ForwardConfig

        order: list[str] = []
        monkeypatch.setattr(
            fwd, "_check_forward_dependencies", lambda: order.append("check")
        )
        monkeypatch.setattr(
            fwd,
            "_read_simnibs_montage",
            lambda *a: order.append("montage") or ({}, {}),
        )
        monkeypatch.setattr(
            fwd, "_compute_leadfield", lambda *a: order.append("fem") or "lf.hdf5"
        )
        with pytest.raises(Exception):
            fwd.prepare_forward("001", ForwardConfig(eeg_net="net"))
        assert order[0] == "check"
