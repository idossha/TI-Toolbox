#!/usr/bin/env simnibs_python
"""
Unit tests for tit.sim.utils — montage file I/O, montage loading,
directory setup, and simulation orchestration helpers.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tit.sim.config import SimulationMode, Montage
from tit.sim.utils import (
    ensure_montage_file,
    load_montage_data,
    save_montage_data,
    ensure_eeg_net_entry,
    upsert_montage,
    list_montage_names,
    load_flex_montages,
    parse_flex_montage,
    load_montages,
    setup_montage_directories,
)

# ============================================================================
# Montage file CRUD
# ============================================================================


@pytest.mark.unit
class TestEnsureMontageFile:
    """ensure_montage_file creates or returns montage_list.json."""

    def test_creates_json_if_missing(self, tmp_project, init_pm):
        path = ensure_montage_file(str(tmp_project))
        assert os.path.isfile(path)
        with open(path) as f:
            data = json.load(f)
        assert data == {"nets": {}}

    def test_returns_existing_file(self, tmp_project, init_pm):
        path1 = ensure_montage_file(str(tmp_project))
        # Write extra data so we can verify it is not overwritten
        with open(path1, "w") as f:
            json.dump({"nets": {"my_net": {}}}, f)
        path2 = ensure_montage_file(str(tmp_project))
        assert path1 == path2
        with open(path2) as f:
            data = json.load(f)
        assert "my_net" in data["nets"]


@pytest.mark.unit
class TestLoadSaveMontageData:
    """Round-trip load/save through montage_list.json."""

    def test_load_returns_default_schema(self, tmp_project, init_pm):
        data = load_montage_data(str(tmp_project))
        assert data == {"nets": {}}

    def test_save_then_load_roundtrip(self, tmp_project, init_pm):
        payload = {
            "nets": {
                "GSN-256": {
                    "uni_polar_montages": {"m1": [["E1", "E2"], ["E3", "E4"]]},
                    "multi_polar_montages": {},
                }
            }
        }
        save_montage_data(str(tmp_project), payload)
        loaded = load_montage_data(str(tmp_project))
        assert loaded == payload


@pytest.mark.unit
class TestEnsureEegNetEntry:
    """ensure_eeg_net_entry adds net entry with correct sub-keys."""

    def test_adds_new_net(self, tmp_project, init_pm):
        ensure_eeg_net_entry(str(tmp_project), "GSN-256")
        data = load_montage_data(str(tmp_project))
        assert "GSN-256" in data["nets"]
        assert data["nets"]["GSN-256"] == {
            "uni_polar_montages": {},
            "multi_polar_montages": {},
        }

    def test_idempotent(self, tmp_project, init_pm):
        pd = str(tmp_project)
        ensure_eeg_net_entry(pd, "GSN-256")
        # Add a montage under the net
        upsert_montage(
            project_dir=pd,
            eeg_net="GSN-256",
            montage_name="m1",
            electrode_pairs=[["E1", "E2"], ["E3", "E4"]],
            mode="U",
        )
        # Calling ensure again should NOT wipe existing montages
        ensure_eeg_net_entry(pd, "GSN-256")
        data = load_montage_data(pd)
        assert "m1" in data["nets"]["GSN-256"]["uni_polar_montages"]


@pytest.mark.unit
class TestUpsertMontage:
    """upsert_montage writes montages under correct polarity key."""

    def test_uni_polar(self, tmp_project, init_pm):
        pd = str(tmp_project)
        upsert_montage(
            project_dir=pd,
            eeg_net="GSN-256",
            montage_name="alpha",
            electrode_pairs=[["E1", "E2"], ["E3", "E4"]],
            mode="U",
        )
        data = load_montage_data(pd)
        assert "alpha" in data["nets"]["GSN-256"]["uni_polar_montages"]

    def test_multi_polar(self, tmp_project, init_pm):
        pd = str(tmp_project)
        upsert_montage(
            project_dir=pd,
            eeg_net="GSN-256",
            montage_name="beta",
            electrode_pairs=[["E1", "E2"], ["E3", "E4"], ["E5", "E6"], ["E7", "E8"]],
            mode="M",
        )
        data = load_montage_data(pd)
        assert "beta" in data["nets"]["GSN-256"]["multi_polar_montages"]

    def test_overwrites_existing(self, tmp_project, init_pm):
        pd = str(tmp_project)
        upsert_montage(
            project_dir=pd,
            eeg_net="GSN-256",
            montage_name="m1",
            electrode_pairs=[["E1", "E2"]],
            mode="U",
        )
        upsert_montage(
            project_dir=pd,
            eeg_net="GSN-256",
            montage_name="m1",
            electrode_pairs=[["E9", "E10"]],
            mode="U",
        )
        data = load_montage_data(pd)
        assert data["nets"]["GSN-256"]["uni_polar_montages"]["m1"] == [["E9", "E10"]]


@pytest.mark.unit
class TestListMontageNames:
    """list_montage_names returns sorted names or empty list."""

    def test_returns_sorted_names(self, tmp_project, init_pm):
        pd = str(tmp_project)
        for name in ("charlie", "alpha", "bravo"):
            upsert_montage(
                project_dir=pd,
                eeg_net="GSN-256",
                montage_name=name,
                electrode_pairs=[["E1", "E2"]],
                mode="U",
            )
        result = list_montage_names(pd, "GSN-256", mode="U")
        assert result == ["alpha", "bravo", "charlie"]

    def test_empty_for_missing_net(self, tmp_project, init_pm):
        pd = str(tmp_project)
        result = list_montage_names(pd, "nonexistent_net", mode="U")
        assert result == []

    def test_empty_for_wrong_mode(self, tmp_project, init_pm):
        pd = str(tmp_project)
        upsert_montage(
            project_dir=pd,
            eeg_net="GSN-256",
            montage_name="m1",
            electrode_pairs=[["E1", "E2"]],
            mode="U",
        )
        result = list_montage_names(pd, "GSN-256", mode="M")
        assert result == []


# ============================================================================
# Montage loading (flex / named)
# ============================================================================


@pytest.mark.unit
class TestParseFlexMontage:
    """parse_flex_montage dispatches on montage type."""

    def test_flex_mapped_returns_montage_with_flex_mapped_mode(self):
        flex = {
            "name": "mapped1",
            "type": "flex_mapped",
            "pairs": [["E1", "E2"], ["E3", "E4"]],
            "eeg_net": "GSN-256.csv",
        }
        m = parse_flex_montage(flex)
        assert not m.is_xyz
        assert m.mode == Montage.Mode.FLEX_MAPPED
        assert m.name == "mapped1"
        assert m.electrode_pairs == [("E1", "E2"), ("E3", "E4")]
        assert m.eeg_net == "GSN-256.csv"

    def test_flex_optimized_returns_xyz_montage(self):
        pos = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0], [10.0, 11.0, 12.0]]
        flex = {
            "name": "opt1",
            "type": "flex_optimized",
            "electrode_positions": pos,
        }
        m = parse_flex_montage(flex)
        assert m.is_xyz
        assert m.mode == Montage.Mode.FLEX_FREE
        assert m.name == "opt1"
        assert len(m.electrode_pairs) == 2

    def test_freehand_xyz_returns_freehand_montage(self):
        pos = [[0, 0, 100], [0, 0, -100], [50, 0, 0], [-50, 0, 0]]
        flex = {
            "name": "fh1",
            "type": "freehand_xyz",
            "electrode_positions": pos,
        }
        m = parse_flex_montage(flex)
        assert m.is_xyz
        assert m.mode == Montage.Mode.FREEHAND
        assert m.name == "fh1"

    def test_unknown_type_raises_value_error(self):
        flex = {"name": "bad", "type": "unknown_type"}
        with pytest.raises(ValueError, match="Unknown flex montage type"):
            parse_flex_montage(flex)


@pytest.mark.unit
class TestLoadFlexMontages:
    """load_flex_montages reads from JSON file or returns []."""

    def test_valid_list_file(self, tmp_path):
        flex_file = str(tmp_path / "flex.json")
        data = [
            {"name": "a", "type": "flex_mapped", "pairs": [["E1", "E2"], ["E3", "E4"]]},
            {"name": "b", "type": "flex_mapped", "pairs": [["E5", "E6"], ["E7", "E8"]]},
        ]
        with open(flex_file, "w") as f:
            json.dump(data, f)
        result = load_flex_montages(flex_file)
        assert len(result) == 2
        assert result[0]["name"] == "a"

    def test_valid_dict_file(self, tmp_path):
        flex_file = str(tmp_path / "flex.json")
        data = {"montage": {"name": "single", "type": "flex_mapped"}}
        with open(flex_file, "w") as f:
            json.dump(data, f)
        result = load_flex_montages(flex_file)
        assert len(result) == 1
        assert result[0]["name"] == "single"

    def test_missing_file_returns_empty(self):
        result = load_flex_montages("/nonexistent/path/flex.json")
        assert result == []

    def test_none_returns_empty(self):
        # Clear env var to ensure no fallback
        with patch.dict(os.environ, {}, clear=True):
            result = load_flex_montages(None)
            assert result == []


@pytest.mark.unit
class TestLoadMontages:
    """load_montages loads named montages from montage_list.json."""

    def test_loads_named_montages_with_montage_mode(self, tmp_project, init_pm):
        pd = str(tmp_project)
        pairs = [["E1", "E2"], ["E3", "E4"]]
        upsert_montage(
            project_dir=pd,
            eeg_net="GSN-256.csv",
            montage_name="m1",
            electrode_pairs=pairs,
            mode="U",
        )
        # Disable flex loading to isolate named montages
        montages = load_montages(["m1"], pd, "GSN-256.csv", include_flex=False)
        assert len(montages) == 1
        assert not montages[0].is_xyz
        assert montages[0].mode == Montage.Mode.NET
        assert montages[0].name == "m1"
        assert montages[0].electrode_pairs == pairs

    def test_skips_missing_names(self, tmp_project, init_pm):
        pd = str(tmp_project)
        upsert_montage(
            project_dir=pd,
            eeg_net="GSN-256.csv",
            montage_name="exists",
            electrode_pairs=[["E1", "E2"]],
            mode="U",
        )
        montages = load_montages(
            ["exists", "does_not_exist"], pd, "GSN-256.csv", include_flex=False
        )
        assert len(montages) == 1
        assert montages[0].name == "exists"

    def test_freehand_net_returns_freehand_montage(self, tmp_project, init_pm):
        pd = str(tmp_project)
        coords = [[[1, 2, 3], [4, 5, 6]], [[7, 8, 9], [10, 11, 12]]]
        upsert_montage(
            project_dir=pd,
            eeg_net="freehand",
            montage_name="fh",
            electrode_pairs=coords,
            mode="U",
        )
        montages = load_montages(["fh"], pd, "freehand", include_flex=False)
        assert len(montages) == 1
        assert montages[0].is_xyz
        assert montages[0].mode == Montage.Mode.FREEHAND


# ============================================================================
# Directory setup
# ============================================================================


@pytest.mark.unit
class TestSetupMontageDirectories:
    """setup_montage_directories creates BIDS output structure."""

    def test_ti_mode_creates_correct_dirs(self, tmp_path):
        montage_dir = str(tmp_path / "test_montage")
        dirs = setup_montage_directories(montage_dir, SimulationMode.TI)

        # All values should be existing directories
        for key, path in dirs.items():
            assert os.path.isdir(path), f"{key} directory not created: {path}"

        # Expected TI keys
        expected_keys = {
            "montage_dir",
            "hf_dir",
            "hf_mesh",
            "hf_niftis",
            "hf_analysis",
            "ti_mesh",
            "ti_niftis",
            "ti_surface_overlays",
            "ti_montage_imgs",
            "documentation",
        }
        assert set(dirs.keys()) == expected_keys

    def test_mti_mode_creates_extra_dirs(self, tmp_path):
        montage_dir = str(tmp_path / "test_montage")
        dirs = setup_montage_directories(montage_dir, SimulationMode.MTI)

        # Should have all TI keys plus mti_* keys
        assert "mti_mesh" in dirs
        assert "mti_niftis" in dirs
        assert "mti_montage_imgs" in dirs

        for key in ("mti_mesh", "mti_niftis", "mti_montage_imgs"):
            assert os.path.isdir(dirs[key])

    def test_returns_correct_paths(self, tmp_path):
        montage_dir = str(tmp_path / "my_montage")
        dirs = setup_montage_directories(montage_dir, SimulationMode.TI)

        assert dirs["montage_dir"] == montage_dir
        assert dirs["hf_dir"] == os.path.join(montage_dir, "high_Frequency")
        assert dirs["ti_mesh"] == os.path.join(montage_dir, "TI", "mesh")
        assert dirs["documentation"] == os.path.join(montage_dir, "documentation")

    def test_idempotent(self, tmp_path):
        montage_dir = str(tmp_path / "test_montage")
        dirs1 = setup_montage_directories(montage_dir, SimulationMode.TI)
        dirs2 = setup_montage_directories(montage_dir, SimulationMode.TI)
        assert dirs1 == dirs2
