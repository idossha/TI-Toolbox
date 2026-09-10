"""Round-trip and exit-code tests for the nine JSON-config runners' `deserialize_config` adoption.

Each runner's `main()` is exercised end to end (argv -> parsed JSON -> `deserialize_config` ->
the runner's pipeline function, mocked) to check three things per runner:

1. the JSON config on disk survives the round trip into the right dataclass, with the right
   values reaching the (mocked) pipeline function -- i.e. `deserialize_config` replaced the old
   hand-rolled dict-reading correctly;
2. `stage`/`result`/`exit` events are emitted (via `$TIT_EVENTS_FILE`);
3. the process exit code matches the pipeline result (success/failure), including the three
   specific exit-code fixes this track made: `tit.analyzer` now calls `sys.exit(0/1)` (it had
   none before), `tit.stats` uses `result.success` instead of the `n_significant_clusters >= 0`
   tautology (also covered in `tests/test_stats_main.py`), and `tit.pre` catches
   `PreprocessError` for a clean message + exit code 2 (previously an uncaught traceback + 1).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# tit.stats.__main__ imports tit.stats.permutation -> tit.stats.engine, which needs real
# scipy.ndimage / scipy.stats (conftest.py mocks bare "scipy" but not those submodules).
# Same local fallback as test_stats_main.py / test_pre_pipeline.py / test_plotting.py so this
# module's stats tests pass regardless of collection order.
_scipy_keys = [k for k in list(sys.modules) if k == "scipy" or k.startswith("scipy.")]
_saved_scipy = {k: sys.modules.pop(k) for k in _scipy_keys}
import scipy  # noqa: E402
import scipy.ndimage  # noqa: E402
import scipy.stats  # noqa: E402

try:
    import scipy.optimize  # noqa: E402
except ImportError:
    sys.modules["scipy.optimize"] = MagicMock()
sys.modules.setdefault("scipy.spatial", MagicMock())
sys.modules.setdefault("scipy.spatial.transform", MagicMock())


def _events(tmp_path: Path) -> list[dict]:
    path = tmp_path / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _types(tmp_path: Path) -> list[str]:
    return [e["type"] for e in _events(tmp_path)]


@pytest.fixture()
def events_env(tmp_path, monkeypatch):
    """Point `$TIT_EVENTS_FILE` at a fresh file under `tmp_path` and reset module state."""
    monkeypatch.setenv("TIT_EVENTS_FILE", str(tmp_path / "events.jsonl"))
    import tit.logger as logger_mod
    import tit.jobs.events as events_mod

    logger_mod._event_sinks.clear()
    events_mod._reset_state()
    yield tmp_path
    logger_mod._event_sinks.clear()
    events_mod._reset_state()


def _write_json(tmp_path: Path, data: dict) -> str:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    return str(path)


# ---------------------------------------------------------------------------
# tit.sim.__main__
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSimMain:
    def _config_path(self, tmp_path, project_dir):
        from tit.sim.config import Montage, SimulationConfig

        config = SimulationConfig(
            subject_id="001",
            montages=[
                Montage(
                    name="m1",
                    mode=Montage.Mode.NET,
                    electrode_pairs=[("E1", "E2"), ("E3", "E4")],
                    eeg_net="GSN-HydroCel-185.csv",
                )
            ],
        )
        data = json.loads(json.dumps(_serialize(config, project_dir)))
        return _write_json(tmp_path, data)

    def test_success_emits_events_and_exits_zero(self, events_env, monkeypatch):
        from tit.sim import __main__ as entry

        config_path = self._config_path(events_env, "/proj")
        monkeypatch.setattr(sys, "argv", ["tit.sim", config_path])
        with (
            patch("tit.sim.__main__.get_path_manager"),
            patch("tit.sim.__main__.run_simulation") as mock_run,
        ):
            mock_run.return_value = [
                {"status": "ok", "montage_name": "m1", "output_mesh": "/out/m1.msh"}
            ]
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 0
        # deserialize_config correctly rebuilt the Montage.
        config = mock_run.call_args.args[0]
        assert config.subject_id == "001"
        assert config.montages[0].name == "m1"
        assert _types(events_env) == ["stage", "artifact", "result", "exit"]

    def test_failed_montage_exits_one(self, events_env, monkeypatch):
        from tit.sim import __main__ as entry

        config_path = self._config_path(events_env, "/proj")
        monkeypatch.setattr(sys, "argv", ["tit.sim", config_path])
        with (
            patch("tit.sim.__main__.get_path_manager"),
            patch("tit.sim.__main__.run_simulation") as mock_run,
        ):
            mock_run.return_value = [{"status": "failed", "montage_name": "m1"}]
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 1
        assert _events(events_env)[-1]["type"] == "exit"
        assert _events(events_env)[-1]["code"] == 1

    def test_tissue_conductivities_set_env_vars_before_run(
        self, events_env, monkeypatch
    ):
        """SimulationConfig.tissue_conductivities reaches
        tit.sim.base.BaseSimulation._apply_tissue_conductivities via the
        TISSUE_COND_<n> environment variables it already reads."""
        from tit.sim import __main__ as entry
        from tit.sim.config import Montage, SimulationConfig

        config = SimulationConfig(
            subject_id="001",
            montages=[
                Montage(
                    name="m1",
                    mode=Montage.Mode.NET,
                    electrode_pairs=[("E1", "E2")],
                    eeg_net="GSN-HydroCel-185.csv",
                )
            ],
            tissue_conductivities={1: 0.126, 3: 1.654},
        )
        data = json.loads(json.dumps(_serialize(config, "/proj")))
        config_path = _write_json(events_env, data)
        monkeypatch.setattr(sys, "argv", ["tit.sim", config_path])
        monkeypatch.delenv("TISSUE_COND_1", raising=False)
        monkeypatch.delenv("TISSUE_COND_3", raising=False)

        seen: dict[str, str | None] = {}

        def _capture_run(cfg, **kwargs):
            seen["TISSUE_COND_1"] = os.environ.get("TISSUE_COND_1")
            seen["TISSUE_COND_3"] = os.environ.get("TISSUE_COND_3")
            return [{"status": "ok", "montage_name": "m1"}]

        try:
            with (
                patch("tit.sim.__main__.get_path_manager"),
                patch("tit.sim.__main__.run_simulation", side_effect=_capture_run),
            ):
                with pytest.raises(SystemExit) as exc_info:
                    entry.main()
        finally:
            # main() sets these directly via os.environ (mirroring the real subprocess
            # environment), not through monkeypatch -- clean up explicitly so they never
            # leak into another test.
            os.environ.pop("TISSUE_COND_1", None)
            os.environ.pop("TISSUE_COND_3", None)
        assert exc_info.value.code == 0
        assert seen == {"TISSUE_COND_1": "0.126", "TISSUE_COND_3": "1.654"}

    def test_no_tissue_conductivities_sets_no_env_vars(self, events_env, monkeypatch):
        from tit.sim import __main__ as entry

        config_path = self._config_path(events_env, "/proj")
        monkeypatch.setattr(sys, "argv", ["tit.sim", config_path])
        monkeypatch.delenv("TISSUE_COND_1", raising=False)
        with (
            patch("tit.sim.__main__.get_path_manager"),
            patch("tit.sim.__main__.run_simulation") as mock_run,
        ):
            mock_run.return_value = [{"status": "ok", "montage_name": "m1"}]
            with pytest.raises(SystemExit):
                entry.main()
        assert "TISSUE_COND_1" not in os.environ


def _serialize(config, project_dir: str) -> dict:
    from tit.config_io import serialize_config

    data = serialize_config(config)
    data["project_dir"] = project_dir
    return data


# ---------------------------------------------------------------------------
# tit.pre.__main__
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPreMain:
    def test_preprocess_error_exits_2_with_clean_message(
        self, events_env, monkeypatch, capsys
    ):
        from tit.pre import __main__ as entry
        from tit.pre.utils import PreprocessError

        config_path = _write_json(
            events_env, {"project_dir": "/proj", "subject_ids": ["001"]}
        )
        monkeypatch.setattr(sys, "argv", ["tit.pre", config_path])
        with (
            patch("tit.pre.__main__.get_path_manager"),
            patch(
                "tit.pre.__main__.run_pipeline",
                side_effect=PreprocessError("DICOM directory not found"),
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 2
        assert "DICOM directory not found" in capsys.readouterr().err
        assert _events(events_env)[-1]["type"] == "exit"
        assert _events(events_env)[-1]["code"] == 2

    def test_qsiprep_settings_reach_run_pipeline_as_a_flat_dict(
        self, events_env, monkeypatch
    ):
        """The PreprocessConfig modelling fix: QSIPrepSettings has no `resources`
        nesting, so `run_pipeline`'s `qsiprep_cfg.get("cpus")` reads find it."""
        from tit.pre import __main__ as entry

        config_path = _write_json(
            events_env,
            {
                "project_dir": "/proj",
                "subject_ids": ["001"],
                "run_qsiprep": True,
                "qsiprep_config": {"cpus": 8, "memory_gb": 32},
            },
        )
        monkeypatch.setattr(sys, "argv", ["tit.pre", config_path])
        with (
            patch("tit.pre.__main__.get_path_manager"),
            patch("tit.pre.__main__.run_pipeline", return_value=0) as mock_run,
        ):
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 0
        qsiprep_config = mock_run.call_args.kwargs["qsiprep_config"]
        assert qsiprep_config["cpus"] == 8
        assert qsiprep_config["memory_gb"] == 32
        assert "resources" not in qsiprep_config
        assert _types(events_env) == ["stage", "result", "exit"]


