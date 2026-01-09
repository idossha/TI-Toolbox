#!/usr/bin/env simnibs_python
"""
Unit tests for sim/montage_loader.py.

Tests montage loading functionality including:
- load_montage_file(): JSON file loading and EEG net extraction
- load_flex_montages(): Flex/freehand montage loading
- parse_flex_montage(): Flex montage parsing (flex_mapped, flex_optimized, freehand_xyz)
- load_montages(): Combined loading of regular + flex montages
- Edge cases: missing files, invalid JSON, unknown montage types
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, mock_open, MagicMock
from pathlib import Path

# Ensure repo root is on sys.path so `import tit` resolves to local sources.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tit.sim.montage_loader import (
    load_montage_file,
    load_flex_montages,
    parse_flex_montage,
    load_montages
)
from tit.sim.config import MontageConfig


@pytest.mark.unit
class TestLoadMontageFile:
    """Test suite for load_montage_file() function."""

    def test_load_existing_montage_file(self, tmp_path):
        """Test loading an existing montage configuration file."""
        # Create test project structure
        project_dir = tmp_path / "test_project"
        config_dir = project_dir / "code" / "ti-toolbox" / "config"
        config_dir.mkdir(parents=True)

        montage_file = config_dir / "montage_list.json"
        test_montages = {
            "nets": {
                "GSN-HydroCel-185": {
                    "uni_polar_montages": {
                        "montage1": [["E1", "E2"], ["E3", "E4"]]
                    },
                    "multi_polar_montages": {
                        "montage2": [["E5", "E6"], ["E7", "E8"]]
                    }
                }
            }
        }

        with open(montage_file, 'w') as f:
            json.dump(test_montages, f)

        # Test loading
        result = load_montage_file(str(project_dir), "GSN-HydroCel-185")

        assert "uni_polar_montages" in result
        assert "multi_polar_montages" in result
        assert "montage1" in result["uni_polar_montages"]
        assert "montage2" in result["multi_polar_montages"]

    def test_create_default_montage_file(self, tmp_path):
        """Test creating default montage file when it doesn't exist."""
        project_dir = tmp_path / "test_project"
        config_dir = project_dir / "code" / "ti-toolbox" / "config"

        # File doesn't exist yet
        montage_file = config_dir / "montage_list.json"
        assert not montage_file.exists()

        # Should create default file
        result = load_montage_file(str(project_dir), "GSN-HydroCel-185")

        # Check file was created
        assert montage_file.exists()
        assert "uni_polar_montages" in result
        assert "multi_polar_montages" in result

    def test_missing_eeg_net(self, tmp_path):
        """Test error when requested EEG net not found."""
        project_dir = tmp_path / "test_project"
        config_dir = project_dir / "code" / "ti-toolbox" / "config"
        config_dir.mkdir(parents=True)

        montage_file = config_dir / "montage_list.json"
        test_montages = {
            "nets": {
                "GSN-HydroCel-185": {
                    "uni_polar_montages": {}
                }
            }
        }

        with open(montage_file, 'w') as f:
            json.dump(test_montages, f)

        # Missing nets are treated as empty (callers may create montages on demand)
        net_data = load_montage_file(str(project_dir), "unknown_net.csv")
        assert net_data["uni_polar_montages"] == {}
        assert net_data["multi_polar_montages"] == {}

    def test_invalid_json(self, tmp_path):
        """Test error handling for invalid JSON file."""
        project_dir = tmp_path / "test_project"
        config_dir = project_dir / "code" / "ti-toolbox" / "config"
        config_dir.mkdir(parents=True)

        montage_file = config_dir / "montage_list.json"
        with open(montage_file, 'w') as f:
            f.write("{ invalid json }")

        with pytest.raises(json.JSONDecodeError):
            load_montage_file(str(project_dir), "GSN-HydroCel-185")


@pytest.mark.unit
class TestLoadFlexMontages:
    """Test suite for load_flex_montages() function."""

    def test_load_from_file_path(self, tmp_path):
        """Test loading flex montages from explicit file path."""
        flex_file = tmp_path / "flex_montages.json"
        flex_data = [
            {
                "name": "flex1",
                "type": "flex_mapped",
                "pairs": [["E1", "E2"], ["E3", "E4"]]
            }
        ]

        with open(flex_file, 'w') as f:
            json.dump(flex_data, f)

        result = load_flex_montages(str(flex_file))

        assert len(result) == 1
        assert result[0]["name"] == "flex1"

    def test_load_from_environment(self, tmp_path):
        """Test loading flex montages from environment variable."""
        flex_file = tmp_path / "flex_montages.json"
        flex_data = [
            {
                "name": "flex1",
                "type": "flex_mapped",
                "pairs": [["E1", "E2"], ["E3", "E4"]]
            }
        ]

        with open(flex_file, 'w') as f:
            json.dump(flex_data, f)

        with patch.dict(os.environ, {'FLEX_MONTAGES_FILE': str(flex_file)}):
            result = load_flex_montages()

        assert len(result) == 1
        assert result[0]["name"] == "flex1"

    def test_empty_when_no_file(self):
        """Test returns empty list when no flex file specified."""
        with patch.dict(os.environ, {}, clear=True):
            result = load_flex_montages()

        assert result == []

    def test_handle_dict_with_montage_key(self, tmp_path):
        """Test handling flex config as dict with 'montage' key."""
        flex_file = tmp_path / "flex_montages.json"
        flex_data = {
            "montage": {
                "name": "flex1",
                "type": "flex_mapped",
                "pairs": [["E1", "E2"], ["E3", "E4"]]
            }
        }

        with open(flex_file, 'w') as f:
            json.dump(flex_data, f)

        result = load_flex_montages(str(flex_file))

        assert len(result) == 1
        assert result[0]["name"] == "flex1"

    def test_handle_single_dict(self, tmp_path):
        """Test handling flex config as single dict."""
        flex_file = tmp_path / "flex_montages.json"
        flex_data = {
            "name": "flex1",
            "type": "flex_mapped",
            "pairs": [["E1", "E2"], ["E3", "E4"]]
        }

        with open(flex_file, 'w') as f:
            json.dump(flex_data, f)

        result = load_flex_montages(str(flex_file))

        assert len(result) == 1
        assert result[0]["name"] == "flex1"


