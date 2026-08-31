#!/usr/bin/env simnibs_python
"""
Unit tests for TI/mTI simulation pipeline classes and run_simulation orchestration.

All SimNIBS calls are mocked (simnibs is a MagicMock in conftest).
Tests verify orchestration logic: construction, dispatch, callbacks, result dicts.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tit import constants as const
from tit.sim.config import (
    SimulationConfig,
    SimulationMode,
    Montage,
)

# Force submodule imports so they are in sys.modules (needed for patch.object)
import tit.sim.base as _base_mod
import tit.sim.TI as _ti_mod
import tit.sim.mTI as _mti_mod
import tit.sim.utils as _utils_mod

# ============================================================================
# Helpers
# ============================================================================


def _mock_mesh_efields(mock_mesh_io, n_elements=8):
    """Give a mocked ``mesh_io`` realistic ``(N, 3)`` E-field values.

    The field metrics in :mod:`tit.fields` validate input shape, so a bare
    ``MagicMock`` (which ``np.asarray`` flattens to an empty array) is not a
    usable stand-in for an E-field.
    """
    value = np.zeros((n_elements, 3), dtype=float)
    mesh = mock_mesh_io.read_msh.return_value.crop_mesh.return_value
    mesh.field.__getitem__.return_value.value = value
    mock_mesh_io.read_msh.return_value.field.__getitem__.return_value.value = value
    return value


def _make_sim_config(**overrides):
    """Build a minimal SimulationConfig for testing."""
    defaults = dict(
        subject_id="001",
        conductivity="scalar",
        intensities=[1.0, 1.0],
        montages=[],
    )
    defaults.update(overrides)
    return SimulationConfig(**defaults)


def _make_ti_montage(name="test_ti"):
    return Montage(
        name=name,
        mode=Montage.Mode.NET,
        electrode_pairs=[("E1", "E2"), ("E3", "E4")],
        eeg_net="GSN-256.csv",
    )


def _make_mti_montage(name="test_mti"):
    return Montage(
        name=name,
        mode=Montage.Mode.NET,
        electrode_pairs=[("E1", "E2"), ("E3", "E4"), ("E5", "E6"), ("E7", "E8")],
        eeg_net="GSN-256.csv",
    )


def _make_xyz_montage(name="test_xyz"):
    return Montage(
        name=name,
        mode=Montage.Mode.FLEX_FREE,
        electrode_pairs=[
            ([0.0, 0.0, 100.0], [0.0, 0.0, -100.0]),
            ([50.0, 0.0, 0.0], [-50.0, 0.0, 0.0]),
        ],
    )


# ============================================================================
# TISimulation
# ============================================================================


@pytest.mark.unit
class TestTISimulation:
    """Tests for tit.sim.TI.TISimulation construction and run orchestration."""

    def test_construction_sets_attributes(self):
        with patch.object(_base_mod, "get_path_manager") as mock_pm:
            mock_pm.return_value.m2m.return_value = "/fake/m2m"

            config = _make_sim_config()
            montage = _make_ti_montage()
            logger = MagicMock()

            sim = _ti_mod.TISimulation(config, montage, logger)

            assert sim.config is config
            assert sim.montage is montage
            assert sim.logger is logger

    def test_run_returns_result_dict(self):
        with (
            patch.object(_base_mod, "get_path_manager") as mock_pm,
            patch.object(_base_mod, "setup_montage_directories") as mock_setup_dirs,
            patch.object(_base_mod, "create_simulation_config_file"),
            patch.object(_base_mod, "run_montage_visualization"),
            patch.object(_base_mod, "run_simnibs"),
            patch.object(_base_mod, "subprocess"),
            patch.object(_ti_mod, "extract_fields"),
            patch.object(_ti_mod, "transform_dirs_to_nifti"),
            patch.object(_ti_mod, "start_t1_to_mni"),
            patch.object(_ti_mod, "finish_t1_to_mni"),
            patch.object(_ti_mod, "safe_move"),
            patch.object(_ti_mod, "mesh_io") as mock_mesh_io,
            patch.object(_ti_mod, "TI"),
            patch.object(_ti_mod, "glob"),
        ):
            mock_pm.return_value.m2m.return_value = "/fake/m2m"
            mock_pm.return_value.simulation.return_value = "/fake/sim/test_ti"
            mock_pm.return_value.eeg_positions.return_value = "/fake/eeg"
            _mock_mesh_efields(mock_mesh_io)

            dirs = {
                "montage_dir": "/fake/sim/test_ti",
                "hf_dir": "/fake/sim/test_ti/high_Frequency",
                "hf_mesh": "/fake/sim/test_ti/high_Frequency/mesh",
                "hf_niftis": "/fake/sim/test_ti/high_Frequency/niftis",
                "hf_analysis": "/fake/sim/test_ti/high_Frequency/analysis",
                "ti_mesh": "/fake/sim/test_ti/TI/mesh",
                "ti_niftis": "/fake/sim/test_ti/TI/niftis",
                "ti_surfaces": "/fake/sim/test_ti/TI/mesh/surfaces",
                "ti_surface_overlays": "/fake/sim/test_ti/TI/surface_overlays",
                "ti_montage_imgs": "/fake/sim/test_ti/TI/montage_imgs",
                "documentation": "/fake/sim/test_ti/documentation",
            }
            mock_setup_dirs.return_value = dirs

            config = _make_sim_config()
            montage = _make_ti_montage()
            logger = MagicMock()

            sim = _ti_mod.TISimulation(config, montage, logger)
            result = sim.run("/fake/simulation_dir")

            assert result["montage_name"] == "test_ti"
            assert result["montage_type"] == "TI"
            assert result["status"] == "completed"
            assert "output_mesh" in result

    def test_run_writes_ti_avg_field(self):
        """TI_avg (tit.calc.get_TI_avg) must be written as a volume field
        on the TI output mesh alongside TI_max, hf_peak, and hf_sar."""
        with (
            patch.object(_base_mod, "get_path_manager") as mock_pm,
            patch.object(_base_mod, "setup_montage_directories") as mock_setup_dirs,
            patch.object(_base_mod, "create_simulation_config_file"),
            patch.object(_base_mod, "run_montage_visualization"),
            patch.object(_base_mod, "run_simnibs"),
            patch.object(_base_mod, "subprocess"),
            patch.object(_ti_mod, "extract_fields"),
            patch.object(_ti_mod, "transform_dirs_to_nifti"),
            patch.object(_ti_mod, "start_t1_to_mni"),
            patch.object(_ti_mod, "finish_t1_to_mni"),
            patch.object(_ti_mod, "safe_move"),
            patch.object(_ti_mod, "mesh_io") as mock_mesh_io,
            patch.object(_ti_mod, "TI"),
            patch.object(_ti_mod, "glob"),
            patch.object(_ti_mod, "deepcopy") as mock_deepcopy,
        ):
            mock_pm.return_value.m2m.return_value = "/fake/m2m"
            mock_pm.return_value.simulation.return_value = "/fake/sim/test_ti"
            mock_pm.return_value.eeg_positions.return_value = "/fake/eeg"
            _mock_mesh_efields(mock_mesh_io)
            # Identity deepcopy so the mesh mock written to (mout) is the
            # same tracked object read from mesh_io.read_msh, letting the
            # add_element_field assertion below see every field written.
            mock_deepcopy.side_effect = lambda obj: obj

            mock_setup_dirs.return_value = {
                "montage_dir": "/fake/sim/test_ti",
                "hf_dir": "/fake/sim/test_ti/high_Frequency",
                "hf_mesh": "/fake/sim/test_ti/high_Frequency/mesh",
                "hf_niftis": "/fake/sim/test_ti/high_Frequency/niftis",
                "hf_analysis": "/fake/sim/test_ti/high_Frequency/analysis",
                "ti_mesh": "/fake/sim/test_ti/TI/mesh",
                "ti_niftis": "/fake/sim/test_ti/TI/niftis",
                "ti_surfaces": "/fake/sim/test_ti/TI/mesh/surfaces",
                "ti_surface_overlays": "/fake/sim/test_ti/TI/surface_overlays",
                "ti_montage_imgs": "/fake/sim/test_ti/TI/montage_imgs",
                "documentation": "/fake/sim/test_ti/documentation",
            }

            sim = _ti_mod.TISimulation(
                _make_sim_config(
                    output_fields=[
                        const.FIELD_TI_MAX,
                        const.FIELD_TI_AVG,
                        const.FIELD_HF_PEAK,
                        const.FIELD_HF_SAR,
                    ]
                ),
                _make_ti_montage(),
                MagicMock(),
            )
            sim.run("/fake/sim_dir")

            mout = mock_mesh_io.read_msh.return_value.crop_mesh.return_value
            written_field_names = [
                call.args[1] for call in mout.add_element_field.call_args_list
            ]
            assert const.FIELD_TI_AVG in written_field_names

    def test_run_calls_setup_and_simnibs(self):
        with (
            patch.object(_base_mod, "get_path_manager") as mock_pm,
            patch.object(_base_mod, "setup_montage_directories") as mock_setup_dirs,
            patch.object(_base_mod, "create_simulation_config_file") as mock_create,
            patch.object(_base_mod, "run_montage_visualization"),
            patch.object(_base_mod, "run_simnibs") as mock_run_simnibs,
            patch.object(_base_mod, "subprocess"),
            patch.object(_ti_mod, "extract_fields"),
            patch.object(_ti_mod, "transform_dirs_to_nifti"),
            patch.object(_ti_mod, "start_t1_to_mni"),
            patch.object(_ti_mod, "finish_t1_to_mni"),
            patch.object(_ti_mod, "safe_move"),
            patch.object(_ti_mod, "mesh_io") as mock_mesh_io,
            patch.object(_ti_mod, "TI"),
            patch.object(_ti_mod, "glob"),
        ):
            mock_pm.return_value.m2m.return_value = "/fake/m2m"
            mock_pm.return_value.simulation.return_value = "/fake/sim/test_ti"
            mock_pm.return_value.eeg_positions.return_value = "/fake/eeg"
            _mock_mesh_efields(mock_mesh_io)
            mock_setup_dirs.return_value = {
                "montage_dir": "/fake",
                "hf_dir": "/fake/hf",
                "hf_mesh": "/fake/hf/mesh",
                "hf_niftis": "/fake/hf/niftis",
                "hf_analysis": "/fake/hf/analysis",
                "ti_mesh": "/fake/ti/mesh",
                "ti_niftis": "/fake/ti/niftis",
                "ti_surfaces": "/fake/ti/mesh/surfaces",
                "ti_surface_overlays": "/fake/ti/surface_overlays",
                "ti_montage_imgs": "/fake/ti/montage_imgs",
                "documentation": "/fake/documentation",
            }

            sim = _ti_mod.TISimulation(
                _make_sim_config(), _make_ti_montage(), MagicMock()
            )
            sim.run("/fake/sim_dir")

            mock_setup_dirs.assert_called_once_with(
                "/fake/sim/test_ti", SimulationMode.TI
            )
            mock_run_simnibs.assert_called_once()
            mock_create.assert_called_once()


# ============================================================================
# mTISimulation
# ============================================================================


@pytest.mark.unit
class TestMTISimulation:
    """Tests for tit.sim.mTI.mTISimulation construction and run orchestration."""

    def test_construction_sets_attributes(self):
        with patch.object(_base_mod, "get_path_manager") as mock_pm:
            mock_pm.return_value.m2m.return_value = "/fake/m2m"

            config = _make_sim_config(intensities=[1.0, 1.0, 1.0, 1.0])
            montage = _make_mti_montage()
            logger = MagicMock()

            sim = _mti_mod.mTISimulation(config, montage, logger)

            assert sim.config is config
            assert sim.montage is montage
            assert sim.montage.simulation_mode == SimulationMode.MTI
            assert sim.montage.num_pairs == 4

    def test_run_returns_mti_result(self):
        with (
            patch.object(_base_mod, "get_path_manager") as mock_pm,
            patch.object(_base_mod, "setup_montage_directories") as mock_setup_dirs,
            patch.object(_base_mod, "create_simulation_config_file"),
            patch.object(_base_mod, "run_montage_visualization"),
            patch.object(_base_mod, "run_simnibs") as mock_run_simnibs,
            patch.object(_base_mod, "subprocess"),
            patch.object(_mti_mod, "extract_fields"),
            patch.object(_mti_mod, "transform_dirs_to_nifti"),
            patch.object(_mti_mod, "start_t1_to_mni"),
            patch.object(_mti_mod, "finish_t1_to_mni"),
            patch.object(_mti_mod, "safe_move"),
            patch.object(_mti_mod, "mesh_io") as mock_mesh_io,
            patch.object(_mti_mod, "TI"),
            patch.object(_mti_mod, "get_TI_vectors") as mock_get_ti,
            patch.object(_mti_mod, "get_TI_dir"),
            patch.object(_mti_mod, "glob"),
            patch.object(_mti_mod, "deepcopy") as mock_deepcopy,
        ):
            mock_pm.return_value.m2m.return_value = "/fake/m2m"
            mock_pm.return_value.simulation.return_value = "/fake/sim/test_mti"
            mock_pm.return_value.eeg_positions.return_value = "/fake/eeg"
            e_field_value = _mock_mesh_efields(mock_mesh_io)
            # Identity deepcopy so the mesh mocks written to (mout) are the
            # same tracked objects read from mesh_io.read_msh, letting the
            # add_element_field assertions below see every field written.
            mock_deepcopy.side_effect = lambda obj: obj

            dirs = {
                "montage_dir": "/fake/sim/test_mti",
                "hf_dir": "/fake/sim/test_mti/high_Frequency",
                "hf_mesh": "/fake/sim/test_mti/high_Frequency/mesh",
                "hf_niftis": "/fake/sim/test_mti/high_Frequency/niftis",
                "hf_analysis": "/fake/sim/test_mti/high_Frequency/analysis",
                "ti_mesh": "/fake/sim/test_mti/TI/mesh",
                "ti_niftis": "/fake/sim/test_mti/TI/niftis",
                "ti_surfaces": "/fake/sim/test_mti/TI/mesh/surfaces",
                "ti_surface_overlays": "/fake/sim/test_mti/TI/surface_overlays",
                "ti_montage_imgs": "/fake/sim/test_mti/TI/montage_imgs",
                "mti_mesh": "/fake/sim/test_mti/mTI/mesh",
                "mti_surfaces": "/fake/sim/test_mti/mTI/mesh/surfaces",
                "mti_niftis": "/fake/sim/test_mti/mTI/niftis",
                "mti_montage_imgs": "/fake/sim/test_mti/mTI/montage_imgs",
                "documentation": "/fake/sim/test_mti/documentation",
            }
            mock_setup_dirs.return_value = dirs

            import numpy as np

            mock_get_ti.return_value = np.zeros((e_field_value.shape[0], 3))

            config = _make_sim_config(
                intensities=[1.0, 1.0, 1.0, 1.0],
                output_fields=[
                    const.FIELD_TI_MAX,
                    const.FIELD_TI_AVG,
                    const.FIELD_HF_PEAK,
                    const.FIELD_HF_SAR,
                ],
            )
            montage = _make_mti_montage()
            logger = MagicMock()

            sim = _mti_mod.mTISimulation(config, montage, logger)
            result = sim.run("/fake/simulation_dir")

            assert result["montage_name"] == "test_mti"
            assert result["montage_type"] == "mTI"
            assert result["status"] == "completed"
            assert "output_mesh" in result

            mock_setup_dirs.assert_called_once_with(
                "/fake/sim/test_mti", SimulationMode.MTI
            )
            mock_run_simnibs.assert_called_once()

            # D3: the final envelope is computed over all four channel
            # fields at once, not a recursive TI-of-TI recombination.
            assert len(mock_get_ti.call_args.args[0]) == 4

            # D2 regression guard: hf_peak/hf_sar safety metrics must be
            # written onto the mTI output mesh when selected.
            mout = mock_mesh_io.read_msh.return_value.crop_mesh.return_value
            written_field_names = [
                call.args[1] for call in mout.add_element_field.call_args_list
            ]
            assert const.FIELD_HF_PEAK in written_field_names
            assert const.FIELD_HF_SAR in written_field_names

            # TI_avg (tit.calc.get_TI_avg): orientation-averaged companion
            # to mTI_max, must also be written when selected.
            assert const.FIELD_TI_AVG in written_field_names

    def test_envelope_uses_positional_channel_pairing(self):
        """get_TI_vectors/get_TI_avg are called with the channel fields
        alone -- pairing is positional (each two consecutive channels share
        a carrier); there is no per-montage carrier override."""
        with (
            patch.object(_base_mod, "get_path_manager") as mock_pm,
            patch.object(_base_mod, "setup_montage_directories") as mock_setup_dirs,
            patch.object(_base_mod, "create_simulation_config_file"),
            patch.object(_base_mod, "run_montage_visualization"),
            patch.object(_base_mod, "run_simnibs"),
            patch.object(_base_mod, "subprocess"),
            patch.object(_mti_mod, "extract_fields"),
            patch.object(_mti_mod, "transform_dirs_to_nifti"),
            patch.object(_mti_mod, "start_t1_to_mni"),
            patch.object(_mti_mod, "finish_t1_to_mni"),
            patch.object(_mti_mod, "safe_move"),
            patch.object(_mti_mod, "mesh_io") as mock_mesh_io,
            patch.object(_mti_mod, "TI"),
            patch.object(_mti_mod, "get_TI_vectors") as mock_get_ti,
            patch.object(_mti_mod, "get_TI_dir"),
            patch.object(_mti_mod, "get_TI_avg") as mock_get_avg,
            patch.object(_mti_mod, "glob"),
            patch.object(_mti_mod, "deepcopy") as mock_deepcopy,
        ):
            mock_pm.return_value.m2m.return_value = "/fake/m2m"
            mock_pm.return_value.simulation.return_value = "/fake/sim/test_mti"
            mock_pm.return_value.eeg_positions.return_value = "/fake/eeg"
            e_field_value = _mock_mesh_efields(mock_mesh_io)
            mock_deepcopy.side_effect = lambda obj: obj

            mock_setup_dirs.return_value = {
                "montage_dir": "/fake/sim/test_mti",
                "hf_dir": "/fake/sim/test_mti/high_Frequency",
                "hf_mesh": "/fake/sim/test_mti/high_Frequency/mesh",
                "hf_niftis": "/fake/sim/test_mti/high_Frequency/niftis",
                "hf_analysis": "/fake/sim/test_mti/high_Frequency/analysis",
                "ti_mesh": "/fake/sim/test_mti/TI/mesh",
                "ti_niftis": "/fake/sim/test_mti/TI/niftis",
                "ti_surfaces": "/fake/sim/test_mti/TI/mesh/surfaces",
                "ti_surface_overlays": "/fake/sim/test_mti/TI/surface_overlays",
                "ti_montage_imgs": "/fake/sim/test_mti/TI/montage_imgs",
                "mti_mesh": "/fake/sim/test_mti/mTI/mesh",
                "mti_surfaces": "/fake/sim/test_mti/mTI/mesh/surfaces",
                "mti_niftis": "/fake/sim/test_mti/mTI/niftis",
                "mti_montage_imgs": "/fake/sim/test_mti/mTI/montage_imgs",
                "documentation": "/fake/sim/test_mti/documentation",
            }

            mock_get_ti.return_value = np.zeros((e_field_value.shape[0], 3))
            mock_get_avg.return_value = np.zeros(e_field_value.shape[0])

            # opt into TI_avg so both envelope calls are exercised.
            config = _make_sim_config(
                intensities=[1.0, 1.0, 1.0, 1.0],
                output_fields=[const.FIELD_TI_MAX, const.FIELD_TI_AVG],
            )
            montage = _make_mti_montage()

            sim = _mti_mod.mTISimulation(config, montage, MagicMock())
            sim.run("/fake/simulation_dir")

            # Once per carrier for the intermediate TI_AB/TI_CD meshes (two
            # channel fields each) plus once for the final joint envelope.
            assert mock_get_ti.call_count == 3
            assert len(mock_get_ti.call_args.args[0]) == 4
            mock_get_avg.assert_called_once()


# ============================================================================
# run_simulation orchestration
# ============================================================================


@pytest.mark.unit
class TestRunSimulation:
    """Tests for run_simulation dispatcher.

    run_simulation does local imports of TISimulation and mTISimulation,
    so we patch them on their home modules which is where the import resolves.
    """

    def _patch_run_sim(self):
        """Return context manager stack that patches TI/mTI classes."""
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            with (
                patch.object(_utils_mod, "get_path_manager") as mock_pm,
                patch.object(_utils_mod.os.path, "isdir", return_value=True),
                patch.object(_utils_mod.os.path, "isfile", return_value=True),
                patch(
                    "tit.telemetry.track_operation",
                    side_effect=lambda _op: contextlib.nullcontext(),
                ),
                patch.object(_ti_mod, "TISimulation") as mock_ti_cls,
                patch.object(_mti_mod, "mTISimulation") as mock_mti_cls,
            ):
                mock_pm.return_value.simulations.return_value = "/fake/sims"
                mock_pm.return_value.m2m.return_value = "/fake/m2m"
                mock_pm.return_value.eeg_positions.return_value = "/fake/eeg"
                # Also need to patch the local imports in run_simulation.
                # run_simulation does `from tit.sim.TI import TISimulation`
                # which resolves to the already-imported module attribute.
                yield mock_pm, mock_ti_cls, mock_mti_cls

        return _ctx()

    def test_dispatches_ti_montage(self):
        with self._patch_run_sim() as (mock_pm, mock_ti_cls, mock_mti_cls):
            mock_ti_cls.return_value.run.return_value = {
                "montage_name": "test_ti",
                "montage_type": "TI",
                "status": "completed",
                "output_mesh": "/fake/mesh.msh",
            }

            montage = _make_ti_montage()
            config = _make_sim_config(montages=[montage])
            logger = MagicMock()

            results = _utils_mod.run_simulation(config, logger=logger)

            assert len(results) == 1
            assert results[0]["montage_type"] == "TI"
            mock_ti_cls.assert_called_once_with(config, montage, logger)
            mock_mti_cls.assert_not_called()

    def test_dispatches_mti_montage(self):
        with self._patch_run_sim() as (mock_pm, mock_ti_cls, mock_mti_cls):
            mock_mti_cls.return_value.run.return_value = {
                "montage_name": "test_mti",
                "montage_type": "mTI",
                "status": "completed",
                "output_mesh": "/fake/mesh.msh",
            }

            montage = _make_mti_montage()
            config = _make_sim_config(
                intensities=[1.0, 1.0, 1.0, 1.0],
                montages=[montage],
            )
            logger = MagicMock()

            results = _utils_mod.run_simulation(config, logger=logger)

            assert len(results) == 1
            assert results[0]["montage_type"] == "mTI"
            mock_mti_cls.assert_called_once_with(config, montage, logger)
            mock_ti_cls.assert_not_called()

    def test_returns_list_of_results(self):
        with self._patch_run_sim() as (mock_pm, mock_ti_cls, mock_mti_cls):
            mock_ti_cls.return_value.run.return_value = {
                "montage_name": "m1",
                "montage_type": "TI",
                "status": "completed",
                "output_mesh": "/a",
            }
            mock_mti_cls.return_value.run.return_value = {
                "montage_name": "m2",
                "montage_type": "mTI",
                "status": "completed",
                "output_mesh": "/b",
            }

            ti_montage = _make_ti_montage("m1")
            mti_montage = _make_mti_montage("m2")
            config = _make_sim_config(
                intensities=[1.0, 1.0, 1.0, 1.0],
                montages=[ti_montage, mti_montage],
            )
            logger = MagicMock()

            results = _utils_mod.run_simulation(config, logger=logger)

            assert len(results) == 2
            assert results[0]["montage_name"] == "m1"
            assert results[1]["montage_name"] == "m2"

    def test_calls_progress_callback(self):
        with self._patch_run_sim() as (mock_pm, mock_ti_cls, mock_mti_cls):
            mock_ti_cls.return_value.run.return_value = {
                "montage_name": "m1",
                "montage_type": "TI",
                "status": "completed",
                "output_mesh": "/a",
            }

            montages = [_make_ti_montage("m1"), _make_ti_montage("m2")]
            config = _make_sim_config(montages=montages)
            logger = MagicMock()
            callback = MagicMock()

            _utils_mod.run_simulation(config, logger=logger, progress_callback=callback)

            # Called with (idx, total, name) for each montage, plus final "Complete"
            assert callback.call_count == 3
            callback.assert_any_call(0, 2, "m1")
            callback.assert_any_call(1, 2, "m2")
            callback.assert_any_call(2, 2, "Complete")

    def test_no_callback_does_not_error(self):
        with self._patch_run_sim() as (mock_pm, mock_ti_cls, mock_mti_cls):
            mock_ti_cls.return_value.run.return_value = {
                "montage_name": "m1",
                "montage_type": "TI",
                "status": "completed",
                "output_mesh": "/a",
            }

            montage = _make_ti_montage()
            config = _make_sim_config(montages=[montage])
            logger = MagicMock()

            results = _utils_mod.run_simulation(config, logger=logger)
            assert len(results) == 1

    def test_empty_montage_list(self):
        with self._patch_run_sim() as (mock_pm, mock_ti_cls, mock_mti_cls):
            config = _make_sim_config(montages=[])
            logger = MagicMock()

            with pytest.raises(ValueError, match="At least one montage"):
                _utils_mod.run_simulation(config, logger=logger)
            mock_ti_cls.assert_not_called()
            mock_mti_cls.assert_not_called()

    def test_xyz_montage_dispatches_to_ti(self):
        """XYZ montage with 2 pairs should dispatch to TISimulation."""
        with self._patch_run_sim() as (mock_pm, mock_ti_cls, mock_mti_cls):
            mock_ti_cls.return_value.run.return_value = {
                "montage_name": "test_xyz",
                "montage_type": "TI",
                "status": "completed",
                "output_mesh": "/a",
            }

            montage = _make_xyz_montage()
            config = _make_sim_config(montages=[montage])
            logger = MagicMock()

            results = _utils_mod.run_simulation(config, logger=logger)

            assert len(results) == 1
            mock_ti_cls.assert_called_once()
            mock_mti_cls.assert_not_called()


# ============================================================================
# Output-field selection
# ============================================================================


@pytest.mark.unit
class TestOutputFieldSelection:
    """Only the selected output fields are computed and written.

    The point of gating is cost, not tidiness: TI_avg runs a direction sweep
    (~0.5s per 200k elements), while hf_peak/hf_sar are nearly free. Skipping
    the write but still computing would save nothing.
    """

    def _run_ti(self, output_fields):
        with (
            patch.object(_base_mod, "get_path_manager") as mock_pm,
            patch.object(_base_mod, "setup_montage_directories") as mock_setup_dirs,
            patch.object(_base_mod, "create_simulation_config_file"),
            patch.object(_base_mod, "run_montage_visualization"),
            patch.object(_base_mod, "run_simnibs"),
            patch.object(_base_mod, "subprocess"),
            patch.object(_ti_mod, "extract_fields"),
            patch.object(_ti_mod, "transform_dirs_to_nifti"),
            patch.object(_ti_mod, "start_t1_to_mni"),
            patch.object(_ti_mod, "finish_t1_to_mni"),
            patch.object(_ti_mod, "safe_move"),
            patch.object(_ti_mod, "mesh_io") as mock_mesh_io,
            patch.object(_ti_mod, "TI"),
            patch.object(_ti_mod, "glob"),
            patch.object(_ti_mod, "deepcopy") as mock_deepcopy,
            patch.object(_ti_mod, "get_TI_avg") as mock_ti_avg,
            patch.object(_ti_mod, "hf_peak") as mock_hf_peak,
            patch.object(_ti_mod, "hf_sar") as mock_hf_sar,
        ):
            mock_pm.return_value.m2m.return_value = "/fake/m2m"
            mock_pm.return_value.simulation.return_value = "/fake/sim/test_ti"
            mock_pm.return_value.eeg_positions.return_value = "/fake/eeg"
            _mock_mesh_efields(mock_mesh_io)
            mock_deepcopy.side_effect = lambda obj: obj
            mock_setup_dirs.return_value = {
                k: f"/fake/{k}"
                for k in (
                    "montage_dir",
                    "hf_dir",
                    "hf_mesh",
                    "hf_niftis",
                    "hf_analysis",
                    "ti_mesh",
                    "ti_niftis",
                    "ti_surfaces",
                    "ti_surface_overlays",
                    "ti_montage_imgs",
                    "documentation",
                )
            }
            sim = _ti_mod.TISimulation(
                _make_sim_config(output_fields=output_fields),
                _make_ti_montage(),
                MagicMock(),
            )
            sim.run("/fake/simulation_dir")
            mout = mock_mesh_io.read_msh.return_value.crop_mesh.return_value
            written = [c.args[1] for c in mout.add_element_field.call_args_list]
            return written, mock_ti_avg, mock_hf_peak, mock_hf_sar

    def test_default_writes_only_ti_max(self):
        written, ti_avg, hf_peak_m, hf_sar_m = self._run_ti([const.FIELD_TI_MAX])
        assert written == [const.FIELD_TI_MAX]

    def test_unselected_fields_are_not_computed(self):
        _, ti_avg, hf_peak_m, hf_sar_m = self._run_ti([const.FIELD_TI_MAX])
        ti_avg.assert_not_called()
        hf_peak_m.assert_not_called()
        hf_sar_m.assert_not_called()

    def test_selecting_ti_avg_computes_it(self):
        written, ti_avg, _, _ = self._run_ti([const.FIELD_TI_MAX, const.FIELD_TI_AVG])
        ti_avg.assert_called_once()
        assert const.FIELD_TI_AVG in written

    def test_selecting_safety_fields_computes_them(self):
        written, ti_avg, hf_peak_m, hf_sar_m = self._run_ti(
            [const.FIELD_HF_PEAK, const.FIELD_HF_SAR]
        )
        hf_peak_m.assert_called_once()
        hf_sar_m.assert_called_once()
        ti_avg.assert_not_called()
        assert const.FIELD_TI_MAX not in written


@pytest.mark.unit
class TestOutputFieldsSurviveDeserialization:
    """``_build_sim_config`` reads an explicit key list, so a new field is
    dropped unless added there -- the class of bug that silently loses a
    new Montage field on the GUI -> JSON -> subprocess path."""

    @staticmethod
    def _rebuild(**overrides):
        import json as _json
        from tit.config_io import serialize_config
        from tit.sim.__main__ import _build_sim_config

        cfg = _make_sim_config(montages=[_make_ti_montage()], **overrides)
        return _build_sim_config(_json.loads(_json.dumps(serialize_config(cfg))))

    def test_selection_survives_round_trip(self):
        back = self._rebuild(output_fields=[const.FIELD_TI_MAX, const.FIELD_HF_SAR])
        assert back.output_fields == [const.FIELD_TI_MAX, const.FIELD_HF_SAR]

    def test_absent_key_defaults_to_ti_max(self):
        from tit.sim.__main__ import _build_sim_config

        import json as _json
        from tit.config_io import serialize_config

        data = _json.loads(
            _json.dumps(
                serialize_config(_make_sim_config(montages=[_make_ti_montage()]))
            )
        )
        data.pop("output_fields", None)
        assert _build_sim_config(data).output_fields == [const.FIELD_TI_MAX]