# ---------------------------------------------------------------------------
# tit.opt.flex / ex / mex __main__
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFlexMain:
    def _config_path(self, tmp_path):
        from tit.opt.config import FlexConfig

        config = FlexConfig(
            subject_id="001",
            goal="mean",
            postproc="max_TI",
            current_mA=2.0,
            electrode=FlexConfig.ElectrodeConfig(),
            roi=FlexConfig.SphericalROI(x=1.0, y=2.0, z=3.0),
        )
        return _write_json(tmp_path, _serialize(config, "/proj"))

    def test_success_emits_events_and_exits_zero(self, events_env, monkeypatch):
        from tit.opt.config import FlexResult
        from tit.opt.flex import __main__ as entry

        config_path = self._config_path(events_env)
        monkeypatch.setattr(sys, "argv", ["tit.opt.flex", config_path])
        with (
            patch("tit.paths.get_path_manager"),
            patch("tit.opt.flex.__main__.run_flex_search") as mock_run,
        ):
            mock_run.return_value = FlexResult(
                success=True,
                output_folder="/out",
                function_values=[-0.1],
                best_value=-0.1,
                best_run_index=0,
            )
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 0
        config = mock_run.call_args.args[0]
        assert config.subject_id == "001"
        assert isinstance(config.roi, type(config).SphericalROI)
        assert _types(events_env) == ["stage", "artifact", "result", "exit"]

    def test_failure_exits_one(self, events_env, monkeypatch):
        from tit.opt.config import FlexResult
        from tit.opt.flex import __main__ as entry

        config_path = self._config_path(events_env)
        monkeypatch.setattr(sys, "argv", ["tit.opt.flex", config_path])
        with (
            patch("tit.paths.get_path_manager"),
            patch("tit.opt.flex.__main__.run_flex_search") as mock_run,
        ):
            mock_run.return_value = FlexResult(
                success=False,
                output_folder="",
                function_values=[],
                best_value=float("inf"),
                best_run_index=-1,
            )
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 1


