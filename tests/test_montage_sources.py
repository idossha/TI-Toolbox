"""Unit tests for :mod:`tit.sim.montage_sources` on a tmp project."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tit.paths import PathManager
from tit.sim import montage_sources
from tit.sim.config import Montage


@pytest.fixture()
def pm(tmp_path: Path) -> PathManager:
    return PathManager(project_dir=str(tmp_path))


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


class TestShortFlexRunId:
    def test_deterministic_and_scoped_to_subject(self):
        a = montage_sources.short_flex_run_id("001", "run1")
        b = montage_sources.short_flex_run_id("001", "run1")
        c = montage_sources.short_flex_run_id("002", "run1")
        assert a == b
        assert a != c
        assert len(a) == 8


class TestFlexMontageName:
    def test_sanitizes_and_caps_length(self):
        name = montage_sources.flex_montage_name("a run/name!!", "abc12345", "mapped")
        assert name == "flex_a_run_name_abc12345_mapped"

    def test_defaults_electrode_type_when_blank(self):
        name = montage_sources.flex_montage_name("run", "abc12345", "")
        assert name.endswith("_mapped")


class TestListFlexRunOptions:
    def test_lists_mapped_always_and_optimized_when_present(self, pm: PathManager):
        run_dir = pm.flex_search_run("001", "runA")
        _write_json(
            os.path.join(run_dir, "electrode_positions.json"),
            {
                "optimized_positions": [[0, 0, 0]] * 4,
                "channel_array_indices": [[0, 0]] * 4,
            },
        )
        options = montage_sources.list_flex_run_options(pm, "001")
        kinds = {(o["run_name"], o["electrode_type"]) for o in options}
        assert ("runA", "mapped") in kinds
        assert ("runA", "optimized") in kinds

    def test_no_optimized_option_without_positions_key(self, pm: PathManager):
        run_dir = pm.flex_search_run("001", "runB")
        _write_json(
            os.path.join(run_dir, "electrode_positions.json"),
            {"optimized_positions": [], "channel_array_indices": []},
        )
        options = montage_sources.list_flex_run_options(pm, "001")
        kinds = {(o["run_name"], o["electrode_type"]) for o in options}
        assert ("runB", "optimized") not in kinds
        assert ("runB", "mapped") in kinds


class TestResolveFlexMontage:
    def test_optimized_uses_raw_xyz_positions(self, pm: PathManager):
        run_dir = pm.flex_search_run("001", "runA")
        positions = [
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0],
            [7.0, 8.0, 9.0],
            [10.0, 11.0, 12.0],
        ]
        _write_json(
            os.path.join(run_dir, "electrode_positions.json"),
            {"optimized_positions": positions, "channel_array_indices": [[0, 0]] * 4},
        )
        montage = montage_sources.resolve_flex_montage(pm, "001", "runA", "optimized")
        assert montage.mode == Montage.Mode.FLEX_FREE
        assert montage.electrode_pairs == [
            (positions[0], positions[1]),
            (positions[2], positions[3]),
        ]
        assert (
            montage.name
            == f"flex_runA_{montage_sources.short_flex_run_id('001', 'runA')}_optimized"
        )

    def test_optimized_requires_at_least_four_electrodes(self, pm: PathManager):
        run_dir = pm.flex_search_run("001", "runA")
        _write_json(
            os.path.join(run_dir, "electrode_positions.json"),
            {
                "optimized_positions": [[0, 0, 0]] * 2,
                "channel_array_indices": [[0, 0]] * 2,
            },
        )
        with pytest.raises(ValueError, match="Not enough optimized electrodes"):
            montage_sources.resolve_flex_montage(pm, "001", "runA", "optimized")

    def test_missing_run_folder_raises(self, pm: PathManager):
        with pytest.raises(ValueError, match="Flex-search folder not found"):
            montage_sources.resolve_flex_montage(pm, "001", "nope", "optimized")

    def test_mapped_requires_eeg_net(self, pm: PathManager):
        run_dir = pm.flex_search_run("001", "runA")
        _write_json(
            os.path.join(run_dir, "electrode_positions.json"),
            {
                "optimized_positions": [[0, 0, 0]] * 4,
                "channel_array_indices": [[0, 0]] * 4,
            },
        )
        with pytest.raises(ValueError, match="eeg_net is required"):
            montage_sources.resolve_flex_montage(pm, "001", "runA", "mapped")

    def test_mapped_calls_map_electrodes_and_caches_result(self, pm, monkeypatch):
        run_dir = pm.flex_search_run("001", "runA")
        _write_json(
            os.path.join(run_dir, "electrode_positions.json"),
            {
                "optimized_positions": [[0, 0, 0]] * 4,
                "channel_array_indices": [[0, 0]] * 4,
            },
        )
        eeg_dir = pm.eeg_positions("001")
        os.makedirs(eeg_dir, exist_ok=True)
        net_path = os.path.join(eeg_dir, "net.csv")
        with open(net_path, "w") as f:
            f.write("dummy\n")

        import tit.tools.map_electrodes as map_electrodes_mod

        def fake_load_positions(path):
            return [[0, 0, 0]] * 4, [[0, 0]] * 4

        def fake_read_csv(path):
            return [[0, 0, 0]] * 8, [f"E{i}" for i in range(8)]

        def fake_map(opt_pos, net_pos, net_labels, ch_idx):
            return {
                "mapped_labels": ["E1", "E2", "E3", "E4"],
                "optimized_positions": opt_pos,
                "mapped_positions": net_pos[:4],
                "distances": [0, 0, 0, 0],
                "channel_array_indices": ch_idx,
            }

        saved = {}

        def fake_save(result, output_path, eeg_net_name=None):
            saved["path"] = output_path
            with open(output_path, "w") as f:
                json.dump(result, f)

        monkeypatch.setattr(
            map_electrodes_mod, "load_electrode_positions_json", fake_load_positions
        )
        monkeypatch.setattr(map_electrodes_mod, "read_csv_positions", fake_read_csv)
        monkeypatch.setattr(map_electrodes_mod, "map_electrodes_to_net", fake_map)
        monkeypatch.setattr(map_electrodes_mod, "save_mapping_result", fake_save)

        montage = montage_sources.resolve_flex_montage(
            pm, "001", "runA", "mapped", eeg_net="net.csv"
        )
        assert montage.mode == Montage.Mode.FLEX_MAPPED
        assert montage.electrode_pairs == [("E1", "E2"), ("E3", "E4")]
        assert montage.eeg_net == "net.csv"
        assert os.path.isfile(saved["path"])


class TestFreehandConfigs:
    def test_list_and_resolve_roundtrip(self, pm: PathManager):
        m2m_dir = pm.m2m("001")
        stim_dir = os.path.join(m2m_dir, "stim_configs")
        os.makedirs(stim_dir, exist_ok=True)
        _write_json(
            os.path.join(stim_dir, "my_stim.json"),
            {
                "name": "my_stim",
                "electrode_positions": {
                    "E1+": [1, 1, 1],
                    "E1-": [2, 2, 2],
                    "E2+": [3, 3, 3],
                    "E2-": [4, 4, 4],
                },
            },
        )
        names = montage_sources.list_freehand_configs(pm, "001")
        assert names == ["my_stim"]

        montage = montage_sources.resolve_freehand_montage(pm, "001", "my_stim")
        assert montage.mode == Montage.Mode.FREEHAND
        assert montage.electrode_pairs == [
            ([1, 1, 1], [2, 2, 2]),
            ([3, 3, 3], [4, 4, 4]),
        ]
        assert montage.eeg_net == "freehand"

    def test_falls_back_to_sorted_keys_when_ordered_keys_missing(self, pm: PathManager):
        m2m_dir = pm.m2m("001")
        stim_dir = os.path.join(m2m_dir, "stim_configs")
        os.makedirs(stim_dir, exist_ok=True)
        _write_json(
            os.path.join(stim_dir, "custom.json"),
            {
                "name": "custom",
                "electrode_positions": {
                    "Zeta": [9, 9, 9],
                    "Alpha": [1, 1, 1],
                    "Beta": [2, 2, 2],
                    "Gamma": [3, 3, 3],
                },
            },
        )
        montage = montage_sources.resolve_freehand_montage(pm, "001", "custom")
        # sorted() order: Alpha, Beta, Gamma, Zeta
        assert montage.electrode_pairs == [
            ([1, 1, 1], [2, 2, 2]),
            ([3, 3, 3], [9, 9, 9]),
        ]

    def test_too_few_electrodes_raises(self, pm: PathManager):
        m2m_dir = pm.m2m("001")
        stim_dir = os.path.join(m2m_dir, "stim_configs")
        os.makedirs(stim_dir, exist_ok=True)
        _write_json(
            os.path.join(stim_dir, "short.json"),
            {"name": "short", "electrode_positions": {"E1+": [0, 0, 0]}},
        )
        with pytest.raises(ValueError, match="fewer than 4"):
            montage_sources.resolve_freehand_montage(pm, "001", "short")

    def test_unknown_config_name_raises(self, pm: PathManager):
        m2m_dir = pm.m2m("001")
        os.makedirs(os.path.join(m2m_dir, "stim_configs"), exist_ok=True)
        with pytest.raises(ValueError, match="not found"):
            montage_sources.resolve_freehand_montage(pm, "001", "missing")

    def test_no_m2m_dir_returns_empty_list(self, pm: PathManager):
        assert montage_sources.list_freehand_configs(pm, "999") == []