@pytest.mark.unit
class TestParseFlexMontage:
    """Test suite for parse_flex_montage() function."""

    def test_parse_flex_mapped(self):
        """Test parsing flex_mapped montage type."""
        flex_data = {
            "name": "flex_mapped_1",
            "type": "flex_mapped",
            "pairs": [["E1", "E2"], ["E3", "E4"]],
            "eeg_net": "GSN-HydroCel-185"
        }

        result = parse_flex_montage(flex_data)

        assert isinstance(result, MontageConfig)
        assert result.name == "flex_mapped_1"
        assert result.is_xyz is False
        assert result.eeg_net == "GSN-HydroCel-185"
        assert len(result.electrode_pairs) == 2
        assert result.electrode_pairs[0] == ("E1", "E2")

    def test_parse_flex_optimized(self):
        """Test parsing flex_optimized montage type (XYZ coordinates)."""
        flex_data = {
            "name": "flex_optimized_1",
            "type": "flex_optimized",
            "electrode_positions": [
                [10.0, 20.0, 30.0],
                [15.0, 25.0, 35.0],
                [20.0, 30.0, 40.0],
                [25.0, 35.0, 45.0]
            ]
        }

        result = parse_flex_montage(flex_data)

        assert isinstance(result, MontageConfig)
        assert result.name == "flex_optimized_1"
        assert result.is_xyz is True
        assert len(result.electrode_pairs) == 2
        assert result.electrode_pairs[0] == ([10.0, 20.0, 30.0], [15.0, 25.0, 35.0])

    def test_parse_freehand_xyz(self):
        """Test parsing freehand_xyz montage type (XYZ coordinates)."""
        flex_data = {
            "name": "freehand_1",
            "type": "freehand_xyz",
            "electrode_positions": [
                [5.0, 10.0, 15.0],
                [10.0, 15.0, 20.0],
                [15.0, 20.0, 25.0],
                [20.0, 25.0, 30.0]
            ]
        }

        result = parse_flex_montage(flex_data)

        assert isinstance(result, MontageConfig)
        assert result.name == "freehand_1"
        assert result.is_xyz is True
        assert len(result.electrode_pairs) == 2

    def test_unknown_montage_type(self):
        """Test error for unknown montage type."""
        flex_data = {
            "name": "unknown",
            "type": "unknown_type",
            "pairs": []
        }

        with pytest.raises(ValueError, match="Unknown flex montage type"):
            parse_flex_montage(flex_data)