@pytest.mark.unit
class TestExMain:
    def _config_path(self, tmp_path):
        from tit.opt.config import ExConfig

        config = ExConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            roi_name="target",
            electrodes=ExConfig.PoolElectrodes(electrodes=["C3", "C4", "Cz", "Pz"]),
        )
        return _write_json(tmp_path, _serialize(config, "/proj"))

    def test_success_emits_events_and_exits_zero(self, events_env, monkeypatch):
        from tit.opt.config import ExResult
        from tit.opt.ex import __main__ as entry

        config_path = self._config_path(events_env)
        monkeypatch.setattr(sys, "argv", ["tit.opt.ex", config_path])
        with (
            patch("tit.paths.get_path_manager"),
            patch("tit.opt.ex.__main__.run_ex_search") as mock_run,
        ):
            mock_run.return_value = ExResult(
                success=True,
                output_dir="/out",
                n_combinations=10,
                results_csv="/out/results.csv",
                config_json="/out/config.json",
            )
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 0
        config = mock_run.call_args.args[0]
        assert config.subject_id == "001"
        assert config.electrodes.electrodes == ["C3", "C4", "Cz", "Pz"]
        assert _types(events_env) == ["stage", "artifact", "artifact", "result", "exit"]


@pytest.mark.unit
class TestMExMain:
    def _config_path(self, tmp_path):
        from tit.opt.config import MExConfig

        config = MExConfig(
            subject_id="001",
            leadfield_hdf="lf.hdf5",
            roi_name="target",
            electrodes=MExConfig.BucketElectrodes(
                e1_plus=["C3"],
                e1_minus=["C4"],
                e2_plus=["Cz"],
                e2_minus=["Pz"],
                e3_plus=["F3"],
                e3_minus=["F4"],
                e4_plus=["P3"],
                e4_minus=["P4"],
            ),
        )
        return _write_json(tmp_path, _serialize(config, "/proj"))

    def test_success_emits_events_and_exits_zero(self, events_env, monkeypatch):
        from tit.opt.config import MExResult
        from tit.opt.mex import __main__ as entry

        config_path = self._config_path(events_env)
        monkeypatch.setattr(sys, "argv", ["tit.opt.mex", config_path])
        with (
            patch("tit.paths.get_path_manager"),
            patch("tit.opt.mex.__main__.run_m_ex_search") as mock_run,
        ):
            mock_run.return_value = MExResult(
                success=True, output_dir="/out", n_combinations=4
            )
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 0
        config = mock_run.call_args.args[0]
        assert isinstance(config.electrodes, type(config).BucketElectrodes)
        assert config.electrodes.e1_plus == ["C3"]


