#!/usr/bin/env simnibs_python
"""
High-impact tests for tit/tools/tissue_analyzer.py

We focus on robust, deterministic logic:
- labeling_LUT.txt discovery + parsing
- label name lookup / overrides
- tissue mask extraction edge cases (no tissue / no brain)
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _fake_nifti(data: np.ndarray):
    header = MagicMock()
    header.get_zooms.return_value = (1.0, 1.0, 1.0, 1.0)
    return SimpleNamespace(
        get_fdata=lambda: data,
        affine=np.eye(4),
        header=header,
    )


@pytest.mark.unit
def test_load_label_names_from_same_directory(tmp_path: Path):
    from tit.tools.tissue_analyzer import TissueAnalyzer

    nifti_path = tmp_path / "seg.nii.gz"
    nifti_path.write_text("dummy")

    lut = tmp_path / "labeling_LUT.txt"
    lut.write_text(
        "# comment\n"
        "1\tGray Matter:\t0\t0\t0\t0\n"
        "2\tWhite Matter:\t0\t0\t0\t0\n"
        "bad\tline\n"
    )

    data = np.zeros((3, 3, 3), dtype=float)
    tissue_config = {
        "name": "CSF",
        "labels": [9],
        "padding": 1,
        "color_scheme": "viridis",
        "tissue_color": "blue",
        "brain_labels": [1, 2],
    }

    with patch("tit.tools.tissue_analyzer.nib.load", return_value=_fake_nifti(data)):
        ta = TissueAnalyzer(str(nifti_path), str(tmp_path / "out"), tissue_config)

    assert ta.get_label_name(1) == "Gray Matter"
    assert ta.get_label_name(2) == "White Matter"
    assert ta.get_label_name(999) == "999"


@pytest.mark.unit
def test_set_tissue_labels_validates_and_reextracts(tmp_path: Path):
    from tit.tools.tissue_analyzer import TissueAnalyzer

    nifti_path = tmp_path / "seg.nii.gz"
    nifti_path.write_text("dummy")

    data = np.zeros((2, 2, 2), dtype=float)
    tissue_config = {
        "name": "CSF",
        "labels": [9],
        "padding": 1,
        "color_scheme": "viridis",
        "tissue_color": "blue",
        "brain_labels": [1, 2],
    }

    with patch("tit.tools.tissue_analyzer.nib.load", return_value=_fake_nifti(data)):
        ta = TissueAnalyzer(str(nifti_path), str(tmp_path / "out"), tissue_config)

    with pytest.raises(ValueError):
        ta.set_tissue_labels("not-a-list")
    with pytest.raises(ValueError):
        ta.set_tissue_labels([1, "x"])

    # Force the "re-extract" branch
    ta.all_tissue_mask = np.zeros_like(data)
    ta.data = data
    ta.extract_tissue_mask = MagicMock()
    ta.set_tissue_labels([7, 8])
    ta.extract_tissue_mask.assert_called_once()


@pytest.mark.unit
def test_extract_tissue_mask_handles_no_tissue(tmp_path: Path):
    from tit.tools.tissue_analyzer import TissueAnalyzer

    nifti_path = tmp_path / "seg.nii.gz"
    nifti_path.write_text("dummy")

    # No voxels with tissue label 9
    data = np.zeros((4, 4, 4), dtype=float)
    tissue_config = {
        "name": "CSF",
        "labels": [9],
        "padding": 1,
        "color_scheme": "viridis",
        "tissue_color": "blue",
        "brain_labels": [1, 2],
    }

    with patch("tit.tools.tissue_analyzer.nib.load", return_value=_fake_nifti(data)):
        ta = TissueAnalyzer(str(nifti_path), str(tmp_path / "out"), tissue_config)

    mask = ta.extract_tissue_mask()
    assert mask.shape == data.shape
    assert mask.sum() == 0


@pytest.mark.unit
def test_extract_tissue_mask_handles_no_brain(tmp_path: Path):
    from tit.tools.tissue_analyzer import TissueAnalyzer

    nifti_path = tmp_path / "seg.nii.gz"
    nifti_path.write_text("dummy")

    # Tissue exists (label 9), but brain labels (1,2) absent
    data = np.zeros((4, 4, 4), dtype=float)
    data[1, 1, 1] = 9
    tissue_config = {
        "name": "CSF",
        "labels": [9],
        "padding": 1,
        "color_scheme": "viridis",
        "tissue_color": "blue",
        "brain_labels": [1, 2],
    }

    with patch("tit.tools.tissue_analyzer.nib.load", return_value=_fake_nifti(data)):
        ta = TissueAnalyzer(str(nifti_path), str(tmp_path / "out"), tissue_config)

    mask = ta.extract_tissue_mask()
    assert mask.sum() == 1  # keeps all tissue when no brain found