@pytest.mark.unit
class TestLoadMontages:
    """Test suite for load_montages() function."""

    def test_load_regular_montages_only(self, tmp_path):
        """Test loading regular montages without flex montages."""
        project_dir = tmp_path / "test_project"
        config_dir = project_dir / "code" / "ti-toolbox" / "config"
        config_dir.mkdir(parents=True)

        montage_file = config_dir / "montage_list.json"
        test_montages = {
            "nets": {
                "GSN-HydroCel-185": {
                    "uni_polar_montages": {
                        "montage1": [["E1", "E2"], ["E3", "E4"]]
                    },
                    "multi_polar_montages": {
                        "montage2": [["E5", "E6"], ["E7", "E8"]]
                    }
                }
            }
        }

        with open(montage_file, 'w') as f:
            json.dump(test_montages, f)

        result = load_montages(
            montage_names=["montage1", "montage2"],
            project_dir=str(project_dir),
            eeg_net="GSN-HydroCel-185",
            include_flex=False
        )

        assert len(result) == 2
        assert all(isinstance(m, MontageConfig) for m in result)
        assert result[0].name == "montage1"
        assert result[1].name == "montage2"

    def test_load_with_flex_montages(self, tmp_path):
        """Test loading both regular and flex montages."""
        project_dir = tmp_path / "test_project"
        config_dir = project_dir / "code" / "ti-toolbox" / "config"
        config_dir.mkdir(parents=True)

        montage_file = config_dir / "montage_list.json"
        test_montages = {
            "nets": {
                "GSN-HydroCel-185": {
                    "uni_polar_montages": {
                        "montage1": [["E1", "E2"], ["E3", "E4"]]
                    },
                    "multi_polar_montages": {}
                }
            }
        }

        with open(montage_file, 'w') as f:
            json.dump(test_montages, f)

        # Create flex file
        flex_file = tmp_path / "flex.json"
        flex_data = [{
            "name": "flex1",
            "type": "flex_mapped",
            "pairs": [["E5", "E6"], ["E7", "E8"]],
            "eeg_net": "GSN-HydroCel-185"
        }]

        with open(flex_file, 'w') as f:
            json.dump(flex_data, f)

        with patch.dict(os.environ, {'FLEX_MONTAGES_FILE': str(flex_file)}):
            result = load_montages(
                montage_names=["montage1"],
                project_dir=str(project_dir),
                eeg_net="GSN-HydroCel-185",
                include_flex=True
            )

        assert len(result) == 2
        assert result[0].name == "montage1"
        assert result[1].name == "flex1"

    def test_freehand_mode(self, tmp_path):
        """Test is_xyz flag for freehand mode."""
        project_dir = tmp_path / "test_project"
        config_dir = project_dir / "code" / "ti-toolbox" / "config"
        config_dir.mkdir(parents=True)

        montage_file = config_dir / "montage_list.json"
        test_montages = {
            "nets": {
                "freehand": {
                    "uni_polar_montages": {
                        "montage1": [[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]]
                    },
                    "multi_polar_montages": {}
                }
            }
        }

        with open(montage_file, 'w') as f:
            json.dump(test_montages, f)

        result = load_montages(
            montage_names=["montage1"],
            project_dir=str(project_dir),
            eeg_net="freehand",
            include_flex=False
        )

        assert len(result) == 1
        assert result[0].is_xyz is True

    def test_skip_failed_flex_montages(self, tmp_path, capsys):
        """Test that failed flex montages are skipped with warning."""
        project_dir = tmp_path / "test_project"
        config_dir = project_dir / "code" / "ti-toolbox" / "config"
        config_dir.mkdir(parents=True)

        montage_file = config_dir / "montage_list.json"
        test_montages = {
            "nets": {
                "GSN-HydroCel-185": {
                    "uni_polar_montages": {},
                    "multi_polar_montages": {}
                }
            }
        }

        with open(montage_file, 'w') as f:
            json.dump(test_montages, f)

        # Create flex file with invalid montage
        flex_file = tmp_path / "flex.json"
        flex_data = [{
            "name": "bad_flex",
            "type": "unknown_type"
        }]

        with open(flex_file, 'w') as f:
            json.dump(flex_data, f)

        with patch.dict(os.environ, {'FLEX_MONTAGES_FILE': str(flex_file)}):
            result = load_montages(
                montage_names=[],
                project_dir=str(project_dir),
                eeg_net="GSN-HydroCel-185",
                include_flex=True
            )

        # Should skip bad montage and continue
        assert len(result) == 0

        # Check warning was printed
        captured = capsys.readouterr()
        assert "Warning: Failed to parse flex montage" in captured.out

    def test_empty_montage_list(self, tmp_path):
        """Test loading with empty montage list."""
        project_dir = tmp_path / "test_project"
        config_dir = project_dir / "code" / "ti-toolbox" / "config"
        config_dir.mkdir(parents=True)

        montage_file = config_dir / "montage_list.json"
        test_montages = {
            "nets": {
                "GSN-HydroCel-185": {
                    "uni_polar_montages": {},
                    "multi_polar_montages": {}
                }
            }
        }

        with open(montage_file, 'w') as f:
            json.dump(test_montages, f)

        result = load_montages(
            montage_names=[],
            project_dir=str(project_dir),
            eeg_net="GSN-HydroCel-185",
            include_flex=False
        )

        assert len(result) == 0

    def test_montage_priority(self, tmp_path):
        """Test that multi_polar is checked before uni_polar."""
        project_dir = tmp_path / "test_project"
        config_dir = project_dir / "code" / "ti-toolbox" / "config"
        config_dir.mkdir(parents=True)

        montage_file = config_dir / "montage_list.json"
        test_montages = {
            "nets": {
                "GSN-HydroCel-185": {
                    "uni_polar_montages": {
                        "montage1": [["E1", "E2"], ["E3", "E4"]]
                    },
                    "multi_polar_montages": {
                        "montage1": [["E5", "E6"], ["E7", "E8"]]  # Same name, different pairs
                    }
                }
            }
        }

        with open(montage_file, 'w') as f:
            json.dump(test_montages, f)

        result = load_montages(
            montage_names=["montage1"],
            project_dir=str(project_dir),
            eeg_net="GSN-HydroCel-185",
            include_flex=False
        )

        # Should use multi_polar version
        assert len(result) == 1
        assert result[0].electrode_pairs == ([["E5", "E6"], ["E7", "E8"]])