# ---------------------------------------------------------------------------
# tit.analyzer.__main__: the new sys.exit(0/1) (there was none before)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalyzerMainExitCodes:
    def test_single_success_exits_zero(self, events_env, monkeypatch):
        from tit.analyzer import __main__ as entry

        config_path = _write_json(
            events_env,
            {
                "project_dir": "/proj",
                "mode": "single",
                "subject_id": "001",
                "simulation": "sim1",
                "analysis_type": "spherical",
                "center": [0, 0, 0],
                "radius": 5,
            },
        )
        monkeypatch.setattr(sys, "argv", ["tit.analyzer", config_path])
        with (
            patch("tit.analyzer.__main__.get_path_manager"),
            patch("tit.analyzer.Analyzer"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 0
        assert _types(events_env) == ["stage", "result", "exit"]
        assert _events(events_env)[-1]["code"] == 0

    def test_uncaught_exception_exits_one(self, events_env, monkeypatch):
        from tit.analyzer import __main__ as entry

        config_path = _write_json(
            events_env,
            {
                "project_dir": "/proj",
                "mode": "single",
                "subject_id": "001",
                "simulation": "sim1",
                "analysis_type": "spherical",
                "center": [0, 0, 0],
                "radius": 5,
            },
        )
        monkeypatch.setattr(sys, "argv", ["tit.analyzer", config_path])
        with (
            patch("tit.analyzer.__main__.get_path_manager"),
            patch("tit.analyzer.Analyzer", side_effect=RuntimeError("mesh not found")),
        ):
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 1

    def test_subcortical_is_a_clear_error_not_a_silent_no_op(
        self, events_env, monkeypatch
    ):
        from tit.analyzer import __main__ as entry

        config_path = _write_json(
            events_env,
            {
                "project_dir": "/proj",
                "mode": "single",
                "subject_id": "001",
                "simulation": "sim1",
                "analysis_type": "subcortical",
                # spherical/cortical fields absent -- AnalyzerConfig itself only
                # validates spherical/cortical shapes, so this must reach __main__.
            },
        )
        monkeypatch.setattr(sys, "argv", ["tit.analyzer", config_path])
        with (
            patch("tit.analyzer.__main__.get_path_manager"),
            patch("tit.analyzer.Analyzer") as MockAnalyzer,
        ):
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 1
        MockAnalyzer.assert_not_called()


# ---------------------------------------------------------------------------
# tit.stats.__main__: result.success replaces the n_significant_clusters >= 0
# tautology (dedicated exit-code coverage; tests/test_stats_main.py covers the
# rest of the deserialize_config adoption in detail).
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStatsMainExitCodes:
    def _config_path(self, tmp_path):
        return _write_json(
            tmp_path,
            {
                "project_dir": "/proj",
                "mode": "group_comparison",
                "analysis_name": "gc",
                "subjects": [
                    {"subject_id": "s1", "simulation_name": "sim1", "response": 1},
                    {"subject_id": "s2", "simulation_name": "sim2", "response": 0},
                ],
            },
        )

    def test_success_true_exits_zero_despite_zero_clusters(
        self, events_env, monkeypatch
    ):
        """The old code's `n_significant_clusters >= 0` was always true; this checks
        the replacement actually discriminates on `result.success`."""
        from tit.stats import __main__ as entry

        config_path = self._config_path(events_env)
        monkeypatch.setattr(sys, "argv", ["tit.stats", config_path])
        result = MagicMock(success=True, n_significant_clusters=0)
        with (
            patch("tit.paths.get_path_manager"),
            patch("tit.stats.permutation.run_group_comparison", return_value=result),
        ):
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 0

    def test_success_false_exits_one(self, events_env, monkeypatch):
        from tit.stats import __main__ as entry

        config_path = self._config_path(events_env)
        monkeypatch.setattr(sys, "argv", ["tit.stats", config_path])
        result = MagicMock(success=False, n_significant_clusters=3)
        with (
            patch("tit.paths.get_path_manager"),
            patch("tit.stats.permutation.run_group_comparison", return_value=result),
        ):
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# tit.source.__main__
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSourceMain:
    def test_forward_success_emits_events(self, events_env, monkeypatch):
        from tit.source import __main__ as entry

        config_path = _write_json(
            events_env,
            {
                "project_dir": "/proj",
                "mode": "forward",
                "subject_ids": ["001"],
                "forward": {"eeg_net": "GSN-HydroCel-185"},
            },
        )
        monkeypatch.setattr(sys, "argv", ["tit.source", config_path])
        with (
            patch("tit.source.__main__.get_path_manager"),
            patch("tit.source.forward._ensure_fork_start_method"),
            patch("tit.source.forward.prepare_forward") as mock_prepare,
        ):
            mock_prepare.return_value = (
                Path("/out/001-fwd.fif"),
                Path("/out/001-src.fif"),
                Path("/out/001-morph.npz"),
            )
            with pytest.raises(SystemExit) as exc_info:
                entry.main()
        assert exc_info.value.code == 0
        assert mock_prepare.call_args.args[0] == "001"
        assert _types(events_env) == [
            "stage",
            "stage",
            "artifact",
            "artifact",
            "artifact",
            "progress",
            "result",
            "exit",
        ]


# ---------------------------------------------------------------------------
# tit.blender.__main__
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBlenderMain:
    def test_montage_dispatch_success_exits_zero(self, events_env, monkeypatch):
        from tit.blender import __main__ as entry

        config_path = _write_json(
            events_env,
            {
                "project_dir": "/proj",
                "_type": "MontageConfig",
                "subject_id": "001",
                "simulation_name": "sim1",
            },
        )
        monkeypatch.setattr(sys, "argv", ["tit.blender", config_path])
        with (
            patch("tit.paths.get_path_manager"),
            patch("tit.blender.montage_publication.run_montage") as mock_run,
        ):
            assert entry.main() == 0
        mock_run.assert_called_once()
        assert _types(events_env) == ["stage", "result", "exit"]

    def test_unknown_type_exits_one(self, events_env, monkeypatch):
        from tit.blender import __main__ as entry

        config_path = _write_json(
            events_env, {"project_dir": "/proj", "_type": "NopeConfig"}
        )
        monkeypatch.setattr(sys, "argv", ["tit.blender", config_path])
        with patch("tit.paths.get_path_manager"):
            assert entry.main() == 1
